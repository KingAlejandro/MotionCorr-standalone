"""End-to-end mcprof runs against the stand-in binary (no GPU).

Covers the A/B instrument's three outcomes and the report contract:
a null comparison is not resolved, a deliberate per-movie slowdown resolves
slower and is localised to its stage, and a product difference fails.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fixture_db  # noqa: E402
import mcprof  # noqa: E402
from test_runner import make_binary, make_data  # noqa: E402


def c_rows(work):
    c = json.load(open(os.path.join(work, "compare.json")))
    return list(c["stage_deltas"]["arms"]["slow"]["stages"].values())


def sections(md):
    """{section title: body} for the level-2 sections of a report."""
    parts = re.split(r"^## ", md, flags=re.M)[1:]
    return {p.splitlines()[0]: p for p in parts}


class Compare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.data = make_data(os.path.join(cls.tmp, "data"))
        cls.base = make_binary(os.path.join(cls.tmp, "base-bin"), {"FAKE_SLEEP": "0.03"})
        cls.same = make_binary(os.path.join(cls.tmp, "same-bin"), {"FAKE_SLEEP": "0.03"})
        cls.slow = make_binary(os.path.join(cls.tmp, "slow-bin"), {"FAKE_SLEEP": "0.03", "FAKE_EXTRA": "0.15"})
        cls.diff = make_binary(os.path.join(cls.tmp, "diff-bin"), {"FAKE_SLEEP": "0.03", "FAKE_VARIANT": "x"})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def compare(self, name, arms, *extra):
        work = os.path.join(self.tmp, name)
        argv = ["compare", *arms, "--data", self.data, "--work", work, "--no-lock", "--pairs", "6",
                "--settle-timeout", "0", *extra, "--", "--gpu", "0"]
        with redirect_stdout(io.StringIO()):
            rc = mcprof.main(argv)
        return rc, work

    def test_null_is_not_resolved(self):
        # The floor keeps scheduler jitter between two identical arms from
        # ever reaching a verdict; the slowdown below is 0.45 s per run.
        rc, work = self.compare("null", ["main=" + self.base, "same=" + self.same], "--noise-floor", "0.1")
        self.assertEqual(rc, 0)
        c = json.load(open(os.path.join(work, "compare.json")))
        v = c["runs"]["comparisons"]["same"]
        self.assertEqual(v["verdict"], "not resolved (below noise %.3f s)" % v["resolution_s"])
        self.assertEqual(v["n_pairs"], 6)
        self.assertTrue(c["identity"]["same"]["identical"])
        orders = [p["order"] for p in self._pairs(work)]
        self.assertEqual(orders, ["AB", "BA"] * 3)

    def _pairs(self, work):
        runs = [json.loads(l) for l in open(os.path.join(work, "runs.jsonl"))]
        warm = [r for r in runs if r["kind"] == "warmup"]
        self.assertEqual(len(warm), 2)
        return [r for r in runs if r["kind"] == "round" and r["arm"] == "same"]

    def test_slowdown_resolves_and_is_localised(self):
        rc, work = self.compare("slow", ["main=" + self.base, "slow=" + self.slow], "--noise-floor", "0.1",
                                "--profile-pass", "3")
        self.assertEqual(rc, 0)
        c = json.load(open(os.path.join(work, "compare.json")))
        self.assertEqual(c["runs"]["comparisons"]["slow"]["verdict"], "resolved slower")
        self.assertEqual(c["stage_deltas"]["passes"], {"main": 3, "slow": 3})
        stages = c["stage_deltas"]["arms"]["slow"]["stages"]
        self.assertTrue(stages["fit polynomial"]["wall_ms"]["flag"])
        self.assertAlmostEqual(stages["fit polynomial"]["wall_ms"]["delta"], 150, delta=40)
        md = open(os.path.join(work, "report.md")).read()
        self.assertIn("**resolved slower**", md)
        self.assertIn("**fit polynomial**", md)
        # Regenerating from stored results reproduces the verdict.
        os.remove(os.path.join(work, "compare.json"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(mcprof.main(["report", work, "--noise-floor", "0.1", "--html"]), 0)
        c2 = json.load(open(os.path.join(work, "compare.json")))
        self.assertEqual(c2["runs"]["comparisons"]["slow"]["verdict"], "resolved slower")
        self.assertTrue(open(os.path.join(work, "report.html")).read().startswith("<!doctype html>"))

    def test_product_difference_fails(self):
        rc, work = self.compare("diff", ["main=" + self.base, "diff=" + self.diff])
        self.assertEqual(rc, 2)
        ident = json.load(open(os.path.join(work, "identity.json")))
        self.assertFalse(ident["diff"]["identical"])
        self.assertEqual(len(ident["diff"]["differences"]), 3)   # three movies' payloads
        md = open(os.path.join(work, "report.md")).read()
        self.assertIn("| diff | FAIL |", md)

    def test_sections_keep_instruments_apart(self):
        rc, work = self.compare("sections", ["main=" + self.base, "slow=" + self.slow], "--noise-floor", "0.1",
                                "--profile-pass", "1")
        md = open(os.path.join(work, "report.md")).read()
        sec = sections(md)
        for title, body in sec.items():
            if title == "Provenance":
                continue
            self.assertEqual(len(re.findall(r"^Instrument: ", body, flags=re.M)), 1, title)
        self.assertIn("mcprof run", sec["Unprofiled wall and resources"].split("\n")[2])
        self.assertIn("--profile", sec["Stage profile deltas"].split("\n")[2])
        # The profiled pass is recorded but never enters the unprofiled summary or the verdict.
        runs = [json.loads(l) for l in open(os.path.join(work, "runs.jsonl"))]
        self.assertEqual(sum(1 for r in runs if r["kind"] == "profile"), 2)
        # One pass per arm: deltas without flags.
        self.assertFalse(any(v["flag"] for row in c_rows(work) for v in row.values()))
        c = json.load(open(os.path.join(work, "compare.json")))
        self.assertEqual(c["runs"]["summary"]["slow"]["n"], 6)
        self.assertEqual(c["runs"]["comparisons"]["slow"]["n_pairs"], 6)


class DeviceTimingMode(unittest.TestCase):
    """Trace passes default to --profile_device_timing 0 and record the mode."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.new = make_binary(os.path.join(self.tmp, "new"))
        self.old = make_binary(os.path.join(self.tmp, "old"), device_timing_option=False)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_trace_payload_defaults_off(self):
        argv, mode = mcprof.trace_payload("off", self.new, ["--gpu", "0"], "s.star", "/o", "/p.jsonl", True)
        self.assertEqual(mode, "off")
        i = argv.index("--profile")
        self.assertEqual(argv[i:i + 4], ["--profile", "/p.jsonl", "--profile_device_timing", "0"])
        argv, mode = mcprof.trace_payload("on", self.new, [], "s.star", "/o", "/p.jsonl", True)
        self.assertEqual((argv[-2:], mode), (["--profile_device_timing", "1"], "on"))
        argv, mode = mcprof.trace_payload("off", self.old, [], "s.star", "/o", "/p.jsonl", False)
        self.assertNotIn("--profile_device_timing", argv)
        self.assertTrue(mode.startswith("on "))
        argv, mode = mcprof.trace_payload("off", self.new, [], "s.star", "/o", None, True)
        self.assertNotIn("--profile", argv)

    def test_parser_default_is_off_for_traces_on_for_profile_passes(self):
        captured = {}
        orig = mcprof.cmd_run
        try:
            mcprof.cmd_run = lambda a, r, compare=False: captured.setdefault("a", a) and 0
            mcprof.main(["compare", "x", "--work", os.path.join(self.tmp, "w")])
        finally:
            mcprof.cmd_run = orig
        self.assertEqual(captured["a"].trace_device_timing, "off")
        self.assertEqual(captured["a"].profile_device_timing, "on")

    def test_detection_and_profile_pass_record(self):
        from lib import provenance as prov
        self.assertTrue(prov.has_device_timing_option(self.new))
        self.assertFalse(prov.has_device_timing_option(self.old))
        data = make_data(os.path.join(self.tmp, "data"))
        work = os.path.join(self.tmp, "cmp")
        argv = ["compare", "a=" + self.new, "b=" + self.old, "--data", data, "--work", work, "--no-lock",
                "--pairs", "1", "--warmup", "0", "--settle-timeout", "0", "--lane-wait", "0",
                "--profile-pass", "1", "--profile-device-timing", "off", "--", "--gpu", "0"]
        with redirect_stdout(io.StringIO()):
            mcprof.main(argv)
        p = json.load(open(os.path.join(work, "provenance.json")))
        self.assertEqual(p["profile_device_timing"]["a"], "off")
        self.assertTrue(p["profile_device_timing"]["b"].startswith("on "))
        recs = [json.loads(l) for l in open(os.path.join(work, "profile", "a-p01.jsonl"))]
        self.assertEqual([r["device_timing"] for r in recs if r["type"] == "process"], ["off"])
        self.assertIn("CUDA device timing in --profile passes", open(os.path.join(work, "report.md")).read())


class DeviceTimingDetection(unittest.TestCase):
    """--use_own --help decides; the string scan is only a fallback."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def script(self, name, body):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, 0o755)
        return path

    def test_help_probe_is_authoritative(self):
        from lib import provenance as prov
        # Mentions the option in a comment, but its help does not list it.
        b = self.script("old", "# --profile_device_timing\n"
                               "[ \"$2\" = --help ] && echo '  --profile () : x' && exit 0\nexit 1")
        self.assertEqual(prov.device_timing_detection(b), (False, "--use_own --help"))
        b = self.script("new", "[ \"$2\" = --help ] && printf '  --profile () : x\\n"
                               "  --profile_device_timing (1) : y\\n' && exit 0\nexit 1")
        self.assertEqual(prov.device_timing_detection(b), (True, "--use_own --help"))

    def test_scan_fallback_when_help_fails(self):
        from lib import provenance as prov
        b = self.script("nohelp", "# --profile_device_timing\nexit 2")
        ok, how = prov.device_timing_detection(b)
        self.assertTrue(ok)
        self.assertTrue(how.startswith("binary scan"), how)


class TraceFromSqlite(unittest.TestCase):
    def test_report_from_fixture(self):
        tmp = tempfile.mkdtemp()
        try:
            db = fixture_db.build(os.path.join(tmp, "f.sqlite"))
            work = os.path.join(tmp, "trace")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(mcprof.main(["trace", "--from-sqlite", db, "--work", work]), 0)
            t = json.load(open(os.path.join(work, "trace.json")))
            self.assertEqual(t["totals"]["busy_ns"], 450)
            md = open(os.path.join(work, "report.md")).read()
            self.assertIn("Instrument: Nsight Systems", md)
            self.assertRegex(md, r"\| A \| 0\.00 \|")
            self.assertTrue(os.path.isfile(os.path.join(work, "timeline.json")))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
