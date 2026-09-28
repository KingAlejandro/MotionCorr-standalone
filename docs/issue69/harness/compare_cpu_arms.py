#!/usr/bin/env python3
"""Same-backend CPU output control for issue #69.

Runs the base and candidate binaries on the repository's own synthetic fixture with the
invocation tests/test_synthetic_regression.py uses, then compares every produced file.

Normalisation, each declared rather than silently applied:
  * the arm's own output root is substituted in text products, because both arms
    necessarily write their own path into STAR, log, EPS and .lst files;
  * the "Full movie wall time" line in the log is dropped;
  * PDFs are reported but not compared: ghostscript stamps a creation date, and the
    known PDF difference is preserved rather than hidden;
  * MRC label blocks are reported separately from the rest of the header, because they
    carry a creation timestamp that is never reproducible.
Everything else -- MRC pixel payloads, the first 224 header bytes, STAR and EPS
content -- is compared exactly.

A negative control runs afterwards: it perturbs one pixel and one STAR character in a
copy of the candidate output and requires the comparator to report both. A comparison
that cannot fail proves nothing.

Usage: compare_cpu_arms.py <base_binary> <cand_binary> <movie> <workdir>
"""
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

SKIP_SUFFIXES = {".pdf"}


def run(binary, movie, out):
    out.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary.resolve()), "--i", str(movie.resolve()), "--o", str(out.resolve()),
           "--use_own", "--j", "1", "--dose_weighting", "--dose_per_frame", "1.0",
           "--voltage", "300", "--angpix", "1.0", "--patch_x", "3", "--patch_y", "3",
           "--bfactor", "150"]
    r = subprocess.run(cmd, cwd=str(out), capture_output=True, text=True)
    if r.returncode != 0:
        print("STDERR:", r.stderr[-3000:])
        raise SystemExit("run failed rc=%d" % r.returncode)


def normalise_text(raw, root):
    text = raw.decode("latin-1").replace(str(root), "<OUTROOT>")
    return "\n".join(l for l in text.split("\n") if "Full movie wall time" not in l)


def compare(b, c, verbose=True, b_root=None, c_root=None):
    """Returns (n_diff, n_images, n_pixels, n_compared). Prints a per-file line.

    b_root/c_root override the path substituted out of text products, so a copied
    tree is still normalised against the root that produced it.
    """
    b_root = b_root or b
    c_root = c_root or c
    bf = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    cf = sorted(p.relative_to(c) for p in c.rglob("*") if p.is_file())
    if bf != cf:
        print("FILE SET DIFFERS")
        print(" base only:", sorted(set(bf) - set(cf)))
        print(" cand only:", sorted(set(cf) - set(bf)))
        return (1, 0, 0, 0)
    if not bf:
        print("FAIL no output files: a zero-file comparison proves nothing")
        return (1, 0, 0, 0)

    diff = images = pixels = compared = 0
    for rel in bf:
        x = (b / rel).read_bytes()
        y = (c / rel).read_bytes()
        if rel.suffix in SKIP_SUFFIXES:
            if verbose:
                print("  %-44s %8d bytes  not compared (ghostscript creation date)"
                      % (str(rel), len(x)))
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
            if verbose:
                print("  %-44s %dx%dx%d mode%d header=%s labels=%s payload=%s sha=%s"
                      % (str(rel), nx, ny, nz, mode,
                         "=" if head_eq else "DIFF",
                         "=" if label_eq else "differ(timestamp)",
                         "=" if data_eq else "DIFF",
                         hashlib.sha256(x[1024:]).hexdigest()[:16]))
            if not (head_eq and data_eq):
                diff += 1
        else:
            eq = normalise_text(x, b_root) == normalise_text(y, c_root)
            if verbose:
                print("  %-44s %8d bytes  %s  sha=%s"
                      % (str(rel), len(x), "=" if eq else "DIFF",
                         hashlib.sha256(normalise_text(x, b_root).encode("latin-1")).hexdigest()[:16]))
            if not eq:
                diff += 1
    return (diff, images, pixels, compared)


def main():
    base, cand, movie, work = (Path(a) for a in sys.argv[1:5])
    b, c = work / "base", work / "cand"
    run(base, movie, b)
    run(cand, movie, c)

    print("=== base vs candidate ===")
    diff, images, pixels, compared = compare(b, c)
    print("\n%d files compared, %d MRC images, %d pixels, %d differing"
          % (compared, images, pixels, diff))
    if compared == 0 or images == 0 or pixels == 0:
        print("FAIL nothing substantive was compared")
        return 1

    # Negative control: the comparator must be able to see a real change.
    print("\n=== negative control: perturb one pixel and one STAR character ===")
    m = work / "mutant"
    if m.exists():
        shutil.rmtree(m)
    shutil.copytree(c, m)
    mrcs = sorted(m.rglob("*.mrc"))
    stars = [p for p in sorted(m.rglob("*.star")) if p.stat().st_size > 0]
    if not mrcs or not stars:
        print("FAIL negative control has nothing to perturb")
        return 1
    raw = bytearray(mrcs[0].read_bytes())
    raw[1024] ^= 0x01                      # one bit of one float32 pixel
    mrcs[0].write_bytes(bytes(raw))
    s = bytearray(stars[0].read_bytes())
    s[-2] = ord("Z") if s[-2] != ord("Z") else ord("Y")
    stars[0].write_bytes(bytes(s))
    ndiff, _, _, _ = compare(b, m, c_root=c)
    print("\nnegative control reported %d differing files (expected exactly 2)" % ndiff)
    if ndiff != 2:
        print("FAIL the comparison cannot detect a change it is supposed to detect")
        return 1

    if diff:
        print("\nFAIL same-backend CPU outputs differ")
        return 1
    print("\nPASS same-backend CPU output identical, and the comparison is able to fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
