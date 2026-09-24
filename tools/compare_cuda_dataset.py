#!/usr/bin/env python3
"""Evaluate CUDA output against CPU j1 across the RELION SPA dataset.

CPU j4 is an optional diagnostic, separate from the CPU j1 Gate 2 decision.

Extracts:
- Trajectory RMS Shift Error & Max Shift Error
- Corrected Image RMSE & Relative RMSE
- Normalized STAR differences
- CUDA Global Alignment Profile (H2D, Custom Kernel, cuFFT, D2H, Total GPU ms, Peak VRAM)
- Full Movie Wall Time
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


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


def run_comparison(ref_mrc: Path, test_mrc: Path, ref_star: Path, test_star: Path,
                   test_log: Path) -> Dict[str, Any]:
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
            "--test-log", str(test_log),
            "--gate", "relaxed",
            "--json-out", str(json_tmp),
        ]
        completed = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True)
        if json_tmp.is_file() and json_tmp.stat().st_size > 0:
            with open(json_tmp, "r") as f:
                report = json.load(f)
            status = report.get("overall_status")
            if status not in ("PASS", "FAIL") or completed.returncode != (0 if status == "PASS" else 1):
                return {"overall_status": "ERROR", "error":
                        f"Comparator exit/status mismatch: exit {completed.returncode}, status {status}"}
            report["comparison_exit_code"] = completed.returncode
            return report
        return {"overall_status": "ERROR", "error":
                f"Comparator produced no report (exit {completed.returncode}): {completed.stderr.strip()}"}
    except Exception as e:
        return {"overall_status": "ERROR", "error": str(e)}
    finally:
        if json_tmp.is_file():
            json_tmp.unlink()

def main():
    parser = argparse.ArgumentParser(description="Evaluate CUDA benchmark against CPU")
    parser.add_argument("--cuda-dir", required=True, type=Path)
    parser.add_argument("--cpu-j1-dir", required=True, type=Path)
    parser.add_argument("--cpu-j4-dir", type=Path,
                        help="Optional CPU j4 comparison for diagnostics; Gate 2 uses CPU j1")
    parser.add_argument("--star", required=True, type=Path)
    parser.add_argument("--cuda-run-log", required=True, type=Path,
                        help="Full CUDA run log from /usr/bin/time -v, including exit status")
    parser.add_argument("--expected-movies", type=int, default=24)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.star.is_file() or not args.cuda_run_log.is_file():
        parser.error("--star and --cuda-run-log must name existing files")
    if args.expected_movies < 1:
        parser.error("--expected-movies must be positive")
    movie_names = extract_movie_names_from_star(args.star)
    if len(movie_names) != args.expected_movies or len(set(movie_names)) != len(movie_names):
        parser.error(f"Expected {args.expected_movies} distinct movies, found {len(movie_names)} entries")
    print(f"Found {len(movie_names)} movies in {args.star}")

    results = []
    print(f"{'#':<3} {'Movie Name':<30} {'GPU ms':>8} {'Traj RMS':>10} {'Max Shift':>10} {'Img RMSE':>10} {'Rel RMSE':>10} {'Gate 2'}")
    print("-" * 88)

    for i, mov in enumerate(movie_names, 1):
        cuda_mrc = args.cuda_dir / "Movies" / f"{mov}.mrc"
        cuda_star = args.cuda_dir / "Movies" / f"{mov}.star"
        cuda_log = args.cuda_dir / "Movies" / f"{mov}.log"

        j1_mrc = args.cpu_j1_dir / "Movies" / f"{mov}.mrc"
        j1_star = args.cpu_j1_dir / "Movies" / f"{mov}.star"

        required = (cuda_mrc, cuda_star, j1_mrc, j1_star)
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            results.append({"movie_index": i, "movie_name": mov, "gate_status": "ERROR",
                            "errors": [f"Missing required output: {path}" for path in missing]})
            print(f"[{i:02d}] {mov:<30} ERROR: missing required output")
            continue

        profile = parse_cuda_profile(cuda_log)
        comp_j1 = run_comparison(j1_mrc, cuda_mrc, j1_star, cuda_star, args.cuda_run_log)

        checks_j1 = comp_j1.get("checks", {})
        traj_j1 = checks_j1.get("motion_trajectory", {})
        img_j1 = checks_j1.get("corrected_image", {})
        star_j1 = checks_j1.get("star_fields", {})

        complete = comp_j1.get("coverage", {}).get("complete") is True
        checks_complete = all(name in checks_j1 for name in
                              ("motion_trajectory", "corrected_image", "star_fields"))
        if not complete or not checks_complete or comp_j1.get("overall_status") == "ERROR":
            gate_str = "ERROR"
        else:
            gate_str = comp_j1["overall_status"]

        def fmt(value: Any) -> str:
            return f"{value:.6f}" if isinstance(value, (int, float)) else "n/a"

        entry = {
            "movie_index": i,
            "movie_name": mov,
            "cuda_profile": profile,
            "gate_status": gate_str,
            "coverage_complete": complete,
            "comparison_exit_code": comp_j1.get("comparison_exit_code"),
            "failure_reasons": (comp_j1.get("errors", []) +
                                traj_j1.get("fail_reasons", []) +
                                img_j1.get("fail_reasons", []) +
                                star_j1.get("fail_reasons", []) +
                                ([comp_j1["error"]] if "error" in comp_j1 else [])),
            "vs_cpu_j1": {
                "coord_rms_shift_px": traj_j1.get("coord_rms_error"),
                "max_shift_px": traj_j1.get("max_shift_error"),
                "image_rmse": img_j1.get("rmse"),
                "relative_rmse": img_j1.get("relative_rmse"),
                "max_pixel_diff": img_j1.get("max_abs_pixel_error"),
                "static_star_diffs": star_j1.get("num_differences"),
            },
        }
        if args.cpu_j4_dir:
            j4_mrc = args.cpu_j4_dir / "Movies" / f"{mov}.mrc"
            j4_star = args.cpu_j4_dir / "Movies" / f"{mov}.star"
            comp_j4 = run_comparison(j4_mrc, cuda_mrc, j4_star, cuda_star, args.cuda_run_log)
            j4_complete = comp_j4.get("coverage", {}).get("complete") is True
            entry["vs_cpu_j4"] = {"status": comp_j4.get("overall_status"),
                                  "coverage_complete": j4_complete,
                                  "checks": comp_j4.get("checks", {}),
                                  "errors": comp_j4.get("errors", [])}
        results.append(entry)
        gpu_ms = profile.get("total_gpu_ms")
        gpu_text = f"{gpu_ms:.1f}" if gpu_ms is not None else "n/a"
        print(f"[{i:02d}] {mov:<30} {gpu_text:>8} {fmt(traj_j1.get('coord_rms_error')):>10} {fmt(traj_j1.get('max_shift_error')):>10} {fmt(img_j1.get('rmse')):>10} {fmt(img_j1.get('relative_rmse')):>10} {gate_str:>6}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWritten summary to {args.json_out}")

    passed = sum(entry["gate_status"] == "PASS" for entry in results)
    print(f"Gate 2: {passed}/{len(movie_names)} movies passed")
    if passed != len(movie_names):
        sys.exit(1)


if __name__ == "__main__":
    main()
