#!/usr/bin/env python3
"""
Unit and Integration Tests for CPU Profiling & Benchmark Suite (Issue #9)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.profile_cpu_benchmark import (
    BenchmarkCaseSummary,
    SingleRunResult,
    StageTimingStats,
    compute_sha256,
    generate_markdown_profile_report,
    get_system_hardware_info,
    parse_stage_times_from_output,
)


class TestProfileCpuBenchmark(unittest.TestCase):

    def test_parse_stage_times(self):
        sample_output = """
        read movie                         : 0.1234 sec (123400 microsec/operation)
        global FFT                         : 0.5678 sec (567800 microsec/operation)
        patch alignment                    : 2.3456 sec (2345600 microsec/operation)
        align - calc CCF (in thread)       : 1.8901 sec (1890100 microsec/operation)
        dose weighting                     : 0.4321 sec (432100 microsec/operation)
        """
        stages = parse_stage_times_from_output(sample_output)
        self.assertIn("read movie", stages)
        self.assertAlmostEqual(stages["read movie"], 0.1234)
        self.assertIn("global FFT", stages)
        self.assertAlmostEqual(stages["global FFT"], 0.5678)
        self.assertIn("patch alignment", stages)
        self.assertAlmostEqual(stages["patch alignment"], 2.3456)
        self.assertIn("align - calc CCF (in thread)", stages)
        self.assertAlmostEqual(stages["align - calc CCF (in thread)"], 1.8901)
        self.assertIn("dose weighting", stages)
        self.assertAlmostEqual(stages["dose weighting"], 0.4321)

    def test_compute_sha256(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"MotionCorr Benchmark Test Content")
            tf_path = Path(tf.name)
        try:
            h = compute_sha256(tf_path)
            self.assertEqual(len(h), 64)
            self.assertEqual(compute_sha256(Path("/non/existent/file.bin")), "")
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_hardware_info(self):
        hw = get_system_hardware_info()
        self.assertIn("os", hw)
        self.assertIn("cpu_arch", hw)
        self.assertIn("cpu_count_logical", hw)
        self.assertTrue(int(hw["cpu_count_logical"]) >= 1)

    def test_markdown_report_generation(self):
        hw = {"os": "Linux-Test", "cpu_model": "Test-CPU", "cpu_count_logical": "8", "total_ram_gb": "32.00 GB"}
        st1 = StageTimingStats(tag="patch alignment", mean_sec=2.0, std_sec=0.1, min_sec=1.9, max_sec=2.1, pct_total=66.7)
        st2 = StageTimingStats(tag="dose weighting", mean_sec=1.0, std_sec=0.05, min_sec=0.95, max_sec=1.05, pct_total=33.3)
        
        summary = BenchmarkCaseSummary(
            name="Test_Case",
            dataset_path="/tmp/test_movie.mrc",
            dataset_sha256="abcd1234ef5678",
            threads=4,
            patch_x=5,
            patch_y=5,
            repetitions=3,
            mean_wall_time_sec=3.0,
            std_wall_time_sec=0.15,
            mean_peak_rss_mb=512.0,
            max_peak_rss_mb=520.0,
            stage_breakdowns=[st1, st2],
            top_time_stages=[("patch alignment", 2.0, 66.7), ("dose weighting", 1.0, 33.3)]
        )
        report = generate_markdown_profile_report([summary], hw)
        self.assertIn("MotionCorr CPU Performance & Profiling Baseline Report", report)
        self.assertIn("Test_Case", report)
        self.assertIn("patch alignment", report)
        self.assertIn("Ranked Optimization Recommendations", report)


if __name__ == "__main__":
    unittest.main()
