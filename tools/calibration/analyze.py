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

def tier_of(rec: Dict[str, Any], harm_key: str, harm_boundary: float,
            noise_floor: Dict[str, float]) -> str:
    """Classify a measured cell as negligible, marginal or unacceptable.

    Harm is read from the absolute measurement where one exists (layer 2's
    ``harm_delta_b_a2``, against the noiseless object) and otherwise from the
    gate-visible envelope loss. Layer 2 is what licenses that substitution, by
    showing the two agree.
    """
    harm = rec.get(harm_key)
    if harm is None or not math.isfinite(float(harm)):
        harm = rec.get("std_delta_b_a2")
    harm = abs(float(harm)) if harm is not None and math.isfinite(float(harm)) else 0.0

    if harm > harm_boundary:
        return "unacceptable"

    shift = get(rec, "std_shift_px") or 0.0
    if shift > UNRECORDED_TRANSLATION_HARM_PX:
        # Declared in the prespecification as unacceptable: an unexplained
        # coordinate translation between two backends on the same input is an
        # implementation defect even though it costs no signal.
        return "unacceptable"

    if harm <= DELTA_B_NEGLIGIBLE_A2:
        eps = get(rec, "std_eps_incoherent")
        floor = noise_floor.get("std_eps_incoherent", 0.0)
        if eps is not None and eps > max(10.0 * floor, 1e-3):
            # Incoherent damage with no envelope signature: hot pixels and the
            # like. Not negligible even though delta-B is small.
            return "unacceptable"
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

def separation(
    records: List[Dict[str, Any]], diag: str, harm_key: str, harm_boundary: float,
    floors: Dict[str, float],
) -> Dict[str, Any]:
    """Largest-margin threshold for one diagnostic on one set of cells.

    Returns the highest negligible value, the lowest unacceptable value, and
    the geometric-mean threshold between them when they are separable.
    """
    neg: List[float] = []
    bad: List[float] = []
    for r in records:
        v = get(r, diag)
        if v is None:
            continue
        v = abs(v)
        t = tier_of(r, harm_key, harm_boundary, floors)
        if t == "negligible":
            neg.append(v)
        elif t == "unacceptable":
            bad.append(v)
    if not neg or not bad:
        return {"separable": False, "n_negligible": len(neg), "n_unacceptable": len(bad)}
    hi_neg = max(neg)
    lo_bad = min(bad)
    separable = lo_bad > hi_neg
    theta = math.sqrt(max(hi_neg, 1e-18) * lo_bad) if separable else float("nan")
    return {
        "separable": bool(separable),
        "n_negligible": len(neg),
        "n_unacceptable": len(bad),
        "max_negligible": hi_neg,
        "min_unacceptable": lo_bad,
        "threshold": theta,
        "separation_ratio": lo_bad / hi_neg if hi_neg > 0 else float("inf"),
    }


def apply_threshold(
    records: List[Dict[str, Any]], diag: str, theta: float, harm_key: str,
    harm_boundary: float, floors: Dict[str, float],
) -> Dict[str, Any]:
    """False-positive and false-negative counts of a fixed threshold on a cell set."""
    fp = fn = n_neg = n_bad = 0
    for r in records:
        v = get(r, diag)
        if v is None:
            continue
        t = tier_of(r, harm_key, harm_boundary, floors)
        if t == "negligible":
            n_neg += 1
            if abs(v) > theta:
                fp += 1
        elif t == "unacceptable":
            n_bad += 1
            if abs(v) <= theta:
                fn += 1
    return {
        "threshold": theta,
        "n_negligible": n_neg, "false_positives": fp,
        "fp_rate": fp / n_neg if n_neg else float("nan"),
        "n_unacceptable": n_bad, "false_negatives": fn,
        "fn_rate": fn / n_bad if n_bad else float("nan"),
    }


def classify(sel: Dict[str, Any], hold: Dict[str, Any], floor: float) -> str:
    """Apply the frozen recommendation rule (prespecification section 6.3)."""
    if not sel.get("separable"):
        return "not_recommended"
    theta = sel["threshold"]
    if floor > 0 and theta < BLOCKING_MARGIN_FACTOR * floor:
        return "strict_cpu_regression"
    if hold.get("fp_rate", 1.0) == 0.0 and hold.get("fn_rate", 1.0) == 0.0:
        return "blocking"
    if hold.get("fp_rate", 1.0) == 0.0:
        return "warning"
    return "not_recommended"


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
