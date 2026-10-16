#!/usr/bin/env python3
"""Paired A/B for the CUDA warm-up changes, on an exclusively allocated SCARF GPU node.

Arms differ only in the binary: build-base (main 116eb04a) vs build-cand (branch
perf/cuda-warmup-thread). The launcher is src-cand's for both arms, so everything
else (worker flags, --skip_report_pdf, aggregate) is held constant. The allocation
itself is the exclusion. Order alternates per rep; one discarded warm-up per arm.
"""
import hashlib, json, shlex, shutil, statistics, subprocess, sys, time
from pathlib import Path

BASE = Path("/home/vol05/scarf1415/mc-warmup-20261014")
BINS = {"base": BASE / "build-base" / "motioncorr", "cand": BASE / "build-cand" / "motioncorr"}
TOOLS = BASE / "src-cand" / "tools" / "multi_gpu"
DATA = Path("/tmp/bench-data")
PY = sys.executable
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
G = [l.split(", ")[1].strip() for l in subprocess.run(
    ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
    capture_output=True, text=True, check=True).stdout.splitlines()]
# physical cores only, each lane on its GPU's NUMA node (gn0005: GPU0,1 -> node0, GPU2,3 -> node1)
LANES = ["0-7", "8-15", "16-23", "24-31"]
WARGS = ("--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 "
         "--bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --ingest nvcomp").split()
W = Path("/tmp/warmab")
if W.exists():
    shutil.rmtree(W)
W.mkdir()
KEEP = BASE / "keep"
if KEEP.exists():
    shutil.rmtree(KEEP)
KEEP.mkdir()

def one(arm, ngpu, out, keep=None):
    la = ["--devices", ",".join(G[:ngpu]), "--cpus", ";".join(LANES[:ngpu]), "--cpu-budget", str(8 * ngpu)]
    cmd = ["taskset", "-c", ",".join(LANES[:ngpu]), PY, str(TOOLS / "run_dataset.py"),
           "--binary", str(BINS[arm]), "--star", "movies.star", "--out", str(out),
           "--launcher-args=" + shlex.join(la), "--", *WARGS]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True)
    wall = time.time() - t0
    try:
        s = json.loads((out / "dataset_status.json").read_text())
        if s.get("verdict") != "PASS":
            raise ValueError(s.get("failure", s.get("verdict")))
    except Exception:
        print("  %s %dx8 FAILED rc=%d\n%s" % (arm, ngpu, p.returncode, (p.stderr or p.stdout)[-2000:]), flush=True)
        raise SystemExit("aborting: a failed run makes the pairing incomplete")
    rec = {"arm": arm, "ngpu": ngpu, "rc": p.returncode, "harness_wall_s": wall,
           "dataset_wall_s": s.get("dataset_wall_s"), "worker_phase_wall_s": s.get("worker_phase_wall_s"),
           "aggregate_phase_wall_s": s.get("aggregate_phase_wall_s"), "verdict": s.get("verdict"),
           "binary": str(BINS[arm])}
    print("  %-4s %dx8-24 rc=%d wall=%7.3f worker=%7.3f agg=%6.3f %s"
          % (arm, ngpu, p.returncode, rec["dataset_wall_s"], rec["worker_phase_wall_s"],
             rec["aggregate_phase_wall_s"], s.get("verdict")), flush=True)
    if keep:
        shutil.copytree(out / "merged", keep)
    return rec

CFG = [1, 4]
recs = []
print("### warmup (discarded; merged tree kept for the product comparison)", flush=True)
for arm in ("base", "cand"):
    d = W / ("warm_" + arm)
    one(arm, 1, d, keep=KEEP / arm)
    shutil.rmtree(d, ignore_errors=True)
for rep in range(REPS):
    print("### rep %d" % rep, flush=True)
    for ngpu in CFG:
        arms = ["base", "cand"] if rep % 2 == 0 else ["cand", "base"]
        for arm in arms:
            d = W / ("r%d_%s_%dx8" % (rep, arm, ngpu))
            r = one(arm, ngpu, d)
            r["rep"] = rep; r["order"] = arms.index(arm)
            recs.append(r)
            shutil.rmtree(d, ignore_errors=True)

print("\n%-8s %9s %9s %9s %8s  %s" % ("cfg", "base_med", "cand_med", "saving", "pct", "pairs cand<base"))
summary = {}
for ngpu in CFG:
    b = {r["rep"]: r["dataset_wall_s"] for r in recs if r["arm"] == "base" and r["ngpu"] == ngpu}
    c = {r["rep"]: r["dataset_wall_s"] for r in recs if r["arm"] == "cand" and r["ngpu"] == ngpu}
    diffs = [b[k] - c[k] for k in sorted(b)]
    wins = sum(d > 0 for d in diffs)
    # exact two-sided sign test
    from math import comb
    n = len(diffs); k = min(wins, n - wins)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    mb, mc = statistics.median(b.values()), statistics.median(c.values())
    tag = "%dx8-24" % ngpu
    summary[tag] = {"base_median": mb, "cand_median": mc, "saving_s": mb - mc, "pct": 100 * (mb - mc) / mb,
                    "median_paired_diff_s": statistics.median(diffs), "paired_diffs_s": diffs,
                    "cand_faster_pairs": wins, "pairs": n, "sign_test_p": p,
                    "base_walls": [b[k] for k in sorted(b)], "cand_walls": [c[k] for k in sorted(c)]}
    print("%-8s %9.3f %9.3f %+9.3f %7.1f%%  %d/%d  p=%.4f  median paired diff %+.3f"
          % (tag, mb, mc, mb - mc, 100 * (mb - mc) / mb, wins, n, p, statistics.median(diffs)))
ok = all(r["rc"] == 0 and r["verdict"] == "PASS" for r in recs)
print("\nruns=%d all_pass=%s" % (len(recs), ok))
(BASE / "warmab.json").write_text(json.dumps(
    {"summary": summary, "records": recs, "all_pass": ok, "lanes": LANES, "reps": REPS, "gpus": G,
     "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in BINS.items()},
     "launcher_sha256": hashlib.sha256((TOOLS / "run_multi_gpu.py").read_bytes()).hexdigest()}, indent=1))
print("ALLDONE")
