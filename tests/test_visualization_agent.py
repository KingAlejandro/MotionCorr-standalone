#!/usr/bin/env python3
"""
Unit and Regression Tests for MotionCorr Visualization Agent and Standalone Plot Tools
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add repo root to import path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.visualization_agent.scripts.svg_engine import (
    SvgCanvas,
    render_speedup_scaling_svg,
    render_stacked_stages_svg,
    render_trajectory_drift_svg,
)
from agents.visualization_agent.scripts.visualize import (
    detect_data_type,
    scaffold_standalone_script,
    execute_standalone_script,
    build_markdown_report,
    resolve_output_directory,
)


class TestVisualizationAgent(unittest.TestCase):
    """Test suite for SVG rendering engine and agent orchestrator."""

    def test_svg_canvas_primitives(self):
        canvas = SvgCanvas(400, 300, "Test Canvas")
        canvas.add_rect(10, 10, 50, 50, fill="#ff0000")
        canvas.add_line(0, 0, 100, 100, stroke="#00ff00")
        canvas.add_circle(50, 50, 10, fill="#0000ff")
        canvas.add_polyline([(0, 0), (10, 20), (30, 40)])
        canvas.add_text(20, 20, "Sample & <Text>")

        svg_str = canvas.render()
        self.assertIn("<svg", svg_str)
        self.assertIn("</svg>", svg_str)
        self.assertIn('fill="#ff0000"', svg_str)
        self.assertIn("Sample &amp; &lt;Text&gt;", svg_str)

    def test_speedup_scaling_svg(self):
        threads = [1, 4, 10]
        times = [60.0, 18.0, 10.0]
        speedups = [1.0, 3.33, 6.0]
        svg = render_speedup_scaling_svg("Test Scaling", threads, times, speedups)
        self.assertIn("Test Scaling", svg)
        self.assertIn("OpenMP Thread Count", svg)
        self.assertIn("Speedup Multiplier", svg)
        self.assertIn("<svg", svg)

    def test_stacked_stages_svg(self):
        cats = ["1 Th", "4 Th"]
        stages = ["FFT", "Dose"]
        matrix = [[40.0, 20.0], [10.0, 5.0]]
        svg = render_stacked_stages_svg("Stage Breakdown", cats, stages, matrix)
        self.assertIn("Stage Breakdown", svg)
        self.assertIn("FFT", svg)
        self.assertIn("Dose", svg)

    def test_trajectory_drift_svg(self):
        frames = [1, 2, 3, 4]
        sx = [0.0, 0.5, 1.2, 1.8]
        sy = [0.0, -0.2, -0.6, -1.0]
        svg = render_trajectory_drift_svg("Drift Trajectory", frames, sx, sy)
        self.assertIn("Drift Trajectory", svg)
        self.assertIn("Shift X (px)", svg)
        self.assertIn("Shift Y (px)", svg)

    def test_detect_data_type(self):
        self.assertEqual(detect_data_type(Path("sample.star")), "trajectory")
        
        # Test JSON with multi-thread cases
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump({"cases": [{"threads": 1}, {"threads": 4}]}, tf)
            tf_path = Path(tf.name)
        try:
            self.assertEqual(detect_data_type(tf_path), "scaling")
        finally:
            tf_path.unlink()

    def test_resolve_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "plots"
            # 1. With timestamp
            target_dir = resolve_output_directory(base_dir, use_timestamp_subdir=True)
            self.assertTrue(target_dir.exists())
            self.assertEqual(target_dir.parent, base_dir)
            
            # 2. Without timestamp
            direct_dir = resolve_output_directory(base_dir, use_timestamp_subdir=False)
            self.assertEqual(direct_dir, base_dir)

    def test_scaffold_and_execute_standalone_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            out_script = tmp_root / "test_plot_scaling.py"
            out_plot_dir = tmp_root / "plots"
            
            # 1. Scaffold
            scaffold_standalone_script("scaling", out_script, "Custom Scaling Title")
            self.assertTrue(out_script.exists())
            
            # 2. Create sample benchmark JSON
            json_file = tmp_root / "bench.json"
            sample_data = {
                "cases": [
                    {"threads": 1, "mean_wall_time_sec": 30.0},
                    {"threads": 4, "mean_wall_time_sec": 10.0},
                ]
            }
            with open(json_file, "w") as f:
                json.dump(sample_data, f)
                
            # 3. Execute standalone script requesting both SVG and PNG
            code, stdout, stderr = execute_standalone_script(
                out_script,
                ["--input", str(json_file), "--out-dir", str(out_plot_dir), "--format", "svg", "png"]
            )
            self.assertEqual(code, 0, f"Script failed with stderr:\n{stderr}")
            self.assertIn("Generated SVG", stdout)
            
            # 4. Verify generated SVG file
            svg_files = list(out_plot_dir.glob("*.svg"))
            self.assertTrue(len(svg_files) >= 1)
            svg_content = svg_files[0].read_text()
            self.assertIn("Custom Scaling Title", svg_content)

    def test_markdown_report_builder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            report_path = tmp_root / "test_report.md"
            plot_file_svg = tmp_root / "sample_plot.svg"
            plot_file_png = tmp_root / "sample_plot.png"
            plot_file_svg.write_text("<svg></svg>")
            plot_file_png.write_text("PNG")
            
            build_markdown_report("Test Suite Report", "test_dataset.mrc", [plot_file_svg, plot_file_png], report_path, "All stages nominal.")
            self.assertTrue(report_path.exists())
            content = report_path.read_text()
            self.assertIn("Visualization Report: Test Suite Report", content)
            self.assertIn("sample_plot.svg", content)
            self.assertIn("sample_plot.png", content)
            self.assertIn("All stages nominal.", content)


if __name__ == "__main__":
    unittest.main()
