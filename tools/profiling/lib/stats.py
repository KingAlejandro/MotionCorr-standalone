"""Paired statistics for A/B wall-time claims (docs/profiling.md, "Verdicts").

A verdict is made only from paired, interleaved runs. For paired differences
d = B - A (positive means B is slower):

* noise = max(1.4826 * MAD(d), any imposed floor). This is the pair-to-pair
  scatter, measured on the same data.
* The median of d gets a distribution-free confidence interval from the
  binomial order statistics (>= 95%). It exists only from 6 pairs up; with
  fewer, nothing can be resolved.
* "resolved" requires the interval to exclude zero AND |median(d)| > noise.
* An unresolved result reports X = max(noise, interval half-width): effects
  smaller than X cannot be distinguished by this data.

Standard library only.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

VERDICT_FASTER = "resolved faster"
VERDICT_SLOWER = "resolved slower"
MIN_PAIRS = 6
CONFIDENCE = 0.95


def verdict_unresolved(noise_s: float) -> str:
    return "not resolved (below noise %s s)" % _fmt_s(noise_s)


def _fmt_s(x: float) -> str:
    return "inf" if math.isinf(x) else "%.3f" % x


def median(xs: Sequence[float]) -> float:
    return statistics.median(xs)


def quartiles(xs: Sequence[float]) -> Tuple[float, float, float]:
    if len(xs) == 1:
        return xs[0], xs[0], xs[0]
    q1, q2, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    return q1, q2, q3


def iqr(xs: Sequence[float]) -> float:
    q1, _, q3 = quartiles(xs)
    return q3 - q1


def mad(xs: Sequence[float]) -> float:
    m = median(xs)
    return median([abs(x - m) for x in xs])


def robust_sd(xs: Sequence[float]) -> float:
    """1.4826 * MAD: the SD of a normal sample, insensitive to single outliers."""
    return 1.4826 * mad(xs) if len(xs) > 1 else 0.0


def binom_cdf_half(k: int, n: int) -> float:
    """P(X <= k) for X ~ Binomial(n, 1/2)."""
    if k < 0:
        return 0.0
    return sum(math.comb(n, i) for i in range(0, min(k, n) + 1)) / 2.0 ** n


def sign_test(diffs: Sequence[float]) -> Dict[str, float]:
    """Exact two-sided sign test; zero differences are dropped."""
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    n = pos + neg
    p = 1.0 if n == 0 else min(1.0, 2.0 * binom_cdf_half(min(pos, neg), n))
    return {"positive": pos, "negative": neg, "ties": len(diffs) - n, "p_two_sided": p}


def median_ci(xs: Sequence[float], confidence: float = CONFIDENCE
              ) -> Optional[Tuple[float, float, float]]:
    """Distribution-free CI for the median: (low, high, achieved confidence).

    Uses order statistics x(k) and x(n+1-k) with the largest k whose two-sided
    binomial tail is <= 1 - confidence. None when n is too small for any k.
    """
    s = sorted(xs)
    n = len(s)
    best = None
    for k in range(1, n // 2 + 1):
        tail = 2.0 * binom_cdf_half(k - 1, n)
        if tail <= 1.0 - confidence:
            best = (s[k - 1], s[n - k], 1.0 - tail)
        else:
            break
    return best


def outliers(xs: Sequence[float], k: float = 3.0) -> List[int]:
    """Indices further than k robust SDs from the median."""
    if len(xs) < 3:
        return []
    m = median(xs)
    sd = robust_sd(xs)
    if sd == 0.0:
        return [i for i, x in enumerate(xs) if x != m]
    return [i for i, x in enumerate(xs) if abs(x - m) > k * sd]


def paired(pairs: Sequence[Dict], floor_s: float = 0.0) -> Dict:
    """Summarise pairs [{"a": s, "b": s, "order": "AB"|"BA", ...}] into a verdict."""
    d = [p["b"] - p["a"] for p in pairs]
    n = len(d)
    out: Dict = {"n_pairs": n, "diffs_s": d, "floor_s": floor_s, "min_pairs": MIN_PAIRS}
    if n == 0:
        out.update({"verdict": verdict_unresolved(math.inf), "resolved": False,
                    "resolution_s": math.inf, "reason": "no retained pairs"})
        return out
    med = median(d)
    q1, _, q3 = quartiles(d)
    noise = max(robust_sd(d), floor_s)
    ci = median_ci(d)
    if ci is not None:
        half = (ci[1] - ci[0]) / 2.0
    elif n >= 2:
        half = (max(d) - min(d)) / 2.0
    else:
        half = math.inf
    excludes_zero = ci is not None and (ci[0] > 0 or ci[1] < 0)
    resolved = excludes_zero and abs(med) > noise
    resolution = max(noise, half)
    if resolved:
        verdict = VERDICT_SLOWER if med > 0 else VERDICT_FASTER
        reason = "CI of median excludes 0 and |median| exceeds noise"
    else:
        verdict = verdict_unresolved(resolution)
        if ci is None:
            reason = "fewer than %d pairs: no %.0f%% CI of the median exists" % (MIN_PAIRS, 100 * CONFIDENCE)
        elif not excludes_zero:
            reason = "CI of median includes 0"
        else:
            reason = "|median| does not exceed noise"
    a = [p["a"] for p in pairs]
    b = [p["b"] for p in pairs]
    out.update({
        "median_diff_s": med, "q1_diff_s": q1, "q3_diff_s": q3,
        "min_diff_s": min(d), "max_diff_s": max(d),
        "median_a_s": median(a), "median_b_s": median(b),
        "relative_median_diff": med / median(a) if median(a) else None,
        "noise_s": noise, "robust_sd_diff_s": robust_sd(d),
        "ci": None if ci is None else {"low_s": ci[0], "high_s": ci[1], "confidence": ci[2]},
        "sign_test": sign_test(d),
        "resolution_s": resolution, "resolved": resolved,
        "verdict": verdict, "reason": reason,
    })
    out["positional"] = positional_bias(pairs)
    return out


def positional_bias(pairs: Sequence[Dict]) -> Optional[Dict]:
    """Split pairs by order. With d = E + P (B second) and d = E - P (B first),
    P is the cost of running second (mostly cache warming of inputs)."""
    ab = [p["b"] - p["a"] for p in pairs if p.get("order") == "AB"]
    ba = [p["b"] - p["a"] for p in pairs if p.get("order") == "BA"]
    if not ab or not ba:
        return None
    mab, mba = median(ab), median(ba)
    return {"n_ab": len(ab), "n_ba": len(ba), "median_diff_ab_s": mab, "median_diff_ba_s": mba,
            "second_position_cost_s": (mab - mba) / 2.0, "order_corrected_effect_s": (mab + mba) / 2.0}


# Two-sided Student-t critical values at alpha = 0.001, by degrees of freedom.
T_CRIT_999 = {1: 636.62, 2: 31.60, 3: 12.92, 4: 8.610, 5: 6.869, 6: 5.959, 7: 5.408, 8: 5.041,
              9: 4.781, 10: 4.587, 12: 4.318, 15: 4.073, 20: 3.850, 30: 3.646, 60: 3.460}


def t_crit(df: int) -> float:
    return T_CRIT_999[max(k for k in T_CRIT_999 if k <= df)]


def replicated_delta(base_passes: Sequence[Sequence[float]], arm_passes: Sequence[Sequence[float]],
                     min_abs: float = 0.0) -> Dict:
    """Stage-level delta between arms from replicated processes.

    Each pass (one process) contributes one value: the median of its samples
    (steady-state movies). Movies inside one process share that process's
    conditions, so they are not independent; the noise comes from the spread
    of pass values within each arm (pooled variance, df = Pa + Pb - 2). A
    stage is flagged when |delta| exceeds t(0.999, df) * SE and min_abs.
    With fewer than two passes per arm the delta is reported without a flag.
    """
    a = [median(p) for p in base_passes if len(p)]
    b = [median(p) for p in arm_passes if len(p)]
    out: Dict = {"passes_a": len(a), "passes_b": len(b), "pass_values_a": a, "pass_values_b": b,
                 "flag": False, "replicated": False}
    if not a or not b:
        out["delta"] = None
        return out
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    out.update({"median_a": ma, "median_b": mb, "delta": mb - ma})
    if len(a) < 2 or len(b) < 2:
        return out
    df = len(a) + len(b) - 2
    ss = sum((x - ma) ** 2 for x in a) + sum((x - mb) ** 2 for x in b)
    se = math.sqrt(ss / df) * math.sqrt(1.0 / len(a) + 1.0 / len(b))
    thr = max(t_crit(df) * se, min_abs)
    out.update({"replicated": True, "df": df, "se": se, "threshold": thr, "flag": abs(mb - ma) > thr})
    return out
