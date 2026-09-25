#!/usr/bin/env python3
"""Controlled perturbation operators for the issue #60 gate calibration.

Every operator takes its severity in a stated physical unit and is exactly
reproducible from (severity, seed). The docstring of each states what the
operator models in the real pipeline and where that model breaks down.

Two application modes exist:

  * **output-space** (layer 1): the operator is applied to an already-summed
    corrected micrograph. Exact, cheap, realistic image statistics, but it
    perturbs the summed noise as well as the signal.
  * **movie-space** (layer 2): the operator is applied to the per-frame stack
    before summation, which is what the real pipeline does. Correct treatment
    of signal versus noise, but only available where a movie is in hand.

Layer 1 and layer 2 forms of the same fault are deliberately given the same
severity parameter so the two can be compared directly.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np

from .prespecification import PIXEL_SIZE_A, X7_HOT_PIXEL_SIGMA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fourier_shift(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Translate an image by (dx, dy) pixels with a Fourier phase ramp.

    Positive dx moves content towards increasing x. Uses a real FFT so the
    result is exactly real; no interpolation kernel is introduced, which keeps
    the perturbation's own spectral signature out of the measurement.
    """
    ny, nx = image.shape
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    ramp = np.exp(-2j * np.pi * (fx * dx + fy * dy))
    return np.fft.irfft2(np.fft.rfft2(image) * ramp, s=(ny, nx))


def apply_envelope(image: np.ndarray, delta_b_a2: float, pixel_size_a: float = PIXEL_SIZE_A) -> np.ndarray:
    """Multiply the spectrum by exp(-delta_B k^2 / 4), k in Angstrom^-1."""
    ny, nx = image.shape
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    k = np.sqrt(fy * fy + fx * fx) / pixel_size_a
    return np.fft.irfft2(np.fft.rfft2(image) * np.exp(-delta_b_a2 * k * k / 4.0), s=(ny, nx))


def smooth_random_field(
    shape: Tuple[int, int],
    rms_px: float,
    correlation_fraction: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """A smooth, zero-mean random 2-D displacement field, shape (ny, nx, 2), in pixels.

    Built by low-pass filtering white noise with a Gaussian whose sigma is
    ``correlation_fraction`` of the image width, then rescaling to the
    requested RMS magnitude. This models a mis-fitted local motion model,
    which varies smoothly across the detector rather than pixel to pixel.
    """
    ny, nx = shape
    sigma = max(correlation_fraction * nx, 1.0)
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    k2 = fy * fy + fx * fx
    lowpass = np.exp(-2.0 * (np.pi * sigma) ** 2 * k2)

    comps = []
    for _ in range(2):
        white = rng.standard_normal((ny, nx))
        smooth = np.fft.irfft2(np.fft.rfft2(white) * lowpass, s=(ny, nx))
        comps.append(smooth)
    field = np.stack(comps, axis=-1)
    field -= field.mean(axis=(0, 1), keepdims=True)
    mag_rms = math.sqrt(float(np.mean((field ** 2).sum(axis=-1))))
    if mag_rms > 0:
        field *= rms_px / mag_rms
    return field


def warp(image: np.ndarray, field: np.ndarray) -> np.ndarray:
    """Warp an image by a per-pixel displacement field, bilinear, edge-clamped.

    ``field[y, x] = (dx, dy)`` is the displacement applied to the content, so
    the output at (y, x) samples the input at (y - dy, x - dx).
    """
    ny, nx = image.shape
    yy, xx = np.mgrid[0:ny, 0:nx].astype(np.float64)
    sx = np.clip(xx - field[..., 0], 0, nx - 1)
    sy = np.clip(yy - field[..., 1], 0, ny - 1)
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    x1 = np.minimum(x0 + 1, nx - 1)
    y1 = np.minimum(y0 + 1, ny - 1)
    tx = sx - x0
    ty = sy - y0
    return (
        image[y0, x0] * (1 - tx) * (1 - ty)
        + image[y0, x1] * tx * (1 - ty)
        + image[y1, x0] * (1 - tx) * ty
        + image[y1, x1] * tx * ty
    )


def apply_shift_set(image: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    """Average ``image`` over a set of translations, in one transform pair.

    The average of shifted copies is the image convolved with the empirical
    shift kernel, so the whole set collapses into a single transfer function

        h(k) = (1/N) sum_f exp(-2 pi i k . delta_f)

    applied once. This is algebraically identical to shifting and averaging
    frame by frame, and avoids N transform pairs per cell on a 3710x3838
    micrograph.
    """
    ny, nx = image.shape
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    h = np.zeros((ny, nx // 2 + 1), dtype=np.complex128)
    for dx, dy in shifts:
        h += np.exp(-2j * np.pi * (fx * float(dx) + fy * float(dy)))
    h /= len(shifts)
    return np.fft.irfft2(np.fft.rfft2(image) * h, s=(ny, nx))


# ---------------------------------------------------------------------------
# X1 -- accounted-for constant translation
# ---------------------------------------------------------------------------

def x1_translation(image: np.ndarray, t_px: float, angle_deg: float = 45.0) -> np.ndarray:
    """Translate the whole micrograph by ``t_px`` pixels.

    Models a backend that places its output on a different coordinate origin
    -- for example an off-by-half-pixel convention in the final inverse FFT.
    If the STAR metadata records the same origin, nothing scientific is lost:
    particle coordinates are extracted from the same micrograph and move with
    it. This is the archetypal FALSE ALARM for a pixel-difference gate.
    """
    r = math.radians(angle_deg)
    return fourier_shift(image, t_px * math.cos(r), t_px * math.sin(r))


# ---------------------------------------------------------------------------
# X2 -- random inter-frame jitter
# ---------------------------------------------------------------------------

def x2_jitter_kernel_transfer(sigma_px: float, n_frames: int, rng: np.random.Generator) -> np.ndarray:
    """Draw the per-frame residual shifts for a jitter perturbation, shape (n_frames, 2).

    Zero-mean Gaussian with per-axis RMS ``sigma_px``. The drawn set is
    re-centred so the mean is exactly zero, which keeps jitter (a blur) cleanly
    separated from drift (a translation).
    """
    d = rng.standard_normal((n_frames, 2)) * sigma_px
    return d - d.mean(axis=0, keepdims=True)


def x2_jitter_output(
    image: np.ndarray, sigma_px: float, n_frames: int, rng: np.random.Generator
) -> np.ndarray:
    """Layer-1 form: average ``n_frames`` shifted copies of the summed micrograph.

    LIMITATION, stated rather than hidden: in the real pipeline each frame
    carries independent noise, so residual jitter blurs the signal and leaves
    the noise essentially unchanged. Here the same noise realisation is shifted
    and averaged, so the noise is blurred too. This makes the layer-1 image
    RMSE LARGER than the pipeline would produce for the same delta-B. Layer 2
    measures that bias directly; the report quotes the factor.
    """
    return apply_shift_set(image, x2_jitter_kernel_transfer(sigma_px, n_frames, rng))


# ---------------------------------------------------------------------------
# X3 -- systematic inter-frame drift bias
# ---------------------------------------------------------------------------

def x3_drift_shifts(total_px: float, n_frames: int, angle_deg: float = 45.0) -> np.ndarray:
    """Per-frame residual shifts for a linear, uncorrected drift of ``total_px``.

    Frame f gets (f / (n-1)) * total, re-centred to zero mean so that the
    perturbation is a blur plus no net translation -- the residual drift a
    global aligner failed to remove.
    """
    r = math.radians(angle_deg)
    t = np.linspace(0.0, total_px, n_frames)
    t = t - t.mean()
    return np.stack([t * math.cos(r), t * math.sin(r)], axis=1)


def x3_drift_output(image: np.ndarray, total_px: float, n_frames: int) -> np.ndarray:
    """Layer-1 form of X3. Same noise caveat as :func:`x2_jitter_output`."""
    return apply_shift_set(image, x3_drift_shifts(total_px, n_frames))


# ---------------------------------------------------------------------------
# X4 -- corrupted local deformation field
# ---------------------------------------------------------------------------

def x4_local_field(
    image: np.ndarray, rms_px: float, correlation_fraction: float, rng: np.random.Generator
) -> np.ndarray:
    """Warp the micrograph by a smooth random displacement field of the given RMS.

    Models a local (patch) motion model that was fitted wrongly: the global
    trajectory can be perfect while the per-patch correction is not. The
    existing Gate 2 trajectory metrics read the global block only, so they are
    blind to this by construction.
    """
    field = smooth_random_field(image.shape, rms_px, correlation_fraction, rng)
    return warp(image, field)


# ---------------------------------------------------------------------------
# X5 -- high-frequency attenuation
# ---------------------------------------------------------------------------

def x5_attenuation(image: np.ndarray, delta_b_a2: float, pixel_size_a: float = PIXEL_SIZE_A) -> np.ndarray:
    """Apply an extra B-factor envelope. The harm metric applied directly as a fault.

    This is the calibration's internal consistency check: the measured
    ``std_delta_b_a2`` must recover the applied value.
    """
    return apply_envelope(image, delta_b_a2, pixel_size_a)


# ---------------------------------------------------------------------------
# X6 -- dose-weighting fault (layer 2 / layer 3)
# ---------------------------------------------------------------------------

def x6_dose_weights(
    n_frames: int,
    dose_per_frame: float,
    pixel_size_a: float,
    voltage_kv: float,
    freq_a_inv: np.ndarray,
    pre_exposure: float = 0.0,
) -> np.ndarray:
    """Grant & Grigorieff (2015) critical-exposure dose weights, shape (n_frames, n_k).

    Reimplemented here rather than imported so that layer 2 can apply a WRONG
    dose without touching the engine. The engine's own weighting is exercised
    in layer 3 through ``--dose_per_frame``.
    """
    k = np.asarray(freq_a_inv, dtype=np.float64)
    n_c = 0.24499 * np.power(np.maximum(k, 1e-8), -1.6649) + 2.8141
    if voltage_kv < 250.0:
        n_c = n_c * 0.8
    acc = pre_exposure + dose_per_frame * (np.arange(n_frames) + 0.5)
    w = np.exp(-0.5 * acc[:, None] / n_c[None, :])
    norm = np.sqrt((w * w).sum(axis=0, keepdims=True))
    return w / np.maximum(norm, 1e-12)


# ---------------------------------------------------------------------------
# X7 -- hot pixels
# ---------------------------------------------------------------------------

def x7_hot_pixels(
    image: np.ndarray, count: int, rng: np.random.Generator, sigma: float = X7_HOT_PIXEL_SIGMA
) -> np.ndarray:
    """Set ``count`` randomly chosen pixels to mean + ``sigma`` standard deviations.

    Models a defect-correction failure. Chosen because it is the archetypal
    *sparse* fault: it moves the maximum-pixel-error diagnostic a long way
    while barely moving RMSE, which is exactly the blind-spot structure the
    calibration is meant to expose.
    """
    out = image.copy()
    if count <= 0:
        return out
    ny, nx = out.shape
    n = min(int(count), ny * nx)
    flat = rng.choice(ny * nx, size=n, replace=False)
    out.reshape(-1)[flat] = float(image.mean()) + sigma * float(image.std())
    return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

#: Layer-1 (output-space) operators, keyed by the severity-grid name.
LAYER1_OPERATORS = {
    "X1_translation_px": lambda img, s, ctx: x1_translation(img, s),
    "X2_jitter_sigma_px": lambda img, s, ctx: x2_jitter_output(img, s, ctx["n_frames"], ctx["rng"]),
    "X3_drift_total_px": lambda img, s, ctx: x3_drift_output(img, s, ctx["n_frames"]),
    "X4_localfield_rms_px": lambda img, s, ctx: x4_local_field(
        img, s, ctx.get("correlation_fraction", 0.25), ctx["rng"]
    ),
    "X5_applied_delta_b_a2": lambda img, s, ctx: x5_attenuation(img, s, ctx["pixel_size_a"]),
    "X7_hot_pixel_count": lambda img, s, ctx: x7_hot_pixels(img, int(s), ctx["rng"]),
}

UNITS = {
    "X1_translation_px": "pixels",
    "X2_jitter_sigma_px": "pixels RMS per axis",
    "X3_drift_total_px": "pixels, total over the movie",
    "X4_localfield_rms_px": "pixels RMS displacement magnitude",
    "X5_applied_delta_b_a2": "Angstrom^2 added B-factor",
    "X6_dose_scale": "dimensionless multiplier on dose_per_frame",
    "X7_hot_pixel_count": "pixels affected",
    "X8_gain_error": "fractional gain error",
}
