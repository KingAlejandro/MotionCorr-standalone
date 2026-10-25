// Experimental default-off global half-gain damping (research prototype, not adoption).
//
// Runs the production MotioncorrRunner::alignPatch on a deterministic 5-frame periodic
// fixture, one iteration at a time, and checks the operator-level contract:
//   1. the first global update with --experimental_global_half_gain is EXACTLY half of
//      the unflagged one (scaling by 0.5 is exact in binary floating point, so == is used);
//   2. the stopping test still sees the unscaled update (identical iteration-1 RMSD line);
//   3. the Fourier re-shift uses the scaled update (frames equal the reference frames
//      shifted by half the unflagged update, bit for bit);
//   4. local patches (is_global == false) are untouched by the flag;
//   5. --experimental_align_tolerance replaces the 0.5 px stop for the global alignment
//      only, and is inert when unset.
// Mutants checked by hand when the test was written (see the evidence README): scaling
// only the accumulation, scaling only the re-shift, and scaling before the sumsq all fail.

#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>

struct MotioncorrRunnerTestAccess {
    static bool alignPatch(MotioncorrRunner &runner,
                           std::vector<MultidimArray<fComplex> > &Fframes,
                           int pnx, int pny, RFLOAT scaled_B,
                           std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts,
                           std::ostream &logfile, bool is_global) {
        return runner.alignPatch(Fframes, pnx, pny, scaled_B, xshifts, yshifts, logfile, is_global);
    }
    static void shift(MotioncorrRunner &runner, MultidimArray<fComplex> &F, RFLOAT sx, RFLOAT sy) {
        runner.shiftNonSquareImageInFourierTransform(F, sx, sy);
    }
};

namespace {

const int PNX = 256;
const int PNY = 256;
const int NFRAMES = 5;
const RFLOAT SCALED_B = 20.0;

// Frame displacements are well above 0.5 px, so one iteration never meets the default stop.
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9, -1.3};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1, 0.7};

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

unsigned int nextRandom(unsigned int &state) {
    state = state * 1664525u + 1013904223u;
    return state;
}

// Band-limited periodic speckle in the half-complex layout (see test_patch_retry_state.cpp).
void buildBaseSpectrum(MultidimArray<fComplex> &F) {
    const int nfx = PNX / 2 + 1, nfy = PNY;
    F.reshape(nfy, nfx);
    F.initZeros();
    const int radius = 24;
    unsigned int state = 20261026u;
    for (int y = 0; y < nfy; y++) {
        const int ly = (y > nfy / 2) ? (y - nfy) : y;
        if (std::abs(ly) > radius) continue;
        for (int x = 0; x < nfx; x++) {
            if (x > radius) continue;
            if (x == 0 && ly == 0) continue;
            if (x == 0 && ly < 0) continue;
            const double r = std::sqrt((double)(x * x + ly * ly));
            const double amp = 1.0 / (1.0 + r);
            const double phase = 2.0 * M_PI * (nextRandom(state) / 4294967296.0);
            DIRECT_A2D_ELEM(F, y, x) = fComplex((float)(amp * std::cos(phase)),
                                                (float)(amp * std::sin(phase)));
        }
    }
    for (int ly = 1; ly <= radius; ly++) {
        const fComplex v = DIRECT_A2D_ELEM(F, ly, 0);
        DIRECT_A2D_ELEM(F, nfy - ly, 0) = fComplex(v.real, -v.imag);
    }
    DIRECT_A2D_ELEM(F, nfy / 2, 0) = fComplex(0.0f, 0.0f);
}

void shiftSpectrum(const MultidimArray<fComplex> &src, MultidimArray<fComplex> &dst,
                   double sx, double sy) {
    const int nfx = PNX / 2 + 1, nfy = PNY;
    dst.reshape(nfy, nfx);
    for (int y = 0; y < nfy; y++) {
        const int ly = (y > nfy / 2) ? (y - nfy) : y;
        for (int x = 0; x < nfx; x++) {
            const double phase = -2.0 * M_PI * ((double)x * sx / PNX + (double)ly * sy / PNY);
            const double c = std::cos(phase), s = std::sin(phase);
            const fComplex v = DIRECT_A2D_ELEM(src, y, x);
            DIRECT_A2D_ELEM(dst, y, x) = fComplex((float)(v.real * c - v.imag * s),
                                                  (float)(v.real * s + v.imag * c));
        }
    }
}

void buildStack(std::vector<MultidimArray<fComplex> > &F) {
    MultidimArray<fComplex> base;
    buildBaseSpectrum(base);
    F.resize(NFRAMES);
    for (int k = 0; k < NFRAMES; k++) shiftSpectrum(base, F[k], TRUE_SX[k], TRUE_SY[k]);
}

struct Run {
    std::vector<RFLOAT> xs, ys;
    std::vector<MultidimArray<fComplex> > frames;
    bool converged = false;
    std::string log;
};

Run runOnce(MotioncorrRunner &runner, bool is_global, bool half_gain, RFLOAT tolerance, int max_iter) {
    runner.experimental_global_half_gain = half_gain;
    runner.experimental_align_tolerance = tolerance;
    runner.max_iter = max_iter;
    Run r;
    buildStack(r.frames);
    r.xs.assign(NFRAMES, 0.0);
    r.ys.assign(NFRAMES, 0.0);
    std::ostringstream log;
    r.converged = MotioncorrRunnerTestAccess::alignPatch(runner, r.frames, PNX, PNY, SCALED_B,
                                                         r.xs, r.ys, log, is_global);
    r.log = log.str();
    return r;
}

// "Iteration N: RMSD = ..." lines only (the experimental banner is not part of the contract).
std::string iterationLines(const std::string &log) {
    std::istringstream in(log);
    std::string line, out;
    while (std::getline(in, line))
        if (line.find("Iteration") != std::string::npos) out += line + "\n";
    return out;
}

int countIterations(const std::string &log) {
    const std::string lines = iterationLines(log);
    return (int)std::count(lines.begin(), lines.end(), '\n');
}

bool framesEqual(const std::vector<MultidimArray<fComplex> > &a, const std::vector<MultidimArray<fComplex> > &b) {
    for (int k = 0; k < NFRAMES; k++) {
        if (XSIZE(a[k]) != XSIZE(b[k]) || YSIZE(a[k]) != YSIZE(b[k])) return false;
        for (long n = 0; n < (long)XSIZE(a[k]) * YSIZE(a[k]); n++) {
            const fComplex u = DIRECT_MULTIDIM_ELEM(a[k], n), v = DIRECT_MULTIDIM_ELEM(b[k], n);
            if (u.real != v.real || u.imag != v.imag) return false;
        }
    }
    return true;
}

} // namespace

int main() {
    try {
        MotioncorrRunner runner;
        runner.use_gpu = false;       // no default member initialiser; see test_patch_retry_state.cpp
        runner.gpu_id = 0;
        runner.n_threads = 1;
        runner.ccf_downsample = 1.0;
        runner.interpolate_shifts = false;

        std::printf("Global half-gain operator test (CPU, %d frames, %dx%d, one thread)\n", NFRAMES, PNX, PNY);

        // Unflagged first update. Its size must be real, or half of it proves nothing.
        const Run base = runOnce(runner, true, false, 0, 1);
        double norm2 = 0;
        for (int k = 0; k < NFRAMES; k++) norm2 += base.xs[k] * base.xs[k] + base.ys[k] * base.ys[k];
        std::printf("  unflagged first update |v| = %.6f px, converged=%d\n", std::sqrt(norm2), (int)base.converged);
        require(std::sqrt(norm2) > 1.0, "unflagged first update is too small to discriminate");
        require(!base.converged, "unflagged one-iteration run unexpectedly met the 0.5 px stop");
        require(base.xs[0] == 0 && base.ys[0] == 0, "frame 0 must stay the origin");

        // 1. exactly half.
        const Run half = runOnce(runner, true, true, 0, 1);
        for (int k = 0; k < NFRAMES; k++) {
            require(half.xs[k] == 0.5 * base.xs[k], "flagged x update at frame " + std::to_string(k) + " is not exactly half");
            require(half.ys[k] == 0.5 * base.ys[k], "flagged y update at frame " + std::to_string(k) + " is not exactly half");
        }
        std::printf("  flagged update == 0.5 * unflagged, exactly, all %d frames\n", NFRAMES);

        // 2. stopping test sees the unscaled update.
        require(iterationLines(half.log) == iterationLines(base.log) && !iterationLines(base.log).empty(),
                "iteration-1 RMSD line differs, so the stop is not using the unscaled update:\n" +
                iterationLines(base.log) + "vs\n" + iterationLines(half.log));
        require(half.converged == base.converged, "convergence verdict changed");
        std::printf("  RMSD stop line identical: %s", iterationLines(half.log).c_str());

        // 3. Fourier re-shift uses the scaled update.
        std::vector<MultidimArray<fComplex> > expected;
        buildStack(expected);
        for (int k = 1; k < NFRAMES; k++)
            MotioncorrRunnerTestAccess::shift(runner, expected[k], -half.xs[k] / PNX, -half.ys[k] / PNY);
        require(framesEqual(half.frames, expected), "flagged frames are not the reference frames shifted by the half update");
        require(!framesEqual(half.frames, base.frames), "flagged and unflagged frames are identical; the re-shift was not damped");
        std::printf("  re-shifted frames == reference shifted by the half update, bitwise\n");

        // 4. local patches untouched.
        const Run local_off = runOnce(runner, false, false, 0, 1);
        const Run local_on = runOnce(runner, false, true, 0, 1);
        for (int k = 0; k < NFRAMES; k++)
            require(local_on.xs[k] == local_off.xs[k] && local_on.ys[k] == local_off.ys[k], "local patch update changed by the flag");
        require(framesEqual(local_on.frames, local_off.frames), "local patch frames changed by the flag");
        require(local_off.xs[1] == base.xs[1] && local_off.ys[1] == base.ys[1], "is_global changes the unflagged update");
        std::printf("  local patch (is_global=false): flag has no effect\n");

        // 5. tolerance override: global only, inert when unset.
        require(!runOnce(runner, true, false, 0, 1).converged, "unset tolerance must keep the 0.5 px stop");
        const Run tol_global = runOnce(runner, true, false, 1e9, 5);
        require(tol_global.converged && countIterations(tol_global.log) == 1, "a 1e9 px tolerance must stop the global alignment at iteration 1");
        const Run tol_local = runOnce(runner, false, false, 1e9, 1);
        require(!tol_local.converged, "the tolerance override must not apply to local patches");
        const Run default_5 = runOnce(runner, true, false, 0, 5);
        const Run tight_5 = runOnce(runner, true, false, 1e-30, 5);
        require(countIterations(tight_5.log) == 5 && !tight_5.converged, "a 1e-30 px tolerance must run all iterations");
        require(countIterations(default_5.log) <= 5, "sanity");
        std::printf("  tolerance override: global only (1e9 stops at iter 1; 1e-30 runs all 5; local unaffected)\n");

        std::printf("PASS\n");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL RelionError\n" << e;
        return 1;
    }
}
