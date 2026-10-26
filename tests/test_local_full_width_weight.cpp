// Experimental --experimental_local_full_width_weight (default off, CPU only): LOCAL patch alignments divide the CCF
// weight's x frequency by the full patch width pnx instead of nfx = pnx/2 + 1.
//
// 1. Weights: flag off reproduces the inherited expression bitwise (x_norm = nfx); flag on, local, reproduces the physical
//    exp(-2 B ((ky/pny)^2 + (kx/pnx)^2)) on non-square patches, including the 42 x 32, B = 150 saved-state geometry,
//    and equal physical frequencies map to equal weights across different pnx.
// 2. Selection: the flag changes only a patch alignment; global x_norm is unchanged with or without the global
//    isotropic flag (that harmful arm is preserved).
// 3. Through alignPatch (non-square, nothing mocked): local ON equals the global isotropic arm bitwise on the same stack,
//    which can only hold if the production weight really uses x_norm = pnx; local ON differs from local OFF; global
//    results are bitwise independent of the flag, with and without the isotropic flag; local OFF is reproducible.
// A build with MC_EXPERIMENT_CCF_DC needs MC_EXPERIMENT_CCF_DC_ARM=none (the global and local arms would otherwise differ).

#include "src/motioncorr_runner.h"
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

void require(bool ok, const std::string &m) { if (!ok) throw std::runtime_error(m); }

// The inherited inline expression, verbatim, with an int denominator (nfx for the inherited weight, pnx for the full width).
RFLOAT inlineWeight(int ly, int x, int nfy, int x_denominator, RFLOAT scaled_B) {
    RFLOAT ly2 = ly * (RFLOAT)ly / (nfy * (RFLOAT)nfy);
    RFLOAT dist2 = ly2 + x * (RFLOAT)x / (x_denominator * x_denominator);
    return exp(- 2 * dist2 * scaled_B);
}

double physicalWeight(double kx, double nx, double ky, double ny, double B) {
    return std::exp(-2.0 * B * ((kx / nx) * (kx / nx) + (ky / ny) * (ky / ny)));
}

struct Geometry { int pnx, pny; RFLOAT B; };

const int NFRAMES = 5;
const RFLOAT SCALED_B = 20.0;
const double TRUE_SX[NFRAMES] = {0.0, 2.7, -3.4, 1.9, -1.3};
const double TRUE_SY[NFRAMES] = {0.0, -1.8, 2.2, -3.1, 0.7};

unsigned int nextRandom(unsigned int &s) { s = s * 1664525u + 1013904223u; return s; }

// Band-limited random spectrum, shifted per frame; non-square so a swapped or halved x normalisation cannot hide.
void buildStack(std::vector<MultidimArray<fComplex> > &F, int pnx, int pny) {
    const int nfx = pnx / 2 + 1, nfy = pny, radius = 24;
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
                const double ph = -2.0 * M_PI * ((double)x * TRUE_SX[k] / pnx + (double)ly * TRUE_SY[k] / pny);
                const fComplex v = DIRECT_A2D_ELEM(base, y, x);
                DIRECT_A2D_ELEM(F[k], y, x) = fComplex((float)(v.real * std::cos(ph) - v.imag * std::sin(ph)),
                                                       (float)(v.real * std::sin(ph) + v.imag * std::cos(ph)));
            }
        }
    }
}

struct Run { std::vector<RFLOAT> xs, ys; std::string log; };

Run runOnce(MotioncorrRunner &r, int pnx, int pny, bool is_global, bool iso, bool local_full) {
    r.experimental_isotropic_weight = iso;
    r.experimental_local_full_width_weight = local_full;
    r.max_iter = 3;
    std::vector<MultidimArray<fComplex> > F;
    buildStack(F, pnx, pny);
    Run out;
    out.xs.assign(NFRAMES, 0.0); out.ys.assign(NFRAMES, 0.0);
    std::ostringstream log;
    MotioncorrRunnerTestAccess::alignPatch(r, F, pnx, pny, SCALED_B, out.xs, out.ys, log, is_global);
    out.log = log.str();
    return out;
}

bool same(const Run &a, const Run &b) { return a.xs == b.xs && a.ys == b.ys; }

const std::string WITNESS = "EXPERIMENTAL local full-width weight";
bool hasWitness(const Run &r) { return r.log.find(WITNESS) != std::string::npos; }

} // namespace

int main() {
    try {
        const Geometry geoms[] = {{42, 32, 150}, {128, 96, 150}, {64, 48, 20}, {192, 128, 20}};
        const double rel = sizeof(RFLOAT) == 4 ? 2e-6 : 1e-12;

        // ---- 1. weights ----
        for (const Geometry &g : geoms) {
            const int nfx = g.pnx / 2 + 1;
            for (int ly = -g.pny / 2 + 1; ly <= g.pny / 2; ly++) {
                for (int x = 0; x < nfx; x++) {
                    // flag off: inherited arithmetic exactly, x_norm = nfx
                    const RFLOAT off_norm = MotioncorrRunner::ccfWeightXNorm(false, false, g.pnx, nfx, false);
                    require(off_norm == (RFLOAT)nfx, "flag off must keep nfx");
                    require(MotioncorrRunner::ccfWeightAt(ly, x, g.pny, off_norm, g.B) == inlineWeight(ly, x, g.pny, nfx, g.B),
                            "flag off weight differs from the inherited expression");
                    // flag on, local: full width, same operation order
                    const RFLOAT on_norm = MotioncorrRunner::ccfWeightXNorm(false, false, g.pnx, nfx, true);
                    require(on_norm == (RFLOAT)g.pnx, "local full-width weight must normalise by pnx");
                    const RFLOAT w = MotioncorrRunner::ccfWeightAt(ly, x, g.pny, on_norm, g.B);
                    require(w == inlineWeight(ly, x, g.pny, g.pnx, g.B), "full-width weight differs from the inherited operation order");
                    const double p = physicalWeight(x, g.pnx, ly, g.pny, g.B);
                    require(std::fabs(w - p) <= rel * p, "full-width weight differs from the physical formula");
                }
            }
        }
        // The 42 x 32 B = 150 saved-state geometry: x denominator 22 -> 42 changes the active x extent, and in float32 the
        // native full-width weight equals the literal physical formula in every bin (704 half-spectrum bins).
        {
            int changed = 0, bins = 0;
            for (int ly = -15; ly <= 16; ly++) {
                for (int x = 0; x < 22; x++) {
                    const float inherited = (float)MotioncorrRunner::ccfWeightAt(ly, x, 32, 22, 150);
                    const float full = (float)MotioncorrRunner::ccfWeightAt(ly, x, 32, 42, 150);
                    if (sizeof(RFLOAT) == 8)
                        require(full == (float)physicalWeight(x, 42, ly, 32, 150), "42x32 float32 weight differs from the literal formula");
                    if (full != inherited) changed++;
                    bins++;
                }
            }
            require(bins == 704, "42x32 half-spectrum bin count");
            require(changed > 600, "full-width weight must change most 42x32 bins");
            require(MotioncorrRunner::ccfWeightAt(0, 21, 32, 42, 150) > 1e10 * MotioncorrRunner::ccfWeightAt(0, 21, 32, 22, 150),
                    "x frequency 21 must be far less suppressed at the full-width normalisation");
        }
        // Physical-frequency pairs: x/pnx equal (pnx 64 and 128, x 10 and 20) gives equal weight at equal ky/pny; the
        // inherited normalisation does not (nfx 33 vs 65).
        {
            const RFLOAT a = MotioncorrRunner::ccfWeightAt(5, 10, 48, MotioncorrRunner::ccfWeightXNorm(false, false, 64, 33, true), 20);
            const RFLOAT b = MotioncorrRunner::ccfWeightAt(10, 20, 96, MotioncorrRunner::ccfWeightXNorm(false, false, 128, 65, true), 20);
            require(std::fabs(a - b) <= rel * a, "equal physical frequencies must give equal full-width weights");
            const RFLOAT ia = MotioncorrRunner::ccfWeightAt(5, 10, 48, 33, 20), ib = MotioncorrRunner::ccfWeightAt(10, 20, 96, 65, 20);
            require(std::fabs(ia - ib) > 1e-3 * ia, "inherited weights must not agree at equal physical frequencies (control)");
        }

        // ---- 2. selection ----
        for (bool iso : {false, true}) {
            for (bool local_full : {false, true}) {
                const RFLOAT expect_global = iso ? 128.0 : 65.0;
                require(MotioncorrRunner::ccfWeightXNorm(true, iso, 128, 65, local_full) == expect_global,
                        "global x normalisation must not depend on the local full-width flag");
            }
        }
        require(MotioncorrRunner::ccfWeightXNorm(false, true, 128, 65, false) == 65.0, "global isotropic must not leak into a patch");
        require(MotioncorrRunner::ccfWeightXNorm(false, true, 128, 65, true) == 128.0, "local flag with isotropic set still uses pnx");

        // ---- 3. through alignPatch ----
        MotioncorrRunner fresh;
        require(!fresh.experimental_local_full_width_weight, "default must be off");
        MotioncorrRunner runner;
        runner.use_gpu = false; runner.gpu_id = 0; runner.n_threads = 1;
        runner.ccf_downsample = 1.0; runner.interpolate_shifts = false;
        for (const int pnx : {192, 96}) {
            const int pny = pnx * 2 / 3;
            const Run l_off = runOnce(runner, pnx, pny, false, false, false);
            const Run l_on = runOnce(runner, pnx, pny, false, false, true);
            require(same(l_off, runOnce(runner, pnx, pny, false, false, false)), "local OFF run is not reproducible");
            require(!same(l_off, l_on), "the flag did not change the local estimate");
            // Local ON must be exactly the global isotropic arm: same x_norm = pnx and nothing else differs in alignPatch.
            const Run g_iso = runOnce(runner, pnx, pny, true, true, false);
            require(same(l_on, g_iso), "local full-width weight is not x_norm = pnx through alignPatch");
            // The local isotropic flag setting is irrelevant to a patch.
            require(same(l_off, runOnce(runner, pnx, pny, false, true, false)), "the global isotropic flag changed a patch alignment");
            require(same(l_on, runOnce(runner, pnx, pny, false, true, true)), "isotropic changed the local full-width result");
            // Global: bitwise independent of the local flag, with and without isotropic.
            const Run g_off = runOnce(runner, pnx, pny, true, false, false);
            require(same(g_off, runOnce(runner, pnx, pny, true, false, true)), "local flag changed the global estimate");
            require(same(g_iso, runOnce(runner, pnx, pny, true, true, true)), "local flag changed the global isotropic estimate");
            require(!same(g_off, g_iso), "control: the global isotropic arm must differ from inherited global");
            // Diagnostic witness: exactly the actual selected normalisation, only for flag ON on a patch alignment.
            std::ostringstream expect;
            expect << " " << WITNESS << ": x_norm = " << (RFLOAT)pnx << ", pnx = " << pnx << ", nfx = " << pnx / 2 + 1 << "\n";
            require(l_on.log.compare(0, expect.str().size(), expect.str()) == 0 && l_on.log.find(WITNESS, expect.str().size()) == std::string::npos,
                    "local ON witness line differs from the actual x_norm/pnx/nfx: '" + l_on.log + "'");
            require(!hasWitness(l_off) && !hasWitness(g_off) && !hasWitness(g_iso), "witness without flag on a patch alignment");
            require(!hasWitness(runOnce(runner, pnx, pny, true, false, true)) && !hasWitness(runOnce(runner, pnx, pny, true, true, true)),
                    "witness on a global alignment");
            require(l_off.log.find("EXPERIMENTAL") == std::string::npos && g_off.log.find("EXPERIMENTAL") == std::string::npos
                        && g_iso.log.find("EXPERIMENTAL") == std::string::npos, "flag off must add no EXPERIMENTAL log line");
            std::printf("  pnx=%d pny=%d: local ON == global iso, local ON != local OFF, global bitwise unchanged\n", pnx, pny);
        }
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
