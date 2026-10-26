// Experimental --experimental_isotropic_weight (default off, CPU only): W5's `iso` CCF weight for the global alignment.
//
// 1. ccfWeightAt reproduces the W5 lib.py weights at sample bins, with reference values computed from the W5 formulas
//    (numpy double; indep.py W_prod / W_iso at 128 x 96, B = 150):
//      prod: exp(-2 B ((ky/NY)^2 + (|kx|/(NX/2+1))^2)),  iso: exp(-2 B ((ky/NY)^2 + (kx/NX)^2)).
//    Native prod is ccfWeightAt with x_norm = nfx = NX/2 + 1 = 65, iso is x_norm = NX = 128.
// 2. Through the production alignPatch: the flag changes the global estimate, leaves the unflagged result bitwise unchanged
//    and leaves a patch alignment (is_global == false) bitwise unchanged.

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

void require(bool ok, const std::string &m) { if (!ok) throw std::runtime_error(m); }

const int PNX = 256, PNY = 256, NFRAMES = 5;
const RFLOAT SCALED_B = 20.0;
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9, -1.3};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1, 0.7};

unsigned int nextRandom(unsigned int &s) { s = s * 1664525u + 1013904223u; return s; }

void buildStack(std::vector<MultidimArray<fComplex> > &F) {
    const int nfx = PNX / 2 + 1, nfy = PNY, radius = 24;
    MultidimArray<fComplex> base;
    base.reshape(nfy, nfx);
    base.initZeros();
    unsigned int state = 20261026u;
    for (int y = 0; y < nfy; y++) {
        const int ly = (y > nfy / 2) ? (y - nfy) : y;
        if (std::abs(ly) > radius) continue;
        for (int x = 0; x < nfx; x++) {
            if (x > radius || (x == 0 && ly <= 0)) continue;
            const double amp = 1.0 / (1.0 + std::sqrt((double)(x * x + ly * ly)));
            const double ph = 2.0 * M_PI * (nextRandom(state) / 4294967296.0);
            DIRECT_A2D_ELEM(base, y, x) = fComplex((float)(amp * std::cos(ph)), (float)(amp * std::sin(ph)));
        }
    }
    for (int ly = 1; ly <= radius; ly++) {
        const fComplex v = DIRECT_A2D_ELEM(base, ly, 0);
        DIRECT_A2D_ELEM(base, nfy - ly, 0) = fComplex(v.real, -v.imag);
    }
    F.resize(NFRAMES);
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

struct Run { std::vector<RFLOAT> xs, ys; };

Run runOnce(MotioncorrRunner &r, bool iso, bool is_global) {
    r.experimental_isotropic_weight = iso;
    r.max_iter = 3;
    std::vector<MultidimArray<fComplex> > F;
    buildStack(F);
    Run out;
    out.xs.assign(NFRAMES, 0.0); out.ys.assign(NFRAMES, 0.0);
    std::ostringstream log;
    MotioncorrRunnerTestAccess::alignPatch(r, F, PNX, PNY, SCALED_B, out.xs, out.ys, log, is_global);
    return out;
}

bool same(const Run &a, const Run &b) { return a.xs == b.xs && a.ys == b.ys; }

} // namespace

int main() {
    try {
        // ---- 1. weights against W5 reference values (128 x 96, B = 150); ly is the signed row frequency ----
        struct S { int ly, x; double prod, iso; };
        const S samples[] = {
            {0, 40, 4.5712523020798704e-50, 1.8902918004419459e-13},
            {3, 0, 0.74604545425339064, 0.74604545425339064},
            {10, 25, 2.0552148547844681e-21, 4.1321403643274364e-07},
            {-46, 64, 5.9620511844987564e-157, 3.2630179716104784e-63},
            {48, 3, 1.4137628169988878e-33, 2.271665236535099e-33},
            {0, 0, 1.0, 1.0},
            {7, 63, 8.1908218500977508e-124, 5.5605411829859987e-33}};
        for (const S &s : samples) {
            const double p = MotioncorrRunner::ccfWeightAt(s.ly, s.x, 96, 65.0, 150.0);
            const double i = MotioncorrRunner::ccfWeightAt(s.ly, s.x, 96, 128.0, 150.0);
            std::printf("  ly=%+3d x=%2d: prod %.6e (W5 %.6e)  iso %.6e (W5 %.6e)\n", s.ly, s.x, p, s.prod, i, s.iso);
            require(std::fabs(p - s.prod) <= 1e-12 * s.prod, "prod weight differs from W5");
            require(std::fabs(i - s.iso) <= 1e-12 * s.iso, "iso weight differs from W5");
        }
        require(MotioncorrRunner::ccfWeightAt(0, 40, 96, 128.0, 150.0) > 1e30 * MotioncorrRunner::ccfWeightAt(0, 40, 96, 65.0, 150.0),
                "iso must be far more permissive than prod along x");

        // ---- 2. through alignPatch ----
        MotioncorrRunner runner;
        runner.use_gpu = false; runner.gpu_id = 0; runner.n_threads = 1;
        runner.ccf_downsample = 1.0; runner.interpolate_shifts = false;
        MotioncorrRunner fresh;
        require(!fresh.experimental_isotropic_weight, "default must be off");
        const Run off = runOnce(runner, false, true), on = runOnce(runner, true, true);
        require(!same(off, on), "the flag did not change the global estimate");
        require(same(off, runOnce(runner, false, true)), "unflagged run is not reproducible");
        const Run l_off = runOnce(runner, false, false), l_on = runOnce(runner, true, false);
        require(same(l_off, l_on), "the flag must not change a patch alignment");
        std::printf("  alignPatch: flag changes the global estimate only\n");
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
