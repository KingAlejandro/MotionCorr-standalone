"""Pinned, interleaved, paired MotionCorr runs with resource capture.

Per run: wall (monotonic, spawn to reap), user+sys CPU, peak RSS and faults
from wait4 rusage (the payload and every descendant it reaped), whole-process
peak VRAM sampled through NVML (or nvidia-smi), host load, lane CPU use by
other processes, and foreign processes on the target GPU.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import statistics
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import provenance as prov

FOREIGN_LANE_CORES = 0.25    # mean foreign CPU on the lane above this discards a run
NVML_INTERVAL_S = 0.010
SMI_INTERVAL_MS = 20


# ----------------------------------------------------------------- input staging

def star_movies(path: str) -> Tuple[List[str], List[Tuple[int, str]]]:
    """Movie names from a RELION STAR file and the (line index, block) of each row."""
    with open(path) as f:
        lines = f.read().splitlines()
    block, in_loop, labels = None, False, []
    rows: List[Tuple[int, str]] = []
    movies: List[str] = []
    col = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("data_"):
            block, in_loop, labels, col = s, False, [], None
        elif s == "loop_":
            in_loop, labels = True, []
        elif s.startswith("_") and in_loop:
            labels.append(s.split()[0])
            if s.split()[0] == "_rlnMicrographMovieName":
                col = len(labels) - 1
        elif s and not s.startswith("#") and in_loop and col is not None:
            movies.append(s.split()[col])
            rows.append((i, block or ""))
    if not movies:
        raise ValueError("%s: no _rlnMicrographMovieName rows" % path)
    return movies, rows


def stage_input(data: str, star: str, n_movies: Optional[int], work: str) -> Dict:
    """Payload working directory and STAR. With n_movies, a staging directory
    holds a STAR with the first n movie rows and symlinks to everything else
    in the data directory, so relative movie paths resolve unchanged."""
    data = os.path.abspath(data)
    src = os.path.join(data, star)
    movies, rows = star_movies(src)
    if n_movies is None or n_movies >= len(movies):
        return {"cwd": data, "star": star, "movies": movies, "staged": False, "star_sha256": prov.sha256_file(src)}
    stage = os.path.join(work, "input")
    os.makedirs(stage, exist_ok=True)
    for name in os.listdir(data):
        if name == star:
            continue
        link = os.path.join(stage, name)
        if not os.path.lexists(link):
            os.symlink(os.path.join(data, name), link)
    with open(src) as f:
        lines = f.read().splitlines()
    drop = {i for i, _ in rows[n_movies:]}
    with open(os.path.join(stage, star), "w") as f:
        f.write("\n".join(l for i, l in enumerate(lines) if i not in drop) + "\n")
    return {"cwd": stage, "star": star, "movies": movies[:n_movies], "staged": True,
            "star_sha256": prov.sha256_file(os.path.join(stage, star)), "source_star": src}


# ----------------------------------------------------------------- GPU samplers

class _NvmlProc(ctypes.Structure):
    _fields_ = [("pid", ctypes.c_uint), ("usedGpuMemory", ctypes.c_ulonglong),
                ("gpuInstanceId", ctypes.c_uint), ("computeInstanceId", ctypes.c_uint)]


class _NvmlMem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


NVML_NA = 0xFFFFFFFFFFFFFFFF


class GpuSampler:
    """Samples device memory used and per-process memory on one GPU (by UUID).

    peak values are lower bounds: a sampler sees only what was resident at
    its sampling instants.
    """
    instrument = "none"

    def __init__(self, uuid: Optional[str]):
        self.uuid = uuid
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.reset()

    def reset(self) -> None:
        self.samples = 0
        self.t_first = self.t_last = None
        self.device_peak = None
        self.own_peak = None
        self.foreign: Dict[int, int] = {}
        self.own_pids: set = set()
        self.unknown_pids: set = set()
        self.errors = 0

    # subclasses implement read() -> (device_used_bytes or None, [(pid, bytes or None)])
    def read(self):
        return None, []

    def processes(self) -> List[Tuple[int, Optional[int]]]:
        return self.read()[1]

    def baseline(self, n: int = 10, gap: float = 0.02) -> Optional[int]:
        vals = []
        for _ in range(n):
            used, _ = self.read()
            if used is not None:
                vals.append(used)
            time.sleep(gap)
        return int(statistics.median(vals)) if vals else None

    def start(self, sid: int) -> None:
        self.reset()
        self._sid = sid
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            t = time.monotonic()
            try:
                used, procs = self.read()
            except Exception:
                self.errors += 1
                used, procs = None, []
            self.samples += 1
            self.t_first = self.t_first or t
            self.t_last = t
            if used is not None:
                self.device_peak = used if self.device_peak is None else max(self.device_peak, used)
            own = 0
            own_seen = False
            for pid, mem in procs:
                owner = classify_pid(pid, self._sid)
                if owner == "own":
                    self.own_pids.add(pid)
                    if mem is not None:
                        own += mem
                        own_seen = True
                elif owner == "foreign":
                    self.foreign[pid] = max(self.foreign.get(pid, 0), mem or 0)
                else:
                    self.unknown_pids.add(pid)
            if own_seen:
                self.own_peak = own if self.own_peak is None else max(self.own_peak, own)
            self._wait(t)

    def _wait(self, t0: float) -> None:
        self._stop.wait(max(0.0, NVML_INTERVAL_S - (time.monotonic() - t0)))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def summary(self, baseline: Optional[int]) -> Dict:
        span = (self.t_last - self.t_first) if self.samples > 1 else None
        return {"instrument": self.instrument, "samples": self.samples,
                "mean_interval_ms": round(1e3 * span / (self.samples - 1), 2) if span else None,
                "peak_process_bytes": self.own_peak,
                "peak_device_used_bytes": self.device_peak, "idle_baseline_bytes": baseline,
                "peak_device_delta_bytes": (self.device_peak - baseline)
                if self.device_peak is not None and baseline is not None else None,
                "own_pids_seen": sorted(self.own_pids), "foreign_pids": dict(sorted(self.foreign.items())),
                "unclassified_pids": sorted(self.unknown_pids), "read_errors": self.errors}


def classify_pid(pid: int, sid: int) -> str:
    try:
        return "own" if os.getsid(pid) == sid else "foreign"
    except (ProcessLookupError, PermissionError):
        return "unknown"


class NvmlSampler(GpuSampler):
    instrument = "NVML (libnvidia-ml via ctypes), device memory used and per-process used memory"

    def __init__(self, uuid: str):
        super().__init__(uuid)
        self.lib = ctypes.CDLL("libnvidia-ml.so.1")
        if self.lib.nvmlInit_v2() != 0:
            raise OSError("nvmlInit_v2 failed")
        self.handle = ctypes.c_void_p()
        if self.lib.nvmlDeviceGetHandleByUUID(uuid.encode(), ctypes.byref(self.handle)) != 0:
            raise OSError("NVML has no device %s" % uuid)
        self._get_procs = getattr(self.lib, "nvmlDeviceGetComputeRunningProcesses_v3", None) or \
            getattr(self.lib, "nvmlDeviceGetComputeRunningProcesses_v2")

    def read(self):
        mem = _NvmlMem()
        used = mem.used if self.lib.nvmlDeviceGetMemoryInfo(self.handle, ctypes.byref(mem)) == 0 else None
        count = ctypes.c_uint(64)
        arr = (_NvmlProc * 64)()
        procs = []
        if self._get_procs(self.handle, ctypes.byref(count), arr) == 0:
            for i in range(count.value):
                m = arr[i].usedGpuMemory
                procs.append((int(arr[i].pid), None if m == NVML_NA else int(m)))
        return used, procs


class SmiSampler(GpuSampler):
    """Fallback: one nvidia-smi query per sample (slower; ~50-100 ms cadence)."""
    instrument = "nvidia-smi --query-gpu/--query-compute-apps polling"

    def __init__(self, uuid: str):
        super().__init__(uuid)
        self.smi = shutil.which("nvidia-smi")
        if not self.smi:
            raise OSError("nvidia-smi not found")

    def read(self):
        rc, out = prov.run_text([self.smi, "--id=%s" % self.uuid, "--query-gpu=memory.used",
                                 "--format=csv,noheader,nounits"], timeout=5)
        used = int(out.split()[0]) << 20 if rc == 0 and out.split() and out.split()[0].isdigit() else None
        rc, out = prov.run_text([self.smi, "--query-compute-apps=pid,gpu_uuid,used_memory",
                                 "--format=csv,noheader,nounits"], timeout=5)
        procs = []
        if rc == 0:
            for line in out.splitlines():
                f = [x.strip() for x in line.split(",")]
                if len(f) >= 3 and f[1] == self.uuid and f[0].isdigit():
                    procs.append((int(f[0]), int(f[2]) << 20 if f[2].isdigit() else None))
        return used, procs

    def _wait(self, t0: float) -> None:
        self._stop.wait(max(0.0, SMI_INTERVAL_MS / 1e3 - (time.monotonic() - t0)))


def make_sampler(uuid: Optional[str]) -> GpuSampler:
    if not uuid:
        return GpuSampler(None)
    try:
        return NvmlSampler(uuid)
    except (OSError, AttributeError):
        return SmiSampler(uuid)


# ----------------------------------------------------------------- one run

def payload_env(gpu_uuid: Optional[str], extra: Sequence[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    env = dict(os.environ)
    changes: Dict[str, str] = {}
    if gpu_uuid:
        changes["CUDA_VISIBLE_DEVICES"] = gpu_uuid
        changes["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    for kv in extra:
        k, _, v = kv.partition("=")
        changes[k] = v
    env.update(changes)
    return env, changes


def payload_argv(binary: str, args: Sequence[str], star: str, out_dir: str, cpus: Sequence[int],
                 profile: Optional[str] = None) -> List[str]:
    for flag in ("--i", "--o", "--profile"):
        if flag in args:
            raise ValueError("pass %s through the kit's own options, not after --" % flag)
    argv = [binary, *args, "--i", star, "--o", out_dir.rstrip("/") + "/"]
    if profile:
        argv += ["--profile", profile]
    if cpus:
        if not shutil.which("taskset"):
            raise RuntimeError("--cpus needs taskset")
        argv = ["taskset", "-c", ",".join(str(c) for c in cpus)] + argv
    return argv


def count_mrc(root: str) -> int:
    n = 0
    for _, _, files in os.walk(root):
        n += sum(1 for f in files if f.lower().endswith(".mrc"))
    return n


def _is_script(path: str) -> bool:
    with open(path, "rb") as f:
        return f.read(2) == b"#!"


def _affinity_of(pid: int) -> Optional[List[int]]:
    try:
        return sorted(os.sched_getaffinity(pid))
    except (AttributeError, OSError):
        return None


def run_once(argv: Sequence[str], cwd: str, env: Dict[str, str], log_path: str, sampler: GpuSampler,
             lane: Sequence[int], binary: str, out_dir: str, n_movies: int) -> Dict:
    """Run one payload to completion and return its record (raises on failure)."""
    os.makedirs(out_dir, exist_ok=True)
    rec: Dict = {"argv": list(argv), "cwd": cwd, "log": log_path, "out_dir": out_dir}
    rec["load1_before"] = os.getloadavg()[0]
    rec["compilers_before"] = prov.compilers_running()
    pre = sampler.processes() if sampler.uuid else []
    rec["gpu_processes_before"] = [p for p, _ in pre]
    baseline = sampler.baseline() if sampler.uuid else None
    j0 = prov.lane_jiffies(lane)
    with open(log_path, "w") as log:
        t0 = time.monotonic()
        p = subprocess.Popen(list(argv), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
        if sampler.uuid:
            sampler.start(p.pid)
        exe = None
        # The payload is exec'd by taskset with the same pid; confirm the image.
        # A script payload (tests) runs under its interpreter and is not checked.
        deadline = time.monotonic() + (0.0 if _is_script(binary) else 2.0)
        while time.monotonic() < deadline:
            try:
                exe = os.path.realpath("/proc/%d/exe" % p.pid) if os.path.exists("/proc/%d" % p.pid) else None
            except OSError:
                exe = None
            if exe is None or exe == os.path.realpath(binary):
                break
            time.sleep(0.002)
        affinity = _affinity_of(p.pid)
        _, status, ru = os.wait4(p.pid, 0)
        wall = time.monotonic() - t0
        p.returncode = os.waitstatus_to_exitcode(status)
        if sampler.uuid:
            sampler.stop()
    j1 = prov.lane_jiffies(lane)
    rc = p.returncode
    rec.update({
        "rc": rc, "wall_s": wall, "user_s": ru.ru_utime, "sys_s": ru.ru_stime,
        "cpu_s": ru.ru_utime + ru.ru_stime,
        # Linux reports ru_maxrss in KiB, macOS in bytes.
        "peak_rss_bytes": ru.ru_maxrss * (1 if os.uname().sysname == "Darwin" else 1024),
        "minflt": ru.ru_minflt, "majflt": ru.ru_majflt, "nvcsw": ru.ru_nvcsw, "nivcsw": ru.ru_nivcsw,
        "payload_pid": p.pid, "payload_exe": exe,
        "payload_exe_verified": (exe == os.path.realpath(binary))
        if exe is not None and not _is_script(binary) else None,
        "payload_affinity": affinity, "load1_after": os.getloadavg()[0],
        "compilers_after": prov.compilers_running(),
    })
    if sampler.uuid:
        rec["vram"] = sampler.summary(baseline)
    if j0 and j1:
        hz = prov.clock_ticks()
        busy = (j1["busy"] - j0["busy"]) / hz
        rec["lane"] = {"busy_s": busy, "steal_s": (j1["steal"] - j0["steal"]) / hz,
                       "foreign_s": max(0.0, busy - rec["cpu_s"]),
                       "foreign_cores": max(0.0, busy - rec["cpu_s"]) / wall if wall > 0 else None}
    if rc != 0:
        raise RuntimeError("payload exited %d; see %s" % (rc, log_path))
    rec["mrc_products"] = count_mrc(out_dir)
    if rec["mrc_products"] < n_movies:
        raise RuntimeError("payload wrote %d MRC products for %d movies; see %s"
                           % (rec["mrc_products"], n_movies, log_path))
    rec["flags"] = run_flags(rec, lane)
    return rec


def run_flags(rec: Dict, lane: Sequence[int]) -> Dict[str, List[str]]:
    """discard: conditions that invalidate a timing. note: recorded only."""
    discard, note = [], []
    v = rec.get("vram") or {}
    if v.get("foreign_pids"):
        discard.append("foreign process on target GPU: %s" % ",".join(map(str, v["foreign_pids"])))
    if rec.get("gpu_processes_before"):
        own = set(v.get("own_pids_seen", []))
        others = [p for p in rec["gpu_processes_before"] if p not in own]
        if others:
            discard.append("GPU busy before start: %s" % ",".join(map(str, others)))
    ln = rec.get("lane")
    if ln and ln["foreign_cores"] is not None and ln["foreign_cores"] > FOREIGN_LANE_CORES:
        discard.append("foreign CPU on lane %.2f cores" % ln["foreign_cores"])
    if lane and rec.get("payload_affinity") is not None and rec["payload_affinity"] != sorted(lane):
        discard.append("payload affinity %s != lane" % rec["payload_affinity"])
    if rec.get("payload_exe_verified") is False:
        discard.append("payload image not verified: %s" % rec.get("payload_exe"))
    if rec.get("compilers_before") or rec.get("compilers_after"):
        note.append("compilers running on the host")
    if v.get("unclassified_pids"):
        note.append("unclassified GPU pids %s" % v["unclassified_pids"])
    return {"discard": discard, "note": note}


# ----------------------------------------------------------------- settle

def settle(sampler: GpuSampler, timeout_s: float, poll_s: float = 5.0) -> Dict:
    """Wait (after taking the locks) until the target GPU has no processes and
    no compiler runs on the host. Returns what was seen and how long it took."""
    t0 = time.monotonic()
    while True:
        gpu = [p for p, _ in sampler.processes()] if sampler.uuid else []
        comp = prov.compilers_running()
        if not gpu and not comp:
            return {"settled": True, "waited_s": round(time.monotonic() - t0, 1)}
        if time.monotonic() - t0 > timeout_s:
            return {"settled": False, "waited_s": round(time.monotonic() - t0, 1),
                    "gpu_processes": gpu, "compilers": comp}
        time.sleep(poll_s)


def lane_busy_cores(lane: Sequence[int], window_s: float = 1.0) -> Optional[float]:
    """Mean busy cores on the lane over a short window (nothing of ours runs there)."""
    j0 = prov.lane_jiffies(lane)
    if not j0:
        return None
    time.sleep(window_s)
    j1 = prov.lane_jiffies(lane)
    return (j1["busy"] - j0["busy"]) / prov.clock_ticks() / window_s if j1 else None


def wait_quiet_lane(lane: Sequence[int], timeout_s: float, threshold: float = FOREIGN_LANE_CORES) -> Dict:
    """Before a round: wait until other processes leave the lane, up to timeout_s."""
    t0 = time.monotonic()
    while True:
        c = lane_busy_cores(lane) if lane else None
        waited = round(time.monotonic() - t0, 1)
        if c is None or c <= threshold:
            return {"waited_s": waited, "busy_cores": c}
        if waited > timeout_s:
            return {"waited_s": waited, "busy_cores": c, "timed_out": True}


# ----------------------------------------------------------------- series

def schedule(arms: Sequence[str], rounds: int) -> List[List[str]]:
    """Round r runs the arms rotated by r, so each arm takes each position
    equally often; with two arms the order alternates AB, BA, AB, ..."""
    k = len(arms)
    return [list(arms[r % k:]) + list(arms[:r % k]) for r in range(rounds)]


def order_label(names: Sequence[str], order: Sequence[str]) -> str:
    """"AB" or "BA" for two arms (A = first arm given); the arm list otherwise."""
    if len(names) == 2 and len(order) == 2:
        return "AB" if list(order) == list(names) else "BA"
    return ",".join(order)


def series(arms: Dict[str, str], args: Sequence[str], staged: Dict, work: str, cpus: Sequence[int],
           gpu_uuid: Optional[str], env_extra: Sequence[str], rounds: int, warmup: int,
           sampler: GpuSampler, sink: Callable[[Dict], None],
           after_round: Optional[Callable[[int, Dict[str, Dict]], None]] = None,
           keep_outputs: bool = False, lane_wait_s: float = 0.0, max_rounds: Optional[int] = None) -> Dict:
    """Warm-up runs, then rounds until `rounds` rounds are clean (no run in
    them carries a discard flag) or `max_rounds` rounds have run. Stopping
    depends only on the discard flags, never on the timings."""
    env, _ = payload_env(gpu_uuid, env_extra)
    names = list(arms)
    max_rounds = max(rounds, max_rounds or rounds)
    plan = [("warmup", w, [n]) for w in range(warmup) for n in names] + \
           [("round", r + 1, order) for r, order in enumerate(schedule(names, max_rounds))]
    runs_dir = os.path.join(work, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    clean = ran = 0
    for kind, r, order in plan:
        if kind == "round" and clean >= rounds:
            break
        done: Dict[str, Dict] = {}
        quiet = wait_quiet_lane(cpus, lane_wait_s) if lane_wait_s > 0 else None
        for pos, arm in enumerate(order):
            tag = "%s-%s%02d" % (arm, "w" if kind == "warmup" else "r", r)
            out = os.path.join(runs_dir, tag, "out")
            argv = payload_argv(arms[arm], args, staged["star"], out, cpus)
            rec = run_once(argv, staged["cwd"], env, os.path.join(runs_dir, tag + ".log"), sampler, cpus,
                           arms[arm], out, len(staged["movies"]))
            rec.update({"arm": arm, "kind": kind, "round": r, "position": pos,
                        "order": order_label(names, order), "lane_before_round": quiet})
            done[arm] = rec
            sink(rec)
        if kind == "round":
            ran += 1
            clean += not any(rec["flags"]["discard"] for rec in done.values())
        if after_round:
            after_round(r if kind == "round" else 0, done)
        if not keep_outputs:
            for rec in done.values():
                shutil.rmtree(os.path.dirname(rec["out_dir"]), ignore_errors=True)
    return {"target_clean_rounds": rounds, "max_rounds": max_rounds, "rounds_run": ran, "clean_rounds": clean,
            "reached_target": clean >= rounds}
