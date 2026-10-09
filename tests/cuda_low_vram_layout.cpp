// Low-VRAM movie layout (docs/low_vram_movie_layout.md): every product a resident
// session hands the runner must be byte-identical to the default two-buffer
// layout. Each geometry runs the runner's resident sequence -- gain and sum,
// forward FFT, global alignment, inverse FFT, unweighted sum, per-patch and
// batched patch preparation, dose weighting -- once per layout and compares the
// bytes of everything that reaches the runner, plus the device Fourier frames at
// the points where the runner may download them for a CPU fallback.
//
// Movie sizes must be even (the runner and the aligner both require it); one
// geometry has odd half-sizes. Patch preparation also covers an odd-sized box,
// which the runner never produces but the layout must not care about.
// Groupings include partial last groups.

#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/image.h"
#include "src/multidim_array.h"

#include <cuda_runtime.h>
#include <cufft.h>

#include <cstdint>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

typedef std::map<std::string, std::vector<unsigned char> > Products;

template <typename T>
void put(Products &p, const std::string &key, const T *data, size_t n) {
    std::vector<unsigned char> &v = p[key];
    v.resize(n * sizeof(T));
    if (n) std::memcpy(v.data(), data, n * sizeof(T));
}

void putImage(Products &p, const std::string &key, const MultidimArray<float> &a) {
    put(p, key, a.data, (size_t)a.nzyxdim);
}

bool putFourier(Products &p, const std::string &key, CudaMovieSession &s) {
    std::vector<MultidimArray<fComplex> > F;
    if (!s.downloadFourierFrames(F)) return false;
    std::vector<unsigned char> &v = p[key];
    v.clear();
    for (const MultidimArray<fComplex> &f : F) {
        const unsigned char *b = (const unsigned char *)f.data;
        v.insert(v.end(), b, b + f.nzyxdim * sizeof(fComplex));
    }
    return true;
}

struct Geometry { int nx, ny, n_frames; };
struct Box { int x, y, w, h; };

// Periodic content drifting by a non-integer step per frame, so global and
// local alignment both find non-zero shifts, plus deterministic noise.
std::vector<Image<float> > makeFrames(const Geometry &g) {
    std::vector<Image<float> > frames(g.n_frames);
    uint32_t state = 2463534242u + (uint32_t)g.nx * 7u + (uint32_t)g.ny;
    for (int k = 0; k < g.n_frames; k++) {
        frames[k]().initZeros(g.ny, g.nx);
        const double dx = 0.7 * k, dy = -0.4 * k;
        for (int y = 0; y < g.ny; y++)
            for (int x = 0; x < g.nx; x++) {
                state ^= state << 13; state ^= state >> 17; state ^= state << 5;
                const double u = 2.0 * 3.14159265358979 * (x - dx) / g.nx;
                const double v = 2.0 * 3.14159265358979 * (y - dy) / g.ny;
                const double signal = 4.0 + 2.0 * std::sin(3 * u) * std::cos(2 * v) + std::cos(5 * u + v);
                DIRECT_A2D_ELEM(frames[k](), y, x) = (float)(signal + (state & 0xFF) / 256.0);
            }
    }
    return frames;
}

// Runs the resident sequence. Returns false (with `why`) if any step fails.
bool runArm(const Geometry &g, bool low_vram, Products &p, std::string &why) {
    std::ostringstream log;
    CudaMovieSession s(g.nx, g.ny, g.n_frames, 0, log);
    s.setLowVram(low_vram);
    const std::vector<Image<float> > frames = makeFrames(g);
    MultidimArray<float> gain;
    gain.initZeros(g.ny, g.nx);
    for (long n = 0; n < gain.nzyxdim; n++) DIRECT_MULTIDIM_ELEM(gain, n) = 0.9f + 0.001f * (n % 97);
    MultidimArray<float> unaligned;
#define STEP(name, expr) do { if (!(expr)) { why = std::string(name) + " failed\n" + log.str(); return false; } } while (0)
    STEP("initialize", s.initialize());
    STEP("isLowVram", s.isLowVram() == low_vram);
    // Without this the test would pass on two default-layout arms.
    STEP("buffer aliasing matches the layout",
         ((const void *)s.getDeviceRealFrames() == (const void *)s.getDeviceFourierFrames()) == low_vram);
    STEP("gain and sum", s.applyGainDefectsAndSum(frames, &gain, unaligned, true));
    putImage(p, "unaligned sum", unaligned);
    STEP("release preprocessing", s.releasePreprocessingBuffers());
    STEP("forward FFT", s.computeGlobalForwardFFT());
    STEP("download forward spectrum", putFourier(p, "forward spectrum", s));

    std::vector<RFLOAT> gx(g.n_frames, 0.0), gy(g.n_frames, 0.0);
    STEP("global alignment", cudaAlignPatchDevice(s.getDeviceFourierFrames(), g.n_frames, g.nx, g.ny,
                                                  150.0, gx, gy, 5, 1.0, 0, log, true));
    put(p, "global x", gx.data(), gx.size());
    put(p, "global y", gy.data(), gy.size());
    STEP("download aligned spectrum", putFourier(p, "aligned spectrum", s));

    STEP("inverse FFT", s.computeGlobalInverseFFT());
    {
        std::vector<Image<float> > real;
        STEP("download real frames", s.downloadRealFrames(real));
        for (int k = 0; k < g.n_frames; k++) putImage(p, "real frame " + std::to_string(k), real[k]());
    }
    // What the runner's CPU fallbacks after the inverse would read.
    STEP("download spectrum after inverse", putFourier(p, "spectrum after inverse", s));

    Image<float> sum, even, odd;
    sum().initZeros(g.ny, g.nx);
    even().initZeros(g.ny, g.nx);
    odd().initZeros(g.ny, g.nx);
    STEP("unweighted sum", s.reconstructUnweighted(sum, &even, &odd, nullptr));
    putImage(p, "unweighted sum", sum());
    putImage(p, "unweighted even", even());
    putImage(p, "unweighted odd", odd());

    // Patch preparation: corner, far corner, an interior odd-sized box.
    const int pw = (g.nx / 3) & ~1, ph = (g.ny / 3) & ~1;
    const Box boxes[] = {{0, 0, pw, ph}, {g.nx - pw, g.ny - ph, pw, ph},
                         {5, 7, (pw | 1), (ph | 1) - 2}};
    for (int group = 1; group <= 3; group++) {
        std::vector<int> gs, gz;
        for (int f = 0; f < g.n_frames; f += group) {
            gs.push_back(f);
            gz.push_back(std::min(group, g.n_frames - f));
        }
        const int n_groups = (int)gs.size();
        for (const Box &b : boxes) {
            const size_t n = (size_t)n_groups * b.h * (b.w / 2 + 1);
            cufftComplex *d = nullptr;
            STEP("patch buffer", cudaMalloc((void **)&d, n * sizeof(cufftComplex)) == cudaSuccess);
            const bool ok = s.preparePatchInVram(b.x, b.y, b.w, b.h, n_groups, gs.data(), gz.data(), d);
            std::vector<cufftComplex> h(n);
            const bool copied = ok && cudaMemcpy(h.data(), d, n * sizeof(cufftComplex),
                                                 cudaMemcpyDeviceToHost) == cudaSuccess;
            cudaFree(d);
            STEP("patch preparation", copied);
            std::ostringstream key;
            key << "patch " << b.x << "," << b.y << " " << b.w << "x" << b.h << " group " << group;
            put(p, key.str(), h.data(), n);
        }
        std::vector<CudaMovieSession::PatchBox> pboxes;
        for (int iy = 0; iy < 2; iy++)
            for (int ix = 0; ix < 3; ix++)
                pboxes.push_back({ix * (g.nx - pw) / 2, iy * (g.ny - ph), pw, ph});
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        s.alignPatchesBatched(pboxes, n_groups, gs.data(), gz.data(), 150.0, 5, 1.0, 4, out);
        for (size_t j = 0; j < out.size(); j++) {
            STEP("batched patch alignment", out[j].done);
            std::ostringstream key;
            key << "batched patch " << j << " group " << group;
            put(p, key.str() + " x", out[j].xshifts.data(), out[j].xshifts.size());
            put(p, key.str() + " y", out[j].yshifts.data(), out[j].yshifts.size());
        }
        STEP("release patch workspaces", s.releasePatchAlignmentWorkspace());
    }

    std::vector<RFLOAT> doses(g.n_frames);
    for (int k = 0; k < g.n_frames; k++) doses[k] = 1.277 * (k + 1);
    Image<float> dw;
    dw().initZeros(g.ny, g.nx);
    STEP("dose-weighted sum", s.reconstructDoseWeighted(dw, doses, 1.0, nullptr));
    putImage(p, "dose-weighted sum", dw());
    STEP("download spectrum after dose weighting", putFourier(p, "spectrum after dose weighting", s));

    if (low_vram) {
        // The layout's invariant: after dose weighting the real frames are gone,
        // and handing out stale bytes would be wrong. Refusal is the contract.
        std::vector<Image<float> > real;
        STEP("real frames refused after dose weighting", !s.downloadRealFrames(real));
        STEP("second forward FFT refused", !s.computeGlobalForwardFFT());
        STEP("no failure recorded by refusals", !s.getFailureState().hasFailed());
    }
#undef STEP
    return true;
}

} // namespace

int main() {
    int devices = 0;
    if (cudaGetDeviceCount(&devices) != cudaSuccess || devices == 0) {
        std::cout << "SKIP: no CUDA device\n";
        return 77;
    }
    const Geometry geoms[] = {{256, 192, 7}, {250, 198, 9}, {330, 222, 5}};
    int failures = 0;
    for (const Geometry &g : geoms) {
        Products a, b;
        std::string why;
        if (!runArm(g, false, a, why) || !runArm(g, true, b, why)) {
            std::cerr << "FAIL " << g.nx << "x" << g.ny << "x" << g.n_frames << ": " << why;
            failures++;
            continue;
        }
        int diff = 0;
        for (const auto &kv : a) {
            auto it = b.find(kv.first);
            if (it == b.end() || it->second != kv.second || kv.second.empty()) {
                std::cerr << "FAIL " << g.nx << "x" << g.ny << "x" << g.n_frames << ": '"
                          << kv.first << "' differs between layouts\n";
                diff++;
            }
        }
        if (a.size() != b.size()) diff++;
        std::cout << (diff ? "FAIL " : "PASS ") << g.nx << "x" << g.ny << "x" << g.n_frames
                  << ": " << a.size() << " products compared, " << diff << " differ\n";
        failures += diff;
    }
    return failures == 0 ? 0 : 1;
}
