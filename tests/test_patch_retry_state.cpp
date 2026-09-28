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
        runner.ccf_downsample = 1.0;  // no CCF downsampling, so shifts are recovered directly
        runner.interpolate_shifts = false;

        std::ostringstream log;
        std::printf("Issue #69 patch retry shift-state contract (CPU, no device)\n");
        std::printf("  patch %dx%d, %d groups, scaled_B=%.1f, truth (frame-0 relative):",
                    PNX, PNY, NFRAMES, (double)SCALED_B);
        for (int k = 0; k < NFRAMES; k++) std::printf(" (%+.2f,%+.2f)", TRUE_SX[k], TRUE_SY[k]);
        std::printf("\n\n");

        // ----------------------------------------------------------------------
        // Truth anchor. With enough iterations the estimator converges, and the
        // accumulated correction is the negative of the applied displacement. This
        // ties the arms below to a known quantity rather than only to each other.
        // ----------------------------------------------------------------------
        runner.max_iter = 12;
        std::vector<MultidimArray<fComplex> > anchor_stack;
        buildPatchStack(anchor_stack);
        std::vector<RFLOAT> anchor_x(NFRAMES, 0.0), anchor_y(NFRAMES, 0.0);
        const bool anchor_converged = MotioncorrRunnerTestAccess::alignPatch(
            runner, anchor_stack, PNX, PNY, SCALED_B, anchor_x, anchor_y, log);
        report("converged reference", anchor_x, anchor_y);
        double anchor_dev = 0.0;
        for (int k = 0; k < NFRAMES; k++) {
            anchor_dev = std::max(anchor_dev, std::fabs((double)anchor_x[k] + TRUE_SX[k]));
            anchor_dev = std::max(anchor_dev, std::fabs((double)anchor_y[k] + TRUE_SY[k]));
        }
        std::printf("  max |recovered + truth| = %.4f px  (converged=%s)\n\n",
                    anchor_dev, anchor_converged ? "yes" : "no");
        require(anchor_converged, "Truth anchor did not converge; the fixture is not usable");
        require(anchor_dev < 0.30,
                "Truth anchor did not recover the applied displacement; the fixture, not "
                "the contract, is what this control would be measuring");

        // ----------------------------------------------------------------------
        // Nonconvergence arms. One iteration cannot reach the 0.5 px tolerance for
        // these displacements, which is the state the resident CUDA path's fallback
        // reacts to.
        // ----------------------------------------------------------------------
        runner.max_iter = 1;

        // First attempt: accumulates its estimate S1 into the caller's vectors and
        // reports nonconvergence. This is what alignPatchDevice does in production.
        std::vector<MultidimArray<fComplex> > attempt1;
        buildPatchStack(attempt1);
        std::vector<RFLOAT> s1x(NFRAMES, 0.0), s1y(NFRAMES, 0.0);
        const bool converged1 = MotioncorrRunnerTestAccess::alignPatch(
            runner, attempt1, PNX, PNY, SCALED_B, s1x, s1y, log);
        report("attempt 1 (S1)", s1x, s1y);
        require(!converged1,
                "Setup error: the first attempt converged, so it does not reproduce the "
                "state the retry reacts to");
        require(norm2(s1x, s1y) > 1.0, "First attempt produced no usable estimate");

        // Arm A: restore the state the first attempt touched, then retry. The patch
        // data is rebuilt exactly as the production fallback rebuilds it -- from the
        // same, still unshifted frames.
        std::vector<MultidimArray<fComplex> > attempt2_reset;
        buildPatchStack(attempt2_reset);
        std::vector<RFLOAT> ax(NFRAMES, 0.0), ay(NFRAMES, 0.0);
        MotioncorrRunnerTestAccess::alignPatch(runner, attempt2_reset, PNX, PNY, SCALED_B, ax, ay, log);
        report("arm A: reset (S2)", ax, ay);

        // Arm B: retry without resetting, which is what main did at 4c952b3f.
        std::vector<MultidimArray<fComplex> > attempt2_noreset;
        buildPatchStack(attempt2_noreset);
        std::vector<RFLOAT> bx = s1x, by = s1y;
        MotioncorrRunnerTestAccess::alignPatch(runner, attempt2_noreset, PNX, PNY, SCALED_B, bx, by, log);
        report("arm B: no reset (S1+S2)", bx, by);

        const double na = norm2(ax, ay), nb = norm2(bx, by);
        std::printf("  |arm A| = %.4f   |arm B| = %.4f   ratio B/A = %.4f\n", na, nb, nb / na);

        // The two attempts see identical input, so the retry re-derives the same
        // estimate rather than refining the first one.
        double reproduce_dev = 0.0, sum_dev = 0.0;
        for (int k = 0; k < NFRAMES; k++) {
            reproduce_dev = std::max(reproduce_dev, std::fabs((double)ax[k] - (double)s1x[k]));
            reproduce_dev = std::max(reproduce_dev, std::fabs((double)ay[k] - (double)s1y[k]));
            sum_dev = std::max(sum_dev, std::fabs((double)bx[k] - ((double)s1x[k] + (double)ax[k])));
            sum_dev = std::max(sum_dev, std::fabs((double)by[k] - ((double)s1y[k] + (double)ay[k])));
        }
        std::printf("  max |armA - S1|              = %.3e px\n", reproduce_dev);
        std::printf("  max |armB - (S1 + armA)|     = %.3e px\n", sum_dev);

        require(reproduce_dev < 1e-6,
                "The retry did not re-derive the same estimate, so the two arms are not "
                "measuring the accumulation");
        require(sum_dev < 1e-6,
                "Arm B was not the elementwise sum of the two independent estimates");
        require(std::fabs(nb / na - 2.0) < 0.01,
                "Arm B was not twice arm A");

        std::printf("\nPASS alignPatch accumulates into the caller's vectors and does not\n"
                    "     re-derive them, so re-entering without a reset publishes S1+S2.\n"
                    "     Restoring the vectors publishes the single estimate S2.\n");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL RelionError\n" << e;
        return 1;
    }
}
