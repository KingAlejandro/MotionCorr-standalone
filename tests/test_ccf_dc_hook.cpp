// H3: operator control for the ported #262 CCF DC hook (built only with -DMC_EXPERIMENT_CCF_DC=ON).
//
// Runs the production MotioncorrRunner::alignPatch on a 5-frame periodic fixture carrying a large
// DC pedestal in every frame spectrum, once per hook arm, and checks:
//   * arm none:   global CCF frames are eligible but none is zeroed (hook inert);
//   * arm global: every global CCF frame is zeroed (5/5) and no patch CCF frame is (0/5);
//   * arm local:  the converse;
//   * the stage selection is observable in the result: a global call under arm local is bitwise the
//     arm-none result, a global call under arm global differs from it (the pedestal makes the
//     zeroed DC bin change the float32 CCF map), and a local call under arm global is bitwise the
//     arm-none result.
// Mutants of the hook (restore, wrong bin, stage swap) are run by scripts/mutants_h3.sh.

#include "src/motioncorr_runner.h"
#include "src/experiment_ccf_dc.h"
#include "src/jaz/single_particle/new_ft.h"

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

const int PNX = 256, PNY = 256, NFRAMES = 5;
const RFLOAT SCALED_B = 20.0;
const float PEDESTAL = 100.0f * PNX * PNY;   // 100 grey levels of mean, unnormalised DC bin
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9, -1.3};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1, 0.7};

void require(bool ok, const std::string &m) { if (!ok) throw std::runtime_error(m); }
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
        DIRECT_A2D_ELEM(F[k], 0, 0) = fComplex(PEDESTAL, 0.0f);
    }
}

struct Run { std::vector<RFLOAT> xs, ys; unsigned long long elig[2], zeroed[2]; };

Run runOnce(MotioncorrRunner &r, int arm, bool is_global) {
    experimentCcfDcSetArmForTest(arm);
    ExperimentCcfDcState &st = experimentCcfDcState();
    for (int site = 0; site < EXP_DC_SITES; site++)
        for (int stage = 0; stage < 2; stage++) { st.count[site][stage][0] = 0; st.count[site][stage][1] = 0; }
    std::vector<MultidimArray<fComplex> > F;
    buildStack(F);
    Run out;
    out.xs.assign(NFRAMES, 0.0); out.ys.assign(NFRAMES, 0.0);
    std::ostringstream log;
    r.max_iter = 1;
    MotioncorrRunnerTestAccess::alignPatch(r, F, PNX, PNY, SCALED_B, out.xs, out.ys, log, is_global);
    for (int stage = 0; stage < 2; stage++) { out.elig[stage] = st.count[EXP_DC_CPU][stage][0]; out.zeroed[stage] = st.count[EXP_DC_CPU][stage][1]; }
    return out;
}

bool same(const Run &a, const Run &b) { return a.xs == b.xs && a.ys == b.ys; }

} // namespace

int main() {
    try {
        MotioncorrRunner runner;
        runner.use_gpu = false; runner.gpu_id = 0; runner.n_threads = 1;
        runner.ccf_downsample = 1.0; runner.interpolate_shifts = false;
        const int NONE = 0, GLOBAL = 1, LOCAL = 2;

        const Run g_none = runOnce(runner, NONE, true), g_glob = runOnce(runner, GLOBAL, true), g_loc = runOnce(runner, LOCAL, true);
        const Run l_none = runOnce(runner, NONE, false), l_glob = runOnce(runner, GLOBAL, false), l_loc = runOnce(runner, LOCAL, false);
        auto show = [](const char *n, const Run &r) {
            std::printf("  %-22s global zeroed %llu/%llu, patch zeroed %llu/%llu\n", n, r.zeroed[0], r.elig[0], r.zeroed[1], r.elig[1]);
        };
        show("arm none, global call", g_none); show("arm global, global call", g_glob); show("arm local, global call", g_loc);
        show("arm none, patch call", l_none); show("arm global, patch call", l_glob); show("arm local, patch call", l_loc);

        require(g_none.elig[0] == NFRAMES && g_none.zeroed[0] == 0, "arm none must leave every global CCF DC bin untouched");
        require(g_glob.elig[0] == NFRAMES && g_glob.zeroed[0] == NFRAMES && g_glob.elig[1] == 0 && g_glob.zeroed[1] == 0,
                "arm global must zero N/N global CCF frames and touch no patch frame");
        require(g_loc.elig[0] == NFRAMES && g_loc.zeroed[0] == 0, "arm local must not zero a global CCF frame");
        require(l_glob.elig[1] == NFRAMES && l_glob.zeroed[1] == 0 && l_glob.elig[0] == 0, "arm global must not zero a patch CCF frame");
        require(l_loc.elig[1] == NFRAMES && l_loc.zeroed[1] == NFRAMES, "arm local must zero N/N patch CCF frames");
        require(same(g_loc, g_none), "a global call under arm local must equal the arm-none result bitwise");
        require(same(l_glob, l_none), "a patch call under arm global must equal the arm-none result bitwise");
        require(!same(g_glob, g_none), "zeroing the global DC bin of a pedestal-carrying CCF changed nothing");
        for (int k = 0; k < NFRAMES; k++)
            require(std::isfinite(g_glob.xs[k]) && std::isfinite(g_glob.ys[k]), "non-finite estimate");
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
