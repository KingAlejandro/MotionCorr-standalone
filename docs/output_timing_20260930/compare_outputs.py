#!/usr/bin/env python3
"""Byte-level equivalence check between two MotionCorr output directories.

Whole-file hashing gives false failures here: the MRC header carries a
strftime label at offset 224 and Ghostscript stamps /CreationDate and a
time-derived /ID into every PDF. So each product class is compared on the part
that is supposed to be identical:

  .mrc   bytes 0-223 (which covers amin/amax/amean at 76/80/84 and arms at
         216) and the payload from 1024 on, exactly. Bytes 224-1023 are the
         label; reported, never asserted.
  .star / .eps / .lst   exact bytes.
  .log   exact after dropping the lines that carry a measured duration.
  .pdf   page count and the rendered raster of every page, via Ghostscript.
         Never bytes.

Exit status is 0 only if every asserted comparison matched.
"""
import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Per-movie .log lines that carry a measured duration. The unit list has to
# include ms: the CUDA path reports kernel, cuFFT and transfer times in
# milliseconds, and those differ run to run on identical inputs.
TIMED_LOG_LINE = re.compile(
    r"(wall time|elapsed|took"
    r"|[\d.]+\s*(?:ms|us|µs|ns|s|sec|secs|second|seconds|minutes)\b)",
    re.IGNORECASE)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def compare_mrc(a: Path, b: Path):
    ra, rb = a.read_bytes(), b.read_bytes()
    if len(ra) != len(rb):
        return False, f"size {len(ra)} vs {len(rb)}"
    if len(ra) < 1024:
        return False, f"shorter than an MRC header ({len(ra)} B)"
    notes = []
    ok = True
    if ra[:224] != rb[:224]:
        diff = sum(x != y for x, y in zip(ra[:224], rb[:224]))
        first = next(i for i in range(224) if ra[i] != rb[i])
        ok = False
        notes.append(f"core header differs in {diff} B, first at offset {first}")
    if ra[1024:] != rb[1024:]:
        diff = sum(x != y for x, y in zip(ra[1024:], rb[1024:]))
        ok = False
        notes.append(f"payload differs in {diff} B")
    label_diff = sum(x != y for x, y in zip(ra[224:1024], rb[224:1024]))
    notes.append(f"label bytes 224-1023 differ in {label_diff} B (not asserted)")
    return ok, "; ".join(notes)


def compare_exact(a: Path, b: Path):
    ra, rb = a.read_bytes(), b.read_bytes()
    if ra == rb:
        return True, f"identical, {len(ra)} B"
    return False, f"differ: {sha(ra)[:16]} vs {sha(rb)[:16]} ({len(ra)} vs {len(rb)} B)"


def compare_log(a: Path, b: Path):
    def strip(p):
        return [l for l in p.read_text(errors="replace").splitlines()
                if not TIMED_LOG_LINE.search(l)]
    la, lb = strip(a), strip(b)
    if la == lb:
        return True, f"identical after dropping timed lines ({len(la)} lines kept)"
    # Report the first positional divergence rather than set differences: a
    # single inserted line otherwise prints as dozens of "only in" entries.
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return False, f"differ from line {i + 1}: ref {x!r} vs test {y!r}"
    return False, f"differ in length: {len(la)} vs {len(lb)} kept lines"


def render_pdf(path: Path, outdir: Path, tag: str):
    """Rasterise every page. Returns (page_hashes, error)."""
    pattern = str(outdir / f"{tag}-%03d.ppm")
    proc = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=ppmraw",
         "-r72", f"-sOutputFile={pattern}", str(path)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return None, f"gs failed: {proc.stderr.strip()[:200]}"
    pages = sorted(outdir.glob(f"{tag}-*.ppm"))
    return [sha(p.read_bytes()) for p in pages], None


def compare_pdf(a: Path, b: Path, scratch: Path):
    ha, ea = render_pdf(a, scratch, "ref")
    hb, eb = render_pdf(b, scratch, "test")
    if ea or eb:
        return False, f"ref: {ea}; test: {eb}"
    if len(ha) != len(hb):
        return False, f"{len(ha)} pages vs {len(hb)}"
    bad = [i for i, (x, y) in enumerate(zip(ha, hb)) if x != y]
    if bad:
        return False, f"{len(bad)} of {len(ha)} rendered pages differ (first: page {bad[0] + 1})"
    return True, f"{len(ha)} rendered pages identical"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", type=Path)
    ap.add_argument("test", type=Path)
    ap.add_argument("--quiet-ok", action="store_true",
                    help="only print failures and the summary")
    args = ap.parse_args()

    ref_files = {p.relative_to(args.ref) for p in args.ref.rglob("*") if p.is_file()}
    test_files = {p.relative_to(args.test) for p in args.test.rglob("*") if p.is_file()}

    failures = []
    if ref_files != test_files:
        for missing in sorted(ref_files - test_files):
            failures.append(f"MISSING in test: {missing}")
        for extra in sorted(test_files - ref_files):
            failures.append(f"EXTRA in test: {extra}")

    counts = {}
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        for rel in sorted(ref_files & test_files):
            a, b = args.ref / rel, args.test / rel
            suffix = rel.suffix.lower()
            if suffix in (".mrc", ".mrcs"):
                kind, (ok, note) = "mrc", compare_mrc(a, b)
            elif suffix == ".pdf":
                for f in scratch.glob("*.ppm"):
                    f.unlink()
                kind, (ok, note) = "pdf", compare_pdf(a, b, scratch)
            elif suffix == ".log":
                kind, (ok, note) = "log", compare_log(a, b)
            else:
                kind, (ok, note) = suffix.lstrip(".") or "noext", compare_exact(a, b)
            counts.setdefault(kind, [0, 0])
            counts[kind][0 if ok else 1] += 1
            if not ok:
                failures.append(f"DIFF {rel}: {note}")
            elif not args.quiet_ok:
                print(f"  ok   {rel}: {note}")

    print("\n--- summary ---")
    for kind in sorted(counts):
        ok, bad = counts[kind]
        print(f"  {kind:6s} {ok:4d} matched, {bad:4d} differ")
    for f in failures:
        print(f"  {f}")
    print(f"VERDICT: {'MATCH' if not failures else 'MISMATCH (' + str(len(failures)) + ')'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
