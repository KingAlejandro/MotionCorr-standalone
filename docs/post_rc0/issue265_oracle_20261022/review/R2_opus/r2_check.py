# R2 bounded checks: new tokens cited in f4fc5172 and worst-sample tie claims.
import csv, sys, json
P, S = sys.argv[1], sys.argv[2]
out = {}
rows = list(csv.DictReader(open(P + "/receipts/iteration2/coefficients.csv")))
def get(fx, dim, k, route="real-write-read"):
    for r in rows:
        if r["fixture"].startswith(fx) and r["route"] == route and r["dim"] == dim and int(r["coeff_in_dim"]) == k:
            return r
tok = {}
for fx, dim, k in [("F02","X",1),("F02","X",4),("F02","X",2),("F02","X",8),("F02","X",5),("F02","X",11)]:
    r = get(fx, dim, k); tok[f"{fx}{dim}{k}"] = (r["pre_write"], r["written_token"], r["abs_err"])
for r in rows:
    if r["route"] == "real-write-read" and r["pre_write"] in ("123456.789", "-0.00122271287007", "100000.1234567", "-100000.5", "100000.5", "-99999.99999995"):
        tok[r["fixture"] + ":" + r["dim"] + r["coeff_in_dim"]] = (r["pre_write"], r["written_token"], r["abs_err"], r["bit_equal"])
out["tokens"] = tok
# F02 scientific-branch abs errors (|pre|<0.001 nonzero, or >1e5), any dim
sci = []
for r in rows:
    if r["fixture"].startswith("F02") and r["route"] == "real-write-read":
        v = float(r["pre_write"])
        if v != 0 and (abs(v) < 1e-3 or abs(v) > 1e5):
            sci.append((r["dim"] + r["coeff_in_dim"], r["pre_write"], r["written_token"], float(r["abs_err"])))
out["F02_scientific"] = sci
# ties of worst sample per real-write-read case
best = {}
for r in csv.DictReader(open(S + "/out/run/samples_full.csv")):
    c = r["case"]
    if "fullprecision" in c: continue
    e = float(r["err_vec"])
    b = best.setdefault(c, [-1.0, []])
    if e > b[0]: best[c] = [e, [(r["geometry"], r["frame"], r["px"], r["py"])]]
    elif e == b[0]: b[1].append((r["geometry"], r["frame"], r["px"], r["py"]))
out["ties"] = {c: {"max": v[0], "n": len(v[1]), "first": v[1][0], "locs": v[1][:4]} for c, v in best.items()}
json.dump(out, sys.stdout, indent=1)
