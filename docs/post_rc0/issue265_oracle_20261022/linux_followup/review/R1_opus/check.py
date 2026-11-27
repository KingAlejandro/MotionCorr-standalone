# Independent host-only check of #265 Linux follow-up receipts (reviewer's own code).
import csv, json, os, struct, sys, hashlib, math
B = sys.argv[1]  # docs/post_rc0/issue265_oracle_20261022
L = os.path.join(B, "linux_followup", "receipts"); M = os.path.join(B, "receipts")
out = {}
bits = lambda v: struct.pack(">d", v)
def rows(p): return list(csv.DictReader(open(p)))
def star_tokens(p):
    t = {}
    for line in open(p):
        f = line.split()
        if len(f) == 2 and f[0].isdigit(): t[int(f[0])] = f[1]
    return t
# 1. STAR raw bytes Linux vs Mac
sb = {}
for sub, macsub in (("main/written_star", "iteration2/written_star"), ("main/fullprecision_star", "iteration2/fullprecision_star")):
    for f in sorted(os.listdir(os.path.join(L, sub))):
        a = open(os.path.join(L, sub, f), "rb").read(); mp = os.path.join(M, macsub, f)
        sb[sub + "/" + f] = (os.path.exists(mp) and open(mp, "rb").read() == a)
out["star_identical_count"] = [sum(sb.values()), len(sb)]
out["star_mac_missing_or_diff"] = [k for k, v in sb.items() if not v]
# Mac followup kept no STAR files?
out["mac_followup_dir"] = sorted(os.listdir(os.path.join(M, "followup_subnormal")))
# 2. coefficient-row self-consistency per table, own bit comparisons
res = {}
for t, macp in (("main", "iteration2"), ("followup", "followup_subnormal")):
    lr = rows(os.path.join(L, t, "coefficients.csv")); mr = rows(os.path.join(M, macp, "coefficients.csv"))
    bad_biteq = []; tok_vs_post = []; fp_tok_bad = []; sz = []
    for r in lr:
        pre = float.fromhex(r["pre_write_hex"]); post = float.fromhex(r["post_read_hex"])
        eq = bits(pre) == bits(post)
        if eq != (r["bit_equal"] == "1"): bad_biteq.append(r)
        # the stored decimal pre_write must decode to the same bits as its hex
        if bits(float(r["pre_write"])) != bits(pre): bad_biteq.append(("pre_dec", r["fixture"], r["coeff_index"]))
        # Python's correctly rounded parse of the emitted token vs the libstdc++ read-back
        if bits(float(r["written_token"])) != bits(post): tok_vs_post.append((r["fixture"], r["route"], r["coeff_index"], r["written_token"], r["post_read_hex"]))
        if math.copysign(1, pre) < 0 and pre == 0: sz.append((r["fixture"], r["route"], r["coeff_index"], r["written_token"], r["post_read_hex"], math.copysign(1, post)))
    # full-precision STAR tokens decode to the exact pre-write bits (all fixtures in the table)
    fpdir = os.path.join(L, t, "fullprecision_star")
    pre_by = {(r["fixture"], int(r["coeff_index"])): float.fromhex(r["pre_write_hex"]) for r in lr if r["route"] == "fullprecision-test-only"}
    for f in sorted(os.listdir(fpdir)):
        if "plus1e-6" in f: continue
        fx = f[:-5]; tk = star_tokens(os.path.join(fpdir, f))
        if len(tk) != 36: fp_tok_bad.append((fx, "ntok", len(tk)))
        for i, s in tk.items():
            if bits(float(s)) != bits(pre_by[(fx, i)]): fp_tok_bad.append((fx, i, s))
    # route counts and Mac overlap by bits
    key = lambda r: (r["fixture"], r["route"], r["coeff_index"])
    md = {key(r): r for r in mr}; ld = {key(r): r for r in lr}
    common = set(md) & set(ld)
    res[t] = {"rows": len(lr), "bit_equal_col_inconsistent": len(bad_biteq), "token_parse_ne_readback": tok_vs_post[:10], "n_token_parse_ne_readback": len(tok_vs_post),
              "fullprecision_token_ne_prewrite": fp_tok_bad, "signed_zero_rows": sz,
              "common_with_mac": len(common), "only_linux": len(set(ld) - set(md)), "only_mac": len(set(md) - set(ld)),
              "pre_bits_diff": sum(bits(float.fromhex(ld[k]["pre_write_hex"])) != bits(float.fromhex(md[k]["pre_write_hex"])) for k in common),
              "post_bits_diff": sum(bits(float.fromhex(ld[k]["post_read_hex"])) != bits(float.fromhex(md[k]["post_read_hex"])) for k in common),
              "token_text_diff": sum(ld[k]["written_token"] != md[k]["written_token"] for k in common),
              "pre_hex_text_diff": sorted([k + (md[k]["pre_write_hex"], ld[k]["pre_write_hex"]) for k in common if ld[k]["pre_write_hex"] != md[k]["pre_write_hex"]]),
              "nonbitequal_by_route": {}}
    for r in lr:
        k = (r["fixture"], r["route"]); res[t]["nonbitequal_by_route"].setdefault("|".join(k), 0)
        if r["bit_equal"] != "1": res[t]["nonbitequal_by_route"]["|".join(k)] += 1
    # subnormal pre-write coefficients present
    res[t]["subnormal_prewrite"] = sorted({(r["fixture"], r["coeff_index"], r["pre_write_hex"], r["route"], r["written_token"], r["post_read_hex"]) for r in lr
                                           if 0 < abs(float.fromhex(r["pre_write_hex"])) < 2.2250738585072014e-308})
out["coeff"] = res
# 3. Recompute field error at recorded worst samples from stored coefficients, ordinary double evaluation in source order (no FMA).
def shift(c, z, x, y):
    x2 = x*x; y2 = y*y; xy = x*y; z2 = z*z; z3 = z2*z
    return ((c[0]*z + c[1]*z2 + c[2]*z3) + (c[3]*z + c[4]*z2 + c[5]*z3)*x + (c[6]*z + c[7]*z2 + c[8]*z3)*x2
            + (c[9]*z + c[10]*z2 + c[11]*z3)*y + (c[12]*z + c[13]*z2 + c[14]*z3)*y2 + (c[15]*z + c[16]*z2 + c[17]*z3)*xy)
recomp = []
for t in ("main", "followup"):
    S = json.load(open(os.path.join(L, t, "summary.json"))); lr = rows(os.path.join(L, t, "coefficients.csv"))
    for fr in S["fixtures"]:
        if not fr["read_ok"]: continue
        cr = [r for r in lr if r["fixture"] == fr["fixture"] and r["route"] == fr["route"]]
        pre = [0.0]*36; post = [0.0]*36
        for r in cr: pre[int(r["coeff_index"])] = float.fromhex(r["pre_write_hex"]); post[int(r["coeff_index"])] = float.fromhex(r["post_read_hex"])
        for rn, rg in fr["ranges"].items():
            w = rg["worst_vec_at"]; z = float(w["frame"]); x = w["x_norm"]; y = w["y_norm"]
            px, py = shift(pre[:18], z, x, y), shift(pre[18:], z, x, y); qx, qy = shift(post[:18], z, x, y), shift(post[18:], z, x, y)
            ex, ey = qx - px, qy - py; v = math.hypot(ex, ey)
            recomp.append({"t": t, "fx": fr["fixture"], "route": fr["route"], "range": rn, "frame": w["frame"], "vec_rec": w["vec"], "vec_mine": v,
                           "pre_bits_eq": [px == w["pre"][0], py == w["pre"][1]], "post_bits_eq": [qx == w["post"][0], qy == w["post"][1]],
                           "vec_bits_eq": v == w["vec"], "range_max_eq_worst": rg["max_vec"] == w["vec"], "max_shift_abs": max(abs(px), abs(py))})
out["recompute_n"] = len(recomp)
out["recompute_vec_mismatch"] = [r for r in recomp if not r["vec_bits_eq"]]
out["recompute_shift_mismatch"] = [r for r in recomp if not all(r["pre_bits_eq"] + r["post_bits_eq"])][:20]
out["recompute_shift_mismatch_n"] = sum(1 for r in recomp if not all(r["pre_bits_eq"] + r["post_bits_eq"]))
out["range_max_ne_worst"] = [r for r in recomp if not r["range_max_eq_worst"]]
# 4. Linux vs Mac range max_vec and worst-sample shifts
cmpr = []
for t, macp in (("main", "iteration2"), ("followup", "followup_subnormal")):
    LS = {(f["fixture"], f["route"]): f for f in json.load(open(os.path.join(L, t, "summary.json")))["fixtures"]}
    MS = {(f["fixture"], f["route"]): f for f in json.load(open(os.path.join(M, macp, "summary.json")))["fixtures"]}
    for k, lf in LS.items():
        mf = MS.get(k)
        if not mf or not mf["read_ok"] or not lf["read_ok"]: continue
        for items in [("all", lf, mf)] + [(rn, lf["ranges"][rn], mf["ranges"][rn]) for rn in lf["ranges"]]:
            rn, a, b = items
            if a["max_vec"] != b["max_vec"]:
                d = abs(a["max_vec"] - b["max_vec"])
                ws = (a.get("worst_vec_at") or {})
                mag = max(abs(v) for v in ws.get("pre", [0]) + ws.get("post", [0])) if ws else None
                cmpr.append({"fx": k[0], "route": k[1], "range": rn, "linux": a["max_vec"], "mac": b["max_vec"], "abs_diff": d, "rel": d / max(a["max_vec"], b["max_vec"]),
                             "worst_shift_mag": mag, "abs_diff_over_ulp_of_shift": (d / (math.ulp(mag)) if mag else None),
                             "same_worst_location": (ws.get("frame"), ws.get("px"), ws.get("py")) == ((b.get("worst_vec_at") or {}).get("frame"), (b.get("worst_vec_at") or {}).get("px"), (b.get("worst_vec_at") or {}).get("py")) if ws else None})
out["linux_mac_maxvec_diffs"] = cmpr
# 5. per-frame tables
pl = {(r["fixture"], r["route"], r["frame"]): float(r["max_vec_err_px"]) for r in rows(os.path.join(L, "main", "per_frame_max_vec.csv"))}
pm = {(r["fixture"], r["route"], r["frame"]): float(r["max_vec_err_px"]) for r in rows(os.path.join(M, "iteration2", "per_frame_max_vec.csv"))}
c = set(pl) & set(pm); dif = [(k, pl[k], pm[k]) for k in sorted(c) if pl[k] != pm[k]]
out["per_frame"] = {"common": len(c), "only_linux": len(set(pl) - set(pm)), "only_mac": len(set(pm) - set(pl)), "n_diff": len(dif),
                    "max_rel": max((abs(a - b) / max(a, b) for _, a, b in dif), default=0), "fixtures_with_diff": sorted({k[0] for k, _, _ in dif})}
# 6. LK3 predicted value: delta * |z3 * xy| style basis at G1 frame 49 corner; Y idx17 -> coeffY(17) basis z^3*x*y
ic = json.load(open(os.path.join(L, "main", "summary.json")))["injected_control"]
d = ic["delta_read_minus_pre"]; z = 49.0; x = y = -0.5
out["LK3_mine"] = {"basis_z3xy": z**3 * x * y, "pred": d * z**3 * x * y, "harness_pred": ic["predicted_max_abs_ey"], "measured": ic["measured_max_abs_ey"],
                   "rel_meas_vs_mine": abs(ic["measured_max_abs_ey"] - d * z**3 * x * y) / ic["measured_max_abs_ey"]}
json.dump(out, sys.stdout, indent=1, default=str)
