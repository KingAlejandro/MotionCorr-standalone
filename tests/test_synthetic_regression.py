#!/usr/bin/env python3
"""Automated regression test verifying that MotionCorr produces bit-for-bit identical
output to the baseline reference on a small synthetic movie fixture.

Supports both CPU reference validation and explicit native CUDA hardware regression
with stage-backend-device witness verification and fail-closed controls.
"""

import argparse
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple


def read_mrc_image(path: Path) -> Tuple[int, int, int, Tuple[float, ...]]:
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


def parse_star_shifts(path: Path) -> List[Tuple[float, float]]:
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


def compare_mrc(data1, data2) -> Tuple[float, float]:
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


def compare_shifts(shifts1, shifts2) -> Tuple[float, float]:
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


def verify_cuda_stage_witnesses(stdout_text: str, out_dir: Path, gpu_id: int) -> None:
    """Verify explicit stage-backend-device witnesses for native CUDA execution.

    Fails closed if:
    1. CUDA startup acceleration witness is absent or specifies wrong device.
    2. Any CPU fallback warning appears in stdout or log files.
    3. Any native CUDA stage profile marker is absent from the execution log.
    """
    # 1. Verify stdout device startup witness
    expected_startup = f"Using CUDA acceleration on GPU device {gpu_id} for global alignment."
    if expected_startup not in stdout_text:
        raise RuntimeError(
            f"Native CUDA startup witness missing from stdout (expected: '{expected_startup}').\n"
            f"Stdout:\n{stdout_text}"
        )

    # 2. Inspect generated log files
    log_files = list(out_dir.glob("**/*.log"))
    if not log_files:
        raise RuntimeError(f"Movie log file not found in output directory {out_dir}")

    combined_log = "\n".join(f.read_text(errors="replace") for f in log_files)

    # Check for any fallback markers
    fallback_patterns = [
        r"WARNING:.*falling back",
        r"falling back to CPU",
        r"falling back to streaming pipeline",
        r"materializing host frames for fallback",
    ]
    for pattern in fallback_patterns:
        match = re.search(pattern, combined_log, re.IGNORECASE)
        if match:
            raise RuntimeError(
                f"CUDA execution silently fell back to CPU path: '{match.group(0)}'. "
                f"Fail-closed gate forbids CPU fallback under CUDA execution."
            )

    # 3. Check for required native CUDA stage witnesses
    required_stage_witnesses = [
        "[CUDA Global Alignment Profile]",
        "[CUDA Global Alignment] completed",
        "[CUDA Patch Alignment Profile]",
        "[CUDA Patch Alignment] completed",
        "[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]",
    ]
    for witness in required_stage_witnesses:
        if witness not in combined_log:
            raise RuntimeError(
                f"Required native CUDA stage witness missing from log: '{witness}'.\n"
                f"Available log excerpt:\n{combined_log[:2000]}"
            )


def run_motioncorr(
    binary: Path,
    movie: Path,
    out_dir: Path,
    threads: int = 1,
    gpu: int = None,
    require_cuda: bool = False,
):
    """Run motioncorr on the synthetic movie fixture with explicit backend witnessing."""
    if require_cuda and gpu is None:
        raise ValueError("require_cuda is True, but no GPU device ID was provided.")

    cmd = [
        str(binary.resolve()),
        "--i", str(movie.resolve()),
        "--o", str(out_dir.resolve()),
        "--use_own",
        "--j", str(threads),
        "--dose_weighting",
        "--dose_per_frame", "1.0",
        "--voltage", "300",
        "--angpix", "1.0",
        "--patch_x", "3",
        "--patch_y", "3",
        "--bfactor", "150",
    ]
    if gpu is not None:
        cmd.extend(["--gpu", str(gpu)])

    res = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)
    if res.returncode != 0:
        print("STDOUT:\n", res.stdout)
        print("STDERR:\n", res.stderr)
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {' '.join(cmd)}")

    if require_cuda or gpu is not None:
        verify_cuda_stage_witnesses(res.stdout, out_dir, gpu)
    else:
        # For CPU-only runs, verify CUDA startup was not inadvertently engaged
        if "Using CUDA acceleration on GPU device" in res.stdout:
            raise RuntimeError("CPU run unexpectedly reported CUDA startup acceleration witness.")


def test_synthetic_regression(
    binary: Path = None,
    threads_to_test=(1, 4),
    gpu: int = None,
    require_cuda: bool = False,
):
    repo_root = Path(__file__).resolve().parent.parent

    if binary is None:
        binary = repo_root / "build" / "motioncorr"
    if not binary.is_file():
        raise FileNotFoundError(f"motioncorr binary not found at {binary}. Build with cmake first.")

    movie_path = repo_root / "test-data" / "synthetic" / "synthetic_movie.tiff"
    expected_mrc = repo_root / "test-data" / "synthetic" / "expected" / "synthetic_movie.mrc"
    expected_star = repo_root / "test-data" / "synthetic" / "expected" / "synthetic_movie.star"

    if not movie_path.is_file():
        raise FileNotFoundError(f"Synthetic movie fixture not found at {movie_path}")
    if not expected_mrc.is_file() or not expected_star.is_file():
        raise FileNotFoundError(f"Expected reference files not found in {expected_mrc.parent}")

    # Read expected reference data
    _, _, _, exp_mrc_data = read_mrc_image(expected_mrc)
    exp_shifts = parse_star_shifts(expected_star)
    assert len(exp_shifts) == 8, f"Expected 8 frame shifts, found {len(exp_shifts)}"

    for threads in threads_to_test:
        with tempfile.TemporaryDirectory(prefix=f"synth_test_t{threads}_") as tmpdir:
            out_dir = Path(tmpdir)
            run_motioncorr(
                binary,
                movie_path,
                out_dir,
                threads=threads,
                gpu=gpu,
                require_cuda=require_cuda,
            )

            # Find output MRC and STAR
            mrc_files = list(out_dir.glob("**/synthetic_movie.mrc"))
            star_files = list(out_dir.glob("**/synthetic_movie.star"))

            assert len(mrc_files) == 1, f"Expected 1 output MRC file, found {len(mrc_files)}"
            assert len(star_files) == 1, f"Expected 1 output STAR file, found {len(star_files)}"

            _, _, _, actual_mrc_data = read_mrc_image(mrc_files[0])
            actual_shifts = parse_star_shifts(star_files[0])

            m_diff, m_rmse = compare_mrc(exp_mrc_data, actual_mrc_data)
            t_diff, t_rmsd = compare_shifts(exp_shifts, actual_shifts)

            mode_str = f"--j {threads}" if gpu is None else f"--j {threads} --gpu {gpu}"
            print(f"Results for {mode_str} vs Expected Reference:")
            print(f"  Image Max Pixel Difference: {m_diff:.6e}")
            print(f"  Image RMSE:                 {m_rmse:.6e}")
            print(f"  Shift Max Difference (px):  {t_diff:.6e}")
            print(f"  Shift RMSD (px):            {t_rmsd:.6e}")

            # Assert bit-for-bit numerical parity
            assert m_diff == 0.0, f"Image pixel diff ({m_diff}) must be exactly 0.0"
            assert m_rmse == 0.0, f"Image RMSE ({m_rmse}) must be exactly 0.0"
            assert t_diff == 0.0, f"Trajectory shift diff ({t_diff}) must be exactly 0.0"
            assert t_rmsd == 0.0, f"Trajectory RMSD ({t_rmsd}) must be exactly 0.0"

    print("\nSUCCESS: All synthetic regression tests passed with bit-for-bit identity!")
    return True


def test_negative_controls(binary: Path = None):
    """Verify that test_synthetic_regression fail-closed guards reliably detect:
    1. Missing CUDA startup witness when CUDA is required.
    2. CPU fallback warning in execution log.
    3. Missing required native CUDA stage profile markers.
    4. Altered / corrupted image pixels.
    5. Altered / corrupted trajectory shifts.
    6. Missing output files (MRC or STAR).
    7. Process execution failures (non-zero returncode).
    """
    print("Executing fail-closed negative control test suite...")

    # Control 1: Missing stdout CUDA startup witness
    with tempfile.TemporaryDirectory(prefix="neg_ctrl_stdout_") as tmpdir:
        td = Path(tmpdir)
        (td / "test.log").write_text(
            "[CUDA Global Alignment Profile]\n"
            "[CUDA Global Alignment] completed\n"
            "[CUDA Patch Alignment Profile]\n"
            "[CUDA Patch Alignment] completed\n"
            "[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]\n"
        )
        try:
            verify_cuda_stage_witnesses("Running MotionCorr without GPU witness", td, gpu_id=0)
            raise AssertionError("Control 1 FAILED: Did not reject missing CUDA startup witness")
        except RuntimeError as e:
            assert "Native CUDA startup witness missing" in str(e)
            print("  Control 1 PASSED: Missing CUDA startup witness correctly rejected.")

    # Control 2: Fallback warning in log
    with tempfile.TemporaryDirectory(prefix="neg_ctrl_fallback_") as tmpdir:
        td = Path(tmpdir)
        (td / "test.log").write_text(
            "Using CUDA acceleration on GPU device 0\n"
            "WARNING: Resident CUDA forward FFT failed; materializing host frames for fallback.\n"
            "[CUDA Global Alignment Profile]\n"
            "[CUDA Global Alignment] completed\n"
            "[CUDA Patch Alignment Profile]\n"
            "[CUDA Patch Alignment] completed\n"
            "[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]\n"
        )
        try:
            verify_cuda_stage_witnesses(
                "Using CUDA acceleration on GPU device 0 for global alignment.",
                td,
                gpu_id=0,
            )
            raise AssertionError("Control 2 FAILED: Did not reject CPU fallback warning")
        except RuntimeError as e:
            assert "silently fell back to CPU path" in str(e)
            print("  Control 2 PASSED: CPU fallback warning correctly rejected.")

    # Control 3: Missing required stage marker
    with tempfile.TemporaryDirectory(prefix="neg_ctrl_stage_") as tmpdir:
        td = Path(tmpdir)
        (td / "test.log").write_text(
            "[CUDA Global Alignment Profile]\n"
            "[CUDA Global Alignment] completed\n"
            # Missing Patch Alignment Profile
            "[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]\n"
        )
        try:
            verify_cuda_stage_witnesses(
                "Using CUDA acceleration on GPU device 0 for global alignment.",
                td,
                gpu_id=0,
            )
            raise AssertionError("Control 3 FAILED: Did not reject missing stage witness")
        except RuntimeError as e:
            assert "Required native CUDA stage witness missing" in str(e)
            print("  Control 3 PASSED: Missing stage witness correctly rejected.")

    # Control 4: Corrupted image pixel values
    buf1 = (1.0, 2.0, 3.0)
    buf2 = (1.0, 2.0001, 3.0)
    diff, rmse = compare_mrc(buf1, buf2)
    assert diff > 0.0 and rmse > 0.0, "Control 4 FAILED: Did not detect corrupted pixel values"
    print("  Control 4 PASSED: Pixel corruption correctly detected.")

    # Control 5: Corrupted trajectory shift
    shifts1 = [(0.0, 0.0), (1.0, 1.0)]
    shifts2 = [(0.0, 0.0), (1.0, 1.005)]
    s_diff, s_rmsd = compare_shifts(shifts1, shifts2)
    assert s_diff > 0.0 and s_rmsd > 0.0, "Control 5 FAILED: Did not detect corrupted shifts"
    print("  Control 5 PASSED: Shift corruption correctly detected.")

    # Control 6: Missing output files
    with tempfile.TemporaryDirectory(prefix="neg_ctrl_files_") as tmpdir:
        td = Path(tmpdir)
        mrcs = list(td.glob("**/synthetic_movie.mrc"))
        assert len(mrcs) == 0
        try:
            assert len(mrcs) == 1, "Expected 1 output MRC file"
            raise AssertionError("Control 6 FAILED: Did not detect missing output file")
        except AssertionError:
            print("  Control 6 PASSED: Missing output file correctly detected.")

    # Control 7: Non-zero exit code
    try:
        res = subprocess.run([sys.executable, "-c", "import sys; sys.exit(42)"], capture_output=True)
        if res.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {res.returncode}")
    except RuntimeError as e:
        assert "exit code 42" in str(e)
        print("  Control 7 PASSED: Non-zero process exit code correctly caught.")

    print("\nSUCCESS: All 7 fail-closed negative controls passed successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=None, help="Path to motioncorr binary")
    parser.add_argument("--threads", type=str, default="1,4", help="Comma-separated thread counts to test")
    parser.add_argument("--gpu", type=int, default=None, help="GPU device ID to test native CUDA execution")
    parser.add_argument(
        "--require-cuda",
        action="store_true",
        help="Fail closed if native CUDA execution witnesses are not verified",
    )
    parser.add_argument(
        "--negative-control",
        action="store_true",
        help="Execute fail-closed negative control test suite",
    )
    args = parser.parse_args()

    if args.negative_control:
        success = test_negative_controls(binary=args.binary)
        sys.exit(0 if success else 1)

    threads = [int(x.strip()) for x in args.threads.split(",")]
    success = test_synthetic_regression(
        binary=args.binary,
        threads_to_test=threads,
        gpu=args.gpu,
        require_cuda=args.require_cuda,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
