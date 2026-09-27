#!/usr/bin/env python3
"""Derive the Issue #73 prospective margins from collection physics.

This script exists so the margins in ``docs/issue73/PROTOCOL.md`` are *derived*
and re-checkable rather than asserted.  It reads nothing from any arm's output
and must stay outcome-independent: every input below is either a physical
constant or a published property of the target collection (EMPIAR-12963 /
EMD-45966).

Run: python3 tools/science_issue73/i73_margins.py
"""

import json
import math

# --- Collection constants (EMPIAR-12963 / EMD-45966), verified from the ------
# --- deposited metadata, not from any run of this project. -------------------
COLLECTION = {
    "empiar": "EMPIAR-12963",
    "emdb": "EMD-45966",
    "specimen": "Melbournevirus Mini variant nucleosome",
    "microscope": "FEI Titan Krios",
    "detector": "Falcon IV (4k x 4k)",
    "kv": 300.0,           # EMD-45966 acceleration_voltage
    "cs_mm": 2.7,          # J189_003_particles.cs ctf/cs_mm (unique value)
    "amp_contrast": 0.1,   # J189_003_particles.cs ctf/amp_contrast
    "psize_A": 0.485,      # J189_003_particles.cs blob/psize_A (unique value)
    "box_px": 448,         # J189_003_particles.cs blob/shape
    "micrograph_px": 8192,  # passthrough location/micrograph_shape
    "total_dose_e_per_A2": 50.0,   # EMD-45966 average_electron_dose_per_image
    "map_resolution_A": 4.41,      # EMD-45966 resolution, BY AUTHOR
    "n_particles": 36051,          # EMD-45966 number_images_used
    "n_micrographs_with_particles": 2809,
}

# Rosenthal-Henderson B factor assumed for the effective-particle conversion.
# Not fitted here: a plausible value is chosen and the margin is reported for a
# range so the conclusion does not hinge on one guess.
B_RANGE_A2 = (80.0, 100.0, 150.0, 200.0)


def wavelength_A(kv: float) -> float:
    """Relativistic electron wavelength in Angstrom."""
    v = kv * 1.0e3
    return 12.2639 / math.sqrt(v * (1.0 + 0.97845e-6 * v))


def defocus_for_phase_error(d_A: float, lam_A: float, frac_of_pi: float) -> float:
    """Defocus error giving a CTF phase error of ``frac_of_pi * pi`` at ``d_A``.

    chi = pi * lambda * dz / d^2  ->  dz = frac * d^2 / lambda
    """
    return frac_of_pi * d_A * d_A / lam_A


def resolution_shift_for_particle_loss(d_A: float, b_A2: float, keep: float) -> float:
    """Resolution change (A, positive = worse) from retaining ``keep`` of particles.

    Rosenthal-Henderson: ln(N) ~ B/(2 d^2) + const, so at fixed map quality a
    change in N maps to a change in d:
        1/d_new^2 = 1/d_old^2 + (2/B) * ln(keep)
    """
    inv = 1.0 / (d_A * d_A) + (2.0 / b_A2) * math.log(keep)
    if inv <= 0:
        return float("inf")
    return 1.0 / math.sqrt(inv) - d_A


def main() -> None:
    lam = wavelength_A(COLLECTION["kv"])
    d_map = COLLECTION["map_resolution_A"]
    nyq = 2.0 * COLLECTION["psize_A"]

    out = {"collection": COLLECTION, "wavelength_A": lam, "nyquist_A": nyq}

    # --- A2: defocus equivalence margin --------------------------------------
    # Evaluated at the deposited map resolution; pi/8 is half the conventional
    # pi/4 CTF tolerance, matching the convention used for the tutorial
    # collection in PR #65 so the two studies remain comparable.
    dz_pi8 = defocus_for_phase_error(d_map, lam, 1.0 / 8.0)
    dz_pi4 = defocus_for_phase_error(d_map, lam, 1.0 / 4.0)
    out["defocus_margin"] = {
        "evaluated_at_A": d_map,
        "pi_over_8_A": dz_pi8,
        "pi_over_4_A": dz_pi4,
        "adopted_A": round(dz_pi8 / 5.0) * 5.0,
    }

    # --- B1: effective-data-fraction margin ----------------------------------
    # rho >= 0.95 is the adopted margin.  Report what a 5% and a 20% effective
    # particle loss cost in resolution on THIS collection, so the margin can be
    # read as strict or permissive rather than taken on faith.
    out["effective_data_margin"] = {
        "adopted_rho_lower_bound": 0.95,
        "resolution_cost_A": {
            f"B={b:g}": {
                "loss_5pct": resolution_shift_for_particle_loss(d_map, b, 0.95),
                "loss_20pct": resolution_shift_for_particle_loss(d_map, b, 0.80),
            }
            for b in B_RANGE_A2
        },
    }

    # --- Shell budget for the FSC-based endpoint -----------------------------
    # Qualifying shells run from 8.0 A to the deposited resolution.  For a box
    # of N pixels at pixel size p, shell k sits at d = N*p/k.
    n, p = COLLECTION["box_px"], COLLECTION["psize_A"]
    k_lo = math.ceil(n * p / 8.0)
    k_hi = math.floor(n * p / d_map)
    out["shell_budget"] = {
        "box_px": n,
        "psize_A": p,
        "band_A": [8.0, d_map],
        "k_low": k_lo,
        "k_high": k_hi,
        "n_shells": k_hi - k_lo + 1,
        "min_shells_required": 20,
    }

    # --- Storage / compute sizing -------------------------------------------
    eer_mib = 790.0  # measured mean of sampled EER files on the EMPIAR FTP
    per_mic = COLLECTION["n_particles"] / COLLECTION["n_micrographs_with_particles"]
    sizing = {}
    for nmov in (2, 25, 50, 100, 200, 350, COLLECTION["n_micrographs_with_particles"]):
        sizing[str(nmov)] = {
            "raw_eer_GiB": nmov * eer_mib / 1024.0,
            "expected_particles_random_draw": round(nmov * per_mic),
            # two arms of corrected 8192^2 float32 sums, dose-weighted only
            "corrected_both_arms_GiB": 2 * nmov * (8192 ** 2 * 4) / 2 ** 30,
        }
    out["sizing"] = {"mean_eer_MiB": eer_mib, "particles_per_micrograph": per_mic,
                     "by_movie_count": sizing}

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
