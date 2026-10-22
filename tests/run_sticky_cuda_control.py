#!/usr/bin/env python3
"""Opt-in genuine CUDA context poisoning (#213); never run on an occupied GPU.

Configure MC_ENABLE_STICKY_CUDA_TEST=ON, set CUDA_VISIBLE_DEVICES to one full GPU
UUID, and run under taskset with at most eight CPUs. This driver takes the
canonical gpuN-correctness flock itself (do not take that lock around CTest).
Each arm is a fresh process; no cudaDeviceReset is used. Logs are retained on
failure, including the mandatory post-run nvidia-smi health check.
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from run_resident_retry_controls import require, synthetic_frames, write_star, write_tiff


def command(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=20, **kwargs).stdout


def gpu_state(uuid, work, name, settle=False):
    query = ["nvidia-smi", "-i", uuid, "--query-gpu=uuid,memory.used,utilization.gpu,"
             "ecc.errors.uncorrected.volatile.total", "--format=csv,noheader,nounits"]
    state = command(query)
    samples = [state]
    # Utilization samples include the recently exited test process. Give that
    # sample a bounded time to expire; the final idle/health requirements stay
    # identical, and a foreign compute process still fails the health check.
    if settle:
        for _ in range(10):
            if state.strip().split(",")[2].strip() == "0":
                break
            time.sleep(0.5)
            state = command(query)
            samples.append(state)
    detail = command(["nvidia-smi", "-i", uuid, "-q"])
    apps = command(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"])
    (work / (name + "-nvidia-smi.txt")).write_text(
        "".join(samples) + detail + "\nCompute apps:\n" + apps)
    fields = [x.strip() for x in state.strip().split(",")]
    require(len(fields) == 4 and fields[0] == uuid, "GPU identity/health query failed")
    require(not any(line.split(",")[0].strip() == uuid for line in apps.splitlines()),
            "GPU has a compute process; no fault permitted (or process survived the test)")
    require(int(fields[1]) <= 128 and int(fields[2]) == 0, "GPU is not idle")
    recovery = re.search(r"GPU Recovery Action\s*:\s*(.*)", detail)
    require(not recovery or recovery[1].strip() in ("None", "N/A"), "GPU needs recovery")
    return fields[3]


@contextlib.contextmanager
def _process_cancellation():
    """Defer Python cancellation across spawn/registration and TERM/reap.

    Do not block OS signals around Popen: that would pass a blocked signal mask
    through exec to the child. Once cancellation is delivered, keep subsequent
    signals deferred until cleanup has finished and the old handlers return.
    """
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    deferred = True
    pending = None

    def interrupt(signum, frame):
        nonlocal deferred, pending
        if deferred:
            if pending is None:
                pending = (signum, frame)
            return
        # Shield cleanup before invoking a handler that can raise. In particular,
        # a second cancellation must not escape while unwinding the first one.
        deferred = True
        handler = previous[signum]
        if callable(handler):
            handler(signum, frame)
        else:
            raise RuntimeError(f"driver interrupted by signal {signum}")

    def resume():
        nonlocal deferred
        deferred = False
        if pending is not None:
            interrupt(*pending)

    def defer():
        nonlocal deferred
        deferred = True

    try:
        for sig, handler in previous.items():
            if handler != signal.SIG_IGN:
                signal.signal(sig, interrupt)
        yield resume, defer
        # On normal completion the child has been reaped; do not swallow a
        # cancellation recorded between wait's return and handler restoration.
        resume()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def run_process(argv, cwd, env, work, name, timeout=120):
    # The outer timeout is a failure, never an accepted fatal exit. Fresh process
    # groups bound direct movie runs; the dataset launcher reaps its own workers.
    with (work / (name + ".txt")).open("w") as log, _process_cancellation() as (resume, defer):
        process = None
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            # A pending interruption is delivered only after assignment, inside
            # the cleanup-protected region.
            resume()
            try:
                rc = process.wait(timeout=timeout)
            finally:
                defer()
        except BaseException as error:
            defer()
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    # The dataset coordinator gives its nested launcher up to
                    # 60 s to reap workers; let checked cleanup finish.
                    process.wait(timeout=150)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
            if isinstance(error, subprocess.TimeoutExpired):
                raise RuntimeError(f"{name}: hung; bounded timeout expired") from error
            raise
    (work / (name + "-command.json")).write_text(json.dumps(
        {"argv": argv, "cwd": str(cwd), "returncode": rc}, indent=2) + "\n")
    return rc, (work / (name + ".txt")).read_text()


def fault_verdict(rc, console, out, count, allowed_files=()):
    text = console + "\n".join(p.read_text() for p in out.rglob("*.log"))
    require(console.count("[sticky] launch illegal write in downloadPatchSpectra") == 1,
            "fault did not execute exactly once in the product process")
    require("[sticky] fault completion=700 " in console,
            "illegal write did not produce native cudaErrorIllegalAddress")
    require("[sticky] product cudaMalloc=700 " in console,
            "later real product CUDA call did not observe sticky error after slot clear")
    require(rc == 1, f"documented fatal status must be 1, got {rc}")
    require(re.search(r"CUDA device context is unusable for [^\n]*Movies/control\.tiff \(patch 1, 1\)", text)
            and "Refusing to retry alignment on a poisoned context" in text,
            "fatal refusal missing or attributed to the wrong movie/patch")
    # Startup lists every input, so names elsewhere in the log cannot establish
    # final failure attribution. Error printing can repeat this record; validate
    # every copy rather than accepting one correct copy beside a corrupt one.
    records = re.findall(r"Motion correction failed for [^\r\n]*", text)
    require(records, "job did not attribute all failed/unprocessed movies")
    expected = {"Movies/control.tiff", *(f"Movies/after{i}.tiff" for i in range(1, count))}
    for record in records:
        match = re.fullmatch(
            r"Motion correction failed for (\d+) movie\(s\): (.+)\. "
            r"Successful per-movie outputs were retained; joint output was not generated\.", record)
        require(match is not None, "malformed final movie failure record")
        movies = match[2].split()
        require(int(match[1]) == count and len(movies) == count and set(movies) == expected,
                "final failure record has missing, duplicate or unexpected movies")
    require("[sticky] PRODUCT_KERNEL_AFTER_FAULT" not in console,
            "product dispatched a kernel on the poisoned context")
    # Logs alone are allowed: refuse every product, completion marker and partial
    # file, rather than checking only the final MRC or joint STAR.
    unexpected = [str(p.relative_to(out)) for p in out.rglob("*")
                  if p.is_file() and p.suffix != ".log" and str(p.relative_to(out)) not in allowed_files]
    require(not unexpected, f"failed movies published products/partial products: {unexpected}")


def run_controls(binary, work, uuid):
    data = work / "input"
    write_tiff(data / "Movies/control.tiff", synthetic_frames())
    write_star(data / "single.star")
    multi = (data / "single.star").read_text()
    for i in (1, 2):
        shutil.copyfile(data / "Movies/control.tiff", data / f"Movies/after{i}.tiff")
        multi += f"Movies/after{i}.tiff 1\n"
    (data / "multi.star").write_text(multi)
    (work / "input-sha256.json").write_text(json.dumps({
        str(path.relative_to(data)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(data.rglob("*")) if path.is_file()
    }, indent=2) + "\n")
    options = ["--use_own", "--gpu", "0", "--j", "4", "--max_io_threads", "2",
               "--patch_x", "3", "--patch_y", "3", "--max_iter", "5", "--bfactor", "150",
               "--seed", "1", "--angpix", "1.0", "--voltage", "300"]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=uuid, CUDA_DEVICE_ORDER="PCI_BUS_ID",
               OMP_NUM_THREADS="4", MC_RETRY_CALLER="1", MC_STICKY_FAULT="0")
    # No inherited injected-error controls: this executable links none of them.
    healthy = work / "healthy"
    healthy.mkdir()
    rc, text = run_process([str(binary), "--i", "single.star", "--o", str(healthy) + "/",
                            *options], data, env, work, "healthy")
    require(rc == 0 and "second native alignment succeeded" in text,
            "healthy reference did not complete the actual resident retry")
    require((healthy / "Movies/control.mrc").is_file() and
            (healthy / "Movies/control.star").is_file(), "healthy products absent")
    require("[sticky]" not in text, "healthy process unexpectedly faulted")
    print("PASS healthy: real resident retry and products", flush=True)
    env["MC_STICKY_FAULT"] = "1"
    for name, count in (("single", 1), ("multi", 3)):
        out = work / name
        out.mkdir()
        rc, text = run_process([str(binary), "--i", name + ".star", "--o", str(out) + "/",
                                *options], data, env, work, name)
        fault_verdict(rc, text, out, count)
        print(f"PASS {name}: native sticky error, attributed refusal, exit 1, no products/kernels", flush=True)

    # One isolated GPU worker is enough to exercise the dataset endpoint's #69
    # failure contract; multi-device success/scaling is outside this control.
    dataset = work / "dataset"
    tool = Path(__file__).resolve().parents[1] / "tools/multi_gpu/run_dataset.py"
    cpus = ",".join(str(cpu) for cpu in sorted(os.sched_getaffinity(0)))
    rc, _ = run_process([sys.executable, str(tool), "--binary", str(binary),
                         "--star", str(data / "multi.star"), "--out", str(dataset),
                         "--launcher-args", f"--devices {uuid} --cpus {cpus}",
                         # The launcher supplies --gpu 0 and rejects overrides.
                         "--", options[0], *options[3:]], data, env, work, "dataset", timeout=240)
    status = json.loads((dataset / "dataset_status.json").read_text())
    workers = json.loads((dataset / "workers/status.json").read_text())
    require(rc != 0 and status["verdict"] == "FAIL" and not status["dataset_ready"]
            and not status["workers_complete"], "dataset incorrectly reported success")
    require(len(workers["workers"]) == 1 and workers["workers"][0]["returncode"] == 1,
            "dataset worker did not exit with fatal status 1")
    require(workers["process_cleanup"]["complete"] and not workers["process_cleanup"]["error"]
            and not workers["process_ownership_errors"] and not status["process_ownership_errors"]
            and "cleanup_error" not in status, "dataset worker cleanup failed")
    worker = workers["workers"][0]
    worker_out = dataset / "workers/w0"
    fault_verdict(worker["returncode"], Path(worker["log"]).read_text(), worker_out, 3,
                  allowed_files=("command.json",))
    require(not (dataset / "merged").exists(), "failed worker reached dataset aggregation")
    print("PASS dataset: worker exit 1, dataset FAIL, descendants reaped, no aggregation", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--workdir", type=Path)
    args = parser.parse_args()
    require(sys.platform == "linux", "requires Linux flock and CPU affinity")
    def interrupted(signum, _frame):
        raise RuntimeError(f"driver interrupted by signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    import fcntl
    require(0 < len(os.sched_getaffinity(0)) <= 8, "run under an at-most-eight-CPU taskset cap")
    uuid = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    require(re.fullmatch(r"GPU-[0-9a-fA-F-]{36}", uuid), "CUDA_VISIBLE_DEVICES must be one full GPU UUID")
    inventory = command(["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"])
    indices = [line.split(",")[0].strip() for line in inventory.splitlines()
               if line.split(",")[-1].strip() == uuid]
    require(len(indices) == 1 and indices[0].isdigit(), "UUID not found uniquely in GPU inventory")
    lock = Path(f"/tmp/motioncorr-gpu{indices[0]}-correctness.lock")
    binary = args.binary.resolve()
    require(binary.is_file(), f"missing binary: {binary}")
    work = args.workdir.resolve() if args.workdir else Path(tempfile.mkdtemp(prefix="mc-sticky-"))
    if args.workdir:
        work.mkdir(parents=True, exist_ok=False)
    try:
        with lock.open("a") as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Respect an active benchmark without taking its lock for correctness.
            with open("/tmp/motioncorr-bench.lock", "a") as bench:
                fcntl.flock(bench, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(bench, fcntl.LOCK_UN)
            (work / "provenance.json").write_text(json.dumps({
                "binary": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                "uuid": uuid, "lock": str(lock), "cpus": sorted(os.sched_getaffinity(0)),
                "inputs": "run_resident_retry_controls.py synthetic_frames seed 20261016",
            }, indent=2) + "\n")
            before = gpu_state(uuid, work, "before")
            try:
                run_controls(binary, work, uuid)
            finally:
                after = gpu_state(uuid, work, "after", settle=True)
                require(after == before, "uncorrected volatile ECC count changed")
    except BaseException:
        print(f"FAILED: evidence retained at {work}", file=sys.stderr)
        raise
    print("STICKY_CONTEXT_PASS: GPU healthy after process contexts exited")
    if not args.workdir:
        shutil.rmtree(work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
