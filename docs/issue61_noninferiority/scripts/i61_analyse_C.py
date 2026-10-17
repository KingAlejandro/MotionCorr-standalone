#!/usr/bin/env python3
"""Issue 61 Stage C analysis: normal auto-refinement, paired by random seed.

The unit of replication here is the SEED, not the movie: three seed-matched
refinements per arm.  This is an explicitly under-powered secondary analysis and
is reported as such.
"""
import json, math, os, re, sys
import numpy as np
from scipy.stats import t as tdist

ROOT = "/home/alex/mc-issue61"
ARMS = ["cpu", "default", "allfftw"]
SEEDS = [61, 62, 63]
MARGIN_C1 = 0.05      # A, non-inferiority on d143
MARGIN_C2 = -10.0     # A^2, supportive


def general(path):
    out = {}
    for line in open(path):
        f = line.split()
        if len(f) == 2 and f[0].startswith("_rln"):
            out[f[0]] = f[1]
        if line.strip().startswith("data_fsc"):
            break
    return out


res = {"seeds": SEEDS, "margins": {"C1_d143_A": MARGIN_C1, "C2_bfactor_A2": MARGIN_C2},
       "note": "unit of replication is the random seed (n=3), not the movie",
       "per_run": {}, "uncontrolled_seed_pass": {}, "arms": {}}

for a in ARMS:
    p = f"{ROOT}/pp/{a}/refine_held22.star"
    if os.path.exists(p):
        g = general(p)
        res["uncontrolled_seed_pass"][a] = {
            "d143_A": float(g["_rlnFinalResolution"]),
            "bfactor_A2": float(g["_rlnBfactorUsedForSharpening"])}
    res["per_run"][a] = {}
    for s in SEEDS:
        p = f"{ROOT}/pp/{a}/refine_held22_s{s}.star"
        if not os.path.exists(p):
            continue
        g = general(p)
        res["per_run"][a][str(s)] = {
            "d143_A": float(g["_rlnFinalResolution"]),
            "bfactor_A2": float(g["_rlnBfactorUsedForSharpening"])}

avail = [s for s in SEEDS if all(str(s) in res["per_run"][a] for a in ARMS)]
res["seeds_complete"] = avail

for a in ARMS:
    vals = [res["per_run"][a][str(s)]["d143_A"] for s in avail]
    res["arms"].setdefault(a, {})["d143_by_seed"] = vals
    res["arms"][a]["d143_seed_spread_A"] = float(max(vals) - min(vals)) if vals else None
    bv = [res["per_run"][a][str(s)]["bfactor_A2"] for s in avail]
    res["arms"][a]["bfactor_by_seed"] = bv
    res["arms"][a]["bfactor_seed_spread_A2"] = float(max(bv) - min(bv)) if bv else None

within = [res["arms"][a]["d143_seed_spread_A"] for a in ARMS if res["arms"][a]["d143_seed_spread_A"] is not None]
res["within_arm_seed_spread_max_A"] = float(max(within)) if within else None

for a in ARMS[1:]:
    d = [res["per_run"][a][str(s)]["d143_A"] - res["per_run"]["cpu"][str(s)]["d143_A"] for s in avail]
    b = [res["per_run"][a][str(s)]["bfactor_A2"] - res["per_run"]["cpu"][str(s)]["bfactor_A2"] for s in avail]
    n = len(d)
    e = {"C1_d143_delta_by_seed_A": d, "C2_bfactor_delta_by_seed_A2": b, "n_seeds": n}
    if n >= 2:
        m, sd = float(np.mean(d)), float(np.std(d, ddof=1))
        se = sd / math.sqrt(n)
        tc = float(tdist.ppf(0.95, n - 1))
        e["C1_mean_delta_A"] = m
        e["C1_upper95_one_sided_A"] = m + tc * se
        e["C1_verdict"] = ("PASS" if m + tc * se <= MARGIN_C1 else
                           "FAIL" if m - tc * se > MARGIN_C1 else "INCONCLUSIVE")
        mb, sdb = float(np.mean(b)), float(np.std(b, ddof=1))
        seb = sdb / math.sqrt(n)
        e["C2_mean_delta_A2"] = mb
        e["C2_lower95_one_sided_A2"] = mb - tc * seb
        e["C2_verdict"] = ("PASS" if mb - tc * seb >= MARGIN_C2 else
                           "FAIL" if mb + tc * seb < MARGIN_C2 else "INCONCLUSIVE")
    res["arms"][a].update(e)

json.dump(res, open(f"{ROOT}/results/stageC_refinement.json", "w"), indent=1, sort_keys=True)

print("Stage C - independent auto-refinement, held-out 22 movies (4095 particles)")
print(f"{'arm':10s} " + " ".join(f"seed{s:>3d}" for s in avail) + "   spread   uncontrolled-seed run")
for a in ARMS:
    v = " ".join(f"{res['per_run'][a][str(s)]['d143_A']:7.3f}" for s in avail)
    u = res["uncontrolled_seed_pass"].get(a, {}).get("d143_A")
    print(f"{a:10s} {v}  {res['arms'][a]['d143_seed_spread_A']:7.3f}   {u}")
print()
print(f"within-arm seed-driven spread in d143: up to {res['within_arm_seed_spread_max_A']:.3f} A")
print()
for a in ARMS[1:]:
    e = res["arms"][a]
    if "C1_mean_delta_A" in e:
        print(f"{a:10s} C1 d143 delta by seed {['%+.3f'%x for x in e['C1_d143_delta_by_seed_A']]} "
              f"mean={e['C1_mean_delta_A']:+.4f} upper95={e['C1_upper95_one_sided_A']:+.4f} "
              f"margin=+{MARGIN_C1} -> {e['C1_verdict']}")
        print(f"{'':10s} C2 Bsharp delta by seed {['%+.2f'%x for x in e['C2_bfactor_delta_by_seed_A2']]} "
              f"mean={e['C2_mean_delta_A2']:+.3f} lower95={e['C2_lower95_one_sided_A2']:+.3f} "
              f"margin={MARGIN_C2} -> {e['C2_verdict']}")
