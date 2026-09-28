#!/usr/bin/env python3
"""Run one stock MotionCorr process per physical GPU over disjoint STAR shards.

No production scheduler and no source change: a worker is the existing binary
given a subset of the movies and its own output directory. The serial movie loop
is already exactly the worker loop.

Why distinct output directories. Per-movie outputs are unique, but every process
also writes fixed-path aggregates at the end of its run --
corrected_micrographs.star through a .tmp and rename, logfile.pdf, header.pdf,
batch.pdf, the read-modify-write all_batches.pdf, the <pdf>.lst scratch, the six
corrected_micrographs_*.eps, and gain.mrc. Concurrent writers race on all of
them. Separate directories avoid every one with zero production change; sharing
one output root needs coordinator support that is deliberately not in this PR.

Why whole movies. Per-movie state that is process-global -- init_random_generator
called per movie, and the file-scope device cache in
src/acc/cuda/cuda_fft_prep.cu -- makes process isolation the correct unit. Whole
movies also keep reduction and peak-fit ordering inside one device, so no
numerical contract changes. This is the first experiment, not a claimed optimum.

Device identity. Each worker is pinned with CUDA_VISIBLE_DEVICES=GPU-<uuid> and
passes --gpu 0, so its ordinal cannot be mistaken for a claim about which GPU
ran the work. The launcher never initializes CUDA, so no worker inherits an
already-initialized context. While the workers run, nvidia-smi compute-apps
records are sampled so the physical GPU each worker PID actually held a context
on is witnessed rather than assumed.

This tool measures nothing and claims no speedup. It records wall time for
bookkeeping only; #26 owns this round's benchmark matrix.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_witness  # noqa: E402
import partition_star  # noqa: E402


class Sampler(threading.Thread):
    """Poll nvidia-smi compute-apps while the workers run."""

    def __init__(self, interval: float):
        super().__init__(daemon=True)
        self.interval = interval
        self.samples: list[dict[str, object]] = []
        self.errors: list[str] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.samples.append({"t": time.time(), "apps": gpu_witness.compute_apps()})
            except gpu_witness.WitnessError as exc:
                self.errors.append(str(exc))
                return
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()

    def observations(self) -> list[dict[str, str]]:
        flat = []
        for s in self.samples:
            flat.extend(s["apps"])  # type: ignore[arg-type]
        return flat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--star", required=True, help="full input movies STAR")
    ap.add_argument("--out", required=True, help="run root; must not already exist")
    ap.add_argument("--binary", required=True)
    ap.add_argument("--devices", default=None,
                    help="comma-separated nvidia-smi indices or GPU UUID prefixes; "
                         "one worker per entry. Omit for CPU workers.")
    ap.add_argument("--workers", type=int, default=None,
                    help="worker count when --devices is omitted (CPU workers)")
    ap.add_argument("--cpus", default=None, help="taskset -c mask applied to every worker")
    ap.add_argument("--sample-interval", type=float, default=0.5)
    ap.add_argument("--no-witness", action="store_true",
                    help="skip GPU witnessing; only valid with CPU workers")
    ap.add_argument("worker_args", nargs=argparse.REMAINDER,
                    help="everything after -- is passed to every worker verbatim")
    a = ap.parse_args(argv)

    out = Path(a.out)
    if out.exists():
        print(f"FAIL: refusing to reuse existing --out {out}", file=sys.stderr)
        return 2

    devices: list[dict[str, str]] = []
    if a.devices:
        try:
            devices = gpu_witness.select([s for s in a.devices.split(",") if s.strip()])
        except gpu_witness.WitnessError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        n = len(devices)
        if a.workers is not None and a.workers != n:
            print(f"FAIL: --workers {a.workers} contradicts {n} device(s)", file=sys.stderr)
            return 2
    else:
        if a.workers is None:
            print("FAIL: give --devices or --workers", file=sys.stderr)
            return 2
        if not a.no_witness:
            print("FAIL: --workers without --devices runs CPU workers; pass --no-witness "
                  "to say so explicitly, so a CPU run is never filed as a GPU result",
                  file=sys.stderr)
            return 2
        n = a.workers

    out.mkdir(parents=True)
    shard_dir = out / "shards"
    rc = partition_star.main(["--star", a.star, "--n", str(n),
                              "--outdir", str(shard_dir), "--prefix", "shard"])
    if rc != 0:
        print(f"FAIL: partitioning exited {rc}", file=sys.stderr)
        return rc
    manifest = json.loads((shard_dir / "shard_manifest.json").read_text())

    extra = list(a.worker_args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    sampler = None
    if devices and not a.no_witness:
        sampler = Sampler(a.sample_interval)
        sampler.start()

    procs: list[tuple[int, subprocess.Popen, Path]] = []
    started = time.time()
    try:
        for k in range(n):
            wdir = out / f"w{k}"
            wdir.mkdir()
            env = dict(os.environ)
            cmd: list[str] = []
            if a.cpus:
                cmd += ["taskset", "-c", a.cpus]
            cmd += [a.binary,
                    "--i", str(shard_dir / f"shard_{n}way_{k}.star"),
                    "--o", str(wdir) + os.sep]
            if devices:
                env = gpu_witness.worker_env(devices[k], env)
                cmd += ["--gpu", "0"]
            cmd += extra
            log = (wdir / "run.log").open("w")
            # exec a fresh process: nothing in this launcher has touched CUDA, so
            # no already-initialized context is ever inherited.
            p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                 start_new_session=True)
            procs.append((k, p, wdir))
            (wdir / "command.json").write_text(json.dumps({
                "index": k, "command": cmd, "pid": p.pid,
                "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"),
                "device": devices[k] if devices else None,
            }, indent=2) + "\n")

        results = []
        for k, p, wdir in procs:
            rc = p.wait()
            results.append({"index": k, "pid": p.pid, "returncode": rc,
                            "log": str(wdir / "run.log")})
    except BaseException:
        # Terminate only the children this launcher started, by their own process
        # group, so nothing else on a shared box is touched.
        for k, p, _ in procs:
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
        for k, p, wdir in procs:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        raise
    finally:
        if sampler is not None:
            sampler.stop()
            sampler.join(timeout=5)

    wall = time.time() - started
    status: dict[str, object] = {
        "input_star": a.star,
        "binary": a.binary,
        "n_workers": n,
        "worker_args": extra,
        "cpus": a.cpus,
        "wall_seconds": round(wall, 3),
        "wall_seconds_note": "bookkeeping only; this tool makes no throughput claim and "
                             "is not a benchmark. #26 owns the measurement matrix.",
        "manifest": str(shard_dir / "shard_manifest.json"),
        "workers": results,
        "devices": devices or None,
    }

    verdict_ok = all(r["returncode"] == 0 for r in results)

    if sampler is not None:
        expected = {p.pid: devices[k]["uuid"] for k, p, _ in procs}
        witness = gpu_witness.check_observations(expected, sampler.observations())
        witness["sampler_errors"] = sampler.errors
        witness["n_samples"] = len(sampler.samples)
        status["gpu_witness"] = witness
        if not witness["all_pids_witnessed_on_intended_distinct_devices"]:
            verdict_ok = False
    elif devices:
        status["gpu_witness"] = "skipped by --no-witness; no device claim is supported"

    status["verdict"] = "PASS" if verdict_ok else "FAIL"
    (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    print(json.dumps({"n_workers": n, "wall_seconds": status["wall_seconds"],
                      "returncodes": [r["returncode"] for r in results],
                      "verdict": status["verdict"]}, indent=2))
    if not verdict_ok:
        print(f"FAIL: see {out / 'status.json'}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
