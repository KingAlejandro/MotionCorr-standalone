#!/usr/bin/env python3
"""Complete-tree comparison for one option row.

docs/issue85_laneC/compare_output_trees.py is the stricter gate, but it pins the
product inventory to the default one, so it cannot be used for rows that change
what is produced (--save_noDW, --even_odd_split, a power spectrum, a different
patch grid). This compares two trees of WHATEVER shape, and requires the shapes
to be identical:

  inventory   every relative path present in one arm must be present in the other
  .mrc        header (acquisition timestamp masked), extended header and payload
  .star/.log/ text, with the output root spelled away and measured-duration lines
  .eps/.txt   dropped, since those are not expected to reproduce
  .pdf        inventoried only -- ghostscript stamps dates, and the content check
              is not claimed
  other       raw bytes

The timestamp mask and the timing-line list are the same ones the stricter tool
uses, so the two agree on what "the same output" means.
"""
import argparse, hashlib, json, re, sys
from pathlib import Path

SKIP_CONTENT = {".pdf"}
TEXT_SUFFIXES = {".log", ".star", ".eps", ".lst", ".txt"}
TIMING_MARKERS = ("Full movie wall time", "execution time:", "transfer time:",
                  "Total GPU alignment time:", "Kernel:", " ms", '~~(,_,"')
MRC_HEADER_BYTES = 1024
MRC_NSYMBT_OFFSET = 92
TIMESTAMP = re.compile(rb"(?<=Relion    )[0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}")
TIMESTAMP_MASK = b"00-XXX-00  00:00:00"


def mrc_parts(path):
    raw = path.read_bytes()
    if len(raw) < MRC_HEADER_BYTES:
        return ("short", hashlib.sha256(raw).hexdigest(), "", "")
    header = bytearray(raw[:MRC_HEADER_BYTES])
    nsymbt = int.from_bytes(header[MRC_NSYMBT_OFFSET:MRC_NSYMBT_OFFSET + 4], "little", signed=True)
    masked = TIMESTAMP.sub(TIMESTAMP_MASK, bytes(header))
    ext = raw[MRC_HEADER_BYTES:MRC_HEADER_BYTES + max(0, nsymbt)]
    payload = raw[MRC_HEADER_BYTES + max(0, nsymbt):]
    return ("ok", hashlib.sha256(masked).hexdigest(),
            hashlib.sha256(ext).hexdigest(), hashlib.sha256(payload).hexdigest())


def normalise_text(root, raw):
    text = raw.decode("latin-1")
    for spelling in {str(root), str(Path(root).resolve())}:
        text = text.replace(spelling, "<OUTROOT>")
    return "\n".join(l for l in text.split("\n")
                     if not any(m in l for m in TIMING_MARKERS)).encode("latin-1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--label", default="")
    ap.add_argument("--require-mrc", type=int, default=0,
                    help="Fail unless at least N .mrc products are present in BOTH arms. "
                         "Two arms that both produced nothing compare equal, which is "
                         "not evidence about either of them.")
    ap.add_argument("--rc", type=int, action="append", default=[],
                    help="Exit status of each arm's run; a non-zero one fails the row.")
    o = ap.parse_args()

    def inv(root):
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    b_files, c_files = inv(o.base), inv(o.candidate)
    report = {"label": o.label, "base": str(o.base), "candidate": str(o.candidate),
              "base_files": len(b_files), "candidate_files": len(c_files),
              "arm_exit_status": o.rc, "require_mrc": o.require_mrc}
    b_mrc = sum(1 for f in b_files if f.endswith(".mrc"))
    c_mrc = sum(1 for f in c_files if f.endswith(".mrc"))
    if any(rc != 0 for rc in o.rc):
        report.update(status="FAIL", reason=f"an arm exited non-zero: {o.rc}")
    elif min(b_mrc, c_mrc) < o.require_mrc:
        report.update(status="FAIL",
                      reason=f"only {b_mrc}/{c_mrc} MRC products, need {o.require_mrc}; "
                             "two empty trees are not a comparison")
    elif b_files != c_files:
        report.update(status="FAIL", reason="inventory differs",
                      base_only=sorted(b_files - c_files)[:20],
                      candidate_only=sorted(c_files - b_files)[:20])
    else:
        different, counted = [], {"mrc": 0, "star": 0, "text": 0, "other": 0, "pdf": 0}
        for rel in sorted(b_files):
            bp, cp = o.base / rel, o.candidate / rel
            suffix = Path(rel).suffix.lower()
            if suffix in SKIP_CONTENT:
                counted["pdf"] += 1
                continue
            if suffix == ".mrc":
                equal = mrc_parts(bp) == mrc_parts(cp)
                counted["mrc"] += 1
            elif suffix in TEXT_SUFFIXES:
                equal = normalise_text(o.base, bp.read_bytes()) == \
                        normalise_text(o.candidate, cp.read_bytes())
                counted["star" if suffix == ".star" else "text"] += 1
            else:
                equal = bp.read_bytes() == cp.read_bytes()
                counted["other"] += 1
            if not equal:
                different.append(rel)
        report.update(status="PASS" if not different else "FAIL",
                      compared=counted, different_files=different[:40],
                      n_different=len(different))
    print(f"{report['status']:4s} {o.label}  files={len(b_files)} "
          f"{report.get('compared', '')} diff={report.get('n_different', '-')}"
          f" {report.get('reason', '')}")
    for rel in report.get("different_files", [])[:10]:
        print(f"   DIFF {rel}")
    for rel in report.get("base_only", [])[:5]:
        print(f"   BASE-ONLY {rel}")
    for rel in report.get("candidate_only", [])[:5]:
        print(f"   CAND-ONLY {rel}")
    if o.json_out:
        o.json_out.write_text(json.dumps(report, indent=1))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
