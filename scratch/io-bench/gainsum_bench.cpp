// Isolates MotionCorr's "apply gain and initial sum" loop from the rest of the
// pipeline, so the same stage can be compared across machines in seconds
// instead of a four-minute run.
//
// untiled = the shape on main: pixels outer, frames inner, so each inner step
//           jumps to a different one of n_frames separate multi-MB buffers.
// tiled   = the shape on the branch: a tile of pixels walked through every
//           frame, which keeps the tile's slice of the sum and the gain in
//           cache and makes each frame one sequential run.
//
// Both accumulate frames in the same order into a float, so the sums are
// bit-identical; only the traversal order differs. The checksum proves it.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <omp.h>

static double now_s() {
    using namespace std::chrono;
    return duration<double>(steady_clock::now().time_since_epoch()).count();
}

int main(int argc, char **argv) {
    const long nx     = (argc > 1) ? atol(argv[1]) : 3710;
    const long ny     = (argc > 2) ? atol(argv[2]) : 3838;
    const int  nf     = (argc > 3) ? atoi(argv[3]) : 24;
    const int  thr    = (argc > 4) ? atoi(argv[4]) : 8;
    const int  reps   = (argc > 5) ? atoi(argv[5]) : 3;
    const long tile   = (argc > 6) ? atol(argv[6]) : 4096;
    const long npix   = nx * ny;

    std::vector<float*> frames(nf);
    for (int f = 0; f < nf; f++) {
        frames[f] = (float*)malloc(sizeof(float) * npix);
        for (long p = 0; p < npix; p++) frames[f][p] = (float)((p + f) % 4096) * 0.25f;
    }
    std::vector<float> gain(npix), sum(npix);
    for (long p = 0; p < npix; p++) gain[p] = 1.0f + (float)(p % 7) * 1e-3f;

    const double gib = (double)nf * npix * 4 / (1<<30);
    printf("geometry %ldx%ld x %d frames = %.2f GiB of float, threads=%d, tile=%ld, reps=%d\n",
           nx, ny, nf, gib, thr, tile, reps);

    auto restore = [&]() {
        for (int f = 0; f < nf; f++)
            for (long p = 0; p < npix; p++) frames[f][p] = (float)((p + f) % 4096) * 0.25f;
    };
    auto checksum = [&]() { double s = 0; for (long p = 0; p < npix; p++) s += sum[p]; return s; };

    double best_u = 1e30, best_t = 1e30, cu = 0, ct = 0;
    for (int r = 0; r < reps; r++) {
        restore();
        double t0 = now_s();
        #pragma omp parallel for num_threads(thr)
        for (long pixel = 0; pixel < npix; pixel++) {
            float s = 0.0f;
            for (int f = 0; f < nf; f++) { frames[f][pixel] *= gain[pixel]; s += frames[f][pixel]; }
            sum[pixel] = s;
        }
        best_u = std::min(best_u, now_s() - t0);
        cu = checksum();

        restore();
        t0 = now_s();
        #pragma omp parallel for num_threads(thr) schedule(static)
        for (long base = 0; base < npix; base += tile) {
            const long end = std::min(base + tile, npix);
            for (long p = base; p < end; p++) sum[p] = 0.0f;
            for (int f = 0; f < nf; f++) {
                float *fp = frames[f];
                for (long p = base; p < end; p++) { fp[p] *= gain[p]; sum[p] += fp[p]; }
            }
        }
        best_t = std::min(best_t, now_s() - t0);
        ct = checksum();
    }

    // One movie's worth of traffic: read+write every frame, plus gain and sum.
    const double gb = ((double)nf * npix * 4 * 2 + npix * 4 * 2) / 1e9;
    printf("untiled (main)   best %8.3f s   %6.1f GB/s   checksum %.6e\n", best_u, gb / best_u, cu);
    printf("tiled   (branch) best %8.3f s   %6.1f GB/s   checksum %.6e\n", best_t, gb / best_t, ct);
    printf("speedup %.2fx   checksums %s\n", best_u / best_t, (cu == ct) ? "IDENTICAL" : "DIFFER");
    for (int f = 0; f < nf; f++) free(frames[f]);
    return (cu == ct) ? 0 : 1;
}
