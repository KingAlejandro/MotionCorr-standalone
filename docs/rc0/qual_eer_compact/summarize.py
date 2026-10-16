#!/usr/bin/env python3
"""Tabulate results/*/result.json (from eer_matrix.py) as markdown. Usage: summarize.py RESULTS_DIR"""
import json, pathlib, re, sys

root = pathlib.Path(sys.argv[1])
NFR = {"f3": 2331, "f4": 5782, "g": 1911}


def fam(case):
    for k in ("_f3_", "_f4_", "_g_"):
        if k in case:
            return k.strip("_")
    return None


print("| case | g | up | gain | groups (dropped fractions) | route auto / float | peak RSS auto / float MiB (saving) | NVML VRAM auto / float MiB | tree identity auto vs float |")
print("|---|---:|---:|---|---|---|---|---|---|")
for p in sorted(root.glob("*/result.json")):
    r = json.load(open(p))
    arms = r["arms"]
    opts = r["options"]
    if "--eer_grouping" not in opts or "auto" not in arms or "float" not in arms:
        continue
    g = int(opts[opts.index("--eer_grouping") + 1]); up = opts[opts.index("--eer_upsampling") + 1]
    gain = "yes" if "--gainref" in opts else "no"
    log = root / r["case"] / "out-auto" / "Movies"
    groups = "-"
    lg = next(iter(sorted(log.glob("movie*.log"))), None)
    if lg:
        m = re.search(r"Movie size: X = \d+ Y = \d+ N = (\d+)", lg.read_text(errors="replace"))
        if m:
            n = int(m.group(1)); f = fam(r["case"])
            groups = f"{n} ({NFR[f] - n * g})" if f else str(n)
    A, F = arms["auto"], arms["float"]
    def route(a):
        w = a.get("witness"); return "-" if not w else ",".join(x.split()[-1] for x in w)
    rss = "-"
    if A.get("peak_rss_mib") and F.get("peak_rss_mib"):
        rss = f"{A['peak_rss_mib']:.0f} / {F['peak_rss_mib']:.0f} ({100 * (A['peak_rss_mib'] / F['peak_rss_mib'] - 1):+.0f} %)"
    vr = f"{A.get('nvml_app_peak_mib', '-')} / {F.get('nvml_app_peak_mib', '-')}"
    c = r.get("compare_complete_tree")
    verdict = "no compare (run failed)" if c is None else ("PASS" if c["rc"] == 0 else "FAIL")
    if c is not None and c["rc"] != 0 and r.get("compare_products_only"):
        verdict += " (products-only %s)" % ("PASS" if r["compare_products_only"]["rc"] == 0 else "FAIL")
    print(f"| {r['case']} | {g} | {up} | {gain} | {groups} | {route(A)} / {route(F)} | {rss} | {vr} | {verdict} |")
