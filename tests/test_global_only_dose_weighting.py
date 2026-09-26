#!/usr/bin/env python3
"""Guard for the global-only dose-weighting fast path (Issue #26).

With ``--patch_x 1 --patch_y 1 --dose_weighting`` and no ``--save_noDW``, the
real-space frames produced by the global inverse FFT are overwritten by the
post-dose-weighting inverse FFT before anything reads them, so that first
transform is skipped. ``--save_noDW`` reads those frames, so it takes the other
branch and still performs it.

Both branches must therefore produce a bit-identical dose-weighted micrograph.
That is the invariant this test pins. It needs no new reference fixture: the two
runs check each other.

Two distinct failure modes have to be guarded, and one check does not cover both:

* **Skip too narrow / a new reader appears.** If code is added that reads the
  pre-dose-weighting real-space frames in the global-only path, the skip branch
  and the ``--save_noDW`` branch diverge. Check 1 below catches that;
  ``tests/test_synthetic_regression.py`` cannot, because it runs ``--patch_x 3``
  and never takes the skip branch.
* **Skip too broad.** If the condition is widened so the transform is elided
  when patch clipping still needs it, patch alignment silently degrades to the
  global-only answer. Check 1 cannot see this (both of its arms would skip), so
  check 2 asserts that ``--patch_x 3`` and ``--patch_x 1`` still produce
  *different* micrographs. Both checks were verified against a deliberately
  broken build that always skips; check 2 fails on it, check 1 does not.
"""

import argparse
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def read_mrc_pixels(path: Path) -> bytes:
    """Return the pixel payload only.

    MRC headers are not reproducible between runs: ``src/rwMRC.h`` writes a
    ``strftime`` timestamp into the label area at offset 224, so hashing whole
    files produces spurious mismatches.
    """
    data = path.read_bytes()
    nx, ny, nz, mode = struct.unpack("<4i", data[:16])
    if mode != 2:
        raise ValueError(f"Unsupported MRC mode {mode} in {path}")
    expected = nx * ny * nz * 4
    pixels = data[1024:1024 + expected]
    if len(pixels) != expected:
        raise ValueError(f"Truncated MRC {path}: {len(pixels)} of {expected} bytes")
    return pixels


def run(binary: Path, movie: Path, out_dir: Path, threads: int, extra, patch: int = 1):
    cmd = [
        str(binary.resolve()),
        "--i", str(movie.resolve()),
        "--o", str(out_dir.resolve()),
        "--use_own",
        "--j", str(threads),
        "--dose_weighting",
        "--dose_per_frame", "1.0",
        "--voltage", "300",
        "--angpix", "1.0",
        "--patch_x", str(patch),
        "--patch_y", str(patch),
        "--bfactor", "150",
    ] + list(extra)
    res = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)
    if res.returncode != 0:
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}")
    hits = [p for p in out_dir.glob("**/synthetic_movie.mrc")]
    if len(hits) != 1:
        raise AssertionError(f"Expected 1 dose-weighted MRC, found {len(hits)}")
    return hits[0]


def test_global_only_dose_weighting(binary: Path = None, threads_to_test=(1, 4)):
    repo_root = Path(__file__).resolve().parent.parent
    if binary is None:
        binary = repo_root / "build" / "motioncorr"
    if not binary.is_file():
        raise FileNotFoundError(f"motioncorr binary not found at {binary}. Build with cmake first.")

    movie = repo_root / "test-data" / "synthetic" / "synthetic_movie.tiff"
    if not movie.is_file():
        raise FileNotFoundError(f"Synthetic movie fixture not found at {movie}")

    for threads in threads_to_test:
        # Check 1: the skip branch and the --save_noDW branch must agree.
        digests = {}
        for label, extra in (("skip-path", ()), ("save_noDW-path", ("--save_noDW",))):
            with tempfile.TemporaryDirectory(prefix=f"gonly_{label}_t{threads}_") as tmp:
                mrc = run(binary, movie, Path(tmp), threads, extra)
                digests[label] = read_mrc_pixels(mrc)

        a, b = digests["skip-path"], digests["save_noDW-path"]
        n_diff = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
        print(f"--j {threads}: [1] dose-weighted pixels, skip-path vs --save_noDW path: "
              f"{n_diff} differing bytes of {len(a)}")
        assert n_diff == 0, (
            f"--j {threads}: skipping the global inverse FFT changed the dose-weighted "
            f"result ({n_diff} differing pixel bytes). The skip condition in "
            f"MotioncorrRunner::executeOwnMotionCorrection is too narrow: something now "
            f"reads the real-space frames before dose weighting."
        )

        # Check 2: patch alignment must still do something. If the skip were
        # widened to cover do_local, patch clipping would read frames that were
        # never transformed, every patch would report zero shift, and --patch_x 3
        # would silently collapse to the --patch_x 1 answer.
        with tempfile.TemporaryDirectory(prefix=f"gonly_p3_t{threads}_") as tmp:
            patched = read_mrc_pixels(run(binary, movie, Path(tmp), threads, (), patch=3))
        n_same = sum(x == y for x, y in zip(a, patched))
        print(f"--j {threads}: [2] --patch_x 3 vs --patch_x 1: "
              f"{len(a) - n_same} differing bytes of {len(a)} (must be > 0)")
        assert patched != a, (
            f"--j {threads}: --patch_x 3 produced exactly the --patch_x 1 result. Patch "
            f"alignment is contributing nothing, which is what happens when the global "
            f"inverse FFT is skipped while do_local is true. The skip condition is too broad."
        )

    print("\nSUCCESS: global-only dose-weighting fast path is bit-identical to the full "
          "path, and patch alignment still depends on the transform.")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None, help="Path to motioncorr binary")
    parser.add_argument("--threads", type=str, default="1,4", help="Comma-separated thread counts")
    args = parser.parse_args()
    threads = [int(x.strip()) for x in args.threads.split(",")]
    sys.exit(0 if test_global_only_dose_weighting(args.binary, threads) else 1)


if __name__ == "__main__":
    main()
