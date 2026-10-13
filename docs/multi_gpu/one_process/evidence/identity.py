#!/usr/bin/env python3
"""Identity of one-process multi-device --use_own against single-device runs.

Arms (24 tutorial movies, same per-movie thread count of 2):
  single   cand --gpu 0        --j 2
  multi    cand --gpu 0,1,2,3  --j 8
  nomutex  nomutex --gpu 0,1,2,3 --j 8   (negative control: RNG lock removed)
  seed2    cand --gpu 0 --j 2 --seed 2   (control: gate sees the defect RNG)
"""
import json, re, subprocess, sys, threading, time
from pathlib import Path

D = Path("/home/alex/mc-mdev-20261013")
DATA = Path("/home/alex/MotionCorr-standalone/relion30_tutorial")
PY = "/home/alex/.mc-venv/bin/python3"
CMP = D / "src-cand/docs/issue85_laneC/compare_output_trees.py"
MAN = D / "src-cand/docs/issue85_laneC/tutorial_24_movie_manifest.json"
OUT = D / "runs"
ARGS = ("--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 "
        "--bfactor 150 --gainref Movies/gain.mrc").split()

def gpu_apps():
    r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid",
                        "--format=csv,noheader"], capture_output=True, text=True)
    return {tuple(x.strip() for x in l.split(",")) for l in r.stdout.splitlines() if l.strip()}

def run(tag, binary, extra):
    out = OUT / tag
    out.mkdir(parents=True)
    cmd = [str(D / binary / "motioncorr"), "--i", "movies.star", "--o", str(out) + "/"] + ARGS + extra
    seen, stop = set(), threading.Event()
    def sample():
        while not stop.is_set():
            seen.update(gpu_apps()); time.sleep(0.5)
    th = threading.Thread(target=sample, daemon=True); th.start()
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(DATA), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    console, _ = p.communicate()
    wall = time.time() - t0
    stop.set(); th.join()
    (OUT / (tag + ".console.log")).write_text(console)
    logs = "\n".join(q.read_text(errors="replace") for q in out.rglob("*.log"))
    devs = {}
    for m in re.finditer(r"^\s*Device: (\d+),", logs, re.M):
        devs[m.group(1)] = devs.get(m.group(1), 0) + 1
    own = sorted(u for pid, u in seen if pid == str(p.pid))
    foreign = sorted({(pid, u) for pid, u in seen if pid != str(p.pid)})
    rec = dict(tag=tag, cmd=cmd, rc=p.returncode, wall=round(wall, 2), pid=p.pid,
               own_gpu_uuids=own, foreign_gpu_apps=foreign, log_device_counts=devs,
               accel_line=[l for l in console.splitlines() if "Using CUDA acceleration" in l])
    print(json.dumps(rec), flush=True)
    return rec

def compare(a, b):
    cmd = [PY, str(CMP), str(OUT / a), str(OUT / b), "--manifest", str(MAN),
           "--input-star", str(DATA / "movies.star"), "--allow-added-log-line", "Device:",
           "--json-out", str(OUT / ("cmp-%s-%s.json" % (a, b)))]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (OUT / ("cmp-%s-%s.log" % (a, b))).write_text(r.stdout + r.stderr)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    print(json.dumps(dict(compare=[a, b], rc=r.returncode, tail=tail)), flush=True)
    return r.returncode

if OUT.exists():
    sys.exit("runs/ exists")
recs = [run("single", "build-cand", ["--gpu", "0", "--j", "2", "--seed", "1"]),
        run("multi", "build-cand", ["--gpu", "0,1,2,3", "--j", "8", "--seed", "1"]),
        run("nomutex", "build-nomutex", ["--gpu", "0,1,2,3", "--j", "8", "--seed", "1"]),
        run("seed2", "build-cand", ["--gpu", "0", "--j", "2", "--seed", "2"])]
res = {b: compare("single", b) for b in ("multi", "nomutex", "seed2")}
(OUT / "summary.json").write_text(json.dumps(dict(runs=recs, compare_rc=res), indent=1))
print("IDENTITY_DONE", res, flush=True)
