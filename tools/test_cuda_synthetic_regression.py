#!/usr/bin/env python3
"""Automated verification suite for MotionCorr synthetic regression harness.

Validates the harness acceptance logic through:
1. Positive parity execution
2. Negative test: Missing output file (e.g., deleted MRC or STAR)
3. Negative test: Non-zero MotionCorr process exit (crash / abort)
4. Negative test: Altered image pixels (pixel corruption exceeding tolerance)
5. Negative test: Incomplete comparison coverage (missing STAR / MRC pair)
6. Negative test: Non-existent binary path

Ensures every negative scenario reliably causes the harness to exit non-zero,
report intelligible diagnostic error messages, and preserve failure artifacts.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_SCRIPT = REPO_ROOT / "tools" / "run_cuda_synthetic_regression.py"


def find_cpu_binary() -> Path:
    """Find valid CPU motioncorr executable."""
    for c in [REPO_ROOT / "build" / "motioncorr", REPO_ROOT / "build-cpu" / "motioncorr"]:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise RuntimeError("No executable motioncorr binary found in build/ or build-cpu/")


def create_executable_script(path: Path, content: str) -> None:
    """Write an executable shell script."""
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def create_wrapped_binary(path: Path, cpu_bin: Path, post_hook_sh: str) -> None:
    """Create a wrapper binary that strips --gpu and optionally runs a post-execution hook."""
    content = f"""#!/bin/bash
args=()
skip_next=0
out_dir=""
is_out=0
for a in "$@"; do
    if [ "$skip_next" -eq 1 ]; then
        skip_next=0
        continue
    fi
    if [ "$is_out" -eq 1 ]; then
        out_dir="$a"
        is_out=0
    fi
    if [ "$a" = "--gpu" ]; then
        skip_next=1
        continue
    fi
    if [ "$a" = "--o" ]; then
        is_out=1
    fi
    args+=("$a")
done
"{cpu_bin}" "${{args[@]}}"
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


def test_positive(cpu_bin: Path, temp_dir: Path) -> bool:
    """Verify that a normal valid run exits with status 0 and PASS."""
    print("-> Running Test 1: Positive execution test...")
    out_dir = temp_dir / "positive_run"
    json_report = temp_dir / "positive_report.json"
    wrapper = temp_dir / "wrap_positive.sh"
    create_wrapped_binary(wrapper, cpu_bin, "    :")

    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--cuda-bin", str(wrapper),
        "--output-dir", str(out_dir),
        "--json-out", str(json_report),
        "--gate", "exact",
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


def test_negative_missing_output(cpu_bin: Path, temp_dir: Path) -> bool:
    """Verify that missing output file triggers harness failure (non-zero exit)."""
    print("-> Running Test 2: Negative test - Missing output file...")
    wrapper = temp_dir / "wrap_missing_output.sh"
    create_wrapped_binary(wrapper, cpu_bin, '    rm -f "$out_dir"/*.mrc')

    out_dir = temp_dir / "neg_missing_out"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--cuda-bin", str(wrapper),
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
        "--cuda-bin", str(wrapper),
        "--output-dir", str(out_dir),
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite process exit 139!")
        return False
    if "exited with nonzero status 139" not in stdout:
        print(f"FAILED: Expected 'exited with nonzero status 139' in stdout:\n{stdout}")
        return False
    print("   PASSED: Process crash correctly triggered non-zero exit and diagnostic error.")
    return True


def test_negative_altered_pixels(cpu_bin: Path, temp_dir: Path) -> bool:
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
    create_wrapped_binary(wrapper, cpu_bin, corrupt_cmd)

    out_dir = temp_dir / "neg_corrupt_pixels"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--cuda-bin", str(wrapper),
        "--output-dir", str(out_dir),
        "--gate", "relaxed",
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite corrupted pixel data!")
        return False
    if "Check 'corrected_image' failed" not in stdout and "OVERALL HARNESS RESULT: FAIL" not in stdout:
        print(f"FAILED: Expected corrected_image failure in stdout:\n{stdout}")
        return False
    print("   PASSED: Altered pixels correctly failed numerical acceptance gate.")
    return True


def test_negative_incomplete_coverage(cpu_bin: Path, temp_dir: Path) -> bool:
    """Verify that incomplete comparison coverage causes non-zero exit."""
    print("-> Running Test 5: Negative test - Incomplete comparison coverage...")
    wrapper = temp_dir / "wrap_delete_star.sh"
    create_wrapped_binary(wrapper, cpu_bin, '    rm -f "$out_dir"/synthetic_*.star')

    out_dir = temp_dir / "neg_incomplete_cov"
    code, stdout, stderr = run_harness([
        "--cpu-bin", str(cpu_bin),
        "--cuda-bin", str(wrapper),
        "--output-dir", str(out_dir),
    ])
    if code == 0:
        print("FAILED: Harness exited 0 despite incomplete coverage!")
        return False
    if "Missing expected output file" not in stdout and "incomplete" not in stdout:
        print(f"FAILED: Expected incomplete coverage or missing output error:\n{stdout}")
        return False
    print("   PASSED: Incomplete comparison coverage correctly triggered non-zero exit.")
    return True


def test_negative_missing_binary() -> bool:
    """Verify that specifying a non-existent binary causes immediate error exit code 2."""
    print("-> Running Test 6: Negative test - Non-existent binary path...")
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
    cpu_bin = find_cpu_binary()
    print("=" * 78)
    print(" MOTIONCORR SYNTHETIC HARNESS ACCEPTANCE AND NEGATIVE TEST SUITE")
    print("=" * 78)
    print(f"Target Harness: {HARNESS_SCRIPT}")
    print(f"Target Binary:  {cpu_bin}")
    print("=" * 78)

    temp_dir = Path(tempfile.mkdtemp(prefix="mc_harness_test_"))
    tests = [
        test_positive,
        test_negative_missing_output,
        test_negative_process_crash,
        test_negative_altered_pixels,
        test_negative_incomplete_coverage,
    ]

    all_passed = True
    try:
        for t in tests:
            if not t(cpu_bin, temp_dir):
                all_passed = False
                print(f"FAILED: {t.__name__}")
                break
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
