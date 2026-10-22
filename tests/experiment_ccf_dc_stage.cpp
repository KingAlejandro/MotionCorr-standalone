// SPDX-License-Identifier: GPL-2.0-or-later
// EXPERIMENT ONLY (#262): stage oracle for the four CCF DC conditioning arms.
// Built only with -DMC_EXPERIMENT_CCF_DC=ON. Contract and prospective criteria:
// docs/post_rc0/s1/dc_factorial_20261022/FREEZE.md.
//
// Every call goes through a production entry point: MotioncorrRunner::alignPatch
// (CPU, global and local), cudaAlignPatchDevice (CUDA per-patch path; global,
// local and the retry path) and cudaAlignPatchBatchDevice (CUDA batched local).
// Inputs are exactly Hermitian float half-spectra of band-limited periodic
// textures with known shifts; a pedestal is injected after "preprocessing" by
// adding P*pnx*pny to each frame's (0,0) bin only, so all non-DC bits are equal
// across pedestals.
//
// G1 selection: an arm zeroes exactly the selected stage at each site (counters).
// G2 pedestal invariance: a selected stage is bit-identical across P (shifts,
//    verdict, output spectra); a non-selected stage must change at P=4096
//    somewhere in the corpus (detection power), else G2 is INCONCLUSIVE.
// G3 same-CCF reference (max_iter 1, uncropped CCF): independent long-double
//    direct inverse of the identical float CCF spectrum without its DC term.
//    Selected stages at every P and every arm at P=0: integer peak equal where
//    the reference margin >= 1e-4 of contrast; fitted shift within 1e-3 px.
// G4 resident neutrality: each frame's (0,0) bin bytes are unchanged and frame
//    0's spectrum is byte-identical after alignment, in every arm.
// G5 power-of-two amplitude scaling (2^-6, 2^6) leaves shifts bit-identical.
// Flat, exact tie, boundary and nonfinite cases are characterization only.
//
// Exit 0: all gates pass. Exit 1: an oracle gate failed. Exit 2: setup error.
// --expect-failure (restoring mutants): exit 0 only if an oracle gate failed.
#include "src/motioncorr_runner.h"
#include "src/experiment_ccf_dc.h"
#ifdef _CUDA_ENABLED
#include "src/acc/cuda/cuda_alignpatch.h"
#include <cuda_runtime.h>
#endif
#include <cmath>
#include <complex>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef MC_EXPERIMENT_CCF_DC
#error "experiment_ccf_dc_stage requires -DMC_EXPERIMENT_CCF_DC=ON"
#endif

struct MotioncorrRunnerTestAccess {
    static bool alignPatch(MotioncorrRunner &runner, std::vector<MultidimArray<fComplex> > &F, int pnx, int pny,
                           RFLOAT B, std::vector<RFLOAT> &xs, std::vector<RFLOAT> &ys, std::ostream &log,
                           bool is_global) {
        return runner.alignPatch(F, pnx, pny, B, xs, ys, log, is_global);
    }
};

namespace {

typedef std::vector<MultidimArray<fComplex> > Stack;
typedef long double LD;

struct SetupError : std::runtime_error { using std::runtime_error::runtime_error; };

const double PEDESTALS[] = {0, 1, 16, 256, 4096};
const int N_PED = 5;
const char *ARM_NAMES[] = {"none", "global", "local", "both"};

enum Path { CPU_GLOBAL, CPU_LOCAL, CUDA_SINGLE_GLOBAL, CUDA_SINGLE_LOCAL, CUDA_BATCHED_LOCAL, N_PATHS };
const char *PATH_NAMES[] = {"cpu_global", "cpu_local", "cuda_single_global", "cuda_single_local", "cuda_batched_local"};
bool pathGlobal(int p) { return p == CPU_GLOBAL || p == CUDA_SINGLE_GLOBAL; }
ExperimentCcfDcSite pathSite(int p) {
    return p <= CPU_LOCAL ? EXP_DC_CPU : (p == CUDA_BATCHED_LOCAL ? EXP_DC_CUDA_BATCHED : EXP_DC_CUDA_SINGLE);
}
bool selected(int arm, int path) { return (arm >> (pathGlobal(path) ? 0 : 1)) & 1; }

struct Case {
    std::string name, kind;   // kind: texture, flat, nan_dc, nan_bin
    int pnx, pny, n;
    double B, down;
    int max_iter;
    double sx, sy, curve;     // frame f shift: f*(sx,sy) + curve*f*f*(1,-1); tie/boundary use 2 frames
    double amp;
    bool gate;                // G2..G5 apply; otherwise characterization
};

unsigned nextRandom(unsigned &s) { s = s * 1664525u + 1013904223u; return s; }
double uniform(unsigned &s) { return (nextRandom(s) >> 8) * (1.0 / 16777216.0) - 0.5; }

// Band-limited periodic texture with Nyquist row/column zero, shifted by exact
// signed-frequency phase ramps, rounded once to float, then made exactly
// Hermitian on the x=0 column by copying conjugates.
Stack buildStack(const Case &c, double pedestal, double scale) {
    const int nfx = c.pnx / 2 + 1, nfy = c.pny;
    std::vector<std::complex<double> > base((size_t)nfy * nfx);
    unsigned st = 262u + (unsigned)c.pnx * 7u + (unsigned)c.pny;
    const double rmax = 0.35;
    for (int y = 0; y < nfy; y++)
        for (int x = 0; x < nfx; x++) {
            const int ky = y <= nfy / 2 ? y : y - nfy;
            const double r = std::hypot((double)x / c.pnx, (double)ky / c.pny);
            const double a = uniform(st), b = uniform(st);
            if (c.kind == "flat" || r > rmax || (x == 0 && ky == 0) || x == c.pnx / 2 || y == nfy / 2) continue;
            base[(size_t)y * nfx + x] = std::complex<double>(a, b) * ((double)c.pnx * c.pny * 0.05 / (1 + 40 * r));
        }
    const int frames = c.n;
    Stack F(frames);
    for (int f = 0; f < frames; f++) {
        double dx = f * c.sx + c.curve * f * f, dy = f * c.sy - c.curve * f * f;
        F[f].reshape(nfy, nfx);
        for (int y = 0; y < nfy; y++)
            for (int x = 0; x < nfx; x++) {
                const int ky = y <= nfy / 2 ? y : y - nfy;
                const double ph = -2 * M_PI * ((double)x * dx / c.pnx + (double)ky * dy / c.pny);
                const std::complex<double> v = base[(size_t)y * nfx + x] * std::polar(1.0, ph) * c.amp * scale;
                DIRECT_A2D_ELEM(F[f], y, x) = fComplex((float)v.real(), (float)v.imag());
            }
        for (int y = nfy / 2 + 1; y < nfy; y++) {
            const fComplex v = DIRECT_A2D_ELEM(F[f], nfy - y, 0);
            DIRECT_A2D_ELEM(F[f], y, 0) = fComplex(v.real, -v.imag);
        }
        DIRECT_A2D_ELEM(F[f], 0, 0) = fComplex((float)(pedestal * c.pnx * c.pny * scale), 0.f);
    }
    if (c.kind == "nan_dc") DIRECT_A2D_ELEM(F[1], 0, 0).real = std::numeric_limits<float>::quiet_NaN();
    if (c.kind == "nan_bin") DIRECT_A2D_ELEM(F[1], 2, 3).real = std::numeric_limits<float>::quiet_NaN();
    return F;
}

bool hermitianX0(const Stack &F) {
    for (const auto &m : F) {
        const int ny = YSIZE(m);
        for (int y = 1; y < ny; y++) {
            const fComplex a = DIRECT_A2D_ELEM(m, y, 0), b = DIRECT_A2D_ELEM(m, (ny - y) % ny, 0);
            if (y == ny - y) { if (a.imag != 0.f) return false; continue; }
            if (!(a.real == b.real && a.imag == -b.imag)) return false;
        }
        if (DIRECT_A2D_ELEM(m, 0, 0).imag != 0.f) return false;
    }
    return true;
}

struct Result {
    std::vector<double> xs, ys;
    bool converged = false;
    Stack out;
    unsigned long long eligible = 0, zeroed = 0;
    bool wrong_stage = false; // the call was counted against the other stage
};

unsigned long long counter(int site, int stage, int kind) { return experimentCcfDcState().count[site][stage][kind].load(); }

#ifdef _CUDA_ENABLED
void ck(cudaError_t e, const char *what) { if (e != cudaSuccess) throw SetupError(std::string(what) + ": " + cudaGetErrorString(e)); }
#endif

Result run(const Case &c, int path, int arm, const Stack &in) {
    experimentCcfDcSetArmForTest(arm);
    const int site = pathSite(path), stage = pathGlobal(path) ? 0 : 1;
    const unsigned long long e0 = counter(site, stage, 0), z0 = counter(site, stage, 1);
    const unsigned long long other0 = counter(site, 1 - stage, 0);
    Result r;
    std::vector<RFLOAT> xs(c.n, 0), ys(c.n, 0);
    std::ostringstream log;
    const int nfx = c.pnx / 2 + 1, nfy = c.pny;
    if (path <= CPU_LOCAL) {
        MotioncorrRunner runner;
        runner.use_gpu = false; runner.n_threads = 1; runner.max_iter = c.max_iter;
        runner.ccf_downsample = c.down; runner.gpu_id = 0;
        Stack F = in;
        r.converged = MotioncorrRunnerTestAccess::alignPatch(runner, F, c.pnx, c.pny, c.B, xs, ys, log, pathGlobal(path));
        r.out = F;
    } else {
#ifdef _CUDA_ENABLED
        const size_t fr = (size_t)nfy * nfx;
        std::vector<fComplex> h((size_t)c.n * fr);
        for (int f = 0; f < c.n; f++) std::memcpy(&h[f * fr], in[f].data, fr * sizeof(fComplex));
        if (path != CUDA_BATCHED_LOCAL) {
            cufftComplex *d = nullptr;
            ck(cudaMalloc(&d, h.size() * sizeof(fComplex)), "malloc");
            ck(cudaMemcpy(d, h.data(), h.size() * sizeof(fComplex), cudaMemcpyHostToDevice), "upload");
            r.converged = cudaAlignPatchDevice(d, c.n, c.pnx, c.pny, c.B, xs, ys, c.max_iter, c.down, 0, log, pathGlobal(path));
            ck(cudaMemcpy(h.data(), d, h.size() * sizeof(fComplex), cudaMemcpyDeviceToHost), "download");
            ck(cudaFree(d), "free");
            r.out = in;
            for (int f = 0; f < c.n; f++) std::memcpy(r.out[f].data, &h[f * fr], fr * sizeof(fComplex));
        } else {
            // Two identical patches in one chunk: the second must equal the first.
            int cnx = 0, cny = 0;
            patchSpectrumWindow(c.pnx, c.pny, c.B, c.down, cnx, cny);
            const int wfx = cnx / 2 + 1;
            const size_t wfr = (size_t)cny * wfx;
            std::vector<fComplex> w((size_t)c.n * wfr);
            for (int f = 0; f < c.n; f++)
                for (int y = 0; y < cny; y++) {
                    const int fy = y <= cny / 2 ? y : y - cny + c.pny;
                    for (int x = 0; x < wfx; x++) w[f * wfr + (size_t)y * wfx + x] = h[f * fr + (size_t)fy * nfx + x];
                }
            BatchedPatchAlignmentWorkspace ws;
            if (!ws.reserve(2, c.n, c.pnx, c.pny, c.B, c.down, 0)) throw SetupError("batched reserve declined");
            for (int j = 0; j < 2; j++)
                ck(cudaMemcpy(ws.patchSlot(j), w.data(), w.size() * sizeof(fComplex), cudaMemcpyHostToDevice), "slot upload");
            std::vector<std::vector<RFLOAT> > bx(2, std::vector<RFLOAT>(c.n, 0)), by = bx;
            std::vector<PatchBatchLog> logs(2);
            cudaAlignPatchBatchDevice(ws, 2, c.n, c.pnx, c.pny, c.B, bx.data(), by.data(), c.max_iter, c.down, 0, logs.data());
            std::vector<fComplex> w1(w.size());
            ck(cudaMemcpy(w.data(), ws.patchSlot(0), w.size() * sizeof(fComplex), cudaMemcpyDeviceToHost), "slot download");
            ck(cudaMemcpy(w1.data(), ws.patchSlot(1), w1.size() * sizeof(fComplex), cudaMemcpyDeviceToHost), "slot download");
            if (!ws.release()) throw SetupError("batched release");
            if (bx[0] != bx[1] || by[0] != by[1] || std::memcmp(w.data(), w1.data(), w.size() * sizeof(fComplex)))
                throw SetupError("batched chunk patches disagree");
            xs = bx[0]; ys = by[0]; r.converged = logs[0].converged;
            r.out = Stack(c.n);
            for (int f = 0; f < c.n; f++) {
                r.out[f].reshape(cny, wfx);
                std::memcpy(r.out[f].data, &w[f * wfr], wfr * sizeof(fComplex));
            }
        }
#else
        throw SetupError("CUDA path requested in a CPU build");
#endif
    }
    r.xs.assign(xs.begin(), xs.end()); r.ys.assign(ys.begin(), ys.end());
    r.eligible = counter(site, stage, 0) - e0;
    r.zeroed = counter(site, stage, 1) - z0;
    r.wrong_stage = counter(site, 1 - stage, 0) != other0;
    return r;
}

// Independent long-double reference for one iteration on the uncropped CCF.
struct Ref {
    std::vector<LD> xs, ys, xs_dc, ys_dc;
    std::vector<int> px, py;
    std::vector<LD> margin, contrast, dc_offset;
};

void fit(const std::vector<LD> &m, int W, int R, int &px, int &py, LD &sx, LD &sy, LD &margin, LD &contrast) {
    LD best = -std::numeric_limits<LD>::infinity(), second = best, sum = 0;
    for (int y = -R; y <= R; y++)
        for (int x = -R; x <= R; x++) {
            const LD v = m[(size_t)(y + R) * W + (x + R)];
            sum += v;
            if (v > best) { second = best; best = v; px = x; py = y; }
            else if (v > second) second = v;
        }
    contrast = best - sum / ((LD)W * W);
    margin = best - second;
    auto at = [&](int x, int y) { return m[(size_t)(y + R) * W + (x + R)]; };
    // Same scalar expression and 1e-15 guard as production; neighbours of an
    // edge maximum are outside the scanned window and then use the guard.
    auto vertex = [](int p, LD vp, LD vn, LD mx) {
        const LD d = vp + vn - 2 * mx;
        return std::fabs(d) > 1e-15L ? p - 0.5L * (vp - vn) / d : (LD)p;
    };
    const bool ex = px > -R && px < R, ey = py > -R && py < R;
    sx = ex ? vertex(px, at(px + 1, py), at(px - 1, py), best) : px;
    sy = ey ? vertex(py, at(px, py + 1), at(px, py - 1), best) : py;
}

Ref reference(const Case &c, const Stack &F) {
    const int nfx = c.pnx / 2 + 1, nfy = c.pny, nx = c.pnx, ny = c.pny, n = c.n;
    const int R = std::min(50, std::min(nx / 2 - 1, ny / 2 - 1)), W = 2 * R + 1;
    Ref out;
    std::vector<std::complex<LD> > Rf((size_t)nfy * nfx);
    for (int f = 0; f < n; f++)
        for (size_t i = 0; i < Rf.size(); i++) {
            const fComplex v = F[f].data[i];
            Rf[i] += std::complex<LD>(v.real, v.imag);
        }
    std::vector<std::complex<LD> > ex(nx), ey(ny);
    for (int k = 0; k < nx; k++) ex[k] = std::polar(1.0L, 2 * acosl(-1.0L) * k / nx);
    for (int k = 0; k < ny; k++) ey[k] = std::polar(1.0L, 2 * acosl(-1.0L) * k / ny);
    for (int f = 0; f < n; f++) {
        std::vector<std::complex<LD> > C((size_t)nfy * nfx);
        for (int y = 0; y < nfy; y++)
            for (int x = 0; x < nfx; x++) {
                const int ly = y > nfy / 2 ? y - nfy : y;
                const LD dist2 = (LD)ly * ly / ((LD)nfy * nfy) + (LD)x * x / ((LD)nfx * nfx);
                const LD w = expl(-2 * dist2 * c.B);
                const size_t i = (size_t)y * nfx + x;
                const std::complex<LD> fr(F[f].data[i].real, F[f].data[i].imag);
                C[i] = (Rf[i] - fr) * std::conj(fr) * w;
            }
        // Separable direct inverse, Hermitian weight 1 on self-conjugate columns.
        std::vector<LD> m((size_t)W * W), mdc((size_t)W * W);
        for (int py = -R; py <= R; py++) {
            std::vector<std::complex<LD> > G(nfx);
            for (int x = 0; x < nfx; x++)
                for (int y = 0; y < nfy; y++) {
                    if (x == 0 && y == 0) continue;
                    G[x] += C[(size_t)y * nfx + x] * ey[(((long)y * py) % ny + ny) % ny];
                }
            for (int px = -R; px <= R; px++) {
                LD v = 0;
                for (int x = 0; x < nfx; x++) {
                    const LD cw = (x == 0 || x == nx / 2) ? 1 : 2;
                    v += cw * (G[x] * ex[(((long)x * px) % nx + nx) % nx]).real();
                }
                m[(size_t)(py + R) * W + (px + R)] = v;
                mdc[(size_t)(py + R) * W + (px + R)] = v + C[0].real();
            }
        }
        int px = 0, py = 0, qx = 0, qy = 0;
        LD sx, sy, mg, ct, tx, ty, mg2, ct2;
        fit(m, W, R, px, py, sx, sy, mg, ct);
        fit(mdc, W, R, qx, qy, tx, ty, mg2, ct2);
        out.xs.push_back(sx); out.ys.push_back(sy); out.xs_dc.push_back(tx); out.ys_dc.push_back(ty);
        out.px.push_back(px); out.py.push_back(py); out.margin.push_back(mg); out.contrast.push_back(ct);
        out.dc_offset.push_back(C[0].real());
    }
    for (int f = n - 1; f >= 0; f--) { out.xs[f] -= out.xs[0]; out.ys[f] -= out.ys[0]; out.xs_dc[f] -= out.xs_dc[0]; out.ys_dc[f] -= out.ys_dc[0]; }
    return out;
}

bool sameBytes(const Result &a, const Result &b) {
    if (a.converged != b.converged || a.xs.size() != b.xs.size()) return false;
    if (std::memcmp(a.xs.data(), b.xs.data(), a.xs.size() * sizeof(double)) ||
        std::memcmp(a.ys.data(), b.ys.data(), a.ys.size() * sizeof(double))) return false;
    // Output spectra must match except each frame's (0,0) bin, which carries the
    // injected pedestal by construction and is checked separately by G4.
    for (size_t f = 0; f < a.out.size(); f++)
        if (a.out[f].nzyxdim != b.out[f].nzyxdim ||
            std::memcmp(a.out[f].data + 1, b.out[f].data + 1, (a.out[f].nzyxdim - 1) * sizeof(fComplex))) return false;
    return true;
}
bool sameShifts(const Result &a, const Result &b) {
    return !std::memcmp(a.xs.data(), b.xs.data(), a.xs.size() * sizeof(double)) &&
           !std::memcmp(a.ys.data(), b.ys.data(), a.ys.size() * sizeof(double));
}

std::string num(double v) {
    if (!std::isfinite(v)) return "null";
    std::ostringstream o; o << std::setprecision(17) << v; return o.str();
}
std::string vec(const std::vector<double> &v) {
    std::string s = "[";
    for (size_t i = 0; i < v.size(); i++) s += (i ? "," : "") + num(v[i]);
    return s + "]";
}

struct Tally { int pass = 0, fail = 0, inconclusive = 0; };

} // namespace

int main(int argc, char **argv) {
    bool expect_failure = false;
    std::string json_path;
    for (int i = 1; i < argc; i++) {
        if (std::string(argv[i]) == "--expect-failure") expect_failure = true;
        else if (std::string(argv[i]) == "--json" && i + 1 < argc) json_path = argv[++i];
    }
    std::ostringstream js;
    Tally t[6];   // G1..G5, index 0 unused
    int failures = 0;
    auto gate = [&](int g, bool ok, const std::string &what) {
        (ok ? t[g].pass : t[g].fail)++;
        if (!ok) { ++failures; std::cout << "FAIL G" << g << ": " << what << "\n"; }
    };
    try {
        const std::vector<Case> cases = {
            {"tex128x96_it1", "texture", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0.05, 1, true},
            {"tex128x96_it1_B150", "texture", 128, 96, 5, 150, 1, 1, 1.3, -0.7, 0.05, 1, true},
            {"tex128x96_it1_amp001", "texture", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0.05, 0.01, true},
            {"tex128x96_it1_amp100", "texture", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0.05, 100, true},
            {"tex128x96_it5", "texture", 128, 96, 5, 20, 1, 5, 1.3, -0.7, 0.05, 1, true},
            {"tex384x320_crop_it5", "texture", 384, 320, 6, 150, 0, 5, 2.6, -1.4, 0.1, 1, true},
            {"flat", "flat", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0, 1, false},
            {"tie_half_px", "texture", 128, 96, 2, 20, 1, 1, 0.5, 0, 0, 1, false},
            {"boundary_60px", "texture", 128, 96, 2, 20, 1, 1, 60, 0, 0, 1, false},
            {"nan_dc", "nan_dc", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0.05, 1, false},
            {"nan_bin", "nan_bin", 128, 96, 5, 20, 1, 1, 1.3, -0.7, 0.05, 1, false},
        };
#ifdef _CUDA_ENABLED
        const int n_paths = N_PATHS;
#else
        const int n_paths = CUDA_SINGLE_GLOBAL;
#endif
        bool power_seen[N_PATHS] = {}, power_case[N_PATHS] = {};
        js << "{\"schema\":\"experiment-ccf-dc-stage/1\",\"rows\":[";
        bool first_row = true;
        for (const Case &c : cases) {
            std::vector<Stack> stacks;
            for (int ip = 0; ip < N_PED; ip++) {
                stacks.push_back(buildStack(c, PEDESTALS[ip], 1));
                if (!hermitianX0(stacks.back())) throw SetupError(c.name + ": input not Hermitian on x=0");
            }
            const bool refable = c.max_iter == 1 && c.down == 1 && c.kind == "texture";
            std::vector<Ref> refs;
            if (refable || c.kind == "flat")
                for (int ip = 0; ip < N_PED; ip++) refs.push_back(reference(c, stacks[ip]));
            for (int path = 0; path < n_paths; path++)
                for (int arm = 0; arm < 4; arm++) {
                    const bool sel = selected(arm, path);
                    std::vector<Result> res;
                    for (int ip = 0; ip < N_PED; ip++) res.push_back(run(c, path, arm, stacks[ip]));
                    const std::string tag = c.name + " " + PATH_NAMES[path] + " " + ARM_NAMES[arm];
                    for (int ip = 0; ip < N_PED; ip++) {
                        const Result &r = res[ip];
                        // G1: every eligible frame is zeroed iff the stage is selected.
                        gate(1, !r.wrong_stage && r.eligible > 0 && r.zeroed == (sel ? r.eligible : 0), tag + " counters");
                        if (!c.gate) continue;
                        // G4: resident DC bytes and frame 0 untouched.
                        bool g4 = true;
                        for (int f = 0; f < c.n; f++)
                            g4 = g4 && !std::memcmp(&DIRECT_A2D_ELEM(r.out[f], 0, 0), &DIRECT_A2D_ELEM(stacks[ip][f], 0, 0), sizeof(fComplex));
                        if (path != CUDA_BATCHED_LOCAL)
                            g4 = g4 && !std::memcmp(r.out[0].data, stacks[ip][0].data, r.out[0].nzyxdim * sizeof(fComplex));
                        gate(4, g4, tag + " P=" + num(PEDESTALS[ip]) + " resident spectra");
                    }
                    if (c.gate) {
                        // G2: selected stage invariant to P; unselected changes at P=4096.
                        bool inv = true;
                        for (int ip = 1; ip < N_PED; ip++) inv = inv && sameBytes(res[0], res[ip]);
                        if (sel) gate(2, inv, tag + " pedestal invariance");
                        else {
                            power_case[path] = true;
                            if (!sameShifts(res[0], res[N_PED - 1])) power_seen[path] = true;
                        }
                        // G5: power-of-two amplitude scaling is exact.
                        if (c.name == "tex128x96_it1" || c.name == "tex128x96_it5") {
                            for (double s : {1.0 / 64, 64.0}) {
                                const Result rs = run(c, path, arm, buildStack(c, PEDESTALS[2], s));
                                gate(5, sameShifts(rs, res[2]) && rs.converged == res[2].converged,
                                     tag + " scale " + num(s));
                            }
                        }
                    }
                    for (int ip = 0; ip < N_PED; ip++) {
                        const Result &r = res[ip];
                        double err = 0, dc_err = 0;
                        int int_match = -1, near_tie = 0;
                        if (!refs.empty() && refable) {
                            const Ref &R = refs[ip];
                            int_match = 1;
                            for (int f = 0; f < c.n; f++) {
                                err = std::max(err, (double)std::max(std::fabs(r.xs[f] - R.xs[f]), std::fabs(r.ys[f] - R.ys[f])));
                                dc_err = std::max(dc_err, (double)std::max(std::fabs(R.xs_dc[f] - R.xs[f]), std::fabs(R.ys_dc[f] - R.ys[f])));
                                if (R.margin[f] < 1e-4L * R.contrast[f]) near_tie = 1;
                                // Integer peaks are compared through the fit: an integer change moves
                                // the fitted shift by about a pixel, far beyond the 1e-3 px limit.
                            }
                            if (!(err <= 1e-3)) int_match = 0;
                            if (c.gate && (sel || ip == 0)) {
                                if (near_tie) t[3].inconclusive++;
                                else gate(3, err <= 1e-3, tag + " P=" + num(PEDESTALS[ip]) + " reference error " + num(err));
                            }
                        }
                        const bool finite = std::isfinite(r.xs.back()) && std::isfinite(r.ys.back());
                        js << (first_row ? "" : ",") << "\n{\"case\":\"" << c.name << "\",\"path\":\"" << PATH_NAMES[path]
                           << "\",\"arm\":\"" << ARM_NAMES[arm] << "\",\"selected\":" << (sel ? "true" : "false")
                           << ",\"pedestal\":" << num(PEDESTALS[ip]) << ",\"gate_case\":" << (c.gate ? "true" : "false")
                           << ",\"converged\":" << (r.converged ? "true" : "false") << ",\"finite\":" << (finite ? "true" : "false")
                           << ",\"xs\":" << vec(r.xs) << ",\"ys\":" << vec(r.ys)
                           << ",\"eligible\":" << r.eligible << ",\"zeroed\":" << r.zeroed;
                        if (!refs.empty()) {
                            const Ref &R = refs[ip];
                            std::vector<double> rx(R.xs.begin(), R.xs.end()), ry(R.ys.begin(), R.ys.end());
                            std::vector<double> mc;
                            for (int f = 0; f < c.n; f++) mc.push_back((double)(R.margin[f] / (R.contrast[f] != 0 ? R.contrast[f] : 1)));
                            js << ",\"ref_xs\":" << vec(rx) << ",\"ref_ys\":" << vec(ry)
                               << ",\"ref_margin_over_contrast\":" << vec(mc)
                               << ",\"ref_dc_over_contrast\":" << num((double)(R.dc_offset[1] / (R.contrast[1] != 0 ? R.contrast[1] : 1)));
                            if (refable)
                                js << ",\"max_abs_error_px\":" << num(err) << ",\"ref_dc_neutrality_px\":" << num(dc_err)
                                   << ",\"near_tie\":" << near_tie;
                        }
                        js << "}";
                        first_row = false;
                    }
                }
        }
        for (int path = 0; path < n_paths; path++) {
            if (!power_case[path]) continue;
            if (power_seen[path]) t[2].pass++;
            else { t[2].inconclusive++; std::cout << "INCONCLUSIVE G2 power: " << PATH_NAMES[path] << " never changed with P\n"; }
        }
        js << "\n],\"gates\":{";
        for (int g = 1; g <= 5; g++)
            js << (g > 1 ? "," : "") << "\"G" << g << "\":{\"pass\":" << t[g].pass << ",\"fail\":" << t[g].fail
               << ",\"inconclusive\":" << t[g].inconclusive << "}";
        js << "},\"failures\":" << failures << "}\n";
    } catch (const SetupError &e) {
        std::cout << "SETUP ERROR: " << e.what() << "\n";
        return 2;
    } catch (const std::exception &e) {
        std::cout << "SETUP ERROR (exception): " << e.what() << "\n";
        return 2;
    }
    if (!json_path.empty()) {
        std::ofstream o(json_path);
        o << js.str();
        if (!o.good()) { std::cout << "SETUP ERROR: cannot write " << json_path << "\n"; return 2; }
    }
    for (int g = 1; g <= 5; g++)
        std::cout << "G" << g << " pass=" << t[g].pass << " fail=" << t[g].fail << " inconclusive=" << t[g].inconclusive << "\n";
    const bool oracle_failed = failures > 0;
    std::cout << (oracle_failed ? "ORACLE FAILED" : "ORACLE PASSED") << "\n";
    if (expect_failure) return oracle_failed ? 0 : 1;
    return oracle_failed ? 1 : 0;
}
