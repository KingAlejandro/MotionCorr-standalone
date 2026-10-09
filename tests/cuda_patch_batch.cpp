// Native controls for batched local patch alignment (docs/batched_patch_alignment.md).
//
// Exactness: the batched entry point and CudaMovieSession::alignPatchesBatched must
// reproduce the per-patch path byte for byte -- shifts, convergence verdicts,
// iteration counts, the "Iteration"/"completed" log lines and the shifted Fourier
// payload -- for several geometries, odd patch counts, chunk sizes 1..n and a mix of
// converging and non-converging patches.
//
// --expect-mismatch is for the compiled mutants (CMake rewrites one line of
// cuda_alignpatch.cu): the run passes only if the exactness checks detect a
// difference. Fault controls interpose return codes only; no device is poisoned.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
// ---- interposition -------------------------------------------------------
bool active = false;
std::set<void*> buffers;
size_t stale = 0;
int malloc_calls = 0, r2c_calls = 0, c2r_calls = 0, event_calls = 0, plan_calls = 0;
// Fault plan: fail the Nth call (1-based, counted while armed) of one boundary.
enum Boundary { NONE, MALLOC, MALLOC_ALL, EVENT, PLAN_CREATE, PLAN_MAKE, EXEC_R2C, EXEC_C2R };
Boundary fault = NONE;
int fault_at = 0;
bool fault_fatal = false, fired = false;
void arm(Boundary b = NONE, int at = 0, bool fatal = false) {
    malloc_calls = r2c_calls = c2r_calls = event_calls = plan_calls = 0;
    fault = b; fault_at = at; fault_fatal = fatal; fired = false; stale = 0; active = true;
}
cudaError_t code() { return fault_fatal ? cudaErrorIllegalAddress : cudaErrorMemoryAllocation; }
void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}
}

extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cudaError_t __real_cudaEventCreate(cudaEvent_t*);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int*, int*, int, int,
                                    int*, int, int, cufftType, int, size_t*);
cufftResult __real_cufftExecR2C(cufftHandle, cufftReal*, cufftComplex*);
cufftResult __real_cufftExecC2R(cufftHandle, cufftComplex*, cufftReal*);
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active) {
        ++malloc_calls;
        if (fault == MALLOC_ALL || (fault == MALLOC && malloc_calls == fault_at)) {
            fired = true; *ptr = nullptr; return code();
        }
    }
    const cudaError_t result = __real_cudaMalloc(ptr, bytes);
    if (active && result == cudaSuccess) buffers.insert(*ptr);
    return result;
}
cudaError_t __wrap_cudaFree(void *ptr) {
    const cudaError_t result = __real_cudaFree(ptr);
    if (active && ptr && result == cudaSuccess && !buffers.erase(ptr)) ++stale;
    return result;
}
cudaError_t __wrap_cudaEventCreate(cudaEvent_t *event) {
    if (active && ++event_calls == fault_at && fault == EVENT) {
        fired = true; *event = nullptr; return code();
    }
    return __real_cudaEventCreate(event);
}
cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (active && fault == PLAN_CREATE && ++plan_calls == fault_at) {
        fired = true; return CUFFT_ALLOC_FAILED;
    }
    return __real_cufftCreate(plan);
}
cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
    int *inembed, int istride, int idist, int *onembed, int ostride, int odist,
    cufftType type, int batch, size_t *work) {
    if (active && fault == PLAN_MAKE && ++plan_calls == fault_at) {
        fired = true; return CUFFT_ALLOC_FAILED;
    }
    return __real_cufftMakePlanMany(plan, rank, n, inembed, istride, idist,
                                  onembed, ostride, odist, type, batch, work);
}
cufftResult __wrap_cufftExecR2C(cufftHandle plan, cufftReal *in, cufftComplex *out) {
    if (active && ++r2c_calls == fault_at && fault == EXEC_R2C) {
        fired = true; return CUFFT_EXEC_FAILED;
    }
    return __real_cufftExecR2C(plan, in, out);
}
cufftResult __wrap_cufftExecC2R(cufftHandle plan, cufftComplex *in, cufftReal *out) {
    if (active && ++c2r_calls == fault_at && fault == EXEC_C2R) {
        fired = true; return CUFFT_EXEC_FAILED;
    }
    return __real_cufftExecC2R(plan, in, out);
}
}

namespace {
bool expect_mismatch = false;
int mismatches = 0;
// Coverage the exactness checks need to be able to fail: patches that converge,
// patches that do not, and a chunk in which one patch retires while another is
// still active (only then can a retired patch be wrongly shifted or re-aligned).
int seen_converged = 0, seen_unconverged = 0, seen_mixed_chunks = 0;

void exactOrCount(bool same, const std::string &what) {
    if (same) return;
    if (expect_mismatch) { ++mismatches; return; }
    throw std::runtime_error("batched result differs from per-patch path: " + what);
}

// Lines the runner contract fixes: per-iteration RMSD and the completion verdict.
std::vector<std::string> contractLines(const std::string &log) {
    std::vector<std::string> lines;
    std::istringstream in(log);
    for (std::string line; std::getline(in, line);)
        if (line.rfind(" Iteration ", 0) == 0 || line.rfind(" [CUDA Patch Alignment] completed", 0) == 0)
            lines.push_back(line);
    return lines;
}

int countIterations(const std::string &log) {
    int n = 0;
    for (const auto &line : contractLines(log)) n += line.rfind(" Iteration ", 0) == 0;
    return n;
}

struct PatchResult {
    bool converged = false;
    std::vector<RFLOAT> x, y;
    std::vector<cufftComplex> fourier;
    int iterations = 0;
};

void compare(const std::vector<PatchResult> &ref, const std::vector<PatchResult> &bat,
             const std::string &ref_log, const std::string &bat_log, const std::string &label) {
    require(ref.size() == bat.size(), label + ": patch count");
    for (size_t p = 0; p < ref.size(); p++) {
        const std::string at = label + " patch " + std::to_string(p);
        exactOrCount(ref[p].converged == bat[p].converged, at + " convergence");
        exactOrCount(ref[p].iterations == bat[p].iterations, at + " iteration count");
        exactOrCount(ref[p].x.size() == bat[p].x.size() &&
                     std::memcmp(ref[p].x.data(), bat[p].x.data(), ref[p].x.size() * sizeof(RFLOAT)) == 0 &&
                     std::memcmp(ref[p].y.data(), bat[p].y.data(), ref[p].y.size() * sizeof(RFLOAT)) == 0,
                     at + " shifts");
        exactOrCount(ref[p].fourier.size() == bat[p].fourier.size() &&
                     std::memcmp(ref[p].fourier.data(), bat[p].fourier.data(),
                                 ref[p].fourier.size() * sizeof(cufftComplex)) == 0,
                     at + " shifted Fourier payload");
        (ref[p].converged ? seen_converged : seen_unconverged)++;
    }
    exactOrCount(contractLines(ref_log) == contractLines(bat_log), label + " contract log lines");
}

// Patch stacks in Fourier space. A structured patch is a random image under a
// linear drift (shifted copies), which the aligner recovers and converges on;
// a noise patch has independent frames and does not converge.
std::vector<cufftComplex> makeStack(int pnx, int pny, int n, int kind, unsigned seed) {
    const int nfx = pnx / 2 + 1;
    std::vector<cufftComplex> out((size_t)n * pny * nfx), base((size_t)pny * nfx);
    unsigned s = seed * 2654435761u + 12345u;
    auto rnd = [&]() { s = 1664525u * s + 1013904223u; return ((int)(s & 65535u) - 32768) / 4096.0f; };
    for (auto &v : base) { v.x = rnd(); v.y = rnd(); }
    const double dx = 0.15 * (kind % 4 + 1), dy = -0.1 * (kind % 3 + 1);
    for (int f = 0; f < n; f++)
        for (int y = 0; y < pny; y++)
            for (int x = 0; x < nfx; x++) {
                cufftComplex &o = out[((size_t)f * pny + y) * nfx + x];
                if (kind == 0) { o.x = rnd(); o.y = rnd(); continue; }
                const int ly = y > pny / 2 ? y - pny : y;
                const double ph = -2 * M_PI * (x * dx * f / pnx + ly * dy * f / pny);
                const cufftComplex b = base[(size_t)y * nfx + x];
                o.x = (float)(b.x * cos(ph) - b.y * sin(ph));
                o.y = (float)(b.x * sin(ph) + b.y * cos(ph));
            }
    return out;
}

struct Case { int pnx, pny, n, patches, max_iter; RFLOAT B, down; std::vector<int> caps; };

void directExactness() {
    const Case cases[] = {
        {64, 64, 4, 7, 4, 2, 1, {1, 2, 3, 7}},
        {80, 72, 3, 5, 5, 5, .6, {1, 4, 64}},
        {96, 64, 5, 3, 1, 5, 0, {1, 3}},          // max_iter 1: every verdict at iteration 1
        {320, 256, 6, 9, 5, 150, 0, {2, 9}},
        {766, 742, 24, 3, 5, 150, 0, {1, 3}},     // tutorial patch geometry
    };
    int compared = 0;
    for (const Case &c : cases) {
        std::vector<std::vector<cufftComplex>> inputs;
        for (int p = 0; p < c.patches; p++)
            inputs.push_back(makeStack(c.pnx, c.pny, c.n, p % 3 == 1 ? 0 : p + 1, 7 * p + c.pnx));
        const size_t elems = inputs[0].size();

        // Reference: the per-patch movie workspace, patches in order, one log stream.
        std::vector<PatchResult> ref(c.patches);
        std::ostringstream ref_log;
        {
            PatchAlignmentWorkspace workspace;
            cufftComplex *d = nullptr;
            require(cudaMalloc(&d, elems * sizeof(cufftComplex)) == cudaSuccess, "ref buffer");
            for (int p = 0; p < c.patches; p++) {
                std::ostringstream one;
                one.copyfmt(ref_log);
                require(cudaMemcpy(d, inputs[p].data(), elems * sizeof(cufftComplex), cudaMemcpyHostToDevice) == cudaSuccess, "ref upload");
                ref[p].x.assign(c.n, 0); ref[p].y.assign(c.n, 0);
                ref[p].converged = cudaAlignPatchDeviceWithWorkspace(workspace, d, c.n, c.pnx, c.pny, c.B,
                    ref[p].x, ref[p].y, c.max_iter, c.down, 0, one);
                ref_log.copyfmt(one);
                ref_log << one.str();
                ref[p].iterations = countIterations(one.str());
                ref[p].fourier.resize(elems);
                require(cudaMemcpy(ref[p].fourier.data(), d, elems * sizeof(cufftComplex), cudaMemcpyDeviceToHost) == cudaSuccess, "ref download");
            }
            cudaFree(d);
            require(workspace.release(), "ref release");
        }
        for (int cap : c.caps) {
            BatchedPatchAlignmentWorkspace workspace;
            require(workspace.reserve(cap, c.n, c.pnx, c.pny, c.B, c.down, 0), "reserve declined");
            std::vector<PatchResult> bat(c.patches);
            std::ostringstream bat_log;
            for (int first = 0; first < c.patches; first += cap) {
                const int count = std::min(cap, c.patches - first);
                for (int j = 0; j < count; j++)
                    require(cudaMemcpy(workspace.patchSlot(j), inputs[first + j].data(), elems * sizeof(cufftComplex), cudaMemcpyHostToDevice) == cudaSuccess, "slot upload");
                std::vector<std::vector<RFLOAT>> xs(count, std::vector<RFLOAT>(c.n, 0)), ys = xs;
                std::vector<PatchBatchLog> logs(count);
                cudaAlignPatchBatchDevice(workspace, count, c.n, c.pnx, c.pny, c.B, xs.data(), ys.data(),
                                          c.max_iter, c.down, 0, logs.data());
                std::set<int> iteration_counts; // from the reference, so a mutant cannot erase it
                for (int j = 0; j < count; j++) {
                    PatchResult &r = bat[first + j];
                    r.converged = logs[j].converged;
                    r.x = xs[j]; r.y = ys[j];
                    r.iterations = (int)logs[j].rmsd.size();
                    iteration_counts.insert(ref[first + j].iterations);
                    r.fourier.resize(elems);
                    require(cudaMemcpy(r.fourier.data(), workspace.patchSlot(j), elems * sizeof(cufftComplex), cudaMemcpyDeviceToHost) == cudaSuccess, "slot download");
                    writePatchBatchLog(bat_log, logs[j]);
                }
                seen_mixed_chunks += iteration_counts.size() > 1;
            }
            require(workspace.release(), "batched release");
            compare(ref, bat, ref_log.str(), bat_log.str(),
                    std::to_string(c.pnx) + "x" + std::to_string(c.pny) + " n=" + std::to_string(c.n) +
                    " patches=" + std::to_string(c.patches) + " cap=" + std::to_string(cap));
            ++compared;
        }
    }
    std::cout << (expect_mismatch ? "RAN: " : "PASS: ") << compared << " direct batched/per-patch comparisons\n";
}

// ---- session level ---------------------------------------------------------
const int SNX = 360, SNY = 300, SFRAMES = 8;

std::vector<Image<float>> movieFrames() {
    std::vector<float> base((size_t)SNX * SNY);
    unsigned s = 99u;
    for (auto &v : base) { s = 1664525u * s + 1013904223u; v = (float)((s >> 8) & 1023) / 64.0f; }
    std::vector<Image<float>> frames(SFRAMES);
    for (int k = 0; k < SFRAMES; k++) {
        frames[k]().initZeros(SNY, SNX);
        for (int y = 0; y < SNY; y++)
            for (int x = 0; x < SNX; x++) {
                // Periodic integer drift of one shared image, plus a band of strong
                // independent noise on the right that defeats alignment there.
                const int sx = ((x - k) % SNX + SNX) % SNX, sy = ((y + k / 2) % SNY + SNY) % SNY;
                float v = base[(size_t)sy * SNX + sx];
                if (x >= 2 * SNX / 3) { s = 1664525u * s + 1013904223u; v = (float)((s >> 8) & 65535) / 16.0f; }
                DIRECT_A2D_ELEM(frames[k](), y, x) = v;
            }
    }
    return frames;
}

struct Movie {
    std::ostringstream log;
    CudaMovieSession session;
    Movie(const std::vector<Image<float>> &frames) : session(SNX, SNY, SFRAMES, 0, log) {
        MultidimArray<float> sum;
        require(session.initialize(), "session initialize");
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), "session upload");
        require(session.releasePreprocessingBuffers(), "release preprocessing");
    }
};

const int GROUPS = 4;
const int group_start[GROUPS] = {0, 2, 4, 6}, group_size[GROUPS] = {2, 2, 2, 2};
const RFLOAT SB = 150, SDOWN = 0;
const int SITER = 5;

std::vector<CudaMovieSession::PatchBox> boxes(int px, int py) {
    std::vector<CudaMovieSession::PatchBox> out;
    const int w = (SNX / px) & ~1, h = (SNY / py) & ~1;
    for (int iy = 0; iy < py; iy++)
        for (int ix = 0; ix < px; ix++) out.push_back({ix * (SNX / px), iy * (SNY / py), w, h});
    return out;
}

void sessionReference(Movie &m, const std::vector<CudaMovieSession::PatchBox> &bx,
                      std::vector<PatchResult> &ref, std::string &log) {
    std::ostringstream all;
    const size_t elems = (size_t)GROUPS * bx[0].height * (bx[0].width / 2 + 1);
    cufftComplex *d = nullptr;
    require(cudaMalloc(&d, elems * sizeof(cufftComplex)) == cudaSuccess, "session ref buffer");
    ref.assign(bx.size(), PatchResult());
    for (size_t p = 0; p < bx.size(); p++) {
        require(m.session.preparePatchInVram(bx[p].x_start, bx[p].y_start, bx[p].width, bx[p].height,
                                             GROUPS, group_start, group_size, d), "session ref prep");
        std::ostringstream one;
        one.copyfmt(all);
        ref[p].x.assign(GROUPS, 0); ref[p].y.assign(GROUPS, 0);
        ref[p].converged = cudaAlignPatchDeviceWithWorkspace(m.session.getPatchAlignmentWorkspace(), d, GROUPS,
            bx[p].width, bx[p].height, SB, ref[p].x, ref[p].y, SITER, SDOWN, 0, one);
        all.copyfmt(one);
        all << one.str();
        ref[p].iterations = countIterations(one.str());
    }
    cudaFree(d);
    require(m.session.releasePatchAlignmentWorkspace(), "session ref release");
    log = all.str();
}

void sessionExactness() {
    const auto frames = movieFrames();
    int compared = 0;
    for (auto grid : {std::make_pair(3, 3), std::make_pair(5, 3)}) {
        const auto bx = boxes(grid.first, grid.second);
        std::vector<PatchResult> ref;
        std::string ref_log;
        { Movie m(frames); sessionReference(m, bx, ref, ref_log); }
        for (int cap : {1, 2, 4, 64}) {
            Movie m(frames);
            std::vector<CudaMovieSession::PatchBatchOutcome> out;
            m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, cap, out);
            std::vector<PatchResult> bat(bx.size());
            std::ostringstream log;
            for (size_t p = 0; p < bx.size(); p++) {
                require(out[p].done, "session patch not aligned by the batched path");
                bat[p].converged = out[p].log.converged;
                bat[p].x = out[p].xshifts; bat[p].y = out[p].yshifts;
                bat[p].iterations = (int)out[p].log.rmsd.size();
                writePatchBatchLog(log, out[p].log);
                // The payload is per-chunk scratch; shifts/log carry the comparison here.
                bat[p].fourier = ref[p].fourier;
            }
            require(m.log.str().find("chunk size " + std::to_string(std::min<size_t>(cap, bx.size()))) != std::string::npos,
                    "chunk size not logged: " + m.log.str());
            compare(ref, bat, ref_log, log.str(),
                    "session " + std::to_string(grid.first) + "x" + std::to_string(grid.second) + " cap=" + std::to_string(cap));
            require(m.session.releasePatchAlignmentWorkspace(), "session batched release");
            ++compared;
        }
    }
    std::cout << (expect_mismatch ? "RAN: " : "PASS: ") << compared << " session-level batched/per-patch comparisons (prep into slots included)\n";
}

// ---- chunk arithmetic --------------------------------------------------------
void chunkArithmetic() {
    const size_t GiB = (size_t)1 << 30, MiB = (size_t)1 << 20;
    require(choosePatchBatchChunk(25, 62 * MiB, 70 * GiB, 80 * GiB, 64) == 25, "plenty");
    require(choosePatchBatchChunk(25, 62 * MiB, 70 * GiB, 80 * GiB, 4) == 4, "cap");
    // 80 GiB total: headroom 8 GiB; 8.5 GiB free leaves 512 MiB = 8 patches of 62 MiB.
    require(choosePatchBatchChunk(25, 62 * MiB, 8 * GiB + 512 * MiB, 80 * GiB, 64) == 8, "headroom 10%");
    // 4 GiB total: headroom 1 GiB.
    require(choosePatchBatchChunk(25, 100 * MiB, GiB + 250 * MiB, 4 * GiB, 64) == 2, "headroom 1 GiB");
    require(choosePatchBatchChunk(25, 100 * MiB, GiB, 4 * GiB, 64) == 0, "nothing fits");
    require(choosePatchBatchChunk(25, 100 * MiB, 70 * GiB, 80 * GiB, 0) == 0, "disabled");
    require(choosePatchBatchChunk(3, 1, 70 * GiB, 80 * GiB, 64) == 3, "patch count");
    std::cout << "PASS: chunk-size arithmetic\n";
}

// ---- faults --------------------------------------------------------------------
void requireNothingOwned(const std::string &what) {
    require(buffers.empty() && stale == 0, what + ": batched resources leaked or double-freed");
}

void reserveFaults() {
    int trials = 0;
    const struct { Boundary b; int limit; } plans[] = {{MALLOC, 7}, {EVENT, 2}, {PLAN_CREATE, 1}, {PLAN_MAKE, 1}};
    for (const auto &plan : plans) {
        for (int at = 1; at <= plan.limit; at++) {
            CudaFailureState failure;
            BatchedPatchAlignmentWorkspace workspace(&failure);
            arm(plan.b, at);
            const bool ok = workspace.reserve(3, 4, 64, 64, 2, 1, 0);
            require(!ok && fired && !workspace.isValid() && workspace.capacity() == 0,
                    "declined reservation reported success or kept a capacity");
            require(!failure.hasFailed(), "a declined reservation recorded a failure");
            require(cudaGetLastError() == cudaSuccess, "declined reservation left the error slot set");
            requireNothingOwned("declined reservation");
            arm();
            require(workspace.reserve(3, 4, 64, 64, 2, 1, 0) && workspace.isValid(), "reserve after decline");
            require(workspace.release(), "release after recovery");
            requireNothingOwned("recovered reservation");
            active = false;
            ++trials;
        }
    }
    // Fatal allocation code: thrown, latched, released, and never retried.
    {
        CudaFailureState failure;
        BatchedPatchAlignmentWorkspace workspace(&failure);
        arm(MALLOC, 2, true);
        bool threw = false;
        try { (void)workspace.reserve(3, 4, 64, 64, 2, 1, 0); } catch (RelionError &) { threw = true; }
        require(threw && failure.isPoisoned() && !workspace.isValid(), "fatal reserve not thrown/latched");
        requireNothingOwned("fatal reservation");
        arm();
        bool refused = false;
        try { (void)workspace.reserve(3, 4, 64, 64, 2, 1, 0); } catch (RelionError &) { refused = true; }
        require(refused && malloc_calls == 0, "poisoned workspace allocated again");
        active = false;
        ++trials;
    }
    std::cout << "PASS: " << trials << " reservation fault controls (declines keep nothing and record nothing; fatal is not retried)\n";
}

void sessionFaults() {
    const auto frames = movieFrames();
    const auto bx = boxes(3, 3);
    std::vector<PatchResult> ref;
    std::string ref_log;
    { Movie m(frames); sessionReference(m, bx, ref, ref_log); }

    // 1. No reservation fits: everything is left to the per-patch path.
    {
        Movie m(frames);
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        arm(MALLOC_ALL);
        m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, 64, out);
        active = false;
        bool any = false;
        for (const auto &o : out) any = any || o.done;
        require(fired && !any && !m.session.getFailureState().hasFailed() &&
                cudaGetLastError() == cudaSuccess &&
                m.log.str().find("workspace does not fit") != std::string::npos,
                "declined workspace did not fall back cleanly: " + m.log.str());
        require(!m.session.getBatchedPatchAlignmentWorkspace().isValid(), "declined workspace kept");
    }
    // 2. The first reservation is declined, a smaller one fits: still exact.
    {
        Movie m(frames);
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        arm(MALLOC, 1);
        m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, 9, out);
        active = false;
        require(fired && m.log.str().find("chunk size 4") != std::string::npos, "halving retry not taken: " + m.log.str());
        for (size_t p = 0; p < bx.size(); p++)
            require(out[p].done && std::memcmp(out[p].xshifts.data(), ref[p].x.data(), GROUPS * sizeof(RFLOAT)) == 0 &&
                    out[p].log.converged == ref[p].converged, "halved chunk differs");
        require(m.session.releasePatchAlignmentWorkspace(), "halved release");
    }
    // 3. Recoverable preparation failure in the second chunk: the first chunk is
    //    kept, the rest is left to the per-patch path, the workspace is released.
    {
        Movie m(frames);
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        arm(EXEC_R2C, 5);
        m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, 4, out);
        active = false;
        for (size_t p = 0; p < bx.size(); p++) require(out[p].done == (p < 4), "chunk ownership after recoverable prep failure");
        for (size_t p = 0; p < 4; p++)
            require(std::memcmp(out[p].xshifts.data(), ref[p].x.data(), GROUPS * sizeof(RFLOAT)) == 0, "kept chunk differs");
        require(fired && !m.session.getFailureState().isPoisoned() &&
                !m.session.getBatchedPatchAlignmentWorkspace().isValid() &&
                m.log.str().find("patches 5 to 9 use per-patch alignment") != std::string::npos,
                "recoverable prep failure not handed back: " + m.log.str());
    }
    // 4. An alignment execution error throws and releases the workspace.
    {
        Movie m(frames);
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        arm(EXEC_C2R, 3);
        bool threw = false;
        try {
            m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, 64, out);
        } catch (RelionError &) { threw = true; }
        active = false;
        require(fired && threw && !m.session.getBatchedPatchAlignmentWorkspace().isValid() &&
                m.session.getFailureState().firstCufftError() == CUFFT_EXEC_FAILED,
                "execution error did not throw/release/record");
    }
    // 5. Fatal preparation failure: thrown, no batched alignment is attempted. Last,
    //    because a poisoned session retires this device's worker plan pool.
    {
        Movie m(frames);
        std::vector<CudaMovieSession::PatchBatchOutcome> out;
        // The first cudaMalloc after reservation is preparePatchInVram's scratch.
        arm(MALLOC, 8, true);
        bool threw = false;
        std::string what;
        try {
            m.session.alignPatchesBatched(bx, GROUPS, group_start, group_size, SB, SITER, SDOWN, 64, out);
        } catch (RelionError &e) { threw = true; what = e.msg; }
        active = false;
        require(fired && threw && m.session.getFailureState().isPoisoned() && c2r_calls == 0 &&
                what.find("Refusing to retry") != std::string::npos,
                "fatal prep failure was retried or not thrown: " + what);
    }
    std::cout << "PASS: 5 session fault controls (declined, halved, recoverable prep, fatal prep, exec error)\n";
}
}

int main(int argc, char **argv) {
    expect_mismatch = argc > 1 && std::string(argv[1]) == "--expect-mismatch";
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n"; return 1;
    }
    try {
        directExactness();
        sessionExactness();
        require(seen_converged > 0 && seen_unconverged > 0 && seen_mixed_chunks > 0,
                "fixtures did not exercise converged, unconverged and mixed chunks: " +
                std::to_string(seen_converged) + "/" + std::to_string(seen_unconverged) + "/" +
                std::to_string(seen_mixed_chunks));
        if (expect_mismatch) {
            std::cout << (mismatches ? "PASS" : "FAIL") << ": mutant produced " << mismatches << " detected mismatches\n";
            return mismatches ? 0 : 1;
        }
        chunkArithmetic();
        reserveFaults();
        sessionFaults();
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n'; return 1;
    } catch (RelionError &e) {
        std::cerr << "Unexpected production exception: " << e << '\n'; return 1;
    }
    std::cout << "PASS: batched patch alignment matrix (" << seen_converged << " converged, "
              << seen_unconverged << " unconverged patch comparisons, " << seen_mixed_chunks << " mixed chunks)\n";
    return 0;
}
