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
import contextlib
import datetime
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_witness  # noqa: E402
import partition_star  # noqa: E402

_LAUNCHER_SIGNALS = (signal.SIGINT, signal.SIGTERM)
_TERMINATE_GRACE_SECONDS = 5.0
_KILL_REAP_SECONDS = 5.0
_signal_deferral_depth = 0
_pending_launcher_signal: int | None = None


class LauncherInterrupted(Exception):
    def __init__(self, signum: int):
        super().__init__(f"launcher interrupted by signal {signum}")
        self.signum = signum


def _install_signal_handlers() -> dict[int, object]:
    global _signal_deferral_depth, _pending_launcher_signal
    _signal_deferral_depth = 0
    _pending_launcher_signal = None
    previous = {sig: signal.getsignal(sig) for sig in _LAUNCHER_SIGNALS}

    def interrupt(signum, _frame):
        global _pending_launcher_signal
        if _signal_deferral_depth:
            if _pending_launcher_signal is None:
                _pending_launcher_signal = signum
            return
        raise LauncherInterrupted(signum)

    for sig in _LAUNCHER_SIGNALS:
        signal.signal(sig, interrupt)
    return previous


def _ignore_launcher_signals() -> None:
    for sig in _LAUNCHER_SIGNALS:
        signal.signal(sig, signal.SIG_IGN)


def _restore_signal_handlers(previous: dict[int, object]) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


@contextlib.contextmanager
def _defer_launcher_signals():
    """Record interruption only after a just-started child/thread is owned.

    Defer the Python handler, not the OS signal mask: blocking around Popen
    would leave SIGINT/SIGTERM blocked in every worker across exec.
    Python signal handlers run on the main thread, where this context is used.
    """
    global _signal_deferral_depth, _pending_launcher_signal
    _signal_deferral_depth += 1
    try:
        yield
    finally:
        _signal_deferral_depth -= 1
        if _signal_deferral_depth == 0 and _pending_launcher_signal is not None:
            signum = _pending_launcher_signal
            _pending_launcher_signal = None
            raise LauncherInterrupted(signum)


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_groups(procs: list[tuple[int, subprocess.Popen, Path]],
                              grace_seconds: float | None = None) -> None:
    """Terminate and reap only the process groups started by this launcher.

    A worker's session/process-group id is its PID because it was started with
    ``start_new_session=True``. Signal the group even if its leader has already
    exited: grandchildren may still be running in that owned group.
    """
    groups = sorted({proc.pid for _, proc, _ in procs})
    if grace_seconds is None:
        grace_seconds = _TERMINATE_GRACE_SECONDS
    for pgid in groups:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < deadline and any(_process_group_exists(g) for g in groups):
        for _, proc, _ in procs:
            proc.poll()
        time.sleep(0.05)

    for pgid in groups:
        if _process_group_exists(pgid):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    for _, proc, _ in procs:
        try:
            proc.wait(timeout=_KILL_REAP_SECONDS)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"could not reap owned worker PID {proc.pid}")

    deadline = time.monotonic() + _KILL_REAP_SECONDS
    while time.monotonic() < deadline and any(_process_group_exists(g) for g in groups):
        time.sleep(0.05)
    remaining = [g for g in groups if _process_group_exists(g)]
    if remaining:
        raise RuntimeError(f"owned worker process groups remain after SIGKILL: {remaining}")


def _iso(epoch: float) -> str:
    """UTC ISO-8601, so two arms recorded in different sessions are comparable."""
    return datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc).isoformat(timespec="milliseconds")


class Sampler(threading.Thread):
    """Poll nvidia-smi compute-apps while the workers run."""

    def __init__(self, interval: float):
        super().__init__(daemon=True)
        self.interval = interval
        self.samples: list[dict[str, object]] = []
        self.errors: list[str] = []
        # NOT self._stop: threading.Thread already defines a private _stop(), and
        # join() calls it through _wait_for_tstate_lock() once the thread has
        # finished. Shadowing it with an Event makes every join() raise
        # "'Event' object is not callable" after the workers have already run.
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.samples.append({"t": time.time(), "apps": gpu_witness.compute_apps()})
            except Exception as exc:  # noqa: BLE001
                # Deliberately not just WitnessError. Anything else -- an OSError
                # from subprocess under fork pressure, a MemoryError -- would
                # otherwise kill the thread through threading.excepthook, leave
                # self.errors empty and let join() succeed, so a sampler that died
                # two seconds into a three-minute run would certify the whole run
                # on the samples it happened to collect first.
                self.errors.append(f"{type(exc).__name__}: {exc}")
                return
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()

    def observations(self) -> list[dict[str, str]]:
        flat = []
        for s in self.samples:
            flat.extend(s["apps"])  # type: ignore[arg-type]
        return flat


class ResourceSampler(threading.Thread):
    """Poll /proc/<pid>/status for each worker while it runs.

    VmHWM is the kernel's own peak-resident counter, so a single successful read
    after the peak reports the true peak -- polling is only needed because the
    entry disappears when the process exits. A worker that peaks and exits
    between two polls is reported with whatever was last seen, which is a lower
    bound; the sampled interval is recorded so that is checkable rather than
    implied.

    Scope: the worker process only. MotionCorr spawns ghostscript children for
    the EPS/PDF output, and those are NOT included. This is a per-process
    figure, not a per-run host footprint.
    """

    def __init__(self, interval: float):
        super().__init__(daemon=True)
        self.interval = interval
        self.pids: dict[int, int] = {}
        self.hwm_kib: dict[int, int] = {}
        self.unavailable: str | None = None
        self._stop_event = threading.Event()

    def watch(self, pid: int, index: int) -> None:
        self.pids[pid] = index

    def run(self) -> None:
        if not Path("/proc").is_dir():
            self.unavailable = ("no /proc on this platform, so no resident-set "
                                "figure was sampled and none is claimed")
            return
        while not self._stop_event.is_set():
            for pid in list(self.pids):
                try:
                    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                        if line.startswith("VmHWM:"):
                            kib = int(line.split()[1])
                            if kib > self.hwm_kib.get(pid, 0):
                                self.hwm_kib[pid] = kib
                            break
                except (OSError, ValueError):
                    pass  # exited between listing and reading, or not readable
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()


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
    ap.add_argument("--cpus", default=None,
                    help="taskset -c mask for the workers. One mask applies to every "
                         "worker; N ';'-separated masks pin each worker separately, "
                         "e.g. --cpus '96-103;104-111'. Disjoint per-worker masks are "
                         "what keep two workers on one node from sharing cores, which "
                         "a single shared mask does not.")
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

    if a.devices and a.no_witness:
        # Before touching nvidia-smi, so the combination is refused on any host.
        print("FAIL: --no-witness with --devices would launch real GPU workers and "
              "still report PASS on exit codes alone, and merge_workers trusts that "
              "verdict -- certifying a device claim nothing observed. Drop "
              "--no-witness, or drop --devices to run on CPU.", file=sys.stderr)
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

    masks: list[str | None] = [None] * n
    if a.cpus:
        parts = [m.strip() for m in a.cpus.split(";") if m.strip()]
        if len(parts) == 1:
            masks = [parts[0]] * n
        elif len(parts) == n:
            masks = parts
        else:
            print(f"FAIL: --cpus has {len(parts)} masks for {n} worker(s); give one "
                  "mask for all or exactly one per worker", file=sys.stderr)
            return 2
        if shutil.which("taskset") is None:
            print("FAIL: --cpus needs taskset, which is not on PATH. Refusing rather "
                  "than running unpinned, which would silently break a shared-host "
                  "core budget.", file=sys.stderr)
            return 2

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

    # The launcher owns --i, --o and --gpu, and appends worker_args AFTER them.
    # IOParser::getOption returns the LAST occurrence (src/args.cpp), so a copied
    # command line carrying its own --i or --o silently redirects every worker to
    # one input and one shared output directory -- the exact collision distinct
    # worker directories exist to prevent -- while the children still exit zero
    # and the launcher still writes verdict PASS. Refuse before anything starts.
    OWNED = {"--i", "--o", "--gpu"}
    clashes = sorted({t for t in extra if t in OWNED})
    if clashes:
        print(f"FAIL: {', '.join(clashes)} is set by this launcher and must not appear "
              "in the worker arguments. The binary takes the last occurrence of a "
              "repeated option, so these would override the per-worker shard, output "
              "directory and device while the run still reported PASS.",
              file=sys.stderr)
        return 2

    sampler = None
    # Per-worker timing and resident set. These are the quantities a scaling
    # comparison needs and cannot reconstruct afterwards; recording them costs
    # nothing and changes no production source. This is bookkeeping, not a
    # benchmark: see docs/multi_gpu/SCALING_EXPERIMENT.md for what an
    # interpretable measurement additionally requires.
    resources = ResourceSampler(a.sample_interval)
    procs: list[tuple[int, subprocess.Popen, Path]] = []
    stamps: dict[int, dict[str, float]] = {}
    codes: dict[int, int] = {}
    waiters: list[threading.Thread] = []
    previous_handlers: dict[int, object] = {}
    sampler_started = False
    resources_started = False
    interrupted_signal: int | None = None
    started = time.time()
    try:
        previous_handlers = _install_signal_handlers()
        if devices and not a.no_witness:
            sampler = Sampler(a.sample_interval)
            with _defer_launcher_signals():
                sampler.start()
                sampler_started = True
        with _defer_launcher_signals():
            resources.start()
            resources_started = True

        for k in range(n):
            wdir = out / f"w{k}"
            wdir.mkdir()
            env = dict(os.environ)
            cmd: list[str] = []
            if masks[k]:
                cmd += ["taskset", "-c", masks[k]]
            cmd += [a.binary,
                    "--i", str(shard_dir / f"shard_{n}way_{k}.star"),
                    "--o", str(wdir) + os.sep]
            if devices:
                env = gpu_witness.worker_env(devices[k], env)
                cmd += ["--gpu", "0"]
            cmd += extra
            # exec a fresh process: nothing in this launcher has touched CUDA, so
            # no already-initialized context is ever inherited.
            with (wdir / "run.log").open("w") as log, _defer_launcher_signals():
                p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                     start_new_session=True)
                stamps[k] = {"started": time.time()}
                resources.watch(p.pid, k)
                procs.append((k, p, wdir))
            (wdir / "command.json").write_text(json.dumps({
                "index": k, "command": cmd, "pid": p.pid,
                "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"),
                "device": devices[k] if devices else None,
                "cpu_mask": masks[k],
            }, indent=2) + "\n")

        # One waiter per child. Waiting sequentially would record worker 1's end
        # as the moment worker 0 was reaped, so the final-worker tail -- the whole
        # point of recording ends -- would read as zero whenever the workers are
        # reaped in finishing order.
        def reap(index: int, proc: subprocess.Popen) -> None:
            rc = proc.wait()
            stamps[index]["ended"] = time.time()
            codes[index] = rc

        for k, p, _ in procs:
            waiter = threading.Thread(target=reap, args=(k, p), daemon=True)
            with _defer_launcher_signals():
                waiter.start()
                waiters.append(waiter)
        for w in waiters:
            w.join()

    except LauncherInterrupted as exc:
        interrupted_signal = exc.signum
        _ignore_launcher_signals()
        _terminate_process_groups(procs)
        for waiter in waiters:
            if waiter.ident is not None:
                waiter.join(timeout=_KILL_REAP_SECONDS)
    except BaseException:
        _ignore_launcher_signals()
        _terminate_process_groups(procs)
        raise
    finally:
        if resources_started:
            resources.stop()
            resources.join(timeout=10)
        if sampler is not None:
            sampler.stop()
            # nvidia-smi calls are bounded at 30 s, so a join that still times
            # out means the thread is wedged; observations() would then read a
            # list another thread is writing. Treat it as a witness failure.
            if sampler_started:
                sampler.join(timeout=40)
            if sampler_started and sampler.is_alive():
                sampler.errors.append("sampler thread did not stop; samples are "
                                      "incomplete and cannot witness anything")
        if previous_handlers:
            _restore_signal_handlers(previous_handlers)

    results = []
    for k, p, wdir in procs:
        rc = codes.get(k)
        if rc is None:
            rc = p.wait()
        ended = stamps[k].setdefault("ended", time.time())
        results.append({"index": k, "pid": p.pid, "returncode": rc,
                        "log": str((wdir / "run.log").resolve()),
                        "started_at": _iso(stamps[k]["started"]),
                        "ended_at": _iso(ended),
                        "wall_seconds": round(ended - stamps[k]["started"], 3),
                        "rss_hwm_kib": resources.hwm_kib.get(p.pid),
                        "rss_note": resources.unavailable or
                                    ("worker process only; ghostscript children "
                                     f"excluded; sampled every {a.sample_interval}s")})

    wall = time.time() - started
    # Resolved paths and the manifest digest, so merge_workers.py can prove this
    # status describes the run it is merging rather than another one that happened
    # to have the same worker count. Two runs over the same input produce
    # byte-identical manifests, so the digest alone cannot separate them and the
    # resolved paths do the rest.
    manifest_path = (shard_dir / "shard_manifest.json").resolve()
    status: dict[str, object] = {
        "input_star": a.star,
        "binary": a.binary,
        "n_workers": n,
        "worker_args": extra,
        "cpus": a.cpus,
        "cpu_masks": masks,
        "started_at": _iso(started),
        "ended_at": _iso(started + wall),
        "wall_seconds": round(wall, 3),
        "wall_seconds_note": "bookkeeping only; this tool makes no throughput claim and "
                             "is not a benchmark. #26 owns the measurement matrix.",
        "final_worker_tail_seconds": round(
            max(s["ended"] for s in stamps.values())
            - min(s["ended"] for s in stamps.values()), 3) if stamps else None,
        "final_worker_tail_note": "spread between the first and last worker to exit. "
                                  "Load imbalance is one of the candidate limits on "
                                  "static workers; this makes it observable, it does "
                                  "not attribute it.",
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "workers": results,
        "devices": devices or None,
        "termination_signal": interrupted_signal,
    }

    verdict_ok = (interrupted_signal is None
                  and all(r["returncode"] == 0 for r in results))

    if sampler is not None:
        expected = {p.pid: devices[k]["uuid"] for k, p, _ in procs}
        witness = gpu_witness.check_observations(expected, sampler.observations())
        witness["sampler_errors"] = sampler.errors
        witness["n_samples"] = len(sampler.samples)
        status["gpu_witness"] = witness
        if not witness["all_pids_witnessed_on_intended_distinct_devices"]:
            verdict_ok = False
        if sampler.errors:
            # A sampler that died partway may have witnessed every pid before
            # it failed. That is still an incomplete observation, and calling
            # it a pass would be asserting more than was seen.
            verdict_ok = False
    elif devices:  # unreachable: --devices with --no-witness is rejected above
        status["gpu_witness"] = "skipped by --no-witness; no device claim is supported"
        verdict_ok = False

    status["verdict"] = "PASS" if verdict_ok else "FAIL"
    (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    print(json.dumps({"n_workers": n, "wall_seconds": status["wall_seconds"],
                      "returncodes": [r["returncode"] for r in results],
                      "verdict": status["verdict"]}, indent=2))
    if not verdict_ok:
        print(f"FAIL: see {out / 'status.json'}", file=sys.stderr)
        if interrupted_signal is not None:
            return 128 + interrupted_signal
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
