// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef MOTIONCORR_TEST_REALSPACE_BORDER_VALIDATION_H
#define MOTIONCORR_TEST_REALSPACE_BORDER_VALIDATION_H

#include <cmath>
#include <sstream>
#include <stdexcept>

namespace realspace_border_test {
// Shared by the CUDA regression and its device-free validation controls.
// Nonfinite data is a test failure even in --expect-mismatch mode.
inline bool pixelDiffers(double actual, double expected, const char *case_name,
                         int x, int y, double &error) {
    if (!std::isfinite(actual) || !std::isfinite(expected)) {
        std::ostringstream message;
        message << case_name << ": nonfinite pixel at x=" << x << " y=" << y
                << ", got " << actual << " want " << expected;
        throw std::runtime_error(message.str());
    }
    error = std::fabs(actual - expected);
    return error >= 0.05;
}
} // namespace realspace_border_test

#endif
