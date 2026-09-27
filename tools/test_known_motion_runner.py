#!/usr/bin/env python3
"""Exercise the actual launcher with a small controlled executable and real checker."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_known_motion_verdicts as controls

RUNNER = Path(__file__).with_name("run_known_motion_gates.py").resolve()


class RunnerControls(unittest.TestCase):
    def setUp(self):
        controls.VerdictControls.setUp(self)
        gt = json.loads(self.truth.read_text())
        gt.update({"input_star": "still.star", "movie_file": "movie.mrcs",
                   "recommended_run": {"patch_x": 1, "patch_y": 1, "bin_factor": 1,
                                       "skip_defect": True, "expected_hot_pixels_detected": 0,
                                       "role": "gate"}, "defects": {"n_hot_pixels": 0}})
        gt["geometry"].update({"dose_per_frame": 1.0, "voltage_kv": 300})
        self.truth = self.work / "still_ground_truth.json"
        self.truth.write_text(json.dumps(gt))
        self.binary = self.work / "fake-motioncorr"
        # This fixture executable deliberately does not estimate motion. It controls
        # process/backend/output evidence so launcher acceptance can be falsified.
        self.binary.write_text(f"#!{sys.executable}\n" + '''
import os, shutil, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("--o") + 1])
case = Path(args[args.index("--i") + 1]).stem
mode = os.environ.get("KNOWN_MOTION_CONTROL", "ok")
if mode == "characterization_exit" and case == "noisy":
    sys.exit(3)
star = Path("still.star").read_text()
if mode == "thread_difference" and args[args.index("--j") + 1] == "4":
    star = star.replace("2 0.000000000000000e+00", "2 1.000000000000000e-06")
if mode == "malformed_star":
    star = "not a motion STAR"
(out / (case + ".star")).write_text(star)
shutil.copyfile("sum.mrc", out / (case + ".mrc"))
if "--dose_weighting" in args:
    shutil.copyfile("sum.mrc", out / (case + "_noDW.mrc"))
(out / "corrected_micrographs.star").write_text("data_micrographs\\n")
log = "Full movie wall time: 0.01 s\\n"
if "--gpu" in args and mode != "cpu_despite_gpu":
    gpu = args[args.index("--gpu") + 1]
    print("Using CUDA acceleration on GPU device " + gpu + " for global alignment.")
    if mode != "startup_only":
        log += "[CUDA Global Alignment] completed; converged=yes\\n"
if mode == "unexpected_cuda":
    log += "[CUDA Global Alignment] completed; converged=yes\\n"
(out / (case + ".log")).write_text(log)
''')
        self.binary.chmod(0o755)

    def launch(self, *extra, mode="ok", relative_binary=False):
        report = self.work / "aggregate.json"
        report.unlink(missing_ok=True)
        cmd = [sys.executable, str(RUNNER), "--binary",
               "fake-motioncorr" if relative_binary else str(self.binary),
               "--outdir", str(self.work / "out"), "--fixtures", str(self.work),
               "--no-regenerate", "--json", str(report)]
        env = dict(os.environ, KNOWN_MOTION_CONTROL=mode)
        result = subprocess.run(cmd + list(extra), cwd=self.work, env=env,
                                capture_output=True, text=True)
        return result, json.loads(report.read_text()) if report.exists() else {}

    def test_relative_binary_is_resolved_before_fixture_cwd(self):
        result, report = self.launch(relative_binary=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["overall"], "PASS")
        self.assertEqual(report["binary"], str(self.binary.resolve()))

    def test_thread_difference_blocks_aggregate(self):
        result, report = self.launch(mode="thread_difference")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report["overall"], "FAIL")
        self.assertEqual(report["results"][0]["thread_invariance"]["status"], "DIFFERS")

    def test_missing_requested_case_is_fatal(self):
        result, _ = self.launch("--cases", "still", "absent")
        self.assertEqual(result.returncode, 2)
        self.assertIn("requested fixtures missing", result.stderr)

    def test_cuda_requires_selection_and_completion(self):
        for mode, expected in (("ok", 0), ("cpu_despite_gpu", 1), ("startup_only", 1)):
            with self.subTest(mode=mode):
                result, report = self.launch("--gpu", "0", mode=mode)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                evidence = report["results"][0]["runs"]["j1"]["backend_evidence"]
                self.assertEqual(evidence["complete"], expected == 0)

    def test_cpu_rejects_unexpected_cuda(self):
        result, report = self.launch(mode="unexpected_cuda")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report["results"][0]["status"], "ERROR")

    def add_characterization(self):
        gt = json.loads(self.truth.read_text())
        gt["case"] = "noisy"
        gt["input_star"] = "noisy.star"
        gt["recommended_run"]["role"] = "characterization"
        # Produce a controlled estimator-accuracy failure on a well-formed field.
        gt["expected_applied_field"][1] = [[1.0, 1.0], [1.0, 1.0]]
        (self.work / "noisy_ground_truth.json").write_text(json.dumps(gt))

    def test_characterization_accuracy_failure_remains_visible(self):
        self.add_characterization()
        result, report = self.launch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        noisy = next(r for r in report["results"] if r["case"] == "noisy")
        self.assertEqual(noisy["status"], "FAIL")
        self.assertEqual(noisy["implementation_status"], "PASS")

    def test_characterization_process_failure_blocks_aggregate(self):
        self.add_characterization()
        result, report = self.launch(mode="characterization_exit")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report["overall"], "FAIL")

    def test_malformed_checker_input_is_recorded_as_error(self):
        result, report = self.launch(mode="malformed_star")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report["results"][0]["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
