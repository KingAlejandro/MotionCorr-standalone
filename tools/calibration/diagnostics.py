#!/usr/bin/env python3
"""Candidate diagnostics for the issue #60 gate calibration.

Computes, for a (reference, test) micrograph pair:

  * the five existing Gate 2 image/trajectory metrics, reproduced exactly as
    ``tools/compare_motioncorr.py`` computes them (verified by
    ``test_calibration.py``), so that response curves are directly comparable
    to recorded gate results;
  * frequency-band and interior/border splits of the relative RMSE;
  * the Spectral Transfer Decomposition of the ADR section 3.2, which
    separates a difference into scale, translation, envelope loss (delta-B)
    and an incoherent residual;
  * displacement-field statistics from the shipped motion model;
  * a high-frequency signal-retention screen.

Nothing here is a gate. This module measures; ``analyze.py`` decides.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

from . import mrcio
from .prespecification import (
    BAND_EDGES_A,
    BORDER_WIDTH_PX,
    HF_RETENTION_BAND_A,
    PIXEL_SIZE_A,
    STD_FIT_RANGE_A,
    STD_MIN_FIT_R2,
    STD_MIN_SHELL_POWER_FRACTION,
)


# ---------------------------------------------------------------------------
# Existing Gate 2 metrics
# ---------------------------------------------------------------------------

def existing_image_metrics(ref: np.ndarray, test: np.ndarray) -> Dict[str, float]:
    """The image metrics the comparator already enforces.

    Mirrors ``compare_images`` in tools/compare_motioncorr.py: the relative
    RMSE denominator is the standard deviation of the REFERENCE image, floored
    at 1e-12.
    """
    diff = test.astype(np.float64) - ref.astype(np.float64)
    rmse = float(np.sqrt(np.mean(diff * diff)))
    ref_std = float(np.std(ref.astype(np.float64)))
    return {
        "image_rmse": rmse,
        "image_relative_rmse": rmse / max(ref_std, 1e-12),
        "image_max_abs_error": float(np.max(np.abs(diff))),
        "ref_pixel_std": ref_std,
    }


def existing_trajectory_metrics(ref_shifts: np.ndarray, test_shifts: np.ndarray) -> Dict[str, float]:
    """The trajectory metrics the comparator already enforces, from (n,3) arrays."""
    if ref_shifts.shape != test_shifts.shape or not np.array_equal(
        ref_shifts[:, 0], test_shifts[:, 0]
    ):
        raise ValueError("frame sets differ between reference and test trajectories")
    d = test_shifts[:, 1:] - ref_shifts[:, 1:]
    return {
        "traj_max_shift_error": float(np.max(np.abs(d))),
        "traj_coord_rms_error": float(np.sqrt(np.mean(np.sum(d * d, axis=1)))),
    }


# ---------------------------------------------------------------------------
# Region and band splits
# ---------------------------------------------------------------------------

def region_metrics(
    ref: np.ndarray, test: np.ndarray, border_px: int = BORDER_WIDTH_PX
) -> Dict[str, float]:
    """Relative RMSE computed separately on the interior and the outer border.

    The border width matches the sampled diagnostic already reported in issue
    #36, so the two are directly comparable. Each region is normalised by the
    standard deviation of the REFERENCE within that same region, so the two
    numbers are not distorted by the border having different statistics.
    """
    ny, nx = ref.shape
    b = int(border_px)
    if 2 * b >= min(ny, nx):
        raise ValueError(f"border {b} px too wide for a {ny}x{nx} image")
    mask = np.zeros((ny, nx), dtype=bool)
    mask[b:ny - b, b:nx - b] = True

    out: Dict[str, float] = {"border_px": float(b)}
    for name, sel in (("interior", mask), ("border", ~mask)):
        r = ref[sel]
        d = test[sel] - r
        rmse = float(np.sqrt(np.mean(d * d)))
        out[f"rel_rmse_{name}"] = rmse / max(float(np.std(r)), 1e-12)
        out[f"rmse_{name}"] = rmse
    denom = out["rel_rmse_interior"]
    out["border_interior_ratio"] = out["rel_rmse_border"] / denom if denom > 0 else float("nan")
    return out


def _spectral_weights(ny: int, nx: int) -> Tuple[np.ndarray, np.ndarray]:
    """Hermitian multiplicity weights for an rfft2 grid, and a validity mask.

    ``w`` counts each interior rfft column twice, because it stands for both
    +kx and -kx on the full grid; columns 0 and (for even nx) nx/2 count once.

    ``valid`` drops the self-conjugate Nyquist column (even nx) and Nyquist row
    (even ny). Those lines cannot carry a fractional translation: a real image
    shifted by a non-integer amount is not exactly representable there, so
    ``irfft2`` discards the inconsistent part. Including them would give every
    subpixel-translation measurement an artificial incoherent residual --
    measured at 5e-3 of reference power on a 512x512 test image, which is five
    times the entire Gate 2 relative-RMSE limit. The excluded lines are one row
    and one column out of several thousand and carry negligible signal.
    """
    w = np.full((ny, nx // 2 + 1), 2.0)
    w[:, 0] = 1.0
    if nx % 2 == 0:
        w[:, -1] = 1.0
    valid = np.ones((ny, nx // 2 + 1), dtype=bool)
    if nx % 2 == 0:
        valid[:, -1] = False
    if ny % 2 == 0:
        valid[ny // 2, :] = False
    w = w * valid
    return w, valid


def _radial_shells(ny: int, nx: int) -> Tuple[np.ndarray, np.ndarray, int]:
    """Integer radial shell index over the rfft grid, plus the frequency of each shell.

    Frequencies are in cycles per pixel, computed on the true anisotropic grid
    (``fftfreq`` per axis) so that non-square micrographs are handled correctly.
    """
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    freq = np.sqrt(fy * fy + fx * fx)
    n_shell = int(min(ny, nx) // 2) + 1
    # Shell width chosen so shell i covers frequencies around i / min(ny,nx).
    idx = np.clip((freq * min(ny, nx)).astype(np.int64), 0, n_shell - 1)
    shell_freq = np.arange(n_shell, dtype=np.float64) / float(min(ny, nx))
    return idx, shell_freq, n_shell


def band_metrics(ref: np.ndarray, test: np.ndarray, pixel_size_a: float = PIXEL_SIZE_A) -> Dict[str, float]:
    """Relative RMSE restricted to low, mid and high resolution bands.

    Parseval is used: the band-limited real-space RMSE equals the band-limited
    spectral energy, so this needs no inverse transform. Each band is
    normalised by the reference energy in the SAME band, so a band with little
    reference signal is not automatically reported as a large relative error
    against the whole-image standard deviation.
    """
    ny, nx = ref.shape
    idx, shell_freq, n_shell = _radial_shells(ny, nx)

    fr = np.fft.rfft2(ref)
    ft = np.fft.rfft2(test)
    w, _ = _spectral_weights(ny, nx)

    diff_p = (np.abs(ft - fr) ** 2) * w
    ref_p = (np.abs(fr) ** 2) * w
    ref_p_nodc = ref_p.copy()
    ref_p_nodc[0, 0] = 0.0

    res_a = np.full(n_shell, np.inf)
    nz = shell_freq > 0
    res_a[nz] = pixel_size_a / shell_freq[nz]

    lo_a, hi_a = BAND_EDGES_A
    bands = {
        "low": res_a > lo_a,
        "mid": (res_a <= lo_a) & (res_a > hi_a),
        "high": res_a <= hi_a,
    }

    diff_shell = np.bincount(idx.ravel(), weights=diff_p.ravel(), minlength=n_shell)
    ref_shell = np.bincount(idx.ravel(), weights=ref_p_nodc.ravel(), minlength=n_shell)

    out: Dict[str, float] = {}
    for name, sel in bands.items():
        # Exclude the DC shell from the "low" band so a constant offset does
        # not dominate; DC is reported separately by the scale term of the STD.
        s = sel.copy()
        s[0] = False
        de = float(diff_shell[s].sum())
        re = float(ref_shell[s].sum())
        out[f"rel_rmse_{name}"] = math.sqrt(de / re) if re > 0 else float("nan")
        out[f"ref_power_{name}"] = re
    return out


# ---------------------------------------------------------------------------
# Spectral Transfer Decomposition
# ---------------------------------------------------------------------------

def _subpixel_shift(ref_ft: np.ndarray, test_ft: np.ndarray, shape: Tuple[int, int]) -> Tuple[float, float]:
    """Estimate the translation from reference to test, in pixels, to subpixel accuracy.

    Two stages:

      1. integer peak of the cross-correlation, which fixes the phase branch;
      2. a power-weighted least-squares fit of the residual linear phase ramp
         of the cross-power spectrum over the low-frequency half of the band.

    Stage 2 is used rather than a parabolic fit on the correlation peak because
    the parabolic fit is biased for a broadband image -- it was measured to be
    wrong by up to 0.05 px, which is the same size as the existing Gate 2
    max-shift limit and would have contaminated every translation result here.
    For a pure translation the phase fit is exact to machine precision.
    """
    ny, nx = shape
    cc = np.fft.irfft2(test_ft * np.conj(ref_ft), s=(ny, nx))
    peak = int(np.argmax(cc))
    py, px = divmod(peak, nx)
    if py > ny // 2:
        py -= ny
    if px > nx // 2:
        px -= nx

    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    cross = test_ft * np.conj(ref_ft)
    # Remove the integer part so the residual phase is unwrapped.
    cross = cross * np.exp(2j * np.pi * (fx * px + fy * py))

    # Restrict to |k| <= 0.25 cycles/px: a residual shift below 0.5 px then
    # produces at most +/- pi/4 of phase, well clear of wrapping.
    freq = np.sqrt(fy * fy + fx * fx)
    _, valid = _spectral_weights(ny, nx)
    sel = (freq > 0) & (freq <= 0.25) & valid
    w = np.abs(cross)[sel]
    if w.sum() <= 0:
        return float(px), float(py)
    phase = np.angle(cross[sel])
    kx = np.broadcast_to(fx, cross.shape)[sel]
    ky = np.broadcast_to(fy, cross.shape)[sel]

    # phase = -2 pi (kx*dx + ky*dy); weighted normal equations, no intercept.
    a11 = float((w * kx * kx).sum())
    a12 = float((w * kx * ky).sum())
    a22 = float((w * ky * ky).sum())
    b1 = float((w * kx * phase).sum())
    b2 = float((w * ky * phase).sum())
    det = a11 * a22 - a12 * a12
    if det == 0:
        return float(px), float(py)
    sx = (b1 * a22 - b2 * a12) / det
    sy = (a11 * b2 - a12 * b1) / det
    return float(px - sx / (2.0 * np.pi)), float(py - sy / (2.0 * np.pi))


def spectral_transfer_decomposition(
    ref: np.ndarray,
    test: np.ndarray,
    pixel_size_a: float = PIXEL_SIZE_A,
) -> Dict[str, Any]:
    """Decompose test-vs-reference into scale, translation, envelope and residual.

    See ADR section 3.2. The four outputs answer four different questions that
    a single relative RMSE cannot separate:

      ``scale_g``          multiplicative normalisation difference
      ``shift_px``         rigid translation, in pixels (and Angstrom)
      ``delta_b_a2``       high-frequency envelope loss, in Angstrom^2
      ``eps_incoherent``   the part of the difference that none of the above explains
    """
    ny, nx = ref.shape
    fr = np.fft.rfft2(ref)
    ft = np.fft.rfft2(test)

    dx, dy = _subpixel_shift(fr, ft, (ny, nx))

    # Undo the estimated translation before fitting scale and envelope, so a
    # pure shift does not masquerade as amplitude loss.
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.rfftfreq(nx)[None, :]
    ramp = np.exp(-2j * np.pi * (fx * dx + fy * dy))
    fr_shifted = fr * ramp

    idx, shell_freq, n_shell = _radial_shells(ny, nx)
    w, _ = _spectral_weights(ny, nx)

    num = np.bincount(idx.ravel(), weights=(np.real(ft * np.conj(fr_shifted)) * w).ravel(), minlength=n_shell)
    num_i = np.bincount(idx.ravel(), weights=(np.imag(ft * np.conj(fr_shifted)) * w).ravel(), minlength=n_shell)
    den = np.bincount(idx.ravel(), weights=((np.abs(fr_shifted) ** 2) * w).ravel(), minlength=n_shell)

    with np.errstate(divide="ignore", invalid="ignore"):
        gamma = (num + 1j * num_i) / den
    gamma = np.where(den > 0, gamma, np.nan)

    # Scale from the lowest non-DC shells with real signal.
    peak_power = float(np.nanmax(den[1:])) if n_shell > 1 else 0.0
    usable = (den > peak_power * STD_MIN_SHELL_POWER_FRACTION) & np.isfinite(gamma)
    usable[0] = False  # never fit DC

    scale_g = float(np.abs(gamma[usable][0])) if usable.any() else float("nan")

    # Envelope fit, restricted to the declared resolution window.
    res_a = np.full(n_shell, np.inf)
    nzf = shell_freq > 0
    res_a[nzf] = pixel_size_a / shell_freq[nzf]
    lo_a, hi_a = STD_FIT_RANGE_A
    fit_sel = usable & (res_a <= lo_a) & (res_a >= hi_a) & (np.abs(gamma) > 0)

    delta_b = float("nan")
    fit_r2 = float("nan")
    n_fit = int(fit_sel.sum())
    if n_fit >= 4 and math.isfinite(scale_g) and scale_g > 0:
        k = shell_freq[fit_sel] / pixel_size_a          # Angstrom^-1
        y = np.log(np.abs(gamma[fit_sel]) / scale_g)
        x = -0.25 * k * k
        wt = den[fit_sel]                                # weight by reference power
        wsum = wt.sum()
        xm = float((wt * x).sum() / wsum)
        ym = float((wt * y).sum() / wsum)
        sxx = float((wt * (x - xm) ** 2).sum())
        sxy = float((wt * (x - xm) * (y - ym)).sum())
        if sxx > 0:
            delta_b = sxy / sxx
            pred = ym + delta_b * (x - xm)
            ss_res = float((wt * (y - pred) ** 2).sum())
            ss_tot = float((wt * (y - ym) ** 2).sum())
            fit_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # Incoherent residual: the reference re-expressed through the fitted model,
    # subtracted from the test. Falls back to scale+shift only if the envelope
    # fit is unusable, and says so.
    envelope_used = math.isfinite(delta_b) and math.isfinite(fit_r2) and fit_r2 >= STD_MIN_FIT_R2
    freq = np.sqrt(fy * fy + fx * fx)
    k_map = freq / pixel_size_a
    basis = fr_shifted
    if envelope_used:
        basis = basis * np.exp(-delta_b * k_map * k_map / 4.0)

    # Refit the scale by global least squares against the shifted, enveloped
    # reference rather than reading it off the lowest shell. A single-shell
    # estimate is not a least-squares fit, and it was observed to leave a
    # residual LARGER than doing nothing at all on a structured fault (a single
    # mis-gained detector column): eps_incoherent 2.8e-2 against a plain
    # relative RMSE of 6.6e-3. A decomposition that increases the residual is
    # mis-specified, so the scale is now the projection coefficient, which
    # guarantees eps_incoherent <= the undecomposed residual.
    bw = basis * w
    denom_g = float(np.real(np.sum(basis * np.conj(bw))))
    g_ls = float(np.real(np.sum(ft * np.conj(bw))) / denom_g) if denom_g > 0 else 1.0
    model = basis * g_ls

    resid_p = float((np.abs(ft - model) ** 2 * w).sum())
    ref_p_nodc = float((np.abs(fr) ** 2 * w).sum()) - float(np.abs(fr[0, 0]) ** 2)
    eps_inc = math.sqrt(resid_p / ref_p_nodc) if ref_p_nodc > 0 else float("nan")

    # The undecomposed residual, for reference: what eps would be if no scale,
    # shift or envelope were removed. Reported so the decomposition's value is
    # visible per cell rather than asserted.
    eps_raw = math.sqrt(float((np.abs(ft - fr) ** 2 * w).sum()) / ref_p_nodc) if ref_p_nodc > 0 else float("nan")

    return {
        "scale_g": g_ls,
        "scale_g_lowshell": scale_g,
        "scale_dev": abs(g_ls - 1.0) if math.isfinite(g_ls) else float("nan"),
        "shift_dx_px": dx,
        "shift_dy_px": dy,
        "shift_px": math.hypot(dx, dy),
        "shift_a": math.hypot(dx, dy) * pixel_size_a,
        "delta_b_a2": delta_b,
        "fit_r2": fit_r2,
        "fit_n_shells": n_fit,
        "envelope_used": bool(envelope_used),
        "eps_incoherent": eps_inc,
        "eps_undecomposed": eps_raw,
        "eps_explained_fraction": (1.0 - (eps_inc / eps_raw) ** 2)
        if (math.isfinite(eps_raw) and eps_raw > 0) else float("nan"),
    }


# ---------------------------------------------------------------------------
# Signal-quality screen
# ---------------------------------------------------------------------------

def hf_signal_retention(
    ref: np.ndarray, test: np.ndarray, pixel_size_a: float = PIXEL_SIZE_A
) -> Dict[str, float]:
    """Ratio of test to reference azimuthally averaged power in a high-frequency band.

    This is a SCREEN, not a measurement of scientific quality. It cannot tell
    signal from noise; a backend that adds high-frequency noise scores above
    1.0. A CTF-fit-based measurement is issue #61's deliverable and is
    deliberately not duplicated here.
    """
    ny, nx = ref.shape
    idx, shell_freq, n_shell = _radial_shells(ny, nx)
    w, _ = _spectral_weights(ny, nx)
    pr = np.bincount(idx.ravel(), weights=((np.abs(np.fft.rfft2(ref)) ** 2) * w).ravel(), minlength=n_shell)
    pt = np.bincount(idx.ravel(), weights=((np.abs(np.fft.rfft2(test)) ** 2) * w).ravel(), minlength=n_shell)
    res_a = np.full(n_shell, np.inf)
    nz = shell_freq > 0
    res_a[nz] = pixel_size_a / shell_freq[nz]
    lo_a, hi_a = HF_RETENTION_BAND_A
    sel = (res_a <= lo_a) & (res_a >= hi_a)
    if not sel.any() or pr[sel].sum() <= 0:
        return {"hf_signal_retention": float("nan"), "hf_signal_retention_dev": float("nan")}
    ratio = math.sqrt(float(pt[sel].sum()) / float(pr[sel].sum()))
    return {"hf_signal_retention": ratio, "hf_signal_retention_dev": abs(ratio - 1.0)}


# ---------------------------------------------------------------------------
# Displacement field
# ---------------------------------------------------------------------------

def field_metrics(
    ref_star: Path, test_star: Path, grid: int = 9, pixel_size_a: float = PIXEL_SIZE_A
) -> Dict[str, float]:
    """Difference statistics of the total applied displacement field.

    Reports the constant offset separately from the frame-to-frame change, as
    issue #59 requires: a constant offset is an accounted-for coordinate
    translation, while frame-to-frame change is genuine residual motion.
    """
    a = mrcio.displacement_field(ref_star, grid, grid)
    b = mrcio.displacement_field(test_star, grid, grid)
    if a["field"].shape != b["field"].shape:
        return {"field_error": 1.0}
    d = b["field"] - a["field"]                       # (n_f, gy, gx, 2), px
    mag = np.sqrt((d * d).sum(axis=-1))

    const = d.mean(axis=(0, 1, 2))                    # mean over frames and positions
    d_interframe = d - d.mean(axis=0, keepdims=True)  # remove any per-position constant
    mag_inter = np.sqrt((d_interframe * d_interframe).sum(axis=-1))

    out = {
        "field_rms_px": float(np.sqrt(np.mean(mag ** 2))),
        "field_p95_px": float(np.percentile(mag, 95)),
        "field_max_px": float(np.max(mag)),
        "field_const_offset_px": float(np.hypot(*const)),
        "field_interframe_rms_px": float(np.sqrt(np.mean(mag_inter ** 2))),
        "field_has_local_model": float(a["has_local_model"] and b["has_local_model"]),
    }
    for key in ("field_rms_px", "field_p95_px", "field_max_px",
                "field_const_offset_px", "field_interframe_rms_px"):
        out[key.replace("_px", "_a")] = out[key] * pixel_size_a
    return out


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def all_image_diagnostics(
    ref: np.ndarray,
    test: np.ndarray,
    pixel_size_a: float = PIXEL_SIZE_A,
    border_px: int = BORDER_WIDTH_PX,
) -> Dict[str, Any]:
    """Every image-only diagnostic, flattened into one record."""
    out: Dict[str, Any] = {}
    out.update(existing_image_metrics(ref, test))
    out.update(region_metrics(ref, test, border_px))
    out.update(band_metrics(ref, test, pixel_size_a))
    std = spectral_transfer_decomposition(ref, test, pixel_size_a)
    out.update({f"std_{k}": v for k, v in std.items()})
    out.update(hf_signal_retention(ref, test, pixel_size_a))
    return out
