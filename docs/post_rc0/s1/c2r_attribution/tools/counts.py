#!/usr/bin/env python3
"""Counts and the per-patch first-separation table from summary.json.
  counts.py summary.json > counts.json   (also prints a markdown table)"""
import json, sys

S = json.load(open(sys.argv[1]))
out = {}
lines = ["| case | patch | S1-relevant | acceptance CPU/CUDA | iters | final traj diff px | first separation | frame: CPU pick / CUDA pick, margin CPU map / CUDA map (ulps), cand. diff px |",
         "|---|---|---|---|---|---:|---|---|"]
for c, v in S.items():
    n = {"patches_with_first_event": 0, "events": 0, "int_peak_near_tie_le16": 0, "int_peak_17_to_68": 0,
         "int_peak_adjacent": 0, "same_peak_subpixel": 0, "iteration_count_only": 0, "max_margin_ulps": 0,
         "cuda_map_exact_tie": 0, "cuda_map_exact_tie_cpu_rule_matches_cpu": 0, "s1_relevant_patches": []}
    for k, p in v["patches"].items():
        if k == "global":
            continue
        # S1-relevant: reaches the fit on at least one backend, and either the
        # acceptance differs or the trajectories differ by more than 1 px.
        rel = any(p["converged"]) and (p["acceptance_flip"] or p["final_traj_diff_max_px"] > 1.0)
        if p["kind"].startswith("no frame event"):
            n["iteration_count_only"] += 1
        fr = p.get("frames", {})
        if fr:
            n["patches_with_first_event"] += 1
        cells = []
        for f, x in fr.items():
            n["events"] += 1
            if x["same_peak"]:
                n["same_peak_subpixel"] += 1
                cells.append("%s: same peak %s, %.2f" % (f, tuple(x["cpu_sel"]), x["cand_diff_px"]))
                continue
            mc, mg = x["cpu_map_margin_ulps"], x["cuda_map_margin_ulps"]
            n["max_margin_ulps"] = max(n["max_margin_ulps"], mc, mg)
            n["int_peak_near_tie_le16" if max(mc, mg) <= 16 else "int_peak_17_to_68"] += 1
            n["int_peak_adjacent"] += bool(x["adjacent"])
            note = ""
            if mg == 0:  # equal values on the CUDA map: CUDA's lane tie rule (#70) decided
                n["cuda_map_exact_tie"] += 1
                # CPU's rule keeps the first maximum in signed-y-then-x order.
                cpu_rule = min((x["cpu_sel"][1], x["cpu_sel"][0]), (x["cuda_sel"][1], x["cuda_sel"][0]))
                if cpu_rule == (x["cpu_sel"][1], x["cpu_sel"][0]):
                    n["cuda_map_exact_tie_cpu_rule_matches_cpu"] += 1
                    note = " [CUDA-map tie; CPU rule would match CPU]"
                else:
                    note = " [CUDA-map tie]"
            cells.append("%s: %s / %s%s, %d / %d, %.2f%s" % (f, tuple(x["cpu_sel"]), tuple(x["cuda_sel"]),
                                                               " (adj.)" if x["adjacent"] else "", mc, mg, x["cand_diff_px"], note))
        if rel:
            n["s1_relevant_patches"].append(k)
        if fr or p["kind"].startswith("no frame event") or rel:
            acc = "/".join("yes" if a else "no" for a in p["converged"])
            first = p["kind"] + (" (it %d)" % p["iter"] if "iter" in p else "")
            if "rmsd" in p:
                first += "; last RMSD %.4f / %.4f" % (p["rmsd"][0][-1], p["rmsd"][1][-1])
            lines.append("| %s | (%s) | %s | %s | %d/%d | %.3f | %s | %s |" % (
                c, k, "**yes**" if rel else "", acc, p["iters"][0], p["iters"][1], p["final_traj_diff_max_px"],
                first, "; ".join(cells)))
    out[c] = n
print("\n".join(lines), file=sys.stderr)
json.dump(out, sys.stdout, indent=1)
