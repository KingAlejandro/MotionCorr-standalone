#!/usr/bin/env python3
"""Run the bounded same-process interpolation experiment, never whole movies.

Usage: run-layout-checks.sh python3 run_kernel.py --binary /abs/build/cpu_interpolation_xcoords
Run only in a parent-coordinated exclusive measurement lane. The lock excludes
cooperating local benchmarks; it cannot certify host-wide isolation.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import statistics
import re
import subprocess
import time
from cpu_venue import add_arguments, validate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source-sha", required=True,
                        help="Full source commit used to build the binary (caller attestation, not driver HEAD)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "kernel")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("--source-sha must be a full 40-character lowercase SHA")
    venue = validate(args)
    binary = args.binary.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=True)
    if any(args.out.iterdir()):
        raise RuntimeError("Output directory is not empty; keep the first record and choose a new --out")
    env = dict(os.environ, OMP_DYNAMIC="FALSE", OMP_PROC_BIND="close", OMP_PLACES="cores",
               OMP_WAIT_POLICY="PASSIVE", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    repo = Path(__file__).resolve().parents[2]
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    receipt = {"driver_source": source, "binary": str(binary), "binary_sha256": digest(binary),
               "source": {"commit": args.source_sha, "origin": "caller-attested build source SHA", "dirty": None},
               "wall_start_unix": time.time(), "venue": venue,
               "environment": {k: env[k] for k in ("OMP_DYNAMIC", "OMP_PROC_BIND", "OMP_PLACES",
                               "OMP_WAIT_POLICY", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
               "warmups_per_arm": 1, "pairs": 6, "order": "AB,BA,AB,BA,AB,BA",
               "reference": "frozen main116eb04 functions in the same executable",
               "scope": "kernel only; includes candidate cache allocation/setup, excludes reset/bit comparison",
               "isolation_limit": "cooperating lock only; no verified host-wide process inventory"}
    results = []
    with open("/tmp/motioncorr-bench.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for nx, ny, nf, threads, mode in [(3710, 3838, 24, 1, "sum"), (3710, 3838, 24, 4, "sum"),
                                          (512, 512, 16, 1, "frames"), (512, 512, 16, 4, "frames")]:
            mask = venue["masks"][threads]
            name = f"{nx}x{ny}x{nf}-j{threads}-{mode}"
            command = ["taskset", "-c", mask, str(binary), "--bench", str(nx), str(ny), str(nf),
                       str(threads), "6", mode, "affinity-confirmed"]
            # Independently query the same taskset mask before starting the workload.
            observed = json.loads(subprocess.check_output(
                ["taskset", "-c", mask, "python3", "-c",
                 "import json,os; print(json.dumps(sorted(os.sched_getaffinity(0))))"], env=env))
            if observed != venue["requested_affinity"][threads]:
                raise RuntimeError(f"taskset did not establish requested CPU mask: {mask}, observed {observed}")
            completed = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            raw = args.out / (name + ".jsonl")
            raw.write_bytes(completed.stdout)
            (args.out / (name + ".stderr")).write_bytes(completed.stderr)
            if completed.returncode:
                raise RuntimeError(f"{name} exited {completed.returncode}; raw stdout/stderr retained")
            pairs = [json.loads(line) for line in completed.stdout.splitlines() if line]
            assert len(pairs) == 6 and all(p["bitwise_equal"] for p in pairs)
            reference = [p["reference_seconds"] for p in pairs]
            candidate = [p["candidate_seconds"] for p in pairs]
            deltas = [b - a for a, b in zip(reference, candidate)]
            paired_median = statistics.median(deltas)
            result = {"name": name, "command": command, "affinity": observed,
                      "reference_median_seconds": statistics.median(reference),
                      "candidate_median_seconds": statistics.median(candidate),
                      "paired_deltas_seconds": deltas, "paired_median_seconds": paired_median,
                      "paired_median_ci_96_875_percent_seconds": [min(deltas), max(deltas)],
                      "paired_mad_scaled_seconds": 1.4826 * statistics.median(abs(d - paired_median) for d in deltas),
                      "all_pairs_faster": all(d < 0 for d in deltas),
                      "bitwise_equal": True, "raw_sha256": digest(raw)}
            results.append(result)
            print(json.dumps(result), flush=True)
            (args.out / "results.json").write_text(json.dumps({"receipt": receipt, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
