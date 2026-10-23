// SPDX-License-Identifier: GPL-2.0-or-later
#include "src/local_motion_guard.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <string>

// Independent spatial polynomial, including both output components and cubic
// time dependence. Exhaustive reference below visits integer pixel pairs, not
// the production helper's rectangle corners.
struct Polynomial {
    std::array<long double, 6> x{}, y{}; // 1, x, y, x*x, y*y, x*y
    std::array<long double, 3> time{1, 0, 0}; // z, z*z, z*z*z

    static long double value(const std::array<long double, 6> &c,
                             long double x, long double y)
    {
        return c[0] + c[1]*x + c[2]*y + c[3]*x*x + c[4]*y*y + c[5]*x*y;
    }
    template <typename Real>
    void getShiftAt(int frame, Real px, Real py, Real &sx, Real &sy) const
    {
        const long double z = frame;
        const long double t = time[0]*z + time[1]*z*z + time[2]*z*z*z;
        sx = Real(t * value(x, px, py));
        sy = Real(t * value(y, px, py));
    }
};

long double exhaustive(const Polynomial &p, int nx, int ny, int frames)
{
    long double largest = 0;
    for (int f = 0; f < frames; ++f) {
        const long double z = f;
        const long double t = p.time[0]*z + p.time[1]*z*z + p.time[2]*z*z*z;
        for (int iy = 0; iy < ny; ++iy) {
            for (int ix = 0; ix < nx; ++ix) {
                const long double x = (long double)ix/nx - 0.5L;
                const long double y = (long double)iy/ny - 0.5L;
                for (const auto &c : {p.x, p.y}) {
                    const long double base = t * Polynomial::value(c, x, y);
                    if (ix + 1 < nx) {
                        const long double next = t * Polynomial::value(c, (long double)(ix+1)/nx - 0.5L, y);
                        largest = std::max(largest, std::abs(next - base));
                    }
                    if (iy + 1 < ny) {
                        const long double next = t * Polynomial::value(c, x, (long double)(iy+1)/ny - 0.5L);
                        largest = std::max(largest, std::abs(next - base));
                    }
                }
            }
        }
    }
    return largest;
}

int main()
{
    int checks = 0, failed = 0;
    auto check = [&](bool ok, const std::string &name) {
        ++checks;
        if (!ok) { ++failed; std::cerr << "FAIL " << name << '\n'; }
    };
    auto witness = [&](const std::string &name, const Polynomial &p, int nx, int ny,
                       double expected, bool accepted) {
        const double got = motioncorr::maximumNeighbourShiftDelta<double>(p, nx, ny, 2, 3.0);
        check(std::abs(got - expected) < 2e-11, name + " finite-pair maximum");
        check((got <= 3.0) == accepted, name + " unchanged strict threshold");
    };
    Polynomial p;
    p.x = {0, 200, 0, -200, 0, 0};
    witness("legacy accepted harmful x", p, 100, 80, 3.98, false);
    p.x = {0, 100, 0, 200, 0, 0};
    witness("legacy rejected valid x", p, 100, 80, 2.94, true);
    p.x = {}; p.y = {0, 0, 200, 0, -200, 0};
    witness("legacy accepted harmful y", p, 80, 100, 3.98, false);
    p.y = {0, 0, 100, 0, 200, 0};
    witness("legacy rejected valid y", p, 80, 100, 2.94, true);
    p.y = {}; p.x = {0, 0, 0, 0, 0, 768};
    witness("cross term exactly at threshold", p, 128, 128, 3, true);
    p.x[5] = 769;
    witness("cross term above threshold", p, 128, 128, 769.0/256, false);
    p.x = {0, 8, 0, 8, 0, 0};
    witness("last horizontal pair stays inside image", p, 4, 3, 2.5, true);
    p.x = {}; p.y = {0, 0, 8, 0, 8, 0};
    witness("last vertical pair stays inside image", p, 3, 4, 2.5, true);
    p.x = {37, 0, 0, 0, 0, 0}; p.y = {-19, 0, 0, 0, 0, 0};
    witness("translation", p, 7, 11, 0, true);
    p.x = {5, 7, -11, 0, 0, 0}; p.y = {};
    witness("affine", p, 100, 80, 11.0/80, true);

    const std::array<std::array<long double, 6>, 5> polynomials{{
        {{0, 200, 0, -200, 0, 0}}, {{0, 100, 0, 200, 0, 0}},
        {{3, -7, 11, 13, -17, 19}}, {{0, 0, 0, 0, 0, 600}},
        {{5, 7, -11, 0, 0, 0}}
    }};
    for (const auto &shape : {std::array<int,2>{1,1}, {1,5}, {5,1}, {2,2}, {7,11}, {100,80}}) {
        for (std::size_t i = 0; i < polynomials.size(); ++i) {
            p.x = polynomials[i]; p.y = polynomials[(i+2)%polynomials.size()];
            p.time = {1, -0.25L, 0.0625L};
            const auto ref = exhaustive(p, shape[0], shape[1], 5);
            const auto got = motioncorr::maximumNeighbourShiftDelta<double>(
                p, shape[0], shape[1], 5, std::numeric_limits<double>::infinity());
            check(std::abs(got - ref) < 2e-10L, "exhaustive grid " + std::to_string(shape[0]) + "x" + std::to_string(shape[1]) + " polynomial " + std::to_string(i));
        }
    }
    // Frame 1 is below threshold, frame 2 is above it; preserve frame-wise stop.
    p = Polynomial{}; p.x[1] = 200;
    check(motioncorr::maximumNeighbourShiftDelta<double>(p, 100, 80, 5, 3.0) == 4.0,
          "first failing frame retained");
    std::cout << (failed ? "FAIL" : "PASS") << " checks=" << checks << " failed=" << failed << '\n';
    return failed ? 1 : 0;
}
