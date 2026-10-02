#!/usr/bin/env python3
"""Summarise a graph-probe campaign: per-arm medians and paired deltas."""
import glob, json, os, statistics as st, sys

ARMS = ["prod", "async", "g0", "g1", "greuse", "greuse_noupdate"]


def load(path):
    rows = [json.loads(l) for l in open(path) if l.lstrip().startswith('{')]
    cfg = next((r for r in rows if r.get("section") == "config"), None)
    arms = {}
    for r in rows:
        if "arm" in r:
            arms.setdefault(r["arm"], []).append(r)
    return cfg, arms


def med(v):
    return st.median(v) if v else float('nan')


def bench(path):
    cfg, arms = load(path)
    print(f"\n=== {os.path.basename(path)}  {cfg['nx']}x{cfg['ny']} frames={cfg['frames']} "
          f"model={cfg['model']} reps={cfg['reps']}")
    hdr = ("arm", "wall ms", "submit cpu", "capture", "instant", "update", "launch", "destroy")
    print("{:17s}{:>10s}{:>12s}{:>10s}{:>10s}{:>9s}{:>9s}{:>9s}".format(*hdr))
    for a in ARMS:
        rs = [r for r in arms.get(a, []) if r["rep"] >= 1]   # drop the cold first rep
        if not rs:
            continue
        print("{:17s}{:10.3f}{:12.3f}{:10.3f}{:10.3f}{:9.3f}{:9.3f}{:9.3f}".format(
            a, med([r["wall_ms"] for r in rs]), med([r["submit_cpu_ms"] for r in rs]),
            med([r["capture_ms"] for r in rs]), med([r["instantiate_ms"] for r in rs]),
            med([r["update_ms"] for r in rs]), med([r["launch_ms"] for r in rs]),
            med([r["destroy_ms"] for r in rs])))
    for a in ("g1_build", "greuse_build"):
        for r in arms.get(a, []):
            print(f"{a:17s}{'':10s}{'':12s}{r['capture_ms']:10.3f}{r['instantiate_ms']:10.3f}"
                  f"{'':9s}{'':9s}{'':9s}  nodes={r['nodes']} edges={r['edges']}")
    ref = {r["rep"]: r["wall_ms"] for r in arms.get("async", []) if r["rep"] >= 1}
    print("  paired wall vs async (median, range, n, wins):")
    for a in ARMS:
        if a == "async":
            continue
        d = [r["wall_ms"] - ref[r["rep"]] for r in arms.get(a, [])
             if r["rep"] >= 1 and r["rep"] in ref]
        if d:
            print(f"    {a:16s} {med(d):+8.3f} ms  [{min(d):+8.3f},{max(d):+8.3f}]  "
                  f"n={len(d)}  faster={sum(1 for x in d if x < 0)}")
    cpu = {r["rep"]: r["submit_cpu_ms"] for r in arms.get("async", []) if r["rep"] >= 1}
    for a in ("greuse", "greuse_noupdate"):
        d = [r["submit_cpu_ms"] - cpu[r["rep"]] for r in arms.get(a, [])
             if r["rep"] >= 1 and r["rep"] in cpu]
        if d:
            print(f"    submit-cpu {a:10s} {med(d):+8.3f} ms vs async")


def exact(paths):
    print("\n=== exactness")
    bad = []
    for p in sorted(paths):
        rows = [json.loads(l) for l in open(p) if l.lstrip().startswith('{')]
        e = next((r for r in rows if r.get("section") == "exact"), None)
        if e is None:
            bad.append((os.path.basename(p), "no exact record"))
            continue
        fields = ["async", "g0", "g1", "greuse"]
        ok = all(e[f] for f in fields)
        ctrl = "n/a" if not e["update_control_applicable"] else ("pass" if e["update_control"] else "FAIL")
        print(f"  {os.path.basename(p)[:44]:46s} arms={'pass' if ok else 'FAIL'}  update_control={ctrl}")
        if not ok or ctrl == "FAIL":
            bad.append((os.path.basename(p), f"arms={ok} ctrl={ctrl}"))
    print(f"  -> {len(paths)} configs, {len(bad)} problems" + (f": {bad}" if bad else ""))


if __name__ == '__main__':
    root = sys.argv[1]
    for f in sorted(glob.glob(os.path.join(root, 'bench_*.jsonl'))):
        bench(f)
    exact(glob.glob(os.path.join(root, 'exact_*.jsonl')))
