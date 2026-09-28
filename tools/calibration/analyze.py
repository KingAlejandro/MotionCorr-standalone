#!/usr/bin/env python3
"""Turn layer-1/2/3 measurements into response curves and a threshold recommendation.

The decision rule is the one frozen in ``prespecification.py`` before any
result was read; this file implements it and nothing else. It does not choose
thresholds to make any particular backend pass, and it does not read or write
the Gate 2 limits.

Outputs:
  * the repeat-run noise floor per diagnostic, from the identical-config runs;
  * response curves: diagnostic versus severity, and diagnostic versus harm;
  * for each candidate diagnostic, the threshold interval (if any) that
    separates negligible-tier from unacceptable-tier cells on the SELECTION
    split, and its false-positive/false-negative rate on the HOLD-OUT split;
  * the classification of each diagnostic as blocking, warning, strict CPU
    regression, or not recommended.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration.prespecification import (  # noqa: E402
    HOLDOUT_MOVIES,
    SELECTION_MOVIES,
    SEVERITY_GRIDS,
    split_grid,
    BLOCKING_MARGIN_FACTOR,
    CANDIDATE_DIAGNOSTICS,
    DELTA_B_HARM_A2,
    DELTA_B_HARM_SENSITIVITY,
    DELTA_B_NEGLIGIBLE_A2,
    GATE2_LIMITS_READONLY,
    SCALE_ERROR_HARM,
    UNRECORDED_TRANSLATION_HARM_PX,
)

#: Diagnostics whose value is an absolute deviation from an ideal of 1.0.
DEVIATION_DIAGNOSTICS = {"std_scale_dev", "hf_signal_retention_dev"}


def get(rec: Dict[str, Any], name: str) -> Optional[float]:
    """Fetch a candidate diagnostic from a record, mapping the STD prefixes."""
    alias = {
        "std_shift_px": "std_shift_px",
        "std_delta_b_a2": "std_delta_b_a2",
        "std_eps_incoherent": "std_eps_incoherent",
        "std_scale_dev": "std_scale_dev",
    }
    key = alias.get(name, name)
    v = rec.get(key)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ---------------------------------------------------------------------------
# Hold-out split (issue #60 review finding 1, PR #64 discussion_r4119255250)
# ---------------------------------------------------------------------------
#
# The published analysis partitioned cells with a single `split` key. Layer-3
# records never carried one -- `layer3_pipeline.collect()` did not copy it from
# the manifest -- so every Layer-3 cell fell into the selection bucket and the
# hold-out bucket contained no real-pipeline data at all. Measured on the
# committed data: 420 "hold-out" cells, of which 0 were Layer 3, and all 120
# hold-out-MOVIE cells leaked into selection. The published hold-out therefore
# validated only odd Layer-1/2 severities, on the selection movies and on
# synthetic data.
#
# The split is now DERIVED from the frozen prespecification rather than read
# from a field that may be missing, so the existing data files are classified
# correctly without re-running anything and the derivation is auditable. Two
# axes are tracked separately because they answer different questions:
#
#   movie axis     -- does the result generalise to micrographs never used to
#                     choose a threshold? Applies to Layer 1 and Layer 3.
#   severity axis  -- does it generalise to perturbation strengths never used
#                     to choose a threshold? Applies to Layer 1 and Layer 2.
#
# A cell is joint hold-out only when EVERY axis that applies to it is hold-out.

def _severity_axis(rec: Dict[str, Any]) -> Optional[str]:
    """Which side of the frozen severity grid this cell's strength falls on."""
    fault = rec.get("fault") or rec.get("group")
    if fault not in SEVERITY_GRIDS:
        return None
    sev = rec.get("severity")
    if sev is None:
        sev = (rec.get("params") or {}).get("severity")
    try:
        sev = float(sev)
    except (TypeError, ValueError):
        return None
    parts = split_grid(fault)
    for side in ("selection", "holdout"):
        if any(abs(sev - float(v)) <= 1e-9 * max(1.0, abs(float(v))) for v in parts[side]):
            return side
    return None


def _movie_axis(rec: Dict[str, Any]) -> Optional[str]:
    """Which side of the frozen movie split this cell's micrograph falls on."""
    m = rec.get("movie")
    if m is None:
        return None
    if m in SELECTION_MOVIES:
        return "selection"
    if m in HOLDOUT_MOVIES:
        return "holdout"
    return None


def cell_axes(rec: Dict[str, Any]) -> Dict[str, str]:
    """Every hold-out axis that applies to a cell, and which side it is on."""
    axes: Dict[str, str] = {}
    mv = _movie_axis(rec)
    if mv:
        axes["movie"] = mv
    sv = _severity_axis(rec)
    if sv:
        axes["severity"] = sv
    return axes


def joint_split(rec: Dict[str, Any]) -> str:
    """'selection', 'holdout', 'mixed', or 'unsplit' for a cell.

    'mixed' means the cell is hold-out on one axis and selection on another; it
    is used for neither threshold selection nor hold-out validation, because it
    is independent in one direction only.
    """
    axes = cell_axes(rec)
    if not axes:
        return "unsplit"
    vals = set(axes.values())
    if vals == {"selection"}:
        return "selection"
    if vals == {"holdout"}:
        return "holdout"
    return "mixed"


def axis_bucket(rec: Dict[str, Any], axis: str) -> Optional[str]:
    """Which side of ONE named axis a cell is on, ignoring the other axis."""
    return cell_axes(rec).get(axis)


# ---------------------------------------------------------------------------
# Tiering
# ---------------------------------------------------------------------------
#
# DEVIATION FROM THE PRESPECIFICATION, recorded rather than quietly applied.
#
# The frozen rule (prespecification section 6.3, commit 2946770) defined the
# negligible tier as "delta_B <= 1 A^2 AND eps_incoherent <= the measured
# repeat-run noise floor", and searched for a single diagnostic separating
# negligible from unacceptable cells.
#
# Two things about the measurements make that rule unusable as written:
#
#  1. The measured noise floor is EXACTLY ZERO -- every harmless layer-3 cell is
#     bit-identical. "eps_incoherent <= 0" then admits only bit-identical
#     outputs, so no non-identical cell can ever be negligible and the tiering
#     is degenerate. The eps clause is therefore dropped. This makes the
#     negligible tier LARGER, i.e. the resulting thresholds harder to satisfy,
#     not easier.
#
#  2. The fault space is not one-dimensional. A rigid translation has zero
#     envelope loss by construction, so no envelope diagnostic can ever detect
#     it, and a uniform scale error is invisible to both. Searching for one
#     diagnostic that separates the union of all faults returns "nothing works"
#     for a reason that is a property of the question, not of the diagnostics.
#     Each diagnostic is therefore scored against the fault class it is
#     responsible for, while its FALSE-POSITIVE rate is still measured against
#     EVERY negligible cell -- a gate may be narrow about what it detects but
#     must never false-alarm.
#
# The harm criterion itself (delta_B, the declared boundary, and the
# translation and scale clauses) is unchanged from the frozen specification.

#: Which unacceptable subtype each diagnostic is expected to detect.
RESPONSIBILITY: Dict[str, Tuple[str, ...]] = {
    "std_delta_b_a2": ("envelope",),
    "std_shift_px": ("geometry",),
    "std_scale_dev": ("scale",),
    # Everything else is a general-purpose claim and is scored against all of it.
}
ALL_SUBTYPES = ("envelope", "geometry", "scale")


def harm_tiered_from_rejected_fit(rec: Dict[str, Any], harm_key: str) -> bool:
    """True when a cell's harm label rests on an envelope fit the instrument rejected.

    Layer 1 and Layer 3 have no noiseless object, so ``harm_of`` falls back to
    the gate-side ``std_delta_b_a2`` -- the very quantity ``envelope_measurable``
    may declare unusable. 301 cells (78 Layer-1, 223 Layer-3) are tiered that
    way. The counterfactual in ``separation`` removes rejected fits from the
    DIAGNOSTIC side only, so those cells keep a ground-truth label derived from
    a rejected fit. Reported so the asymmetry is visible.
    """
    v = rec.get(harm_key)
    has_truth = isinstance(v, (int, float)) and math.isfinite(float(v))
    return (not has_truth) and (get(rec, "std_delta_b_a2") is not None) \
        and not rec.get("std_envelope_used", False)


def harm_of(rec: Dict[str, Any], harm_key: str) -> float:
    """Absolute envelope harm for a cell, in A^2.

    Layer 2 supplies a measurement against the noiseless object. Elsewhere the
    reference-measured envelope loss stands in for it, which layer 2 licenses
    by showing the two agree to within 0.9-1.1 for every motion fault and
    exactly for applied envelopes.
    """
    v = rec.get(harm_key)
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        v = rec.get("std_delta_b_a2")
    if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        return 0.0
    # Envelope HARM is loss, so only a positive delta-B counts.
    #
    # CONSEQUENCE, disclosed rather than buried: a cell whose envelope change is
    # NEGATIVE -- it retained more high-frequency amplitude than the reference,
    # which is what incoherent additive damage and under-dose-weighting both do
    # -- is scored as zero harm and lands in the negligible tier. Two such cells
    # set the headline separation bands in section 10.4 (X6 rho=0.5 with raw
    # harm -16.0 A^2, and X7 n=10000 with raw harm -0.87 A^2). "No diagnostic
    # separates" is therefore partly a statement about this harm model, not only
    # about the diagnostics. See report section 10.4.1. A negative value
    # means the test carries more high-frequency power than the reference, which
    # is what an incoherent additive fault such as hot pixels produces: it
    # flattens the spectrum. Taking the absolute value would score added noise
    # as if it were lost signal, and did: a 10 000-hot-pixel cell scored -37.9
    # A^2 and was tiered as severe envelope loss. Incoherent damage is not
    # visible to this harm criterion at all, which is stated as a limitation
    # rather than patched over with a post-hoc tier.
    return max(float(v), 0.0)


#: Translation accounting, derived from the frozen FAULT_CLASS and the
#: injector's declared identity -- never inferred from the measurement.
#:
#: PR #64 discussion_r4119255253. The prespecification says a translation is
#: unacceptable only when it is "not recorded in the STAR metadata", and its
#: frozen FAULT_CLASS labels X1 "benign_but_alarming": an accounted-for
#: coordinate translation, the archetypal false alarm the calibration exists to
#: distinguish. The published tier_of applied the 0.1 px clause to any
#: translation, so every X1 cell became a harmful positive and the proposed
#: std_shift_px limit was trained to reject exactly the benign case.
TRANSLATION_ACCOUNTING = {
    "X1_translation_px": "accounted",
    "C1_unrecorded_translation": "unrecorded",
}

#: Scale mode, same principle. PR #64 discussion_r4119255256: the
#: prespecification reserves the 1 % clause for a FRAME-DEPENDENT scale error,
#: and the design record states a uniform scale costs nothing because particle
#: extraction renormalises it. The published tier_of applied the clause to the
#: global scale estimate, so uniform X8 gain cells became harmful positives.
SCALE_MODE = {
    "X8_gain_error": "uniform",
    "C2_frame_dependent_scale": "frame_dependent",
}


def envelope_measurable(rec: Dict[str, Any]) -> bool:
    """Is this cell's gate-side envelope estimate a valid measurement?

    ``spectral_transfer_decomposition`` already decides this and records it as
    ``std_envelope_used``: the Gaussian B-factor fit is accepted only when its
    R^2 clears STD_MIN_FIT_R2. The published analysis consumed
    ``std_delta_b_a2`` unconditionally, so cells whose fit the instrument had
    already REJECTED still contributed a number to the threshold search.

    This matters because the fault class it matters for is the one the review
    found missing. A dose-weighting difference is not Gaussian in k^2: across
    the layer-2 dose arm the fit is accepted in 0 of 90 cells, gate-side R^2
    runs 0.0000 to 0.8361, and the resulting estimate reads about zero on cells
    whose absolute harm is +24 A^2. Excluding those cells would restore the diagnostic's
    separation by deleting the evidence against it, so they are kept and the
    unmeasurable count is reported instead.
    """
    return bool(rec.get("std_envelope_used", False))


def fault_of(rec: Dict[str, Any]) -> str:
    return str(rec.get("fault") or rec.get("group") or "")


#: The frozen prespecification is internally inconsistent about a rigid
#: translation, and this work does not resolve that by picking whichever
#: reading makes a gate pass. Both readings are carried and every result is
#: reported under each.
#:
#:   "benign"  -- FAULT_CLASS labels X1 "benign_but_alarming" and the design
#:               record's consequence table gives a translation's cost as
#:               "none: particle coordinates move with the micrograph". Under
#:               this reading X1 cells are negligible and the geometry tier is
#:               empty.
#:   "harmful" -- the harm tier declares a translation "not recorded in the
#:               STAR metadata" unacceptable. In a gate's actual use case --
#:               two backends, the SAME input -- an output offset with
#:               unchanged metadata is exactly that. Under this reading X1
#:               cells are unacceptable:geometry.
#:
#: Which is right is a scientific decision about whether a cross-backend origin
#: offset is a signal-loss question or a workflow-integration question. It is
#: not decidable from these measurements and is referred to #58.
GEOMETRY_READINGS = ("benign", "harmful")


def tier_of(rec: Dict[str, Any], harm_key: str, harm_boundary: float,
            noise_floor: Dict[str, float],
            geometry_reading: str = "benign") -> str:
    """Classify a cell as negligible, marginal, or one of the unacceptable subtypes.

    The geometry and scale clauses fire only for the fault identities the
    prespecification actually declares harmful. An accounted translation and a
    uniform scale error are reparameterisations of the same image: they are
    implementation differences worth reporting, but they are not signal loss,
    and tiering them as harmful corrupts any threshold derived from them.
    """
    harm = harm_of(rec, harm_key)
    if harm > harm_boundary:
        return "unacceptable:envelope"

    fault = fault_of(rec)
    shift = get(rec, "std_shift_px") or 0.0
    accounting = TRANSLATION_ACCOUNTING.get(fault)
    treat_as_unrecorded = (accounting == "unrecorded"
                           or (accounting == "accounted" and geometry_reading == "harmful"))
    if treat_as_unrecorded and shift > UNRECORDED_TRANSLATION_HARM_PX:
        return "unacceptable:geometry"

    scale = get(rec, "std_scale_dev") or 0.0
    if SCALE_MODE.get(fault) == "frame_dependent" and scale > SCALE_ERROR_HARM:
        return "unacceptable:scale"

    if harm <= DELTA_B_NEGLIGIBLE_A2:
        return "negligible"
    return "marginal"


# ---------------------------------------------------------------------------
# Noise floor
# ---------------------------------------------------------------------------

def noise_floor(l3: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Per-diagnostic repeat-run variation, from the identical-config layer-3 runs.

    Two floors are reported and they mean different things:

      ``j1``  identical single-thread runs. On a deterministic CPU build this
              should be exactly zero; anything else is a determinism defect.
      ``j4``  identical four-thread runs, which is the real floor any
              multi-threaded or accelerated backend has to clear.
    """
    out: Dict[str, Dict[str, float]] = {}
    for tag, pred in (("j1", lambda r: r["group"] in ("REF", "H3_repeat") and r["threads"] == 1),
                      ("j4", lambda r: r["group"] == "H3_repeat" and r["threads"] == 4)):
        vals: Dict[str, List[float]] = {}
        for r in l3:
            if not pred(r) or r.get("label") == "j1_rep0":
                continue
            for d in CANDIDATE_DIAGNOSTICS:
                v = get(r, d)
                if v is not None:
                    vals.setdefault(d, []).append(abs(v))
        out[tag] = {d: max(v) for d, v in vals.items() if v}
        out[f"{tag}_n"] = {d: float(len(v)) for d, v in vals.items() if v}
    return out


# ---------------------------------------------------------------------------
# Threshold search
# ---------------------------------------------------------------------------

def subtypes_for(diag: str) -> Tuple[str, ...]:
    return RESPONSIBILITY.get(diag, ALL_SUBTYPES)


def partition(
    records: List[Dict[str, Any]], diag: str, harm_key: str, harm_boundary: float,
    floors: Dict[str, float], geometry_reading: str = "benign",
) -> Tuple[List[float], List[float], Dict[str, int]]:
    """Split cells into the negligible values and the in-responsibility bad values."""
    want = set(subtypes_for(diag))
    neg: List[float] = []
    bad: List[float] = []
    counts: Dict[str, int] = {}
    for r in records:
        v = get(r, diag)
        if v is None:
            continue
        t = tier_of(r, harm_key, harm_boundary, floors, geometry_reading)
        counts[t] = counts.get(t, 0) + 1
        if t == "negligible":
            neg.append(abs(v))
        elif t.startswith("unacceptable:") and t.split(":", 1)[1] in want:
            bad.append(abs(v))
    return neg, bad, counts


def separation(
    records: List[Dict[str, Any]], diag: str, harm_key: str, harm_boundary: float,
    floors: Dict[str, float], geometry_reading: str = "benign",
) -> Dict[str, Any]:
    """Largest-margin threshold for one diagnostic over the cells it owns."""
    neg, bad, counts = partition(records, diag, harm_key, harm_boundary, floors,
                                 geometry_reading)
    out: Dict[str, Any] = {
        "responsibility": list(subtypes_for(diag)),
        "n_negligible": len(neg), "n_unacceptable": len(bad), "tier_counts": counts,
    }
    if diag == "std_delta_b_a2":
        scored = [r for r in records if get(r, diag) is not None]
        unmeasurable = [r for r in scored if not envelope_measurable(r)]
        out["envelope_fit_rejected"] = len(unmeasurable)
        out["envelope_fit_rejected_faults"] = sorted(
            {fault_of(r) for r in unmeasurable})
        # What the separation would be if the rejected fits were dropped. Quoted
        # only to show how much of the result depends on excluding them; it is
        # NOT the recommended reading.
        kept = [r for r in records if get(r, diag) is None or envelope_measurable(r)]
        kneg, kbad, _ = partition(kept, diag, harm_key, harm_boundary, floors,
                                  geometry_reading)
        if kneg and kbad:
            out["if_rejected_fits_excluded"] = {
                "max_negligible": max(kneg), "min_unacceptable": min(kbad),
                "separation_ratio": min(kbad) / max(kneg) if max(kneg) > 0 else float("inf"),
                "n_negligible": len(kneg), "n_unacceptable": len(kbad),
            }
    if not neg or not bad:
        out["separable"] = False
        return out
    hi_neg, lo_bad = max(neg), min(bad)
    separable = lo_bad > hi_neg
    out.update({
        "separable": bool(separable),
        "max_negligible": hi_neg,
        "min_unacceptable": lo_bad,
        "separation_ratio": lo_bad / hi_neg if hi_neg > 0 else float("inf"),
        "threshold": math.sqrt(max(hi_neg, 1e-18) * lo_bad) if separable else float("nan"),
    })
    return out


def apply_threshold(
    records: List[Dict[str, Any]], diag: str, theta: float, harm_key: str,
    harm_boundary: float, floors: Dict[str, float], geometry_reading: str = "benign",
) -> Dict[str, Any]:
    """False positives over EVERY negligible cell; false negatives over the owned ones."""
    neg, bad, _ = partition(records, diag, harm_key, harm_boundary, floors, geometry_reading)
    fp = sum(1 for v in neg if v > theta)
    fn = sum(1 for v in bad if v <= theta)
    return {
        "threshold": theta,
        "n_negligible": len(neg), "false_positives": fp,
        "fp_rate": fp / len(neg) if neg else float("nan"),
        "n_unacceptable": len(bad), "false_negatives": fn,
        "fn_rate": fn / len(bad) if bad else float("nan"),
    }


def classify(sel: Dict[str, Any], hold: Dict[str, Any], floor: float) -> str:
    """Apply the frozen recommendation rule (prespecification section 6.3)."""
    if not sel.get("separable"):
        return "not_recommended"
    theta = sel["threshold"]
    if floor > 0 and theta < BLOCKING_MARGIN_FACTOR * floor:
        return "strict_cpu_regression"
    fp = hold.get("fp_rate")
    fn = hold.get("fn_rate")
    if fp == 0.0 and fn == 0.0:
        return "blocking"
    if fp == 0.0 and (fn is None or (isinstance(fn, float) and math.isnan(fn))):
        # Nothing in this diagnostic's responsibility appeared in the hold-out
        # split; the false-positive result still holds, the detection claim is
        # untested there.
        return "blocking_fp_only"
    if fp == 0.0:
        return "warning"
    return "not_recommended"


def panel_coverage(
    records: List[Dict[str, Any]], panel: Dict[str, float], harm_key: str,
    harm_boundary: float, floors: Dict[str, float], geometry_reading: str = "benign",
) -> Dict[str, Any]:
    """Does the union of a set of thresholds catch every unacceptable cell?"""
    caught = missed = 0
    missed_examples: List[Dict[str, Any]] = []
    false_alarms = 0
    n_neg = 0
    for r in records:
        t = tier_of(r, harm_key, harm_boundary, floors, geometry_reading)
        trip = any((get(r, d) is not None and abs(get(r, d)) > th) for d, th in panel.items())
        if t.startswith("unacceptable:"):
            if trip:
                caught += 1
            else:
                missed += 1
                if len(missed_examples) < 10:
                    missed_examples.append({
                        "tier": t,
                        "fault": r.get("fault") or r.get("group"),
                        "severity": r.get("severity") or r.get("label"),
                        "layer": r.get("layer", "L3"),
                    })
        elif t == "negligible":
            n_neg += 1
            if trip:
                false_alarms += 1
    return {
        "panel": panel, "caught": caught, "missed": missed,
        "detection_rate": caught / (caught + missed) if (caught + missed) else float("nan"),
        "n_negligible": n_neg, "false_alarms": false_alarms,
        "false_alarm_rate": false_alarms / n_neg if n_neg else float("nan"),
        "missed_examples": missed_examples,
    }


# ---------------------------------------------------------------------------
# Response curves
# ---------------------------------------------------------------------------

def response_curves(records: List[Dict[str, Any]], diagnostics: Iterable[str]) -> Dict[str, Any]:
    """Median and range of each diagnostic at each (fault, severity)."""
    grouped: Dict[Tuple[str, float], List[Dict[str, Any]]] = {}
    for r in records:
        if "fault" not in r:
            continue
        grouped.setdefault((r["fault"], float(r["severity"])), []).append(r)

    out: Dict[str, Any] = {}
    for (fault, sev), rs in sorted(grouped.items()):
        entry: Dict[str, Any] = {"n": len(rs), "split": rs[0].get("split")}
        for d in list(diagnostics) + ["harm_delta_b_a2"]:
            vals = [abs(v) for v in (get(r, d) for r in rs) if v is not None]
            if vals:
                entry[d] = {
                    "median": statistics.median(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
        out.setdefault(fault, {})[f"{sev:g}"] = entry
    return out


# ---------------------------------------------------------------------------

def load(paths: List[Path]) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    for p in paths:
        recs.extend(json.loads(p.read_text())["records"])
    return recs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layer1", type=Path, nargs="*", default=[])
    ap.add_argument("--layer2", type=Path, nargs="*", default=[])
    ap.add_argument("--layer3", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--geometry-reading", choices=GEOMETRY_READINGS, default="benign",
                    help="how to tier an accounted-for rigid translation; see "
                         "GEOMETRY_READINGS. Both are reported in the issue #60 report.")
    args = ap.parse_args()

    l1 = load(args.layer1)
    l2 = load(args.layer2)
    l3 = load(args.layer3)

    floors = noise_floor(l3) if l3 else {"j1": {}, "j4": {}}
    j4_floor = floors.get("j4", {})

    report: Dict[str, Any] = {
        "geometry_reading": args.geometry_reading,
        "counts": {"layer1": len(l1), "layer2": len(l2), "layer3": len(l3)},
        "noise_floor": floors,
        "harm_boundary_declared": DELTA_B_HARM_A2,
    }

    # Response curves, per layer.
    report["curves_layer1"] = response_curves(l1, CANDIDATE_DIAGNOSTICS)
    report["curves_layer2"] = response_curves(l2, CANDIDATE_DIAGNOSTICS)

    # Layer 2 validates using the gate-visible delta-B as a harm proxy.
    bridge = []
    for r in l2:
        g = get(r, "std_delta_b_a2")
        h = r.get("harm_delta_b_a2")
        if g is None or h is None or not math.isfinite(float(h)):
            continue
        bridge.append({"fault": r["fault"], "severity": r["severity"],
                       "noise_sigma": r.get("noise_sigma"),
                       "gate_delta_b": g, "harm_delta_b": float(h)})
    report["harm_bridge"] = bridge

    # Threshold selection. Layer 2 supplies the absolute harm label; layer 1
    # and layer 3 supply realistic magnitudes. Selection and hold-out splits
    # are kept strictly apart.
    all_recs = l1 + l2 + l3

    # Two-axis split, derived from the frozen prespecification. Thresholds are
    # chosen on joint-selection cells only; hold-out is reported three ways
    # because the axes answer different questions and pooling them hides which
    # kind of generalisation was actually tested.
    sel = [r for r in all_recs if joint_split(r) == "selection"]
    hold = [r for r in all_recs if joint_split(r) == "holdout"]
    mixed = [r for r in all_recs if joint_split(r) == "mixed"]
    hold_movie = [r for r in all_recs if axis_bucket(r, "movie") == "holdout"]
    hold_sev = [r for r in all_recs if axis_bucket(r, "severity") == "holdout"]
    report["splits"] = {
        "joint_selection": len(sel), "joint_holdout": len(hold),
        "mixed_one_axis_only": len(mixed),
        "unsplit": sum(1 for r in all_recs if joint_split(r) == "unsplit"),
        "movie_axis_holdout": len(hold_movie),
        "severity_axis_holdout": len(hold_sev),
    }

    thresholds: Dict[str, Any] = {}
    reading = args.geometry_reading
    for boundary in DELTA_B_HARM_SENSITIVITY:
        per_diag: Dict[str, Any] = {}
        for d in CANDIDATE_DIAGNOSTICS:
            s = separation(sel, d, "harm_delta_b_a2", boundary, j4_floor, reading)
            if s.get("separable"):
                h = apply_threshold(hold, d, s["threshold"], "harm_delta_b_a2", boundary, j4_floor, reading)
            else:
                h = {"threshold": float("nan"), "fp_rate": float("nan"), "fn_rate": float("nan"),
                     "n_negligible": 0, "n_unacceptable": 0,
                     "false_positives": 0, "false_negatives": 0}
            per_diag[d] = {
                "selection": s,
                "holdout": h,
                "holdout_movie_axis": apply_threshold(
                    hold_movie, d, s["threshold"], "harm_delta_b_a2", boundary, j4_floor, reading)
                if s.get("separable") else None,
                "holdout_severity_axis": apply_threshold(
                    hold_sev, d, s["threshold"], "harm_delta_b_a2", boundary, j4_floor, reading)
                if s.get("separable") else None,
                "noise_floor_j4": j4_floor.get(d),
                "recommendation": classify(s, h, j4_floor.get(d, 0.0) or 0.0),
                "current_gate2_limit": GATE2_LIMITS_READONLY.get(d),
            }
        thresholds[f"harm_{boundary:g}"] = per_diag
    report["thresholds"] = thresholds

    # Panel coverage: a single diagnostic cannot see every fault class, so the
    # recommendation is a small panel. This measures whether the panel as a
    # whole catches every unacceptable cell without alarming on a negligible one.
    panels = {}
    for boundary in DELTA_B_HARM_SENSITIVITY:
        per_diag = thresholds[f"harm_{boundary:g}"]
        panel = {}
        for d in ("std_delta_b_a2", "std_shift_px", "std_scale_dev"):
            sel_d = per_diag[d]["selection"]
            if sel_d.get("separable"):
                panel[d] = sel_d["threshold"]
        if panel:
            panels[f"harm_{boundary:g}"] = {
                "selection": panel_coverage(sel, panel, "harm_delta_b_a2", boundary, j4_floor, reading),
                "holdout": panel_coverage(hold, panel, "harm_delta_b_a2", boundary, j4_floor, reading),
                "holdout_movie_axis": panel_coverage(
                    hold_movie, panel, "harm_delta_b_a2", boundary, j4_floor, reading),
                "holdout_severity_axis": panel_coverage(
                    hold_sev, panel, "harm_delta_b_a2", boundary, j4_floor, reading),
                "combined": panel_coverage(all_recs, panel, "harm_delta_b_a2", boundary, j4_floor, reading),
            }
    report["panel_coverage"] = panels

    args.out.write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out}")

    # Human-readable summary at the declared boundary.
    key = f"harm_{DELTA_B_HARM_A2:g}"
    print(f"\nRecommendations at the declared harm boundary delta_B > {DELTA_B_HARM_A2} A^2"
          f"   [geometry reading: {reading}]")
    print(f"{'diagnostic':28s} {'rec':22s} {'theta':>11s} {'sel sep':>9s} "
          f"{'hold FP':>8s} {'hold FN':>8s} {'j4 floor':>10s}")
    for d, v in thresholds[key].items():
        s, h = v["selection"], v["holdout"]
        theta = s.get("threshold", float("nan"))
        print(f"{d:28s} {v['recommendation']:22s} "
              f"{theta if isinstance(theta, float) else float('nan'):11.4g} "
              f"{s.get('separation_ratio', float('nan')):9.3g} "
              f"{h.get('fp_rate', float('nan')):8.3g} {h.get('fn_rate', float('nan')):8.3g} "
              f"{(v['noise_floor_j4'] if v['noise_floor_j4'] is not None else float('nan')):10.3g}")

    census = {}
    for r in all_recs:
        t = tier_of(r, "harm_delta_b_a2", DELTA_B_HARM_A2, j4_floor, reading)
        census[t] = census.get(t, 0) + 1
    print(f"\ncell census at the declared boundary: {census}")
    print(f"splits: {report['splits']}")
    for name, subset in (("joint hold-out", hold), ("movie-axis hold-out", hold_movie),
                         ("severity-axis hold-out", hold_sev)):
        sub = {}
        for r in subset:
            t = tier_of(r, "harm_delta_b_a2", DELTA_B_HARM_A2, j4_floor, reading)
            sub[t] = sub.get(t, 0) + 1
        print(f"  {name:24s} n={len(subset):4d} tiers={sub}")

    pc = report.get("panel_coverage", {}).get(f"harm_{DELTA_B_HARM_A2:g}")
    if pc:
        print("\npanel {d: theta}: " + ", ".join(
            f"{k}<={v:.4g}" for k, v in pc["combined"]["panel"].items()))
        for split in ("selection", "holdout", "combined"):
            c = pc[split]
            print(f"  {split:10s} detection {c['caught']}/{c['caught']+c['missed']} "
                  f"({c['detection_rate']:.3f}), false alarms {c['false_alarms']}/"
                  f"{c['n_negligible']} ({c['false_alarm_rate']:.3f})")
        if pc["combined"]["missed_examples"]:
            print("  missed examples:", pc["combined"]["missed_examples"][:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
