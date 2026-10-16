#!/usr/bin/env python3
"""Standalone controls for the optional JAX global alignment prototype."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from global_align import align_stack, read_mrc_stack, write_mrc_image


ROOT = Path(__file__).resolve().parents[2]


def read_reference_global_shifts(path: Path) -> np.ndarray:
    in_global = False
    in_loop = False
    labels: list[str] = []
    shifts: list[tuple[float, float]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("data_global_shift"):
            in_global = True
            continue
        if in_global and line.startswith("data_"):
            break
        if not in_global or not line or line.startswith("#"):
            continue
        if line == "loop_":
            in_loop = True
            continue
        if not in_loop:
            continue
        if line.startswith("_rln"):
            labels.append(line.split()[0])
            continue
        row = line.split()
        if len(row) < len(labels):
            continue
        ix = labels.index("_rlnMicrographShiftX")
        iy = labels.index("_rlnMicrographShiftY")
        shifts.append((float(row[ix]), float(row[iy])))
    if not shifts:
        raise AssertionError(f"no global shifts found in {path}")
    return np.asarray(shifts, dtype=np.float64)


def check_reference_fixture() -> None:
    input_path = ROOT / "test-data/fixtures/synthetic_128x128_8frames.mrcs"
    reference_path = ROOT / "test-data/fixtures/reference_output/synthetic_128x128_8frames.star"
    stack, header = read_mrc_stack(input_path)
    assert header["nx"] == 128 and header["ny"] == 128 and header["nframes"] == 8
    shifts, corrected_sum, diag = align_stack(stack, scaled_b=150.0)
    reference = read_reference_global_shifts(reference_path)
    error = shifts - reference
    max_error = float(np.max(np.abs(error)))
    coord_rms = float(np.sqrt(np.mean(np.sum(error**2, axis=1))))
    print(f"reference STAR: max shift error={max_error:.6f}px coordinate RMS={coord_rms:.6f}px")
    print(f"reference run: iterations={diag['iterations']} final RMSD={diag['last_iteration_rmsd_px']:.6g}px")
    # Use the existing, provisional Issue #4/Reference Gate 2 limits verbatim;
    # they are not newly fitted to JAX and do not imply scientific equivalence.
    assert max_error <= 0.05, f"max shift error {max_error:.6g}px exceeds 0.05px"
    assert coord_rms <= 0.02, f"2D RMS shift error {coord_rms:.6g}px exceeds 0.02px"

    reference_image_stack, _ = read_mrc_stack(
        ROOT / "test-data/fixtures/reference_output/synthetic_128x128_8frames.mrc"
    )
    reference_image = reference_image_stack[0].astype(np.float64)
    image_error = corrected_sum.astype(np.float64) - reference_image
    absolute_rmse = float(np.sqrt(np.mean(image_error**2)))
    relative_rmse = absolute_rmse / max(float(reference_image.std()), 1e-12)
    max_pixel_error = float(np.max(np.abs(image_error)))
    print(
        "corrected global-only sum: "
        f"absolute RMSE={absolute_rmse:.6g}, relative RMSE={relative_rmse:.6g}, "
        f"max pixel error={max_pixel_error:.6g}"
    )
    # Existing reference-gate thresholds are reported on this synthetic fixture;
    # they are not adjusted for the prototype.
    assert absolute_rmse <= 0.020, f"absolute image RMSE {absolute_rmse:.6g} exceeds 0.020"
    assert relative_rmse <= 0.001, f"relative image RMSE {relative_rmse:.6g} exceeds 0.001"
    assert max_pixel_error <= 5.0, f"max pixel error {max_pixel_error:.6g} exceeds 5.0"
    with tempfile.TemporaryDirectory(prefix="mc-jax-mrc-output-") as temporary:
        corrected_path = Path(temporary) / "global_sum.mrc"
        write_mrc_image(
            corrected_path,
            corrected_sum,
            header["sampling_x_angstrom"],
            header["sampling_y_angstrom"],
        )
        round_trip, _ = read_mrc_stack(corrected_path)
        assert np.array_equal(round_trip[0], corrected_sum), "corrected MRC writer changed pixel values"


def check_cli_writes_reference_shifts() -> None:
    input_path = ROOT / "test-data/fixtures/synthetic_128x128_8frames.mrcs"
    reference_path = ROOT / "test-data/fixtures/reference_output/synthetic_128x128_8frames.star"
    reference = read_reference_global_shifts(reference_path)
    with tempfile.TemporaryDirectory(prefix="mc-jax-cli-") as temporary:
        output_path = Path(temporary) / "shifts.csv"
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("global_align.py")),
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--bfactor",
                "150",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with output_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        shifts = np.asarray(
            [(float(row["shift_x_px"]), float(row["shift_y_px"])) for row in rows],
            dtype=np.float64,
        )
        error = shifts - reference
        max_error = float(np.max(np.abs(error)))
        coord_rms = float(np.sqrt(np.mean(np.sum(error**2, axis=1))))
        assert shifts.shape == (8, 2), f"CLI wrote wrong shift shape: {shifts.shape}"
        assert [int(row["frame_number"]) for row in rows] == list(range(1, 9))
        assert max_error <= 0.05, f"CLI max shift error {max_error:.6g}px exceeds 0.05px"
        assert coord_rms <= 0.02, f"CLI coordinate RMS {coord_rms:.6g}px exceeds 0.02px"
        report = json.loads(output_path.with_suffix(".csv.json").read_text(encoding="utf-8"))
        assert report["input_sha256"] and report["backend"] and report["device"]
        print(f"CLI reference fixture: max shift error={max_error:.6f}px coordinate RMS={coord_rms:.6f}px")


def check_asymmetric_non_square_integer_motion() -> None:
    ny, nx = 64, 96
    y, x = np.mgrid[:ny, :nx]
    # Asymmetric, non-periodic-looking texture catches x/y swaps and sign errors.
    reference = (
        np.exp(-((x - 19.0) ** 2 / 30.0 + (y - 13.0) ** 2 / 12.0))
        + 0.7 * np.exp(-((x - 67.0) ** 2 / 80.0 + (y - 41.0) ** 2 / 20.0))
        + 0.2 * np.sin(2 * np.pi * x / 17.0) * np.cos(2 * np.pi * y / 11.0)
    ).astype(np.float32)
    applied_xy = [(0, 0), (3, 0), (0, 4), (3, 4), (6, 0), (0, 8), (6, 4), (9, 8)]
    stack = np.stack([np.roll(reference, (dy, dx), axis=(0, 1)) for dx, dy in applied_xy])
    shifts, _, diag = align_stack(stack, scaled_b=0.0)
    expected = np.asarray([(-dx, -dy) for dx, dy in applied_xy], dtype=np.float64)
    error = shifts - expected
    assert np.array_equal(shifts[0], np.zeros(2)), f"frame-one origin is not zero: {shifts[0]}"
    assert float(np.max(np.abs(error))) <= 0.05, f"integer control max error too large: {error}"
    coord_rms = float(np.sqrt(np.mean(np.sum(error**2, axis=1))))
    assert coord_rms <= 0.02, f"integer control coordinate RMS too large: {coord_rms}"
    assert diag["converged"], "integer control did not meet the C++ convergence criterion"
    print(f"non-square integer control: max error={np.max(np.abs(error)):.6g}px, 2D RMS={coord_rms:.6g}px")


def check_constant_stack_fails_stably() -> None:
    stack = np.ones((3, 64, 96), dtype=np.float32)
    shifts, _, _ = align_stack(stack, scaled_b=0.0)
    assert np.array_equal(shifts, np.zeros_like(shifts)), f"constant stack produced shifts: {shifts}"
    print("constant-stack control: all shifts zero")


def check_subpixel_fixture_ground_truth() -> None:
    input_path = ROOT / "test-data/fixtures/synthetic_128x128_8frames_subpixel.mrcs"
    truth_path = ROOT / "test-data/fixtures/synthetic_128x128_8frames_subpixel_ground_truth.json"
    stack, _ = read_mrc_stack(input_path)
    truth = np.asarray(json.loads(truth_path.read_text())["expected_alignment_shifts_xy"], dtype=np.float64)
    shifts, _, diag = align_stack(stack, scaled_b=150.0)
    error = shifts - truth
    max_error = float(np.max(np.abs(error)))
    coord_rms = float(np.sqrt(np.mean(error**2)))
    print(f"subpixel truth diagnostic (no separate threshold): max={max_error:.6f}px, per-coordinate RMS={coord_rms:.6f}px")
    print(f"subpixel run: iterations={diag['iterations']} final RMSD={diag['last_iteration_rmsd_px']:.6g}px")
    # This known-motion diagnostic is separate from the C++ reference parity gate.
    assert shifts.shape == truth.shape and np.isfinite(shifts).all()
    assert np.array_equal(shifts[0], np.zeros(2)), "frame-one origin is not zero"


def main() -> None:
    check_reference_fixture()
    check_cli_writes_reference_shifts()
    check_asymmetric_non_square_integer_motion()
    check_constant_stack_fails_stably()
    check_subpixel_fixture_ground_truth()
    print("Issue #14 CPU reference-parity and structural controls passed; subpixel truth diagnostic recorded")


if __name__ == "__main__":
    main()
