#!/usr/bin/env python3
"""Summarise the ncu CSV. Metrics are filtered by UNIT: several metric names
appear both as a percent-of-peak and as an absolute rate, and mixing them
silently produces nonsense."""
import sys, csv, collections, statistics
P = sys.argv[1] if len(sys.argv) > 1 else "ncu_all.csv"
lines = open(P).read().splitlines()
hi = [i for i, l in enumerate(lines) if l.startswith('"ID"')][0]
rd = csv.DictReader(lines[hi:])
PCT = {"Compute (SM) Throughput": "sm", "Memory Throughput": "mem",
       "DRAM Throughput": "dram", "Achieved Occupancy": "occ",
       "Theoretical Occupancy": "theo"}
SCALE = {"ns": 1e-3, "us": 1.0, "ms": 1e3, "s": 1e6}
K = collections.defaultdict(lambda: collections.defaultdict(list))
DUR = collections.defaultdict(list)
for row in rd:
    mn = row.get("Metric Name", ""); un = (row.get("Metric Unit") or "").strip()
    k = row["Kernel Name"].split("(")[0].replace("<unnamed>::", "")
    try: v = float(row["Metric Value"].replace(",", ""))
    except Exception: continue
    if mn in PCT and un == "%": K[k][PCT[mn]].append(v)
    elif mn == "Duration": DUR[k].append(v*SCALE.get(un, 1.0))
med = lambda d, m: statistics.median(d[m]) if d.get(m) else float("nan")
nl = sum(len(v) for v in DUR.values())
print("ncu: %d distinct kernel signatures over %d launches (every launch profiled)." % (len(K), nl))
print("ncu serialises kernels and flushes caches between replays, so its durations")
print("run ~1.1-1.8x the nsys wall-clock figure. The COUNTERS are the point here.")
print()
print("%-44s%5s%9s%7s%7s%7s%7s%7s" % ("kernel signature", "n", "dur_us", "SM%", "MEM%", "DRAM%", "occ%", "theo%"))
tot = lambda k: (statistics.median(DUR[k]) if DUR[k] else 0)*len(DUR[k])
for k in sorted(K, key=lambda k: -tot(k)):
    d = K[k]
    print("%-44s%5d%9.1f%7.1f%7.1f%7.1f%7.1f%7.1f" % (k[:44], len(DUR[k]),
          statistics.median(DUR[k]) if DUR[k] else 0,
          med(d, "sm"), med(d, "mem"), med(d, "dram"), med(d, "occ"), med(d, "theo")))
print()
print("SM% / MEM% are percent of peak. Low on BOTH means latency-bound: not enough")
print("independent work in flight. occ% far under theo% means the grid is too small")
print("to fill 108 SMs. A100 peaks at 1555 GB/s HBM; MEM% is measured against that.")
