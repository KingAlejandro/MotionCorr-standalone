#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fake-child controls for the Stage C driver's per-row process record and child-group lifecycle (amendment 1).

Only fake children (small Python scripts); no MotionCorr child, no GPU. Linux-only assertions run where /proc exists; elsewhere the
record must say UNOBSERVED honestly. Local use: at most two threads, a few MB of scratch.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ccf_dc_stagec_driver as drv          # noqa: E402
import test_ccf_dc_stagec_driver as T       # noqa: E402

LINUX = sys.platform.startswith("linux") and os.path.exists("/proc/self/status")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                   # a zombie is not alive for this purpose
        return open(f"/proc/{pid}/stat").read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def wait_dead(pids, seconds=6.0):
    end = time.time() + seconds
    while time.time() < end and any(alive(p) for p in pids):
        time.sleep(0.05)
    return [p for p in pids if alive(p)]


CHILD = r'''
import os, subprocess, sys, threading, time
mode, pidfile = sys.argv[1], sys.argv[2]
gc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(%d)" % (1 if mode == "short" else 60)])
threading.Thread(target=lambda: time.sleep(60), daemon=True).start()
open(pidfile, "w").write("%d %d" % (os.getpid(), gc.pid))
if mode != "orphan":
    time.sleep(1.6 if mode == "short" else 60)
'''


class Spawner(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.t = Path(self._t.name)
        self.child = self.t / "child.py"
        self.child.write_text(CHILD)

    def spawn(self, mode, timeout=30, env=None):
        run = self.t / f"run-{mode}-{len(list(self.t.iterdir()))}"
        run.mkdir()
        return run, drv.default_spawner([sys.executable, str(self.child), mode, str(self.t / "pids")], str(self.t),
                                        dict(os.environ, **(env or {})), str(run / "stdout.txt"), str(run / "stderr.txt"), timeout)

    def pids(self):
        return [int(x) for x in (self.t / "pids").read_text().split()]

    def test_sampling_records_a_child_and_its_descendant(self):
        run, res = self.spawn("short")
        rc, argv, env, summ = res
        self.assertEqual(rc, 0)
        lines = (run / "procsamples.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), summ["samples"])
        if LINUX:
            self.assertEqual(summ["status"], "OBSERVED")
            self.assertGreaterEqual(summ["samples"], 2)
            self.assertGreaterEqual(summ["max_tree_pids"], 2, "child and grandchild")
            self.assertGreaterEqual(summ["max_threads_total"], 3, "two threads in the child, one in the grandchild")
            self.assertTrue(summ["cpus_allowed_lists"])
            self.assertTrue(any("python" in n.lower() for n in summ["names"]))
            first = json.loads(lines[0])
            self.assertTrue(first["pids"] and {"pid", "ppid", "name", "state", "threads", "tasks", "cpus_allowed", "utime", "stime"} <= set(first["pids"][0]))
        else:
            self.assertTrue(summ["status"].startswith("UNOBSERVED"), summ)
            self.assertEqual(summ["samples"], 0)
        self.assertFalse(summ["stragglers_killed"])
        self.assertEqual(wait_dead(self.pids()), [])

    def test_a_child_that_ends_at_once_is_not_given_invented_numbers(self):
        run = self.t / "fast"
        run.mkdir()
        rc, argv, env, summ = drv.default_spawner([sys.executable, "-c", "pass"], str(self.t), dict(os.environ), str(run / "o"), str(run / "e"), 30)
        self.assertEqual(rc, 0)
        if summ["status"] == "OBSERVED":
            self.assertGreaterEqual(summ["max_tree_pids"], 1)
        else:
            self.assertTrue(summ["status"].startswith("UNOBSERVED"))
            self.assertNotIn("max_threads_total", summ)
            self.assertNotIn("max_tree_pids", summ)

    def test_a_straggler_left_in_the_group_is_killed_and_recorded(self):
        run, res = self.spawn("orphan")
        self.assertEqual(res[0], 0)
        self.assertTrue(res[3]["stragglers_killed"], "the grandchild outlived the child and had to be killed")
        self.assertEqual(wait_dead(self.pids()), [])

    def test_sample_truncation_is_recorded(self):
        with mock.patch.object(drv, "MAX_SAMPLES", 2), mock.patch.object(drv, "SAMPLE_PERIOD_S", 0.1):
            run, res = self.spawn("short")
        summ = res[3]
        if LINUX:
            self.assertEqual(summ["samples"], 2)
            self.assertTrue(summ["truncated"])

    def test_timeout_kills_the_whole_group(self):
        t0 = time.time()
        run, res = self.spawn("long", timeout=3.0)
        self.assertEqual(res[0], 124)
        self.assertLess(time.time() - t0, 20)
        self.assertEqual(wait_dead(self.pids()), [], "child and grandchild must be gone after the timeout")
        self.assertTrue((run / "procsamples.jsonl").exists())

    def test_keyboard_interrupt_and_other_exceptions_clean_up_and_propagate(self):
        for exc, label in ((KeyboardInterrupt, "kbd"), (RuntimeError, "rt")):
            pidfile = self.t / "pids"
            if pidfile.exists():
                pidfile.unlink()
            def handler(signum, frame, exc=exc):
                raise exc("test interrupt")
            old = signal.signal(signal.SIGALRM, handler)
            try:
                signal.setitimer(signal.ITIMER_REAL, 3.0)
                with self.assertRaises(exc):
                    self.spawn("long")
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)
            self.assertEqual(wait_dead(self.pids()), [], f"{label}: no child may outlive the interrupted spawner")
            runs = sorted(p for p in self.t.iterdir() if p.name.startswith("run-long"))
            self.assertTrue((runs[-1] / "procsamples.jsonl").exists(), "partial samples are kept")


class DriverLifecycle(unittest.TestCase):
    def test_spawner_exception_is_a_stop_with_the_exception_text(self):
        def boom(*a):
            raise RuntimeError("boom")
        with tempfile.TemporaryDirectory() as t:
            w, d, res = T.run_world(t, spawner=boom)
            self.assertEqual(res["status"], "STOPPED")
            self.assertIn("RuntimeError during the child run: boom", res["reason"])
            first = next((d.outdir / "runs").iterdir())
            rec = json.loads((first / "receipt.json").read_text())
            self.assertIn("RuntimeError: boom", rec["interrupted"])
            self.assertTrue((d.outdir / "SHA256SUMS").exists())

    def test_unexpected_driver_exception_is_recorded_not_a_crash(self):
        def bad_guard(label, need_gpu):
            raise ValueError("guard hook failed")
        with tempfile.TemporaryDirectory() as t:
            w, d, res = T.run_world(t, guard=bad_guard)
            self.assertEqual(res["status"], "STOPPED")
            self.assertIn("unexpected ValueError", res["reason"])
            self.assertTrue((d.outdir / "final_status.json").exists())

    def test_sigterm_stops_cleanly_kills_the_child_and_releases_the_leases(self):
        import fcntl
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t, control={"exp|cuda|affine|none": "sleep"})
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD)
            timer = threading.Timer(1.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
            timer.start()
            try:
                res = d.execute()
            finally:
                timer.cancel()
            self.assertEqual(res["status"], "STOPPED", res)
            self.assertIn("Terminated", res["reason"])
            pidfile = next((d.outdir / "runs").glob("*/out/pid"))
            self.assertEqual(wait_dead([int(pidfile.read_text())]), [], "the fake child must be gone")
            self.assertEqual(json.loads(next((d.outdir / "runs").glob("*/receipt.json")).read_text())["rc"], None)
            self.assertTrue((d.outdir / "SHA256SUMS").exists())
            for name in ("own", "cpu", "gpu2"):                     # leases are released only after the cleanup
                fd = os.open(w.pins["locks"][name], os.O_RDWR)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(fd)
            self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL, "the previous SIGTERM handler is restored")

    def test_row_receipt_carries_the_sampling_record(self):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            phase, job = d.plan[0]
            d.run_job(phase, job)
            d.release_locks()
            run = d.outdir / "runs" / job["job_id"]
            rec = json.loads((run / "receipt.json").read_text())
            self.assertIn("status", rec["sampling"])
            self.assertTrue((run / "procsamples.jsonl").exists())
            if not LINUX:
                self.assertTrue(rec["sampling"]["status"].startswith("UNOBSERVED"))

    def test_a_spawner_without_sampling_is_recorded_unobserved(self):
        def plain(argv, cwd, env, so, se, timeout):
            return drv.default_spawner(argv, cwd, env, so, se, timeout)[:3]
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            d = drv.Driver(w.write_pins(), Path(t) / "out", dry_run=True, grader=T.make_fake_grader(), guard=T.OK_GUARD, spawner=plain)
            d.outdir.mkdir()
            d.verify()
            d.acquire(["own"])
            phase, job = d.plan[0]
            d.run_job(phase, job)
            d.release_locks()
            rec = json.loads((d.outdir / "runs" / job["job_id"] / "receipt.json").read_text())
            self.assertTrue(rec["sampling"]["status"].startswith("UNOBSERVED: the spawner returned no sampling record"))


class RealEntryRejectsTestHooks(unittest.TestCase):
    def test_real_driver_refuses_a_test_hook_environment_and_guard_gets_the_real_flag(self):
        with tempfile.TemporaryDirectory() as t:
            w = T.World(t)
            pins = dict(w.pins, fake=False, gpu=dict(uuid="GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598", foreign_pid=1))
            pp = w.write_pins("real.json", pins)
            out = Path(t) / "stageC"
            rel = dict(schema="stagec-release/1", test_fixture=False, authorized_by="test-parent", run_id="r",
                       driver_sha256=T.sha(drv.__file__), pins_sha256=T.sha(pp), ledger_sha256=pins["ledger"]["sha256"],
                       source_commit=pins["source"]["commit"], outdir=str(out.resolve()))
            rp = Path(t) / "rel.json"
            rp.write_text(json.dumps(rel))
            with mock.patch.dict(os.environ, {"STAGEC_TEST_MODE": "1"}):
                with self.assertRaises(drv.Stop) as cm:
                    drv.Driver(pp, out, release_path=rp)
                self.assertIn("test hook", str(cm.exception))
            d = drv.Driver(pp, out, release_path=rp)                  # without the hook it constructs
            out.mkdir()
            seen = {}
            def fake_run(cmd, env=None, **kw):
                seen["cmd"], seen["env"] = cmd, env
                return subprocess.CompletedProcess(cmd, 0, "guard ok\n", "")
            with mock.patch.object(drv.subprocess, "run", fake_run):
                d.do_guard("x", True)
            self.assertEqual(seen["env"]["STAGEC_REAL"], "1")
            self.assertFalse([k for k in seen["env"] if k.startswith("STAGEC_TEST_")])
            # amendment 2 (F3): the pinned bytes are hashed and executed as `bash -c <text>`, not re-read from the path by bash
            self.assertEqual(seen["cmd"][:2], ["bash", "-c"])
            self.assertEqual(hashlib.sha256(seen["cmd"][2].encode()).hexdigest(), pins["guard"]["sha256"])
            self.assertEqual(seen["cmd"][3:], ["stageC_guard.sh", "x", "1"])


if __name__ == "__main__":
    unittest.main()
