#!/usr/bin/env python3
"""Issue 61 Stage B analysis: matched-orientation reconstruction endpoints.

B1 (primary): rho = median over qualifying shells of SSNR_arm/SSNR_cpu.
B2          : resolution at FSC = 0.143 (RELION's reported value).
B3          : auto sharpening B-factor.
Uncertainty : delete-one-movie jackknife over the 22 held-out movies.
"""
import glob, json, math, os, sys
import numpy as np
from scipy.stats import t as tdist

ROOT = "/home/alex/mc-issue61"
REAL = ["cpu", "default", "allfftw"]
CTRL = ["ctrl_noise_f005", "ctrl_noise_f020", "ctrl_envelope_b20"]
ALL = REAL + CTRL
BAND = (8.0, 3.0)          # Angstrom, inclusive
FSC_FLOOR = 0.143          # qualifying shells need FSC_cpu >= this
MIN_SHELLS = 20
MARGIN = {"B1_rho": 0.95, "B2_d143_A": 0.05, "B3_bfactor_A2": -10.0}
FSC_COL_PRIMARY = "_rlnFourierShellCorrelationCorrected"
FSC_COL_ALT = "_rlnFourierShellCorrelationUnmaskedMaps"


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
            arr = np.array(rows)
            out["fsc"] = {c: arr[:, n] for n, c in enumerate(cols)}
            i = k
            continue
        i += 1
    return out


def ssnr(fsc):
    f = np.clip(fsc, -0.999, 0.999)
    return 2.0 * f / (1.0 - f)


def rho(pp_arm, pp_cpu, col):
    d = pp_cpu["fsc"]["_rlnAngstromResolution"]
    fc = pp_cpu["fsc"][col]
    fa = pp_arm["fsc"][col]
    q = (d <= BAND[0]) & (d >= BAND[1]) & (fc >= FSC_FLOOR)
    n = int(q.sum())
    if n < MIN_SHELLS:
        return None, n, 0
    r = ssnr(fa[q]) / ssnr(fc[q])
    return float(np.median(r)), n, int((fa[q] < 0).sum())


def load(arm, name):
    p = f"{ROOT}/pp/{arm}/{name}.star"
    return parse_pp(p) if os.path.exists(p) else None


def jk_bounds(theta_full, theta_reps):
    n = len(theta_reps)
    tr = np.asarray(theta_reps, float)
    mean = tr.mean()
    se = math.sqrt((n - 1) / n * np.sum((tr - mean) ** 2))
    tc = float(tdist.ppf(0.95, n - 1))
    bias = (n - 1) * (mean - theta_full)
    return {"jackknife_n": n, "jackknife_se": se,
            "jackknife_bias_estimate": bias,
            "lower95_one_sided": theta_full - tc * se,
            "upper95_one_sided": theta_full + tc * se,
            "ci95_two_sided": [theta_full - float(tdist.ppf(0.975, n - 1)) * se,
                               theta_full + float(tdist.ppf(0.975, n - 1)) * se]}


held = sorted({os.path.basename(p)[3:-5]
               for p in glob.glob(f"{ROOT}/pp/cpu/jk_*.star")})
res = {"band_A": BAND, "fsc_floor": FSC_FLOOR, "min_shells": MIN_SHELLS,
       "margins": MARGIN, "held_out_movies": held,
       "fsc_column_primary": FSC_COL_PRIMARY, "fsc_column_alt": FSC_COL_ALT,
       "arms": {}, "point_estimates": {}}

pp = {a: {n: load(a, n) for n in
          ["all24", "held22"] + [f"jk_{m}" for m in held]} for a in ALL}

for a in ALL:
    res["point_estimates"][a] = {}
    for s in ("all24", "held22"):
        g = pp[a][s]
        if g is None:
            continue
        res["point_estimates"][a][s] = {
            "d143_A": float(g["general"]["_rlnFinalResolution"]),
            "bfactor_A2": float(g["general"]["_rlnBfactorUsedForSharpening"]),
        }

for a in ALL:
    if a == "cpu":
        continue
    res["arms"][a] = {}
    for s in ("held22", "all24"):
        if pp[a].get(s) is None or pp["cpu"].get(s) is None:
            continue
        entry = {}
        for tag, col in (("primary_corrected", FSC_COL_PRIMARY), ("alt_unmasked", FSC_COL_ALT)):
            r, nsh, nneg = rho(pp[a][s], pp["cpu"][s], col)
            entry[f"B1_rho_{tag}"] = {"value": r, "n_shells": nsh, "n_negative_arm_fsc": nneg}
        entry["B2_d143_delta_A"] = (res["point_estimates"][a][s]["d143_A"]
                                    - res["point_estimates"]["cpu"][s]["d143_A"])
        entry["B3_bfactor_delta_A2"] = (res["point_estimates"][a][s]["bfactor_A2"]
                                        - res["point_estimates"]["cpu"][s]["bfactor_A2"])
        res["arms"][a][s] = entry

    # delete-one-movie jackknife, held-out set only, real arms only
    if all(pp[a].get(f"jk_{m}") for m in held) and all(pp["cpu"].get(f"jk_{m}") for m in held):
        reps = {"B1_rho_primary_corrected": [], "B1_rho_alt_unmasked": [],
                "B2_d143_delta_A": [], "B3_bfactor_delta_A2": []}
        for m in held:
            k = f"jk_{m}"
            reps["B1_rho_primary_corrected"].append(rho(pp[a][k], pp["cpu"][k], FSC_COL_PRIMARY)[0])
            reps["B1_rho_alt_unmasked"].append(rho(pp[a][k], pp["cpu"][k], FSC_COL_ALT)[0])
            reps["B2_d143_delta_A"].append(float(pp[a][k]["general"]["_rlnFinalResolution"])
                                           - float(pp["cpu"][k]["general"]["_rlnFinalResolution"]))
            reps["B3_bfactor_delta_A2"].append(float(pp[a][k]["general"]["_rlnBfactorUsedForSharpening"])
                                               - float(pp["cpu"][k]["general"]["_rlnBfactorUsedForSharpening"]))
        jk = {}
        full = res["arms"][a]["held22"]
        for key, vals in reps.items():
            if any(v is None for v in vals):
                jk[key] = {"error": "some replicates had too few qualifying shells"}
                continue
            pt = (full[key]["value"] if key.startswith("B1") else full[key])
            b = jk_bounds(pt, vals)
            b["point_estimate"] = pt
            b["replicates"] = vals
            if key.startswith("B1"):
                b["margin"] = MARGIN["B1_rho"]
                b["verdict"] = ("PASS" if b["lower95_one_sided"] >= MARGIN["B1_rho"] else
                                "FAIL" if b["upper95_one_sided"] < MARGIN["B1_rho"] else "INCONCLUSIVE")
                b["rule"] = f"lower one-sided 95% bound of rho >= {MARGIN['B1_rho']}"
            elif key.startswith("B2"):
                b["margin"] = MARGIN["B2_d143_A"]
                b["verdict"] = ("PASS" if b["upper95_one_sided"] <= MARGIN["B2_d143_A"] else
                                "FAIL" if b["lower95_one_sided"] > MARGIN["B2_d143_A"] else "INCONCLUSIVE")
                b["rule"] = f"upper one-sided 95% bound of (arm-cpu) <= {MARGIN['B2_d143_A']} A"
            else:
                b["margin"] = MARGIN["B3_bfactor_A2"]
                b["verdict"] = ("PASS" if b["lower95_one_sided"] >= MARGIN["B3_bfactor_A2"] else
                                "FAIL" if b["upper95_one_sided"] < MARGIN["B3_bfactor_A2"] else "INCONCLUSIVE")
                b["rule"] = f"lower one-sided 95% bound of (arm-cpu) >= {MARGIN['B3_bfactor_A2']} A^2"
            jk[key] = b
        res["arms"][a]["held22_jackknife"] = jk

json.dump(res, open(f"{ROOT}/results/stageB_reconstruction.json", "w"), indent=1, sort_keys=True,
          default=lambda o: None if o is None else float(o))

print("point estimates (matched-orientation reconstruction)")
print(f"{'arm':18s} {'set':7s} {'d143 A':>8s} {'Bsharp':>9s}")
for a in ALL:
    for s in ("held22", "all24"):
        pe = res["point_estimates"].get(a, {}).get(s)
        if pe:
            print(f"{a:18s} {s:7s} {pe['d143_A']:8.3f} {pe['bfactor_A2']:9.2f}")
print()
print(f"{'arm':18s} {'endpoint':28s} {'point':>9s} {'95% bound':>10s} {'margin':>8s}  verdict")
for a in ALL:
    if a == "cpu":
        continue
    jk = res["arms"][a].get("held22_jackknife")
    if not jk:
        e = res["arms"][a].get("held22", {})
        r = e.get("B1_rho_primary_corrected", {}).get("value")
        print(f"{a:18s} {'B1_rho (no jackknife)':28s} {r if r is None else round(r,5)!s:>9s} "
              f"{'-':>10s} {MARGIN['B1_rho']:8.2f}  POINT-ONLY")
        continue
    for k, v in jk.items():
        if "error" in v:
            print(f"{a:18s} {k:28s}  {v['error']}")
            continue
        b = v["lower95_one_sided"] if "B1" in k or "B3" in k else v["upper95_one_sided"]
        print(f"{a:18s} {k:28s} {v['point_estimate']:9.5f} {b:10.5f} {v['margin']:8.2f}  {v['verdict']}")
