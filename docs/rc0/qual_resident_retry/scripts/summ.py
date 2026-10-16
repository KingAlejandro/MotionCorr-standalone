#!/usr/bin/env python3
"""Per-run summary: rc, peak host RSS (GNU time), NVML peak VRAM for the run's GPU, retry counts."""
import json, re, subprocess, sys
from pathlib import Path
S = Path("/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/runs")
rows = []
for tag in [a for a in sys.argv[1:] if not a.startswith("--")]:
    side = S / (tag + ".side")
    err = (side / "run.stderr").read_text()
    out = (side / "run.stdout").read_text()
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", err).group(1)) / 1048576
    wall = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", err).group(1)
    vals, pids = [], set()
    vram = side / "vram.csv"
    if vram.exists():
        for line in vram.read_text().splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) >= 4:
                try:
                    vals.append(int(p[3])); pids.add(p[2])
                except ValueError:
                    pass
    a = json.loads(subprocess.check_output(["python3", "/mnt/clathrin/alex-motioncorr-rc0/W-RETRY-Q/analyse.py", str(S / tag)]))
    m = re.search(r"resident-retry-preparations=(\d+)", err)
    rows.append({"run": tag, "rc": int(re.search(r"^rc=(\d+)", out, re.M).group(1)),
                 "peak_rss_gib": round(rss, 2), "wall_s_unreliable": wall,
                 "nvml_peak_mib": max(vals) if vals else None, "nvml_samples": len(vals), "nvml_pids": len(pids),
                 "patches": a["patches"], "retried": a["retried"], "retry_conv": a["retry_converged"],
                 "warnings": a["warnings"], "resident_preps": int(m.group(1)) if m else None,
                 "ingest": sorted({l.split()[-1] for l in (side / "witness.txt").read_text().splitlines()}) if (side/"witness.txt").exists() else None})
if "--json" in sys.argv:
    print(json.dumps(rows, indent=1))
else:
    for r in rows:
        print(r)
