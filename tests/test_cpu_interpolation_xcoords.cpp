// Exact-output controls and an optional paired kernel benchmark for issue #10.
// The reference retains the original upstream notice in its separate header.
#include "src/motioncorr_runner.h"
#include "src/micrograph_model.h"
#include "cpu_interpolation_reference.h"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>

struct MotioncorrRunnerTestAccess {
    static void sum(MotioncorrRunner &runner, Image<float> &out,
                    std::vector<Image<float>> &frames, ThirdOrderPolynomialModel &model,
                    std::ostream &log) {
        runner.realSpaceInterpolation_ThirdOrderPolynomial(out, frames, model, log);
    }
    static void frames(MotioncorrRunner &runner, std::vector<Image<float>> &out,
                       std::vector<Image<float>> &frames, ThirdOrderPolynomialModel &model,
                       std::ostream &log) {
        runner.realSpaceInterpolation_ThirdOrderPolynomial_withoutsum(out, frames, model, log);
    }
};

namespace {
void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

float value(std::size_t p, int frame, bool exceptional) {
    if (exceptional) {
        switch ((p + frame * 3) % 41) {
        case 0: return 0.0f;
        case 1: return -0.0f;
        case 2: return std::numeric_limits<float>::denorm_min();
        case 3: return -std::numeric_limits<float>::denorm_min();
        case 4: return std::numeric_limits<float>::infinity();
        case 5: return -std::numeric_limits<float>::infinity();
        case 6: return std::numeric_limits<float>::quiet_NaN();
        }
    }
    // Different rows/frames and both signs, without dependence on libm or RNG.
    std::uint32_t bits = std::uint32_t(p * 1664525u + (frame + 1) * 1013904223u);
    return float(std::int32_t(bits % 200003) - 100001) / 37.0f;
}

std::vector<Image<float>> input(int nx, int ny, int nf, bool exceptional) {
    std::vector<Image<float>> frames(nf);
    for (int f = 0; f < nf; ++f) {
        frames[f]().reshape(ny, nx);
        for (std::size_t p = 0; p < std::size_t(nx) * ny; ++p)
            DIRECT_MULTIDIM_ELEM(frames[f](), p) = value(p, f, exceptional);
    }
    return frames;
}

void fill(Image<float> &im, float seed) {
    for (std::size_t p = 0; p < MULTIDIM_SIZE(im()); ++p)
        DIRECT_MULTIDIM_ELEM(im(), p) = seed + float(p % 7) / 8.0f;
}

void equal(const Image<float> &a, const Image<float> &b, const std::string &tag) {
    require(MULTIDIM_SIZE(a()) == MULTIDIM_SIZE(b()), tag + ": shape");
    const auto bytes = MULTIDIM_SIZE(a()) * sizeof(float);
    if (std::memcmp(a().data, b().data, bytes) != 0) {
        for (std::size_t p = 0; p < MULTIDIM_SIZE(a()); ++p)
            if (std::memcmp(a().data + p, b().data + p, sizeof(float)) != 0)
                throw std::runtime_error(tag + ": bits differ at " + std::to_string(p));
    }
}

ThirdOrderPolynomialModel model(int which) {
    ThirdOrderPolynomialModel m;
    m.coeffX.initZeros(18); m.coeffY.initZeros(18);
    if (which == 1) { // fractional translation, crossing each edge at nonzero frames
        m.coeffX(0) = 0.7; m.coeffY(0) = -0.4;
    } else if (which == 2) { // large translation, clamp-only paths at tiny geometries
        m.coeffX(0) = -37.25; m.coeffY(0) = 28.125;
    } else if (which == 3 || which == 4) { // all spatial and time terms, both signs
        for (int c = 0; c < 18; ++c) {
            m.coeffX(c) = (c % 2 ? -1 : 1) * (c + 1) / 137.0;
            m.coeffY(c) = (c % 3 ? 1 : -1) * (18 - c) / 211.0;
        }
        if (which == 4) { // fractional movement near integer source boundaries
            for (int c = 0; c < 18; ++c) {
                m.coeffX(c) *= 1e-7; m.coeffY(c) *= 1e-7;
            }
        }
    }
    return m;
}

void check(int nx, int ny, int nf, int which, int threads, bool exceptional) {
    auto frames = input(nx, ny, nf, exceptional);
    const auto original = frames;
    auto m = model(which);
    MotioncorrRunner runner; runner.n_threads = threads;
    std::ostringstream log_ref, log_actual;
    Image<float> reference, actual;
    reference().reshape(ny, nx); fill(reference, -0.25f); actual = reference;
    reference_realSpaceInterpolation_ThirdOrderPolynomial(reference, frames, m, log_ref, threads);
    MotioncorrRunnerTestAccess::sum(runner, actual, frames, m, log_actual);
    const std::string tag = std::to_string(nx) + "x" + std::to_string(ny) + "x" +
        std::to_string(nf) + " model=" + std::to_string(which) + " j=" + std::to_string(threads);
    equal(reference, actual, tag + " sum");
    require(log_ref.str() == log_actual.str(), tag + " sum progress log");

    auto ref_frames = input(nx, ny, nf, false);
    for (int f = 0; f < nf; ++f) fill(ref_frames[f], float(f + 1) / 4.0f);
    auto actual_frames = ref_frames;
    log_ref.str(""); log_actual.str("");
    reference_realSpaceInterpolation_ThirdOrderPolynomial_withoutsum(ref_frames, frames, m, log_ref, threads);
    MotioncorrRunnerTestAccess::frames(runner, actual_frames, frames, m, log_actual);
    for (int f = 0; f < nf; ++f) {
        equal(ref_frames[f], actual_frames[f], tag + " frame=" + std::to_string(f));
        equal(original[f], frames[f], tag + " input unchanged");
    }
    require(log_ref.str() == log_actual.str(), tag + " frame progress log");
}

void benchmark(int nx, int ny, int nf, int threads, int repetitions, bool withoutsum) {
    auto frames = input(nx, ny, nf, false);
    auto m = model(3);
    // A smooth, small displacement across 24 frames, rather than a clamp-heavy warp.
    for (int c = 0; c < 18; ++c) { m.coeffX(c) *= 1e-3; m.coeffY(c) *= 1e-3; }
    MotioncorrRunner runner; runner.n_threads = threads;
    Image<float> ref_sum, actual_sum;
    ref_sum().reshape(ny, nx); actual_sum().reshape(ny, nx);
    std::vector<Image<float>> ref_frames, actual_frames;
    if (withoutsum) {
        ref_frames = input(nx, ny, nf, false); actual_frames = ref_frames;
    }
    std::ostringstream sink;
    auto run = [&](bool candidate) {
        sink.str("");
        if (withoutsum) {
            auto &out = candidate ? actual_frames : ref_frames;
            for (auto &im : out) im().initZeros();
        } else {
            (candidate ? actual_sum : ref_sum)().initZeros();
        }
        const auto start = std::chrono::steady_clock::now();
        if (withoutsum) {
            if (candidate) MotioncorrRunnerTestAccess::frames(runner, actual_frames, frames, m, sink);
            else reference_realSpaceInterpolation_ThirdOrderPolynomial_withoutsum(ref_frames, frames, m, sink, threads);
        } else {
            if (candidate) MotioncorrRunnerTestAccess::sum(runner, actual_sum, frames, m, sink);
            else reference_realSpaceInterpolation_ThirdOrderPolynomial(ref_sum, frames, m, sink, threads);
        }
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    };
    auto compare = [&] {
        if (withoutsum) for (int f = 0; f < nf; ++f) equal(ref_frames[f], actual_frames[f], "benchmark frames");
        else equal(ref_sum, actual_sum, "benchmark sum");
    };
    run(false); run(true); compare(); // excluded warmups, including first touch
    std::cout << std::setprecision(12);
    for (int pair = 0; pair < repetitions; ++pair) {
        double ref, candidate;
        if (pair % 2) { candidate = run(true); ref = run(false); }
        else { ref = run(false); candidate = run(true); }
        compare();
        std::cout << "{\"pair\":" << pair << ",\"nx\":" << nx << ",\"ny\":" << ny
                  << ",\"frames\":" << nf << ",\"threads\":" << threads
                  << ",\"withoutsum\":" << (withoutsum ? "true" : "false")
                  << ",\"reference_seconds\":" << ref << ",\"candidate_seconds\":" << candidate
                  << ",\"bitwise_equal\":true}" << std::endl;
    }
}
}

int main(int argc, char **argv) {
    try {
        if (argc > 1) {
            require(argc == 9 && std::string(argv[1]) == "--bench",
                    "Usage: cpu_interpolation_xcoords --bench nx ny frames threads pairs sum|frames affinity-confirmed");
            require(std::string(argv[8]) == "affinity-confirmed", "Pin the process to a fixed CPU set first");
            benchmark(std::stoi(argv[2]), std::stoi(argv[3]), std::stoi(argv[4]), std::stoi(argv[5]),
                      std::stoi(argv[6]), std::string(argv[7]) == "frames");
        } else {
            int cases = 0;
            for (const auto &shape : {std::pair<int,int>{1,1}, {2,3}, {3,2}, {7,9}, {16,16}, {33,17}, {64,49}, {65,8}})
                for (int nf : {1,3,7}) for (int which = 0; which < 5; ++which)
                    for (int threads : {1,4}) for (bool exceptional : {false,true}) {
                        check(shape.first, shape.second, nf, which, threads, exceptional); ++cases;
                    }
            std::cout << "PASS " << cases << " cases, both polynomial paths, exact float bits and unchanged inputs/logs\n";
        }
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << '\n'; return 1;
    }
}
