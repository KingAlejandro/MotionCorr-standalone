"""Known answers for lib/stats.py and the fixed verdict wording."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import stats  # noqa: E402


def pairs(diffs, base=10.0):
    return [{"a": base, "b": base + d, "order": "AB" if i % 2 == 0 else "BA"} for i, d in enumerate(diffs)]


class Basics(unittest.TestCase):
    def test_sign_test(self):
        self.assertAlmostEqual(stats.sign_test([1] * 6)["p_two_sided"], 2 / 64)
        self.assertEqual(stats.sign_test([1, -1, 0])["ties"], 1)
        self.assertEqual(stats.sign_test([])["p_two_sided"], 1.0)

    def test_median_ci(self):
        self.assertIsNone(stats.median_ci([1, 2, 3, 4, 5]))       # n=5 cannot reach 95%
        lo, hi, conf = stats.median_ci([6, 1, 5, 2, 4, 3])
        self.assertEqual((lo, hi), (1, 6))
        self.assertAlmostEqual(conf, 1 - 2 / 64)
        lo, hi, conf = stats.median_ci(list(range(1, 21)))           # n=20: x(6)..x(15)
        self.assertEqual((lo, hi), (6, 15))
        self.assertGreaterEqual(conf, 0.95)

    def test_robust_sd_and_outliers(self):
        self.assertAlmostEqual(stats.robust_sd([1, 2, 3, 4, 100]), 1.4826)
        self.assertEqual(stats.outliers([1.0, 1.01, 0.99, 1.0, 3.0]), [4])


class Verdicts(unittest.TestCase):
    def test_wording_is_fixed(self):
        self.assertEqual(stats.VERDICT_FASTER, "resolved faster")
        self.assertEqual(stats.VERDICT_SLOWER, "resolved slower")
        self.assertEqual(stats.verdict_unresolved(0.0456), "not resolved (below noise 0.046 s)")

    def test_consistent_slowdown_resolves(self):
        c = stats.paired(pairs([0.60, 0.62, 0.58, 0.61, 0.59, 0.60]))
        self.assertEqual(c["verdict"], "resolved slower")
        self.assertTrue(c["resolved"])

    def test_consistent_speedup_resolves(self):
        c = stats.paired(pairs([-0.3, -0.31, -0.29, -0.3, -0.32, -0.28, -0.3, -0.31]))
        self.assertEqual(c["verdict"], "resolved faster")

    def test_null_does_not_resolve(self):
        c = stats.paired(pairs([0.02, -0.01, 0.03, -0.02, 0.01, -0.03]))
        self.assertFalse(c["resolved"])
        self.assertTrue(c["verdict"].startswith("not resolved (below noise "))
        self.assertEqual(c["reason"], "CI of median includes 0")

    def test_too_few_pairs_never_resolves(self):
        c = stats.paired(pairs([1.0, 1.0, 1.0, 1.0, 1.0]))
        self.assertFalse(c["resolved"])
        self.assertIn("fewer than 6 retained pairs (5)", c["reason"])
        # No finite resolution is claimed from too few pairs (the 3-pair null
        # of the first 4GPUs campaign reported "below noise 0.215 s").
        self.assertEqual(c["verdict"], "not resolved (5 retained pairs, 6 needed)")
        self.assertEqual(c["resolution_s"], float("inf"))
        self.assertEqual(stats.paired([])["verdict"], "not resolved (0 retained pairs, 6 needed)")

    def test_min_pairs_does_not_depend_on_ci(self):
        # Even if the CI routine produced an interval for 5 pairs, the 6-pair
        # minimum holds: the rule is enforced in paired() itself.
        real = stats.median_ci
        try:
            stats.median_ci = lambda xs, confidence=stats.CONFIDENCE: (min(xs), max(xs), 0.99)
            c = stats.paired(pairs([1.0, 1.01, 0.99, 1.0, 1.02]))
            self.assertFalse(c["resolved"])
            self.assertTrue(stats.paired(pairs([1.0, 1.01, 0.99, 1.0, 1.02, 1.0]))["resolved"])
        finally:
            stats.median_ci = real
        self.assertEqual(stats.MIN_PAIRS, 6)

    def test_same_sign_but_below_noise(self):
        # Every pair positive, but the median is inside the pair-to-pair scatter.
        c = stats.paired(pairs([0.01, 0.02, 0.5, 0.6, 0.7, 0.03]))
        self.assertFalse(c["resolved"])
        self.assertEqual(c["reason"], "|median| does not exceed noise")

    def test_floor(self):
        d = [0.05, 0.051, 0.049, 0.05, 0.052, 0.048]
        self.assertTrue(stats.paired(pairs(d))["resolved"])
        c = stats.paired(pairs(d), floor_s=0.1)
        self.assertFalse(c["resolved"])
        self.assertEqual(c["verdict"], "not resolved (below noise 0.100 s)")

    def test_positional_bias(self):
        # True effect 0.5 s; whichever arm runs second pays 0.1 s.
        p = [{"a": 10.0, "b": 10.6, "order": "AB"}, {"a": 10.1, "b": 10.5, "order": "BA"}] * 3
        pos = stats.paired(p)["positional"]
        self.assertAlmostEqual(pos["second_position_cost_s"], 0.1)
        self.assertAlmostEqual(pos["order_corrected_effect_s"], 0.5)

    def test_replicated_delta(self):
        base = [[10.0, 10.2, 9.8], [10.1, 10.3, 9.9], [9.9, 10.0, 10.1]]
        # A per-process offset larger than the movie scatter: one pass per arm cannot flag it.
        self.assertFalse(stats.replicated_delta(base[:1], [[x + 25 for x in base[0]]])["flag"])
        self.assertTrue(stats.replicated_delta(base, [[x + 25 for x in p] for p in base], min_abs=0.5)["flag"])
        # Process-to-process spread of +-1 hides a 0.5 shift even though movies agree closely.
        spread = [[10.0, 10.0], [12.0, 12.0], [8.0, 8.0]]
        r = stats.replicated_delta(spread, [[x + 0.5 for x in p] for p in spread])
        self.assertFalse(r["flag"])
        self.assertEqual(r["df"], 4)
        # Deterministic counts: any change above the floor is flagged.
        self.assertTrue(stats.replicated_delta([[3], [3]], [[4], [4]], min_abs=0.5)["flag"])
        self.assertFalse(stats.replicated_delta([[3], [3]], [[3], [3]], min_abs=0.5)["flag"])

    def test_t_crit(self):
        self.assertEqual(stats.t_crit(2), 31.60)
        self.assertEqual(stats.t_crit(13), 4.318)
        self.assertEqual(stats.t_crit(500), 3.460)


if __name__ == "__main__":
    unittest.main()
