#!/usr/bin/env python3
"""Host-stage breakdown of the input path, from TIMING=ON runs.

Only the stages the input path owns are kept. "read movie" is the LibTIFF
decode and, on the float route, the float materialisation with it; "device
ingest (nvCOMP)" is the whole GPU ingest including its own file reads.

The baseline binary predates the device-ingest tag, so on the arms where main
itself takes the nvCOMP route that stage is untagged and reads as zero. Those
rows are marked rather than compared.
"""
import json, re, statistics, sys
from collections import defaultdict

WANT = ["read movie", "device ingest (nvCOMP)", "apply gain and initial sum"]
LINE = re.compile(r"^STAGE rep=(\d+) arm=(\w+) variant=(\S+) (.+?)\s*:\s*([\d.]+) sec")
HDR = re.compile(r"^STAGEHDR rep=\d+ arm=(\w+) variant=(\S+) rc=(\d+) routes=\[\s*\d+ (\w+)")

acc, routes = defaultdict(lambda: defaultdict(list)), {}
for line in open(sys.argv[1], errors="ignore"):
    h = HDR.match(line)
    if h:
        routes[(h.group(2), h.group(1))] = h.group(4)
        continue
    m = LINE.match(line)
    if m and m.group(4) in WANT:
        acc[(m.group(3), m.group(2))][m.group(4)].append(float(m.group(5)))

out = {}
for (var, arm), stages in acc.items():
    rec = {}
    for s in WANT:
        v = stages.get(s, [])
        rec[s] = round(statistics.median(v), 3) if v else 0.0
    rec["route"] = routes.get((var, arm), "?")
    rec["reps"] = max((len(v) for v in stages.values()), default=0)
    out.setdefault(var, {})[arm] = rec
print(json.dumps(out, indent=1, sort_keys=True))
