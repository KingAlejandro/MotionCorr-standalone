#!/usr/bin/env python3
"""Interleaved paired end-to-end timing, main head vs reviewed issue #77 candidate.

Both binaries run inside one invocation of this script, on one host, under one
CPU pin, with identical options and identical input, alternating which side goes
first across blocks. Each block yields one paired difference; the blocks are the
unit of evidence, not the individual runs.

What this does NOT establish, and the report says so in the artefact itself:

  * nothing about a cumulative speedup across a series of merges. Any figure
    quoted from an earlier cumulative head is that head's figure, not this one's;
  * nothing causal from runs on different hosts, different allocations, or from
    a single run;
  * nothing about CPU/CUDA agreement or scientific equivalence -- this is one
    backend compared against itself at two code heads.

Page cache cannot be dropped without root, so a discarded warm-up run precedes
the blocks and is recorded as discarded rather than quietly dropped.

Stage breakdown is read from the runner's own TIMING table when the builds carry
-DTIMING=ON; when they do not, the stage section is reported absent instead of
being fabricated from wall time.
"""
import argparse
import hashlib
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from residency_witness import witness

OPTIONS = ["--use_own", "--dose_weighting", "--dose_per_frame", "1.277",
           "--patch_x", "5", "--patch_y", "5", "--bfactor", "150",
           "--gainref", "Movies/gain.mrc", "--seed", "1", "--gpu", "0"]

# "read movie                         : 12.34 sec (5678 microsec/operation)"
STAGE_RE = re.compile(r"^(?P<tag>\S.*?)\s*:\s*(?P<sec>[0-9]+\.?[0-9]*(?:[eE][+-]?[0-9]+)?)"
                      r"\s+sec\s+\((?P<usec>[0-9]+)\s+microsec/operation\)\s*$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_stages(stdout: str) -> dict:
    stages = {}
    for line in stdout.splitlines():
        match = STAGE_RE.match(line)
        if match:
            stages[match.group("tag")] = {
                "seconds": float(match.group("sec")),
                "microsec_per_operation": int(match.group("usec")),
            }
    return stages


def load_now() -> float:
    try:
        return float(Path("/proc/loadavg").read_text().split()[0])
    except OSError:
        return float("nan")


def one_run(binary: Path, cwd: Path, star: str, outdir: Path, threads: int,
            taskset_cpus: str) -> dict:
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    cmd = [str(binary), "--i", star, "--o", str(outdir), *OPTIONS, "--j", str(threads)]
    if taskset_cpus:
        cmd = ["taskset", "-c", taskset_cpus] + cmd
    load_before = load_now()
    sampler_log = outdir.with_suffix(".gpu.log").open("w")
    sampler = subprocess.Popen(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv", "--loop-ms=200"], stdout=sampler_log, stderr=subprocess.STDOUT)
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    wall = time.monotonic() - started
    sampler.terminate()
    sampler.wait()
    sampler_log.close()
    outdir.with_suffix(".stdout.log").write_text(proc.stdout)
    outdir.with_suffix(".stderr.log").write_text(proc.stderr)
    stages = parse_stages(proc.stdout)
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "wall_seconds": round(wall, 3),
        "load1_before": load_before,
        "load1_after": load_now(),
        "stages": stages,
        "stage_table_present": bool(stages),
        "resident_pipeline": witness(outdir),
        "gpu_samples": str(outdir.with_suffix(".gpu.log")),
        "native_cuda_markers": proc.stdout.count("Using CUDA acceleration on GPU device"),
        "micrographs_written": len(list((outdir / "Movies").glob("*.mrc"))),
        "stderr_tail": proc.stderr[-1500:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-binary", required=True, type=Path)
    parser.add_argument("--ref-label", default="main")
    parser.add_argument("--test-binary", required=True, type=Path)
    parser.add_argument("--test-label", default="candidate")
    parser.add_argument("--tutorial", required=True, type=Path)
    parser.add_argument("--input-star", default="movies.star")
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--taskset", default="",
                        help="CPU list passed to taskset -c for every run")
    args = parser.parse_args()

    args.work.mkdir(parents=True, exist_ok=True)
    sides = {args.ref_label: args.ref_binary, args.test_label: args.test_binary}

    report = {
        "what": f"interleaved paired end-to-end timing, {args.ref_label} vs {args.test_label}",
        "not_a_claim_about": [
            "any cumulative speedup across a series of merges",
            "speed measured on a different host or a different allocation",
            "CPU/CUDA agreement",
            "scientific equivalence",
        ],
        "host": platform.node(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "threads": args.threads,
        "taskset": args.taskset or "none",
        "options": OPTIONS,
        "input_star": args.input_star,
        "tutorial": str(args.tutorial),
        "binaries": {label: {"path": str(path), "sha256": sha256(path)}
                     for label, path in sides.items()},
        "page_cache": "not dropped (no root); one discarded warm-up run precedes the blocks",
        "blocks": [],
    }

    warm = one_run(args.ref_binary, args.tutorial, args.input_star,
                   args.work / "warmup", args.threads, args.taskset)
    report["discarded_warmup"] = warm
    if warm["exit_code"] != 0:
        report["overall"] = "UNRUN"
        report["reason"] = "warm-up run exited nonzero"
        args.json.write_text(json.dumps(report, indent=2) + "\n")
        print("warm-up failed:", warm["stderr_tail"][-400:])
        return 1

    for index in range(args.blocks):
        # Alternate which side runs first so a monotonic drift in machine state
        # cannot favour one side systematically.
        order = ([args.ref_label, args.test_label] if index % 2 == 0
                 else [args.test_label, args.ref_label])
        block = {"block": index + 1, "order": order, "runs": {}}
        for label in order:
            block["runs"][label] = one_run(sides[label], args.tutorial, args.input_star,
                                           args.work / f"t_{label}_b{index + 1}",
                                           args.threads, args.taskset)
        ref = block["runs"][args.ref_label]
        test = block["runs"][args.test_label]
        block["paired"] = {
            "ref_wall_seconds": ref["wall_seconds"],
            "test_wall_seconds": test["wall_seconds"],
            "delta_seconds": round(test["wall_seconds"] - ref["wall_seconds"], 3),
            "test_over_ref": (round(test["wall_seconds"] / ref["wall_seconds"], 4)
                              if ref["wall_seconds"] else None),
            "both_completed": ref["exit_code"] == 0 and test["exit_code"] == 0 and ref["native_cuda_markers"] >= 1 and test["native_cuda_markers"] >= 1 and ref["resident_pipeline"]["pass"] and test["resident_pipeline"]["pass"] and ref["micrographs_written"] == 24 and test["micrographs_written"] == 24,
            "same_micrograph_count": ref["micrographs_written"] == test["micrographs_written"],
            "micrographs": ref["micrographs_written"],
        }
        report["blocks"].append(block)
        print(f"block {index + 1} order={order} "
              f"{args.ref_label}={ref['wall_seconds']}s "
              f"{args.test_label}={test['wall_seconds']}s "
              f"ratio={block['paired']['test_over_ref']}")

    ratios = [b["paired"]["test_over_ref"] for b in report["blocks"]
              if b["paired"]["test_over_ref"] is not None]
    deltas = [b["paired"]["delta_seconds"] for b in report["blocks"]]
    report["paired_summary"] = {
        "blocks": len(report["blocks"]),
        "ratios_test_over_ref": ratios,
        "median_ratio": round(statistics.median(ratios), 4) if ratios else None,
        "min_ratio": min(ratios) if ratios else None,
        "max_ratio": max(ratios) if ratios else None,
        "deltas_seconds": deltas,
        "median_delta_seconds": round(statistics.median(deltas), 3) if deltas else None,
        "all_blocks_completed": all(b["paired"]["both_completed"] for b in report["blocks"]),
        "all_blocks_same_micrograph_count": all(b["paired"]["same_micrograph_count"]
                                                for b in report["blocks"]),
    }

    # Stage breakdown, block-median per tag, only for tags both sides report.
    stage_tables = all(b["runs"][l]["stage_table_present"]
                       for b in report["blocks"] for l in sides)
    if stage_tables:
        tags = set.intersection(*[set(b["runs"][l]["stages"])
                                  for b in report["blocks"] for l in sides])
        breakdown = {}
        for tag in sorted(tags):
            ref_vals = [b["runs"][args.ref_label]["stages"][tag]["seconds"]
                        for b in report["blocks"]]
            test_vals = [b["runs"][args.test_label]["stages"][tag]["seconds"]
                         for b in report["blocks"]]
            breakdown[tag] = {
                f"{args.ref_label}_median_seconds": round(statistics.median(ref_vals), 3),
                f"{args.test_label}_median_seconds": round(statistics.median(test_vals), 3),
                "median_delta_seconds": round(statistics.median(test_vals)
                                              - statistics.median(ref_vals), 3),
            }
        report["stage_breakdown"] = breakdown
    else:
        report["stage_breakdown"] = None
        report["stage_breakdown_absent_reason"] = (
            "builds do not carry -DTIMING=ON, so the runner emits no stage table")

    report["overall"] = ("MEASURED" if report["paired_summary"]["all_blocks_completed"]
                         and report["paired_summary"]["all_blocks_same_micrograph_count"]
                         else "INVALID")
    report["interpretation"] = (
        "Paired, interleaved, same host, same pin, same options, same input. "
        "Reported as a measurement of these two heads on this machine only.")

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["paired_summary"], indent=2))
    print("overall:", report["overall"])
    return 0 if report["overall"] == "MEASURED" else 1


if __name__ == "__main__":
    sys.exit(main())
