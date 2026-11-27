#!/usr/bin/env python3
"""Independent review check for the #265 round-trip oracle packet (bb08502e).

Does not reuse the harness or summarize_receipt.py. From the committed files only:
  1. parses fixtures.txt tokens with Python float() and checks pre_write bits in coefficients.csv;
  2. emulates the RELION formatter rule from src/metadata_table.cpp:252-278 (snprintf(buf,13,"%12.{5,6}{f,e}"))
     and checks it equals the native written_token and the written_star file text;
  3. checks post_read bits == float(written_token) bits (incl. signed zero) and full-precision route bit equality;
  4. recomputes shift error two ways (getShiftAt-order difference, and sum of delta*basis) over the frozen grid
     and compares per-range and per-frame maxima and the worst-sample location against summary.json / per_frame csv;
  5. recomputes K3 from the injected file text.
"""
import csv, json, math, struct, sys, os
import numpy as np

PKT = sys.argv[1]
R2 = os.path.join(PKT, "receipts/iteration2")
NC = 18

def bits(v): return struct.unpack("<Q", struct.pack("<d", v))[0]

def load_spec(path):
    spec = {"geoms": [], "fr": [], "extra": [], "ranges": [], "fx": {}, "order": []}
    cur = None
    for line in open(path):
        line = line.rstrip("\n")
        if not line or line.startswith("#"): continue
        t = line.split()
        if t[0] == "GEOMETRY": spec["geoms"].append((t[1], float(t[2]), float(t[3])))
        elif t[0] == "FRACTIONS": spec["fr"] = [float(x) for x in t[1:]]
        elif t[0] == "EXTRA_PIXEL": spec["extra"].append((float(t[1]), float(t[2])))
        elif t[0] == "FRAMES": spec["frames"] = int(t[1])
        elif t[0] == "RANGE": spec["ranges"].append((t[1], int(t[2]), int(t[3])))
        elif t[0] == "FIXTURE":
            cur = line[8:].split("|")[0].strip(); spec["fx"][cur] = {}; spec["order"].append(cur)
        elif t[0] in ("X", "Y"):
            assert len(t) == NC + 1
            spec["fx"][cur][t[0]] = [float(x) for x in t[1:]]
    return spec

def fmt(v):
    a = abs(v)
    if (a > 0 and a < 0.001) or a > 100000.0:
        s = ("%12.5e" if v < 0 else "%12.6e") % v
    else:
        s = ("%12.5f" if v < 0 else "%12.6f") % v
    return s[:12]

def basis(z, x, y):
    # rows: coefficient index 0..17 per ThirdOrderPolynomialModel::getShiftAt
    zs = [z, z * z, z * z * z]
    sp = [np.ones_like(x), x, x * x, y, y * y, x * y]
    return [zs[k] * sp[j] for j in range(6) for k in range(3)]

def shift_getshiftat_order(c, z, x, y):
    x2, y2, xy, z2 = x * x, y * y, x * y, z * z
    z3 = z2 * z
    return ((c[0] * z + c[1] * z2 + c[2] * z3)
            + (c[3] * z + c[4] * z2 + c[5] * z3) * x
            + (c[6] * z + c[7] * z2 + c[8] * z3) * x2
            + (c[9] * z + c[10] * z2 + c[11] * z3) * y
            + (c[12] * z + c[13] * z2 + c[14] * z3) * y2
            + (c[15] * z + c[16] * z2 + c[17] * z3) * xy)

def grid(spec):
    G, F, PX, PY, X, Y = [], [], [], [], [], []
    for gi, (gn, w, h) in enumerate(spec["geoms"]):
        pos = [(fx * (w - 1), fy * (h - 1)) for fy in spec["fr"] for fx in spec["fr"]] + spec["extra"]
        for (px, py) in pos:
            for f in range(spec["frames"]):
                G.append(gi); F.append(f); PX.append(px); PY.append(py); X.append(px / w - 0.5); Y.append(py / h - 0.5)
    return tuple(np.array(a) for a in (G, F, PX, PY, X, Y))

def main():
    spec = load_spec(os.path.join(PKT, "fixtures.txt"))
    G, F, PX, PY, X, Y = grid(spec)
    Z = F.astype(float)
    B = basis(Z, X, Y)
    rows = list(csv.DictReader(open(os.path.join(R2, "coefficients.csv"))))
    summ = json.load(open(os.path.join(R2, "summary.json")))
    pfm = {}
    for r in csv.DictReader(open(os.path.join(R2, "per_frame_max_vec.csv"))):
        pfm[(r["fixture"], r["route"], int(r["frame"]))] = float(r["max_vec_err_px"])
    out = {"problems": [], "fixtures": {}}
    P = out["problems"]
    by = {}
    for r in rows: by.setdefault((r["fixture"], r["route"]), []).append(r)
    for js in summ["fixtures"]:
        name, route = js["fixture"], js["route"]
        fx = spec["fx"][name]
        pre = fx["X"] + fx["Y"]
        rec = {"read_ok": js["read_ok"]}
        if not js["read_ok"]:
            assert (name, route) not in by
            out["fixtures"][f"{name}|{route}"] = rec; continue
        rs = sorted(by[(name, route)], key=lambda r: int(r["coeff_index"]))
        assert len(rs) == 2 * NC
        post = []
        neq = 0; maxabs = 0.0
        for i, r in enumerate(rs):
            pw = float.fromhex(r["pre_write_hex"]); pr = float.fromhex(r["post_read_hex"])
            if bits(pw) != bits(pre[i]): P.append(f"{name}/{route} idx{i} pre bits differ from fixture token")
            if bits(float(r["pre_write"])) != bits(pw): P.append(f"{name}/{route} idx{i} pre %.17g vs hex")
            if bits(float(r["post_read"])) != bits(pr): P.append(f"{name}/{route} idx{i} post %.17g vs hex")
            tok = r["written_token"]
            if route == "real-write-read":
                if fmt(pre[i]).strip() != tok: P.append(f"{name} idx{i} formatter emulation {fmt(pre[i])!r} != native {tok!r}")
                if bits(float(tok)) != bits(pr): P.append(f"{name} idx{i} post bits != float(token)")
            else:
                if bits(pr) != bits(pre[i]): P.append(f"{name}/{route} idx{i} full-precision not bit-equal")
                if bits(float(tok)) != bits(pre[i]): P.append(f"{name}/{route} idx{i} %.17g token does not parse to pre")
            eq = bits(pr) == bits(pre[i])
            if (r["bit_equal"] == "1") != eq: P.append(f"{name}/{route} idx{i} bit_equal flag wrong")
            neq += (not eq); maxabs = max(maxabs, abs(pr - pre[i]))
            post.append(pr)
        if neq != js["coefficients_not_bit_equal"]: P.append(f"{name}/{route} neq {neq} vs {js['coefficients_not_bit_equal']}")
        if maxabs != js["max_coeff_abs_err"]: P.append(f"{name}/{route} maxabs {maxabs!r} vs {js['max_coeff_abs_err']!r}")
        # written STAR text check (real route): file bytes for the coefficient column
        if route == "real-write-read":
            star = open(os.path.join(R2, "written_star", name + ".star")).read().splitlines()
            data = [l.split() for l in star if l.strip() and l.split()[0].isdigit()]
            assert len(data) == 2 * NC
            for idx, tok in data:
                if fmt(pre[int(idx)]).strip() != tok: P.append(f"{name} star text idx{idx} {tok!r}")
        # shift error, two ways
        px_pre = shift_getshiftat_order(pre[:NC], Z, X, Y); py_pre = shift_getshiftat_order(pre[NC:], Z, X, Y)
        px_post = shift_getshiftat_order(post[:NC], Z, X, Y); py_post = shift_getshiftat_order(post[NC:], Z, X, Y)
        ex1, ey1 = px_post - px_pre, py_post - py_pre
        dX = [post[i] - pre[i] for i in range(NC)]; dY = [post[NC + i] - pre[NC + i] for i in range(NC)]
        ex2 = sum(dX[i] * B[i] for i in range(NC)); ey2 = sum(dY[i] * B[i] for i in range(NC))
        v1, v2 = np.hypot(ex1, ey1), np.hypot(ex2, ey2)
        rec["max_vec_diff_order"] = float(v1.max()); rec["max_vec_delta_basis"] = float(v2.max())
        rec["harness_max_vec"] = js["max_vec"]
        absdiff = float(np.max(np.abs(v1 - v2)))
        rec["max_abs_diff_between_methods_px"] = absdiff
        def relerr(a, b): return abs(a - b) / b if b else abs(a - b)
        # harness value vs independent difference-order value
        rec["rel_harness_vs_diff_order"] = relerr(js["max_vec"], float(v1.max()))
        rec["rel_harness_vs_delta_basis"] = relerr(js["max_vec"], float(v2.max()))
        rng = {}
        for (rn, lo, hi) in spec["ranges"]:
            m = (F >= lo) & (F <= hi)
            mine = float(v2[m].max()); h = js["ranges"][rn]["max_vec"]
            rng[rn] = (mine, h, relerr(h, mine) if mine else abs(h - mine))
        rec["ranges"] = rng
        # per-frame
        worst_pf = 0.0
        for f in range(spec["frames"]):
            mine = float(v2[F == f].max()); h = pfm[(name, route, f)]
            worst_pf = max(worst_pf, relerr(h, mine) if mine else abs(h - mine))
        rec["worst_rel_per_frame"] = worst_pf
        k = int(np.argmax(v2)); w = js["top5_by_vec"][0]
        rec["argmax_mine"] = [spec["geoms"][G[k]][0], int(F[k]), float(PX[k]), float(PY[k])]
        rec["argmax_harness"] = [w["geometry"], w["frame"], w["px"], w["py"]]
        # ties: report how many samples are within 1e-12 relative of the max
        rec["n_ties_at_max"] = int(np.sum(v2 >= v2.max() * (1 - 1e-12))) if v2.max() > 0 else int(v2.size)
        out["fixtures"][f"{name}|{route}"] = rec
    # K3 from injected file text
    inj = json.load(open(os.path.join(R2, "summary.json")))["injected_control"]
    star = open(os.path.join(R2, "fullprecision_star", "F02_ordinary_plus1e-6_Yidx17.star")).read().splitlines()
    data = {int(l.split()[0]): float(l.split()[1]) for l in star if l.strip() and l.split()[0].isdigit()}
    pre = spec["fx"]["F02_ordinary"]["X"] + spec["fx"]["F02_ordinary"]["Y"]
    others = [i for i in range(2 * NC) if i != NC + 17 and bits(data[i]) != bits(pre[i])]
    d = data[NC + 17] - pre[NC + 17]
    dy = d * B[17]
    k = int(np.argmax(np.abs(dy)))
    out["K3"] = {"other_coeffs_changed": others, "d": d, "d_harness": inj["delta_read_minus_pre"],
                 "max_abs_dy_mine": float(np.abs(dy).max()), "harness_measured": inj["measured_max_abs_ey"],
                 "harness_predicted": inj["predicted_max_abs_ey"],
                 "rel_mine_vs_measured": abs(float(np.abs(dy).max()) - inj["measured_max_abs_ey"]) / float(np.abs(dy).max()),
                 "argmax_mine": [spec["geoms"][G[k]][0], int(F[k]), float(PX[k]), float(PY[k])],
                 "n_ties": int(np.sum(np.abs(dy) >= np.abs(dy).max() * (1 - 1e-12))),
                 "harness_K3_criteria_met": inj["K3_criteria_met"], "harness_measured_ex": inj["measured_max_abs_ex"]}
    out["any_read_failed_field"] = summ.get("any_read_failed")
    json.dump(out, sys.stdout, indent=1, default=float)

main()
