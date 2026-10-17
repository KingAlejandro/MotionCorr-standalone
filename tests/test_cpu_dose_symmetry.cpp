#include "src/motioncorr_runner.h"
#include "cpu_dose_reference.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

struct MotioncorrRunnerTestAccess {
    static void weight(MotioncorrRunner &runner,
                       std::vector<MultidimArray<fComplex>> &frames,
                       const std::vector<RFLOAT> &doses, RFLOAT apix) {
        runner.doseWeighting(frames, doses, apix);
    }
};

#ifdef MOTIONCORR_EXP_WITNESS
static std::atomic<size_t> exp_calls{0};
static bool recording = false;
extern "C" double __real_exp(double);
extern "C" float __real_expf(float);
extern "C" double __wrap_exp(double x) {
    if (recording) exp_calls.fetch_add(1, std::memory_order_relaxed);
    return __real_exp(x);
}
extern "C" float __wrap_expf(float x) {
    if (recording) exp_calls.fetch_add(1, std::memory_order_relaxed);
    return __real_expf(x);
}
#endif

static void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}
static void start_count() {
#ifdef MOTIONCORR_EXP_WITNESS
    exp_calls = 0; recording = true;
#endif
}
static size_t stop_count() {
#ifdef MOTIONCORR_EXP_WITNESS
    recording = false; return exp_calls.load();
#else
    return 0;
#endif
}
static std::vector<MultidimArray<fComplex>> allocate(int nfx, int ny, int count) {
    std::vector<MultidimArray<fComplex>> frames(count);
    for (auto &frame : frames) frame.reshape(ny, nfx);
    return frames;
}
static void fill(std::vector<MultidimArray<fComplex>> &frames, bool exceptional, bool stress = true) {
    for (size_t f = 0; f < frames.size(); ++f) {
        auto &frame = frames[f];
        for (size_t n = 0; n < frame.nzyxdim; ++n) {
            // Deliberately asymmetric rows: only weights, never pixels, may be shared.
            float re = static_cast<int>((n * 17 + f * 29) % 1009) * 0.13f - 30.5f;
            float im = static_cast<int>((n * 31 + f * 7) % 997) * -0.17f + 19.25f;
            if (n % 23 == 0) re = -0.0f;
            if (n % 29 == 0) im = 0.0f;
            if (stress && n % 37 == 0) re = std::ldexp(1.0f, -140);
            if (exceptional && n % 41 == 0) im = std::numeric_limits<float>::infinity();
            if (exceptional && n % 43 == 0) re = std::numeric_limits<float>::quiet_NaN();
            frame.data[n] = fComplex(re, im);
        }
    }
}
static bool equal(const std::vector<MultidimArray<fComplex>> &a,
                  const std::vector<MultidimArray<fComplex>> &b) {
    if (a.size() != b.size()) return false;
    for (size_t f = 0; f < a.size(); ++f)
        if (a[f].nzyxdim != b[f].nzyxdim ||
            std::memcmp(a[f].data, b[f].data, a[f].nzyxdim * sizeof(fComplex))) return false;
    return true;
}
static void copy(const std::vector<MultidimArray<fComplex>> &src,
                 std::vector<MultidimArray<fComplex>> &dest) {
    for (size_t f = 0; f < src.size(); ++f)
        std::memcpy(dest[f].data, src[f].data, src[f].nzyxdim * sizeof(fComplex));
}

static int controls() {
    size_t cases = 0;
    // R-NUM-179A: underflowing weights distinguish +0 from -0 under FMA contraction.
    {
        auto expected = allocate(63, 9, 2), actual = allocate(63, 9, 2);
        fill(expected, false); copy(expected, actual);
        const std::vector<RFLOAT> doses = {1000, 2000};
        referenceDoseWeighting(expected, doses, 0.885, 1);
        MotioncorrRunner runner; runner.n_threads = 1;
        MotioncorrRunnerTestAccess::weight(runner, actual, doses, 0.885);
        require(equal(expected, actual), "large-dose signed zeros changed");
        ++cases;
    }
    for (int nfx : {2, 33, 64, 65, 130}) for (int ny : {1, 2, 3, 8, 9, 48, 49})
    for (int count : {1, 7, 24, 64}) for (int threads : {1, 4})
    for (int pattern : {0, 1, 2}) for (bool exceptional : {false, true}) {
        auto expected = allocate(nfx, ny, count), actual = allocate(nfx, ny, count);
        fill(expected, exceptional); copy(expected, actual);
        std::vector<RFLOAT> doses(count);
        for (int f = 0; f < count; ++f)
            doses[f] = pattern == 0 ? 0 : pattern == 1 ? 3.4 + 1.277 * (f + 1)
                        : (0.7 + ((f * 7) % 13)) / 0.64;
        const RFLOAT apix = pattern == 2 ? 1.77 : 0.885;
        start_count(); referenceDoseWeighting(expected, doses, apix, threads);
        const size_t original_calls = stop_count();
        MotioncorrRunner runner; runner.n_threads = threads;
        start_count(); MotioncorrRunnerTestAccess::weight(runner, actual, doses, apix);
        const size_t candidate_calls = stop_count();
        require(equal(expected, actual), "dose symmetry changed complex bits");
#ifdef MOTIONCORR_EXP_WITNESS
        require(original_calls == static_cast<size_t>(ny) * nfx * count,
                "original exp-call count not witnessed");
        require(candidate_calls == static_cast<size_t>(ny / 2 + 1) * nfx * count,
                "production did not eliminate duplicate weight calculations");
#endif
        ++cases;
    }
#ifdef MOTIONCORR_EXP_WITNESS
    std::cout << cases << " cases: exact complex bits and exp-call bound PASS\n";
#else
    std::cout << cases << " cases: exact complex bits PASS; exp-call bound SKIPPED (no witness)\n";
#endif
    return 0;
}

static int benchmark(int argc, char **argv) {
    require(argc == 7 || (argc == 8 && std::string(argv[7]) == "--stress"),
            "cpu_dose_bench --bench nx ny frames threads repetitions [--stress]");
#ifdef MOTIONCORR_EXP_WITNESS
    throw std::runtime_error("use the unwrapped cpu_dose_bench target for timing");
#endif
    const int nx = std::stoi(argv[2]), ny = std::stoi(argv[3]), count = std::stoi(argv[4]);
    const int threads = std::stoi(argv[5]), repeats = std::stoi(argv[6]);
    require(nx >= 2 && nx % 2 == 0 && ny > 0 && count > 0 && threads > 0 && repeats >= 6,
            "invalid benchmark dimensions or fewer than six repetitions");
    const bool stress = argc == 8;
    auto frames = allocate(nx / 2 + 1, ny, count), saved = allocate(nx / 2 + 1, ny, count);
    fill(saved, false, stress); // Work-array first touch is excluded with warmup.
    std::vector<RFLOAT> doses(count);
    for (int f = 0; f < count; ++f) doses[f] = 1.277 * (f + 1);
    MotioncorrRunner runner; runner.n_threads = threads;
    std::cout << std::setprecision(17);
    for (int rep = -1; rep < repeats; ++rep) {
        const bool candidate_first = rep >= 0 && rep % 2 == 1;
        for (int slot = 0; slot < 2; ++slot) {
            const bool candidate = candidate_first != (slot == 1);
            fill(frames, false, stress);
            const auto cpu_start = std::clock();
            const auto start = std::chrono::steady_clock::now();
            if (candidate) MotioncorrRunnerTestAccess::weight(runner, frames, doses, 0.885);
            else referenceDoseWeighting(frames, doses, 0.885, threads);
            const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            const double cpu = static_cast<double>(std::clock() - cpu_start) / CLOCKS_PER_SEC;
            if (slot == 0) copy(frames, saved);
            else require(equal(frames, saved), "benchmark spectra differ bit for bit");
            std::cout << "{\"rep\":" << rep << ",\"arm\":\"" << (candidate ? "candidate" : "base")
                      << "\",\"wall_s\":" << wall << ",\"cpu_s\":" << cpu
                      << ",\"nx\":" << nx << ",\"ny\":" << ny << ",\"frames\":" << count
                      << ",\"threads\":" << threads << "}\n" << std::flush;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    try {
        if (argc > 1 && std::string(argv[1]) == "--bench") return benchmark(argc, argv);
        return controls();
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
