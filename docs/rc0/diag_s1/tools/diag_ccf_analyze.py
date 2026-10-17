#!/usr/bin/env python3
"""Compare MC_DIAG_CCF logs (W-DIAG-S1 round 1) from a CPU and a CUDA run of the same movie.

Per frame and iteration each log holds: the CCF maximum, the position CPU's rule picks (first maximum in
signed-y-then-x order), the position production CUDA's 256-lane strict '>' reduction picks, the number of
exact ties, and the best competing local maximum. "actual" is the position the run used (CPU: its own
posx/posy; CUDA: host emulation, checked against the kernel's subpixel output, emul-ok/MISMATCH).

Reports:
  - tie statistics per run: frame-iterations, how many have an exact tie, and how many have the two
    rules disagree on the same map (the #70 condition);
  - for each patch, the first (iteration, frame) where CPU and CUDA chose different integer peaks,
    with both maps' maximum, tie count, competing peak and relative margin there;
  - the same rows for requested patch/frame pairs.
"""
import argparse, json
from collections import defaultdict


def parse(path):
    rows = []
    for line in open(path):
        t = line.split()
        r = {"tag": t[0], "patch": (int(t[1]), int(t[2])), "it": int(t[4]), "fr": int(t[6]), "max": float(t[8]),
             "cpu": (int(t[10]), int(t[11])), "lane": (int(t[13]), int(t[14])), "ties": int(t[16]),
             "second": float(t[18]), "second_at": (int(t[20]), int(t[21])), "nlm": int(t[23]),
             "actual": (int(t[25]), int(t[26])), "note": t[27], "cputies": int(t[29])}
        r["margin_rel"] = (r["max"] - r["second"]) / abs(r["max"]) if r["max"] != 0 else None
        rows.append(r)
    return rows


def first_attempt(rows, tags):
    """rows of the first attempt only: per (patch) keep rows of the first tag seen (batched before single)."""
    out = defaultdict(dict)
    seen_tag = {}
    for r in rows:
        if r["tag"] not in tags:
            continue
        k = r["patch"]
        if k not in seen_tag:
            seen_tag[k] = r["tag"]
        if r["tag"] != seen_tag[k]:
            continue
        key = (r["it"], r["fr"])
        if key in out[k]:  # a second attempt with the same tag (CUDA retry via the single path): stop
            continue
        out[k][key] = r
    return out


def stats(rows):
    s = defaultdict(lambda: {"frame_iters": 0, "exact_tie": 0, "rules_disagree": 0, "emul_mismatch": 0,
                             "min_margin_rel": None})
    for r in rows:
        g = "global" if r["tag"].endswith("global") else r["tag"]
        x = s[g]
        x["frame_iters"] += 1
        x["exact_tie"] += r["ties"] > 1
        x["rules_disagree"] += r["cpu"] != r["lane"]
        x["emul_mismatch"] += r["note"] == "emul-MISMATCH"
        m = r["margin_rel"]
        if m is not None and (x["min_margin_rel"] is None or m < x["min_margin_rel"]):
            x["min_margin_rel"] = m
    return dict(s)


def brief(r):
    return {"it": r["it"], "fr": r["fr"], "max": r["max"], "actual": r["actual"], "cpu_rule": r["cpu"],
            "lane_rule": r["lane"], "ties": r["ties"], "second": r["second"], "second_at": r["second_at"],
            "margin_rel": r["margin_rel"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", required=True)
    ap.add_argument("--cuda", required=True)
    ap.add_argument("--watch", default="", help="iy,ix:fr,fr;iy,ix:fr")
    ap.add_argument("--json-out", required=True)
    a = ap.parse_args()
    C, G = parse(a.cpu), parse(a.cuda)
    res = {"cpu_log": a.cpu, "cuda_log": a.cuda, "stats_cpu": stats(C), "stats_cuda": stats(G)}
    c1 = first_attempt(C, {"cpu"})
    g1 = first_attempt(G, {"cuda-batched", "cuda-single"})
    cg = first_attempt(C, {"cpu-global"}); gg = first_attempt(G, {"cuda-global"})
    c1[(0, 0)] = cg.get((0, 0), {}); g1[(0, 0)] = gg.get((0, 0), {})
    firsts = []
    for k in sorted(set(c1) & set(g1)):
        for key in sorted(set(c1[k]) & set(g1[k])):
            rc, rg = c1[k][key], g1[k][key]
            if rc["actual"] != rg["actual"]:
                firsts.append({"patch": k, "cpu": brief(rc), "cuda": brief(rg)})
                break
    res["first_selection_divergence_per_patch"] = firsts
    watch = []
    for spec in filter(None, a.watch.split(";")):
        p, frs = spec.split(":")
        k = tuple(int(v) for v in p.split(","))
        for fr in [int(v) for v in frs.split(",")]:
            for it in sorted({key[0] for key in c1.get(k, {})} | {key[0] for key in g1.get(k, {})}):
                rc, rg = c1.get(k, {}).get((it, fr)), g1.get(k, {}).get((it, fr))
                watch.append({"patch": k, "fr": fr, "it": it, "cpu": brief(rc) if rc else None,
                              "cuda": brief(rg) if rg else None})
    res["watch"] = watch
    json.dump(res, open(a.json_out, "w"), indent=1, default=list)
    print("== %s vs %s" % (a.cpu, a.cuda))
    for name in ("stats_cpu", "stats_cuda"):
        print(" %s %s" % (name, json.dumps(res[name])))
    print(" first selection divergence (patch: it fr | CPU actual/max/ties/margin | CUDA actual/max/ties/margin/cpu_rule):")
    for f in firsts:
        c, g = f["cpu"], f["cuda"]
        print("  %s it %d fr %d | %s %.6g t%d m%.2e | %s %.6g t%d m%.2e cpu_rule %s" % (
            f["patch"], c["it"], c["fr"], c["actual"], c["max"], c["ties"], c["margin_rel"],
            g["actual"], g["max"], g["ties"], g["margin_rel"], g["cpu_rule"]))


if __name__ == "__main__":
    main()
