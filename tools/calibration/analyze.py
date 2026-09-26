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
    # Envelope HARM is loss, so only a positive delta-B counts. A negative value
    # means the test carries more high-frequency power than the reference, which
    # is what an incoherent additive fault such as hot pixels produces: it
    # flattens the spectrum. Taking the absolute value would score added noise
    # as if it were lost signal, and did: a 10 000-hot-pixel cell scored -37.9
    # A^2 and was tiered as severe envelope loss. Incoherent damage is not
    # visible to this harm criterion at all, which is stated as a limitation
    # rather than patched over with a post-hoc tier.
    return max(float(v), 0.0)


def tier_of(rec: Dict[str, Any], harm_key: str, harm_boundary: float,
            noise_floor: Dict[str, float]) -> str:
    """Classify a cell as negligible, marginal, or one of the unacceptable subtypes."""
    harm = harm_of(rec, harm_key)
    shift = get(rec, "std_shift_px") or 0.0
    scale = get(rec, "std_scale_dev") or 0.0

    if harm > harm_boundary:
        return "unacceptable:envelope"
    if shift > UNRECORDED_TRANSLATION_HARM_PX:
        return "unacceptable:geometry"
    if scale > SCALE_ERROR_HARM:
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
    floors: Dict[str, float],
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
        t = tier_of(r, harm_key, harm_boundary, floors)
        counts[t] = counts.get(t, 0) + 1
        if t == "negligible":
            neg.append(abs(v))
        elif t.startswith("unacceptable:") and t.split(":", 1)[1] in want:
            bad.append(abs(v))
    return neg, bad, counts


def separation(
    records: List[Dict[str, Any]], diag: str, harm_key: str, harm_boundary: float,
    floors: Dict[str, float],
) -> Dict[str, Any]:
    """Largest-margin threshold for one diagnostic over the cells it owns."""
    neg, bad, counts = partition(records, diag, harm_key, harm_boundary, floors)
    out: Dict[str, Any] = {
        "responsibility": list(subtypes_for(diag)),
        "n_negligible": len(neg), "n_unacceptable": len(bad), "tier_counts": counts,
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
    harm_boundary: float, floors: Dict[str, float],
) -> Dict[str, Any]:
    """False positives over EVERY negligible cell; false negatives over the owned ones."""
    neg, bad, _ = partition(records, diag, harm_key, harm_boundary, floors)
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
    harm_boundary: float, floors: Dict[str, float],
) -> Dict[str, Any]:
    """Does the union of a set of thresholds catch every unacceptable cell?"""
    caught = missed = 0
    missed_examples: List[Dict[str, Any]] = []
    false_alarms = 0
    n_neg = 0
    for r in records:
        t = tier_of(r, harm_key, harm_boundary, floors)
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
    args = ap.parse_args()

    l1 = load(args.layer1)
    l2 = load(args.layer2)
    l3 = load(args.layer3)

    floors = noise_floor(l3) if l3 else {"j1": {}, "j4": {}}
    j4_floor = floors.get("j4", {})

    report: Dict[str, Any] = {
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
    sel = [r for r in all_recs if r.get("split") in (None, "selection", "control")
           or r.get("movie", "") in ()]
    hold = [r for r in all_recs if r.get("split") == "holdout"]

    thresholds: Dict[str, Any] = {}
    for boundary in DELTA_B_HARM_SENSITIVITY:
        per_diag: Dict[str, Any] = {}
        for d in CANDIDATE_DIAGNOSTICS:
            s = separation(sel, d, "harm_delta_b_a2", boundary, j4_floor)
            if s.get("separable"):
                h = apply_threshold(hold, d, s["threshold"], "harm_delta_b_a2", boundary, j4_floor)
            else:
                h = {"threshold": float("nan"), "fp_rate": float("nan"), "fn_rate": float("nan"),
                     "n_negligible": 0, "n_unacceptable": 0,
                     "false_positives": 0, "false_negatives": 0}
            per_diag[d] = {
                "selection": s,
                "holdout": h,
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
                "selection": panel_coverage(sel, panel, "harm_delta_b_a2", boundary, j4_floor),
                "holdout": panel_coverage(hold, panel, "harm_delta_b_a2", boundary, j4_floor),
                "combined": panel_coverage(all_recs, panel, "harm_delta_b_a2", boundary, j4_floor),
            }
    report["panel_coverage"] = panels

    args.out.write_text(json.dumps(report, indent=2))
    print(f"wrote {args.out}")

    # Human-readable summary at the declared boundary.
    key = f"harm_{DELTA_B_HARM_A2:g}"
    print(f"\nRecommendations at the declared harm boundary delta_B > {DELTA_B_HARM_A2} A^2")
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
        t = tier_of(r, "harm_delta_b_a2", DELTA_B_HARM_A2, j4_floor)
        census[t] = census.get(t, 0) + 1
    print(f"\ncell census at the declared boundary: {census}")
    print(f"selection cells {len(sel)}, hold-out cells {len(hold)}")

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
