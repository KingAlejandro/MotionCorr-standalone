#!/usr/bin/env python3
"""Paired summary of timing.sh output. usage: analyse_timing.py RUNDIR"""
import json, sys, statistics as st
R = sys.argv[1]
med = st.median
rows = {}
for l in open(f"{R}/runs.jsonl"):
    r = json.loads(l)
    if r["tag"].startswith("warm"):
        continue
    rep = int(r["tag"].split("_")[0][1:])
    n = int(r["tag"].split("_")[1][1:]); arm = r["tag"].split("_")[2]; pos = int(r["tag"].split("_")[3][1:])
    pr = [json.loads(x) for x in open(f"{R}/{r['tag']}/profile.jsonl")]
    proc = [x for x in pr if x.get("type") == "process"][0]
    th = {t["name"]: t["wall_ms"] for t in proc["threads"]}
    rows[(n, rep, arm)] = dict(rc=r["rc"], mrc=r["n_mrc"], proc=r["proc_wall_ms"], pdf=th.get("main/joint star and logfile pdf"), pos=pos,
                               run=proc["run_wall_ms"], busy=r["lane_busy_jiffies"] / 100 / (r["proc_wall_ms"] / 1000))
for n in (12, 96):
    reps = sorted({k[1] for k in rows if k[0] == n})
    print(f"== {n} movies, {len(reps)} paired reps; rc/mrc: " +
          str({(v['rc'], v['mrc']) for k, v in rows.items() if k[0] == n}))
    for key, label in (("pdf", "task 'main/joint star and logfile pdf' (ms)"), ("proc", "process wall (ms)")):
        b = [rows[(n, r, "base")][key] for r in reps]; c = [rows[(n, r, "cand")][key] for r in reps]
        d = [x - y for x, y in zip(b, c)]
        print(f"  {label}")
        print(f"    base {b}  median {med(b):.0f}")
        print(f"    cand {c}  median {med(c):.0f}")
        print(f"    base-cand per rep {d}  median {med(d):.0f}  pairs cand faster {sum(x > 0 for x in d)}/{len(d)}")
        first = [rows[(n, r, "base")][key] - rows[(n, r, "cand")][key] for r in reps if rows[(n, r, "base")]["pos"] == 1]
        second = [rows[(n, r, "base")][key] - rows[(n, r, "cand")][key] for r in reps if rows[(n, r, "base")]["pos"] == 2]
        print(f"    base-cand when base ran first {first}, second {second}")
