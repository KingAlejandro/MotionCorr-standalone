#!/usr/bin/env python3
"""S1.3 runner (from W-DIAG-S1 diag_run.py): one motioncorr invocation per call.
Lane from LANE_GPU (default 1): GPU UUID, CPU mask and correctness lock below.
CPU-backend runs also hold the lane lock, so they own the lane's CPUs.

Gates every run on /tmp/motioncorr-bench.lock being free, holds the GPU1
correctness lock for the run, records argv/binary hash/env/rc/wall/RSS.
Keeps the per-movie .log and .star; MRCs stay until analysis deletes them.
"""
import argparse, fcntl, hashlib, json, os, subprocess, sys, time
from pathlib import Path

S = Path("/mnt/clathrin/alex-motioncorr-s1ccf")
LANES = {"0": ("GPU-eddb42fe-4f9a-adde-76d3-b924e14add54", "96-103"),
         "1": ("GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d", "104-111"),
         # Used for S1.3: GPU1 was held by another campaign; GPU2's lock and CPUs 112-119 were idle.
         "2": ("GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598", "112-119")}
LANE = os.environ.get("LANE_GPU", "1")
GPU1_UUID, CPUS = LANES[LANE]
LANE_LOCK = "/tmp/motioncorr-gpu%s-correctness.lock" % LANE
BENCH_LOCK = "/tmp/motioncorr-bench.lock"

FAMILIES = {
    "tutorial": ["--dose_per_frame", "1.277", "--expected_frames", "24", "--gainref", "gain.mrc"],
    "e10361":   ["--dose_per_frame", "1.032258064516129", "--expected_frames", "62"],
    "e10474f3": ["--dose_per_frame", "1.0", "--expected_frames", "58", "--eer_grouping", "40", "--eer_upsampling", "1"],
    "e12963":   ["--dose_per_frame", "1.282051282051282", "--expected_frames", "39", "--gainref", "gain.gain",
                 "--eer_grouping", "49", "--eer_upsampling", "1"],
    "e10216":   ["--dose_per_frame", "1.0", "--expected_frames", "59"],
    "e10641":   ["--dose_per_frame", "1.0", "--expected_frames", "70", "--gainref", "gain.mrc"],
    # S1.1 sweep (#243) movie e10641-01, HM70-1_10-A-004_0008; same family options.
    "e10641b":  ["--dose_per_frame", "1.0", "--expected_frames", "70", "--gainref", "gain.mrc"],
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def bench_free():
    try:
        fd = os.open(BENCH_LOCK, os.O_RDONLY)
    except FileNotFoundError:
        return True
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # same test as `flock -n <lock> true`
        fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--config", default="L", choices=["G", "L"])
    ap.add_argument("--patches", type=int, default=5, help="patch grid for config L (5 = #212 L, 3 = #243 3x3)")
    ap.add_argument("--extra", default="", help="extra args, space separated")
    ap.add_argument("--no-ingest-flags", action="store_true", help="old builds without --ingest/--ingest_witness")
    ap.add_argument("--env", action="append", default=[], help="KEY=VALUE for diagnostic builds")
    a = ap.parse_args()

    cwd = S / "inputs" / a.family
    out = S / "runs" / a.label
    out.mkdir(parents=True, exist_ok=True)
    args = ["--use_own", "--dose_weighting", "--bfactor", "150", "--seed", "1"] + FAMILIES[a.family]
    args += ["--i", "movies.star", "--o", str(out) + "/", "--j", "8"]
    if a.config == "L":
        args += ["--patch_x", str(a.patches), "--patch_y", str(a.patches)]
    if a.gpu:
        args += ["--gpu", "0"]
        if not a.no_ingest_flags:
            args += ["--ingest", "auto"]
    if not a.no_ingest_flags:
        args += ["--ingest_witness", str(out / "witness.txt")]
    if a.extra:
        args += a.extra.split()

    env = dict(os.environ, OMP_NUM_THREADS="8", OPENBLAS_NUM_THREADS="1",
               LD_LIBRARY_PATH="/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib")
    if a.gpu:
        env.update(CUDA_VISIBLE_DEVICES=GPU1_UUID, CUDA_DEVICE_ORDER="PCI_BUS_ID")
    else:
        env["CUDA_VISIBLE_DEVICES"] = ""

    extra_env = dict(kv.split("=", 1) for kv in a.env)
    env.update(extra_env)

    waited = 0.0
    while not bench_free():
        time.sleep(30); waited += 30
    lock_fd = os.open(LANE_LOCK, os.O_RDWR | os.O_CREAT, 0o664)
    t_lock = time.time()
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    lane_wait = time.time() - t_lock
    while not bench_free():  # re-check after acquiring the lane
        time.sleep(30); waited += 30

    cmd = ["taskset", "-c", CPUS, "/usr/bin/time", "-v", "-o", str(out / "time-v.log"), a.binary] + args
    rec = {"label": a.label, "family": a.family, "config": a.config, "patches": a.patches, "gpu": a.gpu,
           "binary": a.binary, "binary_sha256": sha256(a.binary), "cwd": str(cwd), "argv": cmd,
           "cpu_mask": CPUS, "lane_lock": LANE_LOCK, "env": {k: env[k] for k in ("OMP_NUM_THREADS", "CUDA_VISIBLE_DEVICES", "LD_LIBRARY_PATH") if k in env},
           "extra_env": extra_env, "bench_wait_s": waited, "lane_lock_wait_s": round(lane_wait, 1),
           "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    t0 = time.time()
    import threading
    smi_uuids, smi_hits = set(), [0]

    def descendants(root):
        fam, frontier = {root}, [root]
        while frontier:
            nxt = []
            for pid in frontier:
                try:
                    kids = open("/proc/%d/task/%d/children" % (pid, pid)).read().split()
                except OSError:
                    kids = []
                nxt += [int(k) for k in kids]
            fam |= set(nxt); frontier = nxt
        return fam

    stop = threading.Event()

    def sampler(root):
        while not stop.is_set():
            try:
                q = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                                   capture_output=True, text=True, timeout=10).stdout
                fam = descendants(root)
                for line in q.splitlines():
                    u, pid = [x.strip() for x in line.split(",")]
                    if int(pid) in fam:
                        smi_uuids.add(u); smi_hits[0] += 1
            except Exception:
                pass
            stop.wait(0.2)

    with open(out / "stdout.log", "w") as so:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=so, stderr=subprocess.STDOUT)
        th = None
        if a.gpu:
            th = threading.Thread(target=sampler, args=(p.pid,), daemon=True); th.start()
        p.wait()
        stop.set()
        if th:
            th.join(15)
    rec["gpu_witness_hits"] = smi_hits[0]
    rec["rc"] = p.returncode
    rec["wall_s"] = round(time.time() - t0, 2)
    rec["gpu_witness_uuids"] = sorted(smi_uuids)
    fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)
    try:
        for line in open(out / "time-v.log"):
            if "Maximum resident" in line:
                rec["max_rss_kib"] = int(line.split()[-1])
            if "Exit status" in line:
                rec["time_exit_status"] = int(line.split()[-1])
    except FileNotFoundError:
        pass
    json.dump(rec, open(out / "run.json", "w"), indent=1)
    print(json.dumps({k: rec[k] for k in ("label", "rc", "wall_s", "gpu_witness_uuids", "bench_wait_s")}))
    sys.exit(rec["rc"])


if __name__ == "__main__":
    main()
