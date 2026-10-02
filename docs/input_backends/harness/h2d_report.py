#!/usr/bin/env python3
"""Host-to-device bytes and time per route, from the retained Nsight reports.

Byte counts are contention-immune: the same payload reports the same number
whatever else the box is doing. The time column from the same capture is not,
and is what bounds any pinning experiment -- it is the most a pinned staging
buffer could recover, before subtracting what pinning costs.
"""
import glob, os, re, subprocess, sys

ROW = re.compile(r"^\s*([\d,.]+)\s+([\d,]+)\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+[\d,.]+\s+\[CUDA memcpy (\S+)\]")

def report(rep, name):
    try:
        out = subprocess.run(["nsys", "stats", "--report", name, "--force-export=true", rep],
                             capture_output=True, text=True, timeout=1800).stdout
    except Exception:
        return {}
    vals = {}
    for line in out.splitlines():
        m = ROW.match(line)
        if m:
            vals[m.group(3)] = (m.group(1), m.group(2))
    return vals

rows = []
for rep in sorted(glob.glob(sys.argv[1] + "/nsys_*.nsys-rep")):
    arm, variant = os.path.basename(rep)[5:-9].split("__", 1)
    size = report(rep, "cuda_gpu_mem_size_sum")
    time = report(rep, "cuda_gpu_mem_time_sum")
    rows.append((variant, arm,
                 size.get("Host-to-Device", ("NA", "NA")),
                 time.get("Host-to-Device", ("NA", "NA"))[0],
                 size.get("Device-to-Host", ("NA", "NA"))[0]))

print(f"{'variant':<24}{'arm':<6}{'H2D_MB':>12}{'H2D_ops':>9}{'H2D_ms':>10}{'D2H_MB':>10}")
for v, a, (mb, ops), ms, d2h in sorted(rows):
    print(f"{v:<24}{a:<6}{mb:>12}{ops:>9}{ms:>10}{d2h:>10}")
