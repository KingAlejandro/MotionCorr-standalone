// Issue #69 -- shift-accumulation contract behind the local-patch retry.
//
// WHAT THIS PROVES, AND WHAT IT DOES NOT
//
// It runs the production MotioncorrRunner::alignPatch on a synthetic patch with an
// exactly known displacement, forces nonconvergence, and re-enters it the way the
// resident CUDA path's fallback does. It shows that re-entering WITHOUT resetting the
// caller's shift vectors publishes the sum of two independent estimates -- roughly
// twice the true shift -- and that resetting them publishes the true shift once.
//
// That is the premise of the production fix in motioncorr_runner.cpp, established on
// production code with no device involved. It is NOT an end-to-end validation of the
// fix: the retry it justifies lives inside #ifdef _CUDA_ENABLED and cannot execute in
// a CPU-only build. The end-to-end witness needs a GPU and is listed under NEEDS_GPU.
//
// The synthetic content is built in Fourier space and displaced by an exact phase
// ramp, so it is periodic and wraps at the patch edge. Non-wrapping content would
// bias the recovered shift low and could be mistaken for an aligner defect.
//
// It also guards the contract going forward: if alignPatch ever stopped accumulating
// and started treating the incoming shifts as absolute, arm B would no longer double
// and this control would fail, which is the signal to revisit the reset in
// motioncorr_runner.cpp rather than to relax the assertion.

#include "src/motioncorr_runner.h"
#include "src/jaz/single_particle/new_ft.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <vector>

// Declared a friend by MotioncorrRunner; see src/motioncorr_runner.h.
struct MotioncorrRunnerTestAccess {
    static bool alignPatch(MotioncorrRunner &runner,
                           std::vector<MultidimArray<fComplex> > &Fframes,
                           int pnx, int pny, RFLOAT scaled_B,
                           std::vector<RFLOAT> &xshifts,
                           std::vector<RFLOAT> &yshifts,
                           std::ostream &logfile) {
        return runner.alignPatch(Fframes, pnx, pny, scaled_B, xshifts, yshifts, logfile, false);
    }
};

namespace {

const int PNX = 256;
const int PNY = 256;
const int NFRAMES = 4;
const RFLOAT SCALED_B = 20.0;

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

// Deterministic, portable, and independent of any std:: distribution implementation.
unsigned int nextRandom(unsigned int &state) {
    state = state * 1664525u + 1013904223u;
    return state;
}

// Band-limited periodic speckle. Built directly in the half-complex R2C layout with
// explicit Hermitian symmetry on the x == 0 column, so the inverse transform is real
// and the image wraps exactly.
void buildBaseSpectrum(MultidimArray<fComplex> &F) {
    const int nfx = PNX / 2 + 1, nfy = PNY;
    F.reshape(nfy, nfx);
    F.initZeros();
    const int radius = 24;
    unsigned int state = 20260928u;
    for (int y = 0; y < nfy; y++) {
        const int ly = (y > nfy / 2) ? (y - nfy) : y;
        if (std::abs(ly) > radius) continue;
        for (int x = 0; x < nfx; x++) {
            if (x > radius) continue;
            if (x == 0 && ly == 0) continue;               // no DC
            if (x == 0 && ly < 0) continue;                // filled by symmetry below
            const double r = std::sqrt((double)(x * x + ly * ly));
            const double amp = 1.0 / (1.0 + r);            // smooth falloff, broad support
            const double phase = 2.0 * M_PI * (nextRandom(state) / 4294967296.0);
            DIRECT_A2D_ELEM(F, y, x) = fComplex((float)(amp * std::cos(phase)),
                                                (float)(amp * std::sin(phase)));
        }
    }
    // Hermitian partner for the x == 0 column: F(0, -ly) = conj(F(0, ly)).
    for (int ly = 1; ly <= radius; ly++) {
        const fComplex v = DIRECT_A2D_ELEM(F, ly, 0);
        DIRECT_A2D_ELEM(F, nfy - ly, 0) = fComplex(v.real, -v.imag);
    }
    // The Nyquist row must be real for a real inverse.
    DIRECT_A2D_ELEM(F, nfy / 2, 0) = fComplex(0.0f, 0.0f);
}

// Displace by (sx, sy) real-space pixels with an exact phase ramp.
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

// Truth: frame k is displaced by these amounts relative to frame 0. The magnitudes are
// well above alignPatch's 0.5 px convergence tolerance, so a single iteration cannot
// converge and the caller sees the nonconverged verdict the retry reacts to.
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1};

void buildPatchStack(std::vector<MultidimArray<fComplex> > &Fframes) {
    MultidimArray<fComplex> base;
    buildBaseSpectrum(base);
    Fframes.resize(NFRAMES);
    for (int k = 0; k < NFRAMES; k++)
        shiftSpectrum(base, Fframes[k], TRUE_SX[k], TRUE_SY[k]);
}

double norm2(const std::vector<RFLOAT> &xs, const std::vector<RFLOAT> &ys) {
    double acc = 0.0;
    for (size_t i = 0; i < xs.size(); i++) acc += (double)xs[i] * xs[i] + (double)ys[i] * ys[i];
    return std::sqrt(acc);
}

void report(const char *label, const std::vector<RFLOAT> &xs, const std::vector<RFLOAT> &ys) {
    std::printf("  %-28s", label);
    for (size_t i = 0; i < xs.size(); i++)
        std::printf(" (%+7.3f,%+7.3f)", (double)xs[i], (double)ys[i]);
    std::printf("   |v| = %.4f\n", norm2(xs, ys));
}

} // namespace

int main() {
    try {
        MotioncorrRunner runner;
        runner.n_threads = 1;
        runner.max_iter = 1;          // force the nonconverged verdict the retry reacts to
        runner.ccf_downsample = 1.0;  // no CCF downsampling, so the recovered shift is direct
        runner.interpolate_shifts = false;

        const double truth = std::sqrt(
            TRUE_SX[0]*TRUE_SX[0] + TRUE_SY[0]*TRUE_SY[0] +
            TRUE_SX[1]*TRUE_SX[1] + TRUE_SY[1]*TRUE_SY[1] +
            TRUE_SX[2]*TRUE_SX[2] + TRUE_SY[2]*TRUE_SY[2] +
            TRUE_SX[3]*TRUE_SX[3] + TRUE_SY[3]*TRUE_SY[3]);

        std::ostringstream log;

        // --- First attempt. This is what the resident CUDA path does: it accumulates
        //     its estimate into the caller's vectors and reports nonconvergence.
        std::vector<MultidimArray<fComplex> > attempt1;
        buildPatchStack(attempt1);
        std::vector<RFLOAT> xs(NFRAMES, 0.0), ys(NFRAMES, 0.0);
        const bool converged1 =
            MotioncorrRunnerTestAccess::alignPatch(runner, attempt1, PNX, PNY, SCALED_B, xs, ys, log);
        const std::vector<RFLOAT> s1x = xs, s1y = ys;

        std::printf("Issue #69 patch retry shift-state contract (CPU, no device)\n");
        std::printf("  patch %dx%d, %d groups, max_iter=%d, scaled_B=%.1f\n",
                    PNX, PNY, NFRAMES, runner.max_iter, (double)SCALED_B);
        std::printf("  |truth| = %.4f px\n", truth);
        report("attempt 1 (S1)", s1x, s1y);

        require(!converged1,
                "Setup error: the first attempt converged, so it does not reproduce the "
                "state the retry reacts to. Increase the synthetic shift or lower max_iter.");
        require(std::fabs(norm2(s1x, s1y) - truth) < 0.25 * truth,
                "Setup error: the first attempt did not recover the known shift, so the "
                "arms below would not be comparable.");

        // --- Arm B: re-enter WITHOUT resetting, which is what main did at 4c952b3f.
        //     The patch data is rebuilt exactly as the production fallback rebuilds it:
        //     from the same, still unshifted frames.
        std::vector<MultidimArray<fComplex> > attempt2_noreset;
        buildPatchStack(attempt2_noreset);
        std::vector<RFLOAT> bx = s1x, by = s1y;
        MotioncorrRunnerTestAccess::alignPatch(runner, attempt2_noreset, PNX, PNY, SCALED_B, bx, by, log);
        report("arm B: no reset (S1+S2)", bx, by);

        // --- Arm A: re-enter after restoring the state the first attempt touched.
        std::vector<MultidimArray<fComplex> > attempt2_reset;
        buildPatchStack(attempt2_reset);
        std::vector<RFLOAT> ax(NFRAMES, 0.0), ay(NFRAMES, 0.0);
        MotioncorrRunnerTestAccess::alignPatch(runner, attempt2_reset, PNX, PNY, SCALED_B, ax, ay, log);
        report("arm A: reset (S2)", ax, ay);

        const double na = norm2(ax, ay), nb = norm2(bx, by);
        std::printf("  |arm A| = %.4f   |arm B| = %.4f   ratio B/A = %.4f\n", na, nb, nb / na);

        // The reset arm reproduces the truth; the non-reset arm doubles it.
        require(std::fabs(na - truth) < 0.10 * truth,
                "Reset arm did not recover the known shift once");
        require(nb > 1.80 * na,
                "Non-reset arm did not show the doubled correction the fix removes");
        require(std::fabs(nb / na - 2.0) < 0.20,
                "Non-reset arm was not close to exactly twice the reset arm");

        // Per-frame, arm B should be the elementwise sum of the two independent estimates.
        double max_dev = 0.0;
        for (int k = 0; k < NFRAMES; k++) {
            max_dev = std::max(max_dev, std::fabs((double)bx[k] - ((double)s1x[k] + (double)ax[k])));
            max_dev = std::max(max_dev, std::fabs((double)by[k] - ((double)s1y[k] + (double)ay[k])));
        }
        std::printf("  max |armB - (S1 + armA)| per frame = %.6f px\n", max_dev);
        require(max_dev < 1e-3,
                "Arm B was not the elementwise sum of the two independent estimates");

        std::printf("PASS alignPatch accumulates; re-entry without reset publishes S1+S2\n");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL RelionError\n" << e;
        return 1;
    }
}
