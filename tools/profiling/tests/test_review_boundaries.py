"""Actual entry-point regressions for the remaining PR165 review findings.

No GPU is needed: payloads are the existing stand-in, GPU ownership is
sampled from a deliberately vanished PID, and overlap uses an nsys database.
"""
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fixture_db
import mcprof
from lib import identity, metrics, nsys_db, provenance as prov, report, runner
from test_discards import runs_for
from test_runner import make_binary, make_data


class Inputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = make_data(os.path.join(self.tmp.name, "data"))
        self.binary = make_binary(os.path.join(self.tmp.name, "binary"))
        self.work = os.path.join(self.tmp.name, "work")
        os.makedirs(self.work)
        # Existing kit work must survive invalid input, including --force.
        with open(os.path.join(self.work, "provenance.json"), "w") as f:
            json.dump({"keep": True}, f)
        self.keep = os.path.join(self.work, "keep.txt")
        with open(self.keep, "w") as f:
            f.write("keep")

    def tearDown(self):
        self.tmp.cleanup()

    def rejected(self, arm="safe", extra=()):
        with open(os.path.join(self.work, "provenance.json"), "w") as f:
            json.dump({"keep": True}, f)
        with open(self.keep, "w") as f:
            f.write("keep")
        argv = ["run", arm + "=" + self.binary, "--data", self.data, "--work", self.work,
                "--force", "--no-lock", "--rounds", "1", "--warmup", "0",
                "--settle-timeout", "0", "--lane-wait", "0", *extra]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                patch.object(runner, "make_sampler", return_value=runner.GpuSampler(None)), \
                patch.object(prov, "gpu_record", return_value={"uuid": "GPU-selected"}):
            try:
                rc = mcprof.main(argv)
            except SystemExit as e:
                rc = e.code
        self.assertNotEqual(rc, 0)
        self.assertTrue(os.path.isfile(self.keep), "invalid input cleared existing work")
        with open(os.path.join(self.work, "provenance.json")) as f:
            self.assertEqual(json.load(f), {"keep": True})

    def test_protected_gpu_environment_is_rejected_before_cleanup(self):
        for key in ("CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"):
            with self.subTest(key=key):
                self.rejected(extra=["--gpu-uuid", "GPU-selected", "--env", key + "=other"])

    def test_unsafe_arm_names_are_rejected_before_cleanup(self):
        for name in ("", os.path.join(self.tmp.name, "absolute-arm"), "../../outside", "a/b", "a\\b",
                     ".", "..", "arm\nname"):
            with self.subTest(name=name):
                self.rejected(arm=name)

    def test_invalid_cpu_lanes_are_rejected_before_cleanup(self):
        for option in ("--cpus", "--runner-cpus"):
            for lane in ("", "119-112", "112,119-112", "1,", "-1", "1-", "a"):
                with self.subTest(option=option, lane=lane):
                    self.rejected(extra=[option, lane])

    def test_valid_names_and_environment_remain_supported(self):
        self.assertEqual(mcprof.parse_arms(["candidate_1.2-rc=" + self.binary]),
                         {"candidate_1.2-rc": self.binary})
        env, changes = runner.payload_env("GPU-selected", ["OMP_NUM_THREADS=4"])
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "GPU-selected")
        self.assertEqual(changes["CUDA_DEVICE_ORDER"], "PCI_BUS_ID")
        self.assertEqual(changes["OMP_NUM_THREADS"], "4")
        self.assertEqual(prov.cpu_list(None), [])
        self.assertEqual(prov.cpu_list("112-115,114,119"), [112, 113, 114, 115, 119])

    def test_run_directory_symlink_cannot_write_or_cleanup_outside_work(self):
        outside = os.path.join(self.tmp.name, "outside")
        os.makedirs(outside)
        sentinel = os.path.join(outside, "keep")
        with open(sentinel, "w") as f:
            f.write("keep")
        runs = os.path.join(self.work, "runs")
        os.makedirs(runs)
        os.symlink(outside, os.path.join(runs, "safe-r01"))
        staged = {"star": "movies.star", "cwd": self.data, "movies": ["a", "b", "c"]}
        with self.assertRaises(ValueError):
            runner.series({"safe": self.binary}, [], staged, self.work, [], None, [], 1, 0,
                          runner.GpuSampler(None), lambda rec: None)
        self.assertEqual(os.listdir(outside), ["keep"])


class UnknownOccupancy(unittest.TestCase):
    def test_run_once_unknown_process_discards_the_complete_pair(self):
        class VanishedSampler(runner.GpuSampler):
            def __init__(self):
                super().__init__("GPU-test")

            def processes(self):
                return []  # Not a separate before-start contamination.

            def baseline(self):
                return 0

            def read(self):
                return 0, [(2147483647, None)]  # No inspectable process identity.

        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"))
            binary = make_binary(os.path.join(tmp, "binary"), {"FAKE_SLEEP": "0.04"})
            out = os.path.join(tmp, "out")
            rec = runner.run_once(runner.payload_argv(binary, [], "movies.star", out, []), data,
                                  dict(os.environ), os.path.join(tmp, "run.log"), VanishedSampler(),
                                  [], binary, out, 3)
        self.assertEqual(rec["vram"]["unclassified_pids"], [2147483647])
        self.assertTrue(any("unclassified GPU" in s for s in rec["flags"]["discard"]))
        rs = runs_for([1.0] * 6, [0.8] * 6)
        rs[1]["flags"] = rec["flags"]
        result = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        self.assertEqual(result["comparisons"]["B"]["n_pairs"], 5)
        self.assertFalse(result["comparisons"]["B"]["resolved"])
        self.assertTrue(rs[0]["discarded"] and rs[1]["discarded"])


class KernelCopyOverlap(unittest.TestCase):
    def analyze(self, kernels, copies, memsets):
        def populate(con, insert):
            for table in ("KERNEL", "MEMCPY", "MEMSET"):
                con.execute("delete from CUPTI_ACTIVITY_KIND_" + table)
            for s, e in kernels:
                insert(con, "CUPTI_ACTIVITY_KIND_KERNEL", start=s, end=e, shortName=1, demangledName=9,
                       streamId=7, deviceId=0)
            for s, e in copies:
                insert(con, "CUPTI_ACTIVITY_KIND_MEMCPY", start=s, end=e, bytes=1, copyKind=1,
                       srcKind=0, dstKind=2, streamId=8)
            for s, e in memsets:
                insert(con, "CUPTI_ACTIVITY_KIND_MEMSET", start=s, end=e, bytes=1, streamId=9)
        with tempfile.TemporaryDirectory() as tmp:
            path = fixture_db.build(os.path.join(tmp, "trace.sqlite"), extra=populate)
            db = nsys_db.NsysDB(path)
            try:
                return metrics.analyze(db)["totals"]
            finally:
                db.close()

    def test_memset_without_copy_is_not_kernel_copy_overlap(self):
        got = self.analyze([(100, 300)], [], [(200, 400)])
        self.assertEqual(got["overlap_ns"], 0)
        self.assertEqual(got["busy_ns"], 300)

    def test_three_way_overlap_counts_kernel_copy_intersection_once(self):
        got = self.analyze([(100, 300), (150, 250)], [(200, 400)], [(150, 350)])
        self.assertEqual(got["overlap_ns"], 100)
        self.assertEqual(got["busy_ns"], 300)


class MrcLabels(unittest.TestCase):
    def compare(self, label_a, label_b, mutation=None, nlabl=1):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [os.path.join(tmp, side + ".mrc") for side in ("a", "b")]
            for i, (path, label) in enumerate(zip(paths, (label_a, label_b))):
                hdr = bytearray(1024)
                struct.pack_into("<i", hdr, 92, 4)
                struct.pack_into("<i", hdr, 220, nlabl)
                hdr[224:224 + len(label)] = label
                if i and mutation:
                    mutation(hdr)
                with open(path, "wb") as f:
                    f.write(hdr + b"EXT!" + b"payload")
            return identity.compare_mrc(*paths)

    def test_only_known_relion_writer_time_is_normalised(self):
        self.assertIsNone(self.compare(b"Relion 5.0.1   01-Jan-26  00:00:00",
                                       b"Relion 5.0.1   02-Feb-26  11:11:11"))

    def test_relion_version_is_compared(self):
        self.assertIsNotNone(self.compare(b"Relion 5.0.1   01-Jan-26  00:00:00",
                                          b"Relion 5.0.2   01-Jan-26  00:00:00"))

    def test_unknown_timestamp_label_is_compared(self):
        self.assertIsNotNone(self.compare(b"Dose 01-Jan-26  00:00:00", b"Dose 02-Feb-26  11:11:11"))

    def test_timestamp_in_an_unused_or_later_label_is_compared(self):
        label_a = b"Relion 5.0.1   01-Jan-26  00:00:00"
        label_b = b"Relion 5.0.1   02-Feb-26  11:11:11"
        self.assertIsNotNone(self.compare(label_a, label_b, nlabl=0))
        self.assertIsNotNone(self.compare(label_a, label_a,
                                          lambda h: h.__setitem__(slice(304, 304 + len(label_b)), label_b)))

    def test_each_label_and_reserved_byte_is_compared(self):
        label = b"Relion 5.0.1   01-Jan-26  00:00:00"
        for offset in (270, 303, 304, 383, 1023):
            with self.subTest(offset=offset):
                self.assertIsNotNone(self.compare(label, label, lambda h: h.__setitem__(offset, 1)))


if __name__ == "__main__":
    unittest.main()
