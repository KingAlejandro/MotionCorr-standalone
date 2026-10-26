// Experimental hypothesis H2 (default-off, CPU only): coupled 2x2-Hessian subpixel peak.
// Frozen spec: docs/post_rc0/s1/global_damping_20261026/H2-coupled-peak-PREDICTION.md.
//
// 1. Operator level, on exact quadratic peaks with a known offset and a tilted Hessian
//    (rho != 0): MotioncorrRunner::coupledPeakOffset recovers the offset to rounding error,
//    while the inherited separable parabola (reproduced verbatim from alignPatch as the
//    control) misses it by about rho * (the other offset component).
// 2. The fixed guard: not negative definite -> 1, |delta| > 1 px in either component -> 2,
//    and the offset is left untouched on rejection.
// 3. Through the production alignPatch on a 5-frame periodic fixture: off is bitwise the
//    default; "global" changes the global estimate and counts every peak, leaves local
//    patches bitwise unchanged; "all" also changes (and counts) patch peaks.

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
    static bool alignPatch(MotioncorrRunner &runner, std::vector<MultidimArray<fComplex> > &Fframes,
                           int pnx, int pny, RFLOAT scaled_B, std::vector<RFLOAT> &xshifts,
                           std::vector<RFLOAT> &yshifts, std::ostream &logfile, bool is_global) {
        return runner.alignPatch(Fframes, pnx, pny, scaled_B, xshifts, yshifts, logfile, is_global);
    }
};

namespace {

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

// Exact quadratic peak f = -1/2 (d^T H d), d = (x - px, y - py), sampled at integer x, y in {-1,0,1}.
void sampleQuadratic(double hxx, double hyy, double hxy, double px, double py, RFLOAT v[3][3]) {
    for (int iy = -1; iy <= 1; iy++)
        for (int ix = -1; ix <= 1; ix++) {
            const double dx = ix - px, dy = iy - py;
            v[iy + 1][ix + 1] = -0.5 * (hxx * dx * dx + 2.0 * hxy * dx * dy + hyy * dy * dy);
        }
}

// The inherited separable fit, verbatim from alignPatch (control, not code under test).
void separable(const RFLOAT v[3][3], double &dx, double &dy) {
    const RFLOAT maxval = v[1][1];
    dx = -0.5 * (v[1][2] - v[1][0]) / (v[1][2] + v[1][0] - 2.0 * maxval);
    dy = -0.5 * (v[2][1] - v[0][1]) / (v[2][1] + v[0][1] - 2.0 * maxval);
}

const int PNX = 256, PNY = 256, NFRAMES = 5;
const RFLOAT SCALED_B = 20.0;
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9, -1.3};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1, 0.7};

unsigned int nextRandom(unsigned int &state) { state = state * 1664525u + 1013904223u; return state; }

void buildBaseSpectrum(MultidimArray<fComplex> &F) {
    const int nfx = PNX / 2 + 1, nfy = PNY, radius = 24;
    F.reshape(nfy, nfx);
    F.initZeros();
    unsigned int state = 20261026u;
    for (int y = 0; y < nfy; y++) {
        const int ly = (y > nfy / 2) ? (y - nfy) : y;
        if (std::abs(ly) > radius) continue;
        for (int x = 0; x < nfx; x++) {
            if (x > radius || (x == 0 && ly <= 0)) continue;
            const double amp = 1.0 / (1.0 + std::sqrt((double)(x * x + ly * ly)));
            const double phase = 2.0 * M_PI * (nextRandom(state) / 4294967296.0);
            DIRECT_A2D_ELEM(F, y, x) = fComplex((float)(amp * std::cos(phase)), (float)(amp * std::sin(phase)));
        }
    }
    for (int ly = 1; ly <= radius; ly++) {
        const fComplex v = DIRECT_A2D_ELEM(F, ly, 0);
        DIRECT_A2D_ELEM(F, nfy - ly, 0) = fComplex(v.real, -v.imag);
    }
}

void buildStack(std::vector<MultidimArray<fComplex> > &F) {
    MultidimArray<fComplex> base;
    buildBaseSpectrum(base);
    F.resize(NFRAMES);
    const int nfx = PNX / 2 + 1, nfy = PNY;
    for (int k = 0; k < NFRAMES; k++) {
        F[k].reshape(nfy, nfx);
        for (int y = 0; y < nfy; y++) {
            const int ly = (y > nfy / 2) ? (y - nfy) : y;
            for (int x = 0; x < nfx; x++) {
                const double ph = -2.0 * M_PI * ((double)x * TRUE_SX[k] / PNX + (double)ly * TRUE_SY[k] / PNY);
                const fComplex v = DIRECT_A2D_ELEM(base, y, x);
                DIRECT_A2D_ELEM(F[k], y, x) = fComplex((float)(v.real * std::cos(ph) - v.imag * std::sin(ph)),
                                                       (float)(v.real * std::sin(ph) + v.imag * std::cos(ph)));
            }
        }
    }
}

struct Run { std::vector<RFLOAT> xs, ys; long peaks, notnd, off1; };

Run runOnce(MotioncorrRunner &r, bool is_global, int mode, int max_iter) {
    r.experimental_coupled_peak = mode;
    r.coupled_peak_last_peaks = r.coupled_peak_last_not_negdef = r.coupled_peak_last_offset_gt_1px = 0;
    r.max_iter = max_iter;
    std::vector<MultidimArray<fComplex> > F;
    buildStack(F);
    Run out;
    out.xs.assign(NFRAMES, 0.0); out.ys.assign(NFRAMES, 0.0);
    std::ostringstream log;
    MotioncorrRunnerTestAccess::alignPatch(r, F, PNX, PNY, SCALED_B, out.xs, out.ys, log, is_global);
    out.peaks = r.coupled_peak_last_peaks; out.notnd = r.coupled_peak_last_not_negdef; out.off1 = r.coupled_peak_last_offset_gt_1px;
    return out;
}

bool same(const Run &a, const Run &b) { return a.xs == b.xs && a.ys == b.ys; }

} // namespace

int main() {
    try {
        // ---- 1. exact tilted quadratics ----
        struct Q { double hxx, hyy, hxy, px, py; };
        const Q cases[] = {{1.0, 1.0, 0.756418, 0.30, -0.20}, {1.0, 1.0, -0.756418, -0.45, 0.25},
                           {2.0, 0.7, 0.9, 0.10, 0.35}, {1.5, 1.2, 0.0, 0.40, -0.30}};
        for (const Q &q : cases) {
            RFLOAT v[3][3];
            sampleQuadratic(q.hxx, q.hyy, q.hxy, q.px, q.py, v);
            RFLOAT dx = 0, dy = 0;
            const int verdict = MotioncorrRunner::coupledPeakOffset(v, dx, dy);
            double sx, sy;
            separable(v, sx, sy);
            const double ecx = std::fabs(dx - q.px), ecy = std::fabs(dy - q.py);
            const double esx = std::fabs(sx - q.px), esy = std::fabs(sy - q.py);
            const double rho = q.hxy / std::sqrt(q.hxx * q.hyy);
            std::printf("  rho=%+.3f offset=(%+.2f,%+.2f): coupled err (%.2e,%.2e), separable err (%.2e,%.2e)\n",
                        rho, q.px, q.py, ecx, ecy, esx, esy);
            require(verdict == 0, "guard rejected an exact negative-definite quadratic");
            require(ecx < 1e-12 && ecy < 1e-12, "coupled estimate does not recover the exact offset to rounding error");
            if (std::fabs(rho) > 0.5)
                require(std::max(esx, esy) > 0.05, "control: the separable fit unexpectedly recovered a tilted peak");
            else
                require(std::max(esx, esy) < 1e-12, "control: with rho = 0 the separable fit must be exact");
        }

        // ---- 2. guard ----
        {
            RFLOAT v[3][3], dx = 7, dy = 7;
            sampleQuadratic(-1.0, -1.0, 0.0, 0.2, 0.2, v);   // positive curvature: a minimum
            require(MotioncorrRunner::coupledPeakOffset(v, dx, dy) == 1 && dx == 7 && dy == 7, "positive-definite H must fall back (1)");
            sampleQuadratic(1.0, -1.0, 0.0, 0.2, 0.2, v);    // saddle
            require(MotioncorrRunner::coupledPeakOffset(v, dx, dy) == 1, "saddle must fall back (1)");
            sampleQuadratic(1.0, 1.0, 1.2, 0.0, 0.0, v);     // hxx > 0, det < 0: indefinite
            require(MotioncorrRunner::coupledPeakOffset(v, dx, dy) == 1, "indefinite H must fall back (1)");
            for (int a = 0; a < 3; a++) for (int b = 0; b < 3; b++) v[a][b] = 5;   // flat (float32 deadzone)
            require(MotioncorrRunner::coupledPeakOffset(v, dx, dy) == 1 && dx == 7, "flat samples must fall back (1)");
            sampleQuadratic(1.0, 1.0, 0.0, 1.4, 0.0, v);     // true offset 1.4 px, beyond the guard
            const int far = MotioncorrRunner::coupledPeakOffset(v, dx, dy);
            require(far == 2 && dx == 7 && dy == 7, "offset > 1 px must fall back (2) and leave dx, dy untouched");
            sampleQuadratic(1.0, 1.0, 0.0, 0.98, -0.98, v);  // inside the guard
            require(MotioncorrRunner::coupledPeakOffset(v, dx, dy) == 0, "offset just inside 1 px must be accepted");
            std::printf("  guard: not-negative-definite and >1 px fall back, 0.98 px accepted\n");
        }

        // ---- 3. through alignPatch ----
        MotioncorrRunner runner;
        runner.use_gpu = false; runner.gpu_id = 0; runner.n_threads = 1;
        runner.ccf_downsample = 1.0; runner.interpolate_shifts = false;
        const Run def = runOnce(runner, true, 0, 1);
        require(def.peaks == 0 && def.notnd == 0 && def.off1 == 0, "off must not count");
        MotioncorrRunner fresh;   // default member initialisers: the option is off by default
        require(fresh.experimental_coupled_peak == 0, "default must be off");
        const Run g = runOnce(runner, true, 1, 1), a = runOnce(runner, true, 2, 1);
        require(g.peaks == NFRAMES && a.peaks == NFRAMES, "every global peak must be fitted (and counted) once per iteration");
        require(!same(g, def), "global mode did not change the global estimate");
        require(same(g, a), "global and all modes must agree on a global alignment");
        const Run l_off = runOnce(runner, false, 0, 1), l_glob = runOnce(runner, false, 1, 1), l_all = runOnce(runner, false, 2, 1);
        require(same(l_off, l_glob) && l_glob.peaks == 0, "global mode must leave patch alignment bitwise unchanged and uncounted");
        require(!same(l_off, l_all) && l_all.peaks == NFRAMES, "all mode must change and count patch peaks");
        require(same(runOnce(runner, true, 0, 1), def), "off is not reproducible");
        std::printf("  alignPatch: off == default; global changes global only (%ld peaks); all changes patches (%ld peaks)\n", g.peaks, l_all.peaks);
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
