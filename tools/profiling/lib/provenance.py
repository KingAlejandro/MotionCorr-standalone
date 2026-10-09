"""Provenance, host state and shared-host locks (docs/profiling.md, "Trust rules").

Every output of the kit carries a provenance record built here: binary
SHA-256, source commit (with how it was determined), the command, the host
and GPU environment, and the instrument that produced the numbers.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

KIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPILERS = ("cc1plus", "cc1", "nvcc", "cicc", "ptxas")
DEFAULT_BENCH_LOCK = "/tmp/motioncorr-bench.lock"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run_text(argv: Sequence[str], timeout: float = 20, cwd: Optional[str] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                           timeout=timeout, cwd=cwd, check=False)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def git_info(path: str, untracked: bool = False) -> Optional[Dict]:
    rc, top = run_text(["git", "-C", path, "rev-parse", "--show-toplevel"])
    if rc != 0:
        return None
    _, commit = run_text(["git", "-C", path, "rev-parse", "HEAD"])
    _, status = run_text(["git", "-C", path, "status", "--porcelain",
                          "--untracked-files=" + ("normal" if untracked else "no"), "--", path])
    return {"toplevel": top, "commit": commit, "dirty": bool(status)}


def _cmake_source_dir(binary: str) -> Optional[str]:
    d = os.path.dirname(os.path.abspath(binary))
    for _ in range(3):
        cache = os.path.join(d, "CMakeCache.txt")
        if os.path.isfile(cache):
            with open(cache, errors="replace") as f:
                for line in f:
                    if line.startswith("CMAKE_HOME_DIRECTORY:"):
                        return line.split("=", 1)[1].strip()
        d = os.path.dirname(d)
    return None


def source_for_binary(binary: str, source: Optional[str] = None, commit: Optional[str] = None) -> Dict:
    """Source revision of a build. Explicit values win; otherwise the source
    directory recorded in the build's CMakeCache.txt (which is what was really
    compiled, even for a copied build tree), then git or a SOURCE_COMMIT file."""
    rec: Dict = {"source_dir": source, "commit": commit, "dirty": None, "origin": None}
    if commit:
        rec["origin"] = "given on command line"
        return rec
    src = source or _cmake_source_dir(binary)
    rec["source_dir"] = src
    if not src:
        rec["origin"] = "unknown: no --source and no CMakeCache.txt near the binary"
        return rec
    g = git_info(src)
    if g:
        rec.update(commit=g["commit"], dirty=g["dirty"], origin="git in %s" % g["toplevel"])
        return rec
    pin = os.path.join(src, "SOURCE_COMMIT")
    if os.path.isfile(pin):
        with open(pin) as f:
            rec.update(commit=f.read().strip(), origin="SOURCE_COMMIT file (not verified against the tree)")
        return rec
    rec["origin"] = "unknown: %s is not a git checkout and has no SOURCE_COMMIT" % src
    return rec


def binary_record(binary: str, source: Optional[str] = None, commit: Optional[str] = None) -> Dict:
    path = os.path.abspath(binary)
    rec = {"path": path, "realpath": os.path.realpath(path), "sha256": sha256_file(path),
           "size": os.path.getsize(path), "source": source_for_binary(path, source, commit),
           "has_profile_option": has_profile_option(path),
           }
    rec["has_device_timing_option"], rec["device_timing_detection"] = device_timing_detection(path)
    libs = linked_libraries(path)
    if libs:
        rec["linked"] = libs
    return rec


def has_profile_option(binary: str) -> bool:
    """True when the binary carries the --profile option string (#154).
    For a script payload (tests) the option name must appear in its text."""
    with open(binary, "rb") as f:
        data = f.read()
    if data.startswith(b"#!"):
        return b"--profile" in data
    return b"--profile\x00" in data


def has_device_timing_option(binary: str) -> bool:
    """True when the binary accepts --profile_device_timing (profile without
    CUDA event waits). See device_timing_detection for how it is decided."""
    return device_timing_detection(binary)[0]


def device_timing_detection(binary: str) -> Tuple[bool, str]:
    """(supported, method). The binary's own --help is asked first.

    MotionCorr prints its option list only once the implementation is chosen
    (plain --help stops at "choose either UCSF MotionCor2 or RELION's own"),
    so the probe is `--use_own --help`. A probe that runs and lists --profile
    is authoritative either way. If it cannot run or lists nothing the kit
    recognises, the decision falls back to scanning the binary for the option
    string, the rule has_profile_option uses."""
    rc, out = run_text([binary, "--use_own", "--help"], timeout=30)
    if rc == 0 and re.search(r"--profile\s+\(", out):
        return re.search(r"--profile_device_timing\s+\(", out) is not None, "--use_own --help"
    with open(binary, "rb") as f:
        data = f.read()
    if data.startswith(b"#!"):
        return b"--profile_device_timing" in data, "binary scan (help probe rc %d)" % rc
    return b"--profile_device_timing\x00" in data, "binary scan (help probe rc %d)" % rc


def linked_libraries(binary: str) -> Dict[str, str]:
    """Resolved paths of the CUDA, cuFFT and nvCOMP libraries (Linux, ldd)."""
    if not shutil.which("ldd"):
        return {}
    rc, out = run_text(["ldd", binary])
    if rc != 0:
        return {}
    libs = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s+=>\s+(\S+)", line)
        if m and re.match(r"lib(cudart|cufft|nvcomp|cuda|tiff|fftw3)", m.group(1)):
            libs[m.group(1)] = m.group(2)
    return libs


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def gpu_record(uuid: Optional[str]) -> Optional[Dict]:
    if not uuid:
        return None
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"uuid": uuid, "error": "nvidia-smi not found"}
    q = "index,uuid,name,driver_version,memory.total,memory.used,persistence_mode,clocks.max.sm,pci.bus_id"
    rc, out = run_text([smi, "--id=%s" % uuid, "--query-gpu=" + q, "--format=csv,noheader,nounits"])
    if rc != 0 or not out:
        return {"uuid": uuid, "error": out}
    vals = [v.strip() for v in out.splitlines()[0].split(",")]
    rec = dict(zip(q.split(","), vals))
    _, head = run_text([smi])
    m = re.search(r"CUDA Version:\s*([0-9.]+)", head)
    rec["driver_cuda_version"] = m.group(1) if m else None
    return rec


def cpu_list(spec: Optional[str]) -> List[int]:
    if not spec:
        return []
    out: List[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a), int(b or a) + 1))
    return sorted(set(out))


def host_record(cpus: Sequence[int]) -> Dict:
    rec: Dict = {"hostname": socket.gethostname(), "platform": platform.platform(),
                 "python": sys.version.split()[0], "cpu_count": os.cpu_count(),
                 "load1_5_15": list(os.getloadavg()), "lane_cpus": list(cpus),
                 "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    model = None
    info = _read("/proc/cpuinfo")
    if info:
        m = re.search(r"model name\s*:\s*(.*)", info)
        model = m.group(1) if m else None
    rec["cpu_model"] = model or platform.processor()
    rec["clocksource"] = _read("/sys/devices/system/clocksource/clocksource0/current_clocksource")
    rec["thp_enabled"] = _read("/sys/kernel/mm/transparent_hugepage/enabled")
    rec["thp_defrag"] = _read("/sys/kernel/mm/transparent_hugepage/defrag")
    rec["perf_event_paranoid"] = _read("/proc/sys/kernel/perf_event_paranoid")
    nvcc = shutil.which("nvcc") or ("/usr/local/cuda/bin/nvcc" if os.path.exists("/usr/local/cuda/bin/nvcc") else None)
    if nvcc:
        _, out = run_text([nvcc, "--version"])
        m = re.search(r"release ([0-9.]+)", out)
        rec["nvcc_release"] = m.group(1) if m else None
    rec["env"] = {k: v for k, v in sorted(os.environ.items())
                  if k.startswith(("OMP_", "CUDA_", "MC_", "GOMP_", "MALLOC_", "SLURM_"))}
    return rec


def kit_record() -> Dict:
    g = git_info(KIT_DIR, untracked=True)
    return {"path": KIT_DIR, "commit": g["commit"] if g else None, "dirty": g["dirty"] if g else None}


def provenance(instrument: str, command: Sequence[str], binaries: Dict[str, Dict], cpus: Sequence[int],
               gpu_uuid: Optional[str], extra: Optional[Dict] = None) -> Dict:
    rec = {"instrument": instrument, "command": list(command), "kit": kit_record(),
           "binaries": binaries, "host": host_record(cpus), "gpu": gpu_record(gpu_uuid)}
    if extra:
        rec.update(extra)
    return rec


# ----------------------------------------------------------------- host state

def compilers_running() -> List[str]:
    """Compiler processes on the box, by exact process name."""
    found = []
    if not os.path.isdir("/proc"):
        return found
    for p in os.listdir("/proc"):
        if p.isdigit():
            comm = _read("/proc/%s/comm" % p)
            if comm in COMPILERS:
                found.append("%s:%s" % (p, comm))
    return found


def lane_jiffies(cpus: Sequence[int]) -> Optional[Dict[str, int]]:
    """Summed /proc/stat counters for the lane CPUs: busy (all non-idle,
    non-iowait time including steal) and steal separately."""
    text = _read("/proc/stat")
    if text is None or not cpus:
        return None
    want = {"cpu%d" % c for c in cpus}
    busy = steal = 0
    seen = 0
    for line in text.splitlines():
        f = line.split()
        if f and f[0] in want:
            v = [int(x) for x in f[1:]]
            # user nice system idle iowait irq softirq steal guest guest_nice
            busy += v[0] + v[1] + v[2] + v[5] + v[6] + (v[7] if len(v) > 7 else 0)
            steal += v[7] if len(v) > 7 else 0
            seen += 1
    if seen != len(want):
        return None
    return {"busy": busy, "steal": steal}


def clock_ticks() -> int:
    return os.sysconf("SC_CLK_TCK")


# ----------------------------------------------------------------- locks

class LockError(Exception):
    pass


class HostLock:
    """flock on a shared lock file, held in this process only.

    The descriptor is close-on-exec, so payloads and samplers never inherit
    it and cannot keep the lock after the kit exits. The file is never
    deleted. After acquiring, the inode behind the path must be the one we
    locked: a lock file unlinked by someone else splits the mutex in two.
    """

    def __init__(self, path: str, timeout_s: float = 3600.0, poll_s: float = 2.0):
        self.path, self.timeout_s, self.poll_s = path, timeout_s, poll_s
        self.fd: Optional[int] = None
        self.waited_s = 0.0

    def __enter__(self) -> "HostLock":
        t0 = time.monotonic()
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o664)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    os.close(fd)
                    raise
                if time.monotonic() - t0 > self.timeout_s:
                    os.close(fd)
                    raise LockError("timed out after %.0f s waiting for %s" % (self.timeout_s, self.path))
                time.sleep(self.poll_s)
        try:
            same = os.stat(self.path).st_ino == os.fstat(fd).st_ino
        except FileNotFoundError:
            same = False
        if not same:
            os.close(fd)
            raise LockError("%s was unlinked or replaced while held; the mutex is split. "
                            "Wait until no process holds the deleted inode." % self.path)
        self.fd = fd
        self.waited_s = time.monotonic() - t0
        return self

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def record(self) -> Dict:
        return {"path": self.path, "waited_s": round(self.waited_s, 3)}


def write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=False, default=str)
        f.write("\n")
    os.replace(tmp, path)
