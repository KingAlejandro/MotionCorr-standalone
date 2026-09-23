#!/usr/bin/env python3
"""Repeat-run diagnostic script to measure trajectory and image dispersion.

Runs the same movie repeatedly across thread counts (e.g., 1 and 4 threads)
to verify determinism and numerical equivalence.
"""

import argparse
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
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


def run_motioncorr(binary: Path, work_dir: Path, out_dir: str, threads: int, extra_args: list) -> float:
    """Run motioncorr binary and return wall-clock execution time."""
    cmd = [
        str(binary.resolve()),
        "--i", "movies.star",
        "--o", out_dir,
        "--use_own",
        "--j", str(threads),
        "--dose_weighting",
        "--dose_per_frame", "1.277",
        "--patch_x", "5",
        "--patch_y", "5",
        "--bfactor", "150",
        "--gainref", "Movies/gain.mrc",
    ] + extra_args

    t0 = time.perf_counter()
    res = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True)
    t1 = time.perf_counter()

    if res.returncode != 0:
        print(f"Error executing command: {' '.join(cmd)}")
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        raise RuntimeError(f"MotionCorr exited with code {res.returncode}")

    return t1 - t0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=Path("build/motioncorr"), help="Path to motioncorr binary")
    parser.add_argument("--dataset", type=Path, default=Path("relion30_tutorial"), help="Tutorial directory")
    parser.add_argument("--repeats", type=int, default=5, help="Number of repeat runs per thread count")
    parser.add_argument("--thread-list", type=str, default="1,4", help="Comma-separated list of thread counts")
    parser.add_argument("--keep-runs", action="store_true", help="Keep run output directories after comparison")
    args = parser.parse_args()

    binary = args.binary.resolve()
    if not binary.is_file():
        sys.exit(f"Binary not found: {binary}")

    dataset = args.dataset.resolve()
    movie_star = dataset / "movies.star"
    if not movie_star.is_file():
        sys.exit(f"Input movies.star not found in {dataset}")

    thread_counts = [int(x.strip()) for x in args.thread_list.split(",")]
    print(f"Starting determinism diagnostics on {dataset.name} with {args.repeats} repeats each for threads: {thread_counts}")

    results = {}
    run_data = {}  # (threads, run_idx) -> (mrc_data, shifts, runtime)

    for threads in thread_counts:
        print(f"\n{'='*20} Testing {threads} Thread(s) ({args.repeats} repeats) {'='*20}")
        runtimes = []
        for r in range(1, args.repeats + 1):
            out_name = f"diag_t{threads}_r{r}"
            out_path = dataset / out_name
            if out_path.exists():
                shutil.rmtree(out_path)

            print(f"  [T={threads}] Run {r}/{args.repeats} ...", end=" ", flush=True)
            elapsed = run_motioncorr(binary, dataset, out_name, threads, [])
            runtimes.append(elapsed)
            print(f"done in {elapsed:.2f}s")

            # Load outputs
            # Find the MRC and STAR files
            mrc_files = list((out_path / "Movies").glob("*.mrc"))
            star_files = list((out_path / "Movies").glob("*.star"))
            if not mrc_files or not star_files:
                sys.exit(f"Error: Output files missing in {out_path / 'Movies'}")

            _, _, _, mrc_data = read_mrc_image(mrc_files[0])
            shifts = parse_star_shifts(star_files[0])
            run_data[(threads, r)] = (mrc_data, shifts, elapsed, out_path)

        # Compute within-thread dispersion across repeats against run 1
        ref_mrc, ref_shifts, _, _ = run_data[(threads, 1)]
        max_mrc_diff = 0.0
        max_mrc_rmse = 0.0
        max_traj_diff = 0.0
        max_traj_rmsd = 0.0

        for r in range(2, args.repeats + 1):
            cur_mrc, cur_shifts, _, _ = run_data[(threads, r)]
            m_diff, m_rmse = compare_mrc(ref_mrc, cur_mrc)
            t_diff, t_rmsd = compare_shifts(ref_shifts, cur_shifts)

            max_mrc_diff = max(max_mrc_diff, m_diff)
            max_mrc_rmse = max(max_mrc_rmse, m_rmse)
            max_traj_diff = max(max_traj_diff, t_diff)
            max_traj_rmsd = max(max_traj_rmsd, t_rmsd)

        avg_time = sum(runtimes) / len(runtimes)
        results[threads] = {
            "avg_time": avg_time,
            "max_mrc_diff": max_mrc_diff,
            "max_mrc_rmse": max_mrc_rmse,
            "max_traj_diff": max_traj_diff,
            "max_traj_rmsd": max_traj_rmsd,
        }

        print(f"\n  Within-thread dispersion for {threads} thread(s):")
        print(f"    Average runtime: {avg_time:.2f}s")
        print(f"    Image max pixel difference: {max_mrc_diff:.6e}")
        print(f"    Image RMSE:                 {max_mrc_rmse:.6e}")
        print(f"    Shift max diff (px):        {max_traj_diff:.6e}")
        print(f"    Shift RMSD (px):            {max_traj_rmsd:.6e}")

    # Cross-thread comparison: Compare 4-thread runs against 1-thread reference
    ref_1t_mrc, ref_1t_shifts, _, _ = run_data[(1, 1)]
    print(f"\n{'='*20} Cross-Thread Numerical Parity (vs. 1-Thread Reference) {'='*20}")
    cross_success = True
    for threads in thread_counts:
        if threads == 1:
            continue
        cur_mrc, cur_shifts, _, _ = run_data[(threads, 1)]
        m_diff, m_rmse = compare_mrc(ref_1t_mrc, cur_mrc)
        t_diff, t_rmsd = compare_shifts(ref_1t_shifts, cur_shifts)
        print(f"  {threads} Threads vs 1 Thread Reference:")
        print(f"    Image max pixel diff: {m_diff:.6e}")
        print(f"    Image RMSE:           {m_rmse:.6e}")
        print(f"    Shift max diff (px):  {t_diff:.6e}")
        print(f"    Shift RMSD (px):      {t_rmsd:.6e}")
        if m_diff > 1e-4 or t_diff > 1e-4:
            cross_success = False

    # Cleanup temporary directories unless requested
    if not args.keep_runs:
        print("\nCleaning up diagnostic output directories...")
        for (threads, r), (_, _, _, p) in run_data.items():
            if p.exists():
                shutil.rmtree(p)

    # Summary
    print(f"\n{'='*20} Final Summary {'='*20}")
    all_deterministic = True
    for t, res in results.items():
        is_det = (res["max_mrc_diff"] == 0.0 and res["max_traj_diff"] == 0.0)
        status = "PASSED (Deterministic)" if is_det else "FAILED (Non-deterministic)"
        if not is_det:
            all_deterministic = False
        print(f"  Threads={t:2d}: {status} (MRC max diff: {res['max_mrc_diff']:.2e}, Shift max diff: {res['max_traj_diff']:.2e})")

    cross_status = "PASSED (Exact Parity)" if cross_success else "FAILED (Divergence)"
    print(f"  Cross-thread parity (Multi-thread vs 1-Thread): {cross_status}")

    if all_deterministic and cross_success:
        print("\nSUCCESS: All determinism and numerical parity criteria satisfied!")
        sys.exit(0)
    else:
        print("\nFAILURE: Determinism or parity check failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()

