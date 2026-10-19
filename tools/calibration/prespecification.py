#!/usr/bin/env python3
"""Frozen prespecification for the issue #60 gate calibration.

This module is committed BEFORE any calibration result is inspected. It fixes
the perturbation matrix, the severity grids, the movie split, the harm tiers,
and the rule by which a candidate limit is accepted or rejected.

Nothing here may be edited once calibration results have been read. If a change
is unavoidable, it must be a new commit that says so explicitly and the report
must present both the original and the revised plan.

Reference: agents/designs/issue_60_gate_calibration.md
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

# ---------------------------------------------------------------------------
# Dataset constants (RELION SPA tutorial, EMPIAR-10204)
# ---------------------------------------------------------------------------

PIXEL_SIZE_A = 0.885          # Angstrom / pixel, from test-data/prepare_movies_star.py
VOLTAGE_KV = 200.0
NYQUIST_A = 2.0 * PIXEL_SIZE_A
DOSE_PER_FRAME = 1.277        # e-/A^2/frame, the documented tutorial setting
N_FRAMES = 24
PATCH_X = 5
PATCH_Y = 5
BFACTOR = 150.0

# ---------------------------------------------------------------------------
# Harm tiers (section 3.3 of the ADR). Declared in advance.
# ---------------------------------------------------------------------------

DELTA_B_NEGLIGIBLE_A2 = 1.0   # <= this is "must not fail a blocking gate"
DELTA_B_HARM_A2 = 5.0         # >  this is "must fail a blocking gate"
DELTA_B_HARM_SENSITIVITY = (2.0, 5.0, 10.0)   # every conclusion re-reported at each

#: Resolution at which amplitude loss is quoted, in Angstrom.
HARM_REPORT_RESOLUTION_A = 3.0

#: A frame-dependent scale error above this fraction is unacceptable regardless of dB.
SCALE_ERROR_HARM = 0.01

#: A translation larger than this, not recorded in the STAR metadata, is unacceptable.
UNRECORDED_TRANSLATION_HARM_PX = 0.10


def amplitude_loss(delta_b_a2: float, resolution_a: float = HARM_REPORT_RESOLUTION_A) -> float:
    """Fractional amplitude loss implied by an added B-factor at a given resolution."""
    return 1.0 - math.exp(-delta_b_a2 / (4.0 * resolution_a * resolution_a))


def sigma_px_for_delta_b(delta_b_a2: float, pixel_size_a: float = PIXEL_SIZE_A) -> float:
    """Per-axis RMS residual shift (px) that produces a given added B-factor.

    Forward model (ADR section 3.4): for zero-mean Gaussian per-frame residual
    shifts with per-axis RMS ``sigma`` pixels, the sum is convolved with a
    Gaussian whose transfer is exp(-2 pi^2 sigma^2 k^2), i.e.

        delta_B = 8 * pi^2 * sigma^2 * a^2   [A^2]

    This is a PREDICTION made before measurement; layer 2 checks it.
    """
    return math.sqrt(delta_b_a2 / (8.0 * math.pi * math.pi)) / pixel_size_a


def delta_b_for_sigma_px(sigma_px: float, pixel_size_a: float = PIXEL_SIZE_A) -> float:
    """Inverse of :func:`sigma_px_for_delta_b`."""
    return 8.0 * math.pi * math.pi * sigma_px * sigma_px * pixel_size_a * pixel_size_a


# ---------------------------------------------------------------------------
# Existing Gate 2 limits, quoted here read-only for comparison.
# THESE ARE NOT MODIFIED BY THIS WORK.
# ---------------------------------------------------------------------------

GATE2_LIMITS_READONLY = {
    "traj_max_shift_error": 0.05,      # px
    "traj_coord_rms_error": 0.02,      # px
    "image_rmse": 0.020,               # absolute
    "image_relative_rmse": 0.001,      # relative to reference std
    "image_max_abs_error": 5.0,        # absolute
}

GATE1_LIMITS_READONLY = {
    "traj_max_shift_error": 1e-4,
    "traj_coord_rms_error": 1e-4,
    "image_rmse": 1e-7,
    "image_max_abs_error": 1e-7,
}

# ---------------------------------------------------------------------------
# Perturbation matrix (ADR section 6.1)
# ---------------------------------------------------------------------------

#: Every grid is ordered ascending. Index 0,2,4,... -> selection; 1,3,5,... -> hold-out.
SEVERITY_GRIDS: Dict[str, Sequence[float]] = {
    "X1_translation_px": (0.10, 0.25, 0.50, 1.00, 2.00, 4.00),
    "X2_jitter_sigma_px": (0.02, 0.05, 0.10, 0.20, 0.40, 0.80),
    "X3_drift_total_px": (0.05, 0.10, 0.25, 0.50, 1.00, 2.00),
    "X4_localfield_rms_px": (0.05, 0.10, 0.20, 0.50, 1.00, 2.00),
    "X5_applied_delta_b_a2": (1.0, 2.0, 5.0, 10.0, 25.0, 50.0),
    "X6_dose_scale": (0.50, 0.80, 0.95, 1.05, 1.25, 2.00),
    "X7_hot_pixel_count": (1, 10, 100, 1000, 10000),
    "X8_gain_error": (1e-4, 1e-3, 1e-2, 1e-1),
}

#: Secondary factor for X4: correlation length as a fraction of image width.
X4_CORRELATION_LENGTHS = (0.25, 0.50)

#: Hot-pixel amplitude, in units of the frame standard deviation above its mean.
X7_HOT_PIXEL_SIGMA = 50.0

FAULT_CLASS = {
    "H1_threads": "harmless",
    "H2_proc_bind": "harmless",
    "H3_repeat": "harmless",
    "H4_null": "harmless",
    "X1_translation_px": "benign_but_alarming",
    "X2_jitter_sigma_px": "harmful",
    "X3_drift_total_px": "harmful",
    "X4_localfield_rms_px": "harmful",
    "X5_applied_delta_b_a2": "harmful",
    "X6_dose_scale": "harmful",
    "X7_hot_pixel_count": "harmful",
    "X8_gain_error": "harmful",
}

#: Which experiment layers can reach which fault (ADR section 4.2).
FAULT_LAYERS = {
    "H1_threads": ("L3",),
    "H2_proc_bind": ("L3",),
    "H3_repeat": ("L3",),
    "H4_null": ("L1", "L2", "L3"),
    "X1_translation_px": ("L1", "L2", "L3"),
    "X2_jitter_sigma_px": ("L1", "L2"),
    "X3_drift_total_px": ("L1", "L2"),
    "X4_localfield_rms_px": ("L1", "L2"),
    "X5_applied_delta_b_a2": ("L1", "L2"),
    "X6_dose_scale": ("L2", "L3"),
    "X7_hot_pixel_count": ("L1", "L2", "L3"),
    "X8_gain_error": ("L3",),
}

# ---------------------------------------------------------------------------
# Splits (ADR section 6.2). Frozen.
# ---------------------------------------------------------------------------

SELECTION_MOVIES = ("00021", "00023", "00025", "00027", "00029", "00031")
HOLDOUT_MOVIES = ("00042", "00044", "00046", "00047", "00048", "00049")
#: Never touched by this issue; reserved for #61 and future confirmation.
RESERVED_MOVIES = (
    "00022", "00024", "00026", "00028", "00030", "00035",
    "00036", "00037", "00039", "00040", "00043", "00045",
)

#: Harmless-variation matrix run on every selection movie (L3).
L3_THREAD_COUNTS = (1, 2, 4, 8)
L3_PROC_BIND = ("unset", "close", "spread")
L3_REPEATS = 5


def split_grid(name: str) -> Dict[str, List[float]]:
    """Return {'selection': [...], 'holdout': [...]} for a named severity grid."""
    grid = list(SEVERITY_GRIDS[name])
    return {
        "selection": grid[0::2],
        "holdout": grid[1::2],
    }


# ---------------------------------------------------------------------------
# Acceptance rule for a candidate limit (ADR section 6.3). Frozen.
# ---------------------------------------------------------------------------

#: A blocking limit must clear the measured repeat-run noise floor by this factor.
BLOCKING_MARGIN_FACTOR = 3.0

#: Maximum false-positive rate on negligible-tier cells for a blocking limit.
BLOCKING_MAX_FP = 0.0

#: Maximum false-negative rate on unacceptable-tier cells for a blocking limit.
BLOCKING_MAX_FN = 0.0

RECOMMENDATION_TIERS = (
    "blocking",               # fails the build for every backend
    "warning",                # reported, non-blocking
    "strict_cpu_regression",  # blocking only for same-platform single-thread CPU
    "not_recommended",        # measured, does not discriminate
)

#: Candidate diagnostics evaluated in this calibration.
CANDIDATE_DIAGNOSTICS = (
    "image_rmse",
    "image_relative_rmse",
    "image_max_abs_error",
    "traj_max_shift_error",
    "traj_coord_rms_error",
    "rel_rmse_low",
    "rel_rmse_mid",
    "rel_rmse_high",
    "rel_rmse_interior",
    "rel_rmse_border",
    "std_scale_dev",
    "std_shift_px",
    "std_delta_b_a2",
    "std_eps_incoherent",
    "field_rms_px",
    "field_interframe_rms_px",
    "field_max_px",
    "hf_signal_retention_dev",
)

# ---------------------------------------------------------------------------
# Spectral Transfer Decomposition fit configuration (ADR section 3.2). Frozen.
# ---------------------------------------------------------------------------

#: B-factor fit range, in Angstrom resolution (low-res bound, high-res bound).
STD_FIT_RANGE_A = (20.0, 3.0)

#: Shells whose reference power is below this fraction of the peak shell power
#: are excluded from the fit.
STD_MIN_SHELL_POWER_FRACTION = 1e-6

#: Fits below this R^2 are excluded and counted as failures.
STD_MIN_FIT_R2 = 0.90

#: Border width, in pixels, for the interior/border split. Matches the
#: sampled diagnostic already reported in issue #36.
BORDER_WIDTH_PX = 100

#: Frequency-band edges for the low/mid/high split, in Angstrom resolution.
#: low: worse than 10 A; mid: 10-4 A; high: better than 4 A.
BAND_EDGES_A = (10.0, 4.0)

#: High-frequency signal-retention screen band, in Angstrom.
HF_RETENTION_BAND_A = (8.0, 4.0)


def summary() -> str:
    lines = [
        "MotionCorr issue #60 calibration prespecification",
        f"  pixel size            : {PIXEL_SIZE_A} A/px  (Nyquist {NYQUIST_A} A)",
        f"  harm boundary         : delta_B > {DELTA_B_HARM_A2} A^2 "
        f"({100*amplitude_loss(DELTA_B_HARM_A2):.1f}% amplitude loss at "
        f"{HARM_REPORT_RESOLUTION_A} A)",
        f"  negligible boundary   : delta_B <= {DELTA_B_NEGLIGIBLE_A2} A^2 "
        f"({100*amplitude_loss(DELTA_B_NEGLIGIBLE_A2):.1f}% at "
        f"{HARM_REPORT_RESOLUTION_A} A)",
        f"  predicted sigma at harm boundary : "
        f"{sigma_px_for_delta_b(DELTA_B_HARM_A2):.4f} px",
        f"  predicted sigma at negligible    : "
        f"{sigma_px_for_delta_b(DELTA_B_NEGLIGIBLE_A2):.4f} px",
        f"  existing coord-RMS gate 0.02 px  -> delta_B = "
        f"{delta_b_for_sigma_px(0.02):.5f} A^2",
        f"  selection movies      : {' '.join(SELECTION_MOVIES)}",
        f"  hold-out movies       : {' '.join(HOLDOUT_MOVIES)}",
        f"  reserved (untouched)  : {' '.join(RESERVED_MOVIES)}",
    ]
    for name in SEVERITY_GRIDS:
        s = split_grid(name)
        lines.append(f"  {name:26s} sel={s['selection']} hold={s['holdout']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
