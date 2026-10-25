// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef MOTIONCORR_LOCAL_MOTION_GUARD_H
#define MOTIONCORR_LOCAL_MOTION_GUARD_H

#include <cmath>

namespace motioncorr {

// The quadratic spatial model has affine forward differences. The largest
// absolute component therefore occurs at a corner of each valid pair domain.
// Horizontal and vertical pairs have different last base pixels: neither pair
// may extend past the image. Coordinates match the reconstruction's ix/nx-0.5.
// Keep the existing component-wise bound and early exit after a failing frame.
template <typename Real, typename Model>
Real maximumNeighbourShiftDelta(const Model &model, int nx, int ny,
                                int n_frames, Real stop_above)
{
    Real largest_delta = 0;
    for (int z = 0; z < n_frames; ++z) {
        for (int axis = 0; axis < 2; ++axis) {
            if ((axis == 0 ? nx : ny) < 2) continue;
            const int last_x = nx - 1 - (axis == 0);
            const int last_y = ny - 1 - (axis == 1);
            for (int cy = 0; cy < 2; ++cy) {
                for (int cx = 0; cx < 2; ++cx) {
                    const int ix = cx ? last_x : 0;
                    const int iy = cy ? last_y : 0;
                    const Real x = Real(ix) / nx - Real(0.5);
                    const Real y = Real(iy) / ny - Real(0.5);
                    const Real next_x = Real(ix + (axis == 0)) / nx - Real(0.5);
                    const Real next_y = Real(iy + (axis == 1)) / ny - Real(0.5);
                    Real x1, y1, x2, y2;
                    model.getShiftAt(z, x, y, x1, y1);
                    model.getShiftAt(z, next_x, next_y, x2, y2);
                    if (largest_delta < std::abs(x2 - x1)) largest_delta = std::abs(x2 - x1);
                    if (largest_delta < std::abs(y2 - y1)) largest_delta = std::abs(y2 - y1);
                }
            }
        }
        if (largest_delta > stop_above) break;
    }
    return largest_delta;
}

} // namespace motioncorr
#endif
