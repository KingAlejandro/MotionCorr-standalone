#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Dry-run controls for tools/ccf_dc_stagec_driver.py. No real MotionCorr row, GPU, SSH or CI action.

The "binaries" are tiny fake producer scripts pinned by sha256; the pins are fake (`"fake": true`); the guard and the
grader are injected hooks that only a dry run accepts. The fake grader reuses the real `grade_witness` and `stage_coverage`
for witness decisions, so wrong-stage, zero-eligible and fallback controls go through the real witness rules. Not covered
here (covered by CcfDcRowsNative): the real graders on real products, and anything on a GPU.
"""
import copy
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "test-data"))
import ccf_dc_native_rows as rows            # noqa: E402
import ccf_dc_stagec_driver as drv           # noqa: E402

DOCS = REPO / "docs/post_rc0/ccf_dc_native_compat_20261026"
K267 = ["zero", "integer", "fractional", "affine", "pedestal", "noisy", "flat", "repeated"]
NCASES = [f"vel{v}-N{n}" for v in (0, 1) for n in (5, 9, 13, 20)]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


FAKE_PRODUCER = r'''#!%(py)s
import hashlib, json, os, sys
sys.path.insert(0, %(testdata)r)
import numpy as np
from generate_known_motion_fixture import write_mrc_stack
args = sys.argv[1:]
opt = lambda n: args[args.index(n) + 1]
name = opt("--i")[:-5]
out = opt("--o")
gpu = "--gpu" in args
patches = int(opt("--patch_x"))
kind = os.path.basename(sys.argv[0]).replace("motioncorr_", "")
env = os.environ
arm = env.get("MC_EXPERIMENT_CCF_DC_ARM", "unset")
case = name if name in %(kcases)r else name.replace("_", "-")
key = "|".join([kind, "cuda" if gpu else "cpu", case, arm])
control = json.load(open(env["FAKE_CONTROL"])).get(key, "") if "FAKE_CONTROL" in env else ""
backend = "cuda" if gpu else "cpu"
if control == "fail":
    os._exit(3)
os.makedirs(out)
if control == "sleep":
    import time
    open(os.path.join(out, "pid"), "w").write(str(os.getpid()))
    time.sleep(120)
json.dump(dict(env={k: v for k, v in env.items()}, cwd=sorted(os.listdir(".")), argv=args), open(os.path.join(out, "observed.json"), "w"))
seed = int(hashlib.sha256((case + backend).encode()).hexdigest()[:8], 16)
rng = np.random.default_rng(seed + (7 if control == "pixel" else 0))
write_mrc_stack(__import__("pathlib").Path(out) / (name + ".mrc"), rng.random((1, 4, 4)).astype("<f4"), 0.885)
open(os.path.join(out, name + ".star"), "w").write("star %%s %%s\n" %% (name, backend))
open(os.path.join(out, name + ".log"), "w").write("Global alignment:\n Iteration 1: RMSD = 0.1 px\n")
open(os.path.join(out, "corrected_micrographs.star"), "w").write("corrected\n")
sel = dict(none=(0, 0), unset=(0, 0), **{"global": (1, 0), "local": (0, 1), "both": (1, 1)})[arm]
z = dict(calls_eligible=0, calls_zeroed=0, frames_eligible=0, frames_zeroed=0)
sites = {s: {"global": dict(z), "local": dict(z)} for s in ("cpu", "cuda_single", "cuda_batched")}
gsite = "cuda_single" if gpu else "cpu"
lsite = "cuda_batched" if gpu else "cpu"
def put(site, stage, sel_on, wrong=False):
    sites[site][stage] = dict(calls_eligible=10, calls_zeroed=10 if (sel_on or wrong) else 0, frames_eligible=50,
                              frames_zeroed=50 if (sel_on or wrong) else 0)
put(gsite, "global", sel[0])
if patches > 1 and control != "zero_local":
    put(lsite, "local", sel[1], wrong=(control == "wrong_stage"))
if control == "fallback" and gpu:
    put("cpu", "global", sel[0])
if kind != "def":
    w = dict(schema="mc-ccf-dc-witness-v1", status="atexit", arm="none" if arm == "unset" else arm,
             test_only_isotropic_global_weight=(kind == "iso"), sites=sites)
    json.dump(w, open(env["MC_EXPERIMENT_CCF_DC_REPORT"], "w"))
    if control != "no_tap":
        json.dump(dict(**{"global": [[0.0, 0.0]] * 5}, coeff_x=[0.0] * 18, coeff_y=[0.0] * 18, local_enabled=False),
                  open(env["MC_DIAG_MODEL_OUT"], "w"))
if control == "fail_after_tap":
    os._exit(1)
print("ok" + (" extra" if control == "extra_stdout" else ""))
'''


class World:
    """A temp directory with fake inputs, fake producers, fake pins and the real ledger/pairs/repro/reference files."""

    def __init__(self, tmp, control=None):
        self.tmp = Path(tmp)
        t = self.tmp
        self.control = control or {}
        (t / "control.json").write_text(json.dumps(self.control))
        self.kfx, self.nfx = t / "fx-k267", t / "fx-n"
        self.kfx.mkdir(), self.nfx.mkdir()
        kf = {}
        man = {"cases": {}}
        for c in K267:
            files = {}
            for ext in (".star", ".mrcs", "_target.npy", "_field.npy"):
                (self.kfx / (c + ext)).write_bytes(f"{c}{ext}".encode())
                files[c + ext] = sha(self.kfx / (c + ext))
            man["cases"][c] = dict(files=files)
            kf.update(files)
        (self.kfx / "MANIFEST.json").write_text(json.dumps(man))
        kf["MANIFEST.json"] = sha(self.kfx / "MANIFEST.json")
        nf = {}
        man = {"cases": {}}
        for c in NCASES:
            n = c.replace("-", "_")
            files = {}
            for ext in (".star", ".mrcs", "_truth.npy"):
                (self.nfx / (n + ext)).write_bytes(f"{n}{ext}".encode())
                files[n + ext] = sha(self.nfx / (n + ext))
            man["cases"][n] = dict(files=files)
            nf.update(files)
        (self.nfx / "base_target.npy").write_bytes(b"base")
        man["base_sha256"] = sha(self.nfx / "base_target.npy")
        (self.nfx / "MANIFEST.json").write_text(json.dumps(man))
        nf["base_target.npy"] = man["base_sha256"]
        nf["MANIFEST.json"] = sha(self.nfx / "MANIFEST.json")
        bins = {}
        for k in ("def", "exp", "iso"):
            p = t / f"motioncorr_{k}"
            p.write_text(FAKE_PRODUCER % dict(py=sys.executable, testdata=str(REPO / "test-data"), kcases=K267))
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
            bins[k] = dict(path=str(p), sha256=sha(p))
        f = lambda name: dict(path=str(DOCS / name), sha256=sha(DOCS / name))
        self.pins = dict(
            fake=True, source=dict(commit="0" * 40, archive_sha256="0" * 64),
            ledger=f("ledger.csv"), pairs=f("pairs.csv"), repro=f("repro.csv"), counts=f("counts.json"),
            retained_cpu_reference=f("evidence/retained_cpu_reference.json"),
            retained_render_report=f("evidence/retained_render_report.json"),
            guard=dict(path=str(HERE / "stageC_guard.sh"), sha256=sha(HERE / "stageC_guard.sh")),
            expected=dict(jobs=160, pairs=96, repro=16), binaries=bins,
            fixtures=dict(k267=dict(dir=str(self.kfx), manifest_sha256=kf["MANIFEST.json"], files=33, file_hashes=kf),
                          n=dict(dir=str(self.nfx), manifest_sha256=nf["MANIFEST.json"], files=26, file_hashes=nf)),
            locks=dict(own=str(t / "l1"), cpu=str(t / "l2"), gpu2=str(t / "l3")),
            gpu=dict(uuid="GPU-FAKE", foreign_pid=1), dryrun_env=dict(FAKE_CONTROL=str(t / "control.json")))

    def write_pins(self, name="pins.json", pins=None):
        p = self.tmp / name
        p.write_text(json.dumps(pins or self.pins))
        return p


def make_fake_grader(repro_offset=None):
    """Mirrors the real precedence with the REAL witness rules; metrics are synthetic. repro_offset: {(weight,movie): delta}."""
    retained = {(r["movie"], r["weight"]): r for r in json.loads((DOCS / "evidence/retained_cpu_reference.json").read_text())["rows"]}
    offs = repro_offset or {}

    def grade(job, run_dir):
        run = Path(run_dir)
        rc = int((run / "rc.txt").read_text())
        row = dict(run=str(run), movie=job["case"], backend=job["backend"], arm=job["arm"], exit=rc, tier=job["tier"])
        if rc != 0:
            return dict(row, row_status="FAILED_RUN", reason=f"exit status {rc}")
        name = job["case"] if job["tier"] == "K" else job["case"].replace("-", "_")
        if not all((run / "out" / n).is_file() for n in (name + ".mrc", name + ".star", name + ".log", "corrected_micrographs.star")):
            return dict(row, row_status="INCOMPLETE_PUBLICATION", reason="missing products")
        has_w = job["binary"] != "def"
        row["runtime_representation"] = "NOT_REQUESTED"
        arm = "none" if job["arm"] == "unset" else job["arm"]
        stages = rows.k267_stages(job["case"]) if job["tier"] == "K" else ("global",)
        if has_w:
            if not (run / "witness.json").is_file():
                return dict(row, row_status="INVALID", reason="witness.json absent")
            w = json.loads((run / "witness.json").read_text())
            st, reasons = rows.grade_witness(w, job["backend"], arm, set(stages), job["binary"] == "iso")
            row.update(witness_status=st, witness_reasons=reasons, counters=w["sites"], expected_stages=sorted(stages))
            if st == "INVALID":
                return dict(row, row_status="INVALID", reason="; ".join(reasons))
            row["stage_coverage"] = rows.stage_coverage(w, job["backend"], arm, set(stages))
            if not (run / "tap.json").is_file():
                return dict(row, row_status="INVALID", reason="runtime tap requested but absent")
            row["runtime_representation"] = "SCORED"
        h = int(hashlib.sha256("|".join([job["case"], job["backend"], job["binary"], job["arm"]]).encode()).hexdigest()[:4], 16)
        base = 0.05 + (h % 100) / 1000.0
        m = lambda d=0.0: dict(rms=base + d, p95=base * 1.5 + d, max=base * 2 + d)
        row["convergence"] = dict(status="CONVERGED")
        row["local_enabled"] = "local" in stages
        if job["tier"] == "K":
            row["star"] = dict(field_angstrom=m(), accuracy_status="FAIL")
            if has_w:
                row["tap"] = dict(field_angstrom=m(), accuracy_status="FAIL")
        else:
            wt = {"production": "prod", "isotropic": "iso"}[job["weight"]]
            ref = retained.get((job["case"].replace("-", "_"), wt))
            if ref and job["backend"] == "cpu" and job["arm"] == "none":
                d = offs.get((job["weight"], job["case"]), 0.0)
                row["runtime"] = dict(ref["runtime"], rms=ref["runtime"]["rms"] + d)
                row["STAR"] = dict(ref["STAR"])
                row["traj_rms_px_runtime"] = ref["traj_rms_px_runtime"]
            else:
                row["runtime"] = dict(m(), verdict="FAIL")
                row["STAR"] = dict(m(), verdict="FAIL")
                row["traj_rms_px_runtime"] = 0.3
        row["row_status"] = "INCONCLUSIVE" if row.get("witness_status") == "INCONCLUSIVE" else "SCORED"
        if row["row_status"] == "INCONCLUSIVE":
            row["reason"] = "; ".join(row["witness_reasons"])
        return row
    return grade


OK_GUARD = lambda label, need_gpu: (0, f"guard {label} ok\n")


def run_world(tmp, control=None, grader=None, guard=OK_GUARD, spawner=None, pins_mut=None, outname="stageC"):
    w = World(tmp, control)
    pins = copy.deepcopy(w.pins)
    if pins_mut:
        pins_mut(w, pins)
    pp = w.write_pins(pins=pins)
    d = drv.Driver(pp, Path(tmp) / outname, dry_run=True, grader=grader or make_fake_grader(), spawner=spawner, guard=guard)
    return w, d, d.execute()


def read(p):
    return json.loads(Path(p).read_text())


def events(d):
    return [json.loads(l) for l in (d.outdir / "events.jsonl").read_text().splitlines()]


class PlanAndPins(unittest.TestCase):
    def test_plan_order_and_coverage(self):
        led = drv.load_ledger(DOCS / "ledger.csv")
        plan = drv.make_plan(led)
        self.assertEqual(len(plan), 160)
        self.assertEqual(len({j["job_id"] for _, j in plan}), 160)
        self.assertEqual([p for p, _ in plan][:12], [1] * 12)
        self.assertTrue(all("B4" in j["gates"] for _, j in plan[:12]))
        self.assertEqual({j["case"] for _, j in plan[:12]}, {"affine", "pedestal", "noisy"})
        self.assertTrue(all(j["backend"] == "cuda" and j["binary"] == "exp" for _, j in plan[:12]))
        phase2 = [j for p, j in plan if p == 2]
        self.assertEqual(len(phase2), 80)
        self.assertTrue(all(j["backend"] == "cpu" for j in phase2))
        self.assertEqual([j["tier"] for j in phase2], ["K"] * 48 + ["N"] * 32)
        order = [(j["weight"], j["arm"]) for j in phase2 if j["tier"] == "N"]
        self.assertEqual(order[::8], [("production", "none"), ("isotropic", "none"), ("production", "both"), ("isotropic", "both")])
        phase3 = [j for p, j in plan if p == 3]
        self.assertEqual(len(phase3), 68)
        self.assertTrue(all(j["backend"] == "cuda" for j in phase3))
        self.assertFalse(any(j["tier"] == "M" for _, j in plan))

    def test_committed_pins_match_the_repository(self):
        pins = read(DOCS / "evidence/stageC/STAGEC_PINS.json")
        self.assertFalse(pins["fake"])
        for key, name in (("ledger", "ledger.csv"), ("pairs", "pairs.csv"), ("repro", "repro.csv"), ("counts", "counts.json")):
            self.assertEqual(pins[key]["sha256"], sha(DOCS / name), key)
        self.assertEqual(pins["expected"], dict(jobs=160, pairs=96, repro=16))
        self.assertEqual(pins["source"]["commit"], "96e7e7be0f08469da51c67a1ab251ae4e97cdfc3")
        self.assertEqual(pins["source"]["archive_sha256"], "313f671f4af90e227754ec17c6e8a9cae70a7ea5aaca713de62aa1d297b8ea36")
        self.assertEqual({k: v["sha256"] for k, v in pins["binaries"].items()},
                         {"def": "2db45b2df8241e14bda28e9dbe3d7eae0ce9f5612a7b775bc33990aeb27bed6a",
                          "exp": "b918cadc571eb09d753fd454a20554400ea6443b6b0738e14670f96c7afb2857",
                          "iso": "3a7d4f472c0f795f6e3d7fdb7c31ab5c3e6bdef00ccf95d08a5cf5855155d0ff"})
        self.assertEqual(pins["fixtures"]["k267"]["files"], 33)
        self.assertEqual(pins["fixtures"]["n"]["files"], 26)
        self.assertEqual(len(pins["fixtures"]["k267"]["file_hashes"]), 33)
        self.assertEqual(len(pins["fixtures"]["n"]["file_hashes"]), 26)
        self.assertEqual(pins["fixtures"]["k267"]["manifest_sha256"], "9697c20314d3c0ea4496d4747ad14cbb3088e4e2488b7fccad05ff5f88ad02dc")
        self.assertEqual(pins["fixtures"]["n"]["manifest_sha256"], "6e7b19bd4d5be963c51813e7941749daeb1ca44f8825e79f4df623676fd7c2a8")
        self.assertEqual(pins["gpu"]["uuid"], "GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598")
        self.assertEqual(pins["cpus"], list(range(80, 88)))
        self.assertEqual(pins["omp"], dict(k267=8, n=2))
        self.assertEqual(pins["repro_tolerance"], drv.REPRO_TOL)
        self.assertEqual(pins["guard"]["sha256"], sha(HERE / "stageC_guard.sh"))
        self.assertEqual(pins["python"]["version"], "3.12.3")
        self.assertEqual(pins["python"]["numpy"], "2.5.3")
        for name in ("ccf_dc_native_rows", "ccf_dc_tap_field", "check_motion_diagnostics", "check_realistic_motion", "motion_field"):
            self.assertIn(name, pins["modules"])
        self.assertEqual(pins["modules"]["ccf_dc_native_rows"], sha(HERE / "ccf_dc_native_rows.py"))

    def test_there_is_no_tolerance_or_threshold_input(self):
        import inspect
        self.assertEqual(drv.REPRO_TOL, 1e-5)
        src = inspect.getsource(drv.main)
        for opt in ("tol", "threshold", "retry", "waive"):
            self.assertNotIn(opt, src.lower())


class CleanRun(unittest.TestCase):
    def test_full_clean_dry_run(self):
        with tempfile.TemporaryDirectory() as t:
            calls = []
            real = rows.identity_report
            with mock.patch.object(rows, "identity_report", lambda a, b, m: (calls.append((a, b, m)), real(a, b, m))[1]):
                w, d, res = run_world(t)
            self.assertEqual(res["status"], "COMPLETE", res)
            self.assertEqual((res["jobs_executed"], res["jobs_not_run"]), (160, 0))
            self.assertEqual((res["pairs_expected"], res["pairs_evaluated"]), (96, 96))
            self.assertEqual((res["repro_expected"], res["repro_rows_present"]), (16, 16))
            self.assertEqual(len(calls), 32, "two identity comparisons for each of the 16 (ID, backend) triples")
            jobs = [e for e in events(d) if e["kind"] == "job"]
            self.assertEqual(len(jobs), 160)
            self.assertEqual([e["phase"] for e in jobs], [1] * 12 + [2] * 80 + [3] * 68)
            self.assertEqual(len(set(e["job_id"] for e in jobs)), 160)
            self.assertEqual(len(list((d.outdir / "b3").iterdir())), 16)
            self.assertEqual(sorted(p.name for p in (d.outdir / "repro").iterdir()), ["isotropic.json", "production.json"])
            for p in ("production", "isotropic"):
                self.assertEqual(read(d.outdir / "repro" / f"{p}.json")["failed"], [])
            pairs = read(d.outdir / "pairs_report.json")
            self.assertEqual(len(pairs), 96)
            self.assertFalse(any(p["tier"] == "M" for p in pairs))
            p0 = next(p for p in pairs if p["tier"] == "N")
            self.assertIn("runtime", p0)
            self.assertIn("STAR", p0)
            self.assertIn("convergence_a", p0)
            self.assertIn("counters_b", p0)
            # manifest is closed and complete, and nothing was overwritten
            man = (d.outdir / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(man), sum(len(fn) for _, _, fn in os.walk(d.outdir)) - 1)
            for line in man:
                h, rel = line.split("  ", 1)
                self.assertEqual(sha(d.outdir / rel), h)

    def test_child_environment_and_cwd(self):
        with tempfile.TemporaryDirectory() as t:
            inject = dict(MC_EXPERIMENT_CCF_DC_ARM="both", MC_DIAG_MODEL_OUT="/tmp/x", MOTIONCORR_PATCH_BATCH="1",
                          OMP_NUM_THREADS="64", CUDA_VISIBLE_DEVICES="3", NVIDIA_VISIBLE_DEVICES="all", MC_EXPERIMENT_X="1")
            with mock.patch.dict(os.environ, inject):
                w, d, res = run_world(t)
            self.assertEqual(res["status"], "COMPLETE", res)
            seen = {}
            for jid in ("J001", "J045", "J090"):
                run = next((d.outdir / "runs").glob(jid + "-*"))
                obs = read(run / "out" / "observed.json")
                seen[jid] = obs
                rec = read(run / "receipt.json")
                self.assertEqual(sorted(obs["cwd"]), sorted(rec["ledger_row"]["case"].replace("-", "_") + e for e in (".star", ".mrcs")))
                self.assertFalse(any("truth" in n or "field" in n or "target" in n for n in obs["cwd"]))
                self.assertIn("MC_EXPERIMENT_X", rec["env_dropped_names"])
                self.assertNotIn("MC_EXPERIMENT_X", obs["env"])
                self.assertNotIn("MOTIONCORR_PATCH_BATCH", obs["env"])
            # every child saw only the declared arm, report, tap, OMP and device settings
            for run in (d.outdir / "runs").iterdir():
                obs = read(run / "out" / "observed.json")
                rec = read(run / "receipt.json")
                job = rec["ledger_row"]
                self.assertEqual(obs["env"].get("MC_EXPERIMENT_CCF_DC_ARM"), None if job["arm"] == "unset" or job["binary"] == "def" else job["arm"])
                self.assertEqual(obs["env"]["OMP_NUM_THREADS"], "2" if job["tier"] == "N" else "8")
                if job["backend"] == "cpu":
                    self.assertEqual(obs["env"]["CUDA_VISIBLE_DEVICES"], "")
                    self.assertNotIn("--gpu", obs["argv"])
                else:
                    self.assertEqual(obs["env"]["CUDA_VISIBLE_DEVICES"], "GPU-FAKE")
                    self.assertIn("--gpu", obs["argv"])
                    self.assertEqual(obs["argv"][obs["argv"].index("--gpu") + 1], "0")
                if job["binary"] == "def":
                    self.assertNotIn("MC_DIAG_MODEL_OUT", obs["env"])
                    self.assertNotIn("MC_EXPERIMENT_CCF_DC_REPORT", obs["env"])


class StopControls(unittest.TestCase):
    def stopped(self, res, text):
        self.assertEqual(res["status"], "STOPPED", res)
        self.assertIn(text, res["reason"])

    def jobs_run(self, d):
        return len([e for e in events(d) if e["kind"] == "job"])

    def test_wrong_ledger_pairs_repro_binary_and_input_hashes_refuse_before_any_producer(self):
        for key in ("ledger", "pairs", "repro", "counts"):
            with tempfile.TemporaryDirectory() as t:
                w, d, res = run_world(t, pins_mut=lambda w, p, key=key: p[key].update(sha256="0" * 64))
                self.stopped(res, f"{key} hash differs")
                self.assertEqual(self.jobs_run(d), 0)
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, pins_mut=lambda w, p: p["binaries"]["exp"].update(sha256="1" * 64))
            self.stopped(res, "binary exp hash differs")
            self.assertEqual(self.jobs_run(d), 0)
        with tempfile.TemporaryDirectory() as t:
            def mut(w, p):
                (w.kfx / "affine.mrcs").write_bytes(b"tampered")
            w, d, res = run_world(t, pins_mut=mut)
            self.stopped(res, "input affine.mrcs hash differs")
            self.assertEqual(self.jobs_run(d), 0)
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, pins_mut=lambda w, p: p["fixtures"]["n"].update(files=25))
            self.stopped(res, "input file list differs")

    def test_input_or_binary_changed_between_jobs(self):
        with tempfile.TemporaryDirectory() as t:
            holder = {}
            def guard(label, need_gpu):
                if len(holder.setdefault("n", [])) == 3:
                    (Path(holder["w"].kfx) / "pedestal.star").write_bytes(b"changed")
                holder["n"].append(label)
                return 0, "ok\n"
            w = World(t)
            holder["w"] = w
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=make_fake_grader(), guard=guard)
            res = d.execute()
            self.stopped(res, "input pedestal.star hash differs from the pin")
        with tempfile.TemporaryDirectory() as t:
            holder = {}
            def guard2(label, need_gpu):
                holder.setdefault("n", []).append(label)
                if len(holder["n"]) == 4:
                    with open(holder["w"].pins["binaries"]["exp"]["path"], "a") as f:
                        f.write("#")
                return 0, "ok\n"
            w = World(t)
            holder["w"] = w
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=make_fake_grader(), guard=guard2)
            self.stopped(d.execute(), "binary exp changed")

    def test_wrong_arm_env_or_argv_actually_executed(self):
        def flip_arm(argv, cwd, env, so, se, timeout):
            env = dict(env)
            if env.get("MC_EXPERIMENT_CCF_DC_ARM"):
                env["MC_EXPERIMENT_CCF_DC_ARM"] = "none" if env["MC_EXPERIMENT_CCF_DC_ARM"] != "none" else "both"
            return drv.default_spawner(argv, cwd, env, so, se, timeout)[0], list(argv), env
        # a spawner that returns the environment it used: the driver must compare it with the ledger-derived one
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, spawner=lambda *a: flip_arm(*a))
            self.stopped(res, "differs from the ledger-derived")
            self.assertEqual(self.jobs_run(d), 0)
        def wrong_argv(argv, cwd, env, so, se, timeout):
            argv = list(argv)
            argv[argv.index("--j") + 1] = "4"
            return drv.default_spawner(argv, cwd, env, so, se, timeout)[0], argv, env
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, spawner=wrong_argv)
            self.stopped(res, "differs from the ledger-derived")

    def test_nonfinite_missing_tap_failed_after_tap_wrong_stage_zero_eligible_fallback(self):
        cases = [
            ("exp|cpu|zero|none", "no_tap", "runtime tap requested but absent"),
            ("exp|cpu|zero|none", "fail_after_tap", "exit status 1"),
            ("exp|cpu|zero|none", "fail", "exit status 3"),
            ("exp|cpu|affine|none", "zero_local", "never reached"),
            ("exp|cpu|affine|none", "wrong_stage", "zeroed"),
            ("exp|cuda|affine|both", "fallback", "touched"),
            ("exp|cuda|affine|both", "zero_local", "never reached"),
        ]
        for key, mode, text in cases:
            with tempfile.TemporaryDirectory() as t:
                w, d, res = run_world(t, control={key: mode})
                self.stopped(res, text)
                # the failing row is kept (receipt, row, inventories) and nothing after it ran
                last = [e for e in events(d) if e["kind"] == "job"][-1]
                run = d.outdir / "runs" / last["job_id"]
                self.assertTrue((run / "receipt.json").exists() or (run / "rc.txt").exists())
                self.assertTrue((run / "inventory.post.json").exists())
                self.assertEqual(len(list((d.outdir / "runs").iterdir())), self.jobs_run(d))
                self.assertTrue((d.outdir / "final_status.json").exists())

    def test_nonfinite_metric_and_grader_exception(self):
        base = make_fake_grader()
        def nan_grader(job, run_dir):
            row = base(job, run_dir)
            if job["case"] == "zero" and job["backend"] == "cpu" and job["arm"] == "none" and job["binary"] == "exp":
                row["star"]["field_angstrom"]["rms"] = float("nan")
            return row
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, grader=nan_grader)
            self.stopped(res, "non-finite")
        def boom(job, run_dir):
            if job["job_id"].startswith("J003"):
                raise RuntimeError("consumer exploded")
            return base(job, run_dir)
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, grader=boom)
            self.stopped(res, "grader raised RuntimeError")

    def test_extra_case_and_duplicate_job_id(self):
        led = drv.load_ledger(DOCS / "ledger.csv")
        with tempfile.TemporaryDirectory() as t:
            def mut(w, p):
                rows_ = drv.load_ledger(p["ledger"]["path"])
                extra = dict(rows_[0])
                extra["job_id"] = "J999-K-extra"
                extra["case"] = "extra"
                path = Path(w.tmp) / "ledger-extra.csv"
                import csv
                with open(path, "w", newline="") as f:
                    wr = csv.DictWriter(f, list(rows_[0].keys()))
                    wr.writeheader()
                    wr.writerows(rows_ + [extra])
                p["ledger"] = dict(path=str(path), sha256=sha(path))
            w, d, res = run_world(t, pins_mut=mut)
            self.stopped(res, "161 jobs != 160")
            self.assertEqual(self.jobs_run(d), 0)
        dup = led + [dict(led[0])]
        with self.assertRaises(drv.Stop):
            drv.make_plan(dup)

    def test_guard_busy_and_duplicate_run_path(self):
        n = []
        def guard(label, need_gpu):
            n.append(label)
            return (11, "STOP guard: other compute app on GPU2\n") if len(n) == 5 else (0, "ok\n")
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, guard=guard)
            self.stopped(res, "guard")
            self.assertEqual(self.jobs_run(d), 4)
        with tempfile.TemporaryDirectory() as t:
            w = World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=make_fake_grader(), guard=OK_GUARD)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            phase, job = d.plan[0]
            d.run_job(phase, job)
            with self.assertRaises(drv.Stop):
                d.run_job(phase, job)
            d.release_locks()

    def test_lock_busy_stops_before_any_producer(self):
        import fcntl
        with tempfile.TemporaryDirectory() as t:
            w = World(t)
            fd = os.open(w.pins["locks"]["cpu"], os.O_RDWR | os.O_CREAT)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=make_fake_grader(), guard=OK_GUARD)
                res = d.execute()
            finally:
                os.close(fd)
            self.stopped(res, "lock cpu busy")
            self.assertEqual(self.jobs_run(d), 0)

    def test_b3_identity_failure_stops_the_campaign(self):
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, control={"exp|cpu|integer|unset": "pixel"})
            self.stopped(res, "B3 failed for integer cpu")
            self.assertTrue((d.outdir / "b3" / "integer-cpu.json").exists())
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, control={"def|cpu|flat|unset": "extra_stdout"})
            self.stopped(res, "B3 failed for flat cpu")

    def test_repro_threshold_is_fixed_and_stops_only_the_affected_weight_set(self):
        # just inside the fixed tolerance: passes
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, grader=make_fake_grader({("production", "vel1-N13"): 0.9e-5}))
            self.assertEqual(res["status"], "COMPLETE", res)
        # just outside: production weight set stops, isotropic continues, status INCOMPLETE, nothing relaxed
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, grader=make_fake_grader({("production", "vel1-N13"): 1.2e-5}))
            self.assertEqual(res["status"], "INCOMPLETE", res)
            self.assertEqual(res["stopped_weight_sets"].keys(), {"production"})
            cov = read(d.outdir / "coverage.json")
            skipped = [j for j in cov["not_run"]]
            self.assertEqual(len(skipped), 24, "production: 8 CPU both + 8 CUDA none + 8 CUDA both")
            self.assertTrue(all(d.ledger_by_id(j)["tier"] == "N" and d.ledger_by_id(j)["weight"] == "production" for j in skipped))
            ran = {e["job_id"] for e in events(d) if e["kind"] == "job"}
            self.assertEqual(len([j for j in ran if "-N-" in j]), 64 - 24)
            self.assertTrue(read(d.outdir / "repro" / "isotropic.json")["failed"] == [])
            self.assertLess(res["pairs_evaluated"], 96)
        # an isotropic failure stops the isotropic set only
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t, grader=make_fake_grader({("isotropic", "vel0-N5"): 1.2e-5}))
            self.assertEqual(res["stopped_weight_sets"].keys(), {"isotropic"})

    def test_modifying_a_file_after_the_manifest_is_detected_and_live_files_refused(self):
        with tempfile.TemporaryDirectory() as t:
            w, d, res = run_world(t)
            f = d.outdir / "final_status.json"
            line = next(l for l in (d.outdir / "SHA256SUMS").read_text().splitlines() if l.endswith("final_status.json"))
            f.write_text(f.read_text() + " ")
            self.assertNotEqual(sha(f), line.split()[0])
            p = Path(t) / "live.txt"
            p.write_text("a")
            with self.assertRaises(drv.Stop):
                drv.sha256_file(p, _hook=lambda path: open(path, "a").write("b"))


class ReleaseAndWiring(unittest.TestCase):
    def real_pins(self, w):
        pins = copy.deepcopy(w.pins)
        pins["fake"] = False
        pins["gpu"] = dict(uuid="U", foreign_pid=1)
        return w.write_pins("real-pins.json", pins), pins

    def release(self, w, pins_path, pins, **over):
        rel = dict(schema="stagec-release/1", test_fixture=False, authorized_by="test-parent",
                   run_id="r1", driver_sha256=sha(drv.__file__), pins_sha256=sha(pins_path),
                   ledger_sha256=pins["ledger"]["sha256"], source_commit=pins["source"]["commit"],
                   outdir=str((w.tmp / "stageC").resolve()))
        rel.update(over)
        p = w.tmp / "release.json"
        p.write_text(json.dumps(rel))
        return p

    def test_real_run_refuses_without_a_valid_release_and_with_hooks_or_fake_pins(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(t)
            pp, pins = self.real_pins(w)
            out = w.tmp / "stageC"
            with self.assertRaises(drv.Stop):
                drv.Driver(pp, out)                                           # no release
            ok = self.release(w, pp, pins)
            with self.assertRaises(drv.Stop):
                drv.Driver(pp, out, release_path=ok, grader=lambda j, r: {})  # hook in a real run
            drv.Driver(pp, out, release_path=ok)                             # constructs: all fields bind
            for over in (dict(driver_sha256="0" * 64), dict(pins_sha256="0" * 64), dict(ledger_sha256="0" * 64),
                         dict(source_commit="1" * 40), dict(outdir="/elsewhere"), dict(test_fixture=True),
                         dict(authorized_by=""), dict(run_id=""), dict(schema="other")):
                bad = self.release(w, pp, pins, **over)
                with self.assertRaises(drv.Stop, msg=str(over)):
                    drv.Driver(pp, out, release_path=bad)
            with self.assertRaises(drv.Stop):
                drv.Driver(w.write_pins("fake.json"), out, release_path=ok)    # fake pins in a real run
            with self.assertRaises(drv.Stop):
                drv.Driver(w.write_pins("fake2.json"), out, dry_run=True, release_path=ok)  # dry run takes no release
            with self.assertRaises(drv.Stop):
                drv.Driver(pp, out, dry_run=True)                              # dry run needs fake pins
            self.assertFalse((w.tmp / "stageC").exists(), "refusals create nothing")

    def test_real_graders_are_called_with_the_ledger_derived_arguments(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=make_fake_grader(), guard=OK_GUARD)
            led = drv.load_ledger(DOCS / "ledger.csv")
            seen = []
            with mock.patch.object(rows, "grade_k267", lambda *a, **k: seen.append(("K", a, k)) or {}), \
                    mock.patch.object(rows, "grade_n", lambda *a, **k: seen.append(("N", a, k)) or {}):
                kjob = next(j for j in led if j["tier"] == "K" and j["binary"] == "def" and j["backend"] == "cuda" and j["case"] == "affine")
                njob = next(j for j in led if j["tier"] == "N" and j["binary"] == "iso" and j["arm"] == "both" and j["case"] == "vel1-N20" and j["backend"] == "cuda")
                ujob = next(j for j in led if j["tier"] == "K" and j["binary"] == "exp" and j["arm"] == "unset" and j["case"] == "zero")
                d.real_grade(kjob, "/run/k")
                d.real_grade(njob, "/run/n")
                d.real_grade(ujob, "/run/u")
            k, n, u = seen
            self.assertEqual(k[1][2:5], ("affine", "cuda", "none"))
            self.assertEqual(k[2], dict(iso_expected=False, has_witness=False))
            self.assertEqual(n[1][2:5], ("vel1_N20", "cuda", "both"))
            self.assertEqual(n[2], dict(iso_expected=True, has_witness=True))
            self.assertEqual(u[1][2:5], ("zero", "cpu", "none"))
            self.assertEqual(u[2], dict(iso_expected=False, has_witness=True))

    def test_expected_command_uses_the_pinned_functions(self):
        with tempfile.TemporaryDirectory() as t:
            w = World(t)
            led = drv.load_ledger(DOCS / "ledger.csv")
            kj = next(j for j in led if j["tier"] == "K" and j["case"] == "flat" and j["binary"] == "exp" and j["arm"] == "local" and j["backend"] == "cpu")
            argv, env, name, fx = drv.expected_command(kj, w.pins, "/r")
            self.assertEqual(argv, rows.k267_argv(w.pins["binaries"]["exp"]["path"], "flat", Path("/r") / "out", "cpu"))
            self.assertEqual(argv[argv.index("--patch_x") + 1], "1")        # the original 1x1 CLI is kept
            self.assertEqual(env["MC_EXPERIMENT_CCF_DC_ARM"], "local")
            self.assertEqual(env["OMP_NUM_THREADS"], "8")
            nj = next(j for j in led if j["tier"] == "N" and j["case"] == "vel0-N13" and j["backend"] == "cuda" and j["arm"] == "both")
            argv, env, name, fx = drv.expected_command(nj, w.pins, "/r")
            self.assertEqual(name, "vel0_N13")
            self.assertEqual(argv[argv.index("--last_frame_sum") + 1], "13")
            self.assertEqual(env["OMP_NUM_THREADS"], "2")
            self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "GPU-FAKE")


if __name__ == "__main__":
    unittest.main()
