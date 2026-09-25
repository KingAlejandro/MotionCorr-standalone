#!/usr/bin/env python3
"""Whole-dataset throughput on cpu64: is it better to give one MotionCorr
process many threads, or to run several processes with fewer threads each?
Total core budget is held constant at 16 across every configuration."""
import argparse, json, shutil, subprocess, time, hashlib
from pathlib import Path

HDR = Path("/home/ubuntu/mc-issue26/work/movies_all.star").read_text().split("data_movies")[0]
STAR_TAIL = """data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
"""

def make_shard(work, movies, idx):
    p = work / f"shard_{idx}.star"
    p.write_text(HDR + STAR_TAIL + "\n".join(f"Movies/{m} 1" for m in movies) + "\n")
    return p.name

ap = argparse.ArgumentParser()
ap.add_argument("--binary", required=True)
ap.add_argument("--work", default="/home/ubuntu/mc-issue26/work")
ap.add_argument("--cfg", default="--patch_x 1 --patch_y 1")
ap.add_argument("--budget", type=int, default=16)
ap.add_argument("--configs", default="1x16,2x8,4x4,8x2,16x1")
ap.add_argument("--bind", default="")
ap.add_argument("--out", required=True)
ap.add_argument("--label", default="")
a = ap.parse_args()
work = Path(a.work)
movies = sorted(p.name for p in (work / "Movies").iterdir() if p.name.endswith(".tiff"))
print(f"{len(movies)} movies")

res = {"label": a.label, "binary": a.binary,
       "binary_sha256": hashlib.sha256(Path(a.binary).read_bytes()).hexdigest(),
       "cfg": a.cfg, "budget_cores": a.budget, "bind": a.bind,
       "n_movies": len(movies), "configs": []}

import os
for spec in a.configs.split(","):
    nproc, nthr = (int(x) for x in spec.split("x"))
    assert nproc * nthr == a.budget, f"{spec} != {a.budget} cores"
    shards = [movies[i::nproc] for i in range(nproc)]
    names = [make_shard(work, s, i) for i, s in enumerate(shards)]
    for i in range(nproc):
        if (work / f"tp_out_{i}").exists(): shutil.rmtree(work / f"tp_out_{i}")
    env = dict(os.environ)
    if a.bind:
        env["OMP_PROC_BIND"], env["OMP_PLACES"] = a.bind.split(":")
    else:
        env.pop("OMP_PROC_BIND", None); env.pop("OMP_PLACES", None)
    t0 = time.perf_counter()
    procs = [subprocess.Popen(
        [a.binary, "--i", names[i], "--o", f"tp_out_{i}", "--use_own", "--j", str(nthr),
         "--dose_weighting", "--dose_per_frame", "1.277", "--bfactor", "150",
         "--gainref", "Movies/gain.mrc"] + a.cfg.split(),
        cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for i in range(nproc)]
    rcs = [p.wait() for p in procs]
    wall = time.perf_counter() - t0
    digs = {}
    for i in range(nproc):
        for m in sorted((work / f"tp_out_{i}" / "Movies").glob("*.mrc")):
            digs[m.name] = hashlib.sha256(m.read_bytes()[1024:]).hexdigest()
            m.unlink()
    rec = {"spec": spec, "n_proc": nproc, "threads_each": nthr, "wall_s": round(wall, 2),
           "movies_per_min": round(60 * len(movies) / wall, 2),
           "sec_per_movie": round(wall / len(movies), 2),
           "rcs": rcs, "n_outputs": len(digs),
           "output_digests": digs}
    res["configs"].append(rec)
    print(f"  {spec:6s} ({nproc} proc x {nthr} thr) wall={wall:7.1f}s  "
          f"{rec['movies_per_min']:.2f} movies/min  {rec['sec_per_movie']:.2f} s/movie  outputs={len(digs)} rc={set(rcs)}", flush=True)
    Path(a.out).write_text(json.dumps(res, indent=2))
Path(a.out).write_text(json.dumps(res, indent=2))
