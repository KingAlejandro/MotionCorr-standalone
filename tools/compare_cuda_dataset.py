#!/usr/bin/env python3
"""Evaluate CUDA global alignment against CPU baselines across the 24-movie RELION SPA dataset.

Compares:
- MotionCorr CUDA + j4 (MotionCorr_full24_cuda_j4)
vs
- MotionCorr Standalone CPU j1 (MotionCorr_full24_standalone_j1)
- MotionCorr Standalone CPU j4 (MotionCorr_full24_standalone_j4)

Extracts:
- Trajectory RMS Shift Error & Max Shift Error
- Corrected Image RMSE & Relative RMSE
- Normalized STAR differences
- CUDA Global Alignment Profile (H2D, Custom Kernel, cuFFT, D2H, Total GPU ms, Peak VRAM)
- Full Movie Wall Time
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def extract_movie_names_from_star(star_path: Path) -> List[str]:
    movies = []
    in_movies = False
    with open(star_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped == "data_movies":
                in_movies = True
                continue
            if in_movies and stripped.startswith("Movies/"):
                tokens = stripped.split()
                if tokens:
                    fname = tokens[0]
                    base = Path(fname).stem
                    movies.append(base)
    return movies


def parse_cuda_profile(log_path: Path) -> Dict[str, Any]:
    profile: Dict[str, Any] = {}
    if not log_path.is_file():
        return profile

    text = log_path.read_text(errors="replace")
    patterns = {
        "h2d_ms": r"Host-to-Device transfer time:\s*([\d\.]+)\s*ms",
        "kernel_ms": r"Custom kernel execution time:\s*([\d\.]+)\s*ms",
        "cufft_ms": r"cuFFT execution time:\s*([\d\.]+)\s*ms",
        "d2h_ms": r"Device-to-Host transfer time:\s*([\d\.]+)\s*ms",
        "total_gpu_ms": r"Total GPU alignment time:\s*([\d\.]+)\s*ms",
        "buffer_vram_mib": r"Buffer VRAM:\s*([\d\.]+)\s*MiB",
        "cufft_vram_mib": r"cuFFT workspace VRAM:\s*([\d\.]+)\s*MiB",
        "peak_vram_mib": r"Peak GPU memory allocated:\s*([\d\.]+)\s*MiB",
        "full_movie_wall_sec": r"Full movie wall time:\s*([\d\.]+)\s*s",
    }
    for k, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            profile[k] = float(m.group(1))
    return profile


def run_comparison(ref_mrc: Path, test_mrc: Path, ref_star: Path, test_star: Path) -> Dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        json_tmp = Path(tf.name)

    try:
        cmd = [
            sys.executable,
            str(Path(__file__).parent / "compare_motioncorr.py"),
            "--ref", str(ref_mrc),
            "--test", str(test_mrc),
            "--ref-star", str(ref_star),
            "--test-star", str(test_star),
            "--gate", "relaxed",
            "--json-out", str(json_tmp),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if json_tmp.is_file() and json_tmp.stat().st_size > 0:
            with open(json_tmp, "r") as f:
                return json.load(f)
    except Exception as e:
        return {"overall_status": "ERROR", "error": str(e)}
    finally:
        if json_tmp.is_file():
            json_tmp.unlink()

    return {"overall_status": "ERROR"}


def main():
    parser = argparse.ArgumentParser(description="Evaluate CUDA benchmark against CPU")
    parser.add_argument("--cuda-dir", required=True, type=Path)
    parser.add_argument("--cpu-j1-dir", required=True, type=Path)
    parser.add_argument("--cpu-j4-dir", required=True, type=Path)
    parser.add_argument("--star", required=True, type=Path)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    movie_names = extract_movie_names_from_star(args.star)
    print(f"Found {len(movie_names)} movies in {args.star}")

    results = []
    print(f"{'#':<3} {'Movie Name':<30} {'GPU ms':>8} {'Traj RMS':>10} {'Max Shift':>10} {'Img RMSE':>10} {'Wall s':>7} {'Gate 2'}")
    print("-" * 88)

    for i, mov in enumerate(movie_names, 1):
        cuda_mrc = args.cuda_dir / "Movies" / f"{mov}.mrc"
        cuda_star = args.cuda_dir / "Movies" / f"{mov}.star"
        cuda_log = args.cuda_dir / "Movies" / f"{mov}.log"

        j1_mrc = args.cpu_j1_dir / "Movies" / f"{mov}.mrc"
        j1_star = args.cpu_j1_dir / "Movies" / f"{mov}.star"

        j4_mrc = args.cpu_j4_dir / "Movies" / f"{mov}.mrc"
        j4_star = args.cpu_j4_dir / "Movies" / f"{mov}.star"

        if not cuda_mrc.is_file():
            print(f"[{i:02d}/{len(movie_names)}] {mov:<28} pending")
            continue

        profile = parse_cuda_profile(cuda_log)
        comp_j1 = run_comparison(j1_mrc, cuda_mrc, j1_star, cuda_star)
        comp_j4 = run_comparison(j4_mrc, cuda_mrc, j4_star, cuda_star)

        checks_j1 = comp_j1.get("checks", {})
        traj_j1 = checks_j1.get("motion_trajectory", {})
        img_j1 = checks_j1.get("corrected_image", {})
        star_j1 = checks_j1.get("star_fields", {})

        checks_j4 = comp_j4.get("checks", {})
        traj_j4 = checks_j4.get("motion_trajectory", {})
        img_j4 = checks_j4.get("corrected_image", {})

        rms_j1 = traj_j1.get("coord_rms_error", 0.0)
        max_shift_j1 = traj_j1.get("max_shift_error", 0.0)
        img_rmse_j1 = img_j1.get("rmse", 0.0)
        star_diff_j1 = star_j1.get("num_differences", 0)

        rms_j4 = traj_j4.get("coord_rms_error", 0.0)
        max_shift_j4 = traj_j4.get("max_shift_error", 0.0)
        img_rmse_j4 = img_j4.get("rmse", 0.0)

        gate_pass = (rms_j1 <= 0.02 and max_shift_j1 <= 0.05 and star_diff_j1 == 0)
        gate_str = "PASS" if gate_pass else "FAIL"

        entry = {
            "movie_index": i,
            "movie_name": mov,
            "cuda_profile": profile,
            "vs_cpu_j1": {
                "coord_rms_shift_px": rms_j1,
                "max_shift_px": max_shift_j1,
                "image_rmse": img_rmse_j1,
                "relative_rmse": img_j1.get("relative_rmse", 0.0),
                "max_pixel_diff": img_j1.get("max_abs_pixel_error", 0.0),
                "star_diffs": star_diff_j1,
                "trajectory_pass": gate_pass,
            },
            "vs_cpu_j4": {
                "coord_rms_shift_px": rms_j4,
                "max_shift_px": max_shift_j4,
                "image_rmse": img_rmse_j4,
            }
        }
        results.append(entry)
        gpu_ms = profile.get("total_gpu_ms", 0)
        wall_s = profile.get("full_movie_wall_sec", 0)
        print(f"[{i:02d}] {mov:<30} {gpu_ms:>7.1f}ms {rms_j1:>9.6f}px {max_shift_j1:>9.6f}px {img_rmse_j1:>10.6f} {wall_s:>6.1f}s {gate_str:>6}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWritten summary to {args.json_out}")


if __name__ == "__main__":
    main()
