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
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            return None
        nsymbt = int.from_bytes(raw[92:96], "little", signed=True)
        if nsymbt < 0 or 1024 + nsymbt > len(raw):
            return None
        off = 1024 + nsymbt
        return {
            "core_header_sha256": hashlib.sha256(raw[:224]).hexdigest(),
            "labels_sha256": hashlib.sha256(raw[224:1024]).hexdigest(),
            "payload_sha256": hashlib.sha256(raw[off:]).hexdigest(),
            "payload_bytes": len(raw) - off,
            "nsymbt": nsymbt,
        }
    except Exception:
        return None


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
                 period: float = 0.2, ps_period: float = 1.0):
        super().__init__(daemon=True)
        self.own_user = own_user
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

    def _sample_foreign(self) -> None:
        out = subprocess.run(["ps", "-eLo", "user=,pcpu=,psr="],
                             capture_output=True, text=True, timeout=10).stdout
        total, in_mask = 0.0, 0
        for line in out.splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue
            user, pcpu, psr = parts
            if user == self.own_user:
                continue
            try:
                pc, pr = float(pcpu), int(psr)
            except ValueError:
                continue
            if pc <= 1.0:
                continue
            total += pc
            if self.mask_cpus is not None and pr in self.mask_cpus:
                in_mask += 1
        self.foreign_pct.append(total)
        self.foreign_in_mask.append(in_mask)

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

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["ps", "-o", "rss=", "--ppid", str(self.root_pid), "--pid", str(self.root_pid)],
                    capture_output=True, text=True, timeout=10).stdout
                total = sum(int(x) for x in out.split() if x.isdigit())
                if total:
                    self.tree_rss_kib.append(total)
            except Exception:
                pass
            self._halt.wait(self.period)

    def summary(self) -> Dict[str, Any]:
        if not self.tree_rss_kib:
            return {"n": 0, "note": "no RSS sample landed; run may be shorter than the period"}
        return {
            "n": len(self.tree_rss_kib),
            "period_s": self.period,
            "peak_simultaneous_tree_rss_kib": max(self.tree_rss_kib),
            "mean_simultaneous_tree_rss_kib": int(statistics.fmean(self.tree_rss_kib)),
            "note": "maximum of simultaneously observed process-tree totals, not a sum of "
                    "independently observed per-process maxima",
        }


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


def settle(load_max: float, timeout_s: int, log: List[str]) -> Dict[str, Any]:
    """Wait for the previous mutex holder's decay tail. Runs after acquisition, by contract."""
    t0 = time.time()
    waited, load1, comps = 0.0, None, None
    while True:
        load1 = float(open("/proc/loadavg").read().split()[0])
        comps = 0
        for name in COMPILER_NAMES:
            r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
            comps += len([x for x in r.stdout.split() if x.strip()])
        waited = time.time() - t0
        if load1 < load_max and comps == 0:
            break
        if waited >= timeout_s:
            log.append(f"SETTLE_TIMEOUT after {waited:.0f}s load1={load1} compilers={comps}")
            break
        time.sleep(3.0)
    return {"waited_s": round(waited, 1), "load1_at_start": load1,
            "compilers_running": comps, "load_max_threshold": load_max,
            "timed_out": waited >= timeout_s}


# ----------------------------------------------------------------------------- one run


TIMING_LINE = re.compile(r"^\s*([A-Za-z0-9_()\- ]+?)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*(?:sec|s)?\b")


def parse_stage_timers(text: str) -> Dict[str, float]:
    """Parse TIMING stage lines.

    The character class includes a literal '-' placed last. A previous parser wrote
    `[A-Za-z0-9_ -()]`, in which ' -(' is the range 0x20-0x28, so '-' was not a member and
    every hyphenated tag ('dw - iFFT', 'prep patch - FFT') was silently dropped from the
    record rather than merely from the summary.
    """
    out: Dict[str, float] = {}
    for line in text.splitlines():
        m = TIMING_LINE.match(line)
        if m:
            tag, val = m.group(1).strip(), float(m.group(2))
            out[tag] = out.get(tag, 0.0) + val
    return out


def time_v_fields(text: str) -> Dict[str, Any]:
    want = {
        "User time (seconds)": "user_s",
        "System time (seconds)": "sys_s",
        "Elapsed (wall clock) time (h:mm:ss or m:ss)": "wall_str",
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
        k, _, v = line.strip().partition(":")
        key = want.get(k.strip())
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

    # Settle policy. The full gate exists to avoid the *previous mutex holder's* load decay
    # tail, so it is worth its cost once, before the first run. Applying it between every run
    # of one series would instead wait out this series' own tail: after a 16-thread arm,
    # load1 needs minutes to fall below the threshold, so the gate would time out on every
    # run and triple the series length while measuring nothing. Between runs a fixed quiet
    # interval is used instead. It is identical for every arm, so it cannot favour one side
    # of a pair, and each record states which regime applied.
    if cfg.get("settle_full_gate", True) and not cfg.get("_first_run_done"):
        settle_info = settle(cfg.get("settle_load_max", 2.0),
                             cfg.get("settle_timeout_s", 300), log)
        settle_info["regime"] = "full_gate_first_run_of_series"
        cfg["_first_run_done"] = True
    else:
        quiet = float(cfg.get("inter_run_quiet_s", 5.0))
        time.sleep(quiet)
        settle_info = {"regime": "fixed_inter_run_quiet", "waited_s": quiet,
                       "load1_at_start": float(open("/proc/loadavg").read().split()[0])}

    cpu_mask = arm["cpu_mask"]
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
                   ps_period=cfg.get("foreign_sample_period_s", 1.0))
    samp.start()

    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=arm["cwd"], env=env,
                            stdout=(rundir / "stdout.log").open("w"),
                            stderr=(rundir / "time_stderr.log").open("w"))
    rss = RssSampler(proc.pid, period=cfg.get("rss_period_s", 0.25))
    rss.start()

    # Placement is read from the live process, not assumed from the requested mask.
    placement: Dict[str, Any] = {"requested_cpu_mask": cpu_mask}
    for _ in range(40):
        try:
            st = Path(f"/proc/{proc.pid}/status").read_text()
            placement["inherited_Cpus_allowed_list"] = re.search(
                r"Cpus_allowed_list:\s*(\S+)", st).group(1)
            placement["inherited_Mems_allowed_list"] = re.search(
                r"Mems_allowed_list:\s*(\S+)", st).group(1)
            nm = Path(f"/proc/{proc.pid}/numa_maps")
            if nm.exists():
                placement["numa_maps_head"] = "\n".join(nm.read_text().splitlines()[:6])
            placement["numa_policy"] = sh(f"numastat -p {proc.pid} 2>/dev/null | tail -4")
            break
        except Exception:
            time.sleep(0.25)

    rc = proc.wait(timeout=cfg.get("run_timeout_s", 7200))
    wall = time.time() - t0
    samp.stop(); rss.stop()
    samp.join(timeout=5); rss.join(timeout=5)

    time_txt = (rundir / "time_stderr.log").read_text(errors="replace")
    stdout_txt = (rundir / "stdout.log").read_text(errors="replace")

    stage = {}
    for lg in sorted((rundir / "out").rglob("*.log")):
        stage[lg.name] = parse_stage_timers(lg.read_text(errors="replace"))

    products = []
    for f in sorted((rundir / "out").rglob("*")):
        if f.is_file():
            entry = {"path": str(f.relative_to(rundir / "out")),
                     "bytes": f.stat().st_size,
                     "sha256": sha256_file(f)}
            if f.suffix == ".mrc":
                entry["mrc"] = mrc_split_digests(f)
            products.append(entry)

    cuda_witness = [ln for ln in stdout_txt.splitlines()
                    if "GPU" in ln or "CUDA" in ln or "device" in ln.lower()][:8]

    return {
        "tag": tag,
        "arm_id": arm["id"],
        "pair_index": pair_index,
        "order_in_pair": order_in_pair,
        "rep": rep,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "command": cmd,
        "cwd": arm["cwd"],
        "env_overrides": arm.get("env") or {},
        "exit_code": rc,
        "wall_s": round(wall, 3),
        "requested": {"j": arm["j"], "max_io_threads": arm.get("max_io_threads"),
                      "gpu_ordinal": gpu_index},
        "device_identity": device_identity,
        "effective": {"j": arm["j"],
                      "io_threads": min(arm["j"], arm["max_io_threads"])
                      if arm.get("max_io_threads") else arm["j"]},
        "settle": settle_info,
        "cache_regime": {
            "declared": arm.get("cache_regime", "warm-unless-first"),
            "host_cached_kib": int(sh("awk '/^Cached:/{print $2}' /proc/meminfo") or 0),
            "note": "global cache drops are forbidden on this shared host, so the page-cache "
                    "regime is recorded, not controlled; 'File system inputs: 0' in rusage "
                    "means the read was served from cache, not that decode was free",
        },
        "placement": placement,
        "resource_usage": time_v_fields(time_txt),
        "memory": rss.summary(),
        "sampling": samp.summary(),
        "stage_timers": stage,
        "stage_timers_note": "stage intervals nest and overlap; they are not summed into a total, "
                             "and no TIFF cost is derived as wall minus GPU kernel timers",
        "cuda_witness_lines": cuda_witness,
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
    args.out.mkdir(parents=True, exist_ok=True)

    series = {
        "plan_name": plan.get("name", "unnamed"),
        "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
        "source_commit": plan.get("source_commit"),
        "host": host_witness(),
        "config": cfg,
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

    print("SERIES_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
