#!/usr/bin/env python3
"""Automated regression test verifying that MotionCorr produces bit-for-bit identical
output to the baseline reference on a small synthetic movie fixture.
"""

import argparse
import math
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


def read_mrc_image(path: Path):
    """Read dimensions and 32-bit float array from MRC image file."""
    with open(path, "rb") as f:
        header = f.read(1024)
        nx, ny, nz, mode = struct.unpack("<4i", header[:16])
        n_elements = nx * ny * nz
        if mode == 2:  # float32
            data = struct.unpack(f"<{n_elements}f", f.read(n_elements * 4))
        else:
            raise ValueError(f"Unsupported MRC mode: {mode}")
    return nx, ny, nz, data


def parse_star_shifts(path: Path):
    """Extract global frame shifts from STAR file."""
    shifts = []
    with open(path, "r") as f:
        in_global = False
        in_loop = False
        col_x = -1
        col_y = -1
        col_count = 0
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("data_global_shift"):
                in_global = True
                in_loop = False
                continue
            elif line.startswith("data_") and in_global:
                break
            if in_global:
                if line == "loop_":
                    in_loop = True
                    col_count = 0
                    continue
                if in_loop and line.startswith("_rln"):
                    parts = line.split()
                    if parts[0] == "_rlnMicrographShiftX":
                        col_x = col_count
                    elif parts[0] == "_rlnMicrographShiftY":
                        col_y = col_count
                    col_count += 1
                    continue
                if in_loop and col_x >= 0 and col_y >= 0:
                    fields = line.split()
                    if len(fields) >= max(col_x, col_y) + 1:
                        try:
                            sx = float(fields[col_x])
                            sy = float(fields[col_y])
                            shifts.append((sx, sy))
                        except ValueError:
                            pass
    return shifts


def compare_mrc(data1, data2):
    """Compute maximum absolute difference and RMSE between two image buffers."""
    if len(data1) != len(data2):
        raise ValueError(f"Image lengths do not match: {len(data1)} vs {len(data2)}")
    max_diff = 0.0
    sum_sq = 0.0
    for v1, v2 in zip(data1, data2):
        d = abs(v1 - v2)
        if d > max_diff:
            max_diff = d
        sum_sq += d * d
    rmse = math.sqrt(sum_sq / len(data1))
    return max_diff, rmse


def compare_shifts(shifts1, shifts2):
    """Compute maximum absolute difference and RMSD between two trajectory shift sets."""
    if len(shifts1) != len(shifts2):
        raise ValueError(f"Trajectory lengths do not match: {len(shifts1)} vs {len(shifts2)}")
    max_diff = 0.0
    sum_sq = 0.0
    for (x1, y1), (x2, y2) in zip(shifts1, shifts2):
        dx = abs(x1 - x2)
        dy = abs(y1 - y2)
        max_diff = max(max_diff, dx, dy)
        sum_sq += dx * dx + dy * dy
    rmsd = math.sqrt(sum_sq / len(shifts1))
    return max_diff, rmsd


def run_motioncorr(binary: Path, movie: Path, out_dir: Path, threads: int = 1):
    """Run motioncorr on the synthetic movie fixture."""
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
        "--patch_x", "3",
        "--patch_y", "3",
        "--bfactor", "150",
    ]
    res = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)
    if res.returncode != 0:
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {' '.join(cmd)}")


def test_synthetic_regression(binary: Path = None, threads_to_test=(1, 4)):
    repo_root = Path(__file__).resolve().parent.parent

    if binary is None:
        binary = repo_root / "build" / "motioncorr"
    if not binary.is_file():
        raise FileNotFoundError(f"motioncorr binary not found at {binary}. Build with cmake first.")

    movie_path = repo_root / "test-data" / "synthetic" / "synthetic_movie.tiff"
    expected_mrc = repo_root / "test-data" / "synthetic" / "expected" / "synthetic_movie.mrc"
    expected_star = repo_root / "test-data" / "synthetic" / "expected" / "synthetic_movie.star"

    if not movie_path.is_file():
        raise FileNotFoundError(f"Synthetic movie fixture not found at {movie_path}")
    if not expected_mrc.is_file() or not expected_star.is_file():
        raise FileNotFoundError(f"Expected reference files not found in {expected_mrc.parent}")

    # Read expected reference data
    _, _, _, exp_mrc_data = read_mrc_image(expected_mrc)
    exp_shifts = parse_star_shifts(expected_star)
    assert len(exp_shifts) == 8, f"Expected 8 frame shifts, found {len(exp_shifts)}"

    for threads in threads_to_test:
        with tempfile.TemporaryDirectory(prefix=f"synth_test_t{threads}_") as tmpdir:
            out_dir = Path(tmpdir)
            run_motioncorr(binary, movie_path, out_dir, threads=threads)

            # Find output MRC and STAR
            mrc_files = list(out_dir.glob("**/synthetic_movie.mrc"))
            star_files = list(out_dir.glob("**/synthetic_movie.star"))

            assert len(mrc_files) == 1, f"Expected 1 output MRC file, found {len(mrc_files)}"
            assert len(star_files) == 1, f"Expected 1 output STAR file, found {len(star_files)}"

            _, _, _, actual_mrc_data = read_mrc_image(mrc_files[0])
            actual_shifts = parse_star_shifts(star_files[0])

            m_diff, m_rmse = compare_mrc(exp_mrc_data, actual_mrc_data)
            t_diff, t_rmsd = compare_shifts(exp_shifts, actual_shifts)

            print(f"Results for --j {threads} vs Expected Old Baseline:")
            print(f"  Image Max Pixel Difference: {m_diff:.6e}")
            print(f"  Image RMSE:                 {m_rmse:.6e}")
            print(f"  Shift Max Difference (px):  {t_diff:.6e}")
            print(f"  Shift RMSD (px):            {t_rmsd:.6e}")

            # Assert bit-for-bit numerical parity
            assert m_diff == 0.0, f"Image pixel diff ({m_diff}) must be exactly 0.0"
            assert m_rmse == 0.0, f"Image RMSE ({m_rmse}) must be exactly 0.0"
            assert t_diff == 0.0, f"Trajectory shift diff ({t_diff}) must be exactly 0.0"
            assert t_rmsd == 0.0, f"Trajectory RMSD ({t_rmsd}) must be exactly 0.0"

    print("\nSUCCESS: All synthetic regression tests passed with bit-for-bit identity!")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None, help="Path to motioncorr binary")
    parser.add_argument("--threads", type=str, default="1,4", help="Comma-separated thread counts to test")
    args = parser.parse_args()

    threads = [int(x.strip()) for x in args.threads.split(",")]
    success = test_synthetic_regression(binary=args.binary, threads_to_test=threads)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

