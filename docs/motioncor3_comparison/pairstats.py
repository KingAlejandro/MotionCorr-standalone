#!/usr/bin/env python3
"""Paired analysis of the RESULT lines, including recovery of the positional bias P."""
import re, sys, statistics as st

def secs(t):
    p = t.split(":")
    return float(p[0])*60+float(p[1]) if len(p) == 2 else float(p[0])*3600+float(p[1])*60+float(p[2])

rows = []
for line in open(sys.argv[1]):
    if not line.startswith("RESULT,"): continue
    f = line.strip().split(",")
    tag = f[1:-8] if False else None
    # RESULT,<tag fields...>,elapsed,cpu,rss,fsin,rc=,outputs=,OK,foreign=
    elapsed, cpu, rss, fsin, rc, outs, ok, foreign = f[-8:]
    rows.append({"tag": ",".join(f[1:-8]), "s": secs(elapsed), "cpu": cpu,
                 "rss_kb": int(rss), "fsin": fsin, "rc": rc, "outs": outs,
                 "ok": ok, "foreign": foreign.replace("foreign=", "")})

valid = [r for r in rows if r["ok"] == "OK"]
print(f"{len(rows)} results, {len(valid)} valid (rc=0 and 24 outputs)")
for r in rows:
    if r["ok"] != "OK":
        print(f"  EXCLUDED: {r['tag']} {r['s']}s {r['rc']} {r['outs']}")

pairs = {}
for r in valid:
    m = re.match(r"pair(\d+),(MC_first|MC3_first),(\S+)", r["tag"])
    if m:
        pairs.setdefault((int(m.group(1)), m.group(2)), {})[m.group(3)] = r

print("\n== Phase 2 paired: MotionCorr vs MotionCor3 (stock upstream build)")
print(f"{'pair':<5} {'order':<10} {'motioncorr':>11} {'motioncor3':>11} {'diff':>9} {'ratio':>7}  foreign(mc/mc3)")
diffs, ratios, by_order = [], [], {"MC_first": [], "MC3_first": []}
for (i, order) in sorted(pairs):
    p = pairs[(i, order)]
    if "motioncorr" not in p or "motioncor3_stock" not in p: continue
    a, b = p["motioncorr"]["s"], p["motioncor3_stock"]["s"]
    d = b - a
    diffs.append(d); ratios.append(b/a); by_order[order].append(d)
    print(f"{i:<5} {order:<10} {a:>10.2f}s {b:>10.2f}s {d:>8.2f}s {b/a:>7.3f}  "
          f"{p['motioncorr']['foreign']} / {p['motioncor3_stock']['foreign']}")

if diffs:
    n = len(diffs)
    print(f"\n  n pairs                 {n}")
    print(f"  MotionCor3 slower by    median {st.median(diffs):.2f} s   mean {st.mean(diffs):.2f} s"
          + (f"   sd {st.stdev(diffs):.2f} s" if n > 1 else ""))
    print(f"  ratio (mc3 / motioncorr) median {st.median(ratios):.3f}   range {min(ratios):.3f}-{max(ratios):.3f}")
    print(f"  pairs where MotionCorr faster: {sum(1 for d in diffs if d>0)}/{n}")
    if by_order["MC_first"] and by_order["MC3_first"]:
        e1, e2 = st.mean(by_order["MC_first"]), st.mean(by_order["MC3_first"])
        print(f"\n  observed = E +/- P decomposition")
        print(f"    MC_first  mean diff {e1:+.2f} s  (n={len(by_order['MC_first'])})")
        print(f"    MC3_first mean diff {e2:+.2f} s  (n={len(by_order['MC3_first'])})")
        print(f"    E (true effect)     {(e1+e2)/2:+.2f} s")
        print(f"    P (positional bias) {(e1-e2)/2:+.2f} s   <- advantage to whichever arm runs second")

print("\n== per-arm summary (valid runs only)")
groups = {}
for r in valid:
    key = r["tag"].split(",")[-1]
    groups.setdefault(key, []).append(r)
print(f"{'arm':<28} {'n':>3} {'median s':>9} {'min':>8} {'max':>8} {'peak RSS GB':>12}")
for k, v in sorted(groups.items()):
    s = [x["s"] for x in v]
    print(f"{k:<28} {len(v):>3} {st.median(s):>9.2f} {min(s):>8.2f} {max(s):>8.2f} "
          f"{max(x['rss_kb'] for x in v)/1048576:>12.2f}")
