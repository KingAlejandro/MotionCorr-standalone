#!/usr/bin/env python3
"""Re-derive every load-bearing number quoted in the issue #60 report.

Run from the repository root:

    python3 tools/calibration/verify_report_numbers.py

Exits non-zero if any number in docs/calibration/issue60_gate_calibration.md
drifts from what docs/calibration/data/*.json actually contains. It exists so a
reviewer does not have to take the prose on trust, and so a later edit to the
data cannot silently invalidate the report.

Revised 28 September 2026 for the review round: the split, the tiering and the
Layer-2 dose arm all changed, so the expected values here changed with them.
The superseded pre-review values are listed in report section 0.1.
"""

from __future__ import annotations

import collections
import glob
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.calibration import analyze as A  # noqa: E402

OK: list[bool] = []


def chk(claim: str, got: float, want: float, tol: float = 0.02) -> None:
    good = abs(got - want) <= tol * max(abs(want), 1e-12) if want else abs(got) <= tol
    OK.append(good)
    print(f"[{'OK ' if good else 'BAD'}] {claim}: report {want}, data {got}")


def med(rows, key):
    vals = [v for v in (A.get(r, key) for r in rows) if v is not None]
    return st.median(vals) if vals else float("nan")


def main() -> int:
    paths = [Path(p) for p in glob.glob("docs/calibration/data/layer*.json")]
    l1 = A.load([p for p in paths if "layer1" in p.name])
    l2 = A.load([p for p in paths if "layer2" in p.name])
    l3 = A.load([p for p in paths if "layer3" in p.name])
    allr = l1 + l2 + l3
    floors = A.noise_floor(l3)["j4"]

    print("--- cell counts ---")
    chk("layer 1 cells", len(l1), 252, 0)
    chk("layer 2 cells (with the X6 arm and C2 control)", len(l2), 780, 0)
    chk("layer 3 cells", len(l3), 247, 0)
    chk("total cells", len(allr), 1279, 0)

    print("\n--- section 5: harmless-variation floor ---")
    harmless = [r for r in l3 if r.get("group") in
                ("REF", "H1_threads", "H2_proc_bind", "H3_repeat")
                or r.get("label") in ("gain_null", "mov_null")]
    vals = [abs(A.get(r, d)) for r in harmless for d in
            ("image_relative_rmse", "image_rmse", "image_max_abs_error",
             "std_delta_b_a2", "std_eps_incoherent", "std_shift_px",
             "std_scale_dev", "traj_max_shift_error", "traj_coord_rms_error",
             "field_rms_px") if A.get(r, d) is not None]
    chk("harmless cell count", len(harmless), 176, 0)
    chk("largest harmless value", max(vals), 1.478e-15, 0.05)

    print("\n--- section 0 / 9: the corrected two-axis split ---")
    js = collections.Counter(A.joint_split(r) for r in allr)
    chk("joint selection cells", js["selection"], 619, 0)
    chk("joint hold-out cells", js["holdout"], 441, 0)
    chk("mixed (one axis only)", js["mixed"], 144, 0)
    chk("movie-axis hold-out cells",
        sum(1 for r in allr if A.axis_bucket(r, "movie") == "holdout"), 120, 0)
    chk("severity-axis hold-out cells",
        sum(1 for r in allr if A.axis_bucket(r, "severity") == "holdout"), 471, 0)
    chk("Layer-3 cells with no resolvable movie axis",
        sum(1 for r in l3 if A.axis_bucket(r, "movie") is None), 0, 0)
    hm = [r for r in allr if A.axis_bucket(r, "movie") == "holdout"]
    hm_t = collections.Counter(A.tier_of(r, "harm_delta_b_a2", 5.0, floors) for r in hm)
    chk("hold-out movies carry no unacceptable cells (section 0.3)",
        sum(v for k, v in hm_t.items() if k.startswith("unacceptable")), 0, 0)
    chk("hold-out movie negligible cells", hm_t["negligible"], 114, 0)

    print("\n--- section 0 / 10: the corrected tiering ---")
    cen = collections.Counter(A.tier_of(r, "harm_delta_b_a2", 5.0, floors) for r in allr)
    chk("negligible cells (benign reading)", cen["negligible"], 727, 0)
    chk("unacceptable:envelope cells", cen["unacceptable:envelope"], 344, 0)
    chk("marginal cells", cen["marginal"], 208, 0)
    chk("geometry positives under the benign reading",
        cen.get("unacceptable:geometry", 0), 0, 0)
    chk("scale positives (no frame-dependent fault in the frozen matrix)",
        cen.get("unacceptable:scale", 0), 0, 0)
    cenh = collections.Counter(
        A.tier_of(r, "harm_delta_b_a2", 5.0, floors, "harmful") for r in allr)
    chk("geometry positives under the harmful reading",
        cenh.get("unacceptable:geometry", 0), 112, 0)

    print("\n--- section 6.1: the X6 dose arm ---")
    x6 = [r for r in l2 if A.fault_of(r) == "X6_dose_scale"]
    chk("X6 cells generated", len(x6), 90, 0)
    chk("X6 cells whose Gaussian envelope fit was accepted",
        sum(1 for r in x6 if r.get("std_envelope_used")), 0, 0)
    for rho, gate, harm in ((0.5, 3.199, -15.804), (2.0, -0.953, 24.130)):
        rows = [r for r in x6 if abs(r["severity"] - rho) < 1e-9
                and r.get("noise_sigma") == 10]
        chk(f"X6 rho={rho} gate delta-B (noise 10)", med(rows, "std_delta_b_a2"), gate, 0.05)
        chk(f"X6 rho={rho} absolute harm delta-B (noise 10)",
            st.median([r["harm_delta_b_a2"] for r in rows]), harm, 0.05)
    worst = sorted(abs(A.get(r, "std_delta_b_a2")) for r in x6
                   if abs(r["severity"] - 2.0) < 1e-9 and A.get(r, "std_delta_b_a2") is not None)
    chk("smallest gate delta-B among the double-dose cells", worst[0], 0.0004, 0.5)

    print("\n--- section 10.3: the C2 frame-dependent scale control ---")
    c2 = [r for r in l2 if A.fault_of(r) == "C2_frame_dependent_scale"]
    chk("C2 cells generated", len(c2), 60, 0)
    rows = [r for r in c2 if abs(r["severity"] - 0.5) < 1e-9 and r.get("noise_sigma") == 10]
    chk("C2 eps=0.5 scale_dev (noise 10)", med(rows, "std_scale_dev"), 1.657e-4, 0.05)
    chk("C2 eps=0.5 absolute harm (noise 10)",
        st.median([r["harm_delta_b_a2"] for r in rows]), 0.057, 0.15)

    print("\n--- section 10.4: separation now fails for every diagnostic ---")
    sel = [r for r in allr if A.joint_split(r) == "selection"]
    for d, mx, mn in (("std_delta_b_a2", 3.296, 0.1207),
                      ("image_relative_rmse", 4.885, 0.0605)):
        s = A.separation(sel, d, "harm_delta_b_a2", 5.0, floors)
        chk(f"{d} separable", 1.0 if s.get("separable") else 0.0, 0.0, 0)
        chk(f"{d} max on negligible", s["max_negligible"], mx, 0.01)
        chk(f"{d} min on unacceptable", s["min_unacceptable"], mn, 0.01)
    s = A.separation(sel, "std_delta_b_a2", "harm_delta_b_a2", 5.0, floors)
    chk("std_delta_b_a2 separation ratio", s["separation_ratio"], 0.0366, 0.02)
    chk("cells whose envelope fit was rejected", s["envelope_fit_rejected"], 353, 0)
    ex = s["if_rejected_fits_excluded"]
    chk("band if rejected fits were excluded", ex["separation_ratio"], 7.02, 0.02)
    for d in ("std_shift_px", "std_scale_dev"):
        s2 = A.separation(sel, d, "harm_delta_b_a2", 5.0, floors)
        chk(f"{d} has no positive class (benign reading)", s2.get("n_unacceptable", 0), 0, 0)

    print("\n--- sections 7 and 8: unchanged by the review round ---")
    def l1row(flt, sev, key):
        return med([r for r in l1 if r["fault"] == flt
                    and abs(r["severity"] - sev) < 1e-9], key)
    chk("L1 translation 0.1 px relative RMSE", l1row("X1_translation_px", 0.1,
                                                     "image_relative_rmse"), 0.1681, 0.005)
    chk("L1 translation 0.1 px delta-B is zero",
        l1row("X1_translation_px", 0.1, "std_delta_b_a2"), 0.0, 1e-12)
    chk("L1 jitter 0.4 px delta-B", l1row("X2_jitter_sigma_px", 0.4, "std_delta_b_a2"),
        9.911, 0.01)
    chk("L1 applied 5 A^2 recovered", l1row("X5_applied_delta_b_a2", 5.0,
                                            "std_delta_b_a2"), 5.004, 0.005)
    r0 = l1row("X2_jitter_sigma_px", 0.02, "image_relative_rmse")
    b0 = l1row("X2_jitter_sigma_px", 0.02, "std_delta_b_a2")
    chk("delta-B at relative RMSE 0.001 (jitter extrapolation)", b0 * (0.001 / r0), 0.017, 0.10)

    def l3cell(label, key):
        v = [abs(A.get(r, key)) for r in l3 if r.get("label") == label
             and A.get(r, key) is not None]
        return max(v) if v else float("nan")
    chk("L3 translated movie relative RMSE", l3cell("mov_shift2_gplus",
                                                    "image_relative_rmse"), 1.399, 0.005)
    chk("L3 translated movie recovered shift", l3cell("mov_shift2_gplus",
                                                      "std_shift_px"), 2.850, 0.01)
    chk("L3 translated movie trajectory error is zero",
        l3cell("mov_shift2_gplus", "traj_max_shift_error"), 0.0, 1e-12)
    chk("L3 gain 1 ppm relative RMSE", l3cell("gain_1e-06",
                                              "image_relative_rmse"), 2.037e-3, 0.01)
    chk("L3 dose 0.5 delta-B", l3cell("dose_0.5", "std_delta_b_a2"), 3.560, 0.002)

    print("\n--- section 10.4.1: boundary sensitivity and the three disclosures ---")
    hold = [r for r in allr if A.joint_split(r) == "holdout"]
    s10 = A.separation(sel, "std_delta_b_a2", "harm_delta_b_a2", 10.0, floors)
    chk("separable at the 10 A^2 boundary", 1.0 if s10.get("separable") else 0.0, 1.0, 0)
    chk("theta at the 10 A^2 boundary", s10["threshold"], 5.722, 0.01)
    h10 = A.apply_threshold(hold, "std_delta_b_a2", s10["threshold"],
                            "harm_delta_b_a2", 10.0, floors)
    chk("hold-out FN rate at the 10 A^2 boundary", h10["fn_rate"], 0.112, 0.02)
    chk("frozen rule verdict at 10 A^2 is warning, not blocking",
        1.0 if A.classify(s10, h10, floors.get("std_delta_b_a2", 0.0) or 0.0) == "warning"
        else 0.0, 1.0, 0)
    chk("cells tiered from a rejected fit",
        sum(1 for r in allr if A.harm_tiered_from_rejected_fit(r, "harm_delta_b_a2")), 301, 0)
    chk("Layer 1 cells in the joint hold-out (structurally zero)",
        sum(1 for r in l1 if A.joint_split(r) == "holdout"), 0, 0)
    chk("rejected fits over the whole corpus",
        sum(1 for r in allr if A.get(r, "std_delta_b_a2") is not None
            and not A.envelope_measurable(r)), 757, 0)
    x6 = [r for r in l2 if A.fault_of(r) == "X6_dose_scale"]
    chk("gate-side R^2 maximum on the dose arm",
        max(r["std_fit_r2"] for r in x6), 0.8361, 0.001)

    print(f"\n{sum(OK)}/{len(OK)} checks passed")
    return 0 if all(OK) else 1


if __name__ == "__main__":
    raise SystemExit(main())
