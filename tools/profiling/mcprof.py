#!/usr/bin/env python3
"""MotionCorr profiling kit (docs/profiling.md).

  mcprof.py run      ARM... --data D --work W [--rounds N] -- <motioncorr options>
  mcprof.py compare  ARM... --data D --work W [--pairs N] [--profile-pass] [--trace-pass] -- <options>
  mcprof.py trace    ARM    --data D --work W [--osrt] [--sample] -- <options>
  mcprof.py trace    --from-sqlite FILE --work W
  mcprof.py kernels  ARM    --data D --work W (--kernel NAME... | --from-trace trace.json --top N) -- <options>
  mcprof.py report   W [--html]
  mcprof.py selftest

ARM is NAME=PATH or PATH. The kit supplies --i, --o and --profile itself and
pins the payload to --cpus and --gpu-uuid. Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import identity, metrics, nsys_db, provenance as prov, report, runner  # noqa: E402


class IdentityFailure(Exception):
    pass


# ----------------------------------------------------------------- common options

def add_common(p: argparse.ArgumentParser, arms: str) -> None:
    if arms == "many":
        p.add_argument("arms", nargs="+", help="NAME=PATH or PATH; the first arm is the baseline")
    elif arms == "one":
        p.add_argument("arms", nargs="?", help="NAME=PATH or PATH")
    p.add_argument("--data", help="directory the STAR's relative movie paths resolve from (payload cwd)")
    p.add_argument("--star", default="movies.star")
    p.add_argument("--movies", type=int, help="use only the first N movies of the STAR")
    p.add_argument("--work", required=True, help="output directory for this kit invocation")
    p.add_argument("--cpus", help="CPU list for taskset, e.g. 96-103")
    p.add_argument("--gpu-uuid", help="physical GPU; sets CUDA_VISIBLE_DEVICES (pass --gpu 0 to MotionCorr)")
    p.add_argument("--runner-cpus", help="pin the kit itself here, away from the payload lane")
    p.add_argument("--env", action="append", default=[], help="extra payload environment, K=V")
    p.add_argument("--source", action="append", default=[], help="NAME=DIR source tree of an arm")
    p.add_argument("--commit", action="append", default=[], help="NAME=SHA source commit of an arm")
    p.add_argument("--no-lock", action="store_true", help="do not take shared-host locks (tests only)")
    p.add_argument("--bench-lock", default=prov.DEFAULT_BENCH_LOCK)
    p.add_argument("--gpu-lock", help="default /tmp/motioncorr-gpu<index>-correctness.lock")
    p.add_argument("--lock-timeout", type=float, default=7200)
    p.add_argument("--settle-timeout", type=float, default=300)
    p.add_argument("--force", action="store_true", help="reuse a non-empty --work")


def parse_arms(specs):
    arms = {}
    for i, s in enumerate(specs or []):
        name, sep, path = s.partition("=")
        if not sep:
            name, path = ("A", "B", "C", "D", "E")[i] if i < 5 else "arm%d" % i, s
        if name in arms:
            raise SystemExit("duplicate arm name %s" % name)
        path = os.path.abspath(path)
        if not os.access(path, os.X_OK):
            raise SystemExit("arm %s: %s is not executable" % (name, path))
        arms[name] = path
    return arms


def kv(items):
    out = {}
    for s in items:
        k, sep, v = s.partition("=")
        if not sep:
            raise SystemExit("expected NAME=VALUE, got %r" % s)
        out[k] = v
    return out


def prepare_work(a) -> str:
    work = os.path.abspath(a.work)
    if os.path.isdir(work) and os.listdir(work) and not a.force:
        raise SystemExit("%s is not empty (use --force to reuse it)" % work)
    os.makedirs(work, exist_ok=True)
    return work


def gpu_lock_path(a):
    if a.gpu_lock:
        return a.gpu_lock
    rec = prov.gpu_record(a.gpu_uuid)
    if not rec or "index" not in rec:
        raise SystemExit("cannot resolve the GPU index of %s for its lock; pass --gpu-lock" % a.gpu_uuid)
    return "/tmp/motioncorr-gpu%s-correctness.lock" % rec["index"]


@contextlib.contextmanager
def held_locks(a, records):
    if a.no_lock:
        yield
        return
    paths = [a.bench_lock] + ([gpu_lock_path(a)] if a.gpu_uuid else [])
    with contextlib.ExitStack() as stack:
        for p in paths:
            print("mcprof: waiting for %s" % p, flush=True)
            lk = stack.enter_context(prov.HostLock(p, timeout_s=a.lock_timeout))
            records.append(lk.record())
        yield


def pin_runner(a):
    if a.runner_cpus and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, prov.cpu_list(a.runner_cpus))


def binaries_record(a, arms):
    src, com = kv(a.source), kv(a.commit)
    return {n: prov.binary_record(p, src.get(n), com.get(n)) for n, p in arms.items()}


def payload_args(rest):
    if rest and rest[0] == "--":
        rest = rest[1:]
    return rest


def start(a, rest, instrument, need_arms=True):
    """Shared setup: arms, work dir, staged input, sampler, provenance skeleton."""
    arms = parse_arms(a.arms if isinstance(a.arms, list) else ([a.arms] if a.arms else []))
    if need_arms and not arms:
        raise SystemExit("no arm given")
    if not a.data:
        raise SystemExit("--data is required")
    work = prepare_work(a)
    cpus = prov.cpu_list(a.cpus)
    pin_runner(a)
    staged = runner.stage_input(a.data, a.star, a.movies, work)
    args = payload_args(rest)
    _, env_changes = runner.payload_env(a.gpu_uuid, a.env)
    p = prov.provenance(instrument, sys.argv, binaries_record(a, arms), cpus, a.gpu_uuid,
                        {"arms": list(arms), "input": staged, "payload_args": args, "payload_env": env_changes,
                         "locks": []})
    return arms, work, cpus, staged, args, p


# ----------------------------------------------------------------- run / compare

def cmd_run(a, rest, compare=False):
    arms, work, cpus, staged, args, p = start(a, rest, "mcprof compare" if compare else "mcprof run")
    sampler = runner.make_sampler(a.gpu_uuid)
    p["vram_instrument"] = sampler.instrument
    runs_path = os.path.join(work, "runs.jsonl")
    ident = {}
    base = list(arms)[0]

    def sink(rec):
        with open(runs_path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print("mcprof: %-8s %-6s r%02d wall %.3f s%s" % (rec["arm"], rec["kind"], rec["round"], rec["wall_s"],
              ("  DISCARD: " + "; ".join(rec["flags"]["discard"])) if rec["flags"]["discard"] else ""), flush=True)

    def after_round(r, done):
        if not compare or r != 1:
            return
        for arm, rec in done.items():
            if arm == base:
                continue
            ident[arm] = identity.compare_trees(done[base]["out_dir"], rec["out_dir"])
        prov.write_json(os.path.join(work, "identity.json"), ident)
        if any(not v["identical"] for v in ident.values()):
            raise IdentityFailure("products differ: " + "; ".join(
                "%s: %s" % (k, ", ".join(v["problems"])) for k, v in ident.items() if not v["identical"]))

    status = 0
    with held_locks(a, p["locks"]):
        p["settle"] = runner.settle(sampler, a.settle_timeout)
        prov.write_json(os.path.join(work, "provenance.json"), p)
        try:
            rounds = a.pairs if compare else a.rounds
            runner.series(arms, args, staged, work, cpus, a.gpu_uuid, a.env, rounds, a.warmup, sampler, sink,
                          after_round, keep_outputs=a.keep_outputs, lane_wait_s=a.lane_wait)
        except IdentityFailure as e:
            print("mcprof: IDENTITY FAILURE: %s" % e, flush=True)
            status = 2
        if compare and status == 0:
            if a.profile_pass:
                profile_passes(a, arms, args, staged, work, cpus, sampler, p)
            if a.trace_pass:
                order = list(arms)
                for k in range(a.trace_pass):
                    for arm in (order if k % 2 == 0 else order[::-1]):
                        trace_dir = os.path.join(work, "trace", arm, "p%02d" % (k + 1))
                        os.makedirs(trace_dir, exist_ok=True)
                        do_trace(a, arms[arm], args, staged, trace_dir, cpus,
                                 p["binaries"][arm]["has_profile_option"])
                        print("mcprof: %-8s trace p%02d done" % (arm, k + 1), flush=True)
                p["trace_pass"] = "%d trace(s) per arm" % a.trace_pass
    prov.write_json(os.path.join(work, "provenance.json"), p)
    write_report(work, a.noise_floor, a.html)
    return status


def profile_passes(a, arms, args, staged, work, cpus, sampler, p):
    missing = [n for n in arms if not p["binaries"][n]["has_profile_option"]]
    if missing:
        p["profile_pass"] = "skipped: no --profile option in %s" % ", ".join(missing)
        return
    env, _ = runner.payload_env(a.gpu_uuid, a.env)
    pdir = os.path.join(work, "profile")
    os.makedirs(pdir, exist_ok=True)
    order = list(arms)
    for k in range(a.profile_pass):
        for arm in (order if k % 2 == 0 else order[::-1]):
            tag = "%s-p%02d" % (arm, k + 1)
            out = os.path.join(pdir, tag, "out")
            jsonl = os.path.join(pdir, tag + ".jsonl")
            argv = runner.payload_argv(arms[arm], args, staged["star"], out, cpus, profile=jsonl)
            rec = runner.run_once(argv, staged["cwd"], env, os.path.join(pdir, tag + ".log"), sampler, cpus,
                                  arms[arm], out, len(staged["movies"]))
            rec.update({"arm": arm, "kind": "profile", "round": k + 1, "position": 0, "order": "", "jsonl": jsonl})
            with open(os.path.join(work, "runs.jsonl"), "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            print("mcprof: %-8s profile p%02d wall %.3f s (profiled; not used for the verdict)"
                  % (arm, k + 1, rec["wall_s"]), flush=True)
            shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    p["profile_pass"] = "%d pass(es) per arm" % a.profile_pass


# ----------------------------------------------------------------- trace

def sudo_wrap(cmd, env_changes):
    keep = {k: os.environ[k] for k in ("PATH", "LD_LIBRARY_PATH", "HOME") if k in os.environ}
    keep.update(env_changes)
    return ["sudo", "-n", "env"] + ["%s=%s" % kv for kv in keep.items()] + cmd


def do_trace(a, binary, args, staged, work, cpus, has_profile):
    nsys = a.nsys or shutil.which("nsys") or "/usr/local/bin/nsys"
    base = os.path.join(work, "trace")
    out = os.path.join(work, "out")
    prof_file = os.path.join(work, "trace.profile.jsonl") if has_profile else None
    payload = runner.payload_argv(binary, args, staged["star"], out, [], profile=prof_file)
    trace = "cuda,nvtx" + (",osrt" if a.osrt else "")
    cmd = [nsys, "profile", "--trace=" + trace, "--cuda-memory-usage=true", "--stats=false",
           "--force-overwrite=true", "-o", base]
    if a.sample:
        cmd += ["--sample=process-tree", "--backtrace=fp", "--sampling-period=250000"]
    else:
        cmd += ["--sample=none", "--cpuctxsw=none"]
    cmd += payload
    if cpus:
        cmd = ["taskset", "-c", ",".join(map(str, cpus))] + cmd
    env, changes = runner.payload_env(a.gpu_uuid, a.env)
    if a.sample:
        cmd = sudo_wrap(cmd, changes)
    os.makedirs(out, exist_ok=True)
    log = os.path.join(work, "trace.log")
    t0 = time.monotonic()
    with open(log, "w") as f:
        rc = subprocess.call(cmd, cwd=staged["cwd"], env=env, stdout=f, stderr=subprocess.STDOUT)
    wall = time.monotonic() - t0
    if a.sample:
        subprocess.call(["sudo", "-n", "chown", "-R", "%d:%d" % (os.getuid(), os.getgid()), work])
    if rc != 0:
        raise SystemExit("nsys profile exited %d; see %s" % (rc, log))
    n = runner.count_mrc(out)
    if n < len(staged["movies"]):
        raise SystemExit("traced run wrote %d MRC products for %d movies; see %s" % (n, len(staged["movies"]), log))
    sqlite = base + ".sqlite"
    rc = subprocess.call([nsys, "export", "--type", "sqlite", "--force-overwrite", "true", "-o", sqlite,
                          base + ".nsys-rep"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if rc != 0 or not os.path.isfile(sqlite):
        raise SystemExit("nsys export failed (%d)" % rc)
    meta = {"command": cmd, "nsys_wall_s": wall, "binary_sha256": prov.sha256_file(binary),
            "profile_jsonl": prof_file, "trace": trace, "sampled": bool(a.sample),
            "nvtx_stages": bool(has_profile)}
    result = analyze_sqlite(sqlite, work, meta, sample=a.sample)
    shutil.rmtree(out, ignore_errors=True)
    if a.keep != "sqlite":
        os.remove(sqlite)
    if a.keep == "none":
        os.remove(base + ".nsys-rep")
    return result


def analyze_sqlite(sqlite, work, meta, sample=False):
    db = nsys_db.NsysDB(sqlite)
    t = metrics.analyze(db)
    t["capture"] = meta
    if not meta.get("nvtx_stages", True):
        t["warning"] = "binary has no --profile option: no stage ranges, whole-trace figures only"
    prov.write_json(os.path.join(work, "trace.json"), t)
    prov.write_json(os.path.join(work, "timeline.json"), metrics.timeline(db, t))
    if sample and db.has_sampling():
        samples, frames, names = db.sampling()
        folded, dropped = metrics.folded_stacks(samples, frames, names)
        with open(os.path.join(work, "folded.txt"), "w") as f:
            for k, v in sorted(folded.items(), key=lambda kv: -kv[1]):
                f.write("%s %d\n" % (k, v))
        t["sampling"] = {"samples": sum(folded.values()), "stacks": len(folded), "without_callchain": dropped,
                         "note": "CPU sampling inflates some host calls (cuModuleLoadData >10x measured); "
                                 "cross-check host figures against an unsampled run"}
        prov.write_json(os.path.join(work, "trace.json"), t)
    db.close()
    return t


def cmd_trace(a, rest):
    if a.from_sqlite:
        work = prepare_work(a)
        analyze_sqlite(os.path.abspath(a.from_sqlite), work, {"from_sqlite": os.path.abspath(a.from_sqlite)},
                       sample=a.sample)
        prov.write_json(os.path.join(work, "provenance.json"),
                        prov.provenance("Nsight Systems (existing export)", sys.argv, {}, [], None))
        write_report(work, 0.0, a.html)
        return 0
    arms, work, cpus, staged, args, p = start(a, rest, "Nsight Systems trace")
    if len(arms) != 1:
        raise SystemExit("trace takes exactly one arm")
    (name, binary), = arms.items()
    sampler = runner.make_sampler(a.gpu_uuid)
    with held_locks(a, p["locks"]):
        p["settle"] = runner.settle(sampler, a.settle_timeout)
        prov.write_json(os.path.join(work, "provenance.json"), p)
        do_trace(a, binary, args, staged, work, cpus, p["binaries"][name]["has_profile_option"])
    write_report(work, 0.0, a.html)
    return 0


# ----------------------------------------------------------------- kernels

def cmd_kernels(a, rest):
    arms, work, cpus, staged, args, p = start(a, rest, "Nsight Compute")
    if len(arms) != 1:
        raise SystemExit("kernels takes exactly one arm")
    (name, binary), = arms.items()
    names = list(a.kernel)
    nsys_k = {}
    if a.from_trace:
        t = report.load_json(a.from_trace)
        nsys_k = {k["name"]: k for k in t["top_kernels"]}
        if not names:
            names = [k["name"] for k in t["top_kernels"][:a.top]]
    if not names:
        raise SystemExit("give --kernel NAME or --from-trace trace.json")
    ncu = a.ncu or shutil.which("ncu") or "/usr/local/cuda/bin/ncu"
    env, changes = runner.payload_env(a.gpu_uuid, a.env)
    summary = {"kernels": {}, "units_rejected": {}}
    runs = []
    sampler = runner.make_sampler(a.gpu_uuid)
    with held_locks(a, p["locks"]):
        p["settle"] = runner.settle(sampler, a.settle_timeout)
        for i, kname in enumerate(names):
            base = os.path.join(work, "ncu-%d" % i)
            out = os.path.join(work, "out-%d" % i)
            cmd = [ncu, "--target-processes", "all", "--kernel-name-base", "function",
                   "--kernel-name", "regex:^%s$" % _re_escape(kname), "--launch-skip", str(a.launch_skip),
                   "--launch-count", str(a.launch_count), "-f", "-o", base]
            for s in a.section:
                cmd += ["--section", s]
            cmd += runner.payload_argv(binary, args, staged["star"], out, [])
            if cpus:
                cmd = ["taskset", "-c", ",".join(map(str, cpus))] + cmd
            if not a.no_sudo:
                cmd = sudo_wrap(cmd, changes)
            log = base + ".log"
            with open(log, "w") as f:
                rc = subprocess.call(cmd, cwd=staged["cwd"], env=env, stdout=f, stderr=subprocess.STDOUT)
            if not a.no_sudo:
                subprocess.call(["sudo", "-n", "chown", "-R", "%d:%d" % (os.getuid(), os.getgid()), work])
            text = open(log, errors="replace").read()
            if rc != 0:
                raise SystemExit("ncu exited %d for %s; see %s" % (rc, kname, log))
            if "No kernels were profiled" in text:
                raise SystemExit("ncu profiled no kernels for %s (it exits 0 in that case); see %s" % (kname, log))
            rc, csv_text = prov.run_text([ncu, "--import", base + ".ncu-rep", "--csv", "--page", "details"],
                                         timeout=600)
            if rc != 0:
                raise SystemExit("ncu --import failed: %s" % csv_text[:500])
            with open(base + ".csv", "w") as f:
                f.write(csv_text)
            s = metrics.ncu_summary(csv_text)
            if not s["kernels"]:
                raise SystemExit("ncu CSV for %s has no metrics" % kname)
            summary["kernels"].update(s["kernels"])
            for k, v in s["units_rejected"].items():
                summary["units_rejected"].setdefault(k, sorted(set(v)))
            runs.append({"kernel": kname, "command": cmd, "csv": base + ".csv"})
            shutil.rmtree(out, ignore_errors=True)
    res = {"summary": summary, "nsys": nsys_k, "nsys_source": a.from_trace,
           "requested": names, "runs": runs, "sections": a.section,
           "launch_skip": a.launch_skip, "launch_count": a.launch_count}
    prov.write_json(os.path.join(work, "kernels.json"), res)
    prov.write_json(os.path.join(work, "provenance.json"), p)
    write_report(work, 0.0, a.html)
    return 0


def _re_escape(s):
    out = []
    for ch in s:
        out.append("\\" + ch if ch in ".^$*+?{}[]\\|()" else ch)
    return "".join(out)


# ----------------------------------------------------------------- report

def write_report(work, floor_s, want_html):
    p = report.load_json(os.path.join(work, "provenance.json"))
    parts = [report.render_provenance(p)]
    out = {}
    title = "MotionCorr profile"
    runs_path = os.path.join(work, "runs.jsonl")
    if os.path.isfile(runs_path):
        runs = report.load_runs(runs_path)
        arms = p["arms"]
        timing = [r for r in runs if r["kind"] in ("warmup", "round")]
        d = report.derive_runs({"arms": arms, "runs": timing}, floor_s=floor_s)
        out["runs"] = d
        title = "MotionCorr %s: %s" % ("compare" if len(arms) > 1 else "run", " vs ".join(arms))
        parts.append(report.render_run_section(d))
        ip = os.path.join(work, "identity.json")
        if os.path.isfile(ip):
            out["identity"] = report.load_json(ip)
            parts.append(report.render_identity(out["identity"]))
        elif len(arms) > 1 and p["instrument"] == "mcprof compare":
            parts.append("## Product identity\n\nNot checked: the comparison stopped before round 1 finished.\n")
        profiles = {}
        for r in runs:
            if r["kind"] == "profile":
                profiles.setdefault(r["arm"], []).append(r["jsonl"])
        if profiles:
            out["stage_deltas"] = report.derive_stage_deltas(profiles, arms[0])
            parts.append(report.render_stage_deltas(out["stage_deltas"]))
        traces = {}
        for arm in arms:
            found = sorted(glob.glob(os.path.join(work, "trace", arm, "p*", "trace.json")))
            if found:
                traces[arm] = [report.load_json(f) for f in found]
        if traces:
            out["device_deltas"] = report.derive_device_deltas(traces, arms[0])
            parts.append(report.render_device_deltas(out["device_deltas"]))
            for arm, ts in traces.items():
                parts.append(report.render_trace(ts[0]).replace(
                    "## Device", "## Device: `%s` (trace pass 1 of %d)" % (arm, len(ts)), 1))
        prov.write_json(os.path.join(work, "compare.json" if len(arms) > 1 else "results.json"), out)
    elif os.path.isfile(os.path.join(work, "trace.json")):
        t = report.load_json(os.path.join(work, "trace.json"))
        title = "MotionCorr trace"
        if t.get("warning"):
            parts.append("WARNING: %s\n" % t["warning"])
        parts.append(report.render_trace(t))
    elif os.path.isfile(os.path.join(work, "kernels.json")):
        title = "MotionCorr kernel counters"
        parts.append(report.render_kernels(report.load_json(os.path.join(work, "kernels.json"))))
    else:
        raise SystemExit("%s holds no kit results" % work)
    md = report.render_document(title, parts)
    with open(os.path.join(work, "report.md"), "w") as f:
        f.write(md)
    if want_html:
        with open(os.path.join(work, "report.html"), "w") as f:
            f.write(report.to_html(md, title))
    print("mcprof: wrote %s" % os.path.join(work, "report.md"), flush=True)
    return md


def cmd_report(a, rest):
    write_report(os.path.abspath(a.work), a.noise_floor, a.html)
    return 0


def cmd_selftest(a, rest):
    suite = unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"), top_level_dir=HERE)
    res = unittest.TextTestRunner(verbosity=2 if a.verbose else 1).run(suite)
    return 0 if res.wasSuccessful() and res.testsRun > 0 else 1


# ----------------------------------------------------------------- main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    rest = []
    if "--" in argv:
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("run", "compare"):
        p = sub.add_parser(name)
        add_common(p, "many")
        p.add_argument("--warmup", type=int, default=1, help="unrecorded runs per arm first (binary/page cache)")
        p.add_argument("--keep-outputs", action="store_true")
        p.add_argument("--lane-wait", type=float, default=300,
                       help="before each round wait up to S seconds for other processes to leave --cpus")
        p.add_argument("--noise-floor", type=float, default=0.0, help="minimum noise in seconds for a verdict")
        p.add_argument("--html", action="store_true")
        if name == "run":
            p.add_argument("--rounds", type=int, default=6)
        else:
            p.add_argument("--pairs", type=int, default=8)
            p.add_argument("--profile-pass", type=int, nargs="?", const=3, default=0,
                           help="--profile passes per arm for stage deltas (3 when given without N)")
            p.add_argument("--trace-pass", type=int, nargs="?", const=2, default=0,
                           help="Nsight Systems traces per arm for device deltas (2 when given without N)")
            p.add_argument("--nsys")
            p.add_argument("--osrt", action="store_true")
            p.add_argument("--keep", choices=("none", "rep", "sqlite"), default="rep")
            p.add_argument("--sample", action="store_true", help=argparse.SUPPRESS)
    p = sub.add_parser("trace")
    add_common(p, "one")
    p.add_argument("--from-sqlite", help="analyse an existing nsys SQLite export instead of capturing")
    p.add_argument("--nsys")
    p.add_argument("--osrt", action="store_true", help="also trace OS runtime calls")
    p.add_argument("--sample", action="store_true", help="CPU sampling under sudo -n; writes folded.txt")
    p.add_argument("--keep", choices=("none", "rep", "sqlite"), default="rep")
    p.add_argument("--html", action="store_true")
    p = sub.add_parser("kernels")
    add_common(p, "one")
    p.add_argument("--kernel", action="append", default=[], help="kernel function name (exact)")
    p.add_argument("--from-trace", help="trace.json from mcprof trace; supplies names and nsys durations")
    p.add_argument("--top", type=int, default=2)
    p.add_argument("--launch-skip", type=int, default=0)
    p.add_argument("--launch-count", type=int, default=10)
    p.add_argument("--section", action="append",
                   default=None, help="ncu section (repeatable)")
    p.add_argument("--ncu")
    p.add_argument("--no-sudo", action="store_true")
    p.add_argument("--html", action="store_true")
    p = sub.add_parser("report")
    p.add_argument("work")
    p.add_argument("--noise-floor", type=float, default=0.0)
    p.add_argument("--html", action="store_true")
    p = sub.add_parser("selftest")
    p.add_argument("-v", "--verbose", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "kernels" and not a.section:
        a.section = ["SpeedOfLight", "Occupancy", "MemoryWorkloadAnalysis", "LaunchStats"]
    if a.cmd in ("compare",) and a.pairs < 1:
        ap.error("--pairs must be positive")
    fn = {"run": cmd_run, "compare": lambda a, r: cmd_run(a, r, compare=True), "trace": cmd_trace,
          "kernels": cmd_kernels, "report": cmd_report, "selftest": cmd_selftest}[a.cmd]
    try:
        return fn(a, rest)
    except (prov.LockError, nsys_db.SchemaError, metrics.MetricError, RuntimeError, ValueError) as e:
        print("mcprof: error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
