#!/usr/bin/env python3
"""Issue 61 Stage A analysis: paired per-micrograph CTF endpoints.

Unit of replication is the movie.  Confirmatory set = 22 held-out movies.
Margins are those frozen in docs/issue61_noninferiority/PROTOCOL.md.
"""
import json, math, os, sys
import numpy as np

ROOT = "/home/alex/mc-issue61"
REAL = ["cpu", "default", "allfftw"]
CTRL = ["ctrl_noise_f005", "ctrl_noise_f020", "ctrl_envelope_b20"]
ALL = REAL + CTRL
DEV = ["00021", "00046"]
RNG_SEED = 61
NBOOT = 10000

MARGIN = {"CtfMaxResolution": 0.10,      # A, non-inferiority, arm may be at most +0.10 worse
          "DefocusMean": 45.0,           # A, two-sided equivalence (TOST)
          "CtfFigureOfMerit": -0.05}     # relative, non-inferiority


def read_ctf_star(path):
    lines = open(path).read().splitlines()
    i = lines.index("data_micrographs")
    j = i
    while not lines[j].startswith("loop_"):
        j += 1
    k = j + 1
    cols = []
    while lines[k].strip().startswith("_rln"):
        cols.append(lines[k].strip().split()[0])
        k += 1
    out = {}
    for line in lines[k:]:
        if not line.strip():
            continue
        f = line.split()
        rec = dict(zip(cols, f))
        mid = rec["_rlnMicrographName"].split("_")[-2]
        out[mid] = {
            "DefocusU": float(rec["_rlnDefocusU"]),
            "DefocusV": float(rec["_rlnDefocusV"]),
            "DefocusMean": 0.5 * (float(rec["_rlnDefocusU"]) + float(rec["_rlnDefocusV"])),
            "CtfAstigmatism": float(rec["_rlnCtfAstigmatism"]),
            "CtfFigureOfMerit": float(rec["_rlnCtfFigureOfMerit"]),
            "CtfMaxResolution": float(rec["_rlnCtfMaxResolution"]),
        }
    return out


def bca_ci(x, stat, alpha, rng, nboot=NBOOT):
    """BCa bootstrap interval for a 1-D paired-difference sample."""
    x = np.asarray(x, float)
    n = len(x)
    t0 = stat(x)
    idx = rng.integers(0, n, size=(nboot, n))
    boots = np.array([stat(x[i]) for i in idx])
    prop = np.mean(boots < t0)
    prop = min(max(prop, 1.0 / nboot), 1 - 1.0 / nboot)
    from scipy.stats import norm
    z0 = norm.ppf(prop)
    jk = np.array([stat(np.delete(x, i)) for i in range(n)])
    jbar = jk.mean()
    num = np.sum((jbar - jk) ** 3)
    den = 6.0 * (np.sum((jbar - jk) ** 2) ** 1.5)
    a = num / den if den != 0 else 0.0

    def pct(al):
        z = norm.ppf(al)
        adj = norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        return float(np.percentile(boots, 100 * adj))
    return t0, pct, boots


def summarise(diffs, margin, direction, label, rng):
    """direction: 'lower_is_better' (endpoint worse when diff>0) or 'higher_is_better'."""
    from scipy.stats import norm, t as tdist
    x = np.asarray(diffs, float)
    n = len(x)
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    se = sd / math.sqrt(n)
    tcrit95_1s = float(tdist.ppf(0.95, n - 1))
    tcrit975 = float(tdist.ppf(0.975, n - 1))
    t0, pct, boots = bca_ci(x, lambda a: a.mean(), 0.05, rng)
    res = {"n": n, "paired_mean_diff": mean, "sd": sd, "se": se,
           "t_ci95_two_sided": [mean - tcrit975 * se, mean + tcrit975 * se],
           "bca_ci95_two_sided": [pct(0.025), pct(0.975)],
           "bca_ci90_two_sided": [pct(0.05), pct(0.95)],
           "bca_upper95_one_sided": pct(0.95),
           "bca_lower95_one_sided": pct(0.05),
           "t_upper95_one_sided": mean + tcrit95_1s * se,
           "t_lower95_one_sided": mean - tcrit95_1s * se,
           "margin": margin, "label": label}
    if direction == "lower_is_better":
        ub = res["bca_upper95_one_sided"]
        res["verdict"] = ("PASS" if ub <= margin else
                          "FAIL" if res["bca_lower95_one_sided"] > margin else "INCONCLUSIVE")
        res["rule"] = f"upper one-sided 95% bound of (arm - cpu) <= {margin}"
    elif direction == "higher_is_better":
        lb = res["bca_lower95_one_sided"]
        res["verdict"] = ("PASS" if lb >= margin else
                          "FAIL" if res["bca_upper95_one_sided"] < margin else "INCONCLUSIVE")
        res["rule"] = f"lower one-sided 95% bound of (arm - cpu) >= {margin}"
    else:  # two-sided equivalence, TOST at 90%
        lo, hi = res["bca_ci90_two_sided"]
        res["verdict"] = ("PASS" if (lo > -margin and hi < margin) else
                          "FAIL" if (lo > margin or hi < -margin) else "INCONCLUSIVE")
        res["rule"] = f"two-sided 90% CI of (arm - cpu) inside +/-{margin} (TOST)"
    return res


data = {a: read_ctf_star(f"{ROOT}/proj/{a}/CtfFind61/micrographs_ctf.star") for a in ALL}
mids = sorted(data["cpu"])
held = [m for m in mids if m not in DEV]
out = {"per_micrograph": data, "held_out_movies": held, "development_movies": DEV,
       "margins": MARGIN, "bootstrap": {"n": NBOOT, "seed": RNG_SEED, "method": "paired BCa over movies"},
       "endpoints": {}}

for arm in ALL[1:]:
    out["endpoints"][arm] = {}
    for aset, ms in (("held22", held), ("all24", mids)):
        rng = np.random.default_rng(RNG_SEED)
        e = {}
        d = [data[arm][m]["CtfMaxResolution"] - data["cpu"][m]["CtfMaxResolution"] for m in ms]
        e["A1_CtfMaxResolution_A"] = summarise(d, MARGIN["CtfMaxResolution"], "lower_is_better",
                                               "arm - cpu (A); positive = worse", rng)
        rng = np.random.default_rng(RNG_SEED + 1)
        d = [data[arm][m]["DefocusMean"] - data["cpu"][m]["DefocusMean"] for m in ms]
        e["A2_DefocusMean_A"] = summarise(d, MARGIN["DefocusMean"], "two_sided",
                                          "arm - cpu (A)", rng)
        rng = np.random.default_rng(RNG_SEED + 2)
        d = [(data[arm][m]["CtfFigureOfMerit"] - data["cpu"][m]["CtfFigureOfMerit"])
             / data["cpu"][m]["CtfFigureOfMerit"] for m in ms]
        e["A3_CtfFigureOfMerit_rel"] = summarise(d, MARGIN["CtfFigureOfMerit"], "higher_is_better",
                                                 "(arm - cpu)/cpu, relative", rng)
        out["endpoints"][arm][aset] = e

json.dump(out, open(f"{ROOT}/results/stageA_ctf.json", "w"), indent=1, sort_keys=True)

print(f"{'arm':18s} {'set':7s} {'endpoint':26s} {'mean diff':>12s} {'95% bound':>12s} {'margin':>9s}  verdict")
for arm in ALL[1:]:
    for aset in ("held22", "all24"):
        for k, v in out["endpoints"][arm][aset].items():
            if "A2" in k:
                b = "[%.1f, %.1f]" % tuple(v["bca_ci90_two_sided"])
            elif "A3" in k:
                b = "%.5f" % v["bca_lower95_one_sided"]
            else:
                b = "%.5f" % v["bca_upper95_one_sided"]
            print(f"{arm:18s} {aset:7s} {k:26s} {v['paired_mean_diff']:12.5f} {b:>12s} "
                  f"{v['margin']:9.3f}  {v['verdict']}")
