#!/usr/bin/env python3
"""Collect the committed chart inputs from the campaign logs, once."""
import json, os, re, sys
W = sys.argv[1]
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

# per-movie wall, from each retained phase-1 tree's own runner logs
pm = {}
rssd = {}
res = os.path.join(W, "results")
for d in sorted(os.listdir(res)):
    m = re.match(r"^p4_(base|cand)__(.+)$", d)
    if not m or not os.path.isdir(os.path.join(res, d)):
        continue
    arm, var = m.group(1), m.group(2)
    mv = os.path.join(res, d, "Movies")
    if not os.path.isdir(mv):
        continue
    ts = []
    for f in sorted(os.listdir(mv)):
        if not f.endswith(".log"):
            continue
        for line in open(os.path.join(mv, f), errors="ignore"):
            mm = re.search(r"Full movie wall time: ([0-9.]+) s", line)
            if mm:
                ts.append(float(mm.group(1)))
    if len(ts) > 1:
        pm.setdefault(var, {})[arm] = ts[1:]          # drop the startup-bearing first movie

# RSS and H2D from the campaign logs
for line in open(os.path.join(W, "logs", "campaign4.log"), errors="ignore"):
    m = re.match(r"^RESULT arm=(\w+) variant=(\S+) .*rss_kb=(\d+)", line)
    if m and "PHASE3" not in line:
        arm, var, rss = m.group(1), m.group(2), int(m.group(3))
        rssd.setdefault(var, {}).setdefault(arm, round(rss / 1024))
h2d = {}
for line in open(os.path.join(W, "logs", "h2d_report.txt"), errors="ignore"):
    p = line.split()
    if len(p) >= 3 and p[1] in ("base", "cand"):
        try:
            h2d.setdefault(p[0], {})[p[1]] = float(p[2].replace(",", ""))
        except ValueError:
            pass

json.dump(pm, open(os.path.join(OUT, "per_movie.json"), "w"), indent=1)
json.dump(rssd, open(os.path.join(OUT, "rss.json"), "w"), indent=1)
json.dump(h2d, open(os.path.join(OUT, "h2d_bytes.json"), "w"), indent=1)
print("per_movie", len(pm), "rss", len(rssd), "h2d", len(h2d))
