#!/usr/bin/env python3
"""Paired A/B for the aggregate report composition, on SCARF gn0005.

Arms differ only in the binary: build-base (main 8f6b1ea1) vs build-cand
(a3f9049f, the single-pass aggregate logfile.pdf). The launcher is
src-cand's for both arms, so the worker-side --skip_logfile default is held
constant and the only moving part is the aggregate.

Venue is an exclusively allocated node, so there is no box-wide lock: the
allocation itself is the exclusion.
"""
import hashlib, json, shlex, shutil, statistics, subprocess, sys, time
from pathlib import Path

BASE = Path("/home/vol05/scarf1415/mc-overhead-20261013")
BINS = {"base": BASE / "build-base" / "motioncorr",
        "cand": BASE / "build-cand" / "motioncorr"}
TOOLS = BASE / "src-cand" / "tools" / "multi_gpu"
DATA = Path("/tmp/bench-data")
PY = sys.executable
G = ["GPU-47d61ef5-38d4-8bab-6e1b-6673e3e1f011", "GPU-2119ad35-2627-3550-88b2-13639f951704",
     "GPU-1997915e-0e47-700c-c556-b192aef2da1c", "GPU-9349c6e7-7c6a-4f26-1ac1-e30f606986a0"]
# physical cores only, each lane on its GPU's NUMA node
# (GPU0,1 -> node0 = 0-15,32-47 ; GPU2,3 -> node1 = 16-31,48-63)
LANES = ["0-7", "8-15", "16-23", "24-31"]
WARGS = ("--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 "
         "--bfactor 150 --gainref Movies/gain.mrc --seed 1 --j 8 --ingest nvcomp").split()
WL = {"24": "movies.star", "96": "movies96.star"}
W = Path("/tmp/aggrep")
if W.exists():
    shutil.rmtree(W)
W.mkdir()

def one(arm, ngpu, wl, out):
    la = ["--devices", ",".join(G[:ngpu]), "--cpus", ";".join(LANES[:ngpu]),
          "--cpu-budget", str(8 * ngpu)]
    cmd = ["taskset", "-c", ",".join(LANES[:ngpu]), PY,
           str(TOOLS / "run_dataset.py"), "--binary", str(BINS[arm]),
           "--star", WL[wl], "--out", str(out),
           "--launcher-args=" + shlex.join(la), "--", *WARGS]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=DATA, capture_output=True, text=True)
    wall = time.time() - t0
    try:
        s = json.loads((out / "dataset_status.json").read_text())
        if s.get("verdict") != "PASS":
            raise ValueError(s.get("failure", s.get("verdict")))
    except Exception:
        print("  %s %dx8-%s FAILED rc=%d\n%s" % (arm, ngpu, wl, p.returncode,
              (p.stderr or p.stdout)[-2000:]), flush=True)
        raise SystemExit("aborting: a failed run makes the pairing incomplete")
    m = out / "merged"
    rec = {"arm": arm, "ngpu": ngpu, "wl": wl, "rc": p.returncode, "harness_wall_s": wall,
           "dataset_wall_s": s.get("dataset_wall_s"),
           "worker_phase_wall_s": s.get("worker_phase_wall_s"),
           "aggregate_phase_wall_s": s.get("aggregate_phase_wall_s"),
           "verdict": s.get("verdict"),
           # in-band arm witness: only the single-pass aggregate writes this list
           "logfile_lst": (m / "logfile.pdf.lst").exists(),
           "has_header_pdf": (m / "header.pdf").exists(),
           "has_batch_pdf": (m / "batch.pdf").exists(),
           "has_all_batches_pdf": (m / "all_batches.pdf").exists(),
           "logfile_pdf_bytes": (m / "logfile.pdf").stat().st_size if (m / "logfile.pdf").exists() else 0}
    print("  %-4s %dx8-%-2s rc=%d wall=%7.3f worker=%7.3f agg=%6.3f %s lst=%s"
          % (arm, ngpu, wl, p.returncode, rec["dataset_wall_s"], rec["worker_phase_wall_s"],
             rec["aggregate_phase_wall_s"], s.get("verdict"), rec["logfile_lst"]), flush=True)
    return rec

CFG = [(1, "24"), (1, "96"), (4, "24"), (4, "96")]
recs = []
REPS = 5
# one discarded warm-up per arm: a cold binary costs ~0.9 s on first execution
# and alternating arm order does not cancel it
print("### warmup (discarded)", flush=True)
for arm in ("base", "cand"):
    d = W / ("warm_" + arm)
    one(arm, 1, "24", d)
    shutil.rmtree(d, ignore_errors=True)
for rep in range(REPS):
    print("### rep %d" % rep, flush=True)
    for ngpu, wl in CFG:
        arms = ["base", "cand"] if rep % 2 == 0 else ["cand", "base"]
        for arm in arms:
            d = W / ("r%d_%s_%dx8_%s" % (rep, arm, ngpu, wl))
            recs.append(one(arm, ngpu, wl, d))
            shutil.rmtree(d, ignore_errors=True)

print("\n%-10s %9s %9s %9s %9s %8s %7s" % ("cfg", "base_med", "cand_med", "saving", "pct", "agg_b", "agg_c"))
summary = {}
for ngpu, wl in CFG:
    g = lambda a, k: [r[k] for r in recs if r["arm"] == a and r["ngpu"] == ngpu and r["wl"] == wl]
    b, c = g("base", "dataset_wall_s"), g("cand", "dataset_wall_s")
    ab, ac = g("base", "aggregate_phase_wall_s"), g("cand", "aggregate_phase_wall_s")
    if not b or not c:
        continue
    mb, mc = statistics.median(b), statistics.median(c)
    tag = "%dx8-%s" % (ngpu, wl)
    summary[tag] = {"base_median": mb, "cand_median": mc, "saving_s": mb - mc,
                    "pct": 100 * (mb - mc) / mb, "n": [len(b), len(c)],
                    "base_agg_median": statistics.median(ab), "cand_agg_median": statistics.median(ac),
                    "base_walls": b, "cand_walls": c, "base_agg": ab, "cand_agg": ac}
    print("%-10s %9.3f %9.3f %+9.3f %8.1f%% %8.3f %7.3f"
          % (tag, mb, mc, mb - mc, 100 * (mb - mc) / mb, statistics.median(ab), statistics.median(ac)))

ok = all(r["rc"] == 0 and r["verdict"] == "PASS" for r in recs)
witness = all(r["logfile_lst"] == (r["arm"] == "cand") for r in recs)
intact = all(r["has_header_pdf"] and r["has_batch_pdf"] and r["has_all_batches_pdf"] for r in recs)
print("\nruns=%d all_pass=%s arm_witness_consistent=%s intermediate_pdfs_present=%s"
      % (len(recs), ok, witness, intact))
(BASE / "aggrep.json").write_text(json.dumps(
    {"venue": "SCARF gn0005, 2x EPYC 7302, 4x A100-SXM4-40GB, THP=always, gs 9.54.0, exclusive allocation",
     "summary": summary, "records": recs, "all_pass": ok, "arm_witness_consistent": witness,
     "intermediate_pdfs_present": intact, "lanes": LANES, "reps": REPS,
     "binary_sha256": {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in BINS.items()},
     "launcher_sha256": hashlib.sha256((TOOLS / "run_multi_gpu.py").read_bytes()).hexdigest()}, indent=1))
print("ALLDONE")
