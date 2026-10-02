// CUDA hardware control for Issue #85 lane C.
//
// applyGainDefectsAndSumU8/U16 stage a movie in its native unsigned sample type and
// expand it on the device; applyGainDefectsAndSum takes the same movie already
// widened to float on the host. The claim is that the two produce bit-identical
// device state, so this compares BOTH outputs of the preprocessing stage -- the
// unaligned sum and the resident frame buffer -- as raw bytes.
//
// Downloading the frames is the part that matters and the part no other test covers.
// The float kernel writes back to d_Iframes only when a gain is applied; without one
// the H2D copy is the sole writer. The native paths have no such copy, so a missing
// unconditional store would leave d_Iframes uninitialised while the sum stayed
// correct -- invisible to any sum-based check, and consumed by the FFT.
//
// Case 3 uses a gain containing zero, a negative entry and a subnormal entry. The
// negative entry is there for the zero-sample product: 0.0f * -1.5f is -0.0f. The
// reference accumulator starts at +0.0f, and +0.0f + (-0.0f) is +0.0f, so each native
// path must memset d_Isum rather than seed it with frame 0's value -- a seeded store
// would keep -0.0f. That distinction is only observable if the fixture actually
// contains a zero sample under a negative gain entry, which assertFixture() checks.

#include "src/acc/cuda/cuda_movie_session.h"
#include "src/image.h"
#include "src/multidim_array.h"

#include <cuda_runtime.h>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <sstream>
#include <vector>

namespace {

const int NX = 61;   // deliberately not a multiple of the 256-thread block
const int NY = 47;
const int NFRAMES = 5;

// Pixels whose gain entry is pinned below. Chosen so each lands on a distinct pixel.
const long int PIX_GAIN_ZERO     = 101;
const long int PIX_GAIN_NEGATIVE = 103;
const long int PIX_GAIN_SUBNORMAL = 107;

template <typename T>
T sample(int iframe, long int pixel) {
    // Pin 0/max/midpoint for both unsigned widths: the uint8 case observes
    // 255 (and values above 127), so signed reinterpretation cannot pass.
    const unsigned long range = (unsigned long)std::numeric_limits<T>::max() + 1;
    if (pixel == 0) return 0;
    if (pixel == 1) return std::numeric_limits<T>::max();
    if (pixel == 2) return (T)(range / 2);
    // A zero sample on the negative-gain pixel, so the -0.0f product exists.
    if (pixel == PIX_GAIN_NEGATIVE) return 0;
    return (T)((pixel * 7919 + iframe * 104729) % range);
}

bool poisonFrames(CudaMovieSession &s);

struct Arm {
    MultidimArray<float> sum;
    std::vector<Image<float> > frames;
};

bool runFloatArm(const std::vector<Image<float> > &in, const MultidimArray<float> *gain,
                 Arm &out, std::ostream &log) {
    CudaMovieSession s(NX, NY, NFRAMES, 0, log);
    if (!s.initialize()) return false;
    if (!poisonFrames(s)) return false;
    if (!s.applyGainDefectsAndSum(in, gain, out.sum, true)) return false;
    return s.downloadRealFrames(out.frames);
}

// Both arms poison the resident frame buffer before running. Without this the frame
// comparison can be vacuous: the two arms run back to back, cudaMalloc does not zero
// reused memory, and the native arm's d_Iframes is likely to come back holding the
// float arm's just-freed contents -- which are exactly the expected answer. Dropping
// the native kernel's unconditional store would then still pass. 0xA5A5A5A5 is a
// finite float that no legitimate value here can equal.
bool poisonFrames(CudaMovieSession &s) {
    return cudaMemset(s.getDeviceRealFrames(), 0xA5,
                      (size_t)NX * NY * NFRAMES * sizeof(float)) == cudaSuccess &&
           cudaMemset(s.getDeviceUnalignedSum(), 0xA5,
                      (size_t)NX * NY * sizeof(float)) == cudaSuccess;
}

// Overloads select the actual public production entry point for each width.
bool applyNative(CudaMovieSession &s, const std::vector<Image<unsigned short> > &in,
                 const MultidimArray<float> *gain, MultidimArray<float> &sum) {
    return s.applyGainDefectsAndSumU16(in, gain, sum, true);
}
bool applyNative(CudaMovieSession &s, const std::vector<Image<unsigned char> > &in,
                 const MultidimArray<float> *gain, MultidimArray<float> &sum) {
    return s.applyGainDefectsAndSumU8(in, gain, sum, true);
}

template <typename T>
bool runNativeArm(const std::vector<Image<T> > &in, const MultidimArray<float> *gain,
                  Arm &out, std::ostream &log) {
    CudaMovieSession s(NX, NY, NFRAMES, 0, log);
    if (!s.initialize()) return false;
    if (!poisonFrames(s)) return false;
    if (!applyNative(s, in, gain, out.sum)) return false;
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

template <typename T>
int runContract(const char *width) {
    std::cout << "Native staging contract: " << width << "\n";
    std::ostringstream log;
    const long int n = (long int)NX * NY;

    std::vector<Image<T> > native(NFRAMES);
    std::vector<Image<float> > f32(NFRAMES);
    for (int i = 0; i < NFRAMES; i++) {
        native[i]().reshape(NY, NX);
        f32[i]().reshape(NY, NX);
        for (long int p = 0; p < n; p++) {
            const T v = sample<T>(i, p);
            DIRECT_MULTIDIM_ELEM(native[i](), p) = v;
            // Exactly the unsigned reader's conversion to float.
            DIRECT_MULTIDIM_ELEM(f32[i](), p) = (float)v;
        }
    }

    MultidimArray<float> gain_plain(NY, NX), gain_hostile(NY, NX);
    for (long int p = 0; p < n; p++) {
        DIRECT_MULTIDIM_ELEM(gain_plain, p) = 0.5f + (float)(p % 17) / 32.0f;
        float g = 1.0f + (float)(p % 9) / 8.0f;
        if (p == PIX_GAIN_ZERO)      g = 0.0f;      // dead pixel, as a real gain has
        if (p == PIX_GAIN_NEGATIVE)  g = -1.5f;     // sign change: 0 * g == -0.0f
        if (p == PIX_GAIN_SUBNORMAL) g = 1.0e-44f;  // every product is subnormal
        DIRECT_MULTIDIM_ELEM(gain_hostile, p) = g;
    }

    // A fixture that does not contain the cases the comment claims makes every
    // assertion below vacuous for those cases. Count them rather than assume them.
    {
        long int neg_zero_products = 0, zero_gain = 0, subnormal_products = 0;
        for (int i = 0; i < NFRAMES; i++) {
            for (long int p = 0; p < n; p++) {
                const float v = (float)DIRECT_MULTIDIM_ELEM(native[i](), p);
                const float g = DIRECT_MULTIDIM_ELEM(gain_hostile, p);
                const float prod = v * g;
                if (prod == 0.0f && std::signbit(prod)) neg_zero_products++;
                if (g == 0.0f) zero_gain++;
                if (prod != 0.0f && std::fabs(prod) < 1.17549435e-38f) subnormal_products++;
            }
        }
        std::cout << width << " fixture: " << neg_zero_products << " negative-zero products, "
                  << zero_gain << " zero-gain pixels, "
                  << subnormal_products << " subnormal products\n";
        if (neg_zero_products == 0 || zero_gain == 0 || subnormal_products == 0) {
            std::cerr << "FAIL fixture does not contain the cases the hostile-gain arm "
                         "exists to exercise; that arm would prove nothing\n";
            return 1;
        }
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
            std::cerr << "FAIL " << width << " " << c.name << ": float arm did not complete\n" << log.str();
            return 1;
        }
        if (!runNativeArm(native, c.gain, b, log)) {
            std::cerr << "FAIL " << width << " " << c.name << ": native arm did not complete\n" << log.str();
            return 1;
        }
        std::string why;
        if (identical(a, b, why)) {
            std::cout << "PASS " << width << " " << c.name << ": sum and all " << NFRAMES
                      << " resident frames are byte-identical\n";
        } else {
            std::cerr << "FAIL " << width << " " << c.name << ": " << why << "\n";
            failures++;
        }
    }

    // Negative control. A comparison that cannot fail proves nothing, so perturb one
    // sample of one frame by one count and require the same comparison to report it.
    {
        std::vector<Image<T> > tampered = native;
        T &v = DIRECT_MULTIDIM_ELEM(tampered[NFRAMES / 2](), n / 2);
        v = (T)(v ^ 1u);
        Arm a, b;
        if (!runFloatArm(f32, &gain_plain, a, log) ||
            !runNativeArm(tampered, &gain_plain, b, log)) {
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
        if (!runFloatArm(f32, &gain_plain, a, log) || !runNativeArm(native, &gain_plain, b, log)) {
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
    std::cout << "All " << width << " staging equivalence checks passed\n";
    return 0;
}

int main() {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "CUDA device 0 is required for this control\n";
        return 1;
    }
    const int u16 = runContract<unsigned short>("uint16");
    const int u8 = runContract<unsigned char>("uint8");
    return u16 || u8 ? 1 : 0;
}
