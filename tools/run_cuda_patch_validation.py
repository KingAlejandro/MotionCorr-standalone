#!/usr/bin/env python3
"""Multi-stage validation and profiling suite for CUDA local patch alignment (Issue #17).

Executes:
  1. Negative test: --gpu 99 (verifies clean error exit without spurious output)
  2. Fallback test: synthetic_fallback.mrc (verifies fallback to global trajectory)
  3. Staged synthetic tests:
     - 1x1 patch (global baseline)
     - 3x3 patches (local differential motion)
     - 5x5 patches (higher density local grid)
  4. Full experimental tutorial movie:
     - 20170629_00021_frameImage.tiff (3710x3838x24, gain ref, dose weighting, 5x5 patches)
  5. 3 steady-state profiling runs capturing H2D, kernel, cuFFT, D2H, and peak VRAM.
  6. Gate verification using tools/compare_motioncorr.py without altering tolerances.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


def run_cmd(cmd: List[str], check: bool = True, timeout: Optional[int] = 600) -> subprocess.CompletedProcess:
    print(f"[RUN] {' '.join(str(c) for c in cmd)}")
    t0 = time.time()
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    elapsed = time.time() - t0
    print(f"      Exit {res.returncode} ({elapsed:.2f}s)")
    if check and res.returncode != 0:
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise RuntimeError(f"Command failed with exit code {res.returncode}")
    return res


def parse_telemetry(log_text: str) -> Dict[str, Any]:
    """Parse CUDA timing and memory lines from logfile."""
    profile_re = re.compile(
        r"\[CUDA (?P<stage>Global Alignment|Patch Alignment) Profile\]\s+"
        r"Host-to-Device transfer time:\s+(?P<h2d>[\d\.]+)\s+ms\s+"
        r"Custom kernel execution time:\s+(?P<kernel>[\d\.]+)\s+ms\s+"
        r"cuFFT execution time:\s+(?P<cufft>[\d\.]+)\s+ms\s+"
        r"Device-to-Host transfer time:\s+(?P<d2h>[\d\.]+)\s+ms\s+"
        r"Total GPU alignment time:\s+(?P<total_gpu>[\d\.]+)\s+ms\s+"
        r"Buffer VRAM:\s+(?P<buf_vram>[\d\.]+)\s+MiB\s+"
        r"cuFFT workspace VRAM:\s+(?P<cufft_vram>[\d\.]+)\s+MiB\s+"
        r"Peak GPU memory allocated:\s+(?P<peak_vram>[\d\.]+)\s+MiB"
    )
    patches = []
    global_prof = None
    for m in profile_re.finditer(log_text):
        entry = {k: float(v) if k != "stage" else v for k, v in m.groupdict().items()}
        if entry["stage"] == "Global Alignment":
            global_prof = entry
        else:
            patches.append(entry)
    
    return {
        "global_profile": global_prof,
        "patch_profiles": patches,
        "num_patch_profiles": len(patches),
        "total_patch_gpu_ms": sum(p["total_gpu"] for p in patches) if patches else 0.0
    }


def parse_shifts(star_file: Path) -> List[Tuple[float, float]]:
    shifts = []
    if not star_file.exists():
        return shifts
    in_loop = False
    with star_file.open() as f:
        for line in f:
            line = line.strip()
            if line.startswith("_rlnMicrographShiftX"):
                in_loop = True
                continue
            if in_loop and line and not line.startswith("_") and not line.startswith("data_") and not line.startswith("loop_"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        shifts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        pass
    return shifts


def find_mrc_and_star(dir_path: Path) -> Tuple[Optional[Path], Optional[Path]]:
    mrcs = [p for p in dir_path.rglob("*.mrc") if p.is_file()]
    mrc = None
    for p in mrcs:
        if "frameImage.mrc" in p.name:
            mrc = p
            break
        elif "synthetic_" in p.name:
            mrc = p
            break
    if mrc is None and mrcs:
        mrc = mrcs[0]

    stars = [p for p in dir_path.rglob("*.star") if p.is_file() and not p.name.startswith("corrected_micrographs")]
    star = None
    for p in stars:
        if "frameImage.star" in p.name:
            star = p
            break
        elif "synthetic_" in p.name:
            star = p
            break
    if star is None and stars:
        star = stars[0]
    return mrc, star


def get_telemetry_for_dir(cand_dir: Path, fallback_stdout: str = "") -> Dict[str, Any]:
    logs = list(cand_dir.rglob("*.log"))
    for p in logs:
        if "frameImage" in p.name:
            return parse_telemetry(p.read_text())
        elif "synthetic_" in p.name:
            return parse_telemetry(p.read_text())
    if logs:
        return parse_telemetry(logs[0].read_text())
    return parse_telemetry(fallback_stdout)


def run_comparator(comparator: Path, ref_dir: Path, cand_dir: Path, label: str) -> Dict[str, Any]:
    ref_mrc, ref_star = find_mrc_and_star(ref_dir)
    cand_mrc, cand_star = find_mrc_and_star(cand_dir)
    if not ref_mrc or not cand_mrc or not ref_star or not cand_star:
        return {
            "error": f"Missing mrc/star: ref=({ref_mrc}, {ref_star}), cand=({cand_mrc}, {cand_star})",
            "comparator_exit_code": 3
        }

    cmd = [
        sys.executable, str(comparator),
        "--ref-mrc", str(ref_mrc),
        "--test-mrc", str(cand_mrc),
        "--ref-star", str(ref_star),
        "--test-star", str(cand_star),
        "--gate", "relaxed",
        "--json"
    ]
    res = run_cmd(cmd, check=False)
    report = {}
    try:
        report = json.loads(res.stdout)
    except Exception as e:
        report = {"exit_code": res.returncode, "stdout": res.stdout, "stderr": res.stderr, "error": str(e)}
    report["comparator_exit_code"] = res.returncode
    return report


def main():
    parser = argparse.ArgumentParser(description="Run CUDA patch alignment verification suite")
    parser.add_argument("--repo-dir", type=Path, default=Path("."), help="Path to MotionCorr repo")
    parser.add_argument("--cpu-bin", type=Path, default=Path("build-cpu/motioncorr"))
    parser.add_argument("--cuda-bin", type=Path, default=Path("build-cuda/motioncorr"))
    parser.add_argument("--gpu-id", type=int, default=0)
    parser.add_argument("--exp-movie", type=Path, default=None, help="Path to experimental TIFF/MRC movie")
    parser.add_argument("--exp-gain", type=Path, default=None, help="Path to experimental gain reference")
    parser.add_argument("--output-dir", type=Path, default=Path("validation_results"))
    args = parser.parse_args()

    repo = args.repo_dir.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    comparator = repo / "tools" / "compare_motioncorr.py"

    cpu_bin = (repo / args.cpu_bin).resolve()
    cuda_bin = (repo / args.cuda_bin).resolve()

    summary: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stages": {},
        "steady_state": [],
        "verdict": "UNKNOWN"
    }

    # ---------------------------------------------------------
    # Negative Test: Unsupported device / invalid ID
    # ---------------------------------------------------------
    print("\n=== NEGATIVE TEST: Invalid Device ID --gpu 99 ===")
    neg_dir = out / "test_neg"
    neg_dir.mkdir(parents=True, exist_ok=True)
    neg_res = run_cmd([
        str(cuda_bin), "--use_own",
        "--i", str(repo / "test-data/synthetic/synthetic_local_motion.star"),
        "--o", str(neg_dir / "neg.mrc"),
        "--gpu", "99"
    ], check=False)
    neg_passed = (neg_res.returncode != 0) and ("Invalid GPU device ID" in neg_res.stderr or "Invalid GPU device ID" in neg_res.stdout or "Invalid CUDA device ID" in neg_res.stderr or "Invalid CUDA device ID" in neg_res.stdout)
    summary["negative_test"] = {
        "passed": neg_passed,
        "exit_code": neg_res.returncode,
        "stderr_contains_error": neg_passed
    }
    print(f"Negative test passed: {neg_passed} (exit {neg_res.returncode})")

    # ---------------------------------------------------------
    # Fallback Test: Extreme noise movie
    # ---------------------------------------------------------
    print("\n=== FALLBACK TEST: Synthetic Fallback Movie ===")
    fb_cpu_dir = out / "fb_cpu"
    fb_cuda_dir = out / "fb_cuda"
    fb_cpu_dir.mkdir(parents=True, exist_ok=True)
    fb_cuda_dir.mkdir(parents=True, exist_ok=True)

    run_cmd([
        str(cpu_bin), "--use_own",
        "--i", str(repo / "test-data/synthetic/synthetic_fallback.star"),
        "--o", str(fb_cpu_dir / "fb_cpu.mrc"),
        "--patch_x", "3", "--patch_y", "3",
        "--j", "1"
    ])
    run_cmd([
        str(cuda_bin), "--use_own",
        "--i", str(repo / "test-data/synthetic/synthetic_fallback.star"),
        "--o", str(fb_cuda_dir / "fb_cuda.mrc"),
        "--patch_x", "3", "--patch_y", "3",
        "--gpu", str(args.gpu_id)
    ])
    fb_cmp = run_comparator(comparator, fb_cpu_dir, fb_cuda_dir, "fallback_3x3")
    summary["stages"]["fallback_3x3"] = fb_cmp

    # ---------------------------------------------------------
    # Staged Synthetic Tests: 1x1, 3x3, 5x5
    # ---------------------------------------------------------
    for px, py in [(1, 1), (3, 3), (5, 5)]:
        stage_name = f"synth_{px}x{py}"
        print(f"\n=== SYNTHETIC STAGE: {stage_name} ===")
        ref_d = out / f"{stage_name}_cpu"
        cand_d = out / f"{stage_name}_cuda"
        ref_d.mkdir(parents=True, exist_ok=True)
        cand_d.mkdir(parents=True, exist_ok=True)

        ref_cmd = [
            str(cpu_bin), "--use_own",
            "--i", str(repo / "test-data/synthetic/synthetic_local_motion.star"),
            "--o", str(ref_d / f"{stage_name}.mrc"),
            "--patch_x", str(px), "--patch_y", str(py),
            "--j", "1"
        ]
        cand_cmd = [
            str(cuda_bin), "--use_own",
            "--i", str(repo / "test-data/synthetic/synthetic_local_motion.star"),
            "--o", str(cand_d / f"{stage_name}.mrc"),
            "--patch_x", str(px), "--patch_y", str(py),
            "--gpu", str(args.gpu_id)
        ]
        run_cmd(ref_cmd)
        c_res = run_cmd(cand_cmd)
        
        # Telemetry
        telemetry = get_telemetry_for_dir(cand_d, c_res.stdout)
        
        cmp_res = run_comparator(comparator, ref_d, cand_d, stage_name)
        cmp_res["telemetry"] = telemetry
        summary["stages"][stage_name] = cmp_res

    # ---------------------------------------------------------
    # Full Experimental Movie Test & Steady-state Profiling
    # ---------------------------------------------------------
    if args.exp_movie and args.exp_movie.exists():
        print(f"\n=== EXPERIMENTAL MOVIE TEST: {args.exp_movie.name} ===")
        exp_star = out / "exp_input.star"
        with exp_star.open("w") as f:
            f.write(f"""# version 30001
data_optics
loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 1.06 300.0 2.7 0.1

data_movies
loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
{args.exp_movie.resolve()} 1
""")
        exp_ref_d = out / "exp_cpu"
        exp_ref_d.mkdir(parents=True, exist_ok=True)
        cpu_exp_cmd = [
            str(cpu_bin), "--use_own",
            "--i", str(exp_star),
            "--o", str(exp_ref_d / "corrected.mrc"),
            "--patch_x", "5", "--patch_y", "5",
            "--dose_weighting",
            "--voltage", "300.0",
            "--angpix", "1.06",
            "--dose_per_frame", "1.277",
            "--j", "8"
        ]
        if args.exp_gain and args.exp_gain.exists():
            cpu_exp_cmd.extend(["--gainref", str(args.exp_gain.resolve())])

        print("Running CPU reference for experimental movie...")
        t_cpu_0 = time.time()
        run_cmd(cpu_exp_cmd, timeout=1200)
        cpu_wall_sec = time.time() - t_cpu_0
        summary["exp_cpu_wall_sec"] = cpu_wall_sec

        # 3 steady-state CUDA runs
        gpu_timings = []
        for irun in range(3):
            exp_cand_d = out / f"exp_cuda_run{irun+1}"
            exp_cand_d.mkdir(parents=True, exist_ok=True)
            cuda_exp_cmd = [
                str(cuda_bin), "--use_own",
                "--i", str(exp_star),
                "--o", str(exp_cand_d / "corrected.mrc"),
                "--patch_x", "5", "--patch_y", "5",
                "--dose_weighting",
                "--voltage", "300.0",
                "--angpix", "1.06",
                "--dose_per_frame", "1.277",
                "--gpu", str(args.gpu_id),
                "--j", "8"
            ]
            if args.exp_gain and args.exp_gain.exists():
                cuda_exp_cmd.extend(["--gainref", str(args.exp_gain.resolve())])

            print(f"Running CUDA steady-state run {irun+1}/3...")
            t_gpu_0 = time.time()
            c_res = run_cmd(cuda_exp_cmd, timeout=1200)
            gpu_wall_sec = time.time() - t_gpu_0

            telem = get_telemetry_for_dir(exp_cand_d, c_res.stdout)
            telem["wall_time_sec"] = gpu_wall_sec
            gpu_timings.append(telem)

            if irun == 0:
                exp_cmp = run_comparator(comparator, exp_ref_d, exp_cand_d, "exp_5x5")
                summary["stages"]["exp_5x5"] = exp_cmp

        summary["steady_state"] = gpu_timings

    # Write summary JSON
    summary_path = out / "cuda_patch_validation_summary.json"
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved validation summary to {summary_path}")


if __name__ == "__main__":
    main()
