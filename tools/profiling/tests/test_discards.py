"""The discard rule cannot bias a verdict silently (docs/profiling.md, rule 3).

A discard removes the whole round, so both arms always keep the same rounds
and every retained difference is a complete pair. Discards are reported per
round with the arm(s) that triggered them, and a one-sided or order-skewing
pattern is warned about. Fewer than 6 retained pairs give no verdict.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import report, runner, stats  # noqa: E402


def runs_for(walls_a, walls_b, flag_a=(), flag_b=()):
    """Round records for two arms with AB/BA alternation and chosen discard flags."""
    out = []
    for i, (wa, wb) in enumerate(zip(walls_a, walls_b)):
        r = i + 1
        order = "AB" if i % 2 == 0 else "BA"
        pa, pb = (0, 1) if order == "AB" else (1, 0)
        out.append({"arm": "A", "kind": "round", "round": r, "position": pa, "order": order, "wall_s": wa,
                    "cpu_s": 1.0, "peak_rss_bytes": 1, "minflt": 1, "majflt": 0,
                    "flags": {"discard": ["foreign CPU on lane 1.00 cores"] if r in flag_a else [], "note": []}})
        out.append({"arm": "B", "kind": "round", "round": r, "position": pb, "order": order, "wall_s": wb,
                    "cpu_s": 1.0, "peak_rss_bytes": 1, "minflt": 1, "majflt": 0,
                    "flags": {"discard": ["foreign CPU on lane 1.00 cores"] if r in flag_b else [], "note": []}})
    return out


class WholeRoundDiscard(unittest.TestCase):
    def test_one_arm_flag_removes_the_pair(self):
        a = [10.0] * 10
        b = [10.5] * 10
        b[2] = 30.0                       # the flagged run is an outlier of arm B only
        d = report.derive_runs({"arms": ["A", "B"], "runs": runs_for(a, b, flag_b={3})})
        self.assertEqual(d["summary"]["A"]["n"], 9)
        self.assertEqual(d["summary"]["B"]["n"], 9)     # never one arm's run alone
        c = d["comparisons"]["B"]
        self.assertEqual(c["n_pairs"], 9)
        self.assertNotIn(30.0 - 10.0, c["diffs_s"])
        self.assertEqual(d["discarded_rounds"], [{"round": 3, "reasons": ["B: foreign CPU on lane 1.00 cores"],
                                                  "triggered_by": ["B"], "order": "AB"}])

    def test_retained_rounds_are_identical_across_arms(self):
        a = [10.0 + 0.01 * i for i in range(10)]
        b = [10.2 + 0.01 * i for i in range(10)]
        rs = runs_for(a, b, flag_a={2, 7}, flag_b={5})
        report.derive_runs({"arms": ["A", "B"], "runs": rs})
        kept = {arm: sorted(r["round"] for r in rs if r["arm"] == arm and not r["discarded"]) for arm in "AB"}
        self.assertEqual(kept["A"], kept["B"])
        self.assertEqual(kept["A"], [1, 3, 4, 6, 8, 9, 10])

    def test_audit_counts_and_report(self):
        a = [10.0] * 10
        b = [10.5] * 10
        rs = runs_for(a, b, flag_a={1}, flag_b={1, 4})
        d = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        au = d["discard_audit"]
        self.assertEqual((au["planned"], au["retained"], au["discarded"]), (10, 8, 2))
        self.assertEqual(au["triggered_any"], {"A": 1, "B": 2})
        self.assertEqual(au["triggered_alone"], {"A": 0, "B": 1})
        self.assertEqual(au["kept_orders"], {"AB": 4, "BA": 4})
        self.assertEqual(au["warnings"], [])
        md = report.render_run_section(d)
        self.assertIn("Rounds: 10 planned, 8 retained, 2 discarded", md)
        self.assertIn("`B` 2 (alone 1)", md)
        self.assertIn("- round 4 (BA): B: foreign CPU", md)

    def test_one_sided_discards_warn(self):
        rs = runs_for([10.0] * 12, [10.5] * 12, flag_b={2, 5, 8, 11})
        d = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        self.assertTrue(any("arm B alone triggered 4 of 4" in w for w in d["discard_audit"]["warnings"]))
        self.assertIn("WARNING: arm B alone triggered", report.render_run_section(d))

    def test_order_imbalance_warns(self):
        # Every discarded round is a BA round: the kept pairs are mostly AB.
        rs = runs_for([10.0] * 10, [10.5] * 10, flag_a={2}, flag_b={4, 6})
        d = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        self.assertEqual(d["discard_audit"]["kept_orders"], {"AB": 5, "BA": 2})
        self.assertTrue(any("unbalanced by order" in w for w in d["discard_audit"]["warnings"]))

    def test_too_few_retained_pairs_give_no_verdict(self):
        # A clear 0.5 s slowdown, but only 5 of 10 rounds survive.
        rs = runs_for([10.0] * 10, [10.5] * 10, flag_a={1, 3, 5}, flag_b={7, 9})
        d = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        c = d["comparisons"]["B"]
        self.assertEqual(c["n_pairs"], 5)
        self.assertFalse(c["resolved"])
        self.assertEqual(c["verdict"], "not resolved (5 retained pairs, 6 needed)")
        # Six survivors resolve it.
        rs = runs_for([10.0] * 10, [10.5] * 10, flag_a={1, 3}, flag_b={7, 9})
        self.assertEqual(report.derive_runs({"arms": ["A", "B"], "runs": rs})["comparisons"]["B"]["verdict"],
                         stats.VERDICT_SLOWER)

    def test_warmup_and_profile_flags_do_not_discard_rounds(self):
        rs = runs_for([10.0] * 6, [10.5] * 6)
        rs.append({"arm": "B", "kind": "warmup", "round": 0, "position": 0, "order": "B", "wall_s": 50.0,
                   "flags": {"discard": ["foreign CPU on lane 2.00 cores"], "note": []}})
        d = report.derive_runs({"arms": ["A", "B"], "runs": rs})
        self.assertEqual(d["comparisons"]["B"]["n_pairs"], 6)
        self.assertEqual(d["discarded_rounds"], [])


class ExtraRounds(unittest.TestCase):
    """--max-rounds: rounds continue until enough are clean; stopping depends
    on discard flags only, and every round is recorded."""

    def setUp(self):
        self.real = runner.run_once
        self.calls = []
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        runner.run_once = self.real
        self.tmp.cleanup()

    def fake(self, dirty_rounds):
        def run_once(argv, cwd, env, log, sampler, lane, binary, out, n):
            tag = os.path.basename(os.path.dirname(out))
            self.calls.append(tag)
            r = int(tag[-2:])
            dirty = tag[-3] == "r" and r in dirty_rounds and binary.endswith("b")
            return {"wall_s": 1.0, "out_dir": out,
                    "flags": {"discard": ["foreign CPU on lane 1.00 cores"] if dirty else [], "note": []}}
        runner.run_once = run_once

    def series(self, rounds, max_rounds, dirty):
        self.fake(dirty)
        recs = []
        res = runner.series({"A": "/x/a", "B": "/x/b"}, [], {"star": "s.star", "cwd": "/", "movies": ["m"]},
                            self.tmp.name, [], None, [], rounds, 0, runner.GpuSampler(None),
                            recs.append, keep_outputs=True, max_rounds=max_rounds)
        return res, recs

    def test_runs_until_clean_target(self):
        res, recs = self.series(6, 10, {2, 3})
        self.assertEqual(res, {"target_clean_rounds": 6, "max_rounds": 10, "rounds_run": 8, "clean_rounds": 6,
                               "reached_target": True})
        self.assertEqual(len(recs), 16)

    def test_stops_at_max_and_says_so(self):
        res, _ = self.series(6, 7, {1, 2, 3})
        self.assertEqual((res["rounds_run"], res["clean_rounds"], res["reached_target"]), (7, 4, False))

    def test_default_runs_exactly_the_requested_rounds(self):
        res, _ = self.series(6, None, {1})
        self.assertEqual((res["rounds_run"], res["clean_rounds"]), (6, 5))


if __name__ == "__main__":
    unittest.main()
