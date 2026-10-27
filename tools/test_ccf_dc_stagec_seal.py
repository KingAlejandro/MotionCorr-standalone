#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Controls for the Stage C driver review r1 findings (amendment 2): leases held through sealing (F1), per-job inputs and truth
against the frozen pins (F2), guard bytes hashed then executed (F3), release record (F4), child environment record (F6),
the prepared loader preflight, and the evidence-manifest counts (F7). Dry run only: fake producers and pins, no real MotionCorr
row, no GPU, no SSH. Local use: at most two threads, a few MB of scratch.
"""
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ccf_dc_stagec_driver as drv          # noqa: E402
import test_ccf_dc_stagec_driver as T       # noqa: E402

DOCS = HERE.parent / "docs/post_rc0/ccf_dc_native_compat_20261026"
LINUX = sys.platform.startswith("linux") and os.path.exists("/proc/self/status")


def lock_state(w):
    """Try to take each of the three lock files from a fresh descriptor; True means it was free."""
    out = {}
    for name in ("own", "cpu", "gpu2"):
        fd = os.open(w.pins["locks"][name], os.O_RDWR | os.O_CREAT, 0o664)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out[name] = True
        except BlockingIOError:
            out[name] = False
        finally:
            os.close(fd)                 # closing also drops a lock this probe just took
    return out


def early_stop_guard():
    n = []
    def guard(label, need_gpu):
        n.append(label)
        return (11, "STOP guard: other compute app on GPU2\n") if len(n) == 2 else (0, "ok\n")
    return guard


class LeasesThroughSealing(unittest.TestCase):
    def run_probed(self, raise_in_manifest=False, guard=None):
        probes = []
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=guard or early_stop_guard())
            orig_pairs, orig_man, orig_wj = drv.Driver.pair_report, drv.Driver.write_manifest, drv.write_json

            def pairs(self_):
                probes.append(("pair_report", lock_state(w)))
                return orig_pairs(self_)

            def man(self_):
                probes.append(("write_manifest", lock_state(w)))
                if raise_in_manifest:
                    raise RuntimeError("seal failed")
                return orig_man(self_)

            def wj(path, obj):
                if Path(path).name in ("coverage.json", "final_status.json"):
                    probes.append((Path(path).name, lock_state(w)))
                return orig_wj(path, obj)

            err = None
            with mock.patch.object(drv.Driver, "pair_report", pairs), mock.patch.object(drv.Driver, "write_manifest", man), \
                    mock.patch.object(drv, "write_json", wj):
                try:
                    res = d.execute()
                except RuntimeError as e:
                    res, err = None, e
            after = lock_state(w)
            return probes, after, res, err

    def test_leases_are_held_while_the_records_and_the_manifest_are_written(self):
        probes, after, res, err = self.run_probed()
        self.assertEqual(res["status"], "STOPPED", res)
        names = [n for n, _ in probes]
        self.assertEqual(names, ["pair_report", "coverage.json", "final_status.json", "write_manifest"])
        for name, state in probes:
            self.assertEqual(state, dict(own=False, cpu=False, gpu2=False), f"a lease was free while {name} ran")
        self.assertEqual(after, dict(own=True, cpu=True, gpu2=True), "all three are free only after execute() returns")

    def test_leases_are_released_after_a_failure_during_sealing_and_not_before(self):
        probes, after, res, err = self.run_probed(raise_in_manifest=True)
        self.assertIsInstance(err, RuntimeError)
        self.assertEqual(dict(probes)["write_manifest"], dict(own=False, cpu=False, gpu2=False))
        self.assertEqual(after, dict(own=True, cpu=True, gpu2=True))

    def test_old_driver_would_have_been_caught(self):
        """The 26e74d8a ordering (release first) fails the lease-held assertions above: shown on a patched finish()."""
        probes = []
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=early_stop_guard())
            orig_finish, orig_man = drv.Driver.finish, drv.Driver.write_manifest
            with mock.patch.object(drv.Driver, "finish", lambda self_, s, r: (self_.release_locks(), orig_finish(self_, s, r))[1]), \
                    mock.patch.object(drv.Driver, "write_manifest", lambda self_: (probes.append(lock_state(w)), orig_man(self_))[1]):
                d.execute()
        self.assertEqual(probes, [dict(own=True, cpu=True, gpu2=True)], "released-first ordering is visible to the probe")


class FrozenFixtureChecks(unittest.TestCase):
    def tampered(self, mutate, job_index=0, hook_at=1):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            n = []
            def guard(label, need_gpu):
                n.append(label)
                if len(n) == hook_at:
                    mutate(w)
                return 0, "ok\n"
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=guard)
            res = d.execute()
            runs = sorted((d.outdir / "runs").iterdir()) if (d.outdir / "runs").exists() else []
            return res, runs

    def assert_stopped_before_the_child(self, res, runs, text):
        self.assertEqual(res["status"], "STOPPED", res)
        self.assertIn(text, res["reason"])
        for r in runs:
            self.assertFalse((r / "stdout.txt").exists(), "no child may have started")
            self.assertFalse((r / "receipt.json").exists())

    def test_input_and_manifest_tampered_together_stops_before_the_child(self):
        def mutate(w):
            (w.kfx / "affine.star").write_bytes(b"TAMPERED")
            man = json.loads((w.kfx / "MANIFEST.json").read_text())
            man["cases"]["affine"]["files"]["affine.star"] = hashlib.sha256(b"TAMPERED").hexdigest()
            (w.kfx / "MANIFEST.json").write_text(json.dumps(man))        # the mutable manifest now agrees with the tampered file
        res, runs = self.tampered(mutate)
        self.assert_stopped_before_the_child(res, runs, "k267 manifest hash differs from the pin")

    def test_truth_file_tampered_stops_before_the_child(self):
        res, runs = self.tampered(lambda w: (w.kfx / "affine_target.npy").write_bytes(b"truth changed"))
        self.assert_stopped_before_the_child(res, runs, "k267 input affine_target.npy hash differs from the pin")
        res, runs = self.tampered(lambda w: (w.kfx / "noisy_field.npy").write_bytes(b"truth changed"))
        self.assert_stopped_before_the_child(res, runs, "k267 input noisy_field.npy hash differs from the pin")

    def test_manifest_alone_tampered_stops_before_the_child(self):
        res, runs = self.tampered(lambda w: (w.kfx / "MANIFEST.json").write_text((w.kfx / "MANIFEST.json").read_text() + " "))
        self.assert_stopped_before_the_child(res, runs, "manifest hash differs from the pin")

    def test_an_n_job_checks_its_own_fixture_including_truth(self):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            njob = next(j for p_, j in d.plan if j["tier"] == "N")
            (w.nfx / "vel0_N5_truth.npy").write_bytes(b"truth changed")
            with self.assertRaises(drv.Stop) as cm:
                d.run_job(2, njob)
            self.assertIn("n input vel0_N5_truth.npy hash differs from the pin", str(cm.exception))
            self.assertFalse((d.outdir / "runs" / njob["job_id"] / "stdout.txt").exists())
            d.release_locks()

    def test_an_untampered_run_still_passes_the_check(self):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            phase, job = d.plan[0]
            d.run_job(phase, job)
            self.assertTrue((d.outdir / "runs" / job["job_id"] / "stdout.txt").exists())
            d.release_locks()

    def test_the_old_per_job_check_is_bypassed_by_the_old_logic(self):
        """What the review's P2b did: input and mutable manifest changed together agree, so a check against the manifest passes."""
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            (w.kfx / "affine.star").write_bytes(b"TAMPERED")
            man = json.loads((w.kfx / "MANIFEST.json").read_text())
            man["cases"]["affine"]["files"]["affine.star"] = hashlib.sha256(b"TAMPERED").hexdigest()
            (w.kfx / "MANIFEST.json").write_text(json.dumps(man))
            old_check = hashlib.sha256((w.kfx / "affine.star").read_bytes()).hexdigest() == man["cases"]["affine"]["files"]["affine.star"]
            pinned = w.pins["fixtures"]["k267"]["file_hashes"]["affine.star"]
            new_check = hashlib.sha256((w.kfx / "affine.star").read_bytes()).hexdigest() == pinned
        self.assertTrue(old_check)
        self.assertFalse(new_check)


class GuardBytes(unittest.TestCase):
    def world_with_private_guard(self, t):
        w = T.World(t)
        guard = Path(t) / "guard.sh"
        shutil.copy(HERE / "stageC_guard.sh", guard)
        w.pins["guard"] = dict(path=str(guard), sha256=T.sha(guard))
        return w, guard

    def test_replacement_after_verify_stops_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as t:
            w, guard = self.world_with_private_guard(t)
            marker = Path(t) / "SENTINEL-EXECUTED"
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader())     # no hook: the real call path
            d.outdir.mkdir()
            d.verify()
            guard.write_text(f"#!/bin/bash\ntouch {marker}\nexit 0\n")                                      # replaced after verify()
            with mock.patch.object(drv.subprocess, "run") as run:
                with self.assertRaises(drv.Stop) as cm:
                    d.do_guard("x", False)
            self.assertIn("guard script differs from the pin", str(cm.exception))
            run.assert_not_called()
            self.assertFalse(marker.exists())
            # and with the real subprocess: the sentinel still never executes
            with self.assertRaises(drv.Stop):
                d.do_guard("y", False)
            self.assertFalse(marker.exists(), "the sentinel guard must not have been executed")

    def test_the_verified_bytes_are_the_executed_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            w, guard = self.world_with_private_guard(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader())
            d.outdir.mkdir()
            d.verify()
            seen = {}
            def fake_run(cmd, env=None, **kw):
                seen["cmd"], seen["env"] = cmd, env
                return subprocess.CompletedProcess(cmd, 0, "guard ok\n", "")
            with mock.patch.object(drv.subprocess, "run", fake_run):
                d.do_guard("lab", True)
            self.assertEqual(seen["cmd"][:2], ["bash", "-c"])
            self.assertEqual(hashlib.sha256(seen["cmd"][2].encode()).hexdigest(), w.pins["guard"]["sha256"])
            self.assertEqual(seen["cmd"][3:], ["stageC_guard.sh", "lab", "1"])
            self.assertEqual(seen["env"]["STAGEC_REAL"], "0")

    def real_driver(self, t, with_modules=True):
        w = T.World(t)
        pins = dict(w.pins, fake=False, gpu=dict(uuid="GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598", foreign_pid=1))
        pins["guard"] = dict(path=str(HERE / "stageC_guard.sh"), sha256=T.sha(HERE / "stageC_guard.sh"))
        pins["modules"] = {m: T.sha(sys.modules[m].__file__) for m in ("ccf_dc_native_rows", "ccf_dc_tap_field", "check_motion_diagnostics",
                                                                        "check_realistic_motion", "motion_field")}
        pp = w.write_pins("real.json", pins)
        out = Path(t) / "stageC"
        rel = dict(schema="stagec-release/1", test_fixture=False, authorized_by="test-parent", run_id="r-test",
                   driver_sha256=T.sha(drv.__file__), pins_sha256=T.sha(pp), ledger_sha256=pins["ledger"]["sha256"],
                   source_commit=pins["source"]["commit"], outdir=str(out.resolve()))
        rp = Path(t) / "release.json"
        rp.write_text(json.dumps(rel))
        return w, pins, pp, out, rp

    def test_real_run_rehashes_guard_modules_and_driver_before_every_job(self):
        with tempfile.TemporaryDirectory() as t:
            w, pins, pp, out, rp = self.real_driver(t)
            d = drv.Driver(pp, out, release_path=rp)
            d.verify_tools()                                          # unchanged: passes
            for mutate, text in ((lambda: d.pins["guard"].update(sha256="0" * 64), "guard script differs"),
                                 (lambda: d.pins["modules"].update(motion_field="0" * 64), "module motion_field differs"),
                                 (lambda: d.release.update(driver_sha256="0" * 64), "driver file differs")):
                d2 = drv.Driver(pp, out, release_path=rp)
                mutate_target = d2
                if text.startswith("guard"):
                    d2.pins["guard"]["sha256"] = "0" * 64
                elif text.startswith("module"):
                    d2.pins["modules"]["motion_field"] = "0" * 64
                else:
                    d2.release["driver_sha256"] = "0" * 64
                with self.assertRaises(drv.Stop) as cm:
                    d2.verify_tools()
                self.assertIn(text, str(cm.exception))


class ReleaseRecord(unittest.TestCase):
    def test_exact_release_bytes_and_ids_are_copied_into_the_sealed_directory(self):
        with tempfile.TemporaryDirectory() as t:
            w, pins, pp, out, rp = GuardBytes().real_driver(t)
            d = drv.Driver(pp, out, release_path=rp)
            out.mkdir()
            d.record_release()
            res = d.finish("STOPPED", "test seal; no producer ran")
            self.assertEqual((out / "release_copy.json").read_bytes(), rp.read_bytes())
            fs = json.loads((out / "final_status.json").read_text())
            self.assertEqual(fs["release"], dict(sha256=T.sha(rp), run_id="r-test", authorized_by="test-parent", copy="release_copy.json"))
            man = dict(l.split("  ", 1)[::-1] for l in (out / "SHA256SUMS").read_text().splitlines())
            self.assertEqual(man["release_copy.json"], T.sha(rp))
            self.assertNotIn("SHA256SUMS", man)
            self.assertEqual(res["status"], "STOPPED")

    def test_a_dry_run_has_no_release_and_the_record_says_so(self):
        with tempfile.TemporaryDirectory() as t:
            w, d, res = T.run_world(t, guard=early_stop_guard())
            fs = json.loads((d.outdir / "final_status.json").read_text())
            self.assertIsNone(fs["release"])
            self.assertFalse((d.outdir / "release_copy.json").exists())


class ChildEnvironmentRecord(unittest.TestCase):
    def test_receipt_records_the_complete_allowlisted_environment_and_the_policy(self):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            phase, job = d.plan[0]
            with mock.patch.dict(os.environ, dict(LD_LIBRARY_PATH="/nowhere", LD_PRELOAD="/nowhere/x.so", MC_EXPERIMENT_CCF_DC_ARM="both")):
                d.run_job(phase, job)
            d.release_locks()
            rec = json.loads((d.outdir / "runs" / job["job_id"] / "receipt.json").read_text())
            passed = rec["env_passed"]
            self.assertTrue(set(passed) <= set(drv.ENV_ALLOW) | set(rec["env_declared"]) | {"FAKE_CONTROL"})
            for k in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "USER", "LOGNAME"):
                if k in os.environ:
                    self.assertEqual(passed[k], os.environ[k], k)
            for k in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
                self.assertNotIn(k, passed)
                self.assertIn(k, rec["env_dropped_names"])
            # the inherited arm ("both") is dropped; the child carries only the arm the ledger row declares
            self.assertIn("MC_EXPERIMENT_CCF_DC_ARM", rec["env_dropped_names"])
            self.assertEqual(passed["MC_EXPERIMENT_CCF_DC_ARM"], rec["env_declared"]["MC_EXPERIMENT_CCF_DC_ARM"])
            self.assertNotEqual(passed["MC_EXPERIMENT_CCF_DC_ARM"], "both")
            self.assertIn("LD_LIBRARY_PATH", rec["env_policy"])
            self.assertIn("full environment", rec["env_policy"])
            if LINUX:
                ident = rec["sampling"].get("identity_first_sample")
                if ident:            # a very short child may end before the first sample; then the status says so
                    self.assertTrue(ident["cmdline_matches_argv"] or "cmdline_error" in ident)
                    self.assertIn("environ_sha256", ident)

    def test_default_spawner_documents_what_it_is(self):
        self.assertIn("not\nindependent proof from the operating system", drv.__doc__)


class LddPreflight(unittest.TestCase):
    SCRIPT = HERE / "stageC_ldd_preflight.sh"

    def run_script(self, t, ldd_body, env_extra=None, binaries=1):
        shim = Path(t) / "shim"
        shim.mkdir()
        (shim / "ldd").write_text("#!/bin/bash\n" + ldd_body)
        (shim / "ldd").chmod(0o755)
        bins = []
        for i in range(binaries):
            b = Path(t) / f"bin{i}"
            b.write_text("x")
            bins.append(str(b))
        env = dict(PATH=f"{shim}:{os.environ['PATH']}", HOME=t, LANG="C")
        env.update(env_extra or {})
        return subprocess.run(["bash", str(self.SCRIPT), *bins], env=env, capture_output=True, text=True, timeout=60)

    GOOD = 'echo "\\tlibm.so.6 => /lib/libm.so.6 (0x1)"\necho "\\tlibc.so.6 => /lib/libc.so.6 (0x2)"\n'

    def test_match_differ_and_failures(self):
        with tempfile.TemporaryDirectory() as t:
            r = self.run_script(t, self.GOOD)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("LDD_MATCH", r.stdout)
        with tempfile.TemporaryDirectory() as t:       # the full environment resolves differently (LD_LIBRARY_PATH), the scrubbed one does not
            body = 'if [ -n "${LD_LIBRARY_PATH:-}" ]; then echo "\\tlibm.so.6 => /opt/other/libm.so.6 (0x1)"; else echo "\\tlibm.so.6 => /lib/libm.so.6 (0x1)"; fi\n'
            r = self.run_script(t, body, env_extra=dict(LD_LIBRARY_PATH="/opt/other"))
            self.assertEqual(r.returncode, 17, r.stdout + r.stderr)
            self.assertIn("LDD_DIFFERS", r.stdout)
        with tempfile.TemporaryDirectory() as t:
            r = self.run_script(t, "exit 1\n")
            self.assertEqual(r.returncode, 14)
        with tempfile.TemporaryDirectory() as t:
            r = self.run_script(t, 'echo "\\tlibcufft.so.11 => not found"\n')
            self.assertEqual(r.returncode, 15)
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(["bash", str(self.SCRIPT)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 14)


class EvidenceManifestCounts(unittest.TestCase):
    """F7: the original amend1_window/SHA256SUMS lists itself; the counts are recorded, the v2 manifest is closed."""
    D = DOCS / "evidence/stageC/amend1_window"

    @staticmethod
    def check(manifest, base):
        ok, bad = 0, []
        for line in manifest.read_text().splitlines():
            h, name = line.split(None, 1)
            p = base / name
            if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == h:
                ok += 1
            else:
                bad.append(name)
        return ok, bad

    def test_original_has_12_ok_and_one_self_listed_failure_and_v2_is_closed(self):
        ok, bad = self.check(self.D / "SHA256SUMS", self.D)
        self.assertEqual((ok, bad), (12, ["./SHA256SUMS"]))
        v2 = self.D / "SHA256SUMS.v2"
        ok2, bad2 = self.check(v2, self.D)
        self.assertEqual(bad2, [])
        self.assertEqual(ok2, 12)
        names = [l.split(None, 1)[1] for l in v2.read_text().splitlines()]
        self.assertNotIn("./SHA256SUMS", names)
        self.assertNotIn("./SHA256SUMS.v2", names)
        self.assertNotIn("./AMENDMENT.md", names)
        self.assertTrue((self.D / "AMENDMENT.md").exists())

    def test_every_manifest_written_by_the_driver_excludes_itself(self):
        with tempfile.TemporaryDirectory() as t:
            w, d, res = T.run_world(t, guard=early_stop_guard())
            names = [l.split("  ", 1)[1] for l in (d.outdir / "SHA256SUMS").read_text().splitlines()]
            self.assertNotIn("SHA256SUMS", names)
            self.assertEqual(self.check_driver(d), (len(names), []))

    @staticmethod
    def check_driver(d):
        ok, bad = 0, []
        for line in (d.outdir / "SHA256SUMS").read_text().splitlines():
            h, name = line.split("  ", 1)
            if hashlib.sha256((d.outdir / name).read_bytes()).hexdigest() == h:
                ok += 1
            else:
                bad.append(name)
        return ok, bad


if __name__ == "__main__":
    unittest.main()
