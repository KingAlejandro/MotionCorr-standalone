#!/usr/bin/env python3
"""S1.3c census: per family and grid, S1 incidence (relative RMSE >= 0.1) for
CUDA off / on (GLOBAL+DW toggle) / pr254 (#254, all five C2R sites) / null1 / null2 against the sweep's frozen-F CPU product, the 2x2
transition counts off -> arm, and McNemar's exact two-sided p (binomial on the
discordant pairs).  census.py <rows.json> <out.json>
rows.json: list of {movie, grid, venue, off, [on], [pr254], null1, null2} relative RMSE values."""
import json, sys
from math import comb


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def table(rows, a, b):
    rows = [r for r in rows if a in r and b in r]
    if not rows:
        return None
    t = {"stays+": 0, "+->-": 0, "-->+": 0, "stays-": 0}
    for r in rows:
        x, y = r[a] >= 0.1, r[b] >= 0.1
        t["stays+" if x and y else "+->-" if x else "-->+" if y else "stays-"] += 1
    t["mcnemar_p"] = mcnemar(t["+->-"], t["-->+"])
    t["n"] = len(rows)
    t[a + "_positive"] = sum(r[a] >= 0.1 for r in rows); t[b + "_positive"] = sum(r[b] >= 0.1 for r in rows)
    return t


rows = json.load(open(sys.argv[1]))
fam = lambda m: m.rsplit("-", 1)[0]
groups = {}
for r in rows:
    groups.setdefault((fam(r["movie"]), r["grid"]), []).append(r)
    groups.setdefault((fam(r["movie"]), "both"), []).append(r)
    groups.setdefault(("pooled", r["grid"]), []).append(r)
    groups.setdefault(("pooled", "both"), []).append(r)
out = {}
for key in sorted(groups, key=lambda k: (k[0] == "pooled", k[0], str(k[1]))):
    g = groups[key]; name = "%s-%s" % (key[0], "p%s" % key[1] if key[1] != "both" else "both")
    pairs = [("off", "on"), ("off", "pr254"), ("off", "null1"), ("off", "null2"), ("on", "pr254"),
             ("null1", "on"), ("null2", "on"), ("null1", "pr254"), ("null2", "pr254"), ("null1", "null2")]
    out[name] = {f"{a}->{b}": t for a, b in pairs if (t := table(g, a, b))}
    o = out[name]
    cells = []
    for k in ("off->on", "off->pr254", "off->null1", "off->null2"):
        if k in o:
            t = o[k]; b = k.split("->")[1]
            cells.append("%s %2d (+-%d -+%d p=%.3g)" % (b, t[b + "_positive"], t["+->-"], t["-->+"], t["mcnemar_p"]))
    off = o["off->null1"]["off_positive"] if "off->null1" in o else "-"
    print("%-16s n=%2d  off %2s | %s" % (name, len(g), off, " | ".join(cells)))
json.dump(out, open(sys.argv[2], "w"), indent=1)
