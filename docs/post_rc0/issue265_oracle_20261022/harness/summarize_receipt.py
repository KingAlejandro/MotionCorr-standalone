#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Render the committed summary.json as markdown tables. Reads JSON only; no model code."""
import json
import sys

d = json.load(open(sys.argv[1]))
ranges = ["early", "mid", "late24", "gap", "late40", "gap2", "late50", "all"]
print("| fixture | route | coeffs not bit-equal | max coeff abs err | " + " | ".join(f"max vec {r} (px)" for r in ranges) + " |")
print("|---|---|---|---|" + "---|" * len(ranges))
for r in d["fixtures"]:
    if not r["read_ok"]:
        print(f"| {r['fixture']} | {r['route']} | READ FAILED | | " + " | ".join("" for _ in ranges) + " |")
        continue
    print(f"| {r['fixture']} | {r['route']} | {r['coefficients_not_bit_equal']} | {r['max_coeff_abs_err']:.3e} | "
          + " | ".join(f"{r['ranges'][k]['max_vec']:.3e}" for k in ranges) + " |")
print()
print("Worst sample per real-write-read fixture (by vector error):")
print("| fixture | geometry | frame | px | py | pre (x,y) | post (x,y) | err (x,y) | vec |")
print("|---|---|---|---|---|---|---|---|---|")
for r in d["fixtures"]:
    if r["route"] != "real-write-read" or not r["read_ok"] or r["max_vec"] == 0:
        continue
    s = r["top5_by_vec"][0]
    print(f"| {r['fixture']} | {s['geometry']} | {s['frame']} | {s['px']:g} | {s['py']:g} | "
          f"({s['pre'][0]:.6g}, {s['pre'][1]:.6g}) | ({s['post'][0]:.6g}, {s['post'][1]:.6g}) | "
          f"({s['err'][0]:.3e}, {s['err'][1]:.3e}) | {s['vec']:.3e} |")
