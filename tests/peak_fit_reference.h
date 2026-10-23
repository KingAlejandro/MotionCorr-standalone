// SPDX-License-Identifier: GPL-2.0-or-later
// Bounded exact-rational fixtures for #257; host code only, also used by CUDA tests.
#ifndef MOTIONCORR_TEST_PEAK_FIT_REFERENCE_H
#define MOTIONCORR_TEST_PEAK_FIT_REFERENCE_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace peak_fit_reference {
inline void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}

// Deliberately bounded, not an arbitrary-precision library. Bounds keep every
// cross-product below 2^63. Unsupported fixtures fail rather than approximate.
struct Rational {
    int64_t n, d;
    Rational(int64_t numerator, int64_t denominator = 1) : n(numerator), d(denominator) {
        require(d != 0, "zero rational denominator");
        if (d < 0) { n = -n; d = -d; }
        const auto g = std::gcd(n, d);
        n /= g; d /= g;
        require(std::abs(n) <= 1000000000 && d <= 1000000000, "fixture rational out of bounds");
    }
};
inline bool operator==(Rational a, Rational b) { return a.n == b.n && a.d == b.d; }
inline Rational operator*(Rational a, Rational b) { return {a.n * b.n, a.d * b.d}; }

// The double division only proposes a float. Integer comparisons certify that
// it lies in the exact rational's round-to-nearest cell, including ties to even.
// No floating evaluation of the fit is used to certify the expected answer.
inline float rounded(Rational r) {
    static_assert(std::numeric_limits<float>::is_iec559 &&
                  std::numeric_limits<float>::digits == 24, "requires IEEE binary32");
    static_assert(std::numeric_limits<double>::radix == 2 &&
                  std::numeric_limits<double>::digits >= 53, "requires at least binary64 precision");
    if (r.n == 0) return 0;
    const float f = float(double(r.n) / double(r.d));
    const float lo = std::nextafter(f, -std::numeric_limits<float>::infinity());
    const float hi = std::nextafter(f, std::numeric_limits<float>::infinity());
    int ef, el, eh;
    std::frexp(f, &ef); std::frexp(lo, &el); std::frexp(hi, &eh);
    const int e = std::min({ef, el, eh}) - 24;
    require(e >= -30 && e <= 0, "rounding certificate out of bounds");
    const auto units = [e](float v) { return int64_t(std::ldexp(double(v), -e)); };
    const int64_t mid = 2 * r.n * (int64_t(1) << -e);
    const int64_t lower = (units(lo) + units(f)) * r.d;
    const int64_t upper = (units(f) + units(hi)) * r.d;
    const int64_t significand = int64_t(std::ldexp(double(f), 24 - ef));
    const bool even = significand % 2 == 0;
    require((mid > lower || (mid == lower && even)) &&
            (mid < upper || (mid == upper && even)), "incorrect float rounding certificate");
    return f;
}

struct Case {
    const char* name;
    // Samples are exact integers times 2^exponent; grid values fit binary32.
    int64_t m, xp, xn, yp, yn;
    int exponent, x, y, range;
    Rational sx, sy, vertex_x, vertex_y;
    float sample(int64_t v) const {
        require(std::abs(v) <= 16777216 && exponent >= -73 && exponent <= 0,
                "sample grid out of bounds");
        const double exact = std::ldexp(double(v), exponent);
        const float stored = float(exact);
        require(double(stored) == exact, "sample grid rounded before fit");
        return stored;
    }
};

inline const std::vector<Case>& cases() {
    static const std::vector<Case> values = {
        // Captured samples in units of 1/256; vertex is -19/46.
        {"exact-pedestal", 9309806, 9309617, 9309788, 9309788, 9309617,
            -8, 0, 0, 1, {4}, {3}, {-19,46}, {19,46}},
        // p(t)=16+t-2t^2 has vertex 1/4; reverse t on y.
        {"known-dyadic-vertex", 16, 15, 13, 13, 15,
            0, 0, 0, 1, {4}, {3}, {1,4}, {-1,4}},
        // p(t)=16+t-3t^2 has vertex 1/6. Rounding it before scale
        // 5/4 gives a different float from rounding the scaled rational once.
        {"known-sixth-final-store", 16, 14, 12, 12, 14,
            0, 0, 0, 1, {5,4}, {5,4}, {1,6}, {-1,6}},
        // p(t)=32+11t-18t^2 has vertex 11/36. The scale is the
        // stored float(16/3), exactly 11184811/2097152, not real 16/3.
        {"known-float-scale", 32, 25, 3, 3, 25,
            0, 0, 0, 1, {11184811,2097152}, {11184811,2097152}, {11,36}, {-11,36}},
        {"exact-rounded-zero", 16777216, 16777216, 16777215, 16777215, 16777216,
            -24, 0, 0, 0, {4}, {3}, {1,2}, {-1,2}},
        {"exact-unique-ulp", 16777216, 16777215, 16777215, 16777215, 16777215,
            -24, 0, 0, 1, {4}, {3}, {0}, {0}},
        // Nonzero correction smaller than half an output ULP at x=3, y=-2.
        {"sub-ulp-output", 16777216, 8388608, 8388607, 8388607, 8388608,
            -24, 3, -2, 3, {1}, {1}, {100663303,33554434}, {-67108869,33554434}},
        // EPS is exactly 9444733 * 2^-73. These are adjacent exact curvatures;
        // below/equal retain the selected nonzero integer position.
        {"exact-below-guard", 0, -9444731, -1, -1, -9444731,
            -73, 1, -1, 1, {4}, {3}, {1}, {-1}},
        {"exact-at-guard", 0, -9444732, -1, -1, -9444732,
            -73, 1, -1, 1, {4}, {3}, {1}, {-1}},
        {"exact-above-guard", 0, -9444733, -1, -1, -9444733,
            -73, 1, -1, 1, {4}, {3}, {2361184,4722367}, {-2361184,4722367}},
        {"exact-unbracketed-edge", 400, 401, 398, 399, 402,
            -2, 1, -1, 1, {5,2}, {5,4}, {5,2}, {1,2}},
        // Preserve the existing positive-curvature policy, with only t=0 searched.
        {"exact-positive-curvature", 0, 2, 1, 1, 2,
            0, 0, 0, 0, {4}, {3}, {-1,6}, {1,6}},
        {"quantized-flat", 1, 1, 1, 1, 1,
            0, 0, 0, 0, {1}, {1}, {0}, {0}}
    };
    return values;
}

// Integer drops determine the interpolating polynomial exactly:
// left=m-vn, right=m-vp; p(t)=m+(left-right)t/2-(left+right)t^2/2.
// This uses the stored grid, not cancellation in float/double sample sums.
inline Rational vertex(const Case& c, bool y) {
    c.sample(c.m); c.sample(c.xp); c.sample(c.xn); c.sample(c.yp); c.sample(c.yn);
    const int64_t left = c.m - (y ? c.yn : c.xn);
    const int64_t right = c.m - (y ? c.yp : c.xp);
    const int64_t sum = left + right;
    const int pos = y ? c.y : c.x;
    require(std::abs(pos) <= 8, "position out of bounds");
    // sum has at most 26 bits here. Power-of-two scaling and promotion of the
    // float threshold are exact in binary64; no curvature rounding occurs.
    const bool fit = std::ldexp(double(std::abs(sum)), c.exponent) > double(1e-15f);
    const Rational result = fit ? Rational(2 * sum * pos + left - right, 2 * sum)
                                : Rational(pos);
    require(result == (y ? c.vertex_y : c.vertex_x), "analytic/grid vertex disagreement");
    return result;
}
inline float expected(const Case& c, bool y) {
    return rounded(vertex(c, y) * (y ? c.sy : c.sx));
}
} // namespace peak_fit_reference
#endif
