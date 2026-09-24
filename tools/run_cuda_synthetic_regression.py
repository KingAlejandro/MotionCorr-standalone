#!/usr/bin/env python3
"""Fast, trustworthy synthetic CPU-versus-CUDA regression harness for MotionCorr.

Executes single-threaded CPU (--j 1) and CUDA global alignment (--gpu <id> --j 1)
with identical parameters, random seeds, and disabled local patches (--patch_x 1 --patch_y 1)
on synthetic movies with known ground truth shifts.

Evaluates:
1. CPU vs Known Shifts (Ground Truth recovery)
2. CUDA vs Known Shifts (Ground Truth recovery)
3. CUDA vs CPU (Numerical Equivalence under Gate 2 / relaxed tolerances)

Reuses tools/compare_motioncorr.py and adheres strictly to declared acceptance gates.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def compute_sha256(filepath: Path) -> str:
    """Compute hex SHA256 checksum of a file."""
    h = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def detect_python() -> str:
    """Find a Python interpreter with numpy available."""
    candidates = [
        sys.executable,
        os.environ.get("PYTHON"),
        Path.home() / "mc-env/bin/python3",
        Path.home() / "miniforge3/envs/cil/bin/python3",
        "python3",
    ]
    for c in candidates:
        if not c:
            continue
        c_str = str(c)
        try:
            res = subprocess.run(
                [c_str, "-c", "import numpy"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode == 0:
                return c_str
        except Exception:
            continue
    return sys.executable


def get_git_commit(repo_root: Path) -> str:
    """Get current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def get_gpu_info(gpu_id: int) -> Dict[str, Any]:
    """Query nvidia-smi for GPU model and driver version if available."""
    info: Dict[str, Any] = {"gpu_id": gpu_id, "available": False}
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_id}",
                "--query-gpu=name,driver_version",
                "--format=csv,noheader",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        lines = res.stdout.strip().splitlines()
        if lines:
            parts = [p.strip() for p in lines[0].split(",")]
            info["gpu_name"] = parts[0]
            if len(parts) > 1:
                info["driver_version"] = parts[1]
            info["available"] = True
    except Exception:
        info["gpu_name"] = "N/A (nvidia-smi unavailable or device not present)"
    return info


def run_motioncorr_process(
    binary: Path,
    fixture_dir: Path,
    star_name: str,
    out_dir: Path,
    extra_args: List[str],
) -> Tuple[int, float, Path, List[str]]:
    """Run a single MotionCorr process and log output."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "run.log"
    cmd = [
        str(binary),
        "--i",
        star_name,
        "--o",
        str(out_dir),
        "--use_own",
        "--j",
        "1",
        "--patch_x",
        "1",
        "--patch_y",
        "1",
    ] + extra_args

    t0 = time.perf_counter()
    with log_file.open("w") as lf:
        proc = subprocess.run(
            cmd,
            cwd=str(fixture_dir),
            stdout=lf,
            stderr=subprocess.STDOUT,
            text=True,
        )
    elapsed = time.perf_counter() - t0
    return proc.returncode, elapsed, log_file, cmd


def run_comparator(
    python_bin: str,
    comparator_script: Path,
    ref: Optional[Path] = None,
    test: Optional[Path] = None,
    ground_truth: Optional[Path] = None,
    ref_star: Optional[Path] = None,
    test_star: Optional[Path] = None,
    gate: str = "relaxed",
    json_out: Optional[Path] = None,
) -> Tuple[int, Dict[str, Any], str]:
    """Invoke compare_motioncorr.py and return (exit_code, report_dict, raw_stdout)."""
    cmd = [python_bin, str(comparator_script), "--gate", gate]
    if ref is not None:
        cmd.extend(["--ref", str(ref)])
    if test is not None:
        cmd.extend(["--test", str(test)])
    if ground_truth is not None:
        cmd.extend(["--ground-truth", str(ground_truth)])
    if ref_star is not None:
        cmd.extend(["--ref-star", str(ref_star)])
    if test_star is not None:
        cmd.extend(["--test-star", str(test_star)])

    temp_json = None
    if json_out is None:
        tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        temp_json = Path(tf.name)
        tf.close()
        target_json = temp_json
    else:
        target_json = json_out

    cmd.extend(["--json-out", str(target_json)])

    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    report: Dict[str, Any] = {}
    if target_json.is_file() and target_json.stat().st_size > 0:
        try:
            report = json.loads(target_json.read_text())
        except Exception as e:
            report = {"overall_status": "ERROR", "error": f"Failed to parse comparator JSON: {e}"}

    if temp_json is not None and temp_json.is_file():
        temp_json.unlink(missing_ok=True)

    return res.returncode, report, res.stdout


def verify_fixture_outputs(out_dir: Path, movie_base: str) -> List[str]:
    """Verify that expected MotionCorr output files exist."""
    errors = []
    expected_files = [
        out_dir / f"{movie_base}.mrc",
        out_dir / f"{movie_base}.star",
        out_dir / "corrected_micrographs.star",
    ]
    for ef in expected_files:
        if not ef.is_file():
            errors.append(f"Missing expected output file: {ef}")
        elif ef.stat().st_size == 0:
            errors.append(f"Output file is empty: {ef}")
    return errors


def run_fixture_case(
    case_name: str,
    fixture_star: Path,
    ground_truth_json: Path,
    cpu_bin: Path,
    cuda_bin: Path,
    gpu_id: int,
    seed: int,
    case_run_dir: Path,
    comparator_script: Path,
    python_bin: str,
    gate: str = "relaxed",
    gt_threshold_rms: float = 0.15,
    gt_threshold_max: float = 0.25,
) -> Dict[str, Any]:
    """Execute both CPU and CUDA on a fixture and evaluate parity and ground truth."""
    case_report: Dict[str, Any] = {
        "case_name": case_name,
        "fixture_star": str(fixture_star),
        "ground_truth_json": str(ground_truth_json),
        "passed": False,
        "fail_reasons": [],
    }

    movie_base = fixture_star.stem
    fixture_dir = fixture_star.parent

    # Input file checksums
    input_files: Dict[str, Any] = {
        "star": {"path": str(fixture_star), "sha256": compute_sha256(fixture_star)},
        "ground_truth": {"path": str(ground_truth_json), "sha256": compute_sha256(ground_truth_json)},
    }
    mrcs_candidates = [
        fixture_dir / f"{movie_base}.mrcs",
        fixture_dir / f"{movie_base}.mrc",
    ]
    for mc in mrcs_candidates:
        if mc.is_file():
            input_files["movie"] = {"path": str(mc), "sha256": compute_sha256(mc)}
            break
    case_report["input_files"] = input_files

    cpu_dir = case_run_dir / "cpu"
    cuda_dir = case_run_dir / "cuda"

    # 1. Execute CPU
    cpu_code, cpu_sec, cpu_log, cpu_cmd = run_motioncorr_process(
        binary=cpu_bin,
        fixture_dir=fixture_dir,
        star_name=fixture_star.name,
        out_dir=cpu_dir,
        extra_args=["--seed", str(seed)],
    )
    case_report["cpu_run"] = {
        "command": " ".join(cpu_cmd),
        "exit_code": cpu_code,
        "elapsed_sec": round(cpu_sec, 4),
        "log_path": str(cpu_log),
    }
    if cpu_code != 0:
        case_report["fail_reasons"].append(f"CPU motioncorr process exited with nonzero status {cpu_code}")

    # 2. Execute CUDA
    cuda_code, cuda_sec, cuda_log, cuda_cmd = run_motioncorr_process(
        binary=cuda_bin,
        fixture_dir=fixture_dir,
        star_name=fixture_star.name,
        out_dir=cuda_dir,
        extra_args=["--seed", str(seed), "--gpu", str(gpu_id)],
    )
    case_report["cuda_run"] = {
        "command": " ".join(cuda_cmd),
        "exit_code": cuda_code,
        "elapsed_sec": round(cuda_sec, 4),
        "log_path": str(cuda_log),
    }
    if cuda_code != 0:
        case_report["fail_reasons"].append(f"CUDA motioncorr process exited with nonzero status {cuda_code}")

    # Check for expected files
    cpu_missing = verify_fixture_outputs(cpu_dir, movie_base)
    if cpu_missing:
        case_report["fail_reasons"].extend(cpu_missing)

    cuda_missing = verify_fixture_outputs(cuda_dir, movie_base)
    if cuda_missing:
        case_report["fail_reasons"].extend(cuda_missing)

    # 3. Evaluate Ground Truth Recovery: CPU vs Ground Truth
    cpu_vs_gt_json = case_run_dir / "comp_cpu_vs_gt.json"
    c_gt_code, c_gt_rep, _ = run_comparator(
        python_bin=python_bin,
        comparator_script=comparator_script,
        ref=cpu_dir,
        test=cpu_dir,
        ground_truth=ground_truth_json,
        gate="exact",
        json_out=cpu_vs_gt_json,
    )
    case_report["cpu_vs_ground_truth"] = {
        "comparator_exit": c_gt_code,
        "comparator_status": c_gt_rep.get("overall_status"),
        "report": c_gt_rep.get("checks", {}).get("ground_truth_recovery", {}),
    }
    gt_cpu = c_gt_rep.get("checks", {}).get("ground_truth_recovery", {})
    if "error" in gt_cpu:
        case_report["fail_reasons"].append(f"CPU GT recovery evaluation error: {gt_cpu['error']}")
    else:
        rms_err = gt_cpu.get("coord_rms_error")
        max_err = gt_cpu.get("max_shift_error")
        if rms_err is None or max_err is None:
            case_report["fail_reasons"].append("CPU GT recovery missing shift metrics (never substitute 0.0)")
        elif rms_err > gt_threshold_rms or max_err > gt_threshold_max:
            case_report["fail_reasons"].append(
                f"CPU GT recovery exceeded threshold: rms={rms_err:.4f} > {gt_threshold_rms:.4f} or max={max_err:.4f} > {gt_threshold_max:.4f}"
            )

    # 4. Evaluate Ground Truth Recovery: CUDA vs Ground Truth
    cuda_vs_gt_json = case_run_dir / "comp_cuda_vs_gt.json"
    cu_gt_code, cu_gt_rep, _ = run_comparator(
        python_bin=python_bin,
        comparator_script=comparator_script,
        ref=cuda_dir,
        test=cuda_dir,
        ground_truth=ground_truth_json,
        gate=gate,
        json_out=cuda_vs_gt_json,
    )
    case_report["cuda_vs_ground_truth"] = {
        "comparator_exit": cu_gt_code,
        "comparator_status": cu_gt_rep.get("overall_status"),
        "report": cu_gt_rep.get("checks", {}).get("ground_truth_recovery", {}),
    }
    gt_cuda = cu_gt_rep.get("checks", {}).get("ground_truth_recovery", {})
    if "error" in gt_cuda:
        case_report["fail_reasons"].append(f"CUDA GT recovery evaluation error: {gt_cuda['error']}")
    else:
        rms_err = gt_cuda.get("coord_rms_error")
        max_err = gt_cuda.get("max_shift_error")
        if rms_err is None or max_err is None:
            case_report["fail_reasons"].append("CUDA GT recovery missing shift metrics (never substitute 0.0)")
        elif rms_err > gt_threshold_rms or max_err > gt_threshold_max:
            case_report["fail_reasons"].append(
                f"CUDA GT recovery exceeded threshold: rms={rms_err:.4f} > {gt_threshold_rms:.4f} or max={max_err:.4f} > {gt_threshold_max:.4f}"
            )

    # 5. Evaluate Numerical Acceptance: CUDA vs CPU
    cuda_vs_cpu_json = case_run_dir / "comp_cuda_vs_cpu.json"
    c_vs_code, c_vs_rep, _ = run_comparator(
        python_bin=python_bin,
        comparator_script=comparator_script,
        ref=cpu_dir,
        test=cuda_dir,
        gate=gate,
        json_out=cuda_vs_cpu_json,
    )

    coverage = c_vs_rep.get("coverage", {})
    complete_cov = coverage.get("complete", False)
    checks = c_vs_rep.get("checks", {})

    traj_check = checks.get("motion_trajectory", {})
    img_check = checks.get("corrected_image", {})
    star_check = checks.get("star_fields", {})

    # Extract required metrics strictly without substituting 0.0 for missing
    metrics: Dict[str, Any] = {
        "coord_rms_shift_px": traj_check.get("coord_rms_error"),
        "max_shift_px": traj_check.get("max_shift_error"),
        "image_rmse": img_check.get("rmse"),
        "relative_rmse": img_check.get("relative_rmse"),
        "max_pixel_diff": img_check.get("max_abs_pixel_error"),
        "pixel_identical": img_check.get("pixel_identical"),
        "star_diffs": star_check.get("num_differences"),
    }

    case_report["cuda_vs_cpu"] = {
        "comparator_exit": c_vs_code,
        "comparator_status": c_vs_rep.get("overall_status"),
        "coverage_complete": complete_cov,
        "metrics": metrics,
        "checks": checks,
    }

    if c_vs_code != 0:
        case_report["fail_reasons"].append(f"CUDA vs CPU comparator exited with nonzero code {c_vs_code}")

    if c_vs_rep.get("overall_status") != "PASS":
        case_report["fail_reasons"].append(f"CUDA vs CPU comparator overall_status was '{c_vs_rep.get('overall_status')}'")

    if not complete_cov:
        case_report["fail_reasons"].append("CUDA vs CPU comparison coverage incomplete (missing MRC or STAR pair)")

    for check_name, check_obj in [("motion_trajectory", traj_check), ("corrected_image", img_check), ("star_fields", star_check)]:
        if not check_obj:
            case_report["fail_reasons"].append(f"Missing '{check_name}' check in comparator report")
        elif not check_obj.get("passed", False):
            case_report["fail_reasons"].append(f"Check '{check_name}' failed: {check_obj.get('fail_reasons', ['unspecified failure'])}")

    for metric_name, metric_val in metrics.items():
        if metric_name != "pixel_identical" and metric_val is None:
            case_report["fail_reasons"].append(f"Metric '{metric_name}' is missing (not evaluated)")

    case_report["passed"] = (len(case_report["fail_reasons"]) == 0)
    return case_report


def print_case_summary(report: Dict[str, Any], gate_profile: str) -> None:
    """Print human-readable summary of case comparison."""
    case_name = report["case_name"]
    status_str = "PASS" if report["passed"] else "FAIL"

    print("-" * 78)
    print(f" CASE: {case_name:<30} STATUS: {status_str}")
    print("-" * 78)

    cpu_run = report.get("cpu_run", {})
    cuda_run = report.get("cuda_run", {})
    print(f" CPU Run:   status={cpu_run.get('exit_code')} wall={cpu_run.get('elapsed_sec')}s")
    print(f" CUDA Run:  status={cuda_run.get('exit_code')} wall={cuda_run.get('elapsed_sec')}s")

    gt_cpu = report.get("cpu_vs_ground_truth", {}).get("report", {})
    gt_cuda = report.get("cuda_vs_ground_truth", {}).get("report", {})
    print("\n [Ground Truth Recovery Against Known Shifts]")
    if "coord_rms_error" in gt_cpu:
        print(f"   CPU  RMS error: {gt_cpu['coord_rms_error']:.6f} px | Max error: {gt_cpu['max_shift_error']:.6f} px")
    else:
        print("   CPU  RMS error: MISSING / ERROR")
    if "coord_rms_error" in gt_cuda:
        print(f"   CUDA RMS error: {gt_cuda['coord_rms_error']:.6f} px | Max error: {gt_cuda['max_shift_error']:.6f} px")
    else:
        print("   CUDA RMS error: MISSING / ERROR")

    cu_cpu = report.get("cuda_vs_cpu", {})
    metrics = cu_cpu.get("metrics", {})
    print(f"\n [CUDA vs CPU Parity Checks ({gate_profile.upper()} Gate)]")
    cov_str = "COMPLETE" if cu_cpu.get("coverage_complete") else "INCOMPLETE"
    print(f"   Coverage:              {cov_str}")
    print(f"   Comparator Status:     {cu_cpu.get('comparator_status')}")

    def fmt_val(v: Any, fmt: str = ".6f") -> str:
        if v is None:
            return "MISSING"
        return f"{v:{fmt}}"

    print(f"   Coord RMS Shift Error: {fmt_val(metrics.get('coord_rms_shift_px'))} px (Gate 2: <= 0.020 px)")
    print(f"   Max Frame Shift Error: {fmt_val(metrics.get('max_shift_px'))} px (Gate 2: <= 0.050 px)")
    print(f"   Image Absolute RMSE:   {fmt_val(metrics.get('image_rmse'), '.6e')} (Gate 2: <= 0.020)")
    print(f"   Image Relative RMSE:   {fmt_val(metrics.get('relative_rmse'), '.6e')} (Gate 2: <= 0.001)")
    print(f"   Image Max Pixel Error: {fmt_val(metrics.get('max_pixel_diff'), '.6e')} (Gate 2: <= 5.0)")
    print(f"   STAR Discrepancies:    {metrics.get('star_diffs')} (Gate 2: == 0)")

    if report["fail_reasons"]:
        print("\n [FAILURE REASONS]")
        for fr in report["fail_reasons"]:
            print(f"   ! {fr}")
    print("-" * 78)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fast synthetic CPU-versus-CUDA regression harness for MotionCorr"
    )
    parser.add_argument(
        "--cpu-bin",
        type=Path,
        default=None,
        help="Path to CPU motioncorr executable (default: auto-detected in build/ or build-cpu/)",
    )
    parser.add_argument(
        "--cuda-bin",
        type=Path,
        default=None,
        help="Path to CUDA motioncorr executable (default: auto-detected in build-cuda/ or build/)",
    )
    parser.add_argument(
        "--gpu",
        type=int,
        default=0,
        help="CUDA GPU device ID (default: 0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260923,
        help="Random seed for MotionCorr execution (default: 20260923)",
    )
    parser.add_argument(
        "--gate",
        choices=["relaxed", "exact"],
        default="relaxed",
        help="Acceptance gate profile for CUDA vs CPU (default: relaxed / Gate 2)",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=None,
        help="Directory with synthetic fixtures (default: test-data/fixtures relative to repo)",
    )
    parser.add_argument(
        "--include-subpixel",
        action="store_true",
        help="Include subpixel synthetic fixture case in addition to integer fixture",
    )
    parser.add_argument(
        "--subpixel-only",
        action="store_true",
        help="Run only the subpixel synthetic fixture case",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Base directory for outputs (default: temporary directory)",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Preserve run output artifacts even on success",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Save full structured JSON report to this file",
    )
    parser.add_argument(
        "--gt-threshold-rms",
        type=float,
        default=0.15,
        help="Declared threshold for ground truth RMS shift error (default: 0.15 px)",
    )
    parser.add_argument(
        "--gt-threshold-max",
        type=float,
        default=0.25,
        help="Declared threshold for ground truth max shift error (default: 0.25 px)",
    )
    parser.add_argument(
        "--python",
        type=str,
        default=None,
        help="Python interpreter for compare_motioncorr.py (default: auto-detected with numpy)",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    python_bin = args.python or detect_python()
    comparator_script = repo_root / "tools" / "compare_motioncorr.py"

    if not comparator_script.is_file():
        print(f"ERROR: Comparator not found at {comparator_script}", file=sys.stderr)
        sys.exit(2)

    # Locate binaries
    cpu_bin = args.cpu_bin
    if cpu_bin is None:
        for c in [repo_root / "build-cpu" / "motioncorr", repo_root / "build" / "motioncorr"]:
            if c.is_file() and os.access(c, os.X_OK):
                cpu_bin = c
                break

    cuda_bin = args.cuda_bin
    if cuda_bin is None:
        for c in [repo_root / "build-cuda" / "motioncorr", repo_root / "build" / "motioncorr"]:
            if c.is_file() and os.access(c, os.X_OK):
                cuda_bin = c
                break

    if cpu_bin is None or not cpu_bin.is_file() or not os.access(cpu_bin, os.X_OK):
        print(f"ERROR: CPU executable not found or not executable: {cpu_bin}", file=sys.stderr)
        print("Please build motioncorr or specify --cpu-bin PATH", file=sys.stderr)
        sys.exit(2)

    if cuda_bin is None or not cuda_bin.is_file() or not os.access(cuda_bin, os.X_OK):
        print(f"ERROR: CUDA executable not found or not executable: {cuda_bin}", file=sys.stderr)
        print("Please build motioncorr with -DCUDA=ON or specify --cuda-bin PATH", file=sys.stderr)
        sys.exit(2)

    # Locate fixture directory
    fixture_dir = args.fixture_dir or (repo_root / "test-data" / "fixtures")
    if not fixture_dir.is_dir():
        print(f"ERROR: Fixture directory not found: {fixture_dir}", file=sys.stderr)
        sys.exit(2)

    # Resolve fixture cases
    cases: List[Tuple[str, Path, Path]] = []
    if not args.subpixel_only:
        cases.append((
            "integer_shift_128x128",
            fixture_dir / "synthetic_128x128_8frames.star",
            fixture_dir / "synthetic_128x128_8frames_ground_truth.json",
        ))
    if args.include_subpixel or args.subpixel_only:
        cases.append((
            "subpixel_shift_128x128",
            fixture_dir / "synthetic_128x128_8frames_subpixel.star",
            fixture_dir / "synthetic_128x128_8frames_subpixel_ground_truth.json",
        ))

    for name, star, gt in cases:
        if not star.is_file():
            print(f"ERROR: Fixture STAR file not found for case '{name}': {star}", file=sys.stderr)
            sys.exit(2)
        if not gt.is_file():
            print(f"ERROR: Ground truth JSON file not found for case '{name}': {gt}", file=sys.stderr)
            sys.exit(2)

    # Output directory handling
    created_temp = False
    if args.output_dir is not None:
        run_output_base = args.output_dir.resolve()
        run_output_base.mkdir(parents=True, exist_ok=True)
    else:
        run_output_base = Path(tempfile.mkdtemp(prefix="mc_cuda_syn_"))
        created_temp = True

    harness_t0 = time.perf_counter()
    gpu_info = get_gpu_info(args.gpu)
    git_commit = get_git_commit(repo_root)

    print("=" * 78)
    print(" MOTIONCORR SYNTHETIC CPU-VERSUS-CUDA REGRESSION HARNESS")
    print("=" * 78)
    print(f"Commit:          {git_commit}")
    print(f"Host / OS:       {platform.node()} ({platform.system()} {platform.release()})")
    print(f"CPU Binary:      {cpu_bin}")
    print(f"CUDA Binary:     {cuda_bin}")
    print(f"GPU ID:          {args.gpu} ({gpu_info.get('gpu_name', 'Unknown')})")
    print(f"Driver Version:  {gpu_info.get('driver_version', 'N/A')}")
    print(f"Gate Profile:    {args.gate.upper()}")
    print(f"Declared GT Tol: Coordinate RMS <= {args.gt_threshold_rms} px, Max Shift <= {args.gt_threshold_max} px")
    print(f"Seed:            {args.seed}")
    print(f"Output Root:     {run_output_base}")
    print("=" * 78)

    harness_passed = True
    case_reports = []

    for case_name, star_path, gt_path in cases:
        case_dir = run_output_base / case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        case_rep = run_fixture_case(
            case_name=case_name,
            fixture_star=star_path,
            ground_truth_json=gt_path,
            cpu_bin=cpu_bin,
            cuda_bin=cuda_bin,
            gpu_id=args.gpu,
            seed=args.seed,
            case_run_dir=case_dir,
            comparator_script=comparator_script,
            python_bin=python_bin,
            gate=args.gate,
            gt_threshold_rms=args.gt_threshold_rms,
            gt_threshold_max=args.gt_threshold_max,
        )
        case_reports.append(case_rep)
        print_case_summary(case_rep, args.gate)

        if not case_rep["passed"]:
            harness_passed = False

    total_harness_sec = round(time.perf_counter() - harness_t0, 4)

    overall_status = "PASS" if harness_passed else "FAIL"
    print("\n" + "=" * 78)
    print(f" OVERALL HARNESS RESULT: {overall_status} (Total Elapsed: {total_harness_sec}s)")
    print("=" * 78)

    full_report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": overall_status,
        "total_elapsed_sec": total_harness_sec,
        "environment": {
            "git_commit": git_commit,
            "hostname": platform.node(),
            "os": platform.system(),
            "os_release": platform.release(),
            "python": python_bin,
            "cpu_binary": str(cpu_bin),
            "cuda_binary": str(cuda_bin),
            "gpu_info": gpu_info,
        },
        "configuration": {
            "seed": args.seed,
            "gpu_id": args.gpu,
            "gate": args.gate,
            "gt_threshold_rms_px": args.gt_threshold_rms,
            "gt_threshold_max_px": args.gt_threshold_max,
        },
        "cases": case_reports,
    }

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(full_report, indent=2))
        print(f"Report JSON written to: {args.json_out}")

    # Artifact retention logic
    if not harness_passed or args.keep_artifacts:
        print(f"Artifacts preserved at: {run_output_base}")
    else:
        if created_temp:
            shutil.rmtree(run_output_base, ignore_errors=True)

    sys.exit(0 if harness_passed else 1)


if __name__ == "__main__":
    main()
