#!/usr/bin/env python3
"""Export half-map FSC curves and per-shell SSNR ratios for every arm (held22 and all24)."""
import json, os
import numpy as np

ROOT = "/home/alex/mc-issue61"
ARMS = ["cpu", "default", "allfftw", "ctrl_noise_f005", "ctrl_noise_f020", "ctrl_envelope_b20"]
COLS = ["_rlnFourierShellCorrelationCorrected", "_rlnFourierShellCorrelationUnmaskedMaps"]


def parse_pp(path):
    lines = open(path).read().splitlines()
    out = {"general": {}, "fsc": {}}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "data_general":
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("data_"):
                f = lines[i].split()
                if len(f) == 2 and f[0].startswith("_rln"):
                    out["general"][f[0]] = f[1]
                i += 1
            continue
        if s == "data_fsc":
            j = i
            while not lines[j].strip().startswith("loop_"):
                j += 1
            k = j + 1
            cols = []
            while lines[k].strip().startswith("_rln"):
                cols.append(lines[k].strip().split()[0])
                k += 1
            rows = []
            while k < len(lines) and lines[k].strip() and not lines[k].strip().startswith("data_"):
                rows.append([float(x) for x in lines[k].split()])
                k += 1
            a = np.array(rows)
            out["fsc"] = {c: a[:, n].tolist() for n, c in enumerate(cols)}
            i = k
            continue
        i += 1
    return out


res = {"note": "half-map FSC curves from relion_postprocess; SSNR = 2*FSC/(1-FSC)",
       "sets": {}}
for s in ("held22", "all24"):
    res["sets"][s] = {}
    base = None
    for a in ARMS:
        p = f"{ROOT}/pp/{a}/{s}.star"
        if not os.path.exists(p):
            continue
        d = parse_pp(p)
        entry = {"AngstromResolution": d["fsc"]["_rlnAngstromResolution"],
                 "FinalResolution": float(d["general"]["_rlnFinalResolution"]),
                 "BfactorUsedForSharpening": float(d["general"]["_rlnBfactorUsedForSharpening"]),
                 "RandomiseFrom": d["general"].get("_rlnRandomiseFrom")}
        for c in COLS:
            entry[c] = d["fsc"][c]
        res["sets"][s][a] = entry
    cpu = res["sets"][s].get("cpu")
    if cpu:
        for a in res["sets"][s]:
            if a == "cpu":
                continue
            r = {}
            for c in COLS:
                fa = np.clip(np.array(res["sets"][s][a][c]), -0.999, 0.999)
                fc = np.clip(np.array(cpu[c]), -0.999, 0.999)
                sa, sc = 2 * fa / (1 - fa), 2 * fc / (1 - fc)
                with np.errstate(divide="ignore", invalid="ignore"):
                    r[c] = np.where(np.abs(sc) > 0, sa / sc, np.nan).tolist()
            res["sets"][s][a]["ssnr_ratio_vs_cpu"] = r
json.dump(res, open(f"{ROOT}/results/fsc_curves.json", "w"), indent=1, sort_keys=True,
          default=lambda o: None)

print("randomise-from resolution per arm (must be comparable for the corrected FSC to be comparable):")
for s in ("held22", "all24"):
    print(" ", s, {a: res["sets"][s][a]["RandomiseFrom"] for a in res["sets"][s]})
