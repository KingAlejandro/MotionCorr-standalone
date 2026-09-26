#!/usr/bin/env python3
"""Issue #26 CPU strong-scaling harness for MotionCorr on cpu64.

Must be invoked already holding flock /tmp/motioncorr-cpu64-bench.lock.
Gates on quiescence AFTER acquisition, samples third-party CPU during every
run, and interleaves thread counts across repetitions so drift is spread
across the sweep instead of landing on one j.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, threading, time
from pathlib import Path

QUIET_NAMES = ["cc1plus", "cc1", "as", "ld", "make", "cmake", "motioncorr",
               "relion_run_motioncorr", "ctffind4"]  # pgrep -x: exact name, cannot self-match
# Two permanent ctffind processes (~2 cores) are baseline on this host.
BASELINE_CORES = 2.0


def load1():
    return float(open("/proc/loadavg").read().split()[0])


def busy_compilers():
    n = 0
    for name in QUIET_NAMES:
        r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
        n += len([x for x in r.stdout.split() if x])
    return n


_settle_n = [0]


def settle(max_load, timeout_s, log):
    """Gate AFTER acquiring the lock. load1 is a ~1-minute decayed average, so
    after our own j=16 run it stays high for reasons that are already gone; the
    authoritative contention record is the per-run foreign-CPU sampler. So we
    wait hard once at the start of a series and briefly between runs, and always
    log what we saw rather than silently absorbing it."""
    _settle_n[0] += 1
    if _settle_n[0] > 1:
        timeout_s = min(timeout_s, 90)
    t0 = time.time()
    while True:
        l1, nc = load1(), busy_compilers()
        if l1 <= max_load and nc == 0:
            waited = time.time() - t0
            log(f"settle: OK after {waited:.1f}s (load1={l1:.2f}, procs={nc})")
            return waited, l1
        if time.time() - t0 > timeout_s:
            waited = time.time() - t0
            log(f"settle: TIMEOUT after {waited:.1f}s (load1={l1:.2f}, procs={nc}) -- PROCEEDING, FLAGGED")
            return waited, l1
        time.sleep(2.0)


class Sampler(threading.Thread):
    """Sum %CPU of every process outside our own process tree, once a second.

    The measured binary is a *grandchild* (we launch it under /usr/bin/time), so
    excluding only the direct child pid would count our own workload as foreign
    load -- an instrument that cannot distinguish the condition it asserts. We
    therefore walk the ppid graph each sample and exclude the whole subtree.
    Note ps 'pcpu' is a lifetime average, so this is an average-over-run figure,
    not an instantaneous one; it is reported as such.
    """

    def __init__(self, root_pids):
        super().__init__(daemon=True)
        self.root_pids = {int(p) for p in root_pids}
        self.stop_flag, self.samples, self.loads, self.own = False, [], [], []

    def run(self):
        while not self.stop_flag:
            try:
                out = subprocess.run(["ps", "-eo", "pid,ppid,pcpu"],
                                     capture_output=True, text=True).stdout
                rows, kids = [], {}
                for line in out.splitlines()[1:]:
                    f = line.split()
                    if len(f) != 3:
                        continue
                    try:
                        pid, ppid, pc = int(f[0]), int(f[1]), float(f[2])
                    except ValueError:
                        continue
                    rows.append((pid, ppid, pc))
                    kids.setdefault(ppid, []).append(pid)
                mine, stack = set(self.root_pids), list(self.root_pids)
                while stack:
                    for c in kids.get(stack.pop(), []):
                        if c not in mine:
                            mine.add(c); stack.append(c)
                foreign = sum(pc for pid, _, pc in rows if pid not in mine)
                own = sum(pc for pid, _, pc in rows if pid in mine)
                self.samples.append(foreign / 100.0)
                self.own.append(own / 100.0)
                self.loads.append(load1())
            except Exception:
                pass
            time.sleep(1.0)

    def stats(self):
        s = self.samples or [0.0]
        return {
            "foreign_cores_mean": round(sum(s) / len(s), 2),
            "foreign_cores_max": round(max(s), 2),
            "foreign_cores_min": round(min(s), 2),
            "own_cores_mean": round(sum(self.own) / len(self.own), 2) if self.own else None,
            "own_cores_max": round(max(self.own), 2) if self.own else None,
            "load1_mean": round(sum(self.loads) / len(self.loads), 2) if self.loads else None,
            "load1_max": round(max(self.loads), 2) if self.loads else None,
            "n_samples": len(s),
        }


def mrc_digests(path):
    """Pixel bytes and core-header bytes hashed separately: the MRC label at
    offset 224 carries a strftime timestamp and is never reproducible."""
    d = path.read_bytes()
    return {
        "pixels_sha256": hashlib.sha256(d[1024:]).hexdigest(),
        "core_header_sha256": hashlib.sha256(d[:224]).hexdigest(),
        "bytes": len(d),
    }


TIMEV = {
    "user_s": r"User time \(seconds\): ([\d.]+)",
    "sys_s": r"System time \(seconds\): ([\d.]+)",
    "maxrss_kb": r"Maximum resident set size \(kbytes\): (\d+)",
    "wall_str": r"Elapsed \(wall clock\) time.*: ([\d:.]+)",
    "vol_ctx": r"Voluntary context switches: (\d+)",
    "invol_ctx": r"Involuntary context switches: (\d+)",
    "minor_faults": r"Minor \(reclaiming a frame\) page faults: (\d+)",
}
STAGE_RE = re.compile(r"^\s*(\S.*?)\s*:\s+([\d.]+) sec \((\d+) microsec/operation\)")
LOCK_RE = re.compile(r"^(plan_create|plan_destroy|TOTAL)\s*:\s*n=(\d+)\s+wait=([\d.]+) s\s+held=([\d.]+) s")


def parse_time_v(txt):
    out = {}
    for k, pat in TIMEV.items():
        m = re.search(pat, txt)
        if m:
            out[k] = m.group(1)
    for k in ("user_s", "sys_s"):
        if k in out:
            out[k] = float(out[k])
    for k in ("maxrss_kb", "vol_ctx", "invol_ctx", "minor_faults"):
        if k in out:
            out[k] = int(out[k])
    return out


def parse_stages(txt):
    stages = {}
    for line in txt.splitlines():
        m = STAGE_RE.match(line)
        if m:
            stages[m.group(1).strip()] = {"sec": float(m.group(2)), "count": int(m.group(3))}
    return stages


def parse_lockstats(txt):
    out = {}
    for line in txt.splitlines():
        m = LOCK_RE.match(line.strip())
        if m:
            out[m.group(1)] = {"n": int(m.group(2)), "wait_s": float(m.group(3)), "held_s": float(m.group(4))}
    m = re.search(r"max_single_wait:\s*([\d.]+)", txt)
    if m:
        out["max_single_wait_s"] = float(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--work", default="/home/ubuntu/mc-issue26/work")
    ap.add_argument("--star", default="movies1.star")
    ap.add_argument("--threads", default="1,2,4,8,16")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--patch", default="5")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-load", type=float, default=3.0)
    ap.add_argument("--settle-timeout", type=float, default=900)
    ap.add_argument("--extra", default="", help="extra CLI args, space separated")
    ap.add_argument("--keep-output", action="store_true")
    args = ap.parse_args()

    work = Path(args.work)
    logf = open(args.out + ".log", "w")

    def log(m):
        line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {m}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    threads = [int(t) for t in args.threads.split(",")]
    binary = Path(args.binary)

    meta = {
        "label": args.label,
        "host": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "star": args.star,
        "star_sha256": hashlib.sha256((work / args.star).read_bytes()).hexdigest(),
        "patch": args.patch,
        "threads": threads,
        "reps": args.reps,
        "extra": args.extra,
        "baseline_note": f"~{BASELINE_CORES} cores of permanent ctffind load on this host",
        "nproc": os.cpu_count(),
        "OMP_PROC_BIND": os.environ.get("OMP_PROC_BIND", "(unset)"),
        "OMP_PLACES": os.environ.get("OMP_PLACES", "(unset)"),
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "(unset)"),
        "numactl_prefix": os.environ.get("MC26_NUMACTL", ""),
        "runs": [],
    }

    log(f"=== {args.label}: threads={threads} reps={args.reps} ===")
    inputs = [work / "Movies" / "gain.mrc"] + sorted((work / "Movies").glob("*.tiff"))

    for rep in range(1, args.reps + 1):
        order = threads if rep % 2 == 1 else list(reversed(threads))
        log(f"--- rep {rep}/{args.reps}, order={order} ---")
        for j in order:
            settle_wait, l1_pre = settle(args.max_load, args.settle_timeout, log)
            # warm page cache identically before every run so I/O is not a variable
            for p in inputs[:2]:
                subprocess.run(["dd", f"if={p}", "of=/dev/null", "bs=1M"],
                               capture_output=True)
            outdir = f"run_{args.label}_j{j}"
            if (work / outdir).exists():
                shutil.rmtree(work / outdir)
            cmd = (os.environ.get("MC26_NUMACTL", "").split()
                   + ["/usr/bin/time", "-v", str(binary), "--i", args.star, "--o", outdir,
                   "--use_own", "--j", str(j), "--dose_weighting", "--dose_per_frame", "1.277",
                   "--patch_x", args.patch, "--patch_y", args.patch, "--bfactor", "150",
                   "--gainref", "Movies/gain.mrc"])
            if args.extra:
                cmd += args.extra.split()
            proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            samp = Sampler({str(proc.pid), str(os.getpid())})
            samp.start()
            t0 = time.perf_counter()
            out = proc.communicate()[0]
            wall = time.perf_counter() - t0
            samp.stop_flag = True
            samp.join(timeout=3)

            rec = {
                "rep": rep, "threads": j, "order_index": order.index(j),
                "order": order, "wall_s": round(wall, 3), "rc": proc.returncode,
                "settle_wait_s": round(settle_wait, 1), "load1_pre": l1_pre,
                "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            rec.update(parse_time_v(out))
            rec["contention"] = samp.stats()
            st = parse_stages(out)
            if st:
                rec["stages"] = st
            ls = parse_lockstats(out)
            if ls:
                rec["lock_stats"] = ls
            mrcs = sorted((work / outdir / "Movies").glob("*.mrc"))
            rec["outputs"] = {m.name: mrc_digests(m) for m in mrcs}
            Path(work / outdir / "stdout.txt").write_text(out)
            if not args.keep_output:
                for m in mrcs:
                    m.unlink()
            meta["runs"].append(rec)
            log(f"j={j} rep={rep} wall={wall:.2f}s user={rec.get('user_s')} "
                f"rss={rec.get('maxrss_kb', 0)/1048576:.2f}GiB "
                f"foreign={rec['contention']['foreign_cores_mean']}/{rec['contention']['foreign_cores_max']} cores rc={proc.returncode}")
            Path(args.out).write_text(json.dumps(meta, indent=2))

    meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(args.out).write_text(json.dumps(meta, indent=2))
    log(f"=== done -> {args.out} ===")


if __name__ == "__main__":
    main()
