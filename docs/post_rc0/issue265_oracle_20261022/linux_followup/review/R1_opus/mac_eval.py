import csv, json, os, sys
B = sys.argv[1]
def shift(c, z, x, y):
    x2 = x*x; y2 = y*y; xy = x*y; z2 = z*z; z3 = z2*z
    return ((c[0]*z + c[1]*z2 + c[2]*z3) + (c[3]*z + c[4]*z2 + c[5]*z3)*x + (c[6]*z + c[7]*z2 + c[8]*z3)*x2
            + (c[9]*z + c[10]*z2 + c[11]*z3)*y + (c[12]*z + c[13]*z2 + c[14]*z3)*y2 + (c[15]*z + c[16]*z2 + c[17]*z3)*xy)
res = {}
for lab, sp, cp in (("mac", "receipts/iteration2/summary.json", "receipts/iteration2/coefficients.csv"),
                    ("linux", "linux_followup/receipts/main/summary.json", "linux_followup/receipts/main/coefficients.csv")):
    S = json.load(open(os.path.join(B, sp))); R = list(csv.DictReader(open(os.path.join(B, cp))))
    n = mism = 0; mf = set()
    for fr in S["fixtures"]:
        if not fr["read_ok"]: continue
        pre = [0.0]*36; post = [0.0]*36
        for r in R:
            if r["fixture"] == fr["fixture"] and r["route"] == fr["route"]:
                pre[int(r["coeff_index"])] = float.fromhex(r["pre_write_hex"]); post[int(r["coeff_index"])] = float.fromhex(r["post_read_hex"])
        for rg in fr["ranges"].values():
            w = rg["worst_vec_at"]; z = float(w["frame"]); x, y = w["x_norm"], w["y_norm"]
            v = [shift(pre[:18], z, x, y), shift(pre[18:], z, x, y), shift(post[:18], z, x, y), shift(post[18:], z, x, y)]
            ok = v == list(w["pre"]) + list(w["post"]); n += 1
            if not ok: mism += 1; mf.add(fr["fixture"])
    res[lab] = {"worst_samples": n, "source_order_nonfma_mismatch": mism, "fixtures": sorted(mf)}
print(json.dumps(res, indent=1))
