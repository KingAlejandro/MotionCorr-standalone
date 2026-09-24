#!/usr/bin/env python3
"""Repeatable MotionCorr movie profiler with explicit timing and memory provenance.

Example (arguments after -- are passed verbatim to MotionCorr):
  python3 tools/profile_cuda_movie.py --binary build-cuda/motioncorr \
    --input movie.tiff --gpu 0 --repeat 5 --output-dir profile-out \
    --expect-output corrected.mrc --expect-output shifts.star -- \
    --i movie.tiff --o corrected --gpu 0 -DTIMING

The runner never uses a shell. Device-wide nvidia-smi samples are supplementary
and are labelled as such; use --nsys for a separate CUDA allocation/transfer
trace. Sampled and Nsight timings are stored separately from each other.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any


STAGE_RE = re.compile(r"^\s*(?P<name>[^\n:]{1,120}):\s*(?P<seconds>[0-9]+(?:\.[0-9]+)?)\s+sec\s*(?:\((?P<detail>[^\n]*)\))?", re.M)
MIB_RE = re.compile(r"^\s*(?P<value>[0-9]+)\s*MiB\s*$")


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run_capture(argv: list[str], timeout: float = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def git_source_sha() -> str | None:
    code, out = run_capture(["git", "rev-parse", "HEAD"])
    return out if code == 0 else None


def parse_stages(text: str) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    for m in STAGE_RE.finditer(text):
        name = m.group("name").strip()
        item: dict[str, Any] = {"seconds": float(m.group("seconds"))}
        if m.group("detail"):
            item["timer_detail"] = m.group("detail").strip()
        if name in stages:
            # Preserve multiple invocations (for example per-movie/per-loop).
            old = stages[name]
            if not isinstance(old, list):
                old = [old]
            old.append(item)
            stages[name] = old
        else:
            stages[name] = item
    return stages


def rss_bytes(pid: int) -> int | None:
    """Read resident pages from Linux procfs; this profiler targets CUDA/Linux."""
    try:
        for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def nvidia_info(gpu: str) -> dict[str, Any]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        raise RuntimeError("nvidia-smi not found; this tool requires an NVIDIA GPU host")
    query = [smi, f"--id={gpu}",
             "--query-gpu=name,uuid,driver_version,memory.total,memory.used",
             "--format=csv,noheader,nounits"]
    code, out = run_capture(query)
    if code != 0 or not out:
        raise RuntimeError(f"GPU query failed for GPU {gpu}: {out}")
    fields = [x.strip() for x in out.splitlines()[0].split(",")]
    if len(fields) < 5:
        raise RuntimeError(f"Unexpected nvidia-smi response: {out}")
    return {"name": fields[0], "uuid": fields[1], "driver_version": fields[2],
            "memory_total_mib": int(fields[3]), "idle_memory_used_mib": int(fields[4])}


class Sampler:
    """50 ms device-wide VRAM and child RSS samples; no CUDA allocation claims."""
    def __init__(self, gpu: str, idle_mib: int, interval_s: float = 0.05):
        self.gpu, self.idle_mib, self.interval_s = gpu, idle_mib, interval_s
        self.samples: list[dict[str, Any]] = []
        self.peak_rss: int | None = None
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.pid: int | None = None
        self.smi = shutil.which("nvidia-smi")

    def start(self, pid: int) -> None:
        self.pid = pid
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()

    def _sample(self) -> None:
        while not self.stop.is_set():
            now = time.time()
            if self.pid:
                rss = rss_bytes(self.pid)
                if rss is not None:
                    self.peak_rss = max(self.peak_rss or 0, rss)
            code, out = run_capture([self.smi, f"--id={self.gpu}",
                                     "--query-gpu=memory.used", "--format=csv,noheader,nounits"], timeout=2) if self.smi else (127, "")
            used = None
            if code == 0:
                try:
                    used = int(out.splitlines()[0].strip())
                except (ValueError, IndexError):
                    pass
            self.samples.append({"unix_time": now, "device_total_used_mib": used,
                                 "device_delta_from_idle_mib": (max(0, used-self.idle_mib) if used is not None else None),
                                 "process_rss_bytes": rss_bytes(self.pid) if self.pid else None})
            self.stop.wait(max(0, self.interval_s - (time.time() - now)))

    def finish(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)


def sha_inputs(paths: list[pathlib.Path]) -> list[dict[str, str]]:
    out = []
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f"Input is missing or not a file: {path}")
        out.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    return out


def check_outputs(paths: list[pathlib.Path], started_ns: int,
                  before: dict[str, tuple[int, int, str] | None]) -> list[dict[str, Any]]:
    if not paths:
        raise RuntimeError("At least one --expect-output is required for fail-closed output validation")
    result = []
    for path in paths:
        try:
            st = path.stat()
        except OSError as e:
            raise RuntimeError(f"Expected output missing: {path}: {e}") from e
        if not path.is_file() or st.st_size <= 0:
            raise RuntimeError(f"Expected output is not a non-empty file: {path}")
        old = before[str(path.resolve())]
        digest = sha256_file(path)
        signature = (st.st_mtime_ns, st.st_size, digest)
        if old is not None and signature == old:
            raise RuntimeError(f"Expected output was not refreshed by this run: {path}")
        if st.st_mtime_ns < started_ns - 1_000_000_000:
            raise RuntimeError(f"Expected output appears stale (mtime predates run): {path}")
        result.append({"path": str(path.resolve()), "size_bytes": st.st_size,
                       "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                       "sha256": digest})
    return result


def execute(label: str, argv: list[str], outdir: pathlib.Path, expected: list[pathlib.Path],
            gpu: str, idle_mib: int, timeout: float = 0, profiled: bool = False) -> dict[str, Any]:
    stdout_path, stderr_path = outdir / f"{label}.stdout.log", outdir / f"{label}.stderr.log"
    started_ns = time.time_ns()
    before: dict[str, tuple[int, int, str] | None] = {}
    for path in expected:
        try:
            st = path.stat()
            before[str(path.resolve())] = (st.st_mtime_ns, st.st_size, sha256_file(path)) if path.is_file() else None
        except OSError:
            before[str(path.resolve())] = None
    sampler = Sampler(gpu, idle_mib)
    start = time.perf_counter()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            proc = subprocess.Popen(argv, stdout=stdout, stderr=stderr, shell=False)
        except OSError as e:
            raise RuntimeError(f"Could not start process: {e}") from e
        sampler.start(proc.pid)
        try:
            returncode = proc.wait(timeout=timeout if timeout > 0 else None)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            sampler.finish()
            raise RuntimeError(f"{label} exceeded timeout of {timeout:g} seconds")
    elapsed = time.perf_counter() - start
    sampler.finish()
    out_text = stdout_path.read_text(errors="replace")
    err_text = stderr_path.read_text(errors="replace")
    if returncode != 0:
        raise RuntimeError(f"{label} exited {returncode}; see {stdout_path} and {stderr_path}")
    outputs = check_outputs(expected, started_ns, before)
    vrams = [x["device_total_used_mib"] for x in sampler.samples if x["device_total_used_mib"] is not None]
    return {"label": label, "profiled_with_nsys": profiled,
            "timing_class": "nsys_profiled" if profiled else "sampled_unprofiled",
            "argv": argv, "returncode": returncode, "wall_seconds": elapsed,
            "peak_sampled_process_rss_bytes": sampler.peak_rss,
            "rss_sampling_interval_ms": 50,
            "gpu_vram_sampling": {"scope": "whole_device; idle-subtracted value is a rough delta, not process attribution",
                                  "sample_interval_ms": 50, "sample_count": len(sampler.samples),
                                  "idle_device_used_mib": idle_mib,
                                  "peak_device_total_used_mib": max(vrams) if vrams else None,
                                  "peak_device_delta_from_idle_mib": max((max(0, x-idle_mib) for x in vrams), default=None),
                                  "samples": sampler.samples},
            "timing_stages_seconds": parse_stages(out_text + "\n" + err_text),
            "outputs": outputs, "stdout_log": str(stdout_path), "stderr_log": str(stderr_path)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--binary", required=True, type=pathlib.Path)
    p.add_argument("--input", required=True, type=pathlib.Path, action="append",
                   help="input file to hash; repeat for gain/defect/metadata inputs")
    p.add_argument("--expect-output", required=True, type=pathlib.Path, action="append",
                   help="non-empty output file that must be produced; repeat as needed")
    p.add_argument("--gpu", required=True, help="nvidia-smi GPU index or UUID")
    p.add_argument("--repeat", type=int, default=3, help="unprofiled measured runs (default: 3)")
    p.add_argument("--output-dir", required=True, type=pathlib.Path)
    p.add_argument("--nsys", help="optional path/name of Nsight Systems executable; adds one separate profiled run")
    p.add_argument("--build-info", default="unspecified",
                   help="build flags/configuration label to retain with measurements")
    p.add_argument("--timeout", type=float, default=0, help="per-run timeout in seconds; 0 means no timeout")
    p.add_argument("args", nargs=argparse.REMAINDER, help="MotionCorr argv after --")
    a = p.parse_args()
    if a.repeat < 1:
        p.error("--repeat must be at least 1")
    forwarded = a.args[1:] if a.args[:1] == ["--"] else a.args
    if not forwarded:
        p.error("supply MotionCorr options after --")
    binary = a.binary.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        p.error(f"--binary must name an executable file: {binary}")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    gpu = nvidia_info(a.gpu)
    source_sha = git_source_sha()
    input_hashes = sha_inputs(a.input)
    binary_hash = sha256_file(binary)
    artifact = {"schema_version": 1, "started_utc": datetime.now(timezone.utc).isoformat(),
                "source_git_sha": source_sha, "binary": {"path": str(binary), "sha256": binary_hash},
                "inputs": input_hashes, "gpu": gpu,
                "host": {"hostname": os.uname().nodename, "platform": sys.platform,
                         "python": sys.version.split()[0],
                         "load_average": (list(os.getloadavg()) if hasattr(os, "getloadavg") else None)},
                "build_info": a.build_info,
                "base_command": [str(binary), *forwarded], "runs": [],
                "memory_measurement_notes": [
                    "50 ms nvidia-smi samples report whole-device VRAM; other GPU clients can affect them.",
                    "Idle-subtracted VRAM is an estimate and is not an allocation-event high-water.",
                    "Use the separate Nsight run to inspect CUDA allocation and transfer events.",
                    "Sampled-unprofiled wall times include profiler sampling overhead and are not raw bare-process times."]}
    try:
        for i in range(1, a.repeat + 1):
            artifact["runs"].append(execute(f"run-{i:02d}", [str(binary), *forwarded], a.output_dir,
                                           a.expect_output, a.gpu, gpu["idle_memory_used_mib"], a.timeout))
        if a.nsys:
            nsys = shutil.which(a.nsys) or (str(pathlib.Path(a.nsys).resolve()) if pathlib.Path(a.nsys).is_file() else None)
            if not nsys:
                raise RuntimeError(f"Nsight Systems executable not found: {a.nsys}")
            profile_prefix = str((a.output_dir / "nsys-cuda").resolve())
            nsys_argv = [nsys, "profile", "--trace=cuda,osrt", "--cuda-memory-usage=true",
                         "--force-overwrite=true", f"--output={profile_prefix}", str(binary), *forwarded]
            profiled = execute("nsys-run", nsys_argv, a.output_dir, a.expect_output,
                               a.gpu, gpu["idle_memory_used_mib"], a.timeout, profiled=True)
            profiled["nsys_report_prefix"] = profile_prefix
            reports = [pathlib.Path(profile_prefix + suffix) for suffix in (".nsys-rep", ".qdrep")]
            report = next((x for x in reports if x.is_file() and x.stat().st_size > 0), None)
            if report is None:
                raise RuntimeError(f"Nsight run exited successfully but produced no report at {profile_prefix}.*")
            profiled["nsys_report"] = {"path": str(report), "size_bytes": report.stat().st_size,
                                       "sha256": sha256_file(report)}
            artifact["runs"].append(profiled)
    except Exception as e:
        artifact["status"] = "FAILED"
        artifact["failure"] = str(e)
        artifact["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (a.output_dir / "profile.json").write_text(json.dumps(artifact, indent=2) + "\n")
        print(f"profile failed: {e}", file=sys.stderr)
        return 1
    artifact["status"] = "OK"
    artifact["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (a.output_dir / "profile.json").write_text(json.dumps(artifact, indent=2) + "\n")
    print(a.output_dir / "profile.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
