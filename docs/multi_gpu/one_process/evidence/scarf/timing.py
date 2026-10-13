#!/usr/bin/env python3
"""Paired timing: 1 process x 4 devices (T) vs 4 processes x 1 device (P), 96 movies.

P: four processes, shard k of movies96 (24 movies), CUDA_VISIBLE_DEVICES=<uuid k>,
   taskset lane k (8 CPUs), --gpu 0 --j 8.  T: one process, taskset 0-31,
   --gpu 0,1,2,3 --j 32 over all 96.  Both --skip_logfile, --ingest nvcomp.
Wall is launch to last exit. Arm order alternates per pair; one discarded
warm-up per arm. A final untimed run per arm samples GPU apps for the device
witness and peak VRAM.
"""
import json, os, re, shutil, statistics as st, subprocess, sys, threading, time
from pathlib import Path

BASE = Path("/home/vol05/scarf1415/mc-mdev-20261013")
BIN = BASE / "build-cand" / "motioncorr"
DATA = Path("/tmp/bench-data")
LANES = ["0-7", "8-15", "16-23", "24-31"]
WARGS = ("--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 "
         "--bfactor 150 --gainref Movies/gain.mrc --seed 1 --ingest nvcomp --skip_logfile").split()
PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
q = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
                   capture_output=True, text=True, check=True).stdout
G = [l.split(",")[1].strip() for l in q.splitlines() if l.strip()]
assert len(G) == 4, G
SH = Path("/tmp/mdev-shards")
if SH.exists(): shutil.rmtree(SH)
subprocess.run([sys.executable, str(BASE / "src-cand/tools/multi_gpu/partition_star.py"),
                "--star", "movies96.star", "--n", "4", "--outdir", str(SH)],
               cwd=str(DATA), check=True, capture_output=True, text=True)
SHARDS = sorted(SH.glob("shard_*.star"))
assert len(SHARDS) == 4 and all(x.read_text().count("frameImage") == 24 for x in SHARDS)

def apps():
    r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True)
    return [tuple(x.strip() for x in l.split(",")) for l in r.stdout.splitlines() if l.strip()]

def rows(out):
    n = 0
    for s in out.rglob("corrected_micrographs.star"):
        n += sum(1 for l in s.read_text().splitlines() if "frameImage" in l)
    return n

def launch(arm, out):
    env0 = dict(os.environ, OMP_NUM_THREADS="8")
    tm = ["/usr/bin/time", "-f", "MAXRSS_KB %M"]
    if arm == "T":
        out.mkdir(parents=True)
        return [subprocess.Popen(tm + ["taskset", "-c", "0-31", str(BIN), "--i", "movies96.star",
                "--o", str(out) + "/", "--gpu", "0,1,2,3", "--j", "32"] + WARGS,
                cwd=str(DATA), env=env0, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)]
    ps = []
    for k in range(4):
        d = out / ("w%d" % k); d.mkdir(parents=True)
        env = dict(env0, CUDA_VISIBLE_DEVICES=G[k])
        ps.append(subprocess.Popen(tm + ["taskset", "-c", LANES[k], str(BIN), "--i", str(SHARDS[k]),
                  "--o", str(d) + "/", "--gpu", "0", "--j", "8"] + WARGS,
                  cwd=str(DATA), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
    return ps

def run(arm, witness=False):
    out = Path("/tmp/mdev-out-%s-%d" % (arm, time.time_ns()))
    seen, stop = [], threading.Event()
    t0 = time.time()
    ps = launch(arm, out)
    if witness:
        def sample():
            while not stop.is_set():
                seen.extend(apps()); time.sleep(0.2)
        th = threading.Thread(target=sample, daemon=True); th.start()
    errs = [p.communicate()[1] for p in ps]
    wall = time.time() - t0
    if witness: stop.set(); th.join()
    rcs = [p.returncode for p in ps]
    rss = [int(m.group(1)) for e in errs for m in [re.search(r"MAXRSS_KB (\d+)", e)] if m]
    n = rows(out)
    shutil.rmtree(out, ignore_errors=True)
    rec = dict(arm=arm, wall=round(wall, 4), rcs=rcs, rows=n, maxrss_kb=rss)
    if witness:
        # pid of the payload is the time child's child; report per-uuid pid set and peak MiB
        per = {}
        for pid, u, mem in seen:
            e = per.setdefault(u, {"pids": set(), "peak_mib": 0})
            e["pids"].add(pid); e["peak_mib"] = max(e["peak_mib"], int(mem))
        rec["gpu_apps"] = {u: {"pids": sorted(v["pids"]), "peak_mib": v["peak_mib"]} for u, v in per.items()}
    if set(rcs) != {0} or n != 96:
        print("BAD", json.dumps(rec), [e[-500:] for e in errs], flush=True); sys.exit(1)
    return rec

res = []
print("warm", json.dumps(run("T")), json.dumps(run("P")), flush=True)
for i in range(PAIRS):
    order = ("T", "P") if i % 2 == 0 else ("P", "T")
    pair = {a: run(a) for a in order}
    pair["order"] = "".join(order)
    res.append(pair)
    print(i, pair["order"], pair["T"]["wall"], pair["P"]["wall"], flush=True)
wit = {a: run(a, witness=True) for a in ("T", "P")}
d = [p["T"]["wall"] - p["P"]["wall"] for p in res]
summ = dict(T_median=st.median(p["T"]["wall"] for p in res), P_median=st.median(p["P"]["wall"] for p in res),
            T_range=[min(p["T"]["wall"] for p in res), max(p["T"]["wall"] for p in res)],
            P_range=[min(p["P"]["wall"] for p in res), max(p["P"]["wall"] for p in res)],
            diff_median=st.median(d), diff_min=min(d), diff_max=max(d),
            T_faster_pairs=sum(x < 0 for x in d), n=len(d),
            diff_median_TP_first=st.median(x for x, p in zip(d, res) if p["order"] == "TP"),
            diff_median_PT_first=st.median(x for x, p in zip(d, res) if p["order"] == "PT"))
print(json.dumps(summ, indent=1)); print(json.dumps(wit, indent=1))
(BASE / "timing.json").write_text(json.dumps(dict(pairs=res, witness=wit, summary=summ,
                                                   uuids=G, binary=str(BIN)), indent=1))
print("TIMING_DONE", flush=True)
