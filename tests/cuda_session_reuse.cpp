// SPDX-License-Identifier: GPL-2.0-or-later
// Native controls for CudaMovieSession reuse across movies
// (docs/cuda_session_reuse.md).
//
// The oracle is a whole movie's device outputs (unaligned sum, defect
// neighbour samples, patch spectra, frame spectra) from a reused session,
// compared bit for bit with the same movie on a fresh session. The allocation
// ledger checks that a parked session holds exactly the core and that a reset
// allocates only the unaligned sum. Faults are injected through linker
// --wrap, so the physical device is never poisoned.
//
// --expect-mismatch is for the compiled mutants: CMake rewrites one line of
// cuda_movie_session.cu, and the mutant must make the selected case fail.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {

bool active = false;
std::map<void *, size_t> buffers;
size_t malloc_calls = 0;
size_t plan_creates = 0;
size_t stale_frees = 0;
// A cudaMalloc of exactly this size fails once with a recoverable code.
size_t fail_malloc_bytes = 0;

void require(bool ok, const char *message) {
    if (!ok) {
        std::cerr << "Assertion failed: " << message << std::endl;
        throw std::runtime_error(message);
    }
}

} // namespace

extern "C" {
cudaError_t __real_cudaMalloc(void **, size_t);
cudaError_t __real_cudaFree(void *);
cufftResult __real_cufftCreate(cufftHandle *);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active && fail_malloc_bytes != 0 && bytes == fail_malloc_bytes) {
        fail_malloc_bytes = 0;
        *ptr = nullptr;
        return cudaErrorMemoryAllocation;
    }
    const cudaError_t status = __real_cudaMalloc(ptr, bytes);
    if (active && status == cudaSuccess) {
        buffers[*ptr] = bytes;
        ++malloc_calls;
    }
    return status;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const cudaError_t status = __real_cudaFree(ptr);
    if (active && ptr != nullptr && status == cudaSuccess && buffers.erase(ptr) == 0)
        ++stale_frees;
    return status;
}

cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (active) ++plan_creates;
    return __real_cufftCreate(plan);
}
} // extern "C"

namespace {

const int NX = 64, NY = 64, NF = 4;
const int PATCH = 32, NGROUPS = 2;
const int group_start[NGROUPS] = {0, 2};
const int group_size[NGROUPS] = {2, 2};

struct MovieOutput {
    MultidimArray<float> sum;
    std::vector<float> samples;
    std::vector<cufftComplex> patches;
    std::vector<MultidimArray<fComplex> > spectra;
};

MultidimArray<float> makeGain() {
    MultidimArray<float> gain(NY, NX);
    for (int i = 0; i < NY; ++i)
        for (int j = 0; j < NX; ++j)
            DIRECT_A2D_ELEM(gain, i, j) = 0.9f + 0.001f * (float)((i * NX + j) % 97);
    return gain;
}

// Movies differ in content so a reused session holding any of the previous
// movie's data produces different numbers.
std::vector<Image<float> > makeFrames(int seed) {
    std::vector<Image<float> > frames(NF);
    for (int f = 0; f < NF; ++f) {
        frames[f]().reshape(NY, NX);
        for (int i = 0; i < NY; ++i)
            for (int j = 0; j < NX; ++j)
                DIRECT_A2D_ELEM(frames[f](), i, j) =
                    (float)((seed * 131 + f * 17 + i * 7 + j * 3) % 23) + 0.25f * (float)seed;
    }
    return frames;
}

// The runner's per-movie sequence on one session: sum, defect neighbour
// gather, release of preprocessing buffers, forward FFT, patch preparation.
// Returns false at the first refused step.
bool runMovie(CudaMovieSession &session, int seed, MovieOutput &out) {
    static const MultidimArray<float> gain = makeGain();
    if (!session.applyGainDefectsAndSum(makeFrames(seed), &gain, out.sum)) return false;
    const std::vector<int> sf = {0, 3}, sy = {5, 10}, sx = {7, 20};
    if (!session.gatherFrameSamples(sf, sy, sx, out.samples)) return false;
    if (!session.releasePreprocessingBuffers()) return false;
    if (!session.computeGlobalForwardFFT()) return false;
    if (!session.downloadFourierFrames(out.spectra)) return false;
    const size_t n_patch = (size_t)NGROUPS * PATCH * (PATCH / 2 + 1);
    cufftComplex *d_out = nullptr;
    require(cudaMalloc((void **)&d_out, n_patch * sizeof(cufftComplex)) == cudaSuccess,
            "test patch output allocation failed");
    const bool ok = session.preparePatchInVram(8, 8, PATCH, PATCH, NGROUPS,
                                               group_start, group_size, d_out);
    out.patches.assign(n_patch, cufftComplex{0.0f, 0.0f});
    if (ok)
        require(cudaMemcpy(out.patches.data(), d_out, n_patch * sizeof(cufftComplex),
                           cudaMemcpyDeviceToHost) == cudaSuccess,
                "test patch output download failed");
    require(cudaFree(d_out) == cudaSuccess, "test patch output free failed");
    return ok;
}

bool sameBytes(const void *a, const void *b, size_t n) { return std::memcmp(a, b, n) == 0; }

void requireSameOutput(const MovieOutput &a, const MovieOutput &b, const char *what) {
    bool same = sameBytes(a.sum.data, b.sum.data, sizeof(float) * NX * NY) &&
                a.samples == b.samples && a.patches.size() == b.patches.size() &&
                sameBytes(a.patches.data(), b.patches.data(), a.patches.size() * sizeof(cufftComplex)) &&
                a.spectra.size() == b.spectra.size();
    for (size_t f = 0; same && f < a.spectra.size(); ++f)
        same = sameBytes(a.spectra[f].data, b.spectra[f].data,
                         sizeof(fComplex) * NY * (NX / 2 + 1));
    require(same, what);
}

MovieOutput freshMovie(int seed) {
    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    require(session.initialize(), "fresh session initialization failed");
    MovieOutput out;
    require(runMovie(session, seed, out), "fresh session movie failed");
    session.release();
    require(!session.getFailureState().hasFailed(), "fresh session release failed");
    return out;
}

std::set<void *> liveSet() {
    std::set<void *> live;
    for (std::map<void *, size_t>::const_iterator it = buffers.begin(); it != buffers.end(); ++it)
        live.insert(it->first);
    return live;
}

// Same geometry: the parked session keeps exactly the buffers initialize()
// made except the unaligned sum, the reset allocates only the sum and creates
// no plan, and the second movie matches a fresh session bit for bit.
void testSameGeometryReuse() {
    const MovieOutput reference = freshMovie(2);
    std::ostringstream log1, log2;
    CudaMovieSession session(NX, NY, NF, 0, log1);
    require(session.initialize(), "initialization failed");
    std::set<void *> core = liveSet();
    require(core.erase(session.getDeviceUnalignedSum()) == 1, "unaligned sum not in the ledger");
    float *frames = session.getDeviceRealFrames();
    cufftComplex *spectrum = session.getDeviceFourierFrames();

    MovieOutput first;
    require(runMovie(session, 1, first), "first movie failed");
    require(session.parkForReuse(), "a healthy session was not parked");
    require(liveSet() == core, "parked session holds more or less than the core");
    require(session.matchesGeometry(NX, NY, NF, 0), "geometry predicate rejected its own geometry");

    MovieOutput refused;
    require(!runMovie(session, 2, refused), "a parked session accepted movie work");

    const size_t mallocs_before = malloc_calls, plans_before = plan_creates;
    require(session.resetForMovie(log2), "reset of a parked session failed");
    require(malloc_calls - mallocs_before == 1 && buffers.count(session.getDeviceUnalignedSum()) == 1 &&
            buffers[session.getDeviceUnalignedSum()] == sizeof(float) * NX * NY,
            "reset allocated something other than the unaligned sum");
    require(plan_creates == plans_before, "reset created a cuFFT plan");
    require(session.initialize(), "initialize() of a reset session did not return true");
    require(malloc_calls - mallocs_before == 1, "initialize() of a reset session reallocated");
    require(session.getDeviceRealFrames() == frames && session.getDeviceFourierFrames() == spectrum,
            "reset replaced the retained frame buffers");
    require(log2.str().find("Movie FFT: batch=1") != std::string::npos,
            "reset did not log the movie FFT plan to the new movie's log");

    MovieOutput second;
    require(runMovie(session, 2, second), "movie on a reused session failed");
    requireSameOutput(second, reference, "reused session output differs from a fresh session");
    session.release();
    require(!session.getFailureState().hasFailed(), "release of the reused session failed");
    std::cout << "  PASS: same-geometry reuse" << std::endl;
}

// Different geometry, frame count or device: the predicate refuses and a
// parked session releases completely.
void testGeometryChangeRebuilds() {
    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    require(session.initialize(), "initialization failed");
    MovieOutput out;
    require(runMovie(session, 1, out), "movie failed");
    require(session.parkForReuse(), "a healthy session was not parked");
    require(!session.matchesGeometry(NX + 32, NY, NF, 0), "width change accepted");
    require(!session.matchesGeometry(NX, NY + 32, NF, 0), "height change accepted");
    require(!session.matchesGeometry(NX, NY, NF + 1, 0), "frame count change accepted");
    require(!session.matchesGeometry(NX, NY, NF, 1), "device change accepted");
    session.release();
    require(!session.getFailureState().hasFailed() && buffers.empty() && !session.isParked(),
            "release of a parked session left device buffers");

    // The rebuilt session for the new geometry is an ordinary fresh session.
    CudaMovieSession wide(NX + 32, NY, NF, 0, log);
    require(wide.initialize(), "rebuild at the new geometry failed");
    wide.release();
    std::cout << "  PASS: geometry change rebuilds" << std::endl;
}

// A recoverable failure mid-movie refuses the park; the next movie runs on a
// fresh session and matches the reference.
void testRecoverableFailureRebuilds() {
    const MovieOutput reference = freshMovie(2);
    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    require(session.initialize(), "initialization failed");
    fail_malloc_bytes = (size_t)NGROUPS * PATCH * PATCH * sizeof(float);
    MovieOutput out;
    require(!runMovie(session, 1, out), "injected patch buffer failure did not fail the movie");
    require(fail_malloc_bytes == 0, "injected failure did not fire");
    require(session.getFailureState().hasFailed() && !session.getFailureState().isPoisoned(),
            "injected failure was not recorded as recoverable");
    require(!session.parkForReuse(), "a failed session was parked");
    std::ostringstream log2;
    require(!session.resetForMovie(log2), "an unparked failed session was reset");
    session.release();
    require(buffers.empty(), "release after a recoverable failure left device buffers");

    std::ostringstream log3;
    CudaMovieSession rebuilt(NX, NY, NF, 0, log3);
    require(rebuilt.initialize(), "rebuild after a recoverable failure failed");
    MovieOutput second;
    require(runMovie(rebuilt, 2, second), "movie after rebuild failed");
    requireSameOutput(second, reference, "rebuilt session output differs from a fresh session");
    rebuilt.release();
    std::cout << "  PASS: recoverable failure rebuilds" << std::endl;
}

// A fatal failure recorded before the park refuses it.
void testFatalRefusesPark() {
    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    require(session.initialize(), "initialization failed");
    MovieOutput out;
    require(runMovie(session, 1, out), "movie failed");
    session.getFailureState().record(cudaErrorIllegalAddress, "test fatal", __LINE__);
    require(!session.parkForReuse(), "a poisoned session was parked");
    session.release();
    std::cout << "  PASS: fatal failure refuses park" << std::endl;
}

// A fatal failure recorded on a parked session refuses the reset.
void testFatalRefusesReset() {
    std::ostringstream log;
    CudaMovieSession session(NX, NY, NF, 0, log);
    require(session.initialize(), "initialization failed");
    MovieOutput out;
    require(runMovie(session, 1, out), "movie failed");
    require(session.parkForReuse(), "a healthy session was not parked");
    session.getFailureState().record(cudaErrorIllegalAddress, "test fatal", __LINE__);
    std::ostringstream log2;
    require(!session.resetForMovie(log2), "a poisoned parked session was reset for reuse");
    session.release();
    std::cout << "  PASS: fatal failure refuses reset" << std::endl;
}

// Per-movie state left by a completed movie: the Fourier guard holds the
// spectrum, which refuses the next ingest scratch claim. Without a reset the
// gather is refused (the control); after park and reset it runs.
void testStateResetBetweenMovies() {
    std::ostringstream log;
    CudaMovieSession stale(NX, NY, NF, 0, log);
    require(stale.initialize(), "initialization failed");
    MovieOutput out;
    require(runMovie(stale, 1, out), "movie failed");
    std::vector<float> samples;
    require(!stale.gatherFrameSamples({0}, {1}, {1}, samples),
            "control: a gather after the forward FFT was accepted without a reset");
    require(stale.parkForReuse(), "a healthy session was not parked");
    std::ostringstream log2;
    require(stale.resetForMovie(log2), "reset failed");
    require(stale.gatherFrameSamples({0}, {1}, {1}, samples),
            "gather refused after reset: the Fourier guard was not reset");
    stale.release();
    std::cout << "  PASS: per-movie state reset" << std::endl;
}

} // namespace

int main(int argc, char **argv) {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n";
        return 1;
    }
    bool expect_mismatch = false;
    std::string which = "all";
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--expect-mismatch") expect_mismatch = true;
        else if (arg == "--case" && i + 1 < argc) which = argv[++i];
        else { std::cerr << "invalid arguments\n"; return 2; }
    }
    if (which != "all" && which != "reuse" && which != "geometry" && which != "recoverable" &&
        which != "fatal-park" && which != "fatal-reset" && which != "state") {
        std::cerr << "unknown case selector " << which << "\n";
        return 2;
    }
    active = true;
    try {
        if (which == "all" || which == "reuse") testSameGeometryReuse();
        if (which == "all" || which == "geometry") testGeometryChangeRebuilds();
        if (which == "all" || which == "recoverable") testRecoverableFailureRebuilds();
        if (which == "all" || which == "state") testStateResetBetweenMovies();
        // A fatal release retires the worker gain pool for the process, so each
        // fatal case runs alone.
        if (which == "fatal-park") testFatalRefusesPark();
        if (which == "fatal-reset") testFatalRefusesReset();
        if (which != "fatal-park" && which != "fatal-reset")
            require(mc_cuda::getWorkerPlanPool().dropAll(), "worker gain pool cleanup failed");
        require(buffers.empty() && stale_frees == 0, "device allocation ledger did not close");
    } catch (const std::exception &e) {
        if (expect_mismatch) {
            std::cout << "PASS: mutant detected (" << e.what() << ")" << std::endl;
            return 0;
        }
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL: unexpected production exception: " << e << '\n';
        return 1;
    }
    if (expect_mismatch) {
        std::cerr << "FAIL: mutant was not detected" << std::endl;
        return 1;
    }
    std::cout << "PASS: CUDA session reuse controls (" << which << ")" << std::endl;
    return 0;
}
