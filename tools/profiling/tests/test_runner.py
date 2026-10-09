"""lib/runner.py and lib/provenance.py without a GPU: staging, scheduling,
resource capture from wait4, failure handling and the shared-host lock."""
import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from lib import provenance as prov, runner  # noqa: E402

FAKE = os.path.join(HERE, "fake_motioncorr.py")
STAR = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
opticsGroup1 1

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
Movies/a.tiff 1
Movies/b.tiff 1
Movies/c.tiff 1
"""


def make_data(root):
    os.makedirs(os.path.join(root, "Movies"))
    for n in "abc":
        open(os.path.join(root, "Movies", n + ".tiff"), "w").close()
    with open(os.path.join(root, "movies.star"), "w") as f:
        f.write(STAR)
    return root


def make_binary(path, env=None):
    """Executable wrapper around fake_motioncorr.py with fixed behaviour."""
    lines = ["#!/bin/sh", "# stand-in motioncorr; accepts --profile"]
    lines += ["export %s=%s" % kv for kv in (env or {}).items()]
    lines.append('exec "%s" "%s" "$@"' % (sys.executable, FAKE))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class Staging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = make_data(os.path.join(self.tmp, "data"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_star_movies_reads_movie_block_only(self):
        movies, rows = runner.star_movies(os.path.join(self.data, "movies.star"))
        self.assertEqual(movies, ["Movies/a.tiff", "Movies/b.tiff", "Movies/c.tiff"])

    def test_subset_keeps_header_and_links(self):
        s = runner.stage_input(self.data, "movies.star", 2, os.path.join(self.tmp, "w"))
        self.assertTrue(s["staged"])
        self.assertEqual(s["movies"], ["Movies/a.tiff", "Movies/b.tiff"])
        text = open(os.path.join(s["cwd"], "movies.star")).read()
        self.assertIn("opticsGroup1 1", text)
        self.assertNotIn("c.tiff", text)
        self.assertTrue(os.path.exists(os.path.join(s["cwd"], "Movies", "c.tiff")))

    def test_full_set_uses_data_dir(self):
        s = runner.stage_input(self.data, "movies.star", None, os.path.join(self.tmp, "w"))
        self.assertEqual(s["cwd"], os.path.abspath(self.data))
        self.assertFalse(s["staged"])


class Scheduling(unittest.TestCase):
    def test_two_arms_alternate(self):
        self.assertEqual(runner.schedule(["A", "B"], 4), [["A", "B"], ["B", "A"], ["A", "B"], ["B", "A"]])
        self.assertEqual(runner.order_label(["A", "B"], ["B", "A"]), "BA")

    def test_three_arms_rotate_through_every_position(self):
        sched = runner.schedule(["A", "B", "C"], 3)
        for arm in "ABC":
            self.assertEqual(sorted(r.index(arm) for r in sched), [0, 1, 2])

    def test_kit_owns_io_flags(self):
        with self.assertRaises(ValueError):
            runner.payload_argv("/bin/x", ["--o", "y"], "s.star", "/out", [])

    def test_cpu_list(self):
        self.assertEqual(prov.cpu_list("96-99,101"), [96, 97, 98, 99, 101])


class RunOnce(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = make_data(os.path.join(self.tmp, "data"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_fake(self, env):
        b = make_binary(os.path.join(self.tmp, "mc"), env)
        out = os.path.join(self.tmp, "run", "out")
        argv = runner.payload_argv(b, ["--gpu", "0"], "movies.star", out, [])
        return runner.run_once(argv, self.data, dict(os.environ), os.path.join(self.tmp, "run.log"),
                               runner.GpuSampler(None), [], b, out, 3)

    def test_wall_cpu_rss_products(self):
        rec = self.run_fake({"FAKE_SLEEP": "0.2"})
        self.assertGreaterEqual(rec["wall_s"], 0.2)
        self.assertLess(rec["wall_s"], 5)
        self.assertGreater(rec["peak_rss_bytes"], 1 << 20)   # a Python interpreter, from wait4
        self.assertGreater(rec["cpu_s"], 0)
        self.assertEqual(rec["mrc_products"], 3)
        self.assertEqual(rec["flags"]["discard"], [])

    def test_failure_raises(self):
        with self.assertRaisesRegex(RuntimeError, "exited 3"):
            self.run_fake({"FAKE_FAIL": "1"})

    def test_lane_foreign_cpu_discards(self):
        rec = {"lane": {"foreign_cores": 1.5}, "payload_affinity": None}
        self.assertTrue(any("foreign CPU" in f for f in runner.run_flags(rec, [1, 2])["discard"]))
        rec = {"vram": {"foreign_pids": {123: 0}, "own_pids_seen": []}}
        self.assertTrue(any("foreign process" in f for f in runner.run_flags(rec, [])["discard"]))


class QuietLane(unittest.TestCase):
    def test_waits_then_times_out(self):
        real = runner.lane_busy_cores
        try:
            seq = iter([1.0, 0.9, 0.1])
            runner.lane_busy_cores = lambda lane, window_s=1.0: next(seq)
            q = runner.wait_quiet_lane([1], timeout_s=60)
            self.assertEqual(q["busy_cores"], 0.1)
            self.assertNotIn("timed_out", q)
            runner.lane_busy_cores = lambda lane, window_s=1.0: 1.0
            self.assertTrue(runner.wait_quiet_lane([1], timeout_s=-1)["timed_out"])
        finally:
            runner.lane_busy_cores = real


class Locks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "bench.lock")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_exclusive_and_released(self):
        with prov.HostLock(self.path) as a:
            self.assertIsNotNone(a.fd)
            t0 = time.monotonic()
            with self.assertRaises(prov.LockError):
                with prov.HostLock(self.path, timeout_s=0.2, poll_s=0.05):
                    pass
            self.assertGreaterEqual(time.monotonic() - t0, 0.2)
        with prov.HostLock(self.path, timeout_s=0.2):
            pass
        self.assertTrue(os.path.exists(self.path))   # never deleted

    def test_not_inherited(self):
        with prov.HostLock(self.path) as a:
            self.assertFalse(os.get_inheritable(a.fd))

    def test_unlinked_lock_detected(self):
        real_stat = os.stat
        try:
            os.stat = lambda p, *a, **k: (_ for _ in ()).throw(FileNotFoundError(p)) if p == self.path else real_stat(p, *a, **k)
            with self.assertRaisesRegex(prov.LockError, "unlinked or replaced"):
                with prov.HostLock(self.path):
                    pass
        finally:
            os.stat = real_stat


if __name__ == "__main__":
    unittest.main()
