#!/usr/bin/env python3
"""Summarise analyze.py outputs: first-separation events per patch, with both
maps' margins between the two backends' selected peaks, and the map/rounding
statistics.  summarize.py <analysis_dir> <case> [<case> ...] > summary.json"""
import json, sys
from pathlib import Path

import numpy as np

NEAR_TIE_ULPS = 16  # both maps' margins at or below this: "near-tie" (see README for the choice)


def main(d, cases):
    d = Path(d)
    out = {}
    for c in cases:
        T = json.load(open(d / f"{c}-traj.json"))
        M = json.load(open(d / f"{c}-maps.json"))
        rows = {(r["patch"], r["iter"]): r for r in M["rows"]}
        case = {"emulation_mismatches": T["cuda_emulation_mismatches"],
                "cuda_frame_iterations": T["cuda_frame_iterations"], "patches": {}, "maps": {}}
        for key, p in T["patches"].items():
            e = {"kind": p["first_separation_kind"], "acceptance_flip": p["acceptance_flip"],
                 "iters": [p["iters_cpu"], p["iters_cuda"]], "converged": [p["converged_cpu"], p["converged_cuda"]],
                 "final_traj_diff_max_px": round(p["final_traj_diff_max_px"], 3)}
            if p["iteration_count_differs"]:
                e["rmsd"] = [p["rmsd_cpu"], p["rmsd_cuda"]]
            fe = p.get("first_event")
            if fe:
                e["iter"] = fe["iter"]
                r = rows.get((key, fe["iter"]), {})
                evm = r.get("events", {})
                e["frames"] = {}
                for f, ev in fe["frames"].items():
                    m = evm.get(f, {})
                    x = {"cpu_sel": ev["cpu_sel"], "cuda_sel": ev["cuda_sel"], "same_peak": ev["same_peak"],
                         "adjacent": ev["adjacent"],
                         "cand_diff_px": round(float(np.hypot(ev["cpu_cur"][0] - ev["cuda_cur"][0], ev["cpu_cur"][1] - ev["cuda_cur"][1])), 3),
                         "cpu_curv_ulps": ev["cpu_curv_ulps"], "cuda_curv_ulps": ev["cuda_curv_ulps"],
                         "cpu_max": ev["cpu_max"]}
                    if m:
                        x.update({k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()
                                  if k not in ("cpu_sel", "cuda_sel")})
                        if not ev["same_peak"]:
                            x["near_tie"] = max(m["cpu_map_margin_ulps"], m["cuda_map_margin_ulps"]) <= NEAR_TIE_ULPS
                    e["frames"][f] = x
            case["patches"][key] = e
        # Map statistics over all compared patch iterations (not global).
        prow = [r for r in M["rows"] if r["patch"] != "global"]
        grow = [r for r in M["rows"] if r["patch"] == "global"]
        agg = lambda rs, k, i: float(max(r[k][i] for r in rs)) if rs else None
        med = lambda rs, k: float(np.median([r[k][0] for r in rs])) if rs else None
        for name, rs in (("patches", prow), ("global", grow)):
            case["maps"][name] = {
                "n_iter_rows": len(rs),
                "comp_cpu_f32_vs_f64_rel_max": agg(rs, "cpu_f32_vs_f64_own", 1),
                "comp_cuda_f32_vs_f64_rel_max": agg(rs, "cuda_f32_vs_f64_own", 1),
                "comp_cpu_max_ulps_at_peak": float(max(r["cpu_comp_max_ulps_at_peak"] for r in rs)) if rs else None,
                "comp_cuda_max_ulps_at_peak": float(max(r["cuda_comp_max_ulps_at_peak"] for r in rs)) if rs else None,
                "map_cpu_vs_cuda_rel_median": med(rs, "map_cpu_vs_cuda"),
                "map_cpu_vs_cuda_rel_max": agg(rs, "map_cpu_vs_cuda", 1),
                "f64_maps_from_the_two_inputs_rel_max": agg(rs, "f64_cpu_in_vs_f64_cuda_in", 1),
                "input_rel_diff_median": med(rs, "input_cpu_vs_cuda"),
                "D_offset_ulps_max": agg(rs, "D_offset_ulps", 1),
                "D_local_max_ulps_median": med(rs, "D_local_max_ulps"),
                "D_local_max_ulps_max": agg(rs, "D_local_max_ulps", 1),
                "it1_D_local_max_ulps_max": float(max([r["D_local_max_ulps"][1] for r in rs if r["iter"] == 1] or [0])),
            }
            it1 = [r for r in rs if r["iter"] == 1]
            if it1:
                case["maps"][name]["it1_input_rel_diff_max"] = float(max(r["input_cpu_vs_cuda"][1] for r in it1))
                case["maps"][name]["it1_map_rel_diff_max"] = float(max(r["map_cpu_vs_cuda"][1] for r in it1))
            rt = [r["input_ramp_test_global_shift_diff"] for r in it1 if "input_ramp_test_global_shift_diff" in r]
            if rt:
                case["maps"][name]["it1_ramp_test"] = {
                    "frame1_input_rel_diff_max": max(x["frame1_input_rel_diff"] for x in rt),
                    "corr_input_diff_vs_global_shift_diff_median": float(np.median([x["corr_input_diff_vs_global_shift_diff"] for x in rt])),
                    "before_median": float(np.median([x["before"][0] for x in rt])),
                    "after_median": float(np.median([x["after"][0] for x in rt]))}
        st = M.get("shift_tests", {})
        def smax(be, glob):
            v = [x for k, t in st.items() if (k == "global") == glob for x in t[be]]
            return {"n": len(v), "resid_rel_max": max([x["resid_rel_max"] for x in v] or [None]) if v else None,
                    "max_phase_rad": max([x["max_phase_rad"] for x in v]) if v else None}
        case["shift_test"] = {"patches": {"cpu": smax("cpu", False), "cuda": smax("cuda", False)},
                              "global": {"cpu": smax("cpu", True), "cuda": smax("cuda", True)}}
        fa = d / f"{c}-fitattr.json"
        if fa.exists():
            F = json.load(open(fa))
            case["fit_attribution"] = {k: F[k] for k in ("cpu_patches", "cuda_patches", "refit_reproduces_star", "cpu_vs_cuda",
                                                          "cuda_with_all_patches_over_0.25px_from_cpu")}
            case["fit_attribution"]["obs_diff_max_px"] = F["obs_diff_max_px"]
            case["fit_attribution"]["single_swap"] = F["cuda_with_one_patch_from_cpu"]
        out[c] = case
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
