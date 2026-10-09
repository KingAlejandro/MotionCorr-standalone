#!/usr/bin/env python3
"""Fixed-CPU-budget scaling of the complete dataset endpoint (run_dataset.py).

Each measured run is timed from launching run_dataset.py to publication of the
joint STAR and the report (the later mtime of merged/corrected_micrographs.star
and merged/logfile.pdf). Arms rotate within each rep and workloads alternate, so
host drift lands on every arm. Each arm is compared with the first arm inside the
same rep through paired() from the profiling kit (tools/profiling/lib/stats.py,
loaded by path and recorded by sha256).

  bench_scaling.py --binary B --data D --workload 24=movies.star \
      --arm '1x32=GPU-aaa@72-103' --arm '2x16=GPU-aaa,GPU-bbb@72-87;88-103' \
      --arm-locks '1x32=/tmp/bench.lock,/tmp/gpu2.lock' ... \
      --stats-lib .../stats.py --identity-ref REF --work W --out result.json \
      -- --use_own ... --j 8

--identity-ref is a single-process single-GPU output directory of the same
binary, input and worker arguments; the first measured run of every arm on the
workload named by --identity-workload is compared with it, then deleted like
every other run directory. Only the summaries are kept.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Launcher and coordinator files that exist only in the multi-GPU tree.
LAUNCHER_ONLY = {"_workers"}
PUBLICATION = ("corrected_micrographs.star", "logfile.pdf")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cpu_times() -> dict[int, tuple[int, int]]:
    out = {}
    for line in Path("/proc/stat").read_text().splitlines():
        if line.startswith("cpu") and line[3].isdigit():
            f = line.split()
            v = list(map(int, f[1:]))
            out[int(f[0][3:])] = (sum(v), v[3] + v[4])
    return out


def busy_fraction(a, b, cpus) -> dict[int, float]:
    return {c: round(1 - (b[c][1] - a[c][1]) / max(1, b[c][0] - a[c][0]), 3) for c in cpus}


def host_snapshot(cpus) -> dict:
    a = cpu_times()
    time.sleep(1.0)
    b = cpu_times()
    apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory",
                           "--format=csv,noheader"], capture_output=True, text=True).stdout
    busy = busy_fraction(a, b, cpus)
    return {"loadavg": Path("/proc/loadavg").read_text().split()[:3],
            "arm_cpus_busy_over_0.5": sorted(c for c, v in busy.items() if v > 0.5),
            "arm_cpus_mean_busy": round(sum(busy.values()) / len(busy), 3),
            "gpu_compute_apps": [l.strip() for l in apps.splitlines() if l.strip()]}


def parse_cpus(spec: str) -> set[int]:
    out = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def fmt_cpus(cpus: set[int]) -> str:
    s = sorted(cpus)
    runs, start = [], s[0]
    for x, y in zip(s, s[1:] + [None]):
        if y != x + 1:
            runs.append(f"{start}-{x}" if x != start else str(x))
            start = y
    return ",".join(runs)


def parse_arm(text: str) -> dict:
    name, _, rest = text.partition("=")
    devices, _, masks = rest.partition("@")
    masks = masks.split(";")
    devices = devices.split(",")
    if len(devices) != len(masks):
        raise SystemExit(f"arm {name}: {len(devices)} devices but {len(masks)} masks")
    union = set().union(*(parse_cpus(m) for m in masks))
    return {"name": name, "devices": devices, "masks": masks, "union": fmt_cpus(union),
            "n_cpus": len(union)}


def products(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] not in LAUNCHER_ONLY}


def identity(ref: Path, merged: Path) -> dict:
    """MRC bytes outside the label block, path-normalised STARs, and presence."""
    rp, mp = products(ref), products(merged)
    result = {"missing": sorted(rp - mp), "extra": sorted(mp - rp), "mrc_compared": 0,
              "mrc_differ": [], "star_compared": 0, "star_differ": [], "present_only": 0}
    ref_prefix, merged_prefix = str(ref.resolve()) + "/", str(merged.resolve()) + "/"
    for rel in sorted(rp & mp):
        a, b = (ref / rel).read_bytes(), (merged / rel).read_bytes()
        if rel.endswith(".mrc"):
            result["mrc_compared"] += 1
            # 224..1024 holds the ten 80-byte labels, which carry a timestamp.
            if a[:224] != b[:224] or a[1024:] != b[1024:]:
                result["mrc_differ"].append(rel)
        elif rel.endswith(".star"):
            result["star_compared"] += 1
            na = a.decode().replace(ref_prefix, "OUT/")
            nb = b.decode().replace(merged_prefix, "OUT/")
            if na != nb:
                result["star_differ"].append(rel)
        else:
            result["present_only"] += 1  # logs, EPS and PDF carry times and dates
    joint = "corrected_micrographs.star"
    result["joint_star_published"] = (merged / joint).is_file()
    result["kinds_present"] = sorted({Path(r).suffix for r in mp})
    result["identical"] = (not result["missing"] and not result["extra"]
                           and not result["mrc_differ"] and not result["star_differ"]
                           and result["joint_star_published"] and result["mrc_compared"] > 0)
    return result


class Locks:
    def __init__(self, paths):
        self.paths, self.files = paths, []

    def __enter__(self):
        t = time.time()
        for p in self.paths:  # caller passes bench lock first, then GPUs in index order
            f = open(p, "a")
            fcntl.flock(f, fcntl.LOCK_EX)
            self.files.append(f)
        self.wait_s = round(time.time() - t, 3)
        return self

    def __exit__(self, *exc):
        for f in reversed(self.files):
            fcntl.flock(f, fcntl.LOCK_UN)
            f.close()


def summarise_run(run: Path, t0: float, t_exit: float, rc: int) -> dict:
    merged = run / "merged"
    stamps = [(merged / n).stat().st_mtime for n in PUBLICATION if (merged / n).is_file()]
    rec = {"rc": rc, "exit_s": round(t_exit - t0, 3),
           "publication_s": round(max(stamps) - t0, 3) if len(stamps) == len(PUBLICATION) else None}
    ds_path = run / "dataset_status.json"
    if not ds_path.is_file():
        rec["failure"] = "dataset_status.json missing"
        return rec
    ds = json.loads(ds_path.read_text())
    rec.update({k: ds.get(k) for k in ("verdict", "dataset_ready", "dataset_wall_s",
                                       "worker_phase_wall_s", "aggregate_phase_wall_s",
                                       "aggregate_cpu_mask", "ownership_mode", "failure")})
    agg_path = run / "aggregate.json"
    if agg_path.is_file():
        agg = json.loads(agg_path.read_text())
        # Absent in reports from tools before aggregate staging was reworked.
        rec["merge_timing_s"] = agg.get("timing_seconds")
        rec["merge_staging"] = {k: v for k, v in (agg.get("staging") or {}).items()
                                if k != "seconds"} or None
    tree = ds.get("tree_rss") or {}
    rec["tree_rss_peak_sum_kib"] = tree.get("peak_simultaneous_sum_rss_kib")
    rec["tree_rss_status"] = tree.get("status")
    ws_path = run / "workers" / "status.json"
    if ws_path.is_file():
        ws = json.loads(ws_path.read_text())
        ends = [w["wall_seconds"] for w in ws["workers"]]
        rec["workers"] = [{
            "index": w["index"], "cpu_mask": w["cpu_mask"],
            "busy_span_s": w["wall_seconds"],
            # Workers start together, so the idle tail is time after this worker
            # exited while another was still running.
            "idle_tail_s": round(max(ends) - w["wall_seconds"], 3),
            "rss_hwm_kib": w["rss_hwm_kib"], "rss_status": w["rss_status"],
            "cpu_seconds_sampled": w["cpu_seconds_sampled"],
            "n_products": w["phases"]["n_products"],
            "setup_s": w["phases"]["setup_seconds"], "tail_s": w["phases"]["tail_seconds"],
            "binary_movie_wall_sum": w["phases"]["binary_movie_wall_sum"],
            "exit_digest_s": (w.get("exit_digest") or {}).get("seconds"),
        } for w in ws["workers"]]
        rec["rss_hwm_total_kib"] = (sum(w["rss_hwm_kib"] for w in ws["workers"])
                                    if all(w["rss_hwm_kib"] is not None for w in ws["workers"])
                                    else None)
        rec["sampled_peak_gpu_memory_mib"] = ws.get("sampled_peak_gpu_memory_mib")
        rec["worker_cpu_seconds_total"] = ws.get("cpu_seconds_total")
        rec["mean_cores_busy"] = ws.get("mean_cores_busy")
        rec["cpu_budget_covered"] = ws.get("cpu_budget_covered")
        rec["final_worker_tail_s"] = ws.get("final_worker_tail_seconds")
        witness = ws.get("gpu_witness")
        rec["device_witness_ok"] = (witness.get("all_pids_witnessed_on_intended_distinct_devices")
                                    if isinstance(witness, dict) else None)
    return rec


def launch(a, arm, star, run: Path) -> tuple[float, float, int]:
    launcher = (f"--devices {','.join(arm['devices'])} --cpus {shlex.quote(';'.join(arm['masks']))} "
                f"--cpu-budget {arm['n_cpus']}")
    tools = Path(arm.get("tools") or HERE)
    cmd = ["taskset", "-c", arm["union"], sys.executable, str(tools / "run_dataset.py"),
           "--binary", a.binary, "--star", star, "--out", str(run),
           "--launcher-args=" + launcher, "--", *a.worker_args]
    log = run.with_suffix(".console.log")
    with log.open("w") as fh:
        t0 = time.time()
        rc = subprocess.run(cmd, cwd=a.data, stdout=fh, stderr=subprocess.STDOUT).returncode
        t_exit = time.time()
    return t0, t_exit, rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--data", required=True, help="cwd holding Movies/ and the STARs")
    ap.add_argument("--workload", action="append", required=True, help="NAME=STAR")
    ap.add_argument("--arm", action="append", required=True,
                    help="NAME=UUID[,UUID..]@MASK[;MASK..]; the first arm is the paired baseline")
    ap.add_argument("--arm-locks", action="append", default=[],
                    help="NAME=PATH[,PATH..] taken in order around each run (warm-up included) of that arm")
    ap.add_argument("--arm-tools", action="append", default=[],
                    help="NAME=DIR: run that arm's run_dataset.py from DIR instead of this "
                         "tree, to compare two versions of the tools on one binary")
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--stats-lib", required=True)
    ap.add_argument("--stats-commit", default=None)
    ap.add_argument("--identity-ref", default=None)
    ap.add_argument("--identity-workload", default=None)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provenance", action="append", default=[], help="KEY=VALUE recorded verbatim")
    ap.add_argument("worker_args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    a.worker_args = a.worker_args[1:] if a.worker_args[:1] == ["--"] else a.worker_args
    # run_dataset.py runs with cwd=--data, so every path it is handed is absolute.
    a.binary, a.data = str(Path(a.binary).resolve()), str(Path(a.data).resolve())
    a.work, a.out = str(Path(a.work).resolve()), str(Path(a.out).resolve())
    a.identity_ref = str(Path(a.identity_ref).resolve()) if a.identity_ref else None

    spec = importlib.util.spec_from_file_location("stats", a.stats_lib)
    stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stats)

    arms = [parse_arm(x) for x in a.arm]
    arm_tools = {k: str(Path(v).resolve()) for k, v in (x.split("=", 1) for x in a.arm_tools)}
    for arm in arms:
        arm["tools"] = arm_tools.get(arm["name"])
        arm["tools_sha256"] = {p.name: sha256(p) for p in
                               sorted(Path(arm["tools"] or HERE).glob("*.py"))}
    locks = {k: v.split(",") for k, v in (x.split("=", 1) for x in a.arm_locks)}
    workloads = [tuple(x.split("=", 1)) for x in a.workload]
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=False)
    all_cpus = set().union(*(parse_cpus(x["union"]) for x in arms))
    result = {
        "provenance": {
            "binary": a.binary, "binary_sha256": sha256(Path(a.binary)),
            "tools_sha256": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
            "stats_lib": a.stats_lib, "stats_lib_sha256": sha256(Path(a.stats_lib)),
            "stats_commit": a.stats_commit,
            "inputs": {name: {"star": star, "sha256": sha256(Path(a.data) / star)}
                       for name, star in workloads},
            "worker_args": a.worker_args, "arms": arms, "locks": locks, "reps": a.reps,
            "hostname": os.uname().nodename,
            "extra": dict(x.split("=", 1) for x in a.provenance),
            "timing": "launch of run_dataset.py to the later mtime of "
                      + " and ".join("merged/" + n for n in PUBLICATION),
        },
        "host_before": host_snapshot(all_cpus), "warmup": [], "runs": [], "identity": {},
    }
    out = Path(a.out)

    def run_one(arm, wname, star, tag, measured):
        run = work / tag
        # Warm-ups launch the same GPU workload, so they take the same locks.
        with Locks(locks.get(arm["name"], [])) as held:
            before = host_snapshot(parse_cpus(arm["union"]))
            t0, t_exit, rc = launch(a, arm, star, run)
            after = host_snapshot(parse_cpus(arm["union"]))
        rec = summarise_run(run, t0, t_exit, rc)
        rec.update({"arm": arm["name"], "workload": wname, "tag": tag,
                    "lock_wait_s": held.wait_s, "host_before": before, "host_after": after})
        if (measured and a.identity_ref and wname == (a.identity_workload or workloads[0][0])
                and arm["name"] not in result["identity"]):
            result["identity"][arm["name"]] = identity(Path(a.identity_ref), run / "merged")
        if rc == 0:
            shutil.rmtree(run)
            run.with_suffix(".console.log").unlink()
        else:
            rec["kept"] = str(run)  # a failed run is evidence; keep it for inspection
        print(json.dumps({k: rec.get(k) for k in ("tag", "rc", "publication_s", "verdict")}),
              flush=True)
        return rec

    # A cold binary costs ~0.9 s on first execution; one discarded run per arm.
    for arm in arms:
        result["warmup"].append(run_one(arm, workloads[0][0], workloads[0][1],
                                        f"warmup-{arm['name']}", measured=False))
    for rep in range(a.reps):
        order = arms[rep % len(arms):] + arms[:rep % len(arms)]
        wl = workloads if rep % 2 == 0 else workloads[::-1]
        for wname, star in wl:
            for arm in order:
                rec = run_one(arm, wname, star, f"r{rep}-{wname}-{arm['name']}", measured=True)
                rec["rep"], rec["position"] = rep, [x["name"] for x in order].index(arm["name"])
                result["runs"].append(rec)
                out.write_text(json.dumps(result, indent=2) + "\n")  # survive an interruption
    result["host_after"] = host_snapshot(all_cpus)

    summary = {}
    for wname, _ in workloads:
        base = arms[0]["name"]
        by = {(r["arm"], r["rep"]): r for r in result["runs"]
              if r["workload"] == wname and r["rc"] == 0 and r.get("publication_s") is not None}
        wsum = {}
        for arm in arms:
            vals = [by[(arm["name"], r)]["publication_s"] for r in range(a.reps) if (arm["name"], r) in by]
            q1, med, q3 = stats.quartiles(vals) if len(vals) >= 2 else (None, None, None)
            entry = {"n": len(vals), "median_s": med, "q1_s": q1, "q3_s": q3,
                     "iqr_s": (q3 - q1) if q1 is not None else None, "publication_s": vals}
            if arm["name"] != base:
                pairs = [{"a": by[(base, r)]["publication_s"], "b": by[(arm["name"], r)]["publication_s"],
                          "order": "AB" if by[(base, r)]["position"] < by[(arm["name"], r)]["position"] else "BA"}
                         for r in range(a.reps) if (base, r) in by and (arm["name"], r) in by]
                entry["paired_vs_" + base] = stats.paired(pairs)
                entry["speedup_vs_" + base] = (round(wsum[base]["median_s"] / med, 3)
                                               if med and wsum[base]["median_s"] else None)
            runs = [by[(arm["name"], r)] for r in range(a.reps) if (arm["name"], r) in by]
            def med_of(f):
                v = [x for x in map(f, runs) if x is not None]
                return stats.median(v) if v else None
            entry["median_rss_hwm_total_kib"] = med_of(lambda r: r.get("rss_hwm_total_kib"))
            entry["median_rss_hwm_per_worker_kib"] = med_of(
                lambda r: max((w["rss_hwm_kib"] for w in r.get("workers", []) if w["rss_hwm_kib"] is not None), default=None))
            entry["median_max_idle_tail_s"] = med_of(
                lambda r: max((w["idle_tail_s"] for w in r.get("workers", [])), default=None))
            entry["median_max_busy_span_s"] = med_of(
                lambda r: max((w["busy_span_s"] for w in r.get("workers", [])), default=None))
            entry["median_aggregate_phase_s"] = med_of(lambda r: r.get("aggregate_phase_wall_s"))
            entry["median_worker_phase_s"] = med_of(lambda r: r.get("worker_phase_wall_s"))
            if arm["name"] != base:
                for field in ("aggregate_phase_wall_s", "worker_phase_wall_s"):
                    pairs = [{"a": by[(base, r)][field], "b": by[(arm["name"], r)][field],
                              "order": "AB" if by[(base, r)]["position"]
                              < by[(arm["name"], r)]["position"] else "BA"}
                             for r in range(a.reps) if (base, r) in by and (arm["name"], r) in by
                             and by[(base, r)].get(field) is not None
                             and by[(arm["name"], r)].get(field) is not None]
                    entry[f"paired_{field}_vs_{base}"] = stats.paired(pairs) if pairs else None
            peaks = {}
            for r in runs:
                for uuid, mib in (r.get("sampled_peak_gpu_memory_mib") or {}).items():
                    if mib is not None:
                        peaks[uuid] = max(peaks.get(uuid, 0.0), mib)
            entry["max_sampled_peak_gpu_memory_mib"] = peaks or None
            wsum[arm["name"]] = entry
        summary[wname] = wsum
    result["summary"] = summary
    out.write_text(json.dumps(result, indent=2) + "\n")
    failed = [r["tag"] for r in result["runs"] if r["rc"] != 0]
    ident_bad = [k for k, v in result["identity"].items() if not v["identical"]]
    print(json.dumps({"failed_runs": failed, "identity_failures": ident_bad,
                      "summary": {w: {k: (v["median_s"], v.get("speedup_vs_" + arms[0]["name"]))
                                      for k, v in s.items()} for w, s in summary.items()}}, indent=2))
    return 1 if failed or ident_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
