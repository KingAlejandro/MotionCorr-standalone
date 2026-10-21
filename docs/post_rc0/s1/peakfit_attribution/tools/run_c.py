#!/usr/bin/env python3
"""S1.3c runner: replay a #243 sweep run's exact argv with another binary/env.

  run_c.py --sweep-label e12963-03-p5-F-cuda --label <new> --binary <path> [--env K=V ...]
           [--config G] [--save-nodw] [--gpu]

Reads <sweep>/runs/<sweep-label>/run.json, keeps its options and cwd, replaces
the binary, --o and --ingest_witness, and runs on this lane (LANE_GPU; GPU UUID,
CPU mask, per-GPU lock, bench-lock probe), recording run.json like run.py.
--config G drops --patch_x/--patch_y (global only); --save-nodw adds --save_noDW.
"""
import argparse, fcntl, hashlib, json, os, subprocess, sys, threading, time
from pathlib import Path

S = Path(os.environ.get("S13C_ROOT", "/mnt/clathrin/alex-motioncorr-s1ccf"))
SWEEP = Path(os.environ.get("S13C_SWEEP", "/mnt/clathrin/alex-motioncorr-s1/sweep"))
LANES = {"0": ("GPU-eddb42fe-4f9a-adde-76d3-b924e14add54", "96-103"),
         "1": ("GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d", "104-111"),
         "2": ("GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598", "112-119"),
         "3": ("GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d", "88-95")}
LANE = os.environ.get("LANE_GPU", "2")
UUID, CPUS = LANES[LANE]
LANE_LOCK = "/tmp/motioncorr-gpu%s-correctness.lock" % LANE
BENCH_LOCK = "/tmp/motioncorr-bench.lock"


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
        # Shared probe: correctness work coexists with other shared holders and
        # defers only to an exclusive (benchmark) holder.
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN); return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def main():
    global CPUS, LANE_LOCK
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-label", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--config", default="L", choices=["L", "G"])
    ap.add_argument("--save-nodw", action="store_true")
    ap.add_argument("--gpu", action="store_true")
    a = ap.parse_args()
    if not a.gpu:
        CPUS = os.environ.get("MC_CPU_MASK", CPUS)
        LANE_LOCK = os.environ.get("MC_CPU_LOCK", LANE_LOCK)

    src = json.load(open(SWEEP / "runs" / a.sweep_label / "run.json"))
    argv = src["argv"]
    i = next(k for k, x in enumerate(argv) if x.endswith("/motioncorr"))
    opts = argv[i + 1:]
    out = S / "runs" / a.label
    if (out / "run.json").exists():
        print("skip", a.label); return
    out.mkdir(parents=True, exist_ok=True)
    new, k = [], 0
    while k < len(opts):
        x = opts[k]
        if x == "--o":
            new += [x, str(out) + "/"]; k += 2; continue
        if x == "--ingest_witness":
            new += [x, str(out / "witness.txt")]; k += 2; continue
        if a.config == "G" and x in ("--patch_x", "--patch_y"):
            k += 2; continue
        if x in ("--gpu", "--ingest") and not a.gpu:
            k += 2; continue
        new.append(x); k += 1
    if a.gpu and "--gpu" not in new:
        new += ["--gpu", "0", "--ingest", "auto"]
    if "--o" not in new:
        new += ["--o", str(out) + "/"]
    if a.save_nodw:
        new.append("--save_noDW")

    env = dict(os.environ, OMP_NUM_THREADS="8", OPENBLAS_NUM_THREADS="1",
               LD_LIBRARY_PATH="/usr/local/cuda-12.8/lib64:/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib")
    env["CUDA_VISIBLE_DEVICES"] = UUID if a.gpu else ""
    if a.gpu:
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    extra = dict(kv.split("=", 1) for kv in a.env)
    extra = {k: v.replace("{out}", str(out)) for k, v in extra.items()}
    env.update(extra)

    waited = 0
    while not bench_free():
        time.sleep(30); waited += 30
    lock_fd = os.open(LANE_LOCK, os.O_RDWR | os.O_CREAT, 0o664)
    t = time.time(); fcntl.flock(lock_fd, fcntl.LOCK_EX); lane_wait = time.time() - t
    while not bench_free():
        time.sleep(30); waited += 30

    cmd = ["taskset", "-c", CPUS, "/usr/bin/time", "-v", "-o", str(out / "time-v.log"), a.binary] + new
    rec = {"label": a.label, "sweep_label": a.sweep_label, "sweep_cwd": src["cwd"], "source_sha": os.environ["MC_SOURCE_SHA"], "config": a.config,
           "gpu": a.gpu, "binary": a.binary, "binary_sha256": sha256(a.binary), "argv": cmd, "cpu_mask": CPUS,
           "lane_lock": LANE_LOCK, "extra_env": extra, "cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
           "bench_wait_s": waited, "lane_lock_wait_s": round(lane_wait, 1),
           "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    uuids, stop = set(), threading.Event()

    def descendants(root):
        fam, fr = {root}, [root]
        while fr:
            nxt = []
            for pid in fr:
                try:
                    nxt += [int(c) for c in open("/proc/%d/task/%d/children" % (pid, pid)).read().split()]
                except OSError:
                    pass
            fam |= set(nxt); fr = nxt
        return fam

    def sampler(root):
        while not stop.is_set():
            try:
                q = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"],
                                   capture_output=True, text=True, timeout=10).stdout
                fam = descendants(root)
                for line in q.splitlines():
                    u, pid = [x.strip() for x in line.split(",")]
                    if int(pid) in fam:
                        uuids.add(u)
            except Exception:
                pass
            stop.wait(0.2)

    t0 = time.time()
    with open(out / "stdout.log", "w") as so:
        p = subprocess.Popen(cmd, cwd=src["cwd"], env=env, stdout=so, stderr=subprocess.STDOUT)
        th = threading.Thread(target=sampler, args=(p.pid,), daemon=True) if a.gpu else None
        if th:
            th.start()
        p.wait(); stop.set()
        if th:
            th.join(15)
    fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)
    rec.update(rc=p.returncode, wall_s=round(time.time() - t0, 2), gpu_witness_uuids=sorted(uuids))
    json.dump(rec, open(out / "run.json", "w"), indent=1)
    print(json.dumps({k: rec[k] for k in ("label", "rc", "gpu_witness_uuids", "bench_wait_s")}))
    sys.exit(rec["rc"])


if __name__ == "__main__":
    main()
