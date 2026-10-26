#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage C driver: the 160 frozen K267 and N-control jobs, their B3/B4/SEL gates, 96 pairs and 16 C-REPRO rows.

DRAFT. Nothing here has run a real producer. Plan and rules: docs/post_rc0/ccf_dc_native_compat_20261026/evidence/stageC/DRIVER_PLAN.md.
Real execution needs a parent-written release file (see `verify_release`); this module never creates one.

    python3 ccf_dc_stagec_driver.py run --pins STAGEC_PINS.json --release RELEASE.json --outdir <new dir>

Every grade, scorer, command and identity comparison comes from `ccf_dc_native_rows` unchanged. Hooks (spawner, grader,
guard) exist only for the dry run with fake pins; a real run refuses any hook. The driver compares and records; the only
threshold it owns is the C-REPRO tolerance below, fixed in source.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ccf_dc_native_rows as rows  # noqa: E402

REPRO_TOL = 1e-5                      # fixed (Angstrom or px); there is no option to change it
SCRATCH_CAP = 20 * 2 ** 30
ENV_ALLOW = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "USER", "LOGNAME")
JOB_TIMEOUT_S = 900
TIERS = ("K", "N")                    # M is held
N_PHASE2_ORDER = (("production", "none"), ("isotropic", "none"), ("production", "both"), ("isotropic", "both"))


class Stop(Exception):
    """Campaign stop: everything produced so far is kept, no later row runs."""


class Terminated(BaseException):
    """SIGTERM received by the driver; converted into a recorded stop after the child group is cleaned up."""


# ------------------------------------------------------------------------------------------ helpers
def sha256_file(path, _hook=None):
    """sha256 of a closed file; refuses a file that changes while it is being hashed."""
    st0 = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if _hook:
        _hook(path)
    st1 = os.stat(path)
    if (st0.st_size, st0.st_mtime_ns) != (st1.st_size, st1.st_mtime_ns):
        raise Stop(f"file changed while hashing: {path}")
    return h.hexdigest()


def json_safe(obj):
    """Non-finite floats become strings so the record of a stopped row can still be written."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return repr(obj)
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj


def write_json(path, obj):
    with open(path, "x") as f:        # exclusive: nothing is overwritten
        json.dump(json_safe(obj), f, indent=1, sort_keys=True, allow_nan=False)
        f.write("\n")


def nonfinite(obj, where="row"):
    if isinstance(obj, float) and not math.isfinite(obj):
        return where
    if isinstance(obj, dict):
        for k, v in obj.items():
            r = nonfinite(v, f"{where}.{k}")
            if r:
                return r
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            r = nonfinite(v, f"{where}[{i}]")
            if r:
                return r
    return None


def inventory(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            out.append(dict(path=os.path.relpath(p, root), size=os.path.getsize(p), sha256=sha256_file(p)))
    return out


# ------------------------------------------------------------------------------------------ release
def verify_release(release_path, pins_path, driver_path, pins, outdir):
    """The release file is written by the parent. It must bind this exact driver, pins, ledger, source and outdir."""
    try:
        rel = json.loads(Path(release_path).read_text())
    except (OSError, ValueError) as e:
        raise Stop(f"release unreadable: {e}")
    want = dict(schema="stagec-release/1", driver_sha256=sha256_file(driver_path), pins_sha256=sha256_file(pins_path),
                ledger_sha256=pins["ledger"]["sha256"], source_commit=pins["source"]["commit"],
                outdir=str(Path(outdir).resolve()))
    for k, v in want.items():
        if rel.get(k) != v:
            raise Stop(f"release field {k} does not match ({rel.get(k)!r} != {v!r})")
    if rel.get("test_fixture") is not False:
        raise Stop("release is a test fixture")
    if not isinstance(rel.get("authorized_by"), str) or not rel["authorized_by"].strip() or not rel.get("run_id"):
        raise Stop("release lacks authorized_by or run_id")
    return rel


# ------------------------------------------------------------------------------------------ plan
def load_ledger(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def make_plan(ledger):
    """Order fixed before outcomes: B4 rows, then CPU rows (K, then N with arm none before arm both), then the rest."""
    jobs = [r for r in ledger if r["tier"] in TIERS]
    ids = [r["job_id"] for r in jobs]
    if len(set(ids)) != len(ids):
        raise Stop("duplicate job id in the ledger")
    b4 = [j for j in jobs if "B4" in j["gates"].split("+")]
    b4_ids = {j["job_id"] for j in b4}
    cpu_k = [j for j in jobs if j["backend"] == "cpu" and j["tier"] == "K"]
    cpu_n = [j for w, a in N_PHASE2_ORDER for j in jobs
             if j["backend"] == "cpu" and j["tier"] == "N" and j["weight"] == w and j["arm"] == a]
    rest = [j for j in jobs if j["backend"] == "cuda" and j["job_id"] not in b4_ids]
    plan = [(1, j) for j in b4] + [(2, j) for j in cpu_k + cpu_n] + [(3, j) for j in rest]
    if len(plan) != len(jobs) or {j["job_id"] for _, j in plan} != set(ids):
        raise Stop("plan does not cover the ledger exactly once")
    return plan


def n_name(case):
    return case.replace("-", "_")


def n_frames(case):
    return int(re.search(r"N(\d+)$", case).group(1))


def expected_command(job, pins, run_dir):
    """argv, env and staged inputs for one ledger row, rebuilt from the row and the pins only."""
    binary = pins["binaries"][job["binary"]]["path"]
    out = Path(run_dir) / "out"
    if job["tier"] == "K":
        name, argv = job["case"], rows.k267_argv(binary, job["case"], out, job["backend"])
        fx = pins["fixtures"]["k267"]["dir"]
    else:
        name = n_name(job["case"])
        argv = rows.n_argv(binary, name, n_frames(job["case"]), out, job["backend"])
        fx = pins["fixtures"]["n"]["dir"]
    has_witness = job["binary"] != "def"
    arm = None if (job["arm"] == "unset" or not has_witness) else job["arm"]
    omp = rows.N_OMP if job["tier"] == "N" else rows.K267_OMP
    env = rows.run_env(arm, Path(run_dir) / "witness.json" if has_witness else None,
                       Path(run_dir) / "tap.json" if has_witness else None,
                       pins["gpu"]["uuid"] if job["backend"] == "cuda" else None, omp=omp)
    if job["backend"] == "cpu":
        env.update(CUDA_VISIBLE_DEVICES="", NVIDIA_VISIBLE_DEVICES="void")      # GPU hidden
    return argv, env, name, fx


SAMPLE_PERIOD_S = 0.5
MAX_SAMPLES = 240


def _proc_available():
    return sys.platform.startswith("linux") and os.path.exists("/proc/self/status")


def _pdeath():                                   # runs in the child between fork and exec (Linux only, no new dependency)
    import ctypes
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)       # PR_SET_PDEATHSIG


def _scan_children(pid):
    out = []
    for e in os.listdir("/proc"):
        if e.isdigit():
            try:
                st = open(f"/proc/{e}/stat").read()
                if int(st[st.rindex(")") + 2:].split()[1]) == pid:
                    out.append(int(e))
            except (OSError, ValueError, IndexError):
                pass
    return out


def _read_proc(pid):
    d = f"/proc/{pid}"
    kv = dict(l.split(":", 1) for l in open(d + "/status").read().splitlines() if ":" in l)
    rest = (lambda t: t[t.rindex(")") + 2:].split())(open(d + "/stat").read())
    tasks = os.listdir(d + "/task")
    children, via = [], "children"
    for tid in tasks:
        try:
            children += [int(x) for x in open(f"{d}/task/{tid}/children").read().split()]
        except OSError:
            via = "scan"
    if via == "scan":
        children = _scan_children(pid)
    return dict(pid=pid, ppid=int(kv["PPid"]), name=kv["Name"].strip(), state=kv["State"].split()[0], threads=int(kv["Threads"]),
                tasks=len(tasks), cpus_allowed=kv["Cpus_allowed_list"].strip(), utime=int(rest[11]), stime=int(rest[12]), via=via), children


def sample_tree(root):
    queue, seen, recs, errors = [root], set(), [], []
    while queue and len(seen) < 256:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        try:
            rec, ch = _read_proc(pid)
            recs.append(rec)
            queue += ch
        except (OSError, ValueError, KeyError, IndexError) as e:
            errors.append(f"{pid}: {type(e).__name__}: {e}")
    return recs, errors


def gpu_map(pids):
    r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise OSError(f"nvidia-smi rc {r.returncode}")
    out = {}
    for line in r.stdout.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) >= 2 and f[0].isdigit() and int(f[0]) in pids:
            out.setdefault(int(f[0]), []).append(f[1])
    return out


def _kill_group(proc):
    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        try:
            proc.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue


def _reap_group(proc):
    """Leave no process of the child's group behind; returns whether stragglers had to be killed."""
    if proc is None:
        return False
    stragglers = False
    if proc.poll() is None:
        _kill_group(proc)
    try:
        os.killpg(proc.pid, 0)                     # the root is gone; is anything left in its group?
    except ProcessLookupError:
        return stragglers
    stragglers = True
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return stragglers


def summarize(samples, linux, cuda, truncated, stragglers, sample_file):
    pids_seen = [r for s_ in samples for r in s_["pids"]]
    summ = dict(samples=len(samples), truncated=truncated, stragglers_killed=stragglers, sample_file=sample_file,
                read_errors=sum(len(s_["errors"]) for s_ in samples) + sum(1 for s_ in samples if "gpu_error" in s_))
    if not linux:
        return dict(summ, status="UNOBSERVED: /proc not available on this platform")
    if not pids_seen:
        return dict(summ, status="UNOBSERVED: no readable process sample (the child ended before the first sample or /proc was unreadable)")
    summ.update(status="OBSERVED",
                max_tree_pids=max(len(s_["pids"]) for s_ in samples),
                max_threads_total=max(sum(r["threads"] for r in s_["pids"]) for s_ in samples),
                max_tasks_total=max(sum(r["tasks"] for r in s_["pids"]) for s_ in samples),
                cpus_allowed_lists=sorted({r["cpus_allowed"] for r in pids_seen}),
                names=sorted({r["name"] for r in pids_seen}))
    if cuda:
        seen = {}
        for s_ in samples:
            for pid, uu in s_.get("gpu", {}).items():
                seen.setdefault(str(pid), set()).update(uu)
        summ["gpu_uuids_seen_by_pid"] = {k: sorted(v) for k, v in seen.items()}
        summ["gpu_status"] = "OBSERVED" if seen else "UNOBSERVED: no tree pid listed by nvidia-smi compute-apps"
    return summ


def default_spawner(argv, cwd, env, out_path, err_path, timeout):
    """Run the child in its own process group, sample it immediately and periodically, always clean the group up."""
    sample_path = os.path.join(os.path.dirname(out_path), "procsamples.jsonl")
    linux, cuda = _proc_available(), bool(env.get("CUDA_VISIBLE_DEVICES"))
    samples, truncated, proc, rc, stragglers = [], False, None, None, False
    try:
        with open(out_path, "xb") as so, open(err_path, "xb") as se:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=so, stderr=se, stdin=subprocess.DEVNULL,
                                    start_new_session=True, preexec_fn=_pdeath if linux else None)
            t0 = time.monotonic()

            def take():
                nonlocal truncated
                if not linux:
                    return
                if len(samples) >= MAX_SAMPLES:
                    truncated = True
                    return
                recs, errs = sample_tree(proc.pid)
                ent = dict(t=time.time(), pids=recs, errors=errs)
                if cuda:
                    try:
                        ent["gpu"] = {str(k): v for k, v in gpu_map({r["pid"] for r in recs}).items()}
                    except (OSError, subprocess.SubprocessError) as e:
                        ent["gpu_error"] = repr(e)
                samples.append(ent)

            take()
            while rc is None:
                try:
                    rc = proc.wait(timeout=SAMPLE_PERIOD_S)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - t0 > timeout:
                        _kill_group(proc)
                        rc = 124
                        break
                    take()
    finally:
        stragglers = _reap_group(proc)
        with open(sample_path, "x") as f:                        # written even when the run was interrupted
            for ent in samples:
                f.write(json.dumps(json_safe(ent), sort_keys=True) + "\n")
    return rc, list(argv), dict(env), summarize(samples, linux, cuda, truncated, stragglers, os.path.basename(sample_path))


# ------------------------------------------------------------------------------------------ driver
class Driver:
    def __init__(self, pins_path, outdir, *, release_path=None, dry_run=False, grader=None, spawner=None, guard=None):
        self.pins_path, self.outdir = Path(pins_path), Path(outdir)
        self.pins = json.loads(self.pins_path.read_text())
        self.dry_run = dry_run
        if dry_run:
            if not self.pins.get("fake") or release_path is not None:
                raise Stop("dry run needs fake pins and takes no release")
        else:
            if self.pins.get("fake") or grader or spawner or guard:
                raise Stop("a real run refuses fake pins and every hook")
            if any(k.startswith("STAGEC_TEST_") for k in os.environ):
                raise Stop("a test hook (STAGEC_TEST_*) is present in the environment of a real run")
            if not release_path:
                raise Stop("a real run needs a release file")
            self.release = verify_release(release_path, self.pins_path, Path(__file__).resolve(), self.pins, self.outdir)
        self.grader = grader or self.real_grade
        self.spawner = spawner or default_spawner
        self.guard_hook = guard
        self.ledger, self.plan, self.pairs, self.repro = [], [], [], []
        self.results, self.skipped, self.locks, self.seq, self.b3_done = {}, {}, [], 0, set()
        self.stopped_weights = {}
        self.status, self.reason = None, None

    # -- verification of the frozen pins -----------------------------------------------------
    def verify(self):
        p = self.pins
        for key in ("ledger", "pairs", "repro", "counts"):
            if sha256_file(p[key]["path"]) != p[key]["sha256"]:
                raise Stop(f"{key} hash differs from the pin")
        self.ledger = load_ledger(p["ledger"]["path"])
        self.plan = make_plan(self.ledger)
        c = p["expected"]
        if len(self.plan) != c["jobs"]:
            raise Stop(f"{len(self.plan)} jobs != {c['jobs']}")
        self.pairs = [r for r in load_ledger(p["pairs"]["path"]) if r["tier"] in TIERS]
        self.repro = load_ledger(p["repro"]["path"])
        if len(self.pairs) != c["pairs"] or len(self.repro) != c["repro"]:
            raise Stop("pair or repro count differs from the pin")
        for k, b in p["binaries"].items():
            if sha256_file(b["path"]) != b["sha256"]:
                raise Stop(f"binary {k} hash differs from the pin")
        for k in ("retained_cpu_reference", "retained_render_report", "guard"):
            if sha256_file(p[k]["path"]) != p[k]["sha256"]:
                raise Stop(f"{k} hash differs from the pin")
        self.retained = {(r["movie"], r["weight"]): r for r in json.loads(Path(p["retained_cpu_reference"]["path"]).read_text())["rows"]}
        for tag in ("k267", "n"):
            f = p["fixtures"][tag]
            d = Path(f["dir"])
            if sha256_file(d / "MANIFEST.json") != f["manifest_sha256"]:
                raise Stop(f"{tag} manifest hash differs from the pin")
            files = {"MANIFEST.json": f["manifest_sha256"]}
            man = json.loads((d / "MANIFEST.json").read_text())
            for case in man["cases"].values():
                files.update(case["files"])
            if tag == "n":
                files["base_target.npy"] = man["base_sha256"]
            if len(files) != f["files"] or files != f["file_hashes"]:
                raise Stop(f"{tag} input file list differs from the pin")
            for name, h in files.items():
                if sha256_file(d / name) != h:
                    raise Stop(f"{tag} input {name} hash differs")
        if not self.dry_run:
            self.verify_runtime()
        return self

    def verify_runtime(self):
        p = self.pins
        import numpy
        if sys.executable != p["python"]["executable"] or sys.version.split()[0] != p["python"]["version"] \
                or numpy.__version__ != p["python"]["numpy"]:
            raise Stop("interpreter, Python or NumPy differs from the pin")
        for name, h in p["modules"].items():
            if sha256_file(sys.modules[name].__file__) != h:
                raise Stop(f"module {name} differs from the pin")
        cpus = sorted(os.sched_getaffinity(0))
        if cpus != p["cpus"]:
            raise Stop(f"affinity {cpus} != pinned {p['cpus']}")

    # -- resources -----------------------------------------------------------------------------
    def acquire(self, names):
        for n in names:
            path = self.pins["locks"][n]
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o664)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise Stop(f"lock {n} busy")
            self.locks.append(fd)
            self.event("lock", name=n, path=path)

    def release_locks(self):
        for fd in self.locks:
            os.close(fd)
        self.locks = []

    def do_guard(self, label, need_gpu):
        self.seq += 1
        if self.guard_hook:
            rc, text = self.guard_hook(label, need_gpu)
        else:
            g = self.pins
            env = {k: v for k, v in os.environ.items() if k in ENV_ALLOW}
            env.update(STAGEC_GPU2=g["gpu"]["uuid"], STAGEC_FOREIGN_PID=str(g["gpu"]["foreign_pid"]), STAGEC_SCRATCH=str(self.outdir),
                       STAGEC_REAL="0" if self.dry_run else "1")
            p = subprocess.run(["bash", g["guard"]["path"], label, str(int(need_gpu))], env=env, capture_output=True, text=True)
            rc, text = p.returncode, p.stdout + p.stderr
        (self.outdir / "guards").mkdir(exist_ok=True)
        with open(self.outdir / "guards" / f"{self.seq:04d}-{label}.txt", "x") as f:
            f.write(text)
        if rc != 0:
            raise Stop(f"guard {label} stopped the campaign (rc {rc})")

    def check_scratch(self):
        total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fn in os.walk(self.outdir) for f in fn)
        if total > SCRATCH_CAP:
            raise Stop(f"scratch {total} bytes above the cap")

    # -- events and receipts -------------------------------------------------------------------
    def event(self, kind, **kw):
        with open(self.outdir / "events.jsonl", "a") as f:      # open, write, close: never a long-open file
            f.write(json.dumps(dict(t=time.time(), kind=kind, **kw), sort_keys=True, default=str) + "\n")

    # -- grading ---------------------------------------------------------------------------------
    def real_grade(self, job, run_dir):
        arm = "none" if job["arm"] == "unset" else job["arm"]
        kw = dict(iso_expected=job["binary"] == "iso", has_witness=job["binary"] != "def")
        if job["tier"] == "K":
            return rows.grade_k267(run_dir, self.pins["fixtures"]["k267"]["dir"], job["case"], job["backend"], arm, **kw)
        return rows.grade_n(run_dir, self.pins["fixtures"]["n"]["dir"], n_name(job["case"]), job["backend"], arm, **kw)

    @staticmethod
    def check_row(job, row):
        """Declared coverage per row; anything else stops the campaign. Field FAIL/UNIDENTIFIABLE is not examined here."""
        if row.get("row_status") != "SCORED":
            return f"row status {row.get('row_status')}: {row.get('reason')}"
        bad = nonfinite(row)
        if bad:
            return f"non-finite value at {bad}"
        if job["binary"] == "def":
            return None if row.get("runtime_representation") == "NOT_REQUESTED" else "def row is not STAR-only"
        if row.get("runtime_representation") != "SCORED" or row.get("witness_status") != "VALID":
            return "runtime representation or witness is not valid"
        stages = rows.k267_stages(job["case"]) if job["tier"] == "K" else ("global",)
        cov = row.get("stage_coverage", {})
        if cov.get("global") != "COVERED":
            return f"global coverage {cov.get('global')}"
        if "local" in stages and cov.get("local") != "COVERED":
            return f"local coverage {cov.get('local')} but the row requests the local stage"
        if "local" not in stages and not str(cov.get("local", "")).startswith("NOT_APPLICABLE"):
            return f"local coverage {cov.get('local')} on a row that does not request it"
        c = row["counters"]
        g_site, l_site = rows.DECLARED[job["backend"]]["global"], rows.DECLARED[job["backend"]]["local"]
        if c[g_site]["global"]["frames_eligible"] <= 0 or c[g_site]["global"]["calls_eligible"] <= 0:
            return "global counters are not strictly positive"
        if "local" in stages and (c[l_site]["local"]["frames_eligible"] <= 0 or c[l_site]["local"]["calls_eligible"] <= 0):
            return "local counters are not strictly positive"
        if "local" not in stages and c[l_site]["local"]["frames_eligible"] != 0:
            return "local stage reached on a row that does not request it"
        return None

    # -- one job -----------------------------------------------------------------------------------
    def run_job(self, phase, job):
        jid = job["job_id"]
        run_dir = self.outdir / "runs" / jid
        self.do_guard(f"{phase}-{jid}", job["backend"] == "cuda")     # before anything is created for the job
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise Stop(f"run path exists: {run_dir}")
        argv, env_decl, name, fx = expected_command(job, self.pins, run_dir)
        bpin = self.pins["binaries"][job["binary"]]
        if sha256_file(bpin["path"]) != bpin["sha256"]:
            raise Stop(f"binary {job['binary']} changed before {jid}")
        cwd = run_dir / "cwd"
        cwd.mkdir()
        man = json.loads((Path(fx) / "MANIFEST.json").read_text())["cases"][name]["files"]
        for ext in (".star", ".mrcs"):
            src = Path(fx) / (name + ext)
            if sha256_file(src) != man[name + ext]:
                raise Stop(f"input {name + ext} changed before {jid}")
            (cwd / (name + ext)).write_bytes(src.read_bytes())
        if sorted(p.name for p in cwd.iterdir()) != sorted([name + ".star", name + ".mrcs"]):
            raise Stop("the child's working directory holds more than the case STAR and MRC")
        base = {k: v for k, v in os.environ.items() if k in ENV_ALLOW}
        dropped = sorted(k for k in os.environ if k not in ENV_ALLOW)
        env = dict(base)
        env.update(env_decl)
        extra = self.pins.get("dryrun_env", {}) if self.dry_run else {}
        env.update(extra)
        pre = inventory(run_dir)
        write_json(run_dir / "inventory.pre.json", pre)
        t0 = time.time()
        try:
            res = self.spawner(argv, str(cwd), env, str(run_dir / "stdout.txt"), str(run_dir / "stderr.txt"), JOB_TIMEOUT_S)
        except BaseException as e:                  # the spawner cleans the child group first; record the actual exception
            write_json(run_dir / "receipt.json", dict(job_id=jid, ledger_row=job, phase=phase, argv=argv, rc=None,
                                                      interrupted=f"{type(e).__name__}: {e}", run_dir=str(run_dir)))
            self.event("job_interrupted", job_id=jid, exception=f"{type(e).__name__}: {e}")
            raise Stop(f"{jid}: {type(e).__name__} during the child run: {e}")
        rc, actual = res[0], res[1]
        env_used = res[2] if len(res) > 2 else env
        sampling = res[3] if len(res) > 3 else dict(status="UNOBSERVED: the spawner returned no sampling record")
        t1 = time.time()
        with open(run_dir / "rc.txt", "x") as f:
            f.write(f"{rc}\n")
        write_json(run_dir / "argv.json", actual)
        post = inventory(run_dir)
        write_json(run_dir / "inventory.post.json", post)
        receipt = dict(job_id=jid, ledger_row=job, phase=phase, argv=actual, expected_argv=argv, env_declared=env_decl,
                       env_dropped_names=dropped, sampling=sampling, cwd=str(cwd), binary=bpin, source=self.pins["source"]["commit"],
                       pins_sha256=sha256_file(self.pins_path), run_dir=str(run_dir), rc=rc, seconds=t1 - t0,
                       inventory_pre_sha256=hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest(),
                       inventory_post_sha256=hashlib.sha256(json.dumps(post, sort_keys=True).encode()).hexdigest())
        env_ok = all(env_used.get(k) == v for k, v in env_decl.items()) and \
            set(env_used) <= set(ENV_ALLOW) | set(env_decl) | set(extra)
        if list(actual) != list(argv) or not env_ok:
            write_json(run_dir / "receipt.json", receipt)
            raise Stop(f"{jid}: the executed command or environment differs from the ledger-derived one")
        try:
            row = self.grader(job, str(run_dir))
        except Exception as e:                      # a consumer failure is a stop, never a skipped row
            write_json(run_dir / "receipt.json", receipt)
            raise Stop(f"{jid}: grader raised {type(e).__name__}: {e}")
        receipt["row_status"] = row.get("row_status")
        write_json(run_dir / "receipt.json", receipt)
        write_json(run_dir / "row.json", row)
        self.event("job", job_id=jid, phase=phase, rc=rc, row_status=row.get("row_status"))
        self.results[jid] = dict(job=job, row=row, run_dir=str(run_dir))
        why = self.check_row(job, row)
        if rc != 0 and why is None:
            why = f"exit status {rc}"
        if why:
            raise Stop(f"{jid}: {why}")
        self.check_scratch()

    # -- gates ---------------------------------------------------------------------------------------
    def check_b3(self, case, backend):
        r = {x["job"]["binary"] + ":" + x["job"]["arm"]: x["run_dir"] for x in self.results.values()
             if x["job"]["tier"] == "K" and x["job"]["case"] == case and x["job"]["backend"] == backend}
        need = ("def:unset", "exp:unset", "exp:none")
        if (case, backend) in self.b3_done or not all(k in r for k in need):
            return
        self.b3_done.add((case, backend))
        reps = {"def_vs_exp_unset": rows.identity_report(r["def:unset"], r["exp:unset"], case),
                "exp_unset_vs_exp_none": rows.identity_report(r["exp:unset"], r["exp:none"], case)}
        (self.outdir / "b3").mkdir(exist_ok=True)
        write_json(self.outdir / "b3" / f"{case}-{backend}.json", reps)
        self.event("b3", case=case, backend=backend, identical={k: v["identical"] for k, v in reps.items()})
        bad = [k for k, v in reps.items() if not v["identical"]]
        if bad:
            raise Stop(f"B3 failed for {case} {backend}: {bad}")

    def check_repro(self, weight):
        ids = [r["job_id"] for r in self.repro if self.ledger_by_id(r["job_id"])["weight"] == weight]
        if not all(i in self.results for i in ids):
            return
        report, fails = [], []
        for i in ids:
            row, job = self.results[i]["row"], self.results[i]["job"]
            ref = self.retained[(n_name(job["case"]), {"production": "prod", "isotropic": "iso"}[weight])]
            diffs = {}
            for key in ("runtime", "STAR"):
                for m in ("rms", "p95", "max"):
                    diffs[f"{key}.{m}"] = abs(row[key][m] - ref[key][m])
                diffs[f"{key}.verdict_equal"] = row[key]["verdict"] == ref[key]["verdict"]
            diffs["traj_rms_px_runtime"] = abs(row["traj_rms_px_runtime"] - ref["traj_rms_px_runtime"])
            ok = all(v is True or (not isinstance(v, bool) and v <= REPRO_TOL) for v in diffs.values())
            report.append(dict(job_id=i, ok=ok, diffs=diffs))
            if not ok:
                fails.append(i)
        (self.outdir / "repro").mkdir(exist_ok=True)
        write_json(self.outdir / "repro" / f"{weight}.json", dict(tolerance=REPRO_TOL, rows=report, failed=fails))
        self.event("repro", weight=weight, failed=fails)
        if fails:
            self.stopped_weights[weight] = fails

    def ledger_by_id(self, jid):
        return next(r for r in self.ledger if r["job_id"] == jid)

    # -- reports -------------------------------------------------------------------------------------
    @staticmethod
    def representations(row, tier):
        if tier == "K":
            g = lambda k: (row.get(k) or {}).get("field_angstrom")
            v = lambda k: (row.get(k) or {}).get("accuracy_status")
            return {"runtime": (g("tap"), v("tap")), "STAR": (g("star"), v("star"))}
        return {"runtime": (row.get("runtime"), (row.get("runtime") or {}).get("verdict")),
                "STAR": (row.get("STAR"), (row.get("STAR") or {}).get("verdict"))}

    def pair_report(self):
        out = []
        for p in self.pairs:
            a, b = self.results.get(p["job_a"]), self.results.get(p["job_b"])
            ent = dict(comparison=p["comparison"], tier=p["tier"], case=p["case"], weight=p["weight"], job_a=p["job_a"], job_b=p["job_b"])
            if not a or not b or a["row"].get("row_status") != "SCORED" or b["row"].get("row_status") != "SCORED":
                ent["status"] = "NOT_EVALUABLE"
                out.append(ent)
                continue
            ent["status"] = "EVALUATED"
            for rep in ("runtime", "STAR"):
                (ma, va), (mb, vb) = (self.representations(x["row"], p["tier"])[rep] for x in (a, b))
                if not ma or not mb or "rms" not in ma or "rms" not in mb:
                    ent[rep] = dict(status="NOT_EVALUABLE")
                    continue
                d = {m: mb[m] - ma[m] for m in ("rms", "p95", "max")}
                ent[rep] = dict(status="EVALUATED", a=ma, b=mb, delta_b_minus_a=d, verdict_a=va, verdict_b=vb,
                                regression_pass_to_fail=(va == "PASS" and vb == "FAIL"),
                                numeric_increase=any(d[m] > 0 for m in d))
            for side, x in (("a", a), ("b", b)):
                r = x["row"]
                ent[f"convergence_{side}"] = r.get("convergence")
                ent[f"local_enabled_{side}"] = r.get("local_enabled")
                ent[f"counters_{side}"] = r.get("counters")
            out.append(ent)
        return out

    # -- finish --------------------------------------------------------------------------------------
    def write_manifest(self):
        files = sorted(os.path.relpath(os.path.join(dp, f), self.outdir) for dp, _, fn in os.walk(self.outdir) for f in fn if f != "SHA256SUMS")
        lines = [f"{sha256_file(self.outdir / p)}  {p}" for p in files]
        with open(self.outdir / "SHA256SUMS", "x") as f:
            f.write("\n".join(lines) + "\n")
        for line in lines:                               # closure check: every hashed file still has its hash
            h, p = line.split("  ", 1)
            if sha256_file(self.outdir / p) != h:
                raise Stop(f"manifest not closed: {p} changed")
        return len(lines)

    def finish(self, status, reason):
        self.release_locks()
        done = set(self.results)
        not_run = [j["job_id"] for _, j in self.plan if j["job_id"] not in done]
        pairs = self.pair_report()
        if self.status is None:
            self.status = status
        evaluated = sum(p["status"] == "EVALUATED" for p in pairs)
        repro_done = sum(1 for r in self.repro if r["job_id"] in done)
        coverage = dict(jobs_expected=len(self.plan), jobs_executed=len(done), jobs_not_run=len(not_run),
                        pairs_expected=len(pairs), pairs_evaluated=evaluated,
                        repro_expected=len(self.repro), repro_rows_present=repro_done,
                        stopped_weight_sets=self.stopped_weights)
        if self.status == "COMPLETE" and (not_run or evaluated != len(pairs) or repro_done != len(self.repro) or self.stopped_weights):
            self.status = "INCOMPLETE"
        write_json(self.outdir / "pairs_report.json", pairs)
        write_json(self.outdir / "coverage.json", dict(coverage, not_run=not_run))
        write_json(self.outdir / "final_status.json", dict(
            status=self.status, reason=reason, dry_run=self.dry_run, source=self.pins["source"]["commit"],
            scope="K267 and N controls only; M held; no promotion, no whole-movie parity",
            scientific_note="field FAIL/UNIDENTIFIABLE rows are results, kept; newly harmful results block promotion"))
        self.event("final", status=self.status, reason=reason)
        n = self.write_manifest()
        return dict(status=self.status, reason=reason, files_in_manifest=n, **coverage)

    def execute(self):
        self.outdir.mkdir(parents=True, exist_ok=False)
        old_term = None
        try:
            old_term = signal.signal(signal.SIGTERM, lambda sig, frm: (_ for _ in ()).throw(Terminated(f"signal {sig}")))
        except ValueError:                       # not the main thread (dry-run tests): no handler
            pass
        try:
            self.verify()
            self.acquire(["own", "cpu", "gpu2"])
            for phase, job in self.plan:
                if job["tier"] == "N" and job["weight"] in self.stopped_weights:
                    self.skipped[job["job_id"]] = "C-REPRO failed for this weight set"
                    continue
                self.run_job(phase, job)
                if job["tier"] == "K":
                    self.check_b3(job["case"], job["backend"])
                if job["tier"] == "N" and job["backend"] == "cpu" and job["arm"] == "none":
                    self.check_repro(job["weight"])
            return self.finish("COMPLETE", "all planned rows ran and graded")
        except Stop as e:
            self.status = "STOPPED"
            return self.finish("STOPPED", str(e))
        except (KeyboardInterrupt, Terminated) as e:
            self.status = "STOPPED"
            return self.finish("STOPPED", f"interrupted: {type(e).__name__}: {e}")
        except Exception as e:                   # an unexpected failure is a recorded stop, never a silent crash
            self.status = "STOPPED"
            return self.finish("STOPPED", f"unexpected {type(e).__name__}: {e}")
        finally:
            if old_term is not None:
                signal.signal(signal.SIGTERM, old_term)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--pins", required=True)
    r.add_argument("--release", required=True)
    r.add_argument("--outdir", required=True)
    a = ap.parse_args()
    try:
        res = Driver(a.pins, a.outdir, release_path=a.release).execute()
    except Stop as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(res, indent=1, sort_keys=True))
    sys.exit(0 if res["status"] == "COMPLETE" else 1)


if __name__ == "__main__":
    main()
