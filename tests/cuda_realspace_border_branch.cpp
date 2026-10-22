// #259: the CUDA local warp must take the same border branch as the CPU when the
// source coordinate ix - x_fitted lies within a float step of nx-1 (or ny-1).
//
// The production kernel is launched through cudaRealSpaceInterpolation with a
// ThirdOrderPolynomialModel: frame 0 is all zero (its model shift is zero) and
// frame 1 carries the test image, so the output is the warped test image. The
// oracle is the CPU arithmetic of realSpaceInterpolation_ThirdOrderPolynomial_withoutsum
// in double (floor, bounds test, nearest-pixel fallback, bilinear), evaluated
// from the same float coefficients the kernel receives. The border policy is
// the CPU's; only the branch decision is under test.
//
// --expect-mismatch is for the compiled mutants: the run passes only if some
// non-control case differs from the oracle. Control cases must always match.
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/micrograph_model.h"
#include "realspace_border_validation.h"
#include <cmath>
#include <cstring>
#include <iostream>
#include <sstream>
#include <vector>

namespace {
struct Case {
    const char *name;
    int nx, ny;
    int image; // 0: I = y, 1: I = x, 2: constant 7
    double cx, cy;
    bool control;
};

float pixel(int image, int x, int y) {
    return image == 0 ? (float)y : image == 1 ? (float)x : 7.0f;
}

// CPU branch logic of the polynomial warp for one pixel, all in double.
double cpuValue(const Case &c, const std::vector<float> &img, int ix, int iy, bool *interpolated) {
    const double xt = ix - (double)(float)c.cx, yt = iy - (double)(float)c.cy;
    int x0 = (int)std::floor(xt), y0 = (int)std::floor(yt);
    const int x1 = x0 + 1, y1 = y0 + 1;
    bool valid = true;
    if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
    if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
    if (x1 >= c.nx || x0 >= c.nx - 1) { x0 = c.nx - 1; valid = false; }
    if (y1 >= c.ny || y0 >= c.ny - 1) { y0 = c.ny - 1; valid = false; }
    *interpolated = valid;
    if (!valid) return img[(size_t)y0 * c.nx + x0];
    const double fx = xt - x0, fy = yt - y0;
    const double d00 = img[(size_t)y0 * c.nx + x0], d01 = img[(size_t)y0 * c.nx + x1];
    const double d10 = img[(size_t)y1 * c.nx + x0], d11 = img[(size_t)y1 * c.nx + x1];
    const double dx0 = d00 + fx * (d01 - d00), dx1 = d10 + fx * (d11 - d10);
    return dx0 + fy * (dx1 - dx0);
}

// Returns the number of pixels differing from the oracle by more than a branch
// error (>= 0.05; the bilinear rounding of the float kernel is ~1e-3 at most).
long runCase(const Case &c, std::vector<std::string> &report) {
    std::vector<Image<float> > frames(2);
    for (auto &f : frames) f().initZeros(c.ny, c.nx);
    std::vector<float> img((size_t)c.nx * c.ny);
    for (int y = 0; y < c.ny; y++)
        for (int x = 0; x < c.nx; x++) {
            img[(size_t)y * c.nx + x] = pixel(c.image, x, y);
            frames[1]()(y, x) = img[(size_t)y * c.nx + x];
        }

    ThirdOrderPolynomialModel model;
    model.coeffX.initZeros(ThirdOrderPolynomialModel::NUM_COEFFS_PER_DIM);
    model.coeffY.initZeros(ThirdOrderPolynomialModel::NUM_COEFFS_PER_DIM);
    model.coeffX(0) = c.cx; // frame 1 (z = 1): x_C0 = coeffX(0)
    model.coeffY(0) = c.cy;

    Image<float> sum;
    sum().initZeros(c.ny, c.nx);
    std::ostringstream log;
    if (!cudaRealSpaceInterpolation(sum, nullptr, nullptr, frames, &model, 0, log))
        throw std::runtime_error(std::string(c.name) + ": cudaRealSpaceInterpolation failed");

    long bad = 0;
    double worst = 0.0;
    int bx = -1, by = -1;
    double want_at_worst = 0.0;
    for (int y = 0; y < c.ny; y++)
        for (int x = 0; x < c.nx; x++) {
            bool interpolated;
            const double want = cpuValue(c, img, x, y, &interpolated);
            (void)interpolated;
            double err;
            if (realspace_border_test::pixelDiffers((double)sum()(y, x), want, c.name, x, y, err)) {
                bad++;
                if (err > worst) { worst = err; bx = x; by = y; want_at_worst = want; }
            }
        }
    std::ostringstream line;
    line << c.name << ": " << bad << " pixels differ from the CPU-branch oracle";
    if (bad) line << " (worst " << worst << " at x=" << bx << " y=" << by << ", got " << sum()(by, bx)
                  << " want " << want_at_worst << ")";
    report.push_back(line.str());
    return bad;
}
} // namespace

int main(int argc, char **argv) try {
    bool expect_mismatch = false;
    for (int i = 1; i < argc; i++)
        if (!std::strcmp(argv[i], "--expect-mismatch")) expect_mismatch = true;
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "CUDA device 0 is required for this test\n";
        return 1;
    }

    const double tiny = 1e-5;
    const Case cases[] = {
        // Last column: x_fitted = 1e-5, x_target = nx-1-1e-5 rounds to nx-1 in float. y ramp, y shift 0.5.
        {"last column", 4096, 64, 0, tiny, 0.5, false},
        // The same on the last row, x/y exchanged.
        {"last row", 64, 4096, 1, 0.5, tiny, false},
        // Interior output pixel (nx-4) whose source lands within 1e-5 of nx-1 through a large negative shift.
        {"interior output, edge source (x)", 4096, 64, 0, -3.0 + tiny, 0.5, false},
        {"interior output, edge source (y)", 64, 4096, 1, 0.5, -3.0 + tiny, false},
        // Corner: both axes sub-ULP at once.
        {"corner", 4096, 4096, 0, tiny, tiny, false},
        // Controls: a constant image cannot show the branch; ordinary shifts take the same branch either way.
        {"control: constant image", 4096, 64, 2, tiny, 0.5, true},
        {"control: interior shifts", 4096, 64, 0, 0.3, 0.5, true},
    };

    int failed_cases = 0, control_failures = 0;
    for (const Case &c : cases) {
        std::vector<std::string> report;
        const long bad = runCase(c, report);
        for (const auto &l : report) std::cout << l << "\n";
        if (bad) {
            if (c.control) ++control_failures; else ++failed_cases;
        }
    }
    if (control_failures) {
        std::cout << "FAIL: " << control_failures << " control case(s) differ from the oracle\n";
        return 1;
    }
    if (expect_mismatch) {
        std::cout << (failed_cases ? "RAN: " : "FAIL: mutant not detected; ") << failed_cases
                  << " case(s) differ from the oracle\n";
        return failed_cases ? 0 : 1;
    }
    if (failed_cases) {
        std::cout << "FAIL: " << failed_cases << " case(s) differ from the CPU branch\n";
        return 1;
    }
    std::cout << "PASS: " << (int)(sizeof(cases) / sizeof(cases[0])) << " cases match the CPU branch decision\n";
    return 0;
} catch (const std::exception &exc) {
    std::cerr << "FAIL: " << exc.what() << '\n';
    return 1;
}
