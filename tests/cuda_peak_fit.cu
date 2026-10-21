// Same-map regression for issue #257. Launch the production selector/fit kernel,
// so the test also covers wrapped neighbours, boundary extrapolation and scaling.
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

__global__ void findPeakAndInterpolateKernel(const float*, float*, float*,
    int, int, int, float, float, int);

static void check(cudaError_t err) {
    if (err != cudaSuccess) throw std::runtime_error(cudaGetErrorString(err));
}

struct Case {
    const char* name;
    float m, xp, xn, yp, yn;
    int x = 0, y = 0, range = 0;
    float sx = 4, sy = 3;
};

static float reference(int pos, float m, float vp, float vn, float scale) {
    const double denom = double(vp) + double(vn) - 2.0 * double(m);
    const double vertex = std::abs(denom) > double(1e-15f)
        ? pos - 0.5 * (double(vp) - double(vn)) / denom : pos;
    return float(vertex * double(scale));
}

int main(int argc, char** argv) {
    const bool expect_mismatch = argc == 2 && !std::strcmp(argv[1], "--expect-mismatch");
    try {
        const float eps = 1e-15f;
        const std::vector<Case> cases = {
            {"captured-pedestal", 36366.4296875f, 36365.69140625f, 36366.359375f,
                36366.359375f, 36365.69140625f, 0, 0, 1},
            {"flat", 36000, 36000, 36000, 36000, 36000},
            {"one-ulp-plateau", 1, 1, std::nextafter(1.0f, 0.0f),
                std::nextafter(1.0f, 0.0f), 1},
            {"unique-one-ulp-peak", 1, std::nextafter(1.0f, 0.0f), std::nextafter(1.0f, 0.0f),
                std::nextafter(1.0f, 0.0f), std::nextafter(1.0f, 0.0f), 0, 0, 1},
            {"integer-tie", 1, 1, 0.5f, 0.75f, 0.5f, 0, 0, 1},
            {"below-guard", 0, -2e-16f, -4e-16f, -4e-16f, -2e-16f},
            {"at-guard", 0, -eps, 0, 0, -eps},
            {"above-guard", 0, -std::nextafter(eps, 1.0f), 0,
                0, -std::nextafter(eps, 1.0f)},
            {"subnormal", 0, -1e-40f, -2e-40f, -2e-40f, -1e-40f},
            // A neighbour beyond the searched boundary can exceed the winner.
            // Preserve the existing unbracketed fit rather than clamp it here.
            {"search-boundary", 100, 100.25f, 99.5f, 99.75f, 100.5f, 1, -1, 1, 2.5f, 1.25f},
            {"positive-curvature", 0, 2, 1, 1, 2},
            {"large-finite", 2e38f, 1.9e38f, 1.8e38f, 1.8e38f, 1.9e38f},
            {"nan-neighbour", 1, std::numeric_limits<float>::quiet_NaN(), 0, 0.5f, 0},
            {"infinite-peak", std::numeric_limits<float>::infinity(), 1, 0, 1, 0},
            {"infinite-neighbour", 1, std::numeric_limits<float>::infinity(), 0, 0.5f, 0}
        };
        constexpr int n = 16;
        std::vector<float> maps(cases.size() * n * n, -1e29f);
        for (size_t i = 0; i < cases.size(); ++i) {
            const auto& c = cases[i];
            auto at = [&](int x, int y) -> float& {
                return maps[i * n * n + ((y + n) % n) * n + (x + n) % n];
            };
            at(c.x, c.y) = c.m;
            at(c.x + 1, c.y) = c.xp; at(c.x - 1, c.y) = c.xn;
            at(c.x, c.y + 1) = c.yp; at(c.x, c.y - 1) = c.yn;
        }
        float *dm = nullptr, *dx = nullptr, *dy = nullptr;
        check(cudaMalloc(&dm, maps.size() * sizeof(float)));
        check(cudaMalloc(&dx, sizeof(float)));
        check(cudaMalloc(&dy, sizeof(float)));
        check(cudaMemcpy(dm, maps.data(), maps.size() * sizeof(float), cudaMemcpyHostToDevice));
        int mismatches = 0;
        bool pedestal_mismatch = false;
        for (size_t i = 0; i < cases.size(); ++i) {
            const auto& c = cases[i];
            findPeakAndInterpolateKernel<<<1, 256>>>(dm + i * n * n, dx, dy,
                n, n, c.range, c.sx, c.sy, 1);
            check(cudaGetLastError());
            float x, y;
            check(cudaMemcpy(&x, dx, sizeof(float), cudaMemcpyDeviceToHost));
            check(cudaMemcpy(&y, dy, sizeof(float), cudaMemcpyDeviceToHost));
            const float rx = reference(c.x, c.m, c.xp, c.xn, c.sx);
            const float ry = reference(c.y, c.m, c.yp, c.yn, c.sy);
            auto matches = [](float got, float ref) {
                if (!std::isfinite(ref))
                    return std::isnan(ref) ? std::isnan(got) : got == ref;
                return std::isfinite(got) && std::abs(double(got) - ref) <=
                    std::numeric_limits<float>::epsilon() * std::abs(double(ref));
            };
            const bool ok = matches(x, rx) && matches(y, ry);
            mismatches += !ok;
            if (i == 0) pedestal_mismatch = !ok;
            std::cout << std::setprecision(17) << c.name << " got=" << x << ',' << y
                      << " reference=" << rx << ',' << ry << " match=" << ok << '\n';
        }
        check(cudaFree(dy)); check(cudaFree(dx)); check(cudaFree(dm));
        // Require the named pedestal witness, not an unrelated failure, to kill
        // the float-denominator mutant. CUDA errors always fail above.
        return expect_mismatch ? (pedestal_mismatch ? 0 : 1) : (mismatches ? 1 : 0);
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
