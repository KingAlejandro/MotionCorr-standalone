#!/usr/bin/env python3
"""Matched fixed-total-CPU experiment: float vs compact ingest at 1/2/4 workers.

One question: on the composed source, does splitting the same total host budget
across more single-GPU worker processes buy throughput, and does compact uint16
ingest change that answer? Everything else is held fixed so it cannot be the
explanation.

Held fixed across every arm
  total logical CPUs        24, always: 1x24, 2x12, 4x6
  per-worker decode threads --j and --max_io_threads equal to that worker's CPUs
  output mode               identical option string; the gain series adds only
                            --gainref, the no-gain series only removes it
  input                     the same 24-movie STAR, hashed per block
  host                      one exclusive allocation, one block at a time

Varied, one factor at a time
  ingest      float binary  = composition without PR118  (PR115 + PR117)
              compact       = full composition
  workers     1 / 2 / 4, at constant total CPU
  gain        on / off, as two complete matched series

Why two binaries rather than a flag: compact staging has no runtime switch. It
engages for uint16 TIFF on the resident CUDA path, so the only honest float
control is the same composition with PR118's merge absent. Both binaries
therefore contain PR115 and PR117 and differ only in the ingest change.

Blocking and retention
  Arms run in complete interleaved blocks -- every arm once per block, order
  rotated per block -- so a monotonic host drift cannot land on one arm. At
  least three blocks, giving >=3 pairs per contrast. EVERY run is written to
  runs.jsonl including failures and discards, each with `retained` and, if
  excluded from a contrast, `excluded_because`. Nothing is silently dropped.

Recorded per arm
  wall                 first worker spawn attempt to last worker reaped, i.e.
                       launcher setup and final drain included, taken from the
                       launcher's own started_at/ended_at
  worker tail          status.json final_worker_tail_seconds
  simultaneous RSS     aggregate_sampler, one clock over the whole descendant
                       tree; NOT a sum of per-worker VmHWM
  GPU memory           aggregate_sampler, per-UUID from compute-apps, with the
                       sampling interval beside it
  achieved placement   Cpus_allowed_list read back per worker pid, plus
                       OMP_PROC_BIND / OMP_PLACES as actually exported
  products             every arm graded against that block's serial float
                       reference with compare_output_trees.py; an arm whose
                       products do not grade is retained and excluded, never
                       averaged

Not claimed by this script: speedup, efficiency, per-byte transfer rates, or any
GPU high-water mark. The GPU figure is a sampled lower bound on concurrently
attributed process memory.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_OPTS = ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
             "--patch_x", "5", "--patch_y", "5", "--bfactor", "150"]
GAIN_OPTS = ["--gainref", "Movies/gain.mrc"]
TOTAL_CPUS = 24

# (workers, per-worker cpu masks, per-worker thread count) at a fixed total of 24.
LAYOUTS = {
    1: (["0-23"], 24),
    2: (["0-11", "12-23"], 12),
    4: (["0-5", "6-11", "12-17", "18-23"], 6),
}


def arms(uuids: list[str]) -> list[dict]:
    out = []
    for series in ("gain", "nogain"):
        for ingest in ("float", "compact"):
            for n in (1, 2, 4):
                masks, threads = LAYOUTS[n]
                out.append({"arm": f"{series}-{ingest}-w{n}", "series": series,
                            "ingest": ingest, "workers": n, "masks": masks,
                            "threads": threads, "devices": uuids[:n]})
    return out


def run_arm(a: dict, block: int, cfg, ref: Path | None) -> dict:
    out_root = cfg.out / f"block{block}" / a["arm"]
    out_root.parent.mkdir(parents=True, exist_ok=True)
    binary = cfg.compact_binary if a["ingest"] == "compact" else cfg.float_binary
    opts = list(BASE_OPTS) + (GAIN_OPTS if a["series"] == "gain" else [])
    opts += ["--j", str(a["threads"]), "--max_io_threads", str(a["threads"])]
    env = dict(os.environ)
    # Thread placement is a first-order effect here, so it is set explicitly and
    # read back, never inherited and assumed.
    env["OMP_PROC_BIND"] = cfg.omp_proc_bind
    env["OMP_PLACES"] = cfg.omp_places
    cmd = [sys.executable, str(cfg.src / "tools/multi_gpu/run_multi_gpu.py"),
           "--star", "movies.star", "--out", str(out_root), "--binary", str(binary),
           "--devices", ",".join(a["devices"]), "--cpus", ";".join(a["masks"]),
           "--sample-interval", str(cfg.launcher_interval), "--"] + opts
    rec = {"block": block, "arm": a["arm"], **{k: a[k] for k in
           ("series", "ingest", "workers", "masks", "threads", "devices")},
           "total_cpus": TOTAL_CPUS, "binary": str(binary),
           "binary_sha256": cfg.binary_hashes[str(binary)],
           "omp_proc_bind": env["OMP_PROC_BIND"], "omp_places": env["OMP_PLACES"],
           "command": " ".join(shlex.quote(c) for c in cmd), "retained": True}

    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=cfg.tutorial, env=env,
                            stdout=(out_root.parent / f"{a['arm']}.log").open("wb"),
                            stderr=subprocess.STDOUT)
    sampler = subprocess.Popen(
        [sys.executable, str(HERE / "aggregate_sampler.py"), "--pid", str(proc.pid),
         *sum([["--uuid", u] for u in a["devices"]], []),
         "--interval", str(cfg.sample_interval),
         "--out", str(out_root.parent / f"{a['arm']}.memory.json")])
    rc = proc.wait()
    sampler.wait(timeout=120)
    rec["launcher_rc"] = rc
    rec["driver_wall_s"] = round(time.time() - t0, 3)

    status_path = out_root / "status.json"
    if status_path.is_file():
        st = json.loads(status_path.read_text())
        rec["launcher_wall_s"] = st.get("wall_seconds")
        rec["worker_tail_s"] = st.get("final_worker_tail_seconds")
        rec["workers_detail"] = [{k: w.get(k) for k in
                                  ("index", "pid", "returncode", "wall_seconds",
                                   "rss_hwm_kib", "started_at", "ended_at")}
                                 for w in st.get("workers", [])]
        rec["cpu_masks_requested"] = st.get("cpu_masks")
        rec["achieved_masks"] = st.get("achieved_cpu_masks")
        rec["witness"] = st.get("witness")
    else:
        rec.update({"retained": True, "excluded_because": "no status.json"})
    mem_path = out_root.parent / f"{a['arm']}.memory.json"
    if mem_path.is_file():
        rec["memory"] = json.loads(mem_path.read_text())
        rec["memory"].pop("sweeps_raw", None)   # kept on disk, not in the index
    else:
        rec["excluded_because"] = "no memory record"

    if rc != 0:
        rec["excluded_because"] = f"launcher rc {rc}"
        return rec

    # Merge, then grade the products. An arm is only comparable if its output
    # tree is complete and equal to the block reference.
    merged = out_root.parent / f"{a['arm']}-merged"
    m = subprocess.run(
        [sys.executable, str(cfg.src / "tools/multi_gpu/merge_workers.py"),
         "--manifest", str(out_root / "shards/shard_manifest.json"),
         "--workers", *[str(p) for p in sorted(out_root.glob("worker*"))],
         "--status", str(status_path), "--out", str(merged),
         "--report", str(out_root.parent / f"{a['arm']}-merge.json"),
         "--aggregate-with", str(binary), "--input-star", "movies.star",
         "--aggregate-args", " ".join(opts)],
        cwd=cfg.tutorial, capture_output=True, text=True)
    rec["merge_rc"] = m.returncode
    if m.returncode != 0:
        rec["excluded_because"] = "merge refused"
        return rec
    if ref is None:
        rec["grade"] = "reference"
        return rec
    g = subprocess.run(
        [sys.executable, str(cfg.src / "docs/issue85_laneC/compare_output_trees.py"),
         str(ref), str(merged), "--manifest", str(cfg.manifest),
         "--input-star", "movies.star",
         "--json-out", str(out_root.parent / f"{a['arm']}-grade.json")],
        cwd=cfg.tutorial, capture_output=True, text=True)
    rec["grade_rc"] = g.returncode
    rec["grade"] = "PASS" if g.returncode == 0 else "FAIL"
    if g.returncode != 0:
        rec["excluded_because"] = "products did not grade equal to the block reference"
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--float-binary", type=Path, required=True,
                    help="composition WITHOUT PR118 (PR115 + PR117)")
    ap.add_argument("--compact-binary", type=Path, required=True,
                    help="full composition")
    ap.add_argument("--tutorial", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True,
                    help="movie inventory for compare_output_trees.py")
    ap.add_argument("--uuids", required=True, help="four GPU UUIDs, comma separated")
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--sample-interval", type=float, default=0.25)
    ap.add_argument("--launcher-interval", type=float, default=0.5)
    ap.add_argument("--omp-proc-bind", default="close")
    ap.add_argument("--omp-places", default="cores")
    cfg = ap.parse_args(argv)
    if cfg.blocks < 3:
        print("refusing: fewer than three blocks cannot give three pairs per contrast")
        return 2
    uuids = cfg.uuids.split(",")
    if len(uuids) != 4:
        print("refusing: four device UUIDs are required for the 4-worker arm")
        return 2
    cfg.out.mkdir(parents=True, exist_ok=True)
    cfg.binary_hashes = {}
    for b in (cfg.float_binary, cfg.compact_binary):
        cfg.binary_hashes[str(b)] = subprocess.run(
            ["sha256sum", str(b)], capture_output=True, text=True).stdout.split()[0]
    if cfg.binary_hashes[str(cfg.float_binary)] == cfg.binary_hashes[str(cfg.compact_binary)]:
        print("refusing: the two arms are the same binary, so the contrast is vacuous")
        return 2

    plan = arms(uuids)
    index = (cfg.out / "runs.jsonl").open("a")
    ref = None
    for block in range(1, cfg.blocks + 1):
        # Rotate arm order per block so a monotonic host drift cannot favour one arm.
        order = plan[block % len(plan):] + plan[:block % len(plan)]
        # The block reference is always the same arm and is run first.
        ordered = [a for a in order if a["arm"] == "gain-float-w1"] + \
                  [a for a in order if a["arm"] != "gain-float-w1"]
        for a in ordered:
            is_ref = a["arm"] == "gain-float-w1"
            rec = run_arm(a, block, cfg, None if is_ref else ref)
            if is_ref and rec.get("merge_rc") == 0:
                ref = cfg.out / f"block{block}" / f"{a['arm']}-merged"
            index.write(json.dumps(rec) + "\n"); index.flush()
            print(f"block{block} {a['arm']}: rc={rec.get('launcher_rc')} "
                  f"wall={rec.get('launcher_wall_s')} grade={rec.get('grade')} "
                  f"excluded={rec.get('excluded_because')}")
    index.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
