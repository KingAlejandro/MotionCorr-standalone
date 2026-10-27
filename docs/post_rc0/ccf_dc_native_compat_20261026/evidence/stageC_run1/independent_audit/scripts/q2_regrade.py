"""Q2: own-basis re-score of every K row with a runtime tap, against hash-verified local truth fields.

Field from the C++ ThirdOrderPolynomialModel::getShiftAt term order (src), u = x/nx - .5, v = y/ny - .5,
z = frame index, plus the runtime global shift. Metrics: |field - truth| x 0.885 A over frames x ROI rows
12:84, cols 12:116; PASS iff rms <= .20, p95 <= .40, max <= .80; flat/repeated -> UNIDENTIFIABLE.
Does not import the repo grader. STAR files and N truths are not local, so only the tap representation of
K rows is re-scored. Also: truth-free CPU-vs-CUDA tap field differences for the evaluated CUDA pairs."""
import sys, os, json, hashlib
import numpy as np
X, LOC, PAIRS, OUT = sys.argv[1:5]
R = os.path.join(X, "runs", "runs")
loc = json.load(open(LOC))["found_paths"]
NX, NY, NF, PX = 128, 96, 5, 0.885
Y0, Y1, X0, X1 = 12, 84, 12, 116

def field_from_tap(t):
    yy, xx = np.mgrid[:NY, :NX].astype(float)
    u, v = xx / NX - .5, yy / NY - .5
    spatial = [np.ones_like(u), u, u * u, v, v * v, u * v]          # coeff groups 0-2, 3-5, ..., 15-17
    out = np.zeros((NF, NY, NX, 2))
    for f in range(NF):
        z = float(f); zt = (z, z * z, z ** 3)
        for a, key in enumerate(("coeff_x", "coeff_y")):
            c = t[key]
            out[f, :, :, a] = sum((c[3 * g] * zt[0] + c[3 * g + 1] * zt[1] + c[3 * g + 2] * zt[2]) * spatial[g] for g in range(6))
            out[f, :, :, a] += t["global"][f][a]
    return out

def metrics(err):
    n = np.sqrt((err ** 2).sum(-1)).ravel() * PX
    return dict(rms=float(np.sqrt(np.mean(n * n))), p95=float(np.percentile(n, 95)), max=float(n.max()))

truth = {}
def get_truth(case):
    if case not in truth:
        p = loc[f"k267/{case}_field.npy"]
        a = np.load(p, allow_pickle=False)
        truth[case] = (a, hashlib.sha256(open(p, "rb").read()).hexdigest())
    return truth[case]

rows, maxdiff = [], 0.0
for j in sorted(os.listdir(R)):
    if "-K-" not in j or not os.path.exists(os.path.join(R, j, "tap.json")): continue
    case = j.split("-")[2]
    row = json.load(open(os.path.join(R, j, "row.json")))
    t = json.load(open(os.path.join(R, j, "tap.json")))
    tr, th = get_truth(case)
    assert tr.shape == (NF, NY, NX, 2), tr.shape
    assert th == row["tap"]["fixture_files"][f"{case}_field.npy"], "truth hash differs from row record"
    fld = field_from_tap(t)
    m = metrics((fld - tr)[:, Y0:Y1, X0:X1])
    ok = m["rms"] <= .20 and m["p95"] <= .40 and m["max"] <= .80
    ver = "UNIDENTIFIABLE" if case in ("flat", "repeated") else ("PASS" if ok else "FAIL")
    prod = row["tap"]["field_angstrom"]
    d = max(abs(m[k] - prod[k]) for k in m)
    maxdiff = max(maxdiff, d)
    rows.append(dict(job=j, own=m, own_verdict=ver, producer=prod, producer_verdict=row["tap"]["accuracy_status"],
                     star_producer=row["star"]["field_angstrom"], star_verdict=row["star"]["accuracy_status"],
                     max_abs_diff_A=d, verdict_match=ver == row["tap"]["accuracy_status"]))

pairs = []
for p in json.load(open(PAIRS)):
    if p.get("status") != "EVALUATED" or p["comparison"] == "C-CPU": continue
    fa = field_from_tap(json.load(open(os.path.join(R, p["job_a"], "tap.json"))))
    fb = field_from_tap(json.load(open(os.path.join(R, p["job_b"], "tap.json"))))
    dd = np.sqrt(((fa - fb)[:, Y0:Y1, X0:X1] ** 2).sum(-1))
    pairs.append(dict(comparison=p["comparison"], case=p["case"], a=p["job_a"], b=p["job_b"],
                      field_diff_roi_px=dict(max=float(dd.max()), rms=float(np.sqrt((dd ** 2).mean()))),
                      field_diff_roi_A_max=float(dd.max() * PX)))
res = dict(rows_rescored=len(rows), verdict_mismatches=[r["job"] for r in rows if not r["verdict_match"]],
           max_abs_metric_diff_A=maxdiff, truth_hashes={k: v[1] for k, v in truth.items()},
           verdict_counts={}, rows=rows, cuda_pairs_truth_free=pairs)
import collections
res["verdict_counts"] = {f"{b}/{k}": v for (b, k), v in collections.Counter(
    (("cuda" if "-cuda-" in r["job"] else "cpu"), r["own_verdict"]) for r in rows).items()}
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps({k: res[k] for k in ("rows_rescored", "verdict_mismatches", "max_abs_metric_diff_A", "verdict_counts")}))
for p in pairs: print(p["comparison"], p["case"], p["field_diff_roi_px"])
