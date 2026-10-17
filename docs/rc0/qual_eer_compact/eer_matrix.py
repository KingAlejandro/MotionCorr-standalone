#!/usr/bin/env python3
"""W-EER-Q driver: run one EER case under the GPU2 correctness lock.

A case runs the same movie list through two or more arms (--ingest auto / float /
compact) in the lane (taskset 112-119, CUDA_VISIBLE_DEVICES=2), records peak RSS
(/usr/bin/time -v), peak GPU2 memory and the compute-apps PIDs from NVML (nvidia-smi,
selected by UUID because nvidia-smi ignores CUDA_VISIBLE_DEVICES), the ingest witness,
exit code and the full log, and finally compares the arms with compare_output_trees.py.

Usage: eer_matrix.py CASE.json   (see cases/ for the schema)
"""
import fcntl, json, os, re, subprocess, sys, threading, time, shutil, pathlib

ROOT = pathlib.Path("/mnt/clathrin/alex-motioncorr-rc0/W-EER-Q")
CPUS = "112-119"
UUID = "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598"   # GPU2
LOCK = "/tmp/motioncorr-gpu2-correctness.lock"
CMP = pathlib.Path("/home/alex/motioncorr-validation-20261011-vm/harness/compare_output_trees.py")
PY = "/home/alex/.mc-venv/bin/python"
ALLOW = ["--allow-added-log-line", "Staging this movie as native",
         "--allow-added-log-line", "Released native uint",
         "--allow-added-log-line", "Materialized native uint",
         "--allow-added-log-line", "EER grouping"]   # the fallback record that auto adds when counts could exceed uint16


def smi(*q):
    return subprocess.run(["nvidia-smi", "-i", UUID] + list(q), capture_output=True, text=True).stdout


def descendants(pid):
    out, todo = set(), [pid]
    while todo:
        p = todo.pop()
        r = subprocess.run(["pgrep", "-P", str(p)], capture_output=True, text=True).stdout.split()
        for c in map(int, r):
            if c not in out:
                out.add(c); todo.append(c)
    return out


BENCH = "/tmp/motioncorr-bench.lock"


def bench_free():
    # `flock -n` takes and drops the lock at once; it never touches a holder.
    return subprocess.run(["flock", "-n", BENCH, "true"]).returncode == 0


def wait_bench_free(waits):
    while not bench_free():
        waits.append(time.strftime("%H:%M:%S"))
        print("bench lock held (W-EER-DEV timing); waiting 60 s", flush=True)
        time.sleep(60)


def wait_gpu_clear():
    while True:
        apps = smi("--query-compute-apps=pid,name,used_memory", "--format=csv,noheader").strip()
        if not apps:
            return
        print("GPU2 busy (foreign process), waiting:", apps, flush=True)
        time.sleep(10)


def run_arm(case, arm, extra, bin_, indir, outdir, logdir):
    outdir.mkdir(parents=True, exist_ok=True)
    witness = logdir / f"{arm}.witness"
    if witness.exists(): witness.unlink()
    opts = case["options"] + ["--ingest", extra] if extra else list(case["options"])
    if case.get("witness", True) and extra is not None:
        opts += ["--ingest_witness", str(witness)]
    cmd = [bin_, "--i", "movies.star", "--o", str(outdir) + "/"] + opts
    tfile = logdir / f"{arm}.time"
    full = ["taskset", "-c", CPUS, "env", "CUDA_VISIBLE_DEVICES=2", "/usr/bin/time", "-v", "-o", str(tfile)] + cmd
    waits = []
    while True:
        wait_bench_free(waits)
        lockfd = os.open(LOCK, os.O_RDWR | os.O_CREAT, 0o666)
        fcntl.flock(lockfd, fcntl.LOCK_EX)
        if bench_free():
            break
        fcntl.flock(lockfd, fcntl.LOCK_UN); os.close(lockfd)   # bench taken while we queued for the GPU lock
    try:
        wait_gpu_clear()
        base_mem = int(smi("--query-gpu=memory.used", "--format=csv,noheader,nounits").strip() or 0)
        # Streaming NVML queries (-lms): per-call nvidia-smi sampling can miss a short run.
        gm = open(logdir / f"{arm}.nvml-gpu.csv", "w"); am = open(logdir / f"{arm}.nvml-apps.csv", "w")
        s_gpu = subprocess.Popen(["nvidia-smi", "-i", UUID, "--query-gpu=timestamp,memory.used", "--format=csv,noheader,nounits", "-lms", "100"], stdout=gm, stderr=subprocess.STDOUT)
        s_app = subprocess.Popen(["nvidia-smi", "-i", UUID, "--query-compute-apps=timestamp,pid,used_gpu_memory", "--format=csv,noheader,nounits", "-lms", "100"], stdout=am, stderr=subprocess.STDOUT)
        time.sleep(0.5)
        sid = {}   # pid -> session id, read from /proc while the process is alive
        stop = threading.Event(); holder = {}

        def classify():
            seen = 0
            while not stop.is_set():
                try:
                    lines = (logdir / f"{arm}.nvml-apps.csv").read_text().splitlines()
                except Exception:
                    lines = []
                for line in lines[seen:]:
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) not in sid:
                        try:
                            sid[int(parts[1])] = int(open(f"/proc/{parts[1]}/stat").read().rsplit(")", 1)[1].split()[3])
                        except Exception:
                            sid[int(parts[1])] = None
                seen = len(lines)
                time.sleep(0.2)

        t0 = time.time()
        with open(logdir / f"{arm}.stdout", "wb") as so, open(logdir / f"{arm}.stderr", "wb") as se:
            p = subprocess.Popen(full, cwd=indir, stdout=so, stderr=se, start_new_session=True)
            holder["p"] = p
            th = threading.Thread(target=classify, daemon=True); th.start()
            rc = p.wait()
            time.sleep(0.5)
            stop.set(); th.join()
        wall = time.time() - t0
        for sp in (s_gpu, s_app):
            sp.terminate()
            try:
                sp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sp.kill(); sp.wait()
        gm.close(); am.close()
    finally:
        fcntl.flock(lockfd, fcntl.LOCK_UN); os.close(lockfd)
    # reduce the NVML streams
    gpu_peak = base_mem; gpu_samples = 0
    for line in (logdir / f"{arm}.nvml-gpu.csv").read_text().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 2 and parts[1].isdigit():
            gpu_samples += 1; gpu_peak = max(gpu_peak, int(parts[1]))
    per_ts = {}; foreign = set(); mine_pids = set()
    for line in (logdir / f"{arm}.nvml-apps.csv").read_text().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            pid = int(parts[1])
            if sid.get(pid) == holder["p"].pid:
                mine_pids.add(pid); per_ts[parts[0]] = per_ts.get(parts[0], 0) + int(parts[2])
            else:
                foreign.add(pid)
    peak = {"mem": gpu_peak, "app_mem": max(per_ts.values()) if per_ts else 0, "foreign": sorted(foreign), "samples": gpu_samples, "mine": sorted(mine_pids)}
    rss = None
    try:
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", tfile.read_text())
        rss = int(m.group(1)) / 1024.0
    except Exception:
        pass
    routes = witness.read_text().strip().splitlines() if witness.exists() else None
    res = {"arm": arm, "ingest": extra, "rc": rc, "wall_s": round(wall, 2), "peak_rss_mib": rss and round(rss, 1),
           "gpu2_mem_base_mib": base_mem, "gpu2_peak_used_mib": peak["mem"],
           "gpu2_peak_over_base_mib": peak["mem"] - base_mem, "nvml_app_peak_mib": peak["app_mem"],
           "foreign_pids_seen": peak["foreign"], "nvml_gpu_samples": peak["samples"], "nvml_my_pids": peak["mine"], "witness": routes, "cmd": cmd, "bench_lock_waits_60s": len(waits)}
    return res


def compare(case, a_dir, b_dir, manifest, star, out_json, products_only=False):
    cmd = [PY, "-I", str(CMP), str(a_dir), str(b_dir), "--manifest", str(manifest), "--input-star", str(star)] + ALLOW
    if products_only: cmd.append("--products-only")
    cmd += ["--json-out", str(out_json)]
    r = subprocess.run(["taskset", "-c", CPUS] + cmd, capture_output=True, text=True)
    return {"rc": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()[-600:], "products_only": products_only}


def main():
    case = json.load(open(sys.argv[1]))
    name = case["name"]
    caseroot = ROOT / "runs" / name
    indir = caseroot / "in"
    logdir = ROOT / "results" / name
    logdir.mkdir(parents=True, exist_ok=True)
    result = {"case": name, "desc": case.get("desc"), "options": case["options"], "arms": {}}
    for arm in case["arms"]:
        r = run_arm(case, arm["name"], arm["ingest"], case["binary"], indir, caseroot / f"out-{arm['name']}", logdir)
        result["arms"][arm["name"]] = r
        print(name, arm["name"], "rc", r["rc"], "wall", r["wall_s"], "rss", r["peak_rss_mib"], "vram", r["gpu2_peak_over_base_mib"], r["witness"], flush=True)
    if case.get("compare"):
        a, b = case["compare"]
        mf = indir / "manifest.json"
        ra = result["arms"][a]; rb = result["arms"][b]
        if ra["rc"] == 0 and rb["rc"] == 0:
            result["compare_complete_tree"] = compare(case, caseroot / f"out-{a}", caseroot / f"out-{b}", mf, indir / "movies.star", logdir / f"compare-{a}-vs-{b}.json")
            if result["compare_complete_tree"]["rc"] != 0:
                result["compare_products_only"] = compare(case, caseroot / f"out-{a}", caseroot / f"out-{b}", mf, indir / "movies.star", logdir / f"compare-{a}-vs-{b}-products.json", True)
            print(name, "compare", result["compare_complete_tree"]["rc"], result["compare_complete_tree"]["stdout"], flush=True)
    # keep logs/star; drop bulk MRC outputs once compared
    if not case.get("keep_mrc"):
        for d in caseroot.glob("out-*"):
            for f in d.rglob("*.mrc"):
                f.unlink()
    for d in caseroot.glob("out-*"):
        dst = logdir / d.name
        if dst.exists(): shutil.rmtree(dst)
        shutil.copytree(d, dst, ignore=shutil.ignore_patterns("*.mrc", "*.mrcs", "*.eps", "*.pdf"))
    (logdir / "result.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
