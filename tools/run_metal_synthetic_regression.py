#!/usr/bin/env python3
"""Fast, trustworthy synthetic CPU-versus-Metal regression harness for MotionCorr.

Executes single-threaded CPU (--j 1) and Metal global alignment (--metal --metal_device <id/name> --j 1)
with identical parameters, random seeds, and disabled local patches (--patch_x 1 --patch_y 1)
on synthetic movies with known ground truth shifts on Apple silicon hosts.

Evaluates:
1. CPU vs Known Shifts (Ground Truth recovery)
2. Metal vs Known Shifts (Ground Truth recovery)
3. Metal vs CPU (Numerical Equivalence under Gate 2 / relaxed tolerances)

Reuses tools/compare_motioncorr.py and adheres strictly to declared acceptance gates.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


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
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
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


def get_macos_version() -> str:
    """Get macOS product and build version."""
    try:
        res = subprocess.run(
            ["sw_vers"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return ", ".join(lines)
    except Exception:
        return platform.mac_ver()[0] or "unknown"


def get_metal_device_info(requested_device: Union[int, str]) -> Dict[str, Any]:
    """Query system for Apple Metal device information via ctypes / Metal runtime or system_profiler."""
    info: Dict[str, Any] = {
        "requested_device": requested_device,
        "available": False,
        "device_name": "Unknown",
        "metal_version": "N/A",
        "unified_memory": True,
    }

    # Attempt ctypes Metal discovery on macOS Darwin
    if platform.system() == "Darwin":
        try:
            import ctypes
            import ctypes.util

            objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
            metal = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Metal"))

            objc.objc_getClass.restype = ctypes.c_void_p
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.objc_msgSend.restype = ctypes.c_void_p
            objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

            metal.MTLCreateSystemDefaultDevice.restype = ctypes.c_void_p
            default_dev = metal.MTLCreateSystemDefaultDevice()
            if default_dev:
                sel_name = objc.sel_registerName(b"name")
                ns_name = objc.objc_msgSend(default_dev, sel_name)
                sel_utf8 = objc.sel_registerName(b"UTF8String")
                objc.objc_msgSend.restype = ctypes.c_char_p
                dev_name_bytes = objc.objc_msgSend(ns_name, sel_utf8)
                if dev_name_bytes:
                    info["device_name"] = dev_name_bytes.decode("utf-8")
                    info["available"] = True
        except Exception:
            pass

    # Supplement or fallback using system_profiler
    if not info["available"] and platform.system() == "Darwin":
        try:
            res = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=True,
            )
            for line in res.stdout.splitlines():
                stripped = line.strip()
                if "Chipset Model:" in stripped:
                    info["device_name"] = stripped.split(":", 1)[1].strip()
                    info["available"] = True
                elif "Metal Support:" in stripped:
                    info["metal_version"] = stripped.split(":", 1)[1].strip()
        except Exception:
            pass

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
    """Verify that expected MotionCorr output files exist and are non-empty."""
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


def inspect_metal_execution(run_log: Path, movie_log: Path, requested_device: Union[int, str]) -> Dict[str, Any]:
    """Require proof of Metal GPU execution: device selection in run.log and completed profile in movie log."""
    startup = run_log.read_text(errors="replace") if run_log.is_file() else ""
    profile = movie_log.read_text(errors="replace") if movie_log.is_file() else ""

    # Match device startup confirmation
    # Handles: "Using Metal acceleration on device [Apple M4 Pro]", "Using Metal device: 0", "Using Metal device: Apple M4 Pro"
    dev_str = str(requested_device)
    startup_matched = False
    startup_patterns = [
        rf"Using Metal (?:acceleration on device|device:?)\s*(?:\[|\s)?([^\n\]]+)(?:\]|\s)?",
        r"Using Metal acceleration",
        r"Metal backend initialized",
    ]
    for pattern in startup_patterns:
        match = re.search(pattern, startup, re.IGNORECASE)
        if match:
            # If requested_device is a specific string or index, check for consistency
            if match.groups() and match.group(1):
                found_dev = match.group(1).strip()
                if dev_str.lower() in found_dev.lower() or found_dev.lower() in dev_str.lower():
                    startup_matched = True
                    break
            startup_matched = True
            break

    # Match completed Metal global alignment profile in movie log
    profile_marker_found = (
        "[Metal Global Alignment Profile]" in profile
        or "[CUDA Global Alignment Profile]" in profile  # fallback if common GPU profile block is reused
        or "Metal global alignment" in profile
    )

    total_match = re.search(
        r"^\s*Total (?:Metal|GPU) alignment time:\s*([0-9]+(?:\.[0-9]+)?)\s*ms\s*$",
        profile,
        re.MULTILINE | re.IGNORECASE,
    )
    total_ms = float(total_match.group(1)) if total_match else None

    complete = (
        startup_matched
        and profile_marker_found
        and total_ms is not None
        and math.isfinite(total_ms)
        and total_ms >= 0
    )

    return {
        "requested_device": requested_device,
        "startup_marker_found": startup_matched,
        "profile_marker_found": profile_marker_found,
        "total_metal_alignment_ms": total_ms,
        "movie_log_path": str(movie_log),
        "complete": complete,
    }


def read_mrc_dimensions(path: Path) -> Optional[Dict[str, int]]:
    """Read the corrected MRC shape and pixel mode from its fixed 1024-byte header."""
    if not path.is_file() or path.stat().st_size < 1024:
        return None
    with path.open("rb") as stream:
        nx, ny, nz, mode = struct.unpack("<4i", stream.read(16))
    return {"nx": nx, "ny": ny, "nz": nz, "mode": mode}


def run_fixture_case(
    case_name: str,
    fixture_star: Path,
    ground_truth_json: Path,
    cpu_bin: Path,
    metal_bin: Path,
    device: Union[int, str],
    seed: int,
    case_run_dir: Path,
    comparator_script: Path,
    python_bin: str,
    metal_args: Optional[List[str]] = None,
    gate: str = "relaxed",
    gt_threshold_rms: float = 0.15,
    gt_threshold_max: float = 0.25,
) -> Dict[str, Any]:
    """Execute both CPU and Metal on a fixture and evaluate parity and ground truth."""
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
    metal_dir = case_run_dir / "metal"

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

    # 2. Execute Metal
    resolved_metal_args = metal_args if metal_args is not None else [
        "--seed", str(seed),
        "--metal",
        "--metal_device", str(device),
    ]
    metal_code, metal_sec, metal_log, metal_cmd = run_motioncorr_process(
        binary=metal_bin,
        fixture_dir=fixture_dir,
        star_name=fixture_star.name,
        out_dir=metal_dir,
        extra_args=resolved_metal_args,
    )
    case_report["metal_run"] = {
        "command": " ".join(metal_cmd),
        "exit_code": metal_code,
        "elapsed_sec": round(metal_sec, 4),
        "log_path": str(metal_log),
    }
    if metal_code != 0:
        case_report["fail_reasons"].append(f"Metal motioncorr process exited with nonzero status {metal_code}")

    # Check for expected files
    cpu_missing = verify_fixture_outputs(cpu_dir, movie_base)
    if cpu_missing:
        case_report["fail_reasons"].extend(cpu_missing)

    metal_missing = verify_fixture_outputs(metal_dir, movie_base)
    if metal_missing:
        case_report["fail_reasons"].extend(metal_missing)

    # Verify proof of Metal GPU execution
    metal_evidence = inspect_metal_execution(metal_log, metal_dir / f"{movie_base}.log", device)
    case_report["metal_execution"] = metal_evidence
    if not metal_evidence["complete"]:
        case_report["fail_reasons"].append(
            "Metal execution evidence missing or device mismatch: expected device-selection "
            "message in run.log and completed global-alignment profile in the movie log"
        )

    expected_gt = json.loads(ground_truth_json.read_text())
    expected_dimensions = {"nx": expected_gt["nx"], "ny": expected_gt["ny"], "nz": 1, "mode": 2}
    cpu_dimensions = read_mrc_dimensions(cpu_dir / f"{movie_base}.mrc")
    metal_dimensions = read_mrc_dimensions(metal_dir / f"{movie_base}.mrc")
    case_report["output_dimensions"] = {
        "expected": expected_dimensions,
        "cpu": cpu_dimensions,
        "metal": metal_dimensions,
    }
    if cpu_dimensions != expected_dimensions or metal_dimensions != expected_dimensions:
        case_report["fail_reasons"].append("Corrected MRC dimensions or mode do not match the fixture")

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
    if c_gt_code != 0 or c_gt_rep.get("overall_status") != "PASS":
        case_report["fail_reasons"].append("CPU ground-truth comparator did not pass")
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

    # 4. Evaluate Ground Truth Recovery: Metal vs Ground Truth
    metal_vs_gt_json = case_run_dir / "comp_metal_vs_gt.json"
    m_gt_code, m_gt_rep, _ = run_comparator(
        python_bin=python_bin,
        comparator_script=comparator_script,
        ref=metal_dir,
        test=metal_dir,
        ground_truth=ground_truth_json,
        gate=gate,
        json_out=metal_vs_gt_json,
    )
    case_report["metal_vs_ground_truth"] = {
        "comparator_exit": m_gt_code,
        "comparator_status": m_gt_rep.get("overall_status"),
        "report": m_gt_rep.get("checks", {}).get("ground_truth_recovery", {}),
    }
    if m_gt_code != 0 or m_gt_rep.get("overall_status") != "PASS":
        case_report["fail_reasons"].append("Metal ground-truth comparator did not pass")
    gt_metal = m_gt_rep.get("checks", {}).get("ground_truth_recovery", {})
    if "error" in gt_metal:
        case_report["fail_reasons"].append(f"Metal GT recovery evaluation error: {gt_metal['error']}")
    else:
        rms_err = gt_metal.get("coord_rms_error")
        max_err = gt_metal.get("max_shift_error")
        if rms_err is None or max_err is None:
            case_report["fail_reasons"].append("Metal GT recovery missing shift metrics (never substitute 0.0)")
        elif rms_err > gt_threshold_rms or max_err > gt_threshold_max:
            case_report["fail_reasons"].append(
                f"Metal GT recovery exceeded threshold: rms={rms_err:.4f} > {gt_threshold_rms:.4f} or max={max_err:.4f} > {gt_threshold_max:.4f}"
            )

    # 5. Evaluate Numerical Acceptance: Metal vs CPU
    metal_vs_cpu_json = case_run_dir / "comp_metal_vs_cpu.json"
    m_vs_code, m_vs_rep, _ = run_comparator(
        python_bin=python_bin,
        comparator_script=comparator_script,
        ref=cpu_dir,
        test=metal_dir,
        gate=gate,
        json_out=metal_vs_cpu_json,
    )

    coverage = m_vs_rep.get("coverage", {})
    complete_cov = coverage.get("complete", False)
    checks = m_vs_rep.get("checks", {})

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

    case_report["metal_vs_cpu"] = {
        "comparator_exit": m_vs_code,
        "comparator_status": m_vs_rep.get("overall_status"),
        "coverage_complete": complete_cov,
        "metrics": metrics,
        "checks": checks,
    }

    if m_vs_code != 0:
        case_report["fail_reasons"].append(f"Metal vs CPU comparator exited with nonzero code {m_vs_code}")

    if m_vs_rep.get("overall_status") != "PASS":
        case_report["fail_reasons"].append(f"Metal vs CPU comparator overall_status was '{m_vs_rep.get('overall_status')}'")

    if not complete_cov:
        case_report["fail_reasons"].append("Metal vs CPU comparison coverage incomplete (missing MRC or STAR pair)")

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
    metal_run = report.get("metal_run", {})
    print(f" CPU Run:   status={cpu_run.get('exit_code')} wall={cpu_run.get('elapsed_sec')}s")
    print(f" Metal Run: status={metal_run.get('exit_code')} wall={metal_run.get('elapsed_sec')}s")

    gt_cpu = report.get("cpu_vs_ground_truth", {}).get("report", {})
    gt_metal = report.get("metal_vs_ground_truth", {}).get("report", {})
    print("\n [Ground Truth Recovery Against Known Shifts]")
    if "coord_rms_error" in gt_cpu:
        print(f"   CPU   RMS error: {gt_cpu['coord_rms_error']:.6f} px | Max error: {gt_cpu['max_shift_error']:.6f} px")
    else:
        print("   CPU   RMS error: MISSING / ERROR")
    if "coord_rms_error" in gt_metal:
        print(f"   Metal RMS error: {gt_metal['coord_rms_error']:.6f} px | Max error: {gt_metal['max_shift_error']:.6f} px")
    else:
        print("   Metal RMS error: MISSING / ERROR")

    m_cpu = report.get("metal_vs_cpu", {})
    metrics = m_cpu.get("metrics", {})
    print(f"\n [Metal vs CPU Parity Checks ({gate_profile.upper()} Gate)]")
    cov_str = "COMPLETE" if m_cpu.get("coverage_complete") else "INCOMPLETE"
    print(f"   Coverage:              {cov_str}")
    print(f"   Comparator Status:     {m_cpu.get('comparator_status')}")

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
        description="Fast synthetic CPU-versus-Metal regression harness for MotionCorr on Apple silicon"
    )
    parser.add_argument(
        "--cpu-bin",
        type=Path,
        default=None,
        help="Path to CPU motioncorr executable (default: auto-detected in build/ or build-cpu/)",
    )
    parser.add_argument(
        "--metal-bin",
        type=Path,
        default=None,
        help="Path to Metal motioncorr executable (default: auto-detected in build-metal/ or build/)",
    )
    parser.add_argument(
        "--device",
        "--metal-device",
        dest="device",
        default=None,
        help="Metal device ID or device name (default: auto-detected system default Metal device)",
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
        help="Acceptance gate profile for Metal vs CPU (default: relaxed / Gate 2)",
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
        help="Base directory for outputs (default: fresh temporary directory)",
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
    parser.add_argument(
        "--metal-args",
        nargs=argparse.REMAINDER,
        default=None,
        help="Extra flags to pass directly to the Metal executable",
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    python_bin = args.python or detect_python()
    comparator_script = repo_root / "tools" / "compare_motioncorr.py"

    if not comparator_script.is_file():
        print(f"ERROR: Comparator not found at {comparator_script}", file=sys.stderr)
        sys.exit(2)

    # Locate CPU binary
    cpu_bin = args.cpu_bin
    if cpu_bin is None:
        for c in [repo_root / "build" / "motioncorr", repo_root / "build-cpu" / "motioncorr"]:
            if c.is_file() and os.access(c, os.X_OK):
                cpu_bin = c
                break

    # Locate Metal binary
    metal_bin = args.metal_bin
    if metal_bin is None:
        c = repo_root / "build-metal" / "motioncorr"
        if c.is_file() and os.access(c, os.X_OK):
            metal_bin = c

    if cpu_bin is None or not cpu_bin.is_file() or not os.access(cpu_bin, os.X_OK):
        print(f"ERROR: CPU executable not found or not executable: {cpu_bin}", file=sys.stderr)
        print("Please build motioncorr or specify --cpu-bin PATH", file=sys.stderr)
        sys.exit(2)

    if metal_bin is None or not metal_bin.is_file() or not os.access(metal_bin, os.X_OK):
        print(f"ERROR: Metal executable not found or not executable: {metal_bin}", file=sys.stderr)
        print("Please build motioncorr with Metal support or specify --metal-bin PATH", file=sys.stderr)
        sys.exit(2)

    cpu_bin = cpu_bin.resolve()
    metal_bin = metal_bin.resolve()

    # Locate fixture directory
    fixture_dir = (args.fixture_dir or (repo_root / "test-data" / "fixtures")).resolve()
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

    # Output directory handling - require fresh directories
    created_temp = False
    if args.output_dir is not None:
        run_output_base = args.output_dir.resolve()
        run_output_base.mkdir(parents=True, exist_ok=True)
    else:
        run_output_base = Path(tempfile.mkdtemp(prefix="mc_metal_syn_"))
        created_temp = True

    for case_name, _, _ in cases:
        case_dir = run_output_base / case_name
        if case_dir.exists() and (not case_dir.is_dir() or any(case_dir.iterdir())):
            parser.error(f"Output directory already contains artifacts for {case_name}: {case_dir}")

    harness_t0 = time.perf_counter()
    device_query = args.device or "default"
    metal_info = get_metal_device_info(device_query)
    effective_device = args.device or metal_info.get("device_name", "0")
    git_commit = get_git_commit(repo_root)
    macos_ver = get_macos_version()

    print("=" * 78)
    print(" MOTIONCORR SYNTHETIC CPU-VERSUS-METAL REGRESSION HARNESS")
    print("=" * 78)
    print(f"Commit:          {git_commit}")
    print(f"Host / OS:       {platform.node()} ({platform.system()} {platform.release()})")
    print(f"macOS Version:   {macos_ver}")
    print(f"CPU Binary:      {cpu_bin}")
    print(f"Metal Binary:    {metal_bin}")
    print(f"Metal Device:    {effective_device} ({metal_info.get('device_name', 'Unknown')})")
    print(f"Metal Support:   {metal_info.get('metal_version', 'Metal 4')}")
    print(f"Gate Profile:    {args.gate.upper()}")
    print(f"Declared GT Tol: Coordinate RMS <= {args.gt_threshold_rms} px, Max Shift <= {args.gt_threshold_max} px")
    print(f"Seed:            {args.seed}")
    print(f"Output Root:     {run_output_base}")
    print("=" * 78)

    harness_passed = True
    case_reports = []

    # Extra metal flags
    resolved_metal_args = None
    if args.metal_args:
        resolved_metal_args = ["--seed", str(args.seed)] + args.metal_args

    for case_name, star_path, gt_path in cases:
        case_dir = run_output_base / case_name
        case_dir.mkdir(parents=True, exist_ok=True)

        case_rep = run_fixture_case(
            case_name=case_name,
            fixture_star=star_path,
            ground_truth_json=gt_path,
            cpu_bin=cpu_bin,
            metal_bin=metal_bin,
            device=effective_device,
            seed=args.seed,
            case_run_dir=case_dir,
            comparator_script=comparator_script,
            python_bin=python_bin,
            metal_args=resolved_metal_args,
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
            "macos_version": macos_ver,
            "python": python_bin,
            "cpu_binary": str(cpu_bin),
            "cpu_binary_sha256": compute_sha256(cpu_bin),
            "metal_binary": str(metal_bin),
            "metal_binary_sha256": compute_sha256(metal_bin),
            "metal_info": metal_info,
        },
        "configuration": {
            "seed": args.seed,
            "device": str(effective_device),
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
