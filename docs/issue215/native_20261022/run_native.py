#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded #215 correctness run; invoke under taskset -c 8-9 in NEW scratch."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
UUID = "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598"
PYTHON = "/home/alex/.mc-venv/bin/python3"
CUDA = "/usr/local/cuda-12.8"
NVCOMP = "/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive"
HEAD = os.environ.get("MC_SOURCE_HEAD", "fc1c8e6f18fe1f33d4a7cc68da2fbc467bd01c16")
ENV = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
           MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES=UUID,
           PATH=CUDA + "/bin:" + os.environ["PATH"],
           LD_LIBRARY_PATH=CUDA + "/lib64:" + NVCOMP + "/lib")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + "\n")


def command(name, argv, timeout=1800, required=True):
    start = utc()
    with (ROOT / (name + ".log")).open("w") as log:
        p = subprocess.run(argv, env=ENV, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    receipt = dict(start=start, end=utc(), argv=argv, exit=p.returncode,
                   cpu_affinity=sorted(os.sched_getaffinity(0)))
    save(name + ".json", receipt)
    print(name, p.returncode, flush=True)
    if required and p.returncode:
        raise RuntimeError(name + " failed")
    return p.returncode


def lock(path, wait=0):
    handle = open(path, "a")
    deadline = time.monotonic() + wait
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise RuntimeError("lock busy: " + path)
            time.sleep(2)
    with (ROOT / "locks.jsonl").open("a") as out:
        out.write(json.dumps(dict(utc=utc(), path=path, action="acquired", pid=os.getpid())) + "\n")
    return handle


def unlock(handle):
    with (ROOT / "locks.jsonl").open("a") as out:
        out.write(json.dumps(dict(utc=utc(), path=handle.name, action="released", pid=os.getpid())) + "\n")
    fcntl.flock(handle, fcntl.LOCK_UN)
    handle.close()


def parse_health(path):
    gpu = ET.parse(path).getroot().find("gpu")
    assert gpu.findtext("uuid") == UUID
    fields = ("sram_uncorrectable_parity", "sram_uncorrectable_secded", "dram_uncorrectable")
    ecc = {name: gpu.findtext("ecc_errors/volatile/" + name) for name in fields}
    assert all(value == "0" for value in ecc.values()), ("uncorrected ECC", ecc)
    pending = gpu.findtext("retired_pages/pending_blacklist")
    recovery = gpu.findtext("gpu_recovery_action")
    remap = {name: gpu.findtext("remapped_rows/" + name)
             for name in ("remapped_row_pending", "remapped_row_failure")}
    assert pending in ("No", "N/A"), ("pending retirement", pending)
    assert recovery == "None", ("recovery needed", recovery)
    assert all(value == "No" for value in remap.values()), ("row remap", remap)
    return dict(uuid=UUID, volatile_uncorrected_ecc=ecc, pending_retirement=pending,
                recovery_action=recovery, remapped_rows=remap)


def health(phase, require_idle=False):
    command(phase + "-gpus", ["nvidia-smi", "--query-gpu=index,uuid,name,memory.used,utilization.gpu", "--format=csv,noheader"])
    command(phase + "-apps", ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory", "--format=csv,noheader"])
    command(phase + "-xml", ["nvidia-smi", "-i", UUID, "-q", "-x"])
    rows = [r.split(", ") for r in (ROOT / (phase + "-gpus.log")).read_text().splitlines()]
    row = next(r for r in rows if r[1] == UUID)
    assert row[0] == "2", row
    assert UUID not in (ROOT / (phase + "-apps.log")).read_text(), "assigned GPU has compute apps"
    if require_idle:
        assert int(row[3].split()[0]) <= 16 and int(row[4].split()[0]) == 0, row
    parsed = parse_health(ROOT / (phase + "-xml.log"))
    save(phase + "-health.json", dict(status="PASS", utc=utc(), index=2,
                                     require_idle=require_idle, **parsed))


def main():
    fd = os.open(ROOT / "started.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w") as out:
        json.dump(dict(utc=utc(), pid=os.getpid(), host=socket.gethostname(), source_head=HEAD,
                  cpu_affinity=sorted(os.sched_getaffinity(0)),
                  env={k: ENV[k] for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                       "NUMEXPR_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "PATH", "LD_LIBRARY_PATH")}), out, indent=2)
    assert sorted(os.sched_getaffinity(0)) == [8, 9]
    os.umask(0o022)
    command("software", ["bash", "-c", "set -eu; hostname; uname -a; cmake --version; c++ --version; nvcc --version; "
            + PYTHON + " -c 'import sys,numpy,os; print(sys.executable,numpy.__version__,sorted(os.sched_getaffinity(0)))'; "
            + "grep -E 'NVCOMP_(MAJOR|MINOR|PATCH|VERSION)' " + NVCOMP + "/include/nvcomp/version.h; "
            + "sha256sum " + NVCOMP + "/lib/libnvcomp.so.5.3.0.16 " + NVCOMP + "/include/nvcomp/deflate.h; df -h /mnt/clathrin"])
    source_files = {str(p.relative_to(ROOT / "src")): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((ROOT / "src").rglob("*")) if p.is_file()}
    save("source-files.json", dict(source_head=HEAD, files=source_files))
    buildlock = lock("/tmp/motioncorr-build.lock", wait=1800)
    try:
        command("configure", ["cmake", "-S", str(ROOT / "src"), "-B", str(ROOT / "build"),
                "-DCMAKE_BUILD_TYPE=Release", "-DCUDA=ON", "-DUSE_NVCOMP=ON", "-DNVCOMP_ROOT=" + NVCOMP,
                "-DCMAKE_CUDA_COMPILER=" + CUDA + "/bin/nvcc", "-DCMAKE_CUDA_ARCHITECTURES=80",
                "-DBUILD_TESTING=ON", "-DPython3_EXECUTABLE=" + PYTHON], timeout=600)
        command("build", ["cmake", "--build", str(ROOT / "build"), "--parallel", "2", "--target",
                "motioncorr_tiff_identity_later", "motioncorr_tiff_identity_first_chunk", "tiff_identity_host_control"], timeout=1800)
    finally:
        unlock(buildlock)
    binaries = [ROOT / "build" / n for n in ("motioncorr_tiff_identity_later", "motioncorr_tiff_identity_first_chunk", "tiff_identity_host_control")]
    save("binaries.json", {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries})
    command("libraries", ["ldd", str(binaries[0])])
    command("host-controls", ["ctest", "--test-dir", str(ROOT / "build"), "-R",
            "TiffIdentityLaterChunkHostControls|NvcompAcceptanceDiagnostics|NvcompGuards|OutputTreeComparator", "--output-on-failure", "-j1"], timeout=180)
    gpulock = lock("/tmp/motioncorr-gpu2-correctness.lock")
    try:
        probe = lock("/tmp/motioncorr-bench.lock")
        unlock(probe)
        health("pre", require_idle=True)
        try:
            rc = command("later-controls", [PYTHON, str(ROOT / "src/tests/run_tiff_identity_later_chunk_controls.py"),
                    "--binary", str(binaries[0]), "--mutant-binary", str(binaries[1]),
                    "--workdir", str(ROOT / "later-controls"), "--cpus", "8-9"], timeout=1500, required=False)
        finally:
            health("post")
        if rc:
            raise RuntimeError("later-controls failed")
    finally:
        unlock(gpulock)


if __name__ == "__main__":
    status = "FAIL"
    try:
        main()
        status = "PASS"
    finally:
        save("exit.json", dict(utc=utc(), status=status, pid=os.getpid()))
