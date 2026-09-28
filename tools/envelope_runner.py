#!/usr/bin/env python3
"""Operating-envelope measurement runner for issue #26.

Executes a declared plan of timed MotionCorr arms, one at a time, and writes one
self-describing JSON record per run. The record is the unit of evidence: it carries the
identity, placement, device, interval, memory, interference and product witnesses that
`agents/designs/issue_26_operating_envelope.md` section 2 requires, so a run can be judged
without reference to the shell that launched it.

Three details are deliberate rather than incidental.

Samplers are in-process daemon threads, not backgrounded shell subshells. A subshell sampler
inherits the flock file descriptor and, if its driver dies, holds the box-wide benchmark
mutex forever while producing nothing; that exact failure held `/tmp/motioncorr-bench.lock`
on `4-gpu-vm` for 2d 2h and was cleared by hand on 2026-09-27. Daemon threads die with the
interpreter.

The settle gate runs after the caller has acquired the mutex, not before, because the flock
serialises ownership but not the previous holder's load decay tail. Compiler detection uses
exact process names: `pgrep -f` matches the probe's own command line and is permanently
non-zero.

Effective settings are recorded alongside requested ones and arms are keyed on the effective
tuple, because `--max_io_threads` above `--j` is silently clamped to `--j` and would
otherwise be timed twice as two distinct treatments.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from pathlib import Path as pathlib_Path
from typing import Any, Dict, List, Optional

RESIDUAL_AFTER_NORMAL_EXIT = "residual group members after normal exit"
COMPILER_NAMES = ("cc1plus", "nvcc", "cicc", "ptxas")


def sh(cmd: str, timeout: int = 60) -> str:
    try:
        p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip()
    except Exception as exc:  # a missing witness tool must not abort a series
        return f"<error: {exc}>"


def mrc_split_digests(path: Path) -> Optional[Dict[str, Any]]:
    """Digest an MRC as core header, label block and payload separately.

    A whole-file digest of an MRC is not a parity statement: the label block at offset 224
    holds an `strftime` timestamp, so two bit-identical reconstructions hash differently.
    The payload digest is the pixel claim; the core-header digest is the geometry/statistics
    claim; the label digest is expected to differ and is recorded, not compared.
    """
    try:
        raw = path.read_bytes()
        if len(raw) < 1024:
            return {"error": f"shorter than an MRC header ({len(raw)} bytes)"}
        nx, ny, nz, mode = (int.from_bytes(raw[i:i + 4], "little", signed=True)
                            for i in (0, 4, 8, 12))
        nsymbt = int.from_bytes(raw[92:96], "little", signed=True)
        if nsymbt < 0 or 1024 + nsymbt > len(raw):
            return {"error": f"implausible nsymbt {nsymbt} for {len(raw)} bytes"}
        off = 1024 + nsymbt
        itemsize = {0: 1, 1: 2, 2: 4, 6: 2, 12: 2}.get(mode)
        expected = off + nx * ny * nz * itemsize if itemsize else None
        if expected is not None and len(raw) != expected:
            # A truncated file would otherwise yield a short payload digest that looks like
            # a confident result. compare_motioncorr.py:62-66 raises on the same condition.
            return {"error": f"size {len(raw)} != expected {expected} "
                             f"(nx={nx} ny={ny} nz={nz} mode={mode} nsymbt={nsymbt})"}
        return {
            "core_header_sha256": hashlib.sha256(raw[:224]).hexdigest(),
            "labels_sha256": hashlib.sha256(raw[224:1024]).hexdigest(),
            "payload_sha256": hashlib.sha256(raw[off:]).hexdigest(),
            "payload_bytes": len(raw) - off,
            "nsymbt": nsymbt, "nx": nx, "ny": ny, "nz": nz, "mode": mode,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _as_int(text: str, default: int = -1) -> int:
    """sh() reports failure as an '<error: ...>' string, which int() would raise on."""
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return default


def sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- witnesses


def host_witness() -> Dict[str, Any]:
    """Static host facts, captured once per series."""
    return {
        "hostname": sh("hostname"),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kernel": sh("uname -r"),
        "online_cpus": sh("cat /sys/devices/system/cpu/online"),
        "lscpu_topology": sh("lscpu -p=CPU,NODE,SOCKET,CORE | grep -v '^#'"),
        "threads_per_core": sh("lscpu | awk -F: '/Thread\\(s\\) per core/{gsub(/ /,\"\",$2); print $2}'"),
        "numactl_hardware": sh("numactl --hardware"),
        "gcc": sh("gcc --version | head -1"),
        "nvidia_smi": sh("nvidia-smi --query-gpu=index,uuid,name,driver_version,memory.total "
                         "--format=csv,noheader"),
        "meminfo_total_kb": sh("awk '/MemTotal/{print $2}' /proc/meminfo"),
    }


class Sampler(threading.Thread):
    """1 Hz background sampling. Daemon, so it cannot outlive the interpreter."""

    def __init__(self, own_user: str, gpu_index: Optional[int], mask: Optional[str],
                 period: float = 0.2, ps_period: float = 1.0, own_root_pid: Optional[int] = None,
                 ownership: Optional[Dict[str, Any]] = None, max_detail: int = 4000):
        super().__init__(daemon=True)
        self.own_user = own_user
        self.own_root_pid = own_root_pid
        self.foreign_detail: Dict[str, int] = {}
        self._prev_snap: Optional[Dict[int, Any]] = None
        self._prev_t = 0.0
        self.ownership = ownership or {"basis": "subtree", "isolated": False,
                                       "sid": _safe_sid(os.getpid()),
                                       "how": "not established by the caller"}
        # Only an isolated session may be owned wholesale. Otherwise the sid is the
        # launching shell's and would hide unrelated same-shell work; ownership then falls
        # back to the process subtree, which cannot.
        self._own_sids = {self.ownership["sid"]} if self.ownership.get("isolated") else set()
        self._own_pids: set = set()
        # Per-sample identity, as the ADR requires: aggregates cannot say which process held
        # the lane at a given instant. Bounded, with the cap and drop count recorded.
        self.samples_detail: List[Dict[str, Any]] = []
        self.samples_dropped = 0
        self.max_detail = max_detail
        self.gpu_index = gpu_index
        self.mask_cpus = parse_cpu_list(mask) if mask else None
        self.period = period
        self.ps_every = max(1, round(ps_period / period))
        self._halt = threading.Event()
        self.foreign_pct: List[float] = []
        self.foreign_in_mask: List[int] = []
        self.vram_mib: List[int] = []
        self.gpu_util: List[int] = []
        self.rss_kib: List[int] = []
        self.samples = 0

    def stop(self) -> None:
        self._halt.set()

    def own_pid_tree(self, root: int) -> None:
        """Adopt a pid subtree as ours. Used when session ownership is not isolated."""
        self._own_pids |= own_subtree(root) | {root}

    def own_also(self, sid: Optional[int]) -> None:
        """Adopt the payload's session. It runs in its own session so that cancellation can
        target the whole group; without this the sampler would report the very process being
        measured as foreign load inside its own lane."""
        if sid:
            self._own_sids.add(sid)

    def _sample_foreign(self) -> None:
        now = time.time()
        snap = cpu_snapshot()
        if self._prev_snap is None:
            self._prev_snap, self._prev_t = snap, now
            return                                  # first tick establishes the baseline
        dt = max(now - self._prev_t, 1e-3)
        total, in_mask = 0.0, 0
        detail: List[Dict[str, Any]] = []
        own_pids = self._own_pids | (own_subtree(self.own_root_pid)
                                     if not self.ownership.get("isolated") else set())
        for pid, (comm, ticks, psid) in snap.items():
            if psid in self._own_sids or pid in own_pids or pid not in self._prev_snap:
                continue
            pct = (ticks - self._prev_snap[pid][1]) / CLK_TCK / dt * 100.0
            if pct <= 1.0:
                continue
            total += pct
            if self.mask_cpus:
                cpus = running_threads_on(self.mask_cpus, pid)
                if cpus:
                    in_mask += len(cpus)
                    self.foreign_detail[comm] = self.foreign_detail.get(comm, 0) + 1
                    detail.append({"pid": pid, "comm": comm, "sid": psid,
                                   "starttime": _starttime(pid), "cpus": sorted(set(cpus)),
                                   "cpu_pct": round(pct, 1), "cmdline": _cmdline(pid)})
        self._prev_snap, self._prev_t = snap, now
        self.foreign_pct.append(round(total, 1))
        self.foreign_in_mask.append(in_mask)
        if detail:
            if len(self.samples_detail) < self.max_detail:
                self.samples_detail.append(
                    {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                     "monotonic_s": round(now, 3), "in_mask": in_mask,
                     "foreign_cpu_pct_total": round(total, 1), "processes": detail})
            else:
                self.samples_dropped += 1

    def _sample_device(self) -> None:
        out = subprocess.run(
            ["nvidia-smi", f"--id={self.gpu_index}",
             "--query-gpu=memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        used, util = (x.strip() for x in out.split(","))
        self.vram_mib.append(int(used))
        self.gpu_util.append(int(util))

    def run(self) -> None:
        while not self._halt.is_set():
            self.samples += 1
            if self.samples % self.ps_every == 1 or self.ps_every == 1:
                try:
                    self._sample_foreign()
                except Exception:
                    pass
            if self.gpu_index is not None:
                try:
                    self._sample_device()
                except Exception:
                    pass
            self._halt.wait(self.period)

    def summary(self) -> Dict[str, Any]:
        def stats(xs: List[Any]) -> Dict[str, Any]:
            if not xs:
                return {"n": 0}
            return {"n": len(xs), "mean": round(statistics.fmean(xs), 2), "max": max(xs)}
        return {
            "device_sample_period_s": self.period,
            "foreign_sample_period_s": round(self.period * self.ps_every, 3),
            "samples_attempted": self.samples,
            "foreign_cpu_pct": stats(self.foreign_pct),
            "foreign_threads_inside_mask": stats(self.foreign_in_mask),
            "foreign_in_mask_by_command": dict(sorted(self.foreign_detail.items(),
                                                      key=lambda kv: -kv[1])[:10]),
            "ownership": self.ownership,
            "owned_sessions": sorted(x for x in self._own_sids if x is not None),
            "per_sample_in_mask_detail": self.samples_detail,
            "per_sample_detail_dropped": self.samples_dropped,
            "per_sample_detail_cap": self.max_detail,
            "foreign_definition": "CPU actually consumed between consecutive samples by "
                                  "processes outside this run's own subtree, from "
                                  "/proc/<pid>/stat utime+stime deltas. Username cannot be "
                                  "used here: concurrent round workers and ctffind all run as "
                                  "the same user. ps pcpu cannot be used either: it is a "
                                  "lifetime average and does not resolve activity during the "
                                  "run. Ownership is by session id, not by a walked process "
                                  "tree, which races with the sampler's own subprocesses. "
                                  "in-mask counts only threads in state R.",
            "device_vram_mib_sampled": stats(self.vram_mib),
            "device_util_pct_sampled": stats(self.gpu_util),
            "vram_note": "NVML sampled at this period; a sampled peak is a lower bound on the "
                         "true peak and is not the allocator-traced peak.",
        }


class RssSampler(threading.Thread):
    """Simultaneous process-tree RSS, so peaks are an observed sum and not a sum of maxima."""

    def __init__(self, root_pid: int, period: float = 0.25):
        super().__init__(daemon=True)
        self.root_pid = root_pid
        self.period = period
        self._halt = threading.Event()
        self.tree_rss_kib: List[int] = []
        self._peak_total = 0
        self._peak_members: List[Dict[str, Any]] = []
        self._peak_utc: Optional[str] = None

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                # Full descendant tree, not `ps --ppid`, which selects only immediate
                # children: helpers MotionCorr spawns (a shell, ghostscript) are
                # grandchildren and were omitted, so a figure labelled
                # peak_simultaneous_tree_rss_kib understated the tree it named -- and that
                # figure is what the per-process guidance rests on.
                pids = sorted(own_subtree(self.root_pid) | {self.root_pid})
                total, members = 0, []
                for pid in pids:
                    rss = _rss_kib(pid)
                    if rss is None:
                        continue                    # exited between listing and reading
                    total += rss
                    members.append({"pid": pid, "comm": _comm(pid), "rss_kib": rss})
                if total:
                    now = time.time()
                    self.tree_rss_kib.append(total)
                    if total > self._peak_total:
                        # Keep the composition of the peak, not just its value: a single
                        # number cannot say which processes were simultaneously resident.
                        self._peak_total = total
                        self._peak_members = members
                        self._peak_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
            except Exception:
                pass
            self._halt.wait(self.period)

    def summary(self) -> Dict[str, Any]:
        if not self.tree_rss_kib:
            return {"n": 0, "note": "no RSS sample landed; run may be shorter than the period"}
        return {
            "n": len(self.tree_rss_kib),
            "period_s": self.period,
            "unit": "KiB (ps/proc VmRSS), summed across all owned descendants in one sweep",
            "peak_simultaneous_tree_rss_kib": max(self.tree_rss_kib),
            "mean_simultaneous_tree_rss_kib": int(statistics.fmean(self.tree_rss_kib)),
            "peak_utc": self._peak_utc,
            "peak_composition": self._peak_members,
            "scope": "full descendant tree of the launcher, resolved per sample",
            "note": "maximum of simultaneously observed process-tree totals, not a sum of "
                    "independently observed per-process maxima",
        }


def own_subtree(root_pid: int) -> set:
    """PIDs of `root_pid` and all its descendants.

    Interference cannot be identified by username on these hosts: every concurrent round
    worker on cpu64 runs as `ubuntu`, and so do the two long-running `ctffind` jobs. A
    user-based filter there reports zero foreign load no matter what else is running, which
    is a check that structurally cannot observe the thing it asserts. Subtree membership is
    the property that actually distinguishes this run's work from everyone else's.
    """
    try:
        out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return {root_pid}
    children: Dict[int, List[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    seen, stack = set(), [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(children.get(pid, []))
    return seen


CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
# _stat_fields returns [comm] + fields 3.. , so returned[k] == /proc stat field (k + 2).
F_STATE, F_PPID, F_PGRP, F_SESSION = 1, 2, 3, 4          # fields 3, 4, 5, 6
F_UTIME, F_STIME, F_STARTTIME, F_PROCESSOR = 12, 13, 20, 37   # fields 14, 15, 22, 39


def _stat_fields(path: str) -> Optional[List[str]]:
    """Fields of a /proc stat file, split safely around the parenthesised comm."""
    try:
        with open(path) as fh:
            raw = fh.read()
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    return [raw[raw.find("(") + 1:close]] + raw[close + 2:].split()


def establish_isolated_session() -> Dict[str, Any]:
    """Make the runner's session genuinely its own, or record that it is not.

    Owning "the runner's session" is only sound if that session contains nothing else. The
    documented reproduction is `taskset -c … flock … python3 envelope_runner.py` with no
    `setsid`, so the sid is the login shell's: another worker's job, a build or an editor
    started from the same shell shares it and would be silently excluded from every
    interference figure, turning real lane contention into a reported zero.

    Already a session leader (launched under `setsid`) means the session is ours alone.
    Otherwise `setsid()` is attempted. If it cannot be had, ownership falls back to the
    process subtree, which is narrower and cannot hide an unrelated same-shell process, and
    the weaker basis is recorded rather than assumed away.
    """
    pid = os.getpid()
    try:
        if os.getsid(pid) == pid:
            return {"basis": "session", "isolated": True, "sid": pid,
                    "how": "already a session leader"}
    except OSError:
        pass
    try:
        os.setsid()
        return {"basis": "session", "isolated": True, "sid": os.getsid(pid),
                "how": "setsid() at startup"}
    except OSError as exc:
        return {"basis": "subtree", "isolated": False, "sid": _safe_sid(pid),
                "how": f"setsid() failed ({exc.__class__.__name__}); the session is shared "
                       f"with whatever launched this runner, so ownership is by process "
                       f"subtree instead and same-session strangers are NOT treated as ours"}


def _safe_sid(pid: int) -> Optional[int]:
    try:
        return os.getsid(pid)
    except OSError:
        return None


def own_session() -> int:
    """Session id of this runner.

    Session membership replaces a walked process tree for deciding what is ours. Building
    the tree from a `ps` snapshot races with the very children the sampler spawns: a `ps` or
    `nvidia-smi` forked microseconds earlier is absent from the snapshot and is then counted
    as foreign load. Observed on a real series as `foreign_cpu_max = 2750%` attributed to
    `ps` -- the sampler's own subprocess -- and to `gs`, MotionCorr's own ghostscript child.
    Every descendant inherits the session id, and the runner is launched under `setsid`, so
    the test is exact and needs no snapshot.
    """
    f = _stat_fields(f"/proc/{os.getpid()}/stat")
    try:
        return int(f[F_SESSION])
    except (TypeError, ValueError, IndexError):
        return -1


def cpu_snapshot() -> Dict[int, Any]:
    """{pid: (comm, busy_ticks, sid)} for every visible process.

    Busy ticks are cumulative utime+stime. Two snapshots give CPU actually consumed *between*
    them, which is the quantity an interference witness needs. `ps`'s `pcpu` cannot supply it:
    it is cputime divided by lifetime, so sampling it at 1 Hz yields the same slowly-drifting
    lifetime average every tick. A process that has run for 49 days and is saturating a core
    right now reads the same as one that is idle right now, and a driver that idles for hours
    and then spawns a build burst stays invisible for the whole burst.
    """
    snap: Dict[int, Any] = {}
    try:
        pids = [int(d) for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        return snap
    for pid in pids:
        f = _stat_fields(f"/proc/{pid}/stat")
        if not f or len(f) < 15:
            continue
        try:
            snap[pid] = (f[0], int(f[F_UTIME]) + int(f[F_STIME]), int(f[F_SESSION]))
        except (ValueError, IndexError):
            continue
    return snap


def running_threads_on(mask_cpus: set, pid: int) -> List[int]:
    """CPUs in `mask_cpus` on which this process currently has a RUNNING thread."""
    hits = []
    try:
        tids = os.listdir(f"/proc/{pid}/task")
    except OSError:
        return hits
    for tid in tids:
        f = _stat_fields(f"/proc/{pid}/task/{tid}/stat")
        if not f or len(f) < 39:
            continue
        # State R only: `psr` is populated for sleeping threads too, so counting every thread
        # whose last CPU happened to fall in the lane would flag idle sleepers as intruders
        # and keep a lane gate permanently non-clear on a quiet host.
        if f[F_STATE] != "R":
            continue
        try:
            cpu = int(f[F_PROCESSOR])
        except (ValueError, IndexError):
            continue
        if cpu in mask_cpus:
            hits.append(cpu)
    return hits


def lane_foreign_threads(mask_cpus: set, own: set, min_pct: float = 20.0,
                         window_s: float = 0.4) -> List[str]:
    """Foreign processes actually burning CPU inside our cpuset over a short window."""
    if not mask_cpus:
        return []
    a = cpu_snapshot()
    time.sleep(window_s)
    b = cpu_snapshot()
    sid = own_session()
    hits = []
    for pid, (comm, ticks, psid) in b.items():
        if psid == sid or pid in own or pid not in a:
            continue
        pct = (ticks - a[pid][1]) / CLK_TCK / window_s * 100.0
        if pct < min_pct:
            continue
        cpus = running_threads_on(mask_cpus, pid)
        if cpus:
            hits.append(f"pid={pid} comm={comm} cpu_pct={pct:.0f} on_cpus={sorted(set(cpus))}")
    return hits


def resolve_payload(launcher_pid: int, binary: Path, deadline_s: float = 20.0
                    ) -> Optional[Dict[str, Any]]:
    """Find the live process actually executing `binary` beneath the launcher.

    `execute_arm` spawns `taskset -c <mask> /usr/bin/time -v <binary> ...`, so `proc.pid` is
    the launcher, and `taskset` execs into `/usr/bin/time` rather than into the payload. A
    witness sampled on `proc.pid` therefore describes `/usr/bin/time` -- which is what
    happened: a retained `numa_maps` mapped `file=/usr/bin/time`, and its `numastat` total of
    1.45 was MB of launcher memory, not GB of movie arrays.

    Identity is confirmed by resolving `/proc/<pid>/exe`, not by matching a command line,
    and the process start time is recorded so a later sample can prove it is still the same
    process rather than a recycled pid.
    """
    want = os.path.realpath(str(binary))
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        # Sorted, not set order: a payload that forks without exec gives parent and child
        # the same /proc/<pid>/exe, and an arbitrary pick would make the identity witness
        # non-deterministic. Lowest pid prefers the process the launcher started.
        for pid in sorted(_descendants(launcher_pid) | {launcher_pid}):
            try:
                exe = os.path.realpath(f"/proc/{pid}/exe")
            except OSError:
                continue
            if exe != want:
                continue
            f = _stat_fields(f"/proc/{pid}/stat")
            return {"pid": pid, "exe": exe,
                    "starttime_ticks": int(f[F_STARTTIME]) if f and len(f) > F_STARTTIME else None,
                    "session": int(f[F_SESSION]) if f and len(f) > F_SESSION else None,
                    "launcher_pid": launcher_pid,
                    "resolved_after_s": round(time.time() - t0, 3)}
        time.sleep(0.05)
    return None


def _descendants(root: int) -> set:
    try:
        out = subprocess.run(["ps", "-eo", "pid=,ppid="], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return set()
    kids: Dict[int, List[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                kids.setdefault(int(parts[1]), []).append(int(parts[0]))
            except ValueError:
                pass
    seen, stack = set(), list(kids.get(root, []))
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        stack.extend(kids.get(pid, []))
    return seen


def numa_residency(pid: int) -> Optional[Dict[str, Any]]:
    """Per-node resident bytes for one pid, aggregated from /proc/<pid>/numa_maps.

    Read in pages and converted with each mapping's own `kernelpagesize_kB`, so the unit is
    explicit. `numastat -p` was used before and reports **MB**; its "Total 1.45" was read as
    1.45 GB, which inflated a launcher's few megabytes into a claim about movie arrays.
    """
    per_node: Dict[str, int] = {}
    total = 0
    try:
        lines = pathlib_Path(f"/proc/{pid}/numa_maps").read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        toks = line.split()
        pagesize_kb = 4
        for t in toks:
            if t.startswith("kernelpagesize_kB="):
                try:
                    pagesize_kb = int(t.split("=", 1)[1])
                except ValueError:
                    pass
        for t in toks:
            if t.startswith("N") and "=" in t and t[1:2].isdigit():
                node, _, cnt = t.partition("=")
                try:
                    b = int(cnt) * pagesize_kb * 1024
                except ValueError:
                    continue
                per_node[node] = per_node.get(node, 0) + b
                total += b
    if not total:
        return None
    return {"resident_bytes_by_node": per_node,
            "resident_bytes_total": total,
            "resident_MiB_total": round(total / 1048576.0, 2),
            "node_local_fraction_note": "fraction is only meaningful once the sampled pid is "
                                        "confirmed to be the payload; see payload_identity",
            "unit": "bytes, from numa_maps page counts x that mapping's kernelpagesize_kB"}


def _rss_kib(pid: int) -> Optional[int]:
    try:
        with open(f"/proc/{pid}/statm") as fh:
            return int(fh.read().split()[1]) * (os.sysconf("SC_PAGE_SIZE") // 1024)
    except (OSError, ValueError, IndexError):
        return None


def _comm(pid: int) -> str:
    f = _stat_fields(f"/proc/{pid}/stat")
    return f[0] if f else ""


def _cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()[:200]
    except OSError:
        return ""


def _starttime(pid: int) -> Optional[int]:
    f = _stat_fields(f"/proc/{pid}/stat")
    try:
        return int(f[F_STARTTIME]) if f and len(f) > F_STARTTIME else None
    except (ValueError, IndexError):
        return None


def parse_cpu_list(spec: str) -> set:
    cpus = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-")
            cpus.update(range(int(lo), int(hi) + 1))
        else:
            cpus.add(int(part))
    return cpus


def group_members(pgid: int, sid: Optional[int] = None) -> Optional[Dict[int, Any]]:
    """Live, non-zombie members of process group `pgid`, keyed by pid -> (comm, starttime).

    Enumerated by scanning `/proc` for the group id rather than by walking descendants.
    Reparenting is exactly the case that matters here: when the launcher dies, its children
    are reparented to init and a descendant walk from the launcher pid finds nothing, while
    the processes keep running. **A process group survives reparenting**, so pgid membership
    still sees them.

    Zombies are excluded: a reaped-but-not-collected process answers `kill(pid, 0)` yet
    consumes nothing, so counting it as a survivor would make cleanup impossible to confirm.

    The start time is returned so a later check can reject a recycled pid: on a busy host a
    pid can be reused between polls, and killing it would target an unrelated process.
    """
    out: Dict[int, Any] = {}
    try:
        pids = [int(d) for d in os.listdir("/proc") if d.isdigit()]
    except OSError:
        # Returning {} here would make "I could not enumerate" indistinguishable from
        # "the group is empty", and the caller would report cleanup confirmed having
        # observed nothing -- the same vacuity class as the defect this function fixes.
        return None
    for pid in pids:
        f = _stat_fields(f"/proc/{pid}/stat")
        if not f or len(f) <= F_STARTTIME:
            continue
        try:
            in_group = int(f[F_PGRP]) == pgid
            # A child that calls setpgid() leaves the group and is invisible to killpg, but
            # setpgid does not change the session, so the session catches it. Only setsid()
            # escapes both, and nothing in this codebase calls it.
            in_session = sid is not None and int(f[F_SESSION]) == sid
            if not (in_group or in_session):
                continue
            if f[F_STATE] == "Z":                 # zombie: not running, not a survivor
                continue
            out[pid] = (f[0], int(f[F_STARTTIME]), in_group)
        except (ValueError, IndexError):
            continue
    return out


def _kill_group(proc: "subprocess.Popen", pgid: int, log: List[str],
                grace_s: float = 10.0, kill_s: float = 10.0,
                hold_s: float = 60.0, sid: Optional[int] = None) -> Dict[str, Any]:
    """Terminate the owned process group and *verify* it is gone before returning.

    Escalation is driven by surviving owned-group members, never by the launcher's exit. The
    previous version broke out of its signal loop as soon as `proc.wait()` returned, so a
    cooperative parent that exits on SIGTERM satisfied it while a child ignoring SIGTERM kept
    running; it then looked for survivors by descending from a dead launcher, found none
    because they had been reparented, logged `group_alive=True`, and returned anyway.

    Fails closed: if the group cannot be confirmed dead, this **blocks** for up to `hold_s`
    rather than returning, because the caller's flock is released when the runner exits and
    an unconfirmed survivor would then run underneath whoever measures next. Holding the lock
    is the safe direction. The outcome is returned so the caller can abort the series.
    """
    sid = sid if sid is not None else pgid          # session leader: sid == launcher pid
    first = group_members(pgid, sid) or {}
    own_start = {pid: meta[1] for pid, meta in first.items()}
    enum_failed = {"v": False}

    def survivors() -> Dict[int, Any]:
        m = group_members(pgid, sid)
        if m is None:
            enum_failed["v"] = True
            # Cannot observe -> must not be read as empty. Report a sentinel survivor so
            # every caller path treats this as unconfirmed.
            return {-1: ("<enumeration-failed>", 0, False)}
        # Reject recycled pids: same pid, different start time is a different process.
        return {pid: meta for pid, meta in m.items()
                if pid not in own_start or own_start[pid] == meta[1]}

    def signal_group(sig: int, name: str) -> None:
        try:
            os.killpg(pgid, sig)
            log.append(f"sent {name} to group {pgid}")
        except ProcessLookupError:
            log.append(f"group {pgid} already gone at {name}")
        except Exception as exc:
            log.append(f"killpg {name} failed: {exc}")
        # killpg cannot reach a member that left the group via setpgid; signal those by pid.
        cur = group_members(pgid, sid)
        for pid, meta in (cur or {}).items():
            if pid > 0 and not meta[2]:
                try:
                    os.kill(pid, sig)
                    log.append(f"sent {name} directly to out-of-group session member {pid}")
                except OSError:
                    pass

    def wait_clear(deadline_s: float) -> Dict[int, Any]:
        t0 = time.time()
        while time.time() - t0 < deadline_s:
            left = survivors()
            if not left:
                return {}
            time.sleep(0.2)
        return survivors()

    signal_group(signal.SIGTERM, "SIGTERM")
    left = wait_clear(grace_s)
    escalated = bool(left)
    if left:
        log.append(f"SIGTERM left {len(left)} owned member(s) alive: "
                   f"{[(pid, meta[0]) for pid, meta in left.items()]}; escalating")
        signal_group(signal.SIGKILL, "SIGKILL")
        left = wait_clear(kill_s)

    held_s = 0.0
    if left:
        # Fail closed. Keep re-signalling and keep the caller's lock held while an owned
        # process is demonstrably still running.
        t0 = time.time()
        while time.time() - t0 < hold_s:
            signal_group(signal.SIGKILL, "SIGKILL(retry)")
            left = wait_clear(2.0)
            if not left:
                break
        held_s = round(time.time() - t0, 1)

    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    confirmed = (not left) and not enum_failed["v"]
    log.append(f"cleanup_confirmed={confirmed} enumeration_failed={enum_failed['v']} "
               f"escalated={escalated} "
               f"held_for_s={held_s} survivors={[(p, m[0]) for p, m in left.items()]}")
    return {"cleanup_confirmed": confirmed,
            "enumeration_failed": enum_failed["v"],
            "escalated_to_sigkill": escalated,
            "blocked_seconds_holding_lock": held_s,
            "surviving_group_members": [{"pid": p, "comm": m[0], "starttime": m[1]}
                                        for p, m in left.items()],
            "returncode": proc.returncode if proc.returncode is not None else -9}


@contextlib.contextmanager
def _deferred_interrupts(log: List[str]):
    """Hold SIGINT/SIGTERM until cleanup finishes, then re-raise the first one seen."""
    caught: List[int] = []
    try:
        prev = {sig: signal.signal(sig, lambda s, f: caught.append(s))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    except (ValueError, OSError):
        yield                                    # not on the main thread; nothing to shield
        return
    try:
        yield
    finally:
        for sig, handler in prev.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
        if caught:
            log.append(f"deferred signals during cleanup: {caught}; re-raising")
            os.kill(os.getpid(), caught[0])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def settle(load_max: float, timeout_s: int, log: List[str], mode: str = "global_load",
           lane_mask: Optional[str] = None) -> Dict[str, Any]:
    """Wait for the previous mutex holder's decay tail. Runs after acquisition, by contract.

    Two modes, because the right gate depends on who else is legitimately on the box.

    `global_load` waits for system `load1` to fall below a threshold. That is correct when
    the mutex is expected to give exclusive use of the whole machine.

    `lane` waits instead for this run's own cpuset to be free of busy foreign threads, and
    records `load1` as a witness without gating on it. On a host where other workers hold a
    different lock and are pinned to a disjoint lane, a global-load gate would time out on
    every run while measuring nothing about our own cores -- and a timeout that fires every
    time degrades silently to "wait the whole budget, then run anyway".

    Compiler detection uses exact process names. `pgrep -f` matches the probe's own command
    line, so it is permanently non-zero and the guard never fires.
    """
    t0 = time.time()
    lane_cpus = parse_cpu_list(lane_mask) if lane_mask else set()
    own = own_subtree(os.getpid())
    waited, load1, comps, intruders = 0.0, None, 0, []
    while True:
        load1 = float(open("/proc/loadavg").read().split()[0])
        comps = 0
        for name in COMPILER_NAMES:
            r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
            comps += len([x for x in r.stdout.split() if x.strip()])
        intruders = lane_foreign_threads(lane_cpus, own) if lane_cpus else []
        waited = time.time() - t0
        clear = (not intruders) if mode == "lane" else (load1 < load_max)
        if clear and comps == 0:
            break
        if waited >= timeout_s:
            log.append(f"SETTLE_TIMEOUT after {waited:.0f}s mode={mode} load1={load1} "
                       f"compilers={comps} lane_intruders={len(intruders)}")
            break
        time.sleep(3.0)
    return {"mode": mode, "waited_s": round(waited, 1), "load1_at_start": load1,
            "compilers_running": comps, "load_max_threshold": load_max,
            "lane_mask": lane_mask, "lane_intruders_at_start": intruders,
            "timed_out": waited >= timeout_s}


# ----------------------------------------------------------------------------- one run


# Two distinct instrumented formats, matched strictly rather than by a loose "name: number"
# rule. A loose rule silently promotes ordinary log prose into the interval record: "Frames to
# be used: 1 2 3 ..." became a stage named "Frames to be used" with value 1.0, and "The pixel
# size for CTF estimation: 1.234" became a 1.234-second stage. Both are reported here as
# stages that do not exist.
#
# The `-` in each class is placed last so it is a literal. Written `[A-Za-z0-9_ -()]`, the
# sequence ' -(' is the range 0x20-0x28 and `-` is not a member, which is how an earlier
# parser silently dropped every hyphenated tag ('dw - iFFT', 'prep patch - FFT').
TIMER_LINE = re.compile(
    r"^([A-Za-z0-9_(). -]+?)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*sec\s*\(\s*([0-9]+)\s*"
    r"microsec/operation\s*\)\s*$")
CUDA_PROFILE_LINE = re.compile(
    r"^\s*([A-Za-z0-9_(). -]+?)\s*:\s*([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)\s*"
    r"(ms|s|MiB)\s*$")
CUDA_FALLBACK = re.compile(
    r"falling back|fall back|materializing host frames|WARNING: CUDA", re.I)
CUDA_EXECUTED = re.compile(r"Total GPU alignment time|\(CUDA in-VRAM\)")


def parse_stage_timers(text: str) -> Dict[str, Any]:
    """Parse both instrumented formats, keeping them in separate namespaces.

    `TIMING=ON` writes its whole-run breakdown to **stdout** (`src/time.cpp` via
    `motioncorr_runner.cpp:654`), not into the per-movie logfile.

    Repeated keys are **never collapsed by addition**. Each tag keeps its occurrence list
    plus an explicit `n`, `sum` and `max`, and the caller must choose which is meaningful for
    that tag. Blind summation produced a concrete false result here: the CUDA profile prints
    `Peak GPU memory allocated` once per global/local call -- 25 patch calls at 62.59 MiB and
    one global call at 1569.59 MiB in a 5x5 movie -- and summing them yielded 3134.34 MiB,
    which was then reported as a process peak. Adding size-accounting values from successive
    calls does not produce a simultaneous peak, and for size-like tags the sum has no
    physical meaning at all.

    Note what these values are at the measured source: `cuda_alignpatch.cu:310-318` builds
    `total_vram_allocated` by adding buffer-size expressions and the cuFFT workspace for one
    function call. It is size accounting, not an allocator trace, whichever statistic is
    taken from it.
    """
    timing: Dict[str, Any] = {}
    cuda: Dict[str, Any] = {}
    for line in text.splitlines():
        m = TIMER_LINE.match(line)
        if m:
            timing.setdefault(m.group(1).strip(), []).append(float(m.group(2)))
            continue
        m = CUDA_PROFILE_LINE.match(line)
        if m:
            tag = m.group(1).strip() + (f" [{m.group(3)}]" if m.group(3) != "s" else "")
            cuda.setdefault(tag, []).append(float(m.group(2)))
    return {"timing_stdout": _collapse(timing), "cuda_profile": _collapse(cuda)}


def _collapse(d: Dict[str, List[float]]) -> Dict[str, Any]:
    """Keep every occurrence; expose n/sum/max without choosing one for the caller."""
    out: Dict[str, Any] = {}
    for tag, vals in d.items():
        entry: Dict[str, Any] = {"n": len(vals), "sum": round(sum(vals), 6),
                                 "max": max(vals), "values": vals if len(vals) <= 64
                                 else vals[:64] + ["...truncated"]}
        if _is_size_tag(tag):
            # A sum of per-call size accounting is not a quantity; refuse to publish one.
            entry["sum"] = None
            entry["sum_withheld_reason"] = (
                "per-call size accounting; the sum across calls is not a peak and has no "
                "physical meaning. Use 'max' as the largest single reported accounting "
                "value, and note that even that is buffer-size accounting, not an "
                "allocator trace.")
        out[tag] = entry
    return out


def _is_size_tag(tag: str) -> bool:
    return "[MiB]" in tag or "VRAM" in tag or "memory" in tag.lower()


def time_v_fields(text: str) -> Dict[str, Any]:
    want = {
        "User time (seconds)": "user_s",
        "System time (seconds)": "sys_s",
        "Elapsed (wall clock) time (h:mm:ss or m:ss)": "wall_str",
        "Percent of CPU this job got": "pct_cpu",
        "Maximum resident set size (kbytes)": "maxrss_kib",
        "Voluntary context switches": "vol_ctx",
        "Involuntary context switches": "invol_ctx",
        "File system inputs": "fs_inputs",
        "File system outputs": "fs_outputs",
        "Exit status": "time_reported_exit",
    }
    out: Dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        # rpartition, not partition: the wall-clock line is
        # "Elapsed (wall clock) time (h:mm:ss or m:ss): 0:29.03" and splitting on the first
        # colon yields the key "Elapsed (wall clock) time (h", which matches nothing.
        k, _, v = line.strip().rpartition(":")
        key = want.get(k.strip())
        if key is None:                       # values like 0:29.03 also contain a colon
            for full, short in want.items():
                if line.strip().startswith(full + ":"):
                    key = short
                    v = line.strip()[len(full) + 1:]
                    break
        if key:
            v = v.strip()
            try:
                out[key] = float(v) if "." in v else int(v)
            except ValueError:
                out[key] = v
    return out


def execute_arm(arm: Dict[str, Any], cfg: Dict[str, Any], outdir: Path,
                pair_index: int, order_in_pair: int, rep: int) -> Dict[str, Any]:
    tag = f"{arm['id']}_pair{pair_index}_ord{order_in_pair}_rep{rep}"
    rundir = outdir / tag
    if rundir.exists():
        shutil.rmtree(rundir)
    (rundir / "out").mkdir(parents=True)
    log: List[str] = []

    cpu_mask = arm["cpu_mask"]
    # Settle policy. The full gate exists to avoid the *previous mutex holder's* load decay
    # tail, so it is worth its cost once, before the first run. Applying it between every run
    # of one series would instead wait out this series' own tail: after a 16-thread arm,
    # load1 needs minutes to fall below the threshold, so the gate would time out on every
    # run and triple the series length while measuring nothing. Between runs a fixed quiet
    # interval is used instead. It is identical for every arm, so it cannot favour one side
    # of a pair, and each record states which regime applied.
    if cfg.get("settle_full_gate", True) and not cfg.get("_first_run_done"):
        settle_info = settle(cfg.get("settle_load_max", 2.0),
                             cfg.get("settle_timeout_s", 300), log,
                             mode=cfg.get("settle_mode", "global_load"),
                             lane_mask=cpu_mask)
        settle_info["regime"] = "full_gate_first_run_of_series"
        cfg["_first_run_done"] = True
    else:
        quiet = float(cfg.get("inter_run_quiet_s", 5.0))
        time.sleep(quiet)
        settle_info = {"regime": "fixed_inter_run_quiet", "waited_s": quiet,
                       "load1_at_start": float(open("/proc/loadavg").read().split()[0]),
                       "lane_intruders_at_start":
                           lane_foreign_threads(parse_cpu_list(cpu_mask), own_subtree(os.getpid()))}

    cmd = ["taskset", "-c", cpu_mask, "/usr/bin/time", "-v", arm["binary"],
           "--i", arm["input_star"], "--o", str(rundir / "out") + "/",
           "--j", str(arm["j"])]
    if arm.get("max_io_threads"):
        cmd += ["--max_io_threads", str(arm["max_io_threads"])]
    if arm.get("gpu") is not None:
        cmd += ["--gpu", str(arm["gpu"])]
    cmd += arm.get("extra_opts", [])

    env = dict(os.environ)
    for k, v in (arm.get("env") or {}).items():
        env[k] = str(v)

    gpu_index = arm.get("gpu")
    # Device identity, per run. An ordinal is not identity: it is relative to
    # CUDA_VISIBLE_DEVICES, which any caller can set. Resolve it to the UUID and record the
    # visibility environment alongside it.
    device_identity: Dict[str, Any] = {"requested_ordinal": gpu_index}
    if gpu_index is not None:
        device_identity["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "<unset>")
        device_identity["nvidia_smi_row"] = sh(
            f"nvidia-smi --id={gpu_index} --query-gpu=index,uuid,name,memory.total "
            f"--format=csv,noheader")

    samp = Sampler(own_user=cfg["own_user"], gpu_index=gpu_index, mask=cpu_mask,
                   period=cfg.get("device_sample_period_s", 0.2),
                   ps_period=cfg.get("foreign_sample_period_s", 1.0),
                   own_root_pid=os.getpid(),
                   ownership=cfg.get("_ownership"),
                   max_detail=cfg.get("per_sample_detail_cap", 4000))
    samp.start()

    t0 = time.time()
    # start_new_session puts the launcher and every descendant in one process group we own,
    # so cancellation can reach the payload. proc.kill() alone signals only the
    # taskset/time launcher, and MotionCorr (or its ghostscript child) can outlive it,
    # keep burning the cpuset and the GPU, and contaminate whichever arm runs next --
    # including someone else's, after the flock is released.
    proc = subprocess.Popen(cmd, cwd=arm["cwd"], env=env,
                            stdout=(rundir / "stdout.log").open("w"),
                            stderr=(rundir / "time_stderr.log").open("w"),
                            start_new_session=True)
    numa_timer: Optional[threading.Timer] = None
    # Everything from here to the wait is inside a guard: any exception in setup --
    # most plausibly "can't start new thread" from a sampler under a cgroup pids.max cap
    # with several round workers active -- would otherwise escape with the payload running
    # and no cleanup, which is the original defect by another route.
    try:
        pgid = os.getpgid(proc.pid)
        # start_new_session makes the launcher a session leader, so its sid equals its pid.
        # Adopt it here rather than waiting for resolve_payload, otherwise every sample taken in
        # the interval between spawning and resolving would count our own payload as foreign.
        samp.own_also(proc.pid)
        samp.own_pid_tree(proc.pid)      # also covers the non-isolated-session fallback
        rss = RssSampler(proc.pid, period=cfg.get("rss_period_s", 0.25))
        rss.start()

        # Placement. Two distinct witnesses, never merged: the launcher's inherited cpuset
        # (which the payload inherits across exec) and the payload's own residency.
        placement: Dict[str, Any] = {"requested_cpu_mask": cpu_mask}
        for _ in range(40):
            try:
                st = Path(f"/proc/{proc.pid}/status").read_text()
                placement["launcher_Cpus_allowed_list"] = re.search(
                    r"Cpus_allowed_list:\s*(\S+)", st).group(1)
                placement["launcher_Mems_allowed_list"] = re.search(
                    r"Mems_allowed_list:\s*(\S+)", st).group(1)
                break
            except Exception:
                time.sleep(0.25)

        payload = resolve_payload(proc.pid, Path(arm["binary"]))
        placement["payload_identity"] = payload or {
            "resolved": False,
            "note": "the process executing the binary was not found beneath the launcher; no "
                    "payload-level memory or cpuset witness is claimed for this run"}
        if payload:
            pid = payload["pid"]
            samp.own_also(payload.get("session"))
            try:
                st = Path(f"/proc/{pid}/status").read_text()
                placement["payload_Cpus_allowed_list"] = re.search(
                    r"Cpus_allowed_list:\s*(\S+)", st).group(1)
                placement["payload_Mems_allowed_list"] = re.search(
                    r"Mems_allowed_list:\s*(\S+)", st).group(1)
            except Exception:
                pass
            # Sample residency mid-run rather than at startup: an early sample catches the
            # process before it has allocated the arrays the witness is supposed to describe.
            placement["payload_numa_early"] = numa_residency(pid)
            threading.Timer(
                max(1.0, cfg.get("numa_sample_at_s", 5.0)),
                lambda: placement.__setitem__("payload_numa_midrun", numa_residency(pid))
            ).start()
    except BaseException:                        # re-raised below, after cleanup
        _pgid = None
        try:
            _pgid = os.getpgid(proc.pid)
        except OSError:
            pass
        if _pgid is not None:
            with _deferred_interrupts(log):
                _kill_group(proc, _pgid, log, sid=_pgid)
        raise

    timed_out = False
    cleanup: Optional[Dict[str, Any]] = None
    sid = pgid                                   # launcher is the session leader
    try:
        rc = proc.wait(timeout=cfg.get("run_timeout_s", 7200))
        # The normal-exit path must verify the group too: any process the payload spawns
        # and does not reap outlives it, is reparented to init, keeps the pgid, and burns
        # the cpuset underneath the next arm. Because it inherits the payload's session the
        # interference sampler adopts it, so it would be neither killed, nor reported, nor
        # quarantined. Checking only the abnormal paths left a hole of the same shape this
        # function exists to close.
        #
        # Not currently reachable via ghostscript, despite the obvious guess: CPlot2D.cpp:57
        # invokes gs through system(), which blocks and reaps. The mechanism is generic, and
        # control_6 drives it with a payload that forks and returns.
        residual = group_members(pgid, sid)
        if residual is None or residual:
            log.append(f"run exited {rc} but the owned group is not empty: "
                       f"{'<enumeration failed>' if residual is None else sorted(residual)}")
            cleanup = _kill_group(proc, pgid, log, sid=sid)
            cleanup["triggered_by"] = RESIDUAL_AFTER_NORMAL_EXIT
    except subprocess.TimeoutExpired:
        timed_out = True
        log.append(f"RUN_TIMEOUT after {cfg.get('run_timeout_s', 7200)}s; "
                   f"terminating owned process group {pgid}")
        cleanup = _kill_group(proc, pgid, log, sid=sid)
        cleanup["triggered_by"] = "run timeout"
        rc = cleanup["returncode"]
    except BaseException:
        # Shield cleanup from a second interrupt. The block below can run for up to
        # grace+kill+hold seconds entirely inside time.sleep(), and a second Ctrl-C there
        # would propagate out with the group unverified. That matters more since
        # start_new_session took the payload out of the terminal's foreground group, so it
        # no longer receives the operator's SIGINT directly and depends on this handler.
        with _deferred_interrupts(log):
            cleanup = _kill_group(proc, pgid, log, sid=sid)
            cleanup["triggered_by"] = "exception during run"
        raise
    finally:
        if numa_timer is not None:
            numa_timer.cancel()
        wall = time.time() - t0
        samp.stop(); rss.stop()
        samp.join(timeout=15); rss.join(timeout=15)
        if samp.is_alive() or rss.is_alive():
            log.append("a sampler thread did not stop within 15s; its summary may be partial")

    time_txt = (rundir / "time_stderr.log").read_text(errors="replace")
    stdout_txt = (rundir / "stdout.log").read_text(errors="replace")

    stage = {"whole_run_stdout": parse_stage_timers(stdout_txt)["timing_stdout"],
             "per_movie": {},
             "semantics": "each tag carries n/sum/max/values. 'sum' is withheld for size-like "
                          "tags because adding per-call size accounting does not yield a "
                          "peak. No tag here is an allocator trace."}
    executed, fell_back, movie_logs = 0, [], 0
    for lg in sorted((rundir / "out").rglob("*.log")):
        txt = lg.read_text(errors="replace")
        movie_logs += 1
        stage["per_movie"][lg.name] = parse_stage_timers(txt)["cuda_profile"]
        if CUDA_EXECUTED.search(txt):
            executed += 1
        for line in txt.splitlines():
            if CUDA_FALLBACK.search(line):
                fell_back.append(f"{lg.name}: {line.strip()[:120]}")
    # The startup banner only proves --gpu was passed to a CUDA build: it is printed in
    # initialise() before any movie is read, and it survives every movie falling back to the
    # CPU. The per-movie evidence below is what distinguishes a GPU run from a silent
    # CPU-fallback run that would look several times slower for no recorded reason.
    backend_witness = {
        "startup_banner": [ln for ln in stdout_txt.splitlines()
                           if "CUDA acceleration on GPU device" in ln][:2],
        "movie_logs_seen": movie_logs,
        "movies_with_cuda_execution_evidence": executed,
        "fallback_warnings": fell_back,
        "all_movies_on_cuda": (gpu_index is not None and movie_logs > 0
                               and executed == movie_logs and not fell_back),
    }

    products = []
    for f in sorted((rundir / "out").rglob("*")):
        if f.is_file():
            entry = {"path": str(f.relative_to(rundir / "out")),
                     "bytes": f.stat().st_size,
                     "sha256": sha256_file(f)}
            if f.suffix in (".mrc", ".mrcs"):
                entry["mrc"] = mrc_split_digests(f)
            products.append(entry)

    return {
        "tag": tag,
        "arm_id": arm["id"],
        "pair_index": pair_index,
        "order_in_pair": order_in_pair,
        "rep": rep,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "command": cmd,
        "binary": arm["binary"],
        "binary_sha256": sha256_file(Path(arm["binary"])),
        "cwd": arm["cwd"],
        "env_overrides": arm.get("env") or {},
        "exit_code": rc,
        "timed_out": timed_out,
        "cleanup": cleanup,
        # An arm whose owned group could not be confirmed dead has left something running
        # that will contaminate whatever measures next, including another task after the
        # lock is released. It is never clean evidence.
        "cleanup_unconfirmed": bool(cleanup and not cleanup.get("cleanup_confirmed")),
        "wall_s": round(wall, 3),
        "requested": {"j": arm["j"], "max_io_threads": arm.get("max_io_threads"),
                      "gpu_ordinal": gpu_index},
        "device_identity": device_identity,
        "effective": {"j": arm["j"],
                      "io_threads": min(arm["j"], arm["max_io_threads"])
                      if (arm.get("max_io_threads") or -1) > 0 else arm["j"]},
        "settle": settle_info,
        # A gate that recorded a timeout or a lane intruder and then ran anyway has not been
        # satisfied. Marking the arm quarantined keeps it in the record -- deleting a timed
        # arm is worse -- while stopping the report from counting it as clean evidence.
        "quarantined": bool(settle_info.get("timed_out")
                            or settle_info.get("lane_intruders_at_start")
                            or (cleanup and not cleanup.get("cleanup_confirmed"))
                            # A residual group member at normal exit was, by construction,
                            # running *during* the timed interval: the payload spawned it
                            # and it outlived the payload. It shared the cpuset while the
                            # arm was measured, and because it inherits the payload's
                            # session the interference sampler adopted it, so it is absent
                            # from foreign_cpu_pct too. Killing it afterwards cleans the
                            # host; it does not clean the measurement.
                            or (cleanup and cleanup.get("triggered_by")
                                == RESIDUAL_AFTER_NORMAL_EXIT)),
        "quarantine_reason": (
            "a process spawned by the payload outlived it and shared the cpuset during the "
            "timed interval; it was reaped afterwards but the timing is contaminated: "
            + str((cleanup or {}).get("surviving_group_members")
                  or (cleanup or {}).get("triggered_by"))
            if (cleanup and cleanup.get("cleanup_confirmed")
                and cleanup.get("triggered_by") == RESIDUAL_AFTER_NORMAL_EXIT) else
            "owned process group could not be confirmed dead: "
            + str((cleanup or {}).get("surviving_group_members"))
            if (cleanup and not cleanup.get("cleanup_confirmed")) else
            "settle gate timed out" if settle_info.get("timed_out") else
            ("foreign threads were in the lane at start: "
             + "; ".join(settle_info.get("lane_intruders_at_start") or [])[:300])
            if settle_info.get("lane_intruders_at_start") else None),
        "cache_regime": {
            "declared": arm.get("cache_regime", "warm-unless-first"),
            "host_cached_kib": _as_int(sh("awk '/^Cached:/{print $2}' /proc/meminfo")),
            "note": "global cache drops are forbidden on this shared host, so the page-cache "
                    "regime is recorded, not controlled; 'File system inputs: 0' in rusage "
                    "means the read was served from cache, not that decode was free",
        },
        "placement": placement,
        "resource_usage": time_v_fields(time_txt),
        "memory": rss.summary(),
        "sampling": samp.summary(),
        "stage_timers": stage,
        "stage_timers_note": "whole_run_stdout comes from the TIMING build only and is absent "
                             "otherwise; per_movie holds the CUDA profile block. Intervals nest "
                             "and overlap, so they are never summed into a total, and no TIFF "
                             "cost is derived as wall minus GPU kernel timers. The in-binary "
                             "Timer is not thread-safe, so a stage covering parallel work is "
                             "indicative, not exact.",
        "backend_witness": backend_witness,
        "products": products,
        "product_count": len(products),
        "notes": log,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--own-user", default=os.environ.get("USER", "unknown"))
    args = ap.parse_args()

    args.out = args.out.resolve()   # child cwd differs from ours; product paths must not be relative
    plan = json.loads(args.plan.read_text())
    cfg = plan.get("config", {})
    cfg.setdefault("own_user", args.own_user)
    cfg["_ownership"] = establish_isolated_session()
    print(f"ownership: {cfg['_ownership']}", flush=True)
    args.out.mkdir(parents=True, exist_ok=True)

    series = {
        "plan_name": plan.get("name", "unnamed"),
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "source_commit": plan.get("source_commit"),
        "host": host_witness(),
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "ownership": cfg.get("_ownership"),
        "inputs": {k: sha256_file(Path(v)) for k, v in (plan.get("input_hashes") or {}).items()},
        "binaries": {k: sha256_file(Path(v)) for k, v in (plan.get("binaries") or {}).items()},
        "runs": [],
    }
    (args.out / "series.json").write_text(json.dumps(series, indent=2))

    arms = {a["id"]: a for a in plan["arms"]}
    for step in plan["schedule"]:
        arm = arms[step["arm"]]
        rec = execute_arm(arm, cfg, args.out, step["pair"], step["order"], step.get("rep", 1))
        series["runs"].append(rec)
        (args.out / "series.json").write_text(json.dumps(series, indent=2))
        print(f"{rec['tag']}: exit={rec['exit_code']} wall={rec['wall_s']}s "
              f"products={rec['product_count']}", flush=True)
        if rec.get("cleanup_unconfirmed"):
            # Abort rather than run the next arm beside a process we could not kill.
            print("SERIES_ABORTED_UNCONFIRMED_CLEANUP "
                  f"{rec['cleanup']['surviving_group_members']}", flush=True)
            series["aborted"] = {"after": rec["tag"], "reason": "cleanup unconfirmed",
                                 "survivors": rec["cleanup"]["surviving_group_members"]}
            (args.out / "series.json").write_text(json.dumps(series, indent=2))
            return 3

    print("SERIES_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
