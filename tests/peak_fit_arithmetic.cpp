// SPDX-License-Identifier: GPL-2.0-or-later
#include "peak_fit_reference.h"
#include <iomanip>
#include <iostream>
#include <string>

namespace ref = peak_fit_reference;

// Host replay of the specified arithmetic, NOT the independent oracle and NOT
// a production-kernel execution. Named alterations must fail the same fixtures.
static float replay(const ref::Case& c, bool y, const std::string& mutation) {
    const float m = c.sample(c.m), p = c.sample(y ? c.yp : c.xp), n = c.sample(y ? c.yn : c.xn);
    const int pos = y ? c.y : c.x;
    const float scale = ref::rounded(y ? c.sy : c.sx);
    const double d = mutation == "float-denominator" ? double(p + n - 2.0f * m)
        : double(p) + double(n) - 2.0 * double(m);
    const double v = std::abs(d) > double(1e-15f) ? pos - 0.5 * (double(p) - double(n)) / d : pos;
    if (mutation == "early-store") return float(v) * scale;
    if (mutation == "wrong-scale" && std::string(c.name) == "known-float-scale")
        return float(v * (16.0 / 3.0));
    return float(v * double(scale));
}

int main(int argc, char** argv) {
    try {
        const bool expect_mismatch = argc == 3 && std::string(argv[1]) == "--expect-mismatch";
        const std::string mutation = expect_mismatch ? argv[2] : (argc == 2 ? argv[1] : "none");
        ref::require((argc <= 2 || expect_mismatch) && (mutation == "none" || mutation == "float-denominator" ||
            mutation == "early-store" || mutation == "wrong-scale"), "unknown replay mutation");
        int mismatches = 0;
        bool pedestal = false, rounded_zero = false, early_store = false, wrong_scale = false;
        for (const auto& c : ref::cases()) {
            const float ex = ref::expected(c, false), ey = ref::expected(c, true);
            const float x = replay(c, false, mutation), y = replay(c, true, mutation);
            const bool ok = x == ex && y == ey;
            mismatches += !ok;
            const std::string name(c.name);
            if (name == "exact-pedestal") pedestal = !ok;
            if (name == "exact-rounded-zero") rounded_zero = !ok;
            if (name == "known-sixth-final-store") early_store = !ok;
            if (name == "known-float-scale") wrong_scale = !ok;
            std::cout << std::setprecision(17) << c.name << " got=" << x << ',' << y
                      << " exact-rounded=" << ex << ',' << ey << " match=" << ok << '\n';
        }
        // A known real parabola whose three samples all round to float(1).
        // Its curvature exceeds EPS, but the stored map is flat: information
        // loss in the map is distinct from the exact fit on the stored samples.
        const double k = std::ldexp(1.0, -28), h = 0.25;
        for (int t = -1; t <= 1; ++t)
            ref::require(float(1.0 - k * (t - h) * (t - h)) == 1.0f, "quantization witness changed");
        std::cout << "quantization: analytic_vertex=0.25 stored_fit_fallback=0 "
                     "map_error=0.25 fit_error_on_stored_samples=0\n";
        // Exercise the rounding certificate's tie-to-even decision too.
        ref::require(ref::rounded({16777217,16777216}) == 1.0f, "lower even midpoint");
        ref::require(ref::rounded({16777219,16777216}) == std::nextafter(
            std::nextafter(1.0f, 2.0f), 2.0f), "upper even midpoint");
        if (mutation == "float-denominator")
            ref::require(pedestal && rounded_zero, "float denominator missed named witnesses");
        if (mutation == "early-store") ref::require(early_store, "early store missed named witness");
        if (mutation == "wrong-scale") ref::require(wrong_scale, "wrong scale missed named witness");
        std::cout << "replay=" << mutation << " mismatches=" << mismatches << '\n';
        return expect_mismatch ? (mismatches ? 0 : 1) : (mismatches ? 1 : 0);
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 2;
    }
}
