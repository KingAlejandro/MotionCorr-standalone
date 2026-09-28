#!/usr/bin/env python3
"""Compare two already-produced MotionCorr output trees, byte for byte.

Unlike compare_cpu_arms.py this does not run the binaries -- it compares trees that
already exist, which is what the native GPU controls produce.

Normalisation, each declared rather than silently applied:
  * each arm's own output root is substituted out of text products, because both arms
    necessarily write their own path into STAR, log, EPS and .lst files;
  * lines carrying a measured duration are dropped -- the wall-time line and the
    per-stage GPU profile timings. These are timings, they are not reproducible, and
    no timing claim is being made from these runs;
  * PDFs are reported but not compared: ghostscript stamps a creation date;
  * MRC label blocks are reported separately from the rest of the header, because they
    carry a creation timestamp that is never reproducible.
Everything else -- MRC pixel payloads, the first 224 header bytes, STAR and EPS
content -- is compared exactly, and the pixel total is reported so a zero-file or
one-movie comparison cannot pass unnoticed.

A negative control runs afterwards: one pixel bit and one STAR character are perturbed
in a copy of the candidate tree and the comparator must report exactly those two files.

Usage: compare_output_trees.py <base_dir> <cand_dir> [--expect-images N]
"""
import hashlib
import shutil
import struct
import sys
from pathlib import Path

SKIP_SUFFIXES = {".pdf"}


TIMING_MARKERS = (
    "Full movie wall time",
    "execution time:",
    "transfer time:",
    "Total GPU alignment time:",
    "Kernel:",
    " ms",
    '~~(,_,"',   # RELION's progress bar, which prints elapsed and estimated seconds
)


def _is_timing(line):
    return any(m in line for m in TIMING_MARKERS)


def normalise_text(raw, root):
    text = raw.decode("latin-1").replace(str(root), "<OUTROOT>")
    return "\n".join(l for l in text.split("\n") if not _is_timing(l))


def compare(b, c, b_root=None, c_root=None, verbose=True):
    b_root = b_root or b
    c_root = c_root or c
    bf = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    cf = sorted(p.relative_to(c) for p in c.rglob("*") if p.is_file())
    if bf != cf:
        print("FILE SET DIFFERS")
        print("  base only:", sorted(set(bf) - set(cf))[:10])
        print("  cand only:", sorted(set(cf) - set(bf))[:10])
        return (1, 0, 0, 0)
    if not bf:
        print("FAIL no output files: a zero-file comparison proves nothing")
        return (1, 0, 0, 0)

    diff = images = pixels = compared = 0
    for rel in bf:
        x = (b / rel).read_bytes()
        y = (c / rel).read_bytes()
        if rel.suffix in SKIP_SUFFIXES:
            continue
        compared += 1
        if rel.suffix == ".mrc":
            images += 1
            hx, hy = x[:1024], y[:1024]
            nx, ny, nz, mode = struct.unpack("<4i", hx[:16])
            pixels += nx * ny * max(nz, 1)
            head_eq = hx[:224] == hy[:224]
            label_eq = hx[224:1024] == hy[224:1024]
            data_eq = x[1024:] == y[1024:]
            if verbose and (not head_eq or not data_eq):
                print("  DIFF %s %dx%dx%d header=%s labels=%s payload=%s"
                      % (rel, nx, ny, nz, head_eq, label_eq, data_eq))
            if not (head_eq and data_eq):
                diff += 1
        else:
            if normalise_text(x, b_root) != normalise_text(y, c_root):
                if verbose:
                    print("  DIFF %s (%d vs %d bytes)" % (rel, len(x), len(y)))
                diff += 1
    return (diff, images, pixels, compared)


def main():
    base, cand = Path(sys.argv[1]), Path(sys.argv[2])
    expect = None
    if "--expect-images" in sys.argv:
        expect = int(sys.argv[sys.argv.index("--expect-images") + 1])

    print("=== base vs candidate ===")
    diff, images, pixels, compared = compare(base, cand)
    print("\n%d files compared, %d MRC images, %d pixels, %d differing"
          % (compared, images, pixels, diff))
    if compared == 0 or images == 0 or pixels == 0:
        print("FAIL nothing substantive was compared")
        return 1
    if expect is not None and images != expect:
        print("FAIL expected %d MRC images, compared %d -- the run did not cover the "
              "dataset it claims to" % (expect, images))
        return 1

    print("\n=== negative control: perturb one pixel and one STAR character ===")
    m = cand.parent / (cand.name + "_mutant")
    if m.exists():
        shutil.rmtree(m)
    shutil.copytree(cand, m)
    mrcs = sorted(m.rglob("*.mrc"))
    stars = [p for p in sorted(m.rglob("*.star")) if p.stat().st_size > 0]
    if not mrcs or not stars:
        print("FAIL negative control has nothing to perturb")
        return 1
    raw = bytearray(mrcs[0].read_bytes())
    raw[1024] ^= 0x01
    mrcs[0].write_bytes(bytes(raw))
    s = bytearray(stars[0].read_bytes())
    s[-2] = ord("Z") if s[-2] != ord("Z") else ord("Y")
    stars[0].write_bytes(bytes(s))
    ndiff, _, _, _ = compare(base, m, c_root=cand, verbose=False)
    shutil.rmtree(m)
    # The perturbation must add exactly two differing files on top of whatever already
    # differed. Asserting a bare 2 would only be right when the trees start identical.
    expected = diff + 2
    print("negative control reported %d differing files (expected %d = %d already "
          "differing + 2 perturbed)" % (ndiff, expected, diff))
    if ndiff != expected:
        print("FAIL the comparison cannot detect a change it is supposed to detect")
        return 1

    if diff:
        print("\nFAIL outputs differ")
        return 1
    print("\nPASS outputs identical over %d images / %d pixels, and the comparison "
          "is able to fail" % (images, pixels))
    return 0


if __name__ == "__main__":
    sys.exit(main())
