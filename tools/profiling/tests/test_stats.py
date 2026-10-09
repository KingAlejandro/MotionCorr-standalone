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
        self.assertIn("fewer than 6 pairs", c["reason"])

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

    def test_per_sample_delta_flags(self):
        a = [10.0, 10.1, 9.9, 10.0, 10.05, 9.95]
        self.assertTrue(stats.per_sample_delta(a, [x + 25 for x in a])["flag"])
        self.assertFalse(stats.per_sample_delta(a, [x + 0.01 for x in a])["flag"])


if __name__ == "__main__":
    unittest.main()
