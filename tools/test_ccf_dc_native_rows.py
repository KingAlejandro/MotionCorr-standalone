#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Controls for tools/ccf_dc_native_rows.py and the N-control generator.

    test_ccf_dc_native_rows.py                       pure controls (no producer)
    test_ccf_dc_native_rows.py --binary B [--iso]    plus real tiny runs of an experiment-build binary B

The native class runs the pinned K267/N commands on the CPU backend of B, then checks the grading with
copy-and-mutate controls on the finished run directories: a failed exit with a complete-looking tap, an
incomplete witness, a wrong arm or build identity, a vacuous local stage, a CUDA-declared row on a CPU run,
a missing marker, a placeholder tap and a tap/STAR disagreement. Truth is used only by the scorers.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "test-data"))
import ccf_dc_native_rows as rows            # noqa: E402
import generate_ccf_dc_n_controls as ngen    # noqa: E402
import generate_motion_diagnostics as kgen   # noqa: E402
from motion_field import read_mrc            # noqa: E402

BINARY = None
ISO = False
_args = sys.argv[1:]
if "--iso" in _args:
    ISO = True
    _args.remove("--iso")
if "--binary" in _args:
    _i = _args.index("--binary")
    BINARY = Path(_args[_i + 1]).resolve()
    del _args[_i:_i + 2]
sys.argv[1:] = _args


class PureControls(unittest.TestCase):
    def test_n_score_limits_and_arithmetic(self):
        truth = np.array([[0.0, 0.0], [1.0, 2.0], [2.0, 4.0]])
        self.assertEqual(rows.n_score(truth, truth)["verdict"], "PASS")
        px = 0.199 / rows.PIXEL_SIZE
        s = rows.n_score(truth + [px, 0.0], truth)
        self.assertAlmostEqual(s["rms"], 0.199, places=12)
        self.assertEqual(s["verdict"], "PASS")
        self.assertEqual(rows.n_score(truth + [0.201 / rows.PIXEL_SIZE, 0.0], truth)["verdict"], "FAIL")
        one = truth.copy()
        one[2] += [0.81 / rows.PIXEL_SIZE, 0.0]
        r = rows.n_score(one, truth)
        self.assertGreater(r["max"], 0.80)
        self.assertEqual(r["verdict"], "FAIL")
        # no scalar floor or offset is subtracted: a constant offset in every frame is an error
        self.assertEqual(rows.n_score(truth + [1.0, 0.0], truth)["verdict"], "FAIL")

    def test_witness_rules(self):
        def w(arm="both", status="atexit", iso=False, cpu=(10, 80), cuda_single=(0, 0), cuda_batched=(0, 0)):
            def st(ge, le, sel_g, sel_l):
                return {"global": dict(calls_eligible=ge, calls_zeroed=ge if sel_g else 0, frames_eligible=ge * 5,
                                       frames_zeroed=ge * 5 if sel_g else 0),
                        "local": dict(calls_eligible=le, calls_zeroed=le if sel_l else 0, frames_eligible=le * 5,
                                      frames_zeroed=le * 5 if sel_l else 0)}
            sg, sl = rows.ARMS[arm]
            return dict(schema="mc-ccf-dc-witness-v1", status=status, arm=arm, test_only_isotropic_global_weight=iso,
                        sites={"cpu": st(cpu[0], cpu[1], sg, sl), "cuda_single": st(cuda_single[0], cuda_single[1], sg, sl),
                               "cuda_batched": st(0, cuda_batched[1], 0, sl)})
        both = ("global", "local")
        self.assertEqual(rows.grade_witness(w(), "cpu", "both", both, False)[0], "VALID")
        self.assertEqual(rows.grade_witness(w(status="incomplete"), "cpu", "both", both, False)[0], "INVALID")
        self.assertEqual(rows.grade_witness(w(arm="none"), "cpu", "both", both, False)[0], "INVALID")
        self.assertEqual(rows.grade_witness(w(iso=True), "cpu", "both", both, False)[0], "INVALID")
        self.assertEqual(rows.grade_witness(w(), "cpu", "both", both, True)[0], "INVALID")
        # vacuous: the local stage never ran, so local/both would equal none/global
        self.assertEqual(rows.grade_witness(w(cpu=(10, 0)), "cpu", "both", both, False)[0], "INCONCLUSIVE")
        # CUDA: batched local must be reached; single local alone is not the declared route
        ok = w(cpu=(0, 0), cuda_single=(10, 0), cuda_batched=(0, 8))
        self.assertEqual(rows.grade_witness(ok, "cuda", "both", both, False)[0], "VALID")
        no_batch = w(cpu=(0, 0), cuda_single=(10, 8), cuda_batched=(0, 0))
        self.assertEqual(rows.grade_witness(no_batch, "cuda", "both", both, False)[0], "INCONCLUSIVE")
        # a CPU-declared row that touched CUDA, and a CUDA-declared row that fell back to the host
        self.assertEqual(rows.grade_witness(w(cuda_single=(1, 1)), "cpu", "both", both, False)[0], "INVALID")
        self.assertEqual(rows.grade_witness(w(cuda_single=(10, 0), cuda_batched=(0, 8)), "cuda", "both", both, False)[0], "INVALID")
        # N controls declare only the global stage and refuse a local call
        self.assertEqual(rows.grade_witness(w(cpu=(10, 0)), "cpu", "both", ("global",), False)[0], "VALID")
        self.assertEqual(rows.grade_witness(w(cpu=(10, 3)), "cpu", "both", ("global",), False)[0], "INVALID")
        # zero count mismatch
        bad = w()
        bad["sites"]["cpu"]["global"]["frames_zeroed"] -= 1
        self.assertEqual(rows.grade_witness(bad, "cpu", "both", both, False)[0], "INVALID")

    def test_clock_normalisation_is_anchored(self):
        bar = '   {}/   {} sec ' + '.' * 60 + '~~(,_,"> yum!'
        a = "head\n" + bar.format(0, 0) + "\ntail 3 sec\n"
        b = "head\n" + bar.format(1, 1) + "\ntail 3 sec\n"
        n = rows.normalise_console
        self.assertEqual(n(a), n(b), "a clock-only change must normalise away")
        c = "head\n" + bar.format(0, 0) + "\ntail 4 sec\n"
        self.assertNotEqual(n(a), n(c), "a number outside the anchored bar must stay")
        d = a.replace("head", "head 1/ 1 sec ...")
        self.assertNotEqual(n(a), n(d), "the anchor must not match mid-line text")
        e = "000/??? sec ~~(,_,\">\n"
        self.assertNotEqual(n(e), n(e.replace("000", "001")))

    def test_log_wall_line_is_anchored(self):
        a = "x\nFull movie wall time: 0.003 s\ny 1\n"
        self.assertEqual(rows.normalise_console(a), rows.normalise_console(a.replace("0.003", "0.9")))
        self.assertNotEqual(rows.normalise_console(a), rows.normalise_console(a.replace("y 1", "y 2")))
        self.assertNotEqual(rows.normalise_console(a), rows.normalise_console(a.replace("Full", "Half")))

    def test_star_format_matches_the_writer_rules(self):
        f = rows.star_format
        self.assertEqual(f(0.1234567891), 0.123457)           # positive, fixed, 6 decimals
        self.assertEqual(f(-0.1234567891), -0.12346)          # negative, fixed, 5 decimals
        self.assertEqual(f(0.00012345678), 0.0001234568)      # |v| < 1e-3, exponent form 1.234568e-04
        self.assertEqual(f(-0.00012345678), -0.000123457)     # negative: -1.23457e-04
        self.assertEqual(f(0.0), 0.0)
        self.assertEqual(f(123456.789), 123456.8)              # > 1e5: 1.234568e+05
        tap = {"global": [[0.123456789, -0.987654321]], "coeff_x": [1e-4] * 18, "coeff_y": [0.5] * 18, "local_enabled": True}
        r = rows.star_rounded_tap(tap)
        self.assertEqual(r["global"], [[0.123457, -0.98765]])

    def test_pinned_commands(self):
        grid = {c: rows.k267_argv("B", c, "O", "cpu")[rows.k267_argv("B", c, "O", "cpu").index("--patch_x") + 1]
                for c in rows.K267_PATCHES}
        self.assertEqual(grid, {"zero": "1", "integer": "1", "fractional": "1", "affine": "3", "pedestal": "3",
                                "noisy": "3", "flat": "1", "repeated": "1"}, "the original per-case patch grid")
        self.assertEqual(rows.k267_stages("affine"), ("global", "local"))
        self.assertEqual(rows.k267_stages("flat"), ("global",))
        self.assertEqual(rows.k267_argv("B", "flat", "O", "cpu", patches=3)[rows.k267_argv("B", "flat", "O", "cpu").index("--patch_x") + 1], "3")
        k = rows.k267_argv("B", "affine", "O", "cuda")
        self.assertIn("--gpu", k)
        self.assertNotIn("--skip_logfile", k)
        n = rows.n_argv("B", "vel0_N5", 5, "O", "cpu")
        self.assertEqual(n[n.index("--j") + 1], "2")
        self.assertEqual(n[n.index("--last_frame_sum") + 1], "5")
        self.assertNotIn("--gpu", n)
        env = rows.run_env("both", "R", "T", "GPU-x")
        self.assertEqual((env["MC_EXPERIMENT_CCF_DC_ARM"], env["CUDA_DEVICE_ORDER"]), ("both", "PCI_BUS_ID"))
        self.assertNotIn("MC_EXPERIMENT_CCF_DC_ARM", rows.run_env(None, None))

    def test_n_control_generator(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "n"
            man = ngen.generate(out)
            self.assertEqual(len(man["cases"]), 8)
            # all eight original movies and STARs, byte for byte (header included), from the retained render report
            pins = json.loads((HERE.parent / "docs/post_rc0/ccf_dc_native_compat_20261026/evidence/retained_render_report.json").read_text())
            self.assertEqual(pins["base_image_sha256"], ngen.BASE_SHA256)
            self.assertEqual(sorted(pins["movies"]), sorted(man["cases"]))
            for name, pin in pins["movies"].items():
                self.assertEqual(ngen.digest(out / f"{name}.mrcs"), pin["mrcs_sha256"], name + " movie differs from the original")
                self.assertEqual(ngen.digest(out / f"{name}.star"), pin["star_sha256"], name + " STAR differs from the original")
                self.assertEqual(man["cases"][name]["velocity"], pin["vel"])
                self.assertEqual(man["cases"][name]["frames"], pin["N"])
            self.assertEqual(ngen.digest(out / "base_target.npy"), ngen.BASE_SHA256)
            for name, c in man["cases"].items():
                for f, h in c["files"].items():
                    self.assertEqual(ngen.digest(out / f), h, f)
            base = ngen.base_image()
            # sign and content: vel0 N=5 is the K267 `integer` movie to one float32 ulp; the opposite sign is not
            k_movie = kgen.render(kgen.recipe("integer"))[0].astype(np.float64)
            for sign, expect_ok in ((1.0, True), (-1.0, False)):
                m = ngen.shifted_frames(base, ngen.VELOCITY["vel0"], 5, sign).astype(np.float64)
                d = np.abs(m - k_movie)
                ulp = np.spacing(np.abs(k_movie).astype(np.float32)).astype(np.float64)
                self.assertEqual(bool((d <= ulp).all()), expect_ok, f"sign {sign}")
            # frame 0 is the base exactly; row order is native; truth is f*vel
            m = ngen.shifted_frames(base, ngen.VELOCITY["vel1"], 20)
            self.assertTrue((m[0] == base).all())
            movie, _ = read_mrc(out / "vel1_N20.mrcs")
            self.assertTrue(np.array_equal(movie, m))
            self.assertFalse(np.array_equal(movie[1], movie[1][::-1]))
            truth = np.load(out / "vel1_N20_truth.npy")
            np.testing.assert_array_equal(truth[7], [7 * -0.8125, 7 * 0.53125])
            with self.assertRaises(FileExistsError):
                ngen.generate(out)


@unittest.skipUnless(BINARY, "native rows need --binary")
class NativeRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.fx = cls.root / "k267"
        kgen.generate(cls.fx)
        cls.nc = cls.root / "n"
        ngen.generate(cls.nc)
        cls.runs = {}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def produce(self, tag, kind, name, arm, frames=5, patches=None):
        run = self.root / tag
        if run.exists():
            return run
        run.mkdir()
        argv = (rows.k267_argv(BINARY, name, run / "out", "cpu") if kind == "K"
                else rows.n_argv(BINARY, name, frames, run / "out", "cpu"))
        if patches:
            argv[argv.index("--patch_x") + 1] = argv[argv.index("--patch_y") + 1] = str(patches)
        env = rows.run_env(arm, run / "witness.json", run / "tap.json")
        import os
        p = subprocess.run(argv, cwd=self.fx if kind == "K" else self.nc, env={**os.environ, **env},
                           capture_output=True, text=True, timeout=600)
        (run / "argv.json").write_text(json.dumps(argv))
        (run / "rc.txt").write_text(f"{p.returncode}\n")
        (run / "stdout.txt").write_text(p.stdout)
        (run / "stderr.txt").write_text(p.stderr)
        return run

    def copy(self, run, tag):
        dst = self.root / tag
        shutil.copytree(run, dst)
        # a copy must look like a producer that wrote into its own directory
        for f in [dst / "stdout.txt", dst / "stderr.txt", *(dst / "out").glob("*.star"), *(dst / "out").glob("*.log")]:
            f.write_text(f.read_text().replace(str(run), str(dst)))
        return dst

    def grade(self, run, arm="both", **kw):
        return rows.grade_k267(run, self.fx, "affine", "cpu", arm, iso_expected=ISO, **kw)

    def test_positive_affine_both(self):
        run = self.produce("affine_both", "K", "affine", "both")
        row = self.grade(run)
        self.assertEqual(row["row_status"], "SCORED", row)
        self.assertEqual(row["witness_status"], "VALID")
        for stage in ("global", "local"):
            c = row["counters"]["cpu"][stage]
            self.assertGreater(c["frames_eligible"], 0)
            self.assertEqual(c["frames_zeroed"], c["frames_eligible"])
        self.assertTrue(row["local_enabled"])
        self.assertEqual(row["stage_coverage"], {"global": "COVERED", "local": "COVERED"})
        self.assertIn("field_angstrom", row["star"])
        self.assertIn("field_angstrom", row["tap"])
        for i in range(2):
            self.assertLessEqual(row["tap_rounded_vs_star_max_px"][i], rows.STAR_FIELD_TOL_PX)
            self.assertLessEqual(row["tap_vs_star_max_px"][i], 1.2e-3, "the writer's own rounding loss stays within the derived bound")
        self.assertNotEqual(row["convergence"]["status"], "MISSING")
        # the tap-derived field is scored by the same unchanged checker, with no offset or floor applied
        self.assertEqual(row["tap"]["field_px"]["rms"] >= 0, True)

    def test_failed_exit_is_not_rescued_by_a_complete_tap(self):
        base = self.produce("affine_both", "K", "affine", "both")
        run = self.copy(base, "failed_rc")
        self.assertTrue(json.loads((run / "tap.json").read_text())["global"], "the tap looks complete")
        (run / "rc.txt").write_text("3\n")
        row = self.grade(run)
        self.assertEqual(row["row_status"], "FAILED_RUN")
        self.assertNotIn("tap", row)
        self.assertNotIn("star", row)

    def test_incomplete_publication(self):
        run = self.copy(self.produce("affine_both", "K", "affine", "both"), "nolog")
        (run / "out" / "affine.log").unlink()
        self.assertEqual(self.grade(run)["row_status"], "INCOMPLETE_PUBLICATION")

    def test_witness_incomplete_arm_and_identity(self):
        base = self.produce("affine_both", "K", "affine", "both")
        w = json.loads((base / "witness.json").read_text())
        for tag, change in (("w_incomplete", dict(status="incomplete")), ("w_arm", dict(arm="none")),
                            ("w_iso", dict(test_only_isotropic_global_weight=not ISO))):
            run = self.copy(base, tag)
            (run / "witness.json").write_text(json.dumps(dict(w, **change)))
            self.assertEqual(self.grade(run)["row_status"], "INVALID", tag)

    def test_global_only_row_cannot_claim_local_coverage(self):
        run = self.produce("zero_p1_both", "K", "zero", "both")   # original CLI: 1x1, no local stage requested
        row = rows.grade_k267(run, self.fx, "zero", "cpu", "both", iso_expected=ISO)
        self.assertEqual(row["row_status"], "SCORED", row)
        self.assertEqual(row["expected_stages"], ["global"])
        self.assertEqual(row["stage_coverage"]["global"], "COVERED")
        self.assertTrue(row["stage_coverage"]["local"].startswith("NOT_APPLICABLE"), row["stage_coverage"])
        self.assertIn("no-op selectivity", row["stage_coverage"]["local"])   # the arm selects local; nothing to zero
        loc = row["counters"]["cpu"]["local"]
        self.assertEqual((loc["frames_eligible"], loc["frames_zeroed"]), (0, 0))
        # a caller that declares local expected on this global-only run gets INCONCLUSIVE, never a pass
        row = rows.grade_k267(run, self.fx, "zero", "cpu", "both", iso_expected=ISO, stages=("global", "local"))
        self.assertEqual(row["row_status"], "INCONCLUSIVE", row)
        self.assertTrue(any("local" in r for r in row["witness_reasons"]))
        self.assertEqual(row["stage_coverage"]["local"], "INCONCLUSIVE")

    def test_local_reached_when_not_requested_is_invalid(self):
        run = self.produce("affine_both", "K", "affine", "both")   # 3x3: local runs
        row = rows.grade_k267(run, self.fx, "affine", "cpu", "both", iso_expected=ISO, stages=("global",))
        self.assertEqual(row["row_status"], "INVALID", row)

    def test_skip_logfile_does_not_change_the_products(self):
        a = self.produce("skiplog_without", "K", "affine", "none")
        b = self.root / "skiplog_with"
        b.mkdir()
        argv = rows.k267_argv(BINARY, "affine", b / "out", "cpu") + ["--skip_logfile"]
        import os
        p = subprocess.run(argv, cwd=self.fx, env={**os.environ, **rows.run_env("none", b / "witness.json", b / "tap.json")},
                           capture_output=True, text=True, timeout=600)
        (b / "rc.txt").write_text(f"{p.returncode}\n")
        (b / "stdout.txt").write_text(p.stdout)
        (b / "stderr.txt").write_text(p.stderr)
        self.assertEqual(p.returncode, 0)
        pa, pb = [read_mrc(x / "out" / "affine.mrc")[0] for x in (a, b)]
        self.assertTrue(np.array_equal(pa, pb), "--skip_logfile changed the pixels")
        sa, sb = [(x / "out" / "affine.star").read_text().replace(str(x), "R") for x in (a, b)]
        self.assertEqual(sa, sb, "--skip_logfile changed the per-movie STAR")
        self.assertEqual((a / "tap.json").read_bytes(), (b / "tap.json").read_bytes(), "--skip_logfile changed the tap")

    def test_cuda_declared_row_on_a_cpu_run(self):
        run = self.produce("affine_both", "K", "affine", "both")
        row = rows.grade_k267(run, self.fx, "affine", "cuda", "both", iso_expected=ISO)
        self.assertEqual(row["row_status"], "INVALID", row)

    def test_missing_marker_is_reported_not_passed(self):
        run = self.copy(self.produce("affine_both", "K", "affine", "both"), "nomarker")
        (run / "out" / "affine.log").write_text("nothing useful\n")
        row = self.grade(run)
        self.assertEqual(row["convergence"]["status"], "MISSING")

    def test_placeholder_tap_and_tap_star_disagreement(self):
        base = self.produce("affine_both", "K", "affine", "both")
        run = self.copy(base, "tap_placeholder")
        (run / "tap.json").write_text('{"status":"incomplete"}\n')
        row = self.grade(run)
        self.assertEqual(row["row_status"], "INVALID")
        self.assertIn("tap", row["reason"])
        run = self.copy(base, "tap_shifted")
        tap = json.loads((run / "tap.json").read_text())
        tap["global"][2][0] += 1e-3
        (run / "tap.json").write_text(json.dumps(tap))
        self.assertEqual(self.grade(run)["row_status"], "INVALID")

    def test_n_control_row(self):
        run = self.produce("n_v0n5_both", "N", "vel0_N5", "both", frames=5)
        row = rows.grade_n(run, self.nc, "vel0_N5", "cpu", "both", iso_expected=ISO)
        self.assertEqual(row["row_status"], "SCORED", row)
        self.assertLessEqual(row["rounded_runtime_minus_STAR_max_px"], rows.STAR_FIELD_TOL_PX)
        self.assertEqual(row["counters"]["cpu"]["local"]["frames_eligible"], 0)
        self.assertIn(row["runtime"]["verdict"], ("PASS", "FAIL"))

    def test_identity_report(self):
        a = self.produce("n_v0n5_none_a", "N", "vel0_N5", "none", frames=5)
        b = self.produce("n_v0n5_none_b", "N", "vel0_N5", "none", frames=5)
        self.assertTrue(rows.identity_report(a, b, "vel0_N5")["identical"])
        # a non-normalised numeric change in a copy must fail the identity
        c = self.copy(b, "id_star")
        p = c / "out" / "vel0_N5.star"
        p.write_text(p.read_text().replace("_rlnMicrographShiftX", "_rlnMicrographShiftX ", 1) + "# 1\n")
        self.assertFalse(rows.identity_report(a, c, "vel0_N5")["identical"])
        d = self.copy(b, "id_pix")
        m = d / "out" / "vel0_N5.mrc"
        raw = bytearray(m.read_bytes())
        raw[2048] ^= 0x01
        m.write_bytes(bytes(raw))
        self.assertFalse(rows.identity_report(a, d, "vel0_N5")["pixels"] and rows.identity_report(a, d, "vel0_N5")["identical"])
        # stderr: a reorder alone is identical, a content change is not
        f = self.copy(b, "id_err_order")
        lines = (f / "stderr.txt").read_text().splitlines()
        (f / "stderr.txt").write_text("\n".join(reversed(lines)) + "\n")
        self.assertTrue(rows.identity_report(a, f, "vel0_N5")["identical"])
        g = self.copy(b, "id_err_content")
        (g / "stderr.txt").write_text((g / "stderr.txt").read_text() + "extra diagnostic 7\n")
        self.assertFalse(rows.identity_report(a, g, "vel0_N5")["identical"])
        # a clock-only change in a copy is still identical
        e = self.copy(b, "id_clock")
        t = (e / "stdout.txt").read_text()
        import re
        t2 = re.sub(r'(?m)^( *)(\d+)/( *)(\d+) sec (\.{60})', lambda mo: f"{mo.group(1)}7/{mo.group(3)}7 sec {mo.group(5)}", t)
        (e / "stdout.txt").write_text(t2)
        self.assertTrue(rows.identity_report(a, e, "vel0_N5")["identical"])


if __name__ == "__main__":
    if BINARY is None:
        print("NATIVE ROWS NOT RUN: no --binary (pure controls only)")
    unittest.main()
