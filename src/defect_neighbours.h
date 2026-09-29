#ifndef DEFECT_NEIGHBOURS_H_
#define DEFECT_NEIGHBOURS_H_

#include <cstddef>

/**
 * Hot-pixel replacement neighbourhood, factored out so the resident CUDA path can
 * fetch one pixel per (defect, frame) instead of downloading the whole movie.
 *
 * The original loop fills a buffer with every valid neighbour of a defect, in window
 * raster order, then picks entry rand() % n_ok. Two facts make the sparse form exact
 * rather than merely equivalent:
 *
 *  - n_ok depends only on the defect mask and the image bounds, never on pixel
 *    values, so it can be computed before any frame data exists;
 *  - the draw is therefore an index into a value-independent ordering, so the chosen
 *    neighbour can be resolved to a coordinate and fetched afterwards.
 *
 * Keeping the same two functions on both paths is what keeps the RNG stream and the
 * selected value identical: callers must still call rand() exactly when
 * n_ok > NUM_MIN_OK, in the same defect-then-frame order, because rnd_gaus() draws
 * from the same stream on the other branch.
 */
namespace mc_defect {

/**
 * Number of in-bounds, non-defective neighbours of (cy, cx) in the +/- d_max window.
 * Mirrors the original gather loop's accept condition exactly.
 */
template <class MaskT>
inline int countValidNeighbours(const MaskT &is_bad, int nx, int ny,
                                int cy, int cx, int d_max) {
    int n_ok = 0;
    for (int dy = -d_max; dy <= d_max; dy++) {
        const int y = cy + dy;
        if (y < 0 || y >= ny) continue;
        for (int dx = -d_max; dx <= d_max; dx++) {
            const int x = cx + dx;
            if (x < 0 || x >= nx) continue;
            if (is_bad(y, x)) continue;
            n_ok++;
        }
    }
    return n_ok;
}

/**
 * Coordinate of the rank-th valid neighbour in the same window raster order the
 * gather loop uses, so rank == the index the original code would have taken from its
 * buffer. Returns false if rank is out of range, leaving the outputs untouched.
 */
template <class MaskT>
inline bool nthValidNeighbour(const MaskT &is_bad, int nx, int ny,
                              int cy, int cx, int d_max, int rank,
                              int *out_y, int *out_x) {
    if (rank < 0) return false;
    int seen = 0;
    for (int dy = -d_max; dy <= d_max; dy++) {
        const int y = cy + dy;
        if (y < 0 || y >= ny) continue;
        for (int dx = -d_max; dx <= d_max; dx++) {
            const int x = cx + dx;
            if (x < 0 || x >= nx) continue;
            if (is_bad(y, x)) continue;
            if (seen == rank) { *out_y = y; *out_x = x; return true; }
            seen++;
        }
    }
    return false;
}

} // namespace mc_defect

#endif // DEFECT_NEIGHBOURS_H_
