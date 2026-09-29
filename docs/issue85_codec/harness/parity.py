#!/usr/bin/env python3
"""Issue #85 codec arms: complete cross-arm product identity.

Compares every product of two MotionCorr output trees produced by the same
binary under two LibTIFF builds (libdeflate vs zlib Deflate subcodec).

Three layers, because each sees something the others cannot:
  1. every .mrc: data region from byte 1024 byte-for-byte, plus the 1024-byte
     header with only the MRC label timestamp normalized;
  2. every .star / .log: text identity after normalizing run paths and dates;
  3. the project's own acceptance gate (tools/compare_motioncorr.py --gate
     exact) on the corrected image + motion STAR of each movie.
Each layer has its own negative control, because one mutation does not
exercise all three: --mutate-pixel flips one float in one corrected image
(MRC bytes + gate), --mutate-star perturbs one shift in one motion STAR
(text + gate). Both run on a copy, and both must turn the run red.
"""
import argparse, json, re, shutil, struct, subprocess, sys, tempfile
from pathlib import Path

# RELION stamps the MRC label block with 'Relion    dd-Mon-yy  HH:MM:SS'.
TS = re.compile(rb"\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}")
DATE_TXT = re.compile(r"\d{2}-[A-Za-z]{3}-\d{2,4}\s+\d{2}:\d{2}:\d{2}")
# Per-movie logs record their own elapsed time, which is not a product value.
ELAPSED_TXT = re.compile(r"(wall time:)\s*[\d.]+\s*s")


def _is_num(tok):
    try:
        float(tok)
        return True
    except ValueError:
        return False


def norm_header(h):
    """Blank the 10 x 80-byte MRC labels' embedded run timestamps only."""
    return TS.sub(b"<TS>", h)


def cmp_mrc(a, b):
    ra, rb = a.read_bytes(), b.read_bytes()
    out = {"file": a.name, "size_a": len(ra), "size_b": len(rb)}
    if len(ra) != len(rb):
        out["verdict"] = "SIZE_DIFF"
        return out
    out["data_identical"] = ra[1024:] == rb[1024:]
    out["header_identical_raw"] = ra[:1024] == rb[:1024]
    out["header_identical_normalized"] = norm_header(ra[:1024]) == norm_header(rb[:1024])
    if not out["data_identical"]:
        out["first_diff_byte"] = next(i for i in range(1024, len(ra)) if ra[i] != rb[i])
        out["n_diff_bytes"] = sum(1 for x, y in zip(ra[1024:], rb[1024:]) if x != y)
    out["verdict"] = "OK" if (out["data_identical"] and out["header_identical_normalized"]) else "DIFF"
    return out


def cmp_text(a, b, ref_root, test_root):
    def norm(path, root):
        t = path.read_text(errors="replace").replace(str(root), "<ROOT>")
        return ELAPSED_TXT.sub(r"\1 <ELAPSED>", DATE_TXT.sub("<TS>", t))
    ta, tb = norm(a, ref_root), norm(b, test_root)
    return {"file": a.name, "verdict": "OK" if ta == tb else "DIFF"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--test", type=Path, required=True)
    ap.add_argument("--compare-tool", type=Path, required=True)
    ap.add_argument("--json-out", type=Path, required=True)
    ap.add_argument("--mutate-pixel", action="store_true",
                    help="negative control: flip one float of one corrected image")
    ap.add_argument("--mutate-star", action="store_true",
                    help="negative control: perturb one shift value in one motion STAR")
    args = ap.parse_args()

    test_root = args.test
    # Text normalisation always strips the ORIGINAL test root: a mutated copy
    # keeps the paths its logs were written with, and normalising against the
    # temporary directory instead would make every log differ for no reason.
    text_root = args.test
    tmp = None
    mutated = None
    if args.mutate_pixel or args.mutate_star:
        tmp = tempfile.mkdtemp(prefix="mc85_mut_")
        test_root = Path(tmp) / "test"
        shutil.copytree(args.test, test_root)
    if args.mutate_pixel:
        target = sorted(test_root.glob("**/*_frameImage.mrc"))[0]
        raw = bytearray(target.read_bytes())
        off = 1024 + 4 * 12345
        bits = struct.unpack_from("<I", raw, off)[0]
        struct.pack_into("<I", raw, off, bits ^ 1)   # one ULP
        mutated = f"{target.name}@float12345 (1 ULP)"
    if args.mutate_star:
        target = sorted(test_root.glob("**/*_frameImage.star"))[0]
        lines = target.read_text().splitlines()
        for i, line in enumerate(lines):
            parts = line.split()
            if len(parts) == 3 and all(_is_num(x) for x in parts):
                parts[1] = "%.6f" % (float(parts[1]) + 0.001)
                lines[i] = " ".join(parts)
                mutated = f"{target.name}@shift line {i} +0.001 px"
                break
        assert mutated, "no motion row found to perturb"
        target.write_text("\n".join(lines) + "\n")
    if args.mutate_pixel:
        sorted(test_root.glob("**/*_frameImage.mrc"))[0].write_bytes(bytes(raw))

    report = {"ref": str(args.ref), "test": str(args.test), "mutated": mutated,
              "mrc": [], "text": [], "gate": [], "missing": []}

    ref_mrc = sorted(p.relative_to(args.ref) for p in args.ref.glob("**/*.mrc"))
    test_mrc = sorted(p.relative_to(test_root) for p in test_root.glob("**/*.mrc"))
    if ref_mrc != test_mrc:
        report["missing"] = [str(p) for p in set(ref_mrc) ^ set(test_mrc)]
    for rel in ref_mrc:
        if rel in test_mrc:
            report["mrc"].append(cmp_mrc(args.ref / rel, test_root / rel))

    for pat in ("**/*.star", "**/*.log"):
        for p in sorted(args.ref.glob(pat)):
            rel = p.relative_to(args.ref)
            q = test_root / rel
            if q.exists():
                report["text"].append(cmp_text(p, q, args.ref, text_root))
            else:
                report["missing"].append(str(rel))

    for rel in ref_mrc:
        if rel.name.endswith("_frameImage.mrc"):
            star = rel.with_name(rel.name.replace(".mrc", ".star"))
            cmd = [sys.executable, str(args.compare_tool),
                   "--ref-mrc", str(args.ref / rel), "--test-mrc", str(test_root / rel),
                   "--ref-star", str(args.ref / star), "--test-star", str(test_root / star),
                   "--gate", "exact", "--require-complete-coverage", "--json"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            try:
                j = json.loads(r.stdout)
                passed = j.get("overall_status") == "PASS"
            except Exception:
                j, passed = {"stdout": r.stdout[-400:], "stderr": r.stderr[-400:]}, None
            report["gate"].append({"movie": rel.name, "rc": r.returncode, "passed": passed})

    n_mrc_bad = sum(1 for m in report["mrc"] if m["verdict"] != "OK")
    n_txt_bad = sum(1 for t in report["text"] if t["verdict"] != "OK")
    n_gate_bad = sum(1 for g in report["gate"] if g["passed"] is not True)
    report["summary"] = {"mrc_files": len(report["mrc"]), "mrc_differing": n_mrc_bad,
                         "text_files": len(report["text"]), "text_differing": n_txt_bad,
                         "gate_movies": len(report["gate"]), "gate_failing": n_gate_bad,
                         "missing": len(report["missing"])}
    allclean = (n_mrc_bad == 0 and n_txt_bad == 0 and n_gate_bad == 0 and not report["missing"])
    report["verdict"] = "IDENTICAL" if allclean else "DIFFERENT"
    args.json_out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"]), report["verdict"])
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
        # Negative control inverts the expectation.
        return 0 if report["verdict"] == "DIFFERENT" else 1
    return 0 if allclean else 1


if __name__ == "__main__":
    sys.exit(main())
