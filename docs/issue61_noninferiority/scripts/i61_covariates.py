#!/usr/bin/env python3
"""Issue 61: harvest the Gate 2 image-agreement covariates from Issue #36's comparator output.

Descriptive only.  No verdict is derived from these numbers.
"""
import glob, json, os
import numpy as np
C = "/home/alex/MotionCorr-issue36-full24/comparisons"
DEV = ["00021", "00046"]
out = {"source": C, "note": "descriptive covariate; not an endpoint", "arms": {}}
for arm in ("default", "allfftw"):
    per = {}
    for p in sorted(glob.glob(f"{C}/{arm}/*.json")):
        mid = os.path.basename(p)[:-5]
        d = json.load(open(p))
        rec = {"overall_status": d.get("overall_status")}
        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}" if path else k)
        for k, v in (d.get("checks") or {}).items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if isinstance(vv, (int, float)) and any(t in kk.lower() for t in
                                                            ("rmse", "max_", "shift", "traj")):
                        rec[f"{k}.{kk}"] = vv
        per[mid] = rec
    keys = sorted({k for r in per.values() for k in r if k != "overall_status"})
    summ = {}
    for k in keys:
        held = [per[m][k] for m in per if m not in DEV and k in per[m]]
        allv = [per[m][k] for m in per if k in per[m]]
        if held and all(isinstance(x, (int, float)) for x in held):
            summ[k] = {"held22_median": float(np.median(held)),
                       "held22_min": float(np.min(held)), "held22_max": float(np.max(held)),
                       "all24_median": float(np.median(allv))}
    out["arms"][arm] = {"per_movie": per, "summary": summ}
json.dump(out, open("/home/alex/mc-issue61/results/gate2_covariates.json", "w"),
          indent=1, sort_keys=True)
for arm in out["arms"]:
    print(arm)
    for k, v in out["arms"][arm]["summary"].items():
        print(f"   {k:44s} held22 median={v['held22_median']:.6g} range=[{v['held22_min']:.6g}, {v['held22_max']:.6g}]")
