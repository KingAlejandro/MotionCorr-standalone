#include "src/motioncorr_runner.h"
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>

// Exercise both production entry points: the former full-stack interpolation
// remains the independent reference for the bounded streaming caller.
struct MotioncorrRunnerTestAccess {
    static void stream(MotioncorrRunner &r, Image<float> &sum, Image<float> *even,
                       Image<float> *odd, std::vector<Image<float>> &frames,
                       MotionModel *model, std::ostream &log) {
        r.sumUnweightedFrames(sum, even, odd, frames, model, log);
    }
    static void materialize(MotioncorrRunner &r, std::vector<Image<float>> &out,
                            std::vector<Image<float>> &frames, MotionModel *model,
                            std::ostream &log, int offset = 0) {
        r.realSpaceInterpolation_withoutsum(out, frames, model, log, offset);
    }
    static void direct(MotioncorrRunner &r, Image<float> &sum,
                       std::vector<Image<float>> &frames, MotionModel *model,
                       std::ostream &log) {
        r.realSpaceInterpolation(sum, frames, model, log);
    }
};

#ifdef MOTIONCORR_ALLOCATION_WITNESS
namespace {
bool recording = false;
size_t threshold = 0, live = 0, peak = 0;
std::map<void *, size_t> tracked;
}
extern "C" void *__real_fftw_malloc(size_t);
extern "C" void __real_fftw_free(void *);
extern "C" void *__wrap_fftw_malloc(size_t n) {
    void *p = __real_fftw_malloc(n);
    if (recording && p && n >= threshold) {
        tracked[p] = n; live += n; peak = std::max(peak, live);
    }
    return p;
}
extern "C" void __wrap_fftw_free(void *p) {
    auto it = tracked.find(p);
    if (it != tracked.end()) { live -= it->second; tracked.erase(it); }
    __real_fftw_free(p);
}
#endif

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
static void start_allocations(size_t frame_bytes) {
#ifdef MOTIONCORR_ALLOCATION_WITNESS
    require(tracked.empty(), "previous scratch allocation leaked");
    threshold = frame_bytes; live = peak = 0; recording = true;
#endif
}
static size_t stop_allocations() {
#ifdef MOTIONCORR_ALLOCATION_WITNESS
    recording = false;
    require(live == 0 && tracked.empty(), "scratch survived reconstruction");
    return peak;
#else
    return 0;
#endif
}
static bool identical(const Image<float> &a, const Image<float> &b) {
    return a().nzyxdim == b().nzyxdim &&
        std::memcmp(a().data, b().data, a().nzyxdim * sizeof(float)) == 0;
}

class GeneralModel : public MotionModel {
public:
    void fit() override {}
    void read(std::ifstream &, std::string) override {}
    void write(std::ostream &, std::string) override {}
    int getModelVersion() const override { return 2; }
    int getShiftAt(RFLOAT z, RFLOAT x, RFLOAT y, RFLOAT &sx, RFLOAT &sy) const override {
        sx = 0.37 * z + 0.13 * x - 0.21 * y;
        sy = -0.23 * z + 0.17 * x + 0.11 * y;
        return 0;
    }
    MotionModel *clone() const override { return new GeneralModel(*this); }
};

int main() {
    try {
        ThirdOrderPolynomialModel polynomial;
        polynomial.coeffX.initZeros(18); polynomial.coeffY.initZeros(18);
        polynomial.coeffX(0) = 0.37; polynomial.coeffX(4) = 0.013;
        polynomial.coeffX(11) = -0.0003;
        polynomial.coeffY(0) = -0.23; polynomial.coeffY(7) = 0.021;
        polynomial.coeffY(15) = 0.017;
        GeneralModel general;
        bool rounding_witness = false, time_witness = false;
        for (int count : {7, 32}) for (int threads : {1, 4})
        for (int nx : {20, 64}) for (bool split : {false, true})
        for (MotionModel *model : {static_cast<MotionModel *>(nullptr),
                                  static_cast<MotionModel *>(&polynomial),
                                  static_cast<MotionModel *>(&general)}) {
            const int ny = nx == 20 ? 18 : 48;
            const size_t frame_bytes = nx * ny * sizeof(float);
            MotioncorrRunner runner; runner.n_threads = threads;
            std::vector<Image<float>> frames(count);
            std::vector<std::vector<float>> original(count);
            for (int f = 0; f < count; ++f) {
                frames[f]().reshape(ny, nx);
                for (int n = 0; n < nx * ny; ++n) {
                    const float scale = n % 5 == 0 ? 16777216.0f : 1.0f;
                    frames[f]().data[n] = scale * ((n * 17 + f * 23) % 101 - 50) +
                        0.13f * ((n + f) % 7);
                }
                original[f].assign(frames[f]().data, frames[f]().data + nx * ny);
            }
            Image<float> expected, expected_even, expected_odd, actual, even, odd, direct;
            for (auto *image : {&expected, &expected_even, &expected_odd, &actual, &even, &odd, &direct})
                (*image)().initZeros(ny, nx);
            std::ostringstream ref_log, stream_log, extra_log;
            start_allocations(frame_bytes);
            {
                std::vector<Image<float>> aligned(count);
                for (int f = 0; f < count; ++f) aligned[f]().initZeros(frames[f]());
                MotioncorrRunnerTestAccess::materialize(runner, aligned, frames, model, ref_log);
                // Former caller's ascending frame additions, including float stores.
                for (int f = 0; f < count; ++f) for (int n = 0; n < nx * ny; ++n) {
                    expected().data[n] += aligned[f]().data[n];
                    if (split) (f % 2 ? expected_odd : expected_even)().data[n] += aligned[f]().data[n];
                }
            }
            const size_t old_peak = stop_allocations();
            start_allocations(frame_bytes);
            MotioncorrRunnerTestAccess::stream(runner, actual, split ? &even : nullptr,
                                               split ? &odd : nullptr, frames, model, stream_log);
            const size_t new_peak = stop_allocations();
            require(identical(expected, actual), "stream changed corrected pixels");
            require(identical(expected_even, even) && identical(expected_odd, odd),
                    "stream changed even/odd products");
            require(ref_log.str() == stream_log.str(), "stream changed progress output");
            for (int f = 0; f < count; ++f)
                require(std::memcmp(original[f].data(), frames[f]().data, frame_bytes) == 0,
                        "stream modified or freed its input alias");
#ifdef MOTIONCORR_ALLOCATION_WITNESS
            require(old_peak == count * frame_bytes, "full-stack allocation control not witnessed");
            require(new_peak == frame_bytes, "stream scratch exceeds one frame");
#endif
            if (model) {
                MotioncorrRunnerTestAccess::direct(runner, direct, frames, model, extra_log);
                rounding_witness |= !identical(expected, direct);
                std::vector<Image<float>> view(1), wrong(1), correct(1);
                view[0]().alias(frames.back()());
                wrong[0]().initZeros(view[0]()); correct[0]().initZeros(view[0]());
                MotioncorrRunnerTestAccess::materialize(runner, wrong, view, model, extra_log);
                MotioncorrRunnerTestAccess::materialize(runner, correct, view, model, extra_log, count - 1);
                time_witness |= !identical(wrong[0], correct[0]);
            }
        }
        require(rounding_witness, "fixture cannot reject fused interpolation/add rounding changes");
        require(time_witness, "fixture cannot reject resetting streamed model time to zero");
        std::cout << "stream/reference pixels, splits, model time, float rounding and scratch bound PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
