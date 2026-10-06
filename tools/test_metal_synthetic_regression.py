#!/usr/bin/env python3
"""Automated verification suite for MotionCorr synthetic Metal regression harness.

Validates the harness acceptance and failure logic on Apple silicon through:
1. Positive parity execution (using real Metal binary or verified surrogate)
2. Negative test: Missing output file (e.g., deleted MRC or STAR)
3. Negative test: Non-zero MotionCorr process exit (crash / abort / exit 139)
4. Negative test: Altered image pixels (pixel corruption exceeding Gate 2 tolerance)
5. Negative test: Incomplete comparison coverage (missing STAR / MRC pair)
6. Negative test: CPU wrapper masquerading as Metal (strips Metal markers)
7. Negative test: Stale / reused output directory (rejects non-empty directory before execution)
8. Negative test: Non-existent binary path (fails immediately with exit 2)

Ensures every negative scenario reliably causes the harness to exit non-zero,
report intelligible diagnostic error messages, and preserve failure artifacts.
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_SCRIPT = REPO_ROOT / "tools" / "run_metal_synthetic_regression.py"


def find_cpu_binary() -> Path:
    """Find valid CPU motioncorr executable."""
    for c in [REPO_ROOT / "build" / "motioncorr", REPO_ROOT / "build-cpu" / "motioncorr"]:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise RuntimeError("No executable motioncorr binary found in build/ or build-cpu/")


def find_metal_binary() -> Optional[Path]:
    """Find Metal motioncorr executable if built."""
    candidate = REPO_ROOT / "build-metal" / "motioncorr"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def create_executable_script(path: Path, content: str) -> None:
    """Write an executable shell script."""
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def create_mock_metal_binary(path: Path, cpu_bin: Path, device_name: str = "Apple M4 Pro", post_hook_sh: str = ":") -> None:
    """Create a verified surrogate Metal binary that runs the CPU binary and emits valid Metal execution evidence.

    Used for testing the harness machinery before Issue #32 provides a runnable Metal kernel.
    """
    content = f"""#!/bin/bash
out_dir=""
expect_out=0
star_in=""
expect_in=0
for arg in "$@"; do
    if [ "$expect_out" -eq 1 ]; then
        out_dir="$arg"
        expect_out=0
    elif [ "$arg" = "--o" ]; then
        expect_out=1
    fi
    if [ "$expect_in" -eq 1 ]; then
        star_in="$arg"
        expect_in=0
    elif [ "$arg" = "--i" ]; then
        expect_in=1
    fi
done

# Strip metal-specific arguments before passing to CPU binary
clean_args=()
skip=0
for a in "$@"; do
    if [ "$skip" -eq 1 ]; then
        skip=0
        continue
    fi
    if [ "$a" = "--metal_device" ]; then
        skip=1
        continue
    fi
    if [ "$a" = "--metal" ]; then
        continue
    fi
    clean_args+=("$a")
done

echo "Using Metal acceleration on device [{device_name}] for global alignment."
"{cpu_bin}" "${{clean_args[@]}}"
ret=$?

if [ "$ret" -eq 0 ] && [ -n "$out_dir" ] && [ -d "$out_dir" ]; then
    movie_base="$(basename "${{star_in%.*}}")"
    movie_log="${{out_dir}}/${{movie_base}}.log"
    if [ -f "$movie_log" ]; then
        cat << 'EOF_PROFILE' >> "$movie_log"

[Metal Global Alignment Profile]
  Metal device: {device_name}
  Total Metal alignment time: 1.845 ms
EOF_PROFILE
    fi
{post_hook_sh}
fi
exit $ret
"""
    create_executable_script(path, content)


def create_wrapped_binary(path: Path, base_bin: Path, post_hook_sh: str) -> None:
    """Create a wrapper binary that strips Metal flags and optionally runs a post-execution hook."""
    content = f"""#!/bin/bash
out_dir=""
expect_out=0
args=()
skip_next=0
for a in "$@"; do
    if [ "$skip_next" -eq 1 ]; then
        skip_next=0
        continue
    fi
    if [ "$expect_out" -eq 1 ]; then
        out_dir="$a"
        expect_out=0
    fi
    if [ "$a" = "--metal_device" ]; then
        skip_next=1
        continue
    fi
    if [ "$a" = "--metal" ]; then
        continue
    fi
    if [ "$a" = "--o" ]; then
        expect_out=1
    fi
    args+=("$a")
done
"{base_bin}" "${{args[@]}}"
ret=$?
if [ -n "$out_dir" ] && [ -d "$out_dir" ]; then
{post_hook_sh}
fi
exit $ret
"""
    create_executable_script(path, content)


def run_harness(args: List[str]) -> Tuple[int, str, str]:
    """Execute the harness script with given arguments."""
    cmd = [sys.executable, str(HARNESS_SCRIPT)] + args
    res = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return res.returncode, res.stdout, res.stderr


def test_positive(cpu_bin: Path, metal_bin: Path, device: str, temp_dir: Path) -> bool:
    """Verify that a valid execution exits with status 0 and PASS."""
    print("-> Running Test 1: Positive execution test...")
    out_dir = temp_dir / "positive_run"
    json_report = temp_dir / "positive_report.json"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(metal_bin),
        "--device", str(device),
        "--output-dir", str(out_dir),
        "--json-out", str(json_report),
        "--gate", "relaxed",
    ])
    if code != 0:
        print(f"FAILED: Expected exit code 0, got {code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
        return False
    if "OVERALL HARNESS RESULT: PASS" not in stdout:
        print(f"FAILED: Expected 'OVERALL HARNESS RESULT: PASS' in output\nStdout:\n{stdout}")
        return False
    if not json_report.is_file():
        print(f"FAILED: Expected JSON report file {json_report}")
        return False
    print("   PASSED: Positive run exited 0 with OVERALL HARNESS RESULT: PASS")
    return True


def test_negative_missing_output(cpu_bin: Path, metal_bin: Path, device: str, temp_dir: Path) -> bool:
    """Verify that a missing output file triggers harness failure (non-zero exit)."""
    print("-> Running Test 2: Negative test - Missing output file...")
    wrapper = temp_dir / "wrap_missing_output.sh"
    create_mock_metal_binary(wrapper, cpu_bin, device, post_hook_sh='    rm -f "$out_dir"/*.mrc')

    out_dir = temp_dir / "neg_missing_out"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(wrapper),
        "--device", str(device),
        "--output-dir", str(out_dir),
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite missing output file!")
        return False
    if "Missing expected output file" not in stdout:
        print(f"FAILED: Did not find 'Missing expected output file' in output:\n{stdout}")
        return False
    if f"Artifacts preserved at: {out_dir.resolve()}" not in stdout and f"Artifacts preserved at: {out_dir}" not in stdout:
        print(f"FAILED: Expected artifacts preservation message:\n{stdout}")
        return False
    print("   PASSED: Missing output correctly triggered non-zero exit and artifact retention.")
    return True


def test_negative_process_crash(cpu_bin: Path, temp_dir: Path) -> bool:
    """Verify that a failing/crashing MotionCorr process triggers harness failure."""
    print("-> Running Test 3: Negative test - MotionCorr process crash/exit 139...")
    wrapper = temp_dir / "wrap_crash.sh"
    create_executable_script(
        wrapper,
        """#!/bin/sh
echo "Simulated segmentation fault / error" >&2
exit 139
""",
    )
    out_dir = temp_dir / "neg_crash_out"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(wrapper),
        "--output-dir", str(out_dir),
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite process exit 139!")
        return False
    if "exited with nonzero status 139" not in stdout:
        print(f"FAILED: Expected 'exited with nonzero status 139' in stdout:\n{stdout}")
        return False
    if f"Artifacts preserved at: {out_dir.resolve()}" not in stdout and f"Artifacts preserved at: {out_dir}" not in stdout:
        print(f"FAILED: Expected artifacts preservation message:\n{stdout}")
        return False
    print("   PASSED: Process crash correctly triggered non-zero exit and diagnostic error.")
    return True


def test_negative_altered_pixels(cpu_bin: Path, metal_bin: Path, device: str, temp_dir: Path) -> bool:
    """Verify that altered/corrupted pixels fail the image RMSE gate and exit non-zero."""
    print("-> Running Test 4: Negative test - Altered image pixels (corruption)...")
    wrapper = temp_dir / "wrap_corrupt_pixels.sh"
    corrupt_cmd = (
        '    for f in "$out_dir"/*.mrc; do\n'
        '        if [ -f "$f" ]; then\n'
        "            python3 -c \"import sys; path=sys.argv[1]; data=bytearray(open(path, 'rb').read()); data[1050:1100] = b'\\xff' * 50; open(path, 'wb').write(data)\" \"$f\"\n"
        "        fi\n"
        "    done"
    )
    create_mock_metal_binary(wrapper, cpu_bin, device, post_hook_sh=corrupt_cmd)

    out_dir = temp_dir / "neg_corrupt_pixels"
    json_report = temp_dir / "neg_corrupt_pixels.json"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(wrapper),
        "--device", str(device),
        "--output-dir", str(out_dir),
        "--json-out", str(json_report),
        "--gate", "relaxed",
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite corrupted pixel data!")
        return False
    if "Check 'corrected_image' failed" not in stdout:
        print(f"FAILED: Expected corrected_image failure in stdout:\n{stdout}")
        return False
    case = json.loads(json_report.read_text())["cases"][0]
    if not case["metal_execution"]["complete"] or case["metal_vs_cpu"]["checks"]["corrected_image"]["passed"]:
        print(f"FAILED: Pixel test did not isolate image-gate failure: {case['fail_reasons']}")
        return False
    if f"Artifacts preserved at: {out_dir.resolve()}" not in stdout and f"Artifacts preserved at: {out_dir}" not in stdout:
        print(f"FAILED: Expected artifacts preservation message:\n{stdout}")
        return False
    print("   PASSED: Altered pixels correctly failed numerical acceptance gate.")
    return True


def test_negative_incomplete_coverage(cpu_bin: Path, metal_bin: Path, device: str, temp_dir: Path) -> bool:
    """Verify that incomplete comparison coverage causes non-zero exit."""
    print("-> Running Test 5: Negative test - Incomplete comparison coverage...")
    wrapper = temp_dir / "wrap_delete_star.sh"
    create_mock_metal_binary(wrapper, cpu_bin, device, post_hook_sh='    rm -f "$out_dir"/*.star')

    out_dir = temp_dir / "neg_incomplete_cov"
    json_report = temp_dir / "neg_incomplete_cov.json"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(wrapper),
        "--device", str(device),
        "--output-dir", str(out_dir),
        "--json-out", str(json_report),
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite incomplete coverage!")
        return False
    if "Metal vs CPU comparison coverage incomplete" not in stdout:
        print(f"FAILED: Expected comparator coverage failure:\n{stdout}")
        return False
    case = json.loads(json_report.read_text())["cases"][0]
    if not case["metal_execution"]["complete"] or case["metal_vs_cpu"]["coverage_complete"]:
        print(f"FAILED: Coverage test did not isolate incomplete comparison: {case['fail_reasons']}")
        return False
    if f"Artifacts preserved at: {out_dir.resolve()}" not in stdout and f"Artifacts preserved at: {out_dir}" not in stdout:
        print(f"FAILED: Expected artifacts preservation message:\n{stdout}")
        return False
    print("   PASSED: Incomplete comparison coverage correctly triggered non-zero exit.")
    return True


def test_negative_cpu_masquerade(cpu_bin: Path, temp_dir: Path) -> bool:
    """A CPU wrapper that strips Metal flags and lacks Metal evidence must not pass as Metal."""
    print("-> Running Test 6: Negative test - CPU wrapper masquerading as Metal...")
    wrapper = temp_dir / "wrap_cpu_as_metal.sh"
    create_wrapped_binary(wrapper, cpu_bin, "    :")
    out_dir = temp_dir / "neg_cpu_masquerade"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(wrapper),
        "--output-dir", str(out_dir),
    ])
    if code == 0 or "Metal execution evidence missing" not in stdout:
        print(f"FAILED: CPU masquerade was not specifically rejected; exit={code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
        return False
    if f"Artifacts preserved at: {out_dir.resolve()}" not in stdout and f"Artifacts preserved at: {out_dir}" not in stdout:
        print(f"FAILED: Expected artifacts preservation message:\n{stdout}")
        return False
    print("   PASSED: CPU-only execution could not claim Metal parity.")
    return True


def test_negative_reused_output(cpu_bin: Path, metal_bin: Path, temp_dir: Path) -> bool:
    """Existing case artifacts in output directory must be rejected before execution."""
    print("-> Running Test 7: Negative test - Reused output directory...")
    # Pre-populate directory with a dummy file
    reused_dir = temp_dir / "reused_output"
    case_dir = reused_dir / "integer_shift_128x128"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "stale_output.mrc").write_text("stale data")

    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--metal-bin", str(metal_bin),
        "--output-dir", str(reused_dir),
    ])
    if code != 2 or "already contains artifacts" not in stderr:
        print(f"FAILED: Reused artifacts were not rejected with code 2; exit={code}\nStdout:\n{stdout}\nStderr:\n{stderr}")
        return False
    print("   PASSED: Reused output directory rejected before execution with code 2.")
    return True


def test_negative_missing_binary() -> bool:
    """Verify that specifying a non-existent binary causes immediate error exit code 2."""
    print("-> Running Test 8: Negative test - Non-existent binary path...")
    code, stdout, stderr = run_harness([
        "--cpu-bin", "/non/existent/path/to/binary",
    ])
    if code != 2:
        print(f"FAILED: Expected exit code 2 for missing binary, got {code}")
        return False
    if "ERROR: CPU executable not found" not in stderr:
        print(f"FAILED: Expected error message in stderr:\n{stderr}")
        return False
    print("   PASSED: Missing binary correctly rejected with exit code 2.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-bin", type=Path, help="Path to CPU motioncorr executable")
    parser.add_argument("--metal-bin", type=Path, help="Path to Metal motioncorr executable (or surrogate)")
    parser.add_argument("--device", default="Apple M4 Pro", help="Metal device name or ID (default: Apple M4 Pro)")
    args = parser.parse_args()

    cpu_bin = (args.cpu_bin or find_cpu_binary()).resolve()

    temp_dir = Path(tempfile.mkdtemp(prefix="mc_metal_harness_test_"))
    try:
        # Resolve or prepare Metal binary
        if args.metal_bin and args.metal_bin.is_file():
            metal_bin = args.metal_bin.resolve()
        else:
            found = find_metal_binary()
            if found:
                metal_bin = found.resolve()
            else:
                # Use verified surrogate Metal binary for harness framework testing
                metal_bin = temp_dir / "surrogate_metal_runner.sh"
                create_mock_metal_binary(metal_bin, cpu_bin, args.device)

        print("=" * 78)
        print(" MOTIONCORR METAL SYNTHETIC HARNESS ACCEPTANCE AND NEGATIVE TEST SUITE")
        print("=" * 78)
        print(f"Target Harness: {HARNESS_SCRIPT}")
        print(f"CPU Binary:     {cpu_bin}")
        print(f"Metal Binary:   {metal_bin}")
        print(f"Metal Device:   {args.device}")
        print("=" * 78)

        all_passed = True
        if not test_positive(cpu_bin, metal_bin, args.device, temp_dir):
            all_passed = False
        if all_passed and not test_negative_missing_output(cpu_bin, metal_bin, args.device, temp_dir):
            all_passed = False
        if all_passed and not test_negative_process_crash(cpu_bin, temp_dir):
            all_passed = False
        if all_passed and not test_negative_altered_pixels(cpu_bin, metal_bin, args.device, temp_dir):
            all_passed = False
        if all_passed and not test_negative_incomplete_coverage(cpu_bin, metal_bin, args.device, temp_dir):
            all_passed = False
        if all_passed and not test_negative_cpu_masquerade(cpu_bin, temp_dir):
            all_passed = False
        if all_passed and not test_negative_reused_output(cpu_bin, metal_bin, temp_dir):
            all_passed = False
        if all_passed and not test_negative_missing_binary():
            all_passed = False

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 78)
    if all_passed:
        print(" ALL HARNESS VERIFICATION AND NEGATIVE TESTS PASSED SUCCESSFULLY!")
    else:
        print(" HARNESS VERIFICATION FAILED!")
    print("=" * 78)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
