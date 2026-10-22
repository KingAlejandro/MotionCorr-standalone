#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Report-only comparison of the Linux follow-up receipts against the committed Mac receipts.

Applies the criteria LK1, LK2, LK3, LKF exactly as stated in PROTOCOL_FROZEN.md, plus the
diagnostic Mac comparison (no gate, no tolerance). Reads committed JSON/CSV/STAR files only.
usage: compare_platforms.py > platform_comparison.json
"""
import csv
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAC = os.path.join(HERE, "..", "receipts")


def load_summary(p):
    return json.load(open(p))


def rows(p):
    with open(p) as f:
        return list(csv.DictReader(f))


def key(r):
    return (r["fixture"], r["route"], r["dim"], r["coeff_in_dim"])


def bits(hexstr):
    """IEEE-754 bit pattern of a %a string; glibc and Apple render subnormals differently."""
    return struct.pack(">d", float.fromhex(hexstr))


def route_index(summary):
    return {(r["fixture"], r["route"]): r for r in summary["fixtures"]}


lin = {t: load_summary(f"{HERE}/receipts/{t}/summary.json") for t in ("main", "followup")}
lin_rows = {t: rows(f"{HERE}/receipts/{t}/coefficients.csv") for t in ("main", "followup")}
mac_sum = {"main": load_summary(f"{MAC}/iteration2/summary.json"), "followup": load_summary(f"{MAC}/followup_subnormal/summary.json")}
mac_rows = {"main": rows(f"{MAC}/iteration2/coefficients.csv"), "followup": rows(f"{MAC}/followup_subnormal/coefficients.csv")}
li = {t: route_index(lin[t]) for t in lin}
mi = {t: route_index(mac_sum[t]) for t in mac_sum}

out = {"criteria": {}, "per_route": [], "mac_comparison": {}, "special_coefficients": []}

# ---- criteria ----
def zero_route(r):
    return r["read_ok"] and r["coefficients_not_bit_equal"] == 0 and r["max_vec"] == 0 and r["max_abs_ex"] == 0 and r["max_abs_ey"] == 0

out["criteria"]["LK1_F00_F01_real_exact"] = all(zero_route(li["main"][(f, "real-write-read")]) for f in ("F00_zero", "F01_exact"))
fp_main = {f: li["main"][(f, "fullprecision-test-only")] for f in sorted({k[0] for k in li["main"]})}
out["criteria"]["LK2_all_11_fullprecision_exact"] = all(zero_route(r) for r in fp_main.values())
out["criteria"]["LK2_per_fixture"] = {f: {"read_ok": r["read_ok"], "coefficients_not_bit_equal": r.get("coefficients_not_bit_equal"), "max_vec": r.get("max_vec"), **({"read_error": r["read_error"]} if not r["read_ok"] else {})} for f, r in fp_main.items()}
out["criteria"]["LK2_note"] = "F09 reported distinctly in LK2_per_fixture; Mac K2 (NOT MET, F09 read failure) is immutable and unchanged."
ic = lin["main"]["injected_control"]
out["criteria"]["LK3_injected"] = {"met": ic["K3_criteria_met"], "relative_difference": ic["relative_difference"], "measured_max_abs_ex": ic["measured_max_abs_ex"], "argmax_frame": ic["measured_argmax_y_at"]["frame"], "predicted_frame": ic["predicted_at"]["frame"], "delta_read_minus_pre": ic["delta_read_minus_pre"]}
out["criteria"]["LKF_followup_per_fixture"] = {f: {"read_ok": r["read_ok"], "coefficients_not_bit_equal": r.get("coefficients_not_bit_equal"), **({"read_error": r["read_error"]} if not r["read_ok"] else {})} for (f, route), r in li["followup"].items() if route == "fullprecision-test-only"}
out["criteria"]["harness_any_read_failed"] = {t: lin[t]["any_read_failed"] for t in lin}

# ---- per route table ----
for t in ("main", "followup"):
    for (f, route), r in li[t].items():
        m = mi[t].get((f, route))
        e = {"table": t, "fixture": f, "route": route, "read_ok": r["read_ok"], "coefficients_not_bit_equal": r.get("coefficients_not_bit_equal"), "max_vec_linux": r.get("max_vec"),
             "mac_read_ok": None if m is None else m["read_ok"], "max_vec_mac": None if m is None or not m["read_ok"] else m["max_vec"]}
        if r["read_ok"] and m is not None and m["read_ok"]:
            a, b = r["max_vec"], m["max_vec"]
            e["max_vec_relative_difference_linux_vs_mac"] = 0.0 if a == b else abs(a - b) / max(abs(a), abs(b))
        out["per_route"].append(e)

# ---- row-level Mac comparison (no gate) ----
for t in ("main", "followup"):
    lr = {key(r): r for r in lin_rows[t]}
    mr = {key(r): r for r in mac_rows[t]}
    common = sorted(set(lr) & set(mr))
    diff_token = [k for k in common if lr[k]["written_token"] != mr[k]["written_token"]]
    diff_post = [k for k in common if lr[k]["post_read_hex"] != mr[k]["post_read_hex"]]
    diff_pre = [k for k in common if lr[k]["pre_write_hex"] != mr[k]["pre_write_hex"]]
    # Added after the first look at the output (textual pre_write_hex differs only for subnormals, where the
    # two C libraries print %a differently): the same comparison at the bit level, via float.fromhex.
    bit_pre = [k for k in common if bits(lr[k]["pre_write_hex"]) != bits(mr[k]["pre_write_hex"])]
    bit_post = [k for k in common if bits(lr[k]["post_read_hex"]) != bits(mr[k]["post_read_hex"])]
    dec_pre = [k for k in common if lr[k]["pre_write"] != mr[k]["pre_write"]]
    only_lin = sorted(set(lr) - set(mr))
    out["mac_comparison"][t] = {"rows_compared": len(common), "rows_only_in_linux": len(only_lin),
                                "rows_only_in_linux_routes": sorted({k[:2] for k in only_lin}),
                                "pre_write_hex_differs_textual": len(diff_pre), "pre_write_decimal_differs": len(dec_pre),
                                "pre_write_bits_differ": len(bit_pre), "post_read_bits_differ": len(bit_post),
                                "pre_write_hex_textual_diff_examples": [list(k) + [mr[k]["pre_write_hex"], lr[k]["pre_write_hex"]] for k in diff_pre[:5]], "written_token_differs": len(diff_token), "post_read_hex_differs_textual": len(diff_post),
                                "written_token_diff_examples": [list(k) + [mr[k]["written_token"], lr[k]["written_token"]] for k in diff_token[:5]],
                                "post_read_diff_examples": [list(k) + [mr[k]["post_read_hex"], lr[k]["post_read_hex"]] for k in diff_post[:5]]}

# written STAR byte comparison (original 11 fixtures; the Mac follow-up kept no STAR files)
byte = {}
for f in sorted(os.listdir(f"{HERE}/receipts/main/written_star")):
    a = open(f"{HERE}/receipts/main/written_star/{f}", "rb").read()
    mp = f"{MAC}/iteration2/written_star/{f}"
    byte[f"written_star/{f}"] = "identical" if os.path.exists(mp) and open(mp, "rb").read() == a else "DIFFERENT_OR_MISSING"
for f in sorted(os.listdir(f"{HERE}/receipts/main/fullprecision_star")):
    a = open(f"{HERE}/receipts/main/fullprecision_star/{f}", "rb").read()
    mp = f"{MAC}/iteration2/fullprecision_star/{f}"
    byte[f"fullprecision_star/{f}"] = "identical" if os.path.exists(mp) and open(mp, "rb").read() == a else "DIFFERENT_OR_MISSING"
out["mac_comparison"]["star_bytes_main"] = byte

# ---- special coefficients ----
want = [("main", "F09_tiny_and_signed_zero", "X", "3"), ("main", "F09_tiny_and_signed_zero", "Y", "0"), ("followup", "G00_smallest_normal_and_1e-300", "X", "3"),
        ("main", "F09_tiny_and_signed_zero", "X", "0"), ("main", "F09_tiny_and_signed_zero", "X", "1"), ("main", "F09_tiny_and_signed_zero", "X", "2"),
        ("followup", "G00_smallest_normal_and_1e-300", "X", "0"), ("followup", "G00_smallest_normal_and_1e-300", "X", "1"), ("followup", "G00_smallest_normal_and_1e-300", "X", "2"),
        ("followup", "G01_subnormal_1e-310", "X", "0"), ("followup", "G02_subnormal_min", "X", "0")]
for t, fx, dim, idx in want:
    for r in lin_rows[t]:
        if r["fixture"] == fx and r["dim"] == dim and r["coeff_in_dim"] == idx:
            out["special_coefficients"].append({k: r[k] for k in ("fixture", "route", "dim", "coeff_in_dim", "pre_write", "pre_write_hex", "written_token", "post_read", "post_read_hex", "bit_equal", "abs_err")})
json.dump(out, sys.stdout, indent=1)
print()
