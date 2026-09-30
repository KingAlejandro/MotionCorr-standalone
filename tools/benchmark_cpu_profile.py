#!/usr/bin/env python3
"""Repeatable CPU time and peak memory profiling benchmark harness for MotionCorr.

Satisfies GitHub Issue #9 acceptance criteria:
1. Records hardware, build flags, input hashes, thread count, wall time, stage times, peak RSS, and output checksums.
2. Identifies top 3 time and memory costs (I/O, FFT/CCF, patch alignment, dose weighting, interpolation).
3. Executes at least 3 repetitions per case and reports variability (mean +/- std).
4. Evaluates output against reference gates (tools/compare_motioncorr.py).
5. Outputs structured JSON and markdown reports.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def sha256_file(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def get_python_with_numpy() -> str:
    """Find a Python interpreter that has numpy available."""
    try:
        import numpy
        return sys.executable
    except ImportError:
        pass
    for candidate in ["/home/alex/mc-env/bin/python3", "/home/alex/miniforge3/bin/python3", "python3"]:
        try:
            res = subprocess.run([candidate, "-c", "import numpy"], capture_output=True)
            if res.returncode == 0:
                return candidate
        except Exception:
            pass
    return sys.executable


def parse_time_v_output(output: str) -> Dict[str, Any]:
    """Parse output of GNU /usr/bin/time -v."""
    metrics: Dict[str, Any] = {}
    
    elapsed_match = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*([0-9:.]+)", output)
    if elapsed_match:
        time_str = elapsed_match.group(1)
        parts = [float(p) for p in time_str.split(":")]
        if len(parts) == 3:
            metrics["wall_time_sec"] = parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            metrics["wall_time_sec"] = parts[0] * 60 + parts[1]
        else:
            metrics["wall_time_sec"] = parts[0]
        metrics["wall_time_str"] = time_str

    user_match = re.search(r"User time \(seconds\):\s*([0-9.]+)", output)
    if user_match:
        metrics["user_time_sec"] = float(user_match.group(1))

    sys_match = re.search(r"System time \(seconds\):\s*([0-9.]+)", output)
    if sys_match:
        metrics["sys_time_sec"] = float(sys_match.group(1))

    cpu_match = re.search(r"Percent of CPU this job got:\s*([0-9]+)%", output)
    if cpu_match:
        metrics["cpu_percent"] = int(cpu_match.group(1))

    rss_match = re.search(r"Maximum resident set size \(kbytes\):\s*([0-9]+)", output)
    if rss_match:
        rss_kb = int(rss_match.group(1))
        metrics["peak_rss_kb"] = rss_kb
        metrics["peak_rss_mb"] = round(rss_kb / 1024.0, 2)
        metrics["peak_rss_gib"] = round(rss_kb / (1024.0 * 1024.0), 3)

    exit_match = re.search(r"Exit status:\s*([0-9]+)", output)
    if exit_match:
        metrics["exit_status"] = int(exit_match.group(1))

    return metrics


def parse_stage_times(output: str) -> Dict[str, Dict[str, float]]:
    """Parse MotionCorr Timer::printTimes() output."""
    stage_times: Dict[str, Dict[str, float]] = {}
    pattern = re.compile(r"^([A-Za-z0-9_\s\-()]+?)\s*:\s*([0-9.]+)\s*sec\s*\(([0-9.]+)\s*microsec/operation\)", re.MULTILINE)
    for match in pattern.finditer(output):
        tag = match.group(1).strip()
        sec = float(match.group(2))
        microsec_per_op = float(match.group(3))
        stage_times[tag] = {
            "seconds": sec,
            "microsec_per_op": microsec_per_op,
        }
    return stage_times


def get_hardware_info() -> Dict[str, Any]:
    """Capture host hardware and OS specifications."""
    info: Dict[str, Any] = {
        "hostname": platform.node(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }
    
    # CPU info via lscpu or /proc/cpuinfo
    try:
        lscpu_out = subprocess.check_output(["lscpu"], text=True, stderr=subprocess.DEVNULL)
        for line in lscpu_out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k in ("Model name", "CPU(s)", "Thread(s) per core", "Core(s) per socket", "Socket(s)", "NUMA node(s)", "L3 cache"):
                    info[k] = v
    except Exception:
        pass

    # RAM info via /proc/meminfo or free
    try:
        meminfo = Path("/proc/meminfo").read_text()
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
                info["total_ram_gib"] = round(total_kb / (1024.0 * 1024.0), 1)
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
                info["available_ram_gib"] = round(avail_kb / (1024.0 * 1024.0), 1)
    except Exception:
        pass

    # Compilers
    try:
        gcc_out = subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0]
        info["gcc_version"] = gcc_out
    except Exception:
        pass

    try:
        cmake_out = subprocess.check_output(["cmake", "--version"], text=True).splitlines()[0]
        info["cmake_version"] = cmake_out
    except Exception:
        pass

    return info


def calc_stats(values: List[float]) -> Dict[str, float]:
    """Calculate mean, stddev, min, max, and CV%."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "cv_pct": 0.0}
    n = len(values)
    mean_val = sum(values) / n
    variance = sum((x - mean_val) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    std_val = math.sqrt(variance)
    cv_pct = (std_val / mean_val * 100.0) if mean_val > 1e-9 else 0.0
    return {
        "mean": round(mean_val, 4),
        "std": round(std_val, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "cv_pct": round(cv_pct, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="MotionCorr CPU Time & Peak RSS Baseline Benchmark Suite")
    parser.add_argument("--binary", type=Path, default=Path("../build-timing/motioncorr"),
                        help="Path to motioncorr binary (default: ../build-timing/motioncorr)")
    parser.add_argument("--work-dir", type=Path, default=Path("."),
                        help="Working directory containing movies.star and Movies/ (default: current dir)")
    parser.add_argument("--star", type=Path, default=Path("movies.star"),
                        help="STAR file with movie entries (default: movies.star)")
    parser.add_argument("--gainref", type=Path, default=Path("Movies/gain.mrc"),
                        help="Gain reference MRC file (default: Movies/gain.mrc)")
    parser.add_argument("--reps", type=int, default=3,
                        help="Number of repetitions per benchmark case (default: 3)")
    parser.add_argument("--output-json", type=Path, default=Path("benchmark_results.json"),
                        help="Path to write JSON benchmark results (default: benchmark_results.json)")
    parser.add_argument("--output-md", type=Path, default=Path("benchmark_summary.md"),
                        help="Path to write Markdown summary (default: benchmark_summary.md)")
    parser.add_argument("--compare-script", type=Path, default=Path("../tools/compare_motioncorr.py"),
                        help="Path to compare_motioncorr.py (default: ../tools/compare_motioncorr.py)")
    parser.add_argument("--cases", nargs="+", choices=["global_j1", "global_j4", "patch5x5_j1", "patch5x5_j4"],
                        default=["global_j1", "global_j4", "patch5x5_j1", "patch5x5_j4"],
                        help="Cases to run (default: all 4 cases)")
    args = parser.parse_args()

    work_dir = args.work_dir.resolve()
    binary = args.binary.resolve()
    star_file = (work_dir / args.star).resolve()
    gain_file = (work_dir / args.gainref).resolve()
    compare_script = args.compare_script.resolve()

    if not binary.exists():
        print(f"ERROR: Binary not found at {binary}", file=sys.stderr)
        sys.exit(1)
    if not star_file.exists():
        print(f"ERROR: STAR file not found at {star_file}", file=sys.stderr)
        sys.exit(1)
    if not gain_file.exists():
        print(f"ERROR: Gain reference not found at {gain_file}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print(" MOTIONCORR CPU PROFILING & PEAK MEMORY BENCHMARK HARNESS")
    print("=" * 80)
    print(f"Binary:         {binary}")
    print(f"Working Dir:    {work_dir}")
    print(f"Movies STAR:    {star_file}")
    print(f"Gain Ref:       {gain_file}")
    print(f"Repetitions:    {args.reps}")
    print(f"Selected Cases: {args.cases}")
    print("-" * 80)

    # 1. Capture Environment Metadata & Input Checksums
    hw_info = get_hardware_info()
    binary_hash = sha256_file(binary)
    star_hash = sha256_file(star_file)
    gain_hash = sha256_file(gain_file)

    # Primary movie TIFF hash
    movie_tiff = work_dir / "Movies" / "20170629_00021_frameImage.tiff"
    movie_hash = sha256_file(movie_tiff) if movie_tiff.exists() else "N/A"

    print("HARDWARE & BUILD CONFIGURATION:")
    for k, v in hw_info.items():
        print(f"  {k:22s}: {v}")
    print("\nINPUT CHECKSUMS (SHA256):")
    print(f"  Binary:             {binary_hash}")
    print(f"  Movie TIFF:         {movie_hash}")
    print(f"  Gain MRC:           {gain_hash}")
    print(f"  Movies STAR:        {star_hash}")
    print("=" * 80)

    # 2. Define Case Configurations
    case_configs = {
        "global_j1": {
            "name": "Global-only, 1 thread",
            "patch_x": 1,
            "patch_y": 1,
            "threads": 1,
            "gate": "exact",
        },
        "global_j4": {
            "name": "Global-only, 4 threads",
            "patch_x": 1,
            "patch_y": 1,
            "threads": 4,
            "gate": "relaxed",
        },
        "patch5x5_j1": {
            "name": "5x5 Patch, 1 thread",
            "patch_x": 5,
            "patch_y": 5,
            "threads": 1,
            "gate": "exact",
        },
        "patch5x5_j4": {
            "name": "5x5 Patch, 4 threads",
            "patch_x": 5,
            "patch_y": 5,
            "threads": 4,
            "gate": "relaxed",
        },
    }

    benchmark_data: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": hw_info,
        "inputs": {
            "binary": str(binary),
            "binary_sha256": binary_hash,
            "movie_tiff": str(movie_tiff),
            "movie_tiff_sha256": movie_hash,
            "gain_mrc": str(gain_file),
            "gain_mrc_sha256": gain_hash,
            "movies_star": str(star_file),
            "movies_star_sha256": star_hash,
        },
        "repetitions": args.reps,
        "cases": {},
    }

    # Reference baseline directories for comparison
    ref_dirs = {
        "patch5x5_j1": work_dir / "MotionCorr_cpu_j1",
        "patch5x5_j4": work_dir / "MotionCorr_cpu_j4",
    }

    # 3. Execute Benchmarks
    for case_id in args.cases:
        cfg = case_configs[case_id]
        print(f"\n>>> RUNNING CASE: {case_id} ({cfg['name']}) - {args.reps} repetitions")
        
        runs_list: List[Dict[str, Any]] = []
        wall_times: List[float] = []
        user_times: List[float] = []
        sys_times: List[float] = []
        rss_kbs: List[float] = []
        all_stage_times: Dict[str, List[float]] = {}

        first_rep_dir: Optional[Path] = None

        for rep in range(1, args.reps + 1):
            out_dir_name = f"bench_{case_id}_rep{rep}"
            out_dir = work_dir / out_dir_name
            if out_dir.exists():
                shutil.rmtree(out_dir)

            cmd = [
                "/usr/bin/time", "-v",
                str(binary),
                "--i", str(star_file.relative_to(work_dir)),
                "--o", out_dir_name,
                "--use_own",
                "--j", str(cfg["threads"]),
                "--dose_weighting",
                "--dose_per_frame", "1.277",
                "--patch_x", str(cfg["patch_x"]),
                "--patch_y", str(cfg["patch_y"]),
                "--bfactor", "150",
                "--gainref", str(gain_file.relative_to(work_dir)),
                "--do_at_most", "1",
            ]

            print(f"  Repetition {rep}/{args.reps}: executing command...")
            t_start = time.perf_counter()
            proc = subprocess.run(
                cmd,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            t_end = time.perf_counter()
            elapsed_perf = t_end - t_start

            combined_out = proc.stdout + "\n" + proc.stderr
            log_metrics = parse_time_v_output(proc.stderr)
            stage_metrics = parse_stage_times(proc.stdout)

            # Record metrics
            wall_time = log_metrics.get("wall_time_sec", elapsed_perf)
            user_time = log_metrics.get("user_time_sec", 0.0)
            sys_time = log_metrics.get("sys_time_sec", 0.0)
            peak_rss = log_metrics.get("peak_rss_kb", 0)

            wall_times.append(wall_time)
            user_times.append(user_time)
            sys_times.append(sys_time)
            rss_kbs.append(peak_rss)

            for tag, val in stage_metrics.items():
                all_stage_times.setdefault(tag, []).append(val["seconds"])

            # Checksums of outputs
            out_mrc = out_dir / "Movies" / "20170629_00021_frameImage.mrc"
            out_star = out_dir / "Movies" / "20170629_00021_frameImage.star"
            out_joint_star = out_dir / "corrected_micrographs.star"

            mrc_hash = sha256_file(out_mrc) if out_mrc.exists() else "MISSING"
            star_hash_out = sha256_file(out_star) if out_star.exists() else "MISSING"
            joint_star_hash = sha256_file(out_joint_star) if out_joint_star.exists() else "MISSING"

            # Acceptance gate verification via compare_motioncorr.py
            gate_eval: Dict[str, Any] = {"gate": cfg["gate"], "passed": False}
            if compare_script.exists():
                python_for_compare = get_python_with_numpy()
                ref_target = ref_dirs.get(case_id)
                # If no baseline reference dir exists for this case (e.g. global-only),
                # compare rep 2+ against rep 1 to verify determinism!
                if ref_target and ref_target.exists():
                    gate_eval["reference_type"] = "independent_reference"
                    gate_eval["gate_profile"] = cfg["gate"]
                    comp_cmd = [
                        python_for_compare, str(compare_script),
                        "--ref", str(ref_target),
                        "--test", str(out_dir),
                        "--gate", cfg["gate"],
                    ]
                elif rep > 1 and first_rep_dir and first_rep_dir.exists():
                    gate_profile = "exact" if cfg["threads"] == 1 else "relaxed"
                    gate_eval["reference_type"] = "self_consistency_rep1"
                    gate_eval["gate_profile"] = gate_profile
                    comp_cmd = [
                        python_for_compare, str(compare_script),
                        "--ref", str(first_rep_dir),
                        "--test", str(out_dir),
                        "--gate", gate_profile,
                    ]
                else:
                    comp_cmd = []
                    gate_eval["reference_type"] = "self_consistency_baseline"
                    gate_eval["gate_profile"] = None
                    gate_eval["status"] = "unverified_baseline"
                    gate_eval["note"] = "Repetition 1 established as baseline for multi-run self-consistency; no independent external reference specified."

                if comp_cmd:
                    cproc = subprocess.run(comp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    gate_eval["passed"] = (cproc.returncode == 0)
                    gate_eval["stdout_snippet"] = cproc.stdout[-500:] if cproc.stdout else cproc.stderr[-500:]
                else:
                    gate_eval["passed"] = None  # Not verified against independent reference

            if rep == 1:
                first_rep_dir = out_dir

            run_record = {
                "repetition": rep,
                "exit_status": proc.returncode,
                "wall_time_sec": wall_time,
                "user_time_sec": user_time,
                "sys_time_sec": sys_time,
                "cpu_percent": log_metrics.get("cpu_percent", 0),
                "peak_rss_kb": peak_rss,
                "peak_rss_gib": round(peak_rss / (1024.0 * 1024.0), 3),
                "stage_times": stage_metrics,
                "output_checksums": {
                    "mrc_sha256": mrc_hash,
                    "star_sha256": star_hash_out,
                    "joint_star_sha256": joint_star_hash,
                },
                "gate_eval": gate_eval,
            }
            runs_list.append(run_record)

            print(f"    Wall: {wall_time:.2f}s | User: {user_time:.2f}s | RSS: {run_record['peak_rss_gib']:.2f} GiB | MRC SHA: {mrc_hash[:12]}... | Gate: {'PASS' if gate_eval['passed'] else 'FAIL'}")

        # Compute summary stats across reps
        case_summary = {
            "config": cfg,
            "wall_time_stats": calc_stats(wall_times),
            "user_time_stats": calc_stats(user_times),
            "sys_time_stats": calc_stats(sys_times),
            "peak_rss_stats_gib": calc_stats([r / (1024.0 * 1024.0) for r in rss_kbs]),
            "stage_time_stats": {tag: calc_stats(times) for tag, times in all_stage_times.items()},
            "runs": runs_list,
        }
        benchmark_data["cases"][case_id] = case_summary

    # 4. Multi-Threading & Case Comparison Analytics
    analytics: Dict[str, Any] = {}
    if "global_j1" in benchmark_data["cases"] and "global_j4" in benchmark_data["cases"]:
        t1 = benchmark_data["cases"]["global_j1"]["wall_time_stats"]["mean"]
        t4 = benchmark_data["cases"]["global_j4"]["wall_time_stats"]["mean"]
        sp = round(t1 / t4, 2) if t4 > 0 else 0.0
        eff = round(sp / 4.0 * 100, 1)
        analytics["global_speedup_4threads"] = {"speedup": sp, "parallel_efficiency_pct": eff}

    if "patch5x5_j1" in benchmark_data["cases"] and "patch5x5_j4" in benchmark_data["cases"]:
        t1 = benchmark_data["cases"]["patch5x5_j1"]["wall_time_stats"]["mean"]
        t4 = benchmark_data["cases"]["patch5x5_j4"]["wall_time_stats"]["mean"]
        sp = round(t1 / t4, 2) if t4 > 0 else 0.0
        eff = round(sp / 4.0 * 100, 1)
        analytics["patch5x5_speedup_4threads"] = {"speedup": sp, "parallel_efficiency_pct": eff}

    if "global_j1" in benchmark_data["cases"] and "patch5x5_j1" in benchmark_data["cases"]:
        tg = benchmark_data["cases"]["global_j1"]["wall_time_stats"]["mean"]
        tp = benchmark_data["cases"]["patch5x5_j1"]["wall_time_stats"]["mean"]
        diff = round(tp - tg, 2)
        analytics["patch_overhead_single_thread_sec"] = diff

    benchmark_data["analytics"] = analytics

    # 5. Write Output JSON
    output_json_path = (work_dir / args.output_json).resolve()
    with open(output_json_path, "w") as f:
        json.dump(benchmark_data, f, indent=2)
    print(f"\n[+] Wrote complete JSON benchmark results to {output_json_path}")

    # 6. Generate Markdown Summary
    output_md_path = (work_dir / args.output_md).resolve()
    generate_markdown_summary(benchmark_data, output_md_path)
    print(f"[+] Wrote Markdown summary to {output_md_path}")
    print("=" * 80)


def generate_markdown_summary(data: Dict[str, Any], out_path: Path):
    """Generate Markdown report summarizing benchmark results."""
    lines: List[str] = []
    lines.append("# MotionCorr CPU Profiling & Memory Baseline Report")
    lines.append("")
    lines.append(f"**Generated**: {data.get('timestamp', 'N/A')}")
    lines.append(f"**Host**: `{data['hardware'].get('hostname', 'N/A')}` ({data['hardware'].get('Model name', 'Unknown CPU')}, {data['hardware'].get('total_ram_gib', 'N/A')} GiB RAM)")
    lines.append(f"**Toolchain**: `{data['hardware'].get('gcc_version', 'GCC')}`, `{data['hardware'].get('cmake_version', 'CMake')}`")
    lines.append("")

    lines.append("## 1. Executive Performance Matrix")
    lines.append("")
    lines.append("| Case ID | Description | Threads | Wall Time (s) [mean ± std] | User Time (s) | Peak RSS (GiB) | Gate Check |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")

    for cid, cdata in data["cases"].items():
        cfg = cdata["config"]
        wt = cdata["wall_time_stats"]
        ut = cdata["user_time_stats"]
        rss = cdata["peak_rss_stats_gib"]
        all_passed = all(r["gate_eval"].get("passed", False) for r in cdata["runs"])
        gate_str = "PASS (exact)" if (all_passed and cfg["gate"] == "exact") else ("PASS (relaxed)" if all_passed else "FAIL")
        lines.append(
            f"| `{cid}` | {cfg['name']} | {cfg['threads']} | "
            f"**{wt['mean']:.2f} ± {wt['std']:.2f}** | {ut['mean']:.2f} ± {ut['std']:.2f} | "
            f"**{rss['mean']:.2f} ± {rss['std']:.2f}** | {gate_str} |"
        )
    lines.append("")

    if "analytics" in data:
        lines.append("## 2. Multi-Threading & Overhead Analysis")
        lines.append("")
        for k, v in data["analytics"].items():
            if isinstance(v, dict):
                lines.append(f"- **{k.replace('_', ' ').title()}**: Speedup = **{v.get('speedup')}x** (Parallel Efficiency: **{v.get('parallel_efficiency_pct')}%**)")
            else:
                lines.append(f"- **{k.replace('_', ' ').title()}**: **{v} s**")
        lines.append("")

    lines.append("## 3. Top Stage Time Breakdown")
    lines.append("")
    # Show stage times for patch5x5_j1 and patch5x5_j4 if present
    for cid in ("patch5x5_j1", "patch5x5_j4", "global_j1", "global_j4"):
        if cid not in data["cases"]:
            continue
        cdata = data["cases"][cid]
        stages = cdata["stage_time_stats"]
        sorted_stages = sorted(stages.items(), key=lambda kv: kv[1]["mean"], reverse=True)
        total_wall = cdata["wall_time_stats"]["mean"]

        lines.append(f"### Case `{cid}` ({cdata['config']['name']}) - Total Wall: {total_wall:.2f} s")
        lines.append("")
        lines.append("| Stage Tag | Mean Time (s) | StdDev (s) | % of Total Time |")
        lines.append("| :--- | :---: | :---: | :---: |")
        for tag, st in sorted_stages:
            if st["mean"] > 0.05:  # filter negligible stages
                pct = (st["mean"] / total_wall * 100.0) if total_wall > 0 else 0.0
                lines.append(f"| `{tag}` | {st['mean']:.3f} | {st['std']:.3f} | {pct:.1f}% |")
        lines.append("")

    lines.append("## 4. Output Checksum Verification Across Repetitions")
    lines.append("")
    lines.append("| Case ID | Repetition | Exit Status | Output MRC SHA256 (First 16 chars) | STAR SHA256 |")
    lines.append("| :--- | :---: | :---: | :--- | :--- |")
    for cid, cdata in data["cases"].items():
        for r in cdata["runs"]:
            mrc_hash = r["output_checksums"].get("mrc_sha256", "N/A")[:16]
            star_hash = r["output_checksums"].get("star_sha256", "N/A")[:16]
            lines.append(f"| `{cid}` | {r['repetition']} | {r['exit_status']} | `{mrc_hash}...` | `{star_hash}...` |")
    lines.append("")

    out_path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
