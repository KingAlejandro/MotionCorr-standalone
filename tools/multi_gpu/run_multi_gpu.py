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
import resource
import shlex
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
    if sys.platform == "linux":
        # killpg(..., 0) includes zombies. A container's PID 1 can leave adopted
        # grandchildren in that state indefinitely; they cannot run or receive
        # signals, and this launcher can only reap its own direct children.
        # Refuse to declare cleanup complete if /proc cannot establish the
        # member's PID, original session/group and state from one stat record.
        try:
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    raw = (entry / "stat").read_text()
                except FileNotFoundError:
                    continue  # exited while taking this snapshot
                fields = raw.rsplit(")", 1)[1].split()
                if int(raw.split(" ", 1)[0]) != int(entry.name):
                    return True
                if int(fields[2]) != pgid:
                    continue
                if int(fields[3]) != pgid or int(fields[19]) <= 0:
                    return True  # not demonstrably a member of our session
                if fields[0] != "Z":
                    return True
        except (OSError, ValueError, IndexError):
            return True  # unavailable/ambiguous process evidence is not success
        return False
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


_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def parse_cpu_list(spec: str) -> set[int]:
    """Parse a Linux CPU list ("0-3,8,10-11") into a set of cpu ids."""
    cpus: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            lo_i, hi_i = int(lo), int(hi)
            if hi_i < lo_i:
                raise ValueError(f"descending cpu range {part!r}")
            cpus.update(range(lo_i, hi_i + 1))
        else:
            cpus.add(int(part))
    return cpus


def format_cpu_list(cpus: set[int]) -> str:
    out, run = [], []
    for c in sorted(cpus):
        if run and c == run[-1] + 1:
            run.append(c)
            continue
        if run:
            out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
        run = [c]
    if run:
        out.append(str(run[0]) if len(run) == 1 else f"{run[0]}-{run[-1]}")
    return ",".join(out)


def confirm_affinity(pid: int, requested: str, deadline_seconds: float = 5.0
                     ) -> tuple[str | None, str]:
    """Poll /proc/<pid>/status until the requested mask is in force.

    ``taskset -c`` calls sched_setaffinity and then execs, so for a short window
    after fork the child still carries the launcher's inherited mask. Sampling
    at the 0.5 s resource interval is too coarse for that window and too slow
    for a worker that exits quickly, so the mask is confirmed here instead, at
    millisecond granularity, and the sampler keeps watching for a later change.

    Returns (settled_mask_or_None, status) where status is MATCH, MISMATCH,
    EXITED_BEFORE_WITNESS or NO_PROC.
    """
    status_path = Path(f"/proc/{pid}/status")
    if not Path("/proc").is_dir():
        return None, "NO_PROC"
    want = parse_cpu_list(requested)
    last: str | None = None
    deadline = time.monotonic() + deadline_seconds
    while True:
        try:
            for line in status_path.read_text().splitlines():
                if line.startswith("Cpus_allowed_list:"):
                    last = line.split(":", 1)[1].strip()
                    break
        except (OSError, ValueError):
            return (last, "MISMATCH" if last is not None else "EXITED_BEFORE_WITNESS")
        if last is not None:
            try:
                if parse_cpu_list(last) == want:
                    return last, "MATCH"
            except ValueError:
                return last, "MISMATCH"
        if time.monotonic() >= deadline:
            return last, "MISMATCH" if last is not None else "EXITED_BEFORE_WITNESS"
        time.sleep(0.005)


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

    Also samples Cpus_allowed_list and the utime/stime tick counters.

    Affinity has to be read back rather than assumed. ``taskset -c`` calls
    sched_setaffinity and then execs, so between fork and that call the child
    still carries the launcher's inherited mask -- a single read taken right
    after Popen can legitimately observe the wrong mask. More importantly, a
    requested mask is not necessarily the mask in force: a cpuset or cgroup can
    narrow it, and a mask naming a cpu outside the allocation makes taskset fail
    outright. Every distinct observation is kept, in order, so the settled value
    is checkable and a transient one is visible instead of hidden.

    CPU time is sampled for per-worker attribution only. It is a lower bound --
    a worker that exits between two polls is recorded at its last reading -- and
    it excludes ghostscript. The exact run total comes from getrusage
    (RUSAGE_CHILDREN) in main(), which needs no sampling and does include the
    reaped grandchildren.
    """

    def __init__(self, interval: float):
        super().__init__(daemon=True)
        self.interval = interval
        self.pids: dict[int, int] = {}
        self.hwm_kib: dict[int, int] = {}
        self.cpus_allowed: dict[int, list[str]] = {}
        self.cpu_ticks: dict[int, tuple[int, int]] = {}
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
                        elif line.startswith("Cpus_allowed_list:"):
                            seen = self.cpus_allowed.setdefault(pid, [])
                            value = line.split(":", 1)[1].strip()
                            if not seen or seen[-1] != value:
                                seen.append(value)
                except (OSError, ValueError):
                    pass  # exited between listing and reading, or not readable
                try:
                    raw = Path(f"/proc/{pid}/stat").read_text()
                    f = raw.rsplit(")", 1)[1].split()
                    self.cpu_ticks[pid] = (int(f[11]), int(f[12]))  # utime, stime
                except (OSError, ValueError, IndexError):
                    pass
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
    ap.add_argument("--cpu-budget", type=int, default=None,
                    help="assert the union of the per-worker masks is exactly this many "
                         "cpus. A fixed-total-resource comparison is only fixed if the "
                         "budget is checked at every worker count; without this, 4 "
                         "workers at one mask each silently use 4x the cores of 1.")
    ap.add_argument("--worker-extra", action="append", default=None, metavar="ARGS",
                    help="extra arguments for ONE worker, repeatable; give exactly as "
                         "many as there are workers, or none. shlex-split and appended "
                         "AFTER the shared worker arguments, so a per-worker '--j 2' "
                         "overrides a shared '--j 8' (IOParser takes the last "
                         "occurrence). This is how per-worker thread counts are set; a "
                         "single shared --j gives every worker the same count no matter "
                         "how wide its cpu mask is. Write it as "
                         "--worker-extra=--sync_output: argparse only accepts a "
                         "'-'-prefixed value as a separate token when it contains a "
                         "space, so '--worker-extra --j 2' happens to work while "
                         "'--worker-extra --sync_output' exits on a usage error.")
    ap.add_argument("--omp-num-threads", default=None,
                    help="OMP_NUM_THREADS for every worker. Default when --cpus is "
                         "given: that worker's mask width.")
    ap.add_argument("--omp-proc-bind", default=None, help="OMP_PROC_BIND for every worker")
    ap.add_argument("--omp-places", default=None, help="OMP_PLACES for every worker")
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
    mask_sets: list[set[int]] = []
    allocation = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
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
        try:
            mask_sets = [parse_cpu_list(m) for m in masks if m]
        except ValueError as exc:
            print(f"FAIL: --cpus is not a valid cpu list: {exc}", file=sys.stderr)
            return 2
        if any(not s for s in mask_sets):
            print("FAIL: --cpus contains an empty mask", file=sys.stderr)
            return 2
        overlaps = []
        for i in range(len(mask_sets)):
            for j in range(i + 1, len(mask_sets)):
                shared = mask_sets[i] & mask_sets[j]
                if shared:
                    overlaps.append(f"w{i}/w{j} share {format_cpu_list(shared)}")
        masks_disjoint = not overlaps
        union = set().union(*mask_sets)
        # Sharing cores between workers stays available -- it is a real thing to
        # measure. What it must not do is pass as a fixed-budget point, so the
        # refusal attaches to --cpu-budget, which is the flag that makes that
        # claim, rather than to the capability. Union size alone cannot catch it:
        # four workers each on 0-7 cover exactly 8 cpus while oversubscribing 4x.
        if a.cpu_budget is not None and overlaps:
            print("FAIL: --cpu-budget asserts a partitioned budget, but the masks "
                  "overlap: " + "; ".join(overlaps) + ". Give disjoint per-worker "
                  "masks, or drop --cpu-budget and record this as an "
                  "oversubscription run.", file=sys.stderr)
            return 2
        if allocation and not union <= set(allocation):
            outside = union - set(allocation)
            print(f"FAIL: --cpus names cpu(s) {format_cpu_list(outside)} outside this "
                  f"process's allocation ({format_cpu_list(set(allocation))}). taskset "
                  "would fail per worker, or a cpuset would silently narrow the mask.",
                  file=sys.stderr)
            return 2
        if a.cpu_budget is not None and len(union) != a.cpu_budget:
            print(f"FAIL: --cpu-budget {a.cpu_budget} but the masks cover "
                  f"{len(union)} cpu(s) ({format_cpu_list(union)})", file=sys.stderr)
            return 2
    else:
        masks_disjoint = None
    if not a.cpus and a.cpu_budget is not None:
        print("FAIL: --cpu-budget only means something with --cpus; without pinning "
              "every worker sees the whole allocation.", file=sys.stderr)
        return 2

    per_worker_extra: list[list[str]] = [[] for _ in range(n)]
    if a.worker_extra:
        if len(a.worker_extra) != n:
            print(f"FAIL: {len(a.worker_extra)} --worker-extra value(s) for {n} "
                  "worker(s); give exactly one per worker or none", file=sys.stderr)
            return 2
        per_worker_extra = [shlex.split(s) for s in a.worker_extra]

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
    clashes = sorted({tok for tok in extra + [x for e in per_worker_extra for x in e]
                      if tok in OWNED})
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
    confirmed: dict[int, tuple[str | None, str]] = {}
    stamps: dict[int, dict[str, float]] = {}
    codes: dict[int, int] = {}
    waiters: list[threading.Thread] = []
    previous_handlers: dict[int, object] = {}
    sampler_started = False
    resources_started = False
    interrupted_signal: int | None = None
    # Exact, unsampled CPU total for everything this launcher reaps, including
    # the ghostscript grandchildren the per-worker /proc sampling cannot see: a
    # worker's own cutime/cstime roll into its rusage when the launcher reaps it.
    # Taken as a delta because the launcher may already have reaped children
    # (partition_star runs in-process, but a future caller may not).
    ru0 = resource.getrusage(resource.RUSAGE_CHILDREN)
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
            cmd += per_worker_extra[k]
            # OMP settings decide how the worker's threads land on the mask, and
            # an unset OMP_NUM_THREADS makes libgomp default to the cpu count it
            # can see. Resolve it to the mask width so n workers on a partitioned
            # budget do not each open a pool sized for the whole node, and record
            # the resolved values either way so an inherited setting is never
            # mistaken for a chosen one.
            if a.omp_num_threads is not None:
                env["OMP_NUM_THREADS"] = a.omp_num_threads
            elif mask_sets:
                env["OMP_NUM_THREADS"] = str(len(mask_sets[k]))
            if a.omp_proc_bind is not None:
                env["OMP_PROC_BIND"] = a.omp_proc_bind
            if a.omp_places is not None:
                env["OMP_PLACES"] = a.omp_places
            omp_env = {v: env.get(v) for v in
                       ("OMP_NUM_THREADS", "OMP_PROC_BIND", "OMP_PLACES")}
            # exec a fresh process: nothing in this launcher has touched CUDA, so
            # no already-initialized context is ever inherited.
            with (wdir / "run.log").open("w") as log, _defer_launcher_signals():
                p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                     start_new_session=True)
                stamps[k] = {"started": time.time()}
                resources.watch(p.pid, k)
                procs.append((k, p, wdir))
            if masks[k]:
                confirmed[k] = confirm_affinity(p.pid, masks[k])
            (wdir / "command.json").write_text(json.dumps({
                "index": k, "command": cmd, "pid": p.pid,
                "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"),
                "device": devices[k] if devices else None,
                "cpu_mask": masks[k],
                "cpu_mask_width": len(mask_sets[k]) if mask_sets else None,
                "omp": omp_env,
                "worker_extra": per_worker_extra[k],
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

    ru1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds_total = round((ru1.ru_utime - ru0.ru_utime)
                              + (ru1.ru_stime - ru0.ru_stime), 3)

    results = []
    affinity_problems: list[str] = []
    for k, p, wdir in procs:
        rc = codes.get(k)
        if rc is None:
            rc = p.wait()
        ended = stamps[k].setdefault("ended", time.time())
        observed = resources.cpus_allowed.get(p.pid, [])
        requested = masks[k]
        at_launch, verdict = confirmed.get(k, (None, "UNPINNED"))
        affinity: dict[str, object] = {
            "requested": requested,
            "witnessed_at_launch": at_launch,
            "later_observations": observed,
            "verdict": verdict,
            "note": "read back from /proc/<pid>/status Cpus_allowed_list rather than "
                    "assumed from the taskset argument, so a cpuset that narrows the "
                    "mask is visible. later_observations is the 0.5 s sampler trace "
                    "and records any change after launch.",
        }
        if verdict == "MISMATCH":
            affinity_problems.append(
                f"w{k}: requested {requested}, in force {at_launch}")
        elif verdict == "EXITED_BEFORE_WITNESS" and a.cpu_budget is not None:
            # Only a problem when a fixed-budget claim is being made. A worker
            # that exits in under a few milliseconds is a test fake, not a
            # scaling point, and failing those would make the device-free suite
            # flaky for no gain.
            affinity_problems.append(
                f"w{k}: exited before its mask could be read, so the --cpu-budget "
                f"{a.cpu_budget} partition is unwitnessed for this worker")
        elif verdict == "NO_PROC" and a.cpu_budget is not None:
            affinity_problems.append(
                f"w{k}: no /proc on this platform, so --cpu-budget cannot be witnessed")
        ticks = resources.cpu_ticks.get(p.pid)
        wall_s = ended - stamps[k]["started"]
        cpu_s = round(sum(ticks) / _CLK_TCK, 3) if ticks else None
        results.append({"index": k, "pid": p.pid, "returncode": rc,
                        "log": str((wdir / "run.log").resolve()),
                        "started_at": _iso(stamps[k]["started"]),
                        "ended_at": _iso(ended),
                        "wall_seconds": round(wall_s, 3),
                        "rss_hwm_kib": resources.hwm_kib.get(p.pid),
                        "rss_note": resources.unavailable or
                                    ("worker process only; ghostscript children "
                                     f"excluded; sampled every {a.sample_interval}s"),
                        "cpu_seconds_sampled": cpu_s,
                        "mean_threads_running": round(cpu_s / wall_s, 2)
                                                if cpu_s is not None and wall_s > 0
                                                else None,
                        "cpu_mask": requested,
                        "cpu_mask_width": len(mask_sets[k]) if mask_sets else None,
                        "cpu_affinity": affinity})

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
        "cpu_mask_widths": [len(s) for s in mask_sets] or None,
        "cpu_budget_requested": a.cpu_budget,
        "cpu_budget_covered": len(set().union(*mask_sets)) if mask_sets else None,
        "cpu_masks_disjoint": masks_disjoint,
        "cpu_masks_disjoint_note": "false means workers shared cores. Allowed, but "
                                   "such a run is an oversubscription measurement, "
                                   "not a fixed-budget scaling point; --cpu-budget "
                                   "refuses it for that reason.",
        "launcher_allocation": format_cpu_list(set(allocation)) if allocation else None,
        "omp_requested": {"OMP_NUM_THREADS": a.omp_num_threads,
                          "OMP_PROC_BIND": a.omp_proc_bind,
                          "OMP_PLACES": a.omp_places},
        "omp_note": "as requested on the command line. The value each worker was "
                    "actually given, including the mask-width default for "
                    "OMP_NUM_THREADS and anything inherited from the environment, "
                    "is in that worker's command.json.",
        "cpu_seconds_total": cpu_seconds_total,
        "cpu_seconds_total_note": "getrusage(RUSAGE_CHILDREN) delta across the run: "
                                  "exact, unsampled, and includes the ghostscript "
                                  "grandchildren each worker reaps.",
        "mean_cores_busy": round(cpu_seconds_total / wall, 2) if wall > 0 else None,
        "mean_cores_busy_note": "cpu_seconds_total / launcher wall. Achieved "
                                "parallelism averaged over the whole run, including "
                                "the serial tails. Compare against "
                                "cpu_budget_covered: a scaling number is only "
                                "meaningful when the budget was actually used.",
        "affinity_problems": affinity_problems or None,
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
    # A mask that was requested but never observed in force is not pinning. If
    # this did not fail the verdict, an oversubscribed run -- every worker on the
    # whole node -- would be filed as a fixed-budget scaling point.
    if affinity_problems:
        verdict_ok = False

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
                      "cpu_budget_covered": status["cpu_budget_covered"],
                      "cpu_seconds_total": cpu_seconds_total,
                      "mean_cores_busy": status["mean_cores_busy"],
                      "affinity": [r["cpu_affinity"]["verdict"] for r in results],
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
