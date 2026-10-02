#!/usr/bin/env python3
"""Interleaved multi-arm paired campaign for the worker-pool ablation.

Every round runs every arm exactly once, in a rotated (and on even rounds
reversed) order, so slow periods are shared between arms instead of landing on
one of them. Paired differences are taken WITHIN a round against a named
reference arm.

Each run records the complete process wall, CPU seconds, peak host RSS, peak
device memory for its own PID on the named GPU, the full product inventory, the
backend witness, and digests of the MRC data sections and the STAR files. A run
whose digests differ from the reference arm's in the same round is reported as
DIFFER; the campaign does not stop, because an arm that is both faster and wrong
has to appear in the record.
"""
import argparse, hashlib, json, os, re, shutil, signal, statistics, subprocess, sys, time
from pathlib import Path


def settle(gpu_uuid, max_wait=180):
    """Wait until no compute app holds the GPU and the host load is low."""
    for i in range(max_wait):
        try:
            apps = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=gpu_uuid", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=30).stdout
        except Exception:
            apps = ""
        busy = gpu_uuid in apps
        load = float(open("/proc/loadavg").read().split()[0])
        if not busy and load < 2.0:
            return i
        time.sleep(1)
    return -1


def digests(out_dir):
    """MRC data sections (header skipped) and STAR text, both order-stable.

    The output root is spelled away before the STAR text is hashed. Every arm
    writes to its own directory and MotionCorr records the output path inside
    the per-movie and joint STAR files, so without this the STAR digest differs
    between arms for a reason that has nothing to do with the result.
    """
    root = str(Path(out_dir).resolve())
    mrc = hashlib.sha256()
    star = hashlib.sha256()
    n_mrc = n_star = 0
    inventory = []
    for p in sorted(Path(out_dir).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(out_dir).as_posix()
        inventory.append(rel)
        if p.suffix == ".mrc":
            mrc.update(rel.encode())
            with open(p, "rb") as fh:
                fh.seek(1024)
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    mrc.update(chunk)
            n_mrc += 1
        elif p.suffix == ".star":
            star.update(rel.encode())
            text = p.read_bytes().decode("latin-1")
            for spelling in {str(out_dir), root}:
                text = text.replace(spelling, "<OUTROOT>")
            star.update(text.encode("latin-1"))
            n_star += 1
    return {"mrc_sha256": mrc.hexdigest(), "star_sha256": star.hexdigest(),
            "n_mrc": n_mrc, "n_star": n_star, "n_files": len(inventory),
            "inventory_sha256": hashlib.sha256("\n".join(inventory).encode()).hexdigest()}


def sample_device_memory(pid, gpu_uuid, stop_flag, peak):
    import threading
    def loop():
        while not stop_flag[0]:
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10).stdout
                for line in out.splitlines():
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) == 3 and parts[0] == str(pid) and parts[1] == gpu_uuid:
                        peak[0] = max(peak[0], int(parts[2]))
            except Exception:
                pass
            time.sleep(0.1)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def run_one(arm, binary, data, star, out_root, opts, env_extra, cpus, gpu_uuid, round_no):
    out = Path(out_root) / f"{arm}-r{round_no}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    time_log = Path(out_root) / f"time-{arm}-r{round_no}.txt"
    run_log = Path(out_root) / f"run-{arm}-r{round_no}.log"
    env = dict(os.environ)
    env.update(env_extra)
    env["CUDA_VISIBLE_DEVICES"] = gpu_uuid
    cmd = ["/usr/bin/time", "-v", "-o", str(time_log)]
    if cpus:
        cmd = ["taskset", "-c", cpus] + cmd
    cmd += [str(binary), "--i", star, "--o", str(out) + "/"] + opts

    peak = [0]
    stop = [False]
    t0 = time.perf_counter()
    with open(run_log, "wb") as lf:
        proc = subprocess.Popen(cmd, cwd=data, env=env, stdout=lf, stderr=subprocess.STDOUT)
        sample_device_memory(proc.pid, gpu_uuid, stop, peak)
        rc = proc.wait()
    wall = time.perf_counter() - t0
    stop[0] = True

    tv = time_log.read_text() if time_log.exists() else ""
    def grab(pattern, cast=float, default=None):
        m = re.search(pattern, tv)
        return cast(m.group(1)) if m else default
    user = grab(r"User time \(seconds\): ([\d.]+)", float, 0.0)
    sysw = grab(r"System time \(seconds\): ([\d.]+)", float, 0.0)
    rss = grab(r"Maximum resident set size \(kbytes\): (\d+)", int, 0)
    gnu_wall = re.search(r"Elapsed \(wall clock\) time [^:]*: ([\d:.]+)", tv)

    log_text = run_log.read_text(errors="replace")
    witness = {}
    for key, pat in (("nvcomp", r"nvCOMP"), ("pool", r"CUDA worker pool: retained .*")):
        m = re.search(pat, log_text)
        witness[key] = m.group(0) if m else None
    pool_line = witness["pool"]

    row = {"arm": arm, "round": round_no, "rc": rc, "wall_s": round(wall, 4),
           "gnu_elapsed": gnu_wall.group(1) if gnu_wall else None,
           "cpu_s": round(user + sysw, 3), "user_s": user, "sys_s": sysw,
           "max_rss_kb": rss, "peak_device_mib": peak[0],
           "pool_summary": pool_line}
    row.update(digests(out))
    shutil.rmtree(out)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True, help="NAME=/path/to/motioncorr")
    ap.add_argument("--data", required=True)
    ap.add_argument("--star", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--gpu-uuid", required=True)
    ap.add_argument("--cpus", default="")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--env", action="append", default=[], help="K=V")
    ap.add_argument("--opts", required=True)
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--summary", required=True)
    o = ap.parse_args()

    arms = [a.split("=", 1) for a in o.arm]
    names = [a[0] for a in arms]
    binaries = dict(arms)
    assert o.reference in binaries, "reference arm is not among the arms"
    env_extra = dict(e.split("=", 1) for e in o.env)
    opts = o.opts.split()
    Path(o.out).mkdir(parents=True, exist_ok=True)
    rows = []
    jf = open(o.jsonl, "a")

    for r in range(1, o.rounds + 1):
        order = names[(r - 1) % len(names):] + names[:(r - 1) % len(names)]
        if r % 2 == 0:
            order = list(reversed(order))
        for arm in order:
            waited = settle(o.gpu_uuid)
            row = run_one(arm, binaries[arm], o.data, o.star, o.out, opts,
                          env_extra, o.cpus, o.gpu_uuid, r)
            row["settle_s"] = waited
            row["order_in_round"] = order
            rows.append(row)
            jf.write(json.dumps(row) + "\n")
            jf.flush()
            print(f"r{r} {arm:3s} rc={row['rc']} wall={row['wall_s']:.3f} "
                  f"cpu={row['cpu_s']:.2f} rss={row['max_rss_kb']//1024}MiB "
                  f"gpu={row['peak_device_mib']}MiB mrc={row['mrc_sha256'][:12]} "
                  f"n={row['n_mrc']}/{row['n_star']}", flush=True)
    jf.close()

    ref_rows = {r["round"]: r for r in rows if r["arm"] == o.reference}
    summary = {"rounds": o.rounds, "reference": o.reference, "arms": {}}
    for arm in names:
        mine = [r for r in rows if r["arm"] == arm]
        walls = [r["wall_s"] for r in mine]
        diffs, exact, differ = [], 0, []
        for r in mine:
            ref = ref_rows.get(r["round"])
            if not ref:
                continue
            diffs.append(round(r["wall_s"] - ref["wall_s"], 4))
            same = (r["mrc_sha256"] == ref["mrc_sha256"] and
                    r["star_sha256"] == ref["star_sha256"] and
                    r["inventory_sha256"] == ref["inventory_sha256"] and
                    r["rc"] == ref["rc"] == 0)
            exact += 1 if same else 0
            if not same:
                differ.append(r["round"])
        summary["arms"][arm] = {
            "n": len(mine),
            "all_rc0": all(r["rc"] == 0 for r in mine),
            "walls": walls,
            "median_wall_s": round(statistics.median(walls), 4) if walls else None,
            "median_cpu_s": round(statistics.median([r["cpu_s"] for r in mine]), 3) if mine else None,
            "median_rss_kb": int(statistics.median([r["max_rss_kb"] for r in mine])) if mine else None,
            "max_peak_device_mib": max([r["peak_device_mib"] for r in mine], default=0),
            "paired_diff_vs_ref": diffs,
            "median_paired_diff_s": round(statistics.median(diffs), 4) if diffs else None,
            "wins_vs_ref": sum(1 for d in diffs if d < 0),
            "exact_vs_ref": exact,
            "differ_rounds": differ,
            "distinct_mrc_digests": sorted({r["mrc_sha256"][:16] for r in mine}),
            "pool_summary_example": next((r["pool_summary"] for r in mine if r["pool_summary"]), None),
        }
    Path(o.summary).write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["arms"], indent=1))


if __name__ == "__main__":
    sys.exit(main())
