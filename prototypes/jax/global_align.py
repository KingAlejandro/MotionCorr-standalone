#!/usr/bin/env python3
"""Experimental JAX port of MotionCorr's global FFT alignment stage.

This is deliberately separate from the C++ executable. It accepts little-endian,
mode-2 MRC/MRCS stacks and writes one alignment shift per frame. The port keeps
the C++ full-grid weighted CCF, leave-one-frame-out reference, quadratic peak
fit, first-frame origin, iterative Fourier correction, and 0.5 px convergence
criterion. It does not implement local patches, dose weighting, or corrected
frame stacks; it can optionally write a global-only unweighted sum.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import resource
import struct
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any

import jax
import jax.numpy as jnp
import numpy as np
from jax import lax


# MotionCorr stores float32 half-complex FFTs. Keep that numerical path while
# using float64 only for the scalar peak interpolation and accumulated shifts.
jax.config.update("jax_enable_x64", True)

_GOOD_SIZES = (
    192, 216, 256, 288, 324, 384, 432, 486, 512, 576, 648, 768, 800,
    864, 972, 1024, 1296, 1536, 1728, 1944, 2048, 2304, 2592, 3072,
    3200, 3456, 3888, 4096, 4608, 5000, 5184, 6144, 6250, 6400, 6912,
    7776, 8192, 9216, 10240, 12288, 12500,
)


@dataclass(frozen=True)
class Grid:
    nx: int
    ny: int
    ccf_nx: int
    ccf_ny: int
    search_range: int


def read_mrc_stack(path: Path) -> tuple[np.ndarray, dict[str, int | float]]:
    """Read a strict little-endian MRC/MRCS mode-2 stack as (frame,y,x)."""
    with path.open("rb") as stream:
        header = stream.read(1024)
        if len(header) != 1024:
            raise ValueError(f"{path}: MRC header is shorter than 1024 bytes")
        nx, ny, nz, mode = struct.unpack_from("<4i", header, 0)
        mx, my, mz = struct.unpack_from("<3i", header, 28)
        xlen, ylen, zlen = struct.unpack_from("<3f", header, 40)
        nsymbt = struct.unpack_from("<i", header, 92)[0]
        if min(nx, ny, nz) <= 0:
            raise ValueError(f"{path}: invalid MRC dimensions {(nx, ny, nz)}")
        if mode != 2:
            raise ValueError(f"{path}: expected mode 2 float32, got mode {mode}")
        if nsymbt < 0:
            raise ValueError(f"{path}: negative extended-header size {nsymbt}")
        stream.seek(1024 + nsymbt)
        expected = nx * ny * nz
        pixels = np.fromfile(stream, dtype="<f4", count=expected)
        if pixels.size != expected:
            raise ValueError(
                f"{path}: truncated pixel data ({pixels.size} of {expected} float32 values)"
            )
        if stream.read(1):
            raise ValueError(f"{path}: trailing bytes after the declared MRC stack")
    stack = pixels.reshape(nz, ny, nx).astype(np.float32, copy=False)
    if not np.isfinite(stack).all():
        raise ValueError(f"{path}: non-finite input pixels")
    return stack, {
        "nx": nx,
        "ny": ny,
        "nframes": nz,
        "mode": mode,
        "nsymbt": nsymbt,
        "sampling_x_angstrom": float(xlen / mx) if mx > 0 else 1.0,
        "sampling_y_angstrom": float(ylen / my) if my > 0 else 1.0,
        "mrc_grid_nz": mz,
        "mrc_cell_z_angstrom": float(zlen),
    }


def _find_good_size(request: int) -> int:
    for size in _GOOD_SIZES:
        if size >= request:
            return size
    return request


def make_grid(nx: int, ny: int, scaled_b: float, ccf_downsample: float = 0.0) -> Grid:
    """Mirror the dimensions and search-range rules in alignPatch()."""
    if nx % 2 or ny % 2:
        raise ValueError("MotionCorr alignPatch requires even x and y dimensions")
    if not math.isfinite(scaled_b) or scaled_b < 0:
        raise ValueError("scaled_b must be finite and non-negative")
    if not math.isfinite(ccf_downsample) or ccf_downsample < 0 or ccf_downsample > 1:
        raise ValueError("ccf_downsample must be 0 (automatic) or in (0, 1]")

    if ccf_downsample > 0:
        requested_scale = ccf_downsample
    elif scaled_b > 0:
        requested_scale = math.sqrt(-math.log(1e-8) / (2.0 * scaled_b))
    else:
        requested_scale = 1.0

    ccf_nx = min(_find_good_size(int(nx * requested_scale)), nx)
    ccf_ny = min(_find_good_size(int(ny * requested_scale)), ny)
    if ccf_nx % 2:
        ccf_nx += 1
    if ccf_ny % 2:
        ccf_ny += 1
    scale_x = nx / ccf_nx
    scale_y = ny / ccf_ny
    search_range = int(50 / max(scale_x, scale_y))
    if search_range * 2 + 1 > ccf_nx:
        search_range = ccf_nx // 2 - 1
    if search_range * 2 + 1 > ccf_ny:
        search_range = ccf_ny // 2 - 1
    return Grid(nx, ny, ccf_nx, ccf_ny, search_range)


def _crop_rows(ny: int, ccf_ny: int) -> np.ndarray:
    half = ccf_ny // 2
    # Preserve the signed y-frequency order used by MotionCorr's C++ crop.
    return np.asarray([y if y <= half else ny - ccf_ny + y for y in range(ccf_ny)], dtype=np.int32)


@jax.jit
def _forward_rfft(images: jax.Array) -> jax.Array:
    ny, nx = images.shape[-2:]
    return jnp.fft.rfft2(images, axes=(-2, -1), norm="backward") / (nx * ny)


@jax.jit
def _inverse_and_sum(fourier: jax.Array) -> jax.Array:
    ny, nx = fourier.shape[-2], 2 * (fourier.shape[-1] - 1)
    frames = jnp.fft.irfft2(fourier, s=(ny, nx), axes=(-2, -1), norm="backward") * (nx * ny)

    def add_frame(index, accumulated):
        return accumulated + frames[index]

    return lax.fori_loop(0, frames.shape[0], add_frame, jnp.zeros((ny, nx), dtype=jnp.float32))


def _build_aligner(grid: Grid, max_iter: int, scaled_b: float, device: Any):
    nx, ny = grid.nx, grid.ny
    cnx, cny = grid.ccf_nx, grid.ccf_ny
    cfx = cnx // 2 + 1

    # Match the literal C++ frequency-index weight even when the CCF is cropped.
    signed_y = np.arange(cny, dtype=np.int32)
    signed_y = np.where(signed_y > cny // 2, signed_y - cny, signed_y)
    fx = np.arange(cfx, dtype=np.float32)
    # alignPatch's `nfx` is XSIZE(Fframes[0]) (the R2C half-spectrum width),
    # whereas its `nfy` is the real-space y dimension. Preserve that literal
    # reference convention rather than substituting the real nx here.
    nfx = nx // 2 + 1
    weight = np.exp(
        -2.0
        * scaled_b
        * (
            (signed_y.astype(np.float32)[:, None] / np.float32(ny)) ** 2
            + (fx[None, :] / np.float32(nfx)) ** 2
        )
    ).astype(np.float32)

    sy = np.arange(-grid.search_range, grid.search_range + 1, dtype=np.int32)
    sx = np.arange(-grid.search_range, grid.search_range + 1, dtype=np.int32)
    search_y, search_x = np.meshgrid(sy % cny, sx % cnx, indexing="ij")
    full_y = np.arange(ny, dtype=np.int32)
    full_y = np.where(full_y > ny // 2, full_y - ny, full_y)
    full_x = np.arange(nx // 2 + 1, dtype=np.int32)
    ramp_kx = full_x.astype(np.float32)[None, None, :]
    ramp_ky = full_y.astype(np.float32)[None, :, None]
    rows = _crop_rows(ny, cny)
    auxiliary_transfer_start = time.perf_counter()
    weight_j = jax.device_put(weight, device)
    search_y_j = jax.device_put(search_y, device)
    search_x_j = jax.device_put(search_x, device)
    ramp_kx_j = jax.device_put(ramp_kx, device)
    ramp_ky_j = jax.device_put(ramp_ky, device)
    rows_j = jax.device_put(rows, device)
    _block((weight_j, search_y_j, search_x_j, ramp_kx_j, ramp_ky_j, rows_j))
    auxiliary_transfer_seconds = time.perf_counter() - auxiliary_transfer_start

    @jax.jit
    def align(fourier_full: jax.Array, rows_device: jax.Array) -> tuple[jax.Array, jax.Array, jax.Array, jax.Array, jax.Array]:
        nframes = fourier_full.shape[0]
        fourier_ccf = fourier_full[:, rows_device, :cfx]

        initial = (
            jnp.int32(0),
            fourier_full,
            jnp.zeros((nframes,), dtype=jnp.float64),
            jnp.zeros((nframes,), dtype=jnp.float64),
            jnp.asarray(jnp.inf, dtype=jnp.float64),
        )

        def condition(state):
            iteration, _, _, _, previous_rmsd = state
            return (iteration < max_iter) & ((iteration == 0) | (previous_rmsd >= 0.5))

        def body(state):
            iteration, current_full, x_total, y_total, _ = state
            current_ccf = current_full[:, rows_device, :cfx]

            # The C++ implementation accumulates frames in ascending order.
            def add_frame(index, accumulated):
                return accumulated + current_ccf[index]

            reference = lax.fori_loop(
                0,
                nframes,
                add_frame,
                jnp.zeros((cny, cfx), dtype=jnp.complex64),
            )
            ccf_spectrum = (
                (reference[None, :, :] - current_ccf)
                * jnp.conj(current_ccf)
                * weight_j[None, :, :]
            )
            # FFTW's default C++ inverse is unnormalised. jnp.irfft2 is
            # normalized, so multiply by the grid area; the peak is unchanged.
            correlations = jnp.fft.irfft2(
                ccf_spectrum, s=(cny, cnx), axes=(-2, -1), norm="backward"
            ) * np.float32(cnx * cny)
            window = correlations[:, search_y_j, search_x_j]
            flat = window.reshape((nframes, -1))
            argmax = jnp.argmax(flat, axis=1)
            peak_value = jnp.take_along_axis(flat, argmax[:, None], axis=1)[:, 0]
            pos_y = (argmax // search_x_j.shape[1] - grid.search_range).astype(jnp.int32)
            pos_x = (argmax % search_x_j.shape[1] - grid.search_range).astype(jnp.int32)
            frame_ids = jnp.arange(nframes, dtype=jnp.int32)
            px = pos_x % cnx
            py = pos_y % cny

            right = correlations[frame_ids, py, (px + 1) % cnx].astype(jnp.float64)
            left = correlations[frame_ids, py, (px - 1) % cnx].astype(jnp.float64)
            denom_x = right + left - 2.0 * peak_value.astype(jnp.float64)
            delta_x = jnp.where(
                jnp.abs(denom_x) > 1e-15,
                pos_x.astype(jnp.float64) - 0.5 * (right - left) / denom_x,
                pos_x.astype(jnp.float64),
            )
            down = correlations[frame_ids, (py + 1) % cny, px].astype(jnp.float64)
            up = correlations[frame_ids, (py - 1) % cny, px].astype(jnp.float64)
            denom_y = down + up - 2.0 * peak_value.astype(jnp.float64)
            delta_y = jnp.where(
                jnp.abs(denom_y) > 1e-15,
                pos_y.astype(jnp.float64) - 0.5 * (down - up) / denom_y,
                pos_y.astype(jnp.float64),
            )
            delta_x = delta_x * (nx / cnx)
            delta_y = delta_y * (ny / cny)

            # Align every frame to frame zero and keep the first-frame origin.
            delta_x = delta_x - delta_x[0]
            delta_y = delta_y - delta_y[0]
            delta_x = delta_x.at[0].set(0.0)
            delta_y = delta_y.at[0].set(0.0)
            x_total = x_total + delta_x
            y_total = y_total + delta_y

            def add_square(index, sums):
                xsum, ysum = sums
                reverse_index = nframes - 1 - index
                return (
                    xsum + delta_x[reverse_index] * delta_x[reverse_index],
                    ysum + delta_y[reverse_index] * delta_y[reverse_index],
                )

            x_sum, y_sum = lax.fori_loop(
                0,
                nframes,
                add_square,
                (jnp.float64(0.0), jnp.float64(0.0)),
            )
            rmsd = jnp.sqrt((x_sum + y_sum) / nframes)

            phase = -2.0j * jnp.pi * (
                delta_x[:, None, None] * ramp_kx_j / nx
                + delta_y[:, None, None] * ramp_ky_j / ny
            )
            corrected_full = current_full * jnp.exp(phase).astype(jnp.complex64)
            return iteration + 1, corrected_full, x_total, y_total, rmsd

        iterations, current_full, x_shifts, y_shifts, rmsd = lax.while_loop(condition, body, initial)
        return x_shifts, y_shifts, iterations, rmsd, current_full

    return align, rows_j, auxiliary_transfer_seconds


def _block(value: Any) -> Any:
    return jax.block_until_ready(value)


def align_stack(
    stack: np.ndarray,
    scaled_b: float = 150.0,
    ccf_downsample: float = 0.0,
    max_iter: int = 5,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Return C++-sign-convention shifts, a global-only sum, and diagnostics."""
    if stack.ndim != 3 or stack.shape[0] < 2:
        raise ValueError("expected at least two frames in a (frame,y,x) array")
    if not np.isfinite(stack).all():
        raise ValueError("input contains non-finite pixels")
    if max_iter < 1:
        raise ValueError("max_iter must be at least one")
    nframes, ny, nx = stack.shape
    grid = make_grid(nx, ny, scaled_b, ccf_downsample)
    device = jax.devices()[0]

    transfer_start = time.perf_counter()
    images_device = jax.device_put(np.asarray(stack, dtype=np.float32), device)
    _block(images_device)
    transfer_seconds = time.perf_counter() - transfer_start

    forward_start = time.perf_counter()
    forward_compiled = _forward_rfft.lower(images_device).compile()
    forward_compile_seconds = time.perf_counter() - forward_start
    forward_first_start = time.perf_counter()
    fourier = _block(forward_compiled(images_device))
    forward_first_seconds = time.perf_counter() - forward_first_start
    forward_samples = []
    for _ in range(3):
        start = time.perf_counter()
        _block(forward_compiled(images_device))
        forward_samples.append(time.perf_counter() - start)
    forward_warm_median_seconds = median(forward_samples)

    align, ccf_rows, auxiliary_transfer_seconds = _build_aligner(grid, max_iter, scaled_b, device)
    compile_start = time.perf_counter()
    compiled_align = align.lower(fourier, ccf_rows).compile()
    compile_seconds = time.perf_counter() - compile_start
    first_start = time.perf_counter()
    result = _block(compiled_align(fourier, ccf_rows))
    first_seconds = time.perf_counter() - first_start
    warm_samples = []
    for _ in range(3):
        start = time.perf_counter()
        _block(compiled_align(fourier, ccf_rows))
        warm_samples.append(time.perf_counter() - start)
    warm_median_seconds = median(warm_samples)
    x_shifts, y_shifts, iterations, final_rmsd, aligned_fourier = result

    inverse_compile_start = time.perf_counter()
    inverse_compiled = _inverse_and_sum.lower(aligned_fourier).compile()
    inverse_compile_seconds = time.perf_counter() - inverse_compile_start
    inverse_first_start = time.perf_counter()
    corrected_sum_device = _block(inverse_compiled(aligned_fourier))
    inverse_first_seconds = time.perf_counter() - inverse_first_start
    inverse_samples = []
    for _ in range(3):
        start = time.perf_counter()
        _block(inverse_compiled(aligned_fourier))
        inverse_samples.append(time.perf_counter() - start)
    inverse_warm_median_seconds = median(inverse_samples)

    output_transfer_start = time.perf_counter()
    corrected_sum = np.asarray(corrected_sum_device, dtype=np.float32)
    output_transfer_seconds = time.perf_counter() - output_transfer_start

    peak_rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Darwin reports bytes; Linux and the other common Unix platforms report KiB.
    peak_rss_bytes = int(peak_rss_raw if __import__("sys").platform == "darwin" else peak_rss_raw * 1024)
    memory_stats = device.memory_stats()
    if memory_stats:
        device_memory = {str(key): int(value) for key, value in memory_stats.items() if isinstance(value, (int, np.integer))}
    else:
        device_memory = None

    shifts = np.column_stack((np.asarray(x_shifts), np.asarray(y_shifts)))
    diagnostics: dict[str, Any] = {
        "backend": device.platform,
        "device": str(device),
        "dtype": {"real": "float32", "fourier": "complex64", "peak_scalars": "float64"},
        "normalization": "forward FFT / (nx*ny); inverse CCF multiplied by ccf_nx*ccf_ny",
        "grid": asdict(grid),
        "iterations": int(np.asarray(iterations)),
        "last_iteration_rmsd_px": float(np.asarray(final_rmsd)),
        "converged": bool(float(np.asarray(final_rmsd)) < 0.5),
        "host_to_device_transfer_seconds": transfer_seconds,
        "host_to_device_static_alignment_arrays_seconds": auxiliary_transfer_seconds,
        "forward_fft_compile_seconds": forward_compile_seconds,
        "forward_fft_first_seconds": forward_first_seconds,
        "forward_fft_warm_median_seconds": forward_warm_median_seconds,
        "align_compile_seconds": compile_seconds,
        "align_first_seconds": first_seconds,
        "align_warm_median_seconds": warm_median_seconds,
        "inverse_sum_compile_seconds": inverse_compile_seconds,
        "inverse_sum_first_seconds": inverse_first_seconds,
        "inverse_sum_warm_median_seconds": inverse_warm_median_seconds,
        "device_to_host_output_transfer_seconds": output_transfer_seconds,
        "process_peak_rss_bytes": peak_rss_bytes,
        "jax_device_memory_stats_after_run": device_memory,
        "peak_device_memory_bytes": None,
        "memory_note": (
            "JAX exposes no peak active-device-memory counter on this backend; "
            "process peak RSS is reported separately and is not a device-memory peak."
            if device_memory is None
            else "Backend memory_stats are end-state counters, not a measured peak; see process_peak_rss_bytes."
        ),
    }
    return shifts, corrected_sum, diagnostics


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_mrc_image(
    path: Path,
    image: np.ndarray,
    sampling_x_angstrom: float = 1.0,
    sampling_y_angstrom: float = 1.0,
) -> None:
    """Write a simple little-endian mode-2 single-image MRC file."""
    if image.ndim != 2 or not np.isfinite(image).all():
        raise ValueError("corrected sum must be a finite 2D image")
    ny, nx = image.shape
    image = np.asarray(image, dtype="<f4")
    header = bytearray(1024)
    struct.pack_into("<4i", header, 0, nx, ny, 1, 2)
    struct.pack_into("<3i", header, 28, nx, ny, 1)
    struct.pack_into("<3f", header, 40, nx * sampling_x_angstrom, ny * sampling_y_angstrom, 1.0)
    struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)
    struct.pack_into("<3i", header, 64, 1, 2, 3)
    struct.pack_into("<3f", header, 76, float(image.min()), float(image.max()), float(image.mean()))
    struct.pack_into("<2i", header, 88, 0, 0)
    header[208:212] = b"MAP "
    header[212:216] = bytes((0x44, 0x41, 0, 0))
    struct.pack_into("<f", header, 216, float(image.std()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(header)
        image.tofile(stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="little-endian mode-2 MRC/MRCS stack")
    parser.add_argument("--output", required=True, type=Path, help="CSV output path for per-frame shifts")
    parser.add_argument("--corrected-sum", type=Path, help="optional global-only unweighted sum MRC output")
    parser.add_argument("--bfactor", type=float, default=150.0, help="MotionCorr B factor in A^2")
    parser.add_argument("--prescaling", type=float, default=1.0, help="early-binning factor used to scale B")
    parser.add_argument("--ccf-downsample", type=float, default=0.0, help="0=MotionCorr automatic, otherwise CCF linear scale")
    parser.add_argument("--max-iter", type=int, default=5)
    args = parser.parse_args()
    if args.prescaling <= 0:
        parser.error("--prescaling must be positive")

    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    read_start = time.perf_counter()
    stack, header = read_mrc_stack(input_path)
    read_seconds = time.perf_counter() - read_start
    shifts, corrected_sum, diagnostics = align_stack(
        stack,
        scaled_b=args.bfactor / (args.prescaling * args.prescaling),
        ccf_downsample=args.ccf_downsample,
        max_iter=args.max_iter,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("frame_number", "shift_x_px", "shift_y_px"))
        for frame_number, (shift_x, shift_y) in enumerate(shifts, start=1):
            writer.writerow((frame_number, f"{shift_x:.9f}", f"{shift_y:.9f}"))

    report = {
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "input_header": header,
        "input_read_seconds": read_seconds,
        "jax_version": jax.__version__,
        "jaxlib_version": jax.lib.__version__,
        "python_version": platform.python_version(),
        "host_platform": platform.platform(),
        "host_architecture": platform.machine(),
        "source_main": "8323c55faf1c4ddbe35dd36c5cd1266d48f25c38",
        **diagnostics,
    }
    report_path = output_path.with_suffix(output_path.suffix + ".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.corrected_sum:
        corrected_path = args.corrected_sum.expanduser().resolve()
        write_mrc_image(
            corrected_path,
            corrected_sum,
            header["sampling_x_angstrom"],
            header["sampling_y_angstrom"],
        )
        report["corrected_sum_output"] = str(corrected_path)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"shifts: {output_path}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
