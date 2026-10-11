"""Actual CLI/sampler controls for the last PR165 input and occupancy findings."""
import ctypes
import io
import json
import os
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
from lib import provenance as prov, report, runner
from test_cli import FAKE_NSYS
from test_discards import runs_for
from test_runner import make_binary, make_data


class ForcedInputPreflight(unittest.TestCase):
    def rejected(self, extra=(), contents=None):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"))
            binary = make_binary(os.path.join(tmp, "binary"))
            if contents is not None:
                with open(os.path.join(data, "movies.star"), "w") as f:
                    f.write(contents)
            work = os.path.join(tmp, "work")
            os.mkdir(work)
            old = {"provenance.json": b'{"retained": true}', "runs.jsonl": b"old raw results\n"}
            for name, value in old.items():
                with open(os.path.join(work, name), "wb") as f:
                    f.write(value)
            argv = ["run", "A=" + binary, "--data", data, "--work", work, "--force", "--no-lock",
                    "--rounds", "1", "--warmup", "0", "--lane-wait", "0", *extra]
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    rc = mcprof.main(argv)
                except (SystemExit, OSError, ValueError, IndexError) as e:
                    rc = getattr(e, "code", 1)
            self.assertNotEqual(rc, 0)
            self.assertEqual(sorted(os.listdir(work)), sorted(old), "invalid input cleared old evidence")
            for name, value in old.items():
                with open(os.path.join(work, name), "rb") as f:
                    self.assertEqual(f.read(), value)

    def test_escaping_or_missing_star_preserves_forced_work(self):
        for star in ("../movies.star", "/movies.star", "missing.star"):
            with self.subTest(star=star):
                self.rejected(["--star", star])

    def test_empty_or_short_star_preserves_forced_work(self):
        for contents in ("data_movies\nloop_\n_rlnMicrographMovieName #1\n",
                         "data_movies\nloop_\n_rlnOpticsGroup #1\n_rlnMicrographMovieName #2\n1\n"):
            with self.subTest(contents=contents):
                self.rejected(contents=contents)

    def test_nonpositive_movie_counts_preserve_forced_work(self):
        for count in ("-1", "0"):
            with self.subTest(count=count):
                self.rejected(["--movies", count])

    def test_library_staging_rejects_nonpositive_movie_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"))
            for count in (-1, 0):
                with self.subTest(count=count), self.assertRaisesRegex(ValueError, "--movies must be positive"):
                    runner.stage_input(data, "movies.star", count, os.path.join(tmp, "work%d" % count))
                self.assertFalse(os.path.exists(os.path.join(tmp, "work%d" % count)))
            staged = runner.stage_input(data, "movies.star", 2, os.path.join(tmp, "valid"))
            self.assertEqual(staged["movies"], ["Movies/a.tiff", "Movies/b.tiff"])


def nvml_sampler(status=7):
    """Exercise real NvmlSampler.read without loading NVIDIA's library."""
    sampler = runner.NvmlSampler.__new__(runner.NvmlSampler)
    runner.GpuSampler.__init__(sampler, "GPU-fixture")
    sampler.handle = ctypes.c_void_p()

    class Lib:
        def nvmlDeviceGetMemoryInfo(self, handle, mem):
            ctypes.cast(mem, ctypes.POINTER(runner._NvmlMem)).contents.used = 1234
            return 0

    def get_procs(handle, count, arr):
        ctypes.cast(count, ctypes.POINTER(ctypes.c_uint)).contents.value = 65 if status == 7 else 0
        return status

    sampler.lib = Lib()
    sampler._get_procs = get_procs
    return sampler


class OccupancyQueryFailures(unittest.TestCase):
    def test_nvml_enumeration_failure_cannot_settle_as_idle(self):
        for status in (7, 999):  # insufficient-size and an arbitrary query error
            with self.subTest(status=status), patch.object(prov, "compilers_running", return_value=[]):
                with self.assertRaisesRegex(RuntimeError, "NVML process enumeration failed"):
                    runner.settle(nvml_sampler(status), 0)

    def test_nvml_enumeration_failure_prevents_payload_launch(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(runner.subprocess, "Popen", side_effect=AssertionError("payload must not launch")) as launch:
            with self.assertRaisesRegex(RuntimeError, "NVML process enumeration failed"):
                runner.run_once(["never-launch"], tmp, {}, os.path.join(tmp, "run.log"), nvml_sampler(),
                                [], "never-launch", os.path.join(tmp, "out"), 1)
            launch.assert_not_called()

    def test_successful_empty_nvml_inventory_still_settles(self):
        with patch.object(prov, "compilers_running", return_value=[]):
            self.assertTrue(runner.settle(nvml_sampler(0), 0)["settled"])

    def test_nvml_success_with_invalid_buffer_count_is_rejected(self):
        sampler = nvml_sampler(0)

        def over_capacity(handle, count, arr):
            ctypes.cast(count, ctypes.POINTER(ctypes.c_uint)).contents.value = 65
            return 0

        sampler._get_procs = over_capacity
        with self.assertRaisesRegex(RuntimeError, "NVML process enumeration failed"):
            sampler.read()

    def test_successful_nvml_inventory_keeps_all_processes(self):
        sampler = nvml_sampler(0)

        def occupied(handle, count, arr):
            ctypes.cast(count, ctypes.POINTER(ctypes.c_uint)).contents.value = 2
            arr[0].pid, arr[0].usedGpuMemory = 42, 100
            arr[1].pid, arr[1].usedGpuMemory = 43, runner.NVML_NA
            return 0

        sampler._get_procs = occupied
        self.assertEqual(sampler.read(), (1234, [(42, 100), (43, None)]))

    def test_smi_enumeration_failure_cannot_settle_as_idle(self):
        sampler = runner.SmiSampler.__new__(runner.SmiSampler)
        runner.GpuSampler.__init__(sampler, "GPU-fixture")
        sampler.smi = "nvidia-smi-fixture"
        with patch.object(prov, "run_text", side_effect=[(0, "0\n"), (1, "query failed")]), \
                patch.object(prov, "compilers_running", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "nvidia-smi process enumeration failed"):
                runner.settle(sampler, 0)

    def test_smi_malformed_inventory_cannot_settle_as_idle(self):
        sampler = runner.SmiSampler.__new__(runner.SmiSampler)
        runner.GpuSampler.__init__(sampler, "GPU-fixture")
        sampler.smi = "nvidia-smi-fixture"
        with patch.object(prov, "run_text", side_effect=[(0, "0\n"), (0, "unreadable inventory\n")]), \
                patch.object(prov, "compilers_running", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "nvidia-smi process enumeration failed"):
                runner.settle(sampler, 0)

    def test_sampled_nvml_error_discards_the_actual_run_and_whole_pair(self):
        sampler = nvml_sampler()
        # Only during-run enumeration fails: successful preflight is separate.
        sampler.processes = lambda: []
        sampler.baseline = lambda: 0
        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"))
            binary = make_binary(os.path.join(tmp, "binary"), {"FAKE_SLEEP": "0.03"})
            out = os.path.join(tmp, "out")
            rec = runner.run_once(runner.payload_argv(binary, [], "movies.star", out, []), data,
                                  dict(os.environ), os.path.join(tmp, "run.log"), sampler, [], binary, out, 3)
        self.assertGreater(rec["vram"]["read_errors"], 0)
        self.assertTrue(any("GPU occupancy read failed" in x for x in rec["flags"]["discard"]))
        runs = runs_for([1.0] * 6, [0.8] * 6)
        runs[1]["flags"] = rec["flags"]
        result = report.derive_runs({"arms": ["A", "B"], "runs": runs})
        self.assertEqual(result["comparisons"]["B"]["n_pairs"], 5)
        self.assertFalse(result["comparisons"]["B"]["resolved"])
        self.assertTrue(runs[0]["discarded"] and runs[1]["discarded"])


class TraceReadErrors(unittest.TestCase):
    def trace(self, compare):
        sampler = nvml_sampler()
        sampler.processes = lambda: []
        sampler.baseline = lambda: 0
        with tempfile.TemporaryDirectory() as tmp:
            data = make_data(os.path.join(tmp, "data"))
            binary = make_binary(os.path.join(tmp, "binary"), {"FAKE_SLEEP": "0.03"})
            nsys = os.path.join(tmp, "nsys")
            with open(nsys, "w") as f:
                f.write(FAKE_NSYS % {"py": sys.executable})
            os.chmod(nsys, 0o755)
            db = fixture_db.build(os.path.join(tmp, "f.sqlite"))
            work = os.path.join(tmp, "work")
            args = ["compare", "A=" + binary, "B=" + binary] if compare else ["trace", "A=" + binary]
            args += ["--data", data, "--work", work, "--no-lock", "--settle-timeout", "0", "--nsys", nsys]
            if compare:
                args += ["--pairs", "1", "--warmup", "0", "--lane-wait", "0", "--trace-pass", "1"]
            with patch.dict(os.environ, {"FAKE_NSYS_SQLITE": db}), \
                    patch.object(runner, "make_sampler", return_value=sampler), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(mcprof.main(args), 0)
            with open(os.path.join(work, "report.md")) as f:
                md = f.read()
            if compare:
                with open(os.path.join(work, "provenance.json")) as f:
                    p = json.load(f)
                self.assertTrue(all(x["contaminated"] and x["during"]["errors"] > 0 for x in p["trace_occupancy"]))
                for arm in ("A", "B"):
                    self.assertTrue(os.path.isfile(os.path.join(work, "trace", arm, "p01", "CONTAMINATED")))
                with open(os.path.join(work, "compare.json")) as f:
                    self.assertNotIn("device_deltas", json.load(f))
            else:
                self.assertTrue(os.path.isfile(os.path.join(work, "CONTAMINATED")))
                self.assertIn("WARNING: contaminated trace", md)
                self.assertIn("occupancy could not be read", md)

    def test_comparison_trace_read_errors_are_excluded(self):
        self.trace(True)

    def test_standalone_trace_read_errors_are_reported(self):
        self.trace(False)


if __name__ == "__main__":
    unittest.main()
