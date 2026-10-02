#!/usr/bin/env python3
"""Device-side input-stage breakdown per route, from the retained Nsight captures.

Only the stages the ingest owns are reported; everything else is folded into
"other GPU work" so the columns sum to the capture's whole device-busy time and
nothing is silently dropped.

  deflate decode   nvcomp_deflate::inflate_kernel        (GPU route only)
  adler-32 verify  adler32StripsKernel                   (GPU route only)
  convert+gain+sum fusedNativeFlipGainAndSum / convertGainAndAccumulateNative
                                                         (GPU and compact routes)
  H2D copy         [CUDA memcpy Host-to-Device]
"""
import glob, json, os, re, subprocess, sys

KERN = re.compile(r"^\s*[\d.]+\s+([\d,]+)\s+([\d,]+)\s+[\d,.]+\s+[\d,.]+\s+[\d,]+\s+[\d,]+\s+[\d,.]+\s+(.*\S)\s*$")
MEM = re.compile(r"^\s*[\d.]+\s+([\d,]+)\s+([\d,]+)\s+.*\[CUDA memcpy (\S+)\]")

# Matched on substrings that are stable across both arms: main names the fused
# ingest kernel fusedU16FlipGainAndSumKernel and the compact one
# convertGainAndAccumulateU16Kernel, the branch names them ...Native...; a
# matcher that knew only one arm's names would attribute the other arm's work
# to "other" and make the base column look like it does no conversion at all.
STAGES = [
    ("deflate decode", ("nvcomp_deflate", "inflate_kernel")),
    ("adler-32 verify", ("adler32StripsKernel",)),
    ("convert + gain + sum", ("FlipGainAndSum", "GainAndAccumulate", "fusedGainAndSum")),
]

def run(rep, report):
    try:
        return subprocess.run(["nsys", "stats", "--report", report, rep],
                              capture_output=True, text=True, timeout=1800).stdout
    except Exception:
        return ""

out = {}
for rep in sorted(glob.glob(sys.argv[1] + "/nsys_*.nsys-rep")):
    arm, variant = os.path.basename(rep)[5:-9].split("__", 1)
    rec = {k: 0.0 for k, _ in STAGES}
    rec["other GPU kernels"] = 0.0
    for line in run(rep, "cuda_gpu_kern_sum").splitlines():
        m = KERN.match(line)
        if not m:
            continue
        ns = float(m.group(1).replace(",", ""))
        name = m.group(3)
        for stage, keys in STAGES:
            if any(k in name for k in keys):
                rec[stage] += ns / 1e6
                break
        else:
            rec["other GPU kernels"] += ns / 1e6
    for line in run(rep, "cuda_gpu_mem_time_sum").splitlines():
        m = MEM.match(line)
        if m and m.group(3) == "Host-to-Device":
            rec["H2D copy"] = float(m.group(1).replace(",", "")) / 1e6
    out.setdefault(variant, {})[arm] = rec

print(json.dumps(out, indent=1))
