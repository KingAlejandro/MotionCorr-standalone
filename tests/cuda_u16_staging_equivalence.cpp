// CUDA hardware control for Issue #85 lane C.
//
// applyGainDefectsAndSumU16 stages the movie in its native unsigned 16-bit form and
// expands it on the device; applyGainDefectsAndSum takes the same movie already
// widened to float on the host. The claim is that the two produce bit-identical
// device state, so this compares BOTH outputs of the preprocessing stage -- the
// unaligned sum and the resident frame buffer -- as raw bytes.
//
// Downloading the frames is the part that matters and the part no other test covers.
// The float kernel writes back to d_Iframes only when a gain is applied; without one
// the H2D copy is the sole writer. The uint16 path has no such copy, so a missing
// unconditional store would leave d_Iframes uninitialised while the sum stayed
// correct -- invisible to any sum-based check, and consumed by the FFT.
//
// Case 3 uses a gain containing zero, a negative entry and a tiny entry. The negative
// entry is there for the zero-sample product: 0.0f * -1.5f is -0.0f, which a seeded
// accumulator would turn into +0.0f while a zeroed one keeps as -0.0f.

#include "src/acc/cuda/cuda_movie_session.h"
#include "src/image.h"
#include "src/multidim_array.h"

#include <cuda_runtime.h>
#include <cstring>
#include <iostream>
#include <sstream>
#include <vector>

namespace {

const int NX = 61;   // deliberately not a multiple of the 256-thread block
const int NY = 47;
const int NFRAMES = 5;

unsigned short sample(int iframe, long int pixel) {
    // Spans the whole uint16 range and pins the endpoints, so the widening is
    // exercised at 0 and 65535 rather than only in the middle.
    if (pixel == 0) return 0;
    if (pixel == 1) return 65535;
    if (pixel == 2) return 32768;
    return (unsigned short)((pixel * 7919 + iframe * 104729) % 65536);
}

struct Arm {
    MultidimArray<float> sum;
    std::vector<Image<float> > frames;
};

bool runFloatArm(const std::vector<Image<float> > &in, const MultidimArray<float> *gain,
                 Arm &out, std::ostream &log) {
    CudaMovieSession s(NX, NY, NFRAMES, 0, log);
    if (!s.initialize()) return false;
    if (!s.applyGainDefectsAndSum(in, gain, out.sum, true)) return false;
    return s.downloadRealFrames(out.frames);
}

bool runU16Arm(const std::vector<Image<unsigned short> > &in, const MultidimArray<float> *gain,
               Arm &out, std::ostream &log) {
    CudaMovieSession s(NX, NY, NFRAMES, 0, log);
    if (!s.initialize()) return false;
    if (!s.applyGainDefectsAndSumU16(in, gain, out.sum, true)) return false;
    return s.downloadRealFrames(out.frames);
}

// Raw bytes, not a tolerance: the whole point of the change is that nothing moves.
bool identical(const Arm &a, const Arm &b, std::string &why) {
    const size_t n = (size_t)NX * NY;
    if (a.sum.nzyxdim != b.sum.nzyxdim) { why = "sum size differs"; return false; }
    if (std::memcmp(a.sum.data, b.sum.data, n * sizeof(float)) != 0) {
        why = "unaligned sum differs";
        return false;
    }
    if (a.frames.size() != b.frames.size()) { why = "frame count differs"; return false; }
    for (size_t f = 0; f < a.frames.size(); f++) {
        if (std::memcmp(a.frames[f]().data, b.frames[f]().data, n * sizeof(float)) != 0) {
            std::ostringstream os;
            os << "resident frame " << f << " differs";
            why = os.str();
            return false;
        }
    }
    return true;
}

} // namespace

int main() {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "CUDA device 0 is required for this control\n";
        return 1;
    }
    std::ostringstream log;
    const long int n = (long int)NX * NY;

    std::vector<Image<unsigned short> > u16(NFRAMES);
    std::vector<Image<float> > f32(NFRAMES);
    for (int i = 0; i < NFRAMES; i++) {
        u16[i]().reshape(NY, NX);
        f32[i]().reshape(NY, NX);
        for (long int p = 0; p < n; p++) {
            const unsigned short v = sample(i, p);
            DIRECT_MULTIDIM_ELEM(u16[i](), p) = v;
            // This is exactly what castPage2T's UShort branch does for T=float.
            DIRECT_MULTIDIM_ELEM(f32[i](), p) = (float)v;
        }
    }

    MultidimArray<float> gain_plain(NY, NX), gain_hostile(NY, NX);
    for (long int p = 0; p < n; p++) {
        DIRECT_MULTIDIM_ELEM(gain_plain, p) = 0.5f + (float)(p % 17) / 32.0f;
        float g = 1.0f + (float)(p % 9) / 8.0f;
        if (p % 101 == 0) g = 0.0f;         // dead pixel, as a real gain has
        if (p % 103 == 0) g = -1.5f;        // sign change: makes 0 * g == -0.0f
        if (p % 107 == 0) g = 1.0e-30f;     // near-denormal product
        DIRECT_MULTIDIM_ELEM(gain_hostile, p) = g;
    }

    struct Case { const char *name; const MultidimArray<float> *gain; };
    const Case cases[] = {
        {"no gain",      nullptr},
        {"plain gain",   &gain_plain},
        {"hostile gain", &gain_hostile},
    };

    int failures = 0;
    for (const Case &c : cases) {
        Arm a, b;
        if (!runFloatArm(f32, c.gain, a, log)) {
            std::cerr << "FAIL " << c.name << ": float arm did not complete\n" << log.str();
            return 1;
        }
        if (!runU16Arm(u16, c.gain, b, log)) {
            std::cerr << "FAIL " << c.name << ": uint16 arm did not complete\n" << log.str();
            return 1;
        }
        std::string why;
        if (identical(a, b, why)) {
            std::cout << "PASS " << c.name << ": sum and all " << NFRAMES
                      << " resident frames are byte-identical\n";
        } else {
            std::cerr << "FAIL " << c.name << ": " << why << "\n";
            failures++;
        }
    }

    // Negative control. A comparison that cannot fail proves nothing, so perturb one
    // sample of one frame by one count and require the same comparison to report it.
    {
        std::vector<Image<unsigned short> > tampered = u16;
        unsigned short &v = DIRECT_MULTIDIM_ELEM(tampered[NFRAMES / 2](), n / 2);
        v = (unsigned short)(v ^ 1u);
        Arm a, b;
        if (!runFloatArm(f32, &gain_plain, a, log) ||
            !runU16Arm(tampered, &gain_plain, b, log)) {
            std::cerr << "FAIL negative control: an arm did not complete\n" << log.str();
            return 1;
        }
        std::string why;
        if (identical(a, b, why)) {
            std::cerr << "FAIL negative control: a one-count change was not detected, "
                         "so the comparison above is vacuous\n";
            failures++;
        } else {
            std::cout << "PASS negative control: one-count change detected (" << why << ")\n";
        }
    }

    // Second negative control, for the other oracle. The check above short-circuits
    // on the sum, so it never demonstrated that the per-frame comparison can fail.
    // Perturb one downloaded frame value directly and require that branch to report it.
    {
        Arm a, b;
        if (!runFloatArm(f32, &gain_plain, a, log) || !runU16Arm(u16, &gain_plain, b, log)) {
            std::cerr << "FAIL frame-oracle control: an arm did not complete\n" << log.str();
            return 1;
        }
        std::string why;
        if (!identical(a, b, why)) {
            std::cerr << "FAIL frame-oracle control: the unperturbed pair already differs ("
                      << why << ")\n";
            failures++;
        } else {
            const int k = NFRAMES - 1;
            float &v = DIRECT_MULTIDIM_ELEM(b.frames[k](), n / 3);
            v = -v - 1.0f;   // changes the bits for every finite value, including 0
            if (identical(a, b, why)) {
                std::cerr << "FAIL frame-oracle control: a changed resident frame was not "
                             "detected, so the frame comparison above is vacuous\n";
                failures++;
            } else {
                std::cout << "PASS frame-oracle control: changed resident frame detected ("
                          << why << ")\n";
            }
        }
    }

    if (failures) {
        std::cerr << failures << " check(s) failed\n";
        return 1;
    }
    std::cout << "All uint16 staging equivalence checks passed\n";
    return 0;
}
