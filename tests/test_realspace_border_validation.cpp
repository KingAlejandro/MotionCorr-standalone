// SPDX-License-Identifier: GPL-2.0-or-later
// Host controls for the actual CUDA border test predicate; no GPU warp runs here.
#include "realspace_border_validation.h"
#include <iostream>
#include <limits>
#include <string>

namespace {
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
} // namespace

int main() try {
    struct FiniteCase { double actual, expected; bool differs; };
    const FiniteCase finite[] = {
        {7.0, 7.0, false},
        {7.0, 7.025, false},
        {0.0, std::nextafter(0.05, 0.0), false},
        {0.0, 0.05, true},
        {0.0, std::nextafter(0.05, 1.0), true},
        {0.05, 0.0, true},
        {7.0, 7.5, true},
        {7.5, 7.0, true},
    };
    for (const auto &c : finite) {
        double error = -1.0;
        require(realspace_border_test::pixelDiffers(c.actual, c.expected,
                    "finite control", 3, 4, error) == c.differs,
                "finite pixel classification changed");
        require(error == std::fabs(c.actual - c.expected), "wrong finite error");
    }

    const double values[] = {7.0, std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
    int rejected = 0;
    // Includes each nonfinite value on either side alone, and all nine pairs
    // with both sides nonfinite (in particular Inf - Inf and NaN - NaN).
    for (int a = 0; a < 4; ++a)
        for (int e = 0; e < 4; ++e) {
            if (a == 0 && e == 0) continue;
            double error = -1.0;
            bool threw = false;
            try {
                realspace_border_test::pixelDiffers(values[a], values[e],
                    "nonfinite control", 3, 4, error);
            } catch (const std::runtime_error &exc) {
                const std::string message = exc.what();
                require(message.find("nonfinite control: nonfinite pixel at x=3 y=4, got ") == 0
                            && message.find(" want ") != std::string::npos,
                        "nonfinite failure lost its case/pixel/value diagnostic");
                threw = true;
            }
            require(threw, "accepted nonfinite actual or expected pixel");
            require(error == -1.0, "computed error before rejecting nonfinite pixel");
            ++rejected;
        }
    std::cout << "PASS: 8 finite controls and " << rejected << " nonfinite rejections\n";
    return 0;
} catch (const std::exception &exc) {
    std::cerr << "FAIL: " << exc.what() << '\n';
    return 1;
}
