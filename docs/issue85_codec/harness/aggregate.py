#!/usr/bin/env python3
"""Collect the matched-arm runs into one machine-readable record."""
import json, re, statistics, sys
from pathlib import Path

RES = Path(sys.argv[1])
rows = []
for t in sorted(RES.glob("*.time")):
    tag = t.stem
    mode, arm, rep = tag.split("_")
    txt = t.read_text()
    m = re.search(r"wall clock.*?:\s*([\d:.]+)", txt)
    wall = None
    if m:
        p = [float(x) for x in m.group(1).split(":")]
        wall = p[0] * 60 + p[1] if len(p) == 2 else p[0]
    rss = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", txt)
    status = re.search(r"Exit status:\s*(\d+)", txt)
    so = RES / (tag + ".stdout")
    stages = {}
    if so.exists():
        for line in so.read_text().splitlines():
            sm = re.match(r"\s*(.+?)\s*:\s*([\d.]+) sec ", line)
            if sm:
                stages[sm.group(1).strip()] = float(sm.group(2))
    rows.append({"tag": tag, "mode": mode, "arm": arm, "rep": rep,
                 "wall_s": wall, "maxrss_kb": int(rss.group(1)) if rss else None,
                 "exit_status": int(status.group(1)) if status else None,
                 "n_products": len(list((RES / tag).glob("**/*_frameImage.mrc"))),
                 "read_movie_s": stages.get("read movie"),
                 "stages_s": stages})

def med(mode, arm, key):
    v = [r[key] for r in rows if r["mode"] == mode and r["arm"] == arm and r[key] is not None]
    return (round(statistics.median(v), 3), len(v), [round(x, 2) for x in sorted(v)]) if v else None

summary = {}
for mode in ("gain", "nogain"):
    s = {}
    for key in ("wall_s", "read_movie_s"):
        for arm in ("ld", "zlib"):
            s[f"{arm}_{key}"] = med(mode, arm, key)
        a, b = s[f"ld_{key}"], s[f"zlib_{key}"]
        if a and b:
            s[f"delta_{key}"] = round(a[0] - b[0], 3)
            s[f"pct_{key}"] = round(100.0 * (a[0] - b[0]) / b[0], 2)
    summary[mode] = s
print(json.dumps({"runs": rows, "summary": summary}, indent=1))
