#!/usr/bin/env python3
"""Isolated, repeated wall-time benchmarking series for CPU vs CUDA patch alignment.

Measures repeated wall-clock executions on identical experimental inputs,
monitors whole-process peak VRAM via nvidia-smi background sampling,
and calculates statistical metrics (mean, median, stddev, speedup).
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List


def run_cmd(cmd: List[str], cwd: Path = None, timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, cwd=str(cwd) if cwd else None)


def main():
    parser = argparse.ArgumentParser(description="Benchmark CPU vs CUDA wall-time series")
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--cpu-bin", type=Path, default=Path("build-cpu/motioncorr"))
    parser.add_argument("--cuda-bin", type=Path, default=Path("build-cuda/motioncorr"))
    parser.add_argument("--gpu-id", type=int, default=1)
    parser.add_argument("--exp-movie", type=Path, required=True)
    parser.add_argument("--exp-gain", type=Path, required=True)
    parser.add_argument("--num-repeats", type=int, default=5)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark_series_results"))
    args = parser.parse_args()

    repo = args.repo_dir.resolve()
    cpu_bin = (repo / args.cpu_bin).resolve()
    cuda_bin = (repo / args.cuda_bin).resolve()
    exp_movie = args.exp_movie.resolve()
    exp_gain = args.exp_gain.resolve()
    out = args.output_dir.resolve()

    if not cpu_bin.is_file():
        sys.exit(f"CPU binary not found: {cpu_bin}")
    if not cuda_bin.is_file():
        sys.exit(f"CUDA binary not found: {cuda_bin}")
    if not exp_movie.is_file():
        sys.exit(f"Movie not found: {exp_movie}")
    if not exp_gain.is_file():
        sys.exit(f"Gain not found: {exp_gain}")

    out.mkdir(parents=True, exist_ok=True)

    # Prepare input STAR
    exp_star = out / "benchmark_input.star"
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
{exp_movie} 1
""")

    results: Dict[str, Any] = {
        "num_repeats": args.num_repeats,
        "threads": args.threads,
        "gpu_id": args.gpu_id,
        "cpu_runs_sec": [],
        "cuda_runs_sec": [],
        "peak_vram_mib": None
    }

    # 1. Repeated CPU Runs
    print(f"\n--- Running {args.num_repeats} isolated CPU runs (threads={args.threads}) ---")
    for i in range(args.num_repeats):
        run_d = out / f"cpu_{i+1}"
        run_d.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(cpu_bin), "--use_own",
            "--i", str(exp_star),
            "--o", str(run_d / "corrected.mrc"),
            "--patch_x", "5", "--patch_y", "5",
            "--dose_weighting",
            "--voltage", "300.0",
            "--angpix", "1.06",
            "--dose_per_frame", "1.277",
            "--j", str(args.threads),
            "--gainref", str(exp_gain)
        ]
        t0 = time.time()
        res = run_cmd(cmd)
        elapsed = time.time() - t0
        if res.returncode != 0:
            sys.exit(f"CPU run {i+1} failed: {res.stderr}")
        print(f"  CPU run {i+1}: {elapsed:.2f} s")
        results["cpu_runs_sec"].append(elapsed)

    # 2. Repeated CUDA Runs with background VRAM monitor
    vram_log = out / "vram_monitor.log"
    if vram_log.exists():
        vram_log.unlink()

    # Start VRAM monitor sampler (every 50ms)
    mon_cmd = f"while true; do nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i {args.gpu_id} >> {vram_log}; sleep 0.05; done"
    mon_proc = subprocess.Popen(mon_cmd, shell=True)

    try:
        print(f"\n--- Running {args.num_repeats} isolated CUDA runs (GPU={args.gpu_id}, threads={args.threads}) ---")
        for i in range(args.num_repeats):
            run_d = out / f"cuda_{i+1}"
            run_d.mkdir(parents=True, exist_ok=True)
            cmd = [
                str(cuda_bin), "--use_own",
                "--i", str(exp_star),
                "--o", str(run_d / "corrected.mrc"),
                "--patch_x", "5", "--patch_y", "5",
                "--dose_weighting",
                "--voltage", "300.0",
                "--angpix", "1.06",
                "--dose_per_frame", "1.277",
                "--gpu", str(args.gpu_id),
                "--j", str(args.threads),
                "--gainref", str(exp_gain)
            ]
            t0 = time.time()
            res = run_cmd(cmd)
            elapsed = time.time() - t0
            if res.returncode != 0:
                sys.exit(f"CUDA run {i+1} failed: {res.stderr}")
            print(f"  CUDA run {i+1}: {elapsed:.2f} s")
            results["cuda_runs_sec"].append(elapsed)
    finally:
        mon_proc.terminate()
        mon_proc.kill()
        subprocess.run(["pkill", "-f", "nvidia-smi"], check=False)

    # Parse Peak VRAM
    if vram_log.exists():
        vram_samples = []
        for line in vram_log.read_text().splitlines():
            line = line.strip()
            if line.isdigit():
                vram_samples.append(int(line))
        if vram_samples:
            results["peak_vram_mib"] = max(vram_samples)

    # Statistics
    cpu_times = results["cpu_runs_sec"]
    cuda_times = results["cuda_runs_sec"]

    cpu_stats = {
        "mean": statistics.mean(cpu_times),
        "median": statistics.median(cpu_times),
        "min": min(cpu_times),
        "max": max(cpu_times),
        "stdev": statistics.stdev(cpu_times) if len(cpu_times) > 1 else 0.0
    }
    cuda_stats = {
        "mean": statistics.mean(cuda_times),
        "median": statistics.median(cuda_times),
        "min": min(cuda_times),
        "max": max(cuda_times),
        "stdev": statistics.stdev(cuda_times) if len(cuda_times) > 1 else 0.0
    }
    speedup = cpu_stats["median"] / cuda_stats["median"]

    results["cpu_stats"] = cpu_stats
    results["cuda_stats"] = cuda_stats
    results["speedup_median"] = speedup

    summary_file = out / "benchmark_series_summary.json"
    with summary_file.open("w") as f:
        json.dump(results, f, indent=2)

    print("\n================ BENCHMARK SERIES RESULTS ================")
    print(f"CPU Wall Times (s):  {[round(x, 2) for x in cpu_times]}")
    print(f"  Median: {cpu_stats['median']:.2f} s | Mean: {cpu_stats['mean']:.2f} s (±{cpu_stats['stdev']:.2f} s)")
    print(f"CUDA Wall Times (s): {[round(x, 2) for x in cuda_times]}")
    print(f"  Median: {cuda_stats['median']:.2f} s | Mean: {cuda_stats['mean']:.2f} s (±{cuda_stats['stdev']:.2f} s)")
    print(f"Speedup (Median):    {speedup:.2f}x")
    if results["peak_vram_mib"]:
        print(f"Measured Peak VRAM:  {results['peak_vram_mib']} MiB")
    print(f"Summary written to:  {summary_file}")
    print("==========================================================")


if __name__ == "__main__":
    main()
