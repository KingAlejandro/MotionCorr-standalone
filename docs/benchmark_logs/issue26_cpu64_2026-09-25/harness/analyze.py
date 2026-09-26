#!/usr/bin/env python3
"""Turn bench26 JSON files into the scaling table for Issue #26."""
import json, statistics, sys
from collections import defaultdict

def table(path):
    d = json.load(open(path))
    by = defaultdict(list)
    for r in d["runs"]:
        if r["rc"] == 0:
            by[r["threads"]].append(r)
    js = sorted(by)
    base = statistics.median([r["wall_s"] for r in by[js[0]]])
    print(f"\n### {d['label']}   "
          f"(OMP_PROC_BIND={d.get('OMP_PROC_BIND')}, OMP_PLACES={d.get('OMP_PLACES')}"
          f"{', numactl=' + d['numactl_prefix'] if d.get('numactl_prefix') else ''})")
    print(f"binary sha256 {d['binary_sha256'][:16]}…  reps={d['reps']}  star={d['star']}")
    print()
    print("| j | wall s (median) | wall s (all reps) | speedup | par.eff | user s | sys s | peak RSS GiB | own cores | foreign cores mean/max |")
    print("|--:|--:|:--|--:|--:|--:|--:|--:|--:|:--|")
    rows = []
    for j in js:
        w = [r["wall_s"] for r in by[j]]
        med = statistics.median(w)
        u = statistics.median([r.get("user_s", 0) for r in by[j]])
        s = statistics.median([r.get("sys_s", 0) for r in by[j]])
        rss = statistics.median([r.get("maxrss_kb", 0) for r in by[j]]) / 1048576
        fm = statistics.median([r["contention"]["foreign_cores_mean"] for r in by[j]])
        fx = max(r["contention"]["foreign_cores_max"] for r in by[j])
        ow = statistics.median([r["contention"].get("own_cores_mean") or 0 for r in by[j]])
        sp = base / med
        print(f"| {j} | {med:.2f} | {', '.join(f'{x:.2f}' for x in sorted(w))} | "
              f"{sp:.2f}x | {100*sp/j:.1f}% | {u:.1f} | {s:.1f} | {rss:.2f} | {ow:.1f} | {fm:.1f}/{fx:.1f} |")
        rows.append((j, med, sp))
    # distinct output digests
    dig = set()
    for r in d["runs"]:
        for v in r.get("outputs", {}).values():
            dig.add(v["pixels_sha256"])
    print(f"\ndistinct output pixel digests across every run in this arm: {len(dig)}"
          f"  -> {'thread-count independent (bit-exact)' if len(dig)==1 else 'DIFFER'}")
    for x in sorted(dig):
        print(f"   {x}")
    return rows

def stages(path, js=(1, 16)):
    d = json.load(open(path))
    by = defaultdict(list)
    for r in d["runs"]:
        if r.get("stages"): by[r["threads"]].append(r["stages"])
    if not by: return
    have = [j for j in js if j in by]
    if not have: return
    def sec(d, k):
        v = d.get(k, 0)
        return v["sec"] if isinstance(v, dict) else v
    keys = sorted({k for j in have for s in by[j] for k in s},
                  key=lambda k: -statistics.median([sec(s, k) for s in by[have[0]]]))
    print("\n| stage | " + " | ".join(f"j={j} (s)" for j in have) + " | speedup |")
    print("|:--|" + "--:|" * (len(have) + 1))
    for k in keys:
        vals = [statistics.median([sec(s, k) for s in by[j]]) for j in have]
        if max(vals) < 0.02: continue
        sp = (vals[0] / vals[-1]) if vals[-1] > 0 else float("inf")
        print(f"| {k} | " + " | ".join(f"{v:.3f}" for v in vals) + f" | {sp:.2f}x |")

for p in sys.argv[1:]:
    table(p)
    stages(p)
