// Native controls for the worker-lifetime device gain pool.
//
// The pool is the one retained resource whose contents are read by every
// kernel in the preprocessing path, so the oracle here is the produced sum,
// not the pointer identity: a wrongly reused buffer changes pixels. Error
// injection is confined to this executable by the linker --wrap flags and
// does not poison real hardware.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#include "src/motioncorr_runner.h"
#include "src/error.h"
#include <cuda_runtime.h>
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
size_t allocated_bytes = 0;
size_t freed_bytes = 0;
size_t stale_frees = 0;

// Host gain arrays being watched, and how many host-to-device copies have been
// issued out of each. Pointer identity of the device buffer is not an oracle:
// cudaMalloc readily hands back the address just freed. The upload itself is.
std::set<const void *> watched_gain_sources;
size_t gain_uploads = 0;

// Device-selection observation. cudaSetDevice is intercepted so the context
// logic can be exercised with a device id that is not physically present.
bool intercept_set_device = false;
std::vector<int> device_selections;

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
cudaError_t __real_cudaSetDevice(int);
cudaError_t __real_cudaMemcpy(void *, const void *, size_t, cudaMemcpyKind);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    const cudaError_t status = __real_cudaMalloc(ptr, bytes);
    if (active && status == cudaSuccess) {
        buffers[*ptr] = bytes;
        allocated_bytes += bytes;
    }
    return status;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    size_t bytes = 0;
    if (active && ptr != nullptr) {
        std::map<void *, size_t>::iterator it = buffers.find(ptr);
        if (it != buffers.end()) bytes = it->second;
    }
    const cudaError_t status = __real_cudaFree(ptr);
    if (active && ptr != nullptr && status == cudaSuccess) {
        if (buffers.erase(ptr) == 0) ++stale_frees;
        else freed_bytes += bytes;
    }
    return status;
}

cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t bytes, cudaMemcpyKind kind) {
    if (active && kind == cudaMemcpyHostToDevice && watched_gain_sources.count(src) != 0)
        ++gain_uploads;
    return __real_cudaMemcpy(dst, src, bytes, kind);
}

cudaError_t __wrap_cudaSetDevice(int device) {
    if (intercept_set_device) {
        device_selections.push_back(device);
        // Only device 0 physically exists here; a fabricated id is accepted so
        // the selection logic itself can be observed.
        return device == 0 ? __real_cudaSetDevice(0) : cudaSuccess;
    }
    return __real_cudaSetDevice(device);
}
} // extern "C"

namespace {

void reset() {
    (void)mc_cuda::getWorkerPlanPool().dropAll();
    buffers.clear();
    allocated_bytes = freed_bytes = stale_frees = 0;
    watched_gain_sources.clear();
    gain_uploads = 0;
    active = true;
}

MultidimArray<float> makeGain(int nx, int ny, float base) {
    MultidimArray<float> gain(ny, nx);
    for (int i = 0; i < ny; ++i)
        for (int j = 0; j < nx; ++j)
            DIRECT_A2D_ELEM(gain, i, j) = base + 0.001f * (float)(i * nx + j);
    return gain;
}

std::vector<Image<float> > makeFrames(int nx, int ny, int n_frames) {
    std::vector<Image<float> > frames(n_frames);
    for (int f = 0; f < n_frames; ++f) {
        frames[f]().reshape(ny, nx);
        for (int i = 0; i < ny; ++i)
            for (int j = 0; j < nx; ++j)
                DIRECT_A2D_ELEM(frames[f](), i, j) = (float)(f + 1) * 0.5f + 0.25f * (float)j - 0.125f * (float)i;
    }
    return frames;
}

// Ascending per-pixel accumulation in the same order as the device kernel.
MultidimArray<float> hostSum(const std::vector<Image<float> > &frames,
                             const MultidimArray<float> *gain, int nx, int ny) {
    MultidimArray<float> sum(ny, nx);
    for (int i = 0; i < ny; ++i) {
        for (int j = 0; j < nx; ++j) {
            float acc = 0.0f;
            for (size_t f = 0; f < frames.size(); ++f) {
                float value = DIRECT_A2D_ELEM(frames[f](), i, j);
                if (gain != nullptr) value *= DIRECT_A2D_ELEM(*gain, i, j);
                acc += value;
            }
            DIRECT_A2D_ELEM(sum, i, j) = acc;
        }
    }
    return sum;
}

// One movie: a fresh session with the given gain identity, producing the sum.
MultidimArray<float> runMovie(int nx, int ny, const std::vector<Image<float> > &frames,
                              const MultidimArray<float> *gain,
                              unsigned long long generation, const char *what) {
    std::ostringstream log;
    CudaMovieSession session(nx, ny, (int)frames.size(), 0, log);
    session.setGainGeneration(generation);
    require(session.initialize(), what);
    MultidimArray<float> sum;
    const bool ok = session.applyGainDefectsAndSum(frames, gain, sum, true);
    require(ok, what);
    session.release();
    return sum;
}

void requireSameBytes(const MultidimArray<float> &a, const MultidimArray<float> &b,
                      const char *message) {
    require(NZYXSIZE(a) == NZYXSIZE(b), message);
    require(std::memcmp(a.data, b.data, NZYXSIZE(a) * sizeof(float)) == 0, message);
}

// A -> B -> A on one worker thread. If the key let gain B survive under A's
// generation, or ignored the generation entirely, the third movie's pixels
// would be wrong, so the oracle is the sum and not the pointer.
void testGainSequenceABA() {
    std::cout << "Testing retained gain A -> B -> A..." << std::endl;
    const int nx = 64, ny = 48;
    reset();
    const std::vector<Image<float> > frames = makeFrames(nx, ny, 3);
    const MultidimArray<float> gain_a = makeGain(nx, ny, 1.5f);
    const MultidimArray<float> gain_b = makeGain(nx, ny, -0.75f);
    watched_gain_sources.insert(gain_a.data);
    watched_gain_sources.insert(gain_b.data);
    const MultidimArray<float> expect_a = hostSum(frames, &gain_a, nx, ny);
    const MultidimArray<float> expect_b = hostSum(frames, &gain_b, nx, ny);

    requireSameBytes(runMovie(nx, ny, frames, &gain_a, 11, "movie A1"), expect_a,
                     "retained gain A produced wrong sum on first use");
    const float *pooled_a = mc_cuda::getWorkerPlanPool().gain.ptr;
    require(pooled_a != nullptr, "gain was not retained after movie A1");
    require(mc_cuda::getWorkerPlanPool().gain.generation == 11, "retained generation wrong after A1");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == (size_t)nx * ny * sizeof(float),
            "retained byte count does not match the gain size");

    require(gain_uploads == 1, "the first movie did not upload the gain exactly once");

    // Same identity: the retained buffer must be reused rather than re-uploaded.
    requireSameBytes(runMovie(nx, ny, frames, &gain_a, 11, "movie A2"), expect_a,
                     "retained gain A produced wrong sum on reuse");
    require(gain_uploads == 1, "an identical gain identity still re-uploaded the gain");

    requireSameBytes(runMovie(nx, ny, frames, &gain_b, 12, "movie B"), expect_b,
                     "changed gain under a new generation produced wrong sum");
    require(mc_cuda::getWorkerPlanPool().gain.generation == 12, "retained generation wrong after B");
    require(gain_uploads == 2, "a changed generation did not re-upload the gain");

    requireSameBytes(runMovie(nx, ny, frames, &gain_a, 13, "movie A3"), expect_a,
                     "returning to gain A under a new generation produced wrong sum");
    require(gain_uploads == 3, "returning to gain A did not re-upload under its new generation");
    require(stale_frees == 0, "double free observed across the A -> B -> A sequence");

    // Changed geometry under the same generation must miss, not reuse.
    const int nx2 = 32, ny2 = 32;
    const std::vector<Image<float> > frames2 = makeFrames(nx2, ny2, 2);
    const MultidimArray<float> gain_small = makeGain(nx2, ny2, 2.25f);
    requireSameBytes(runMovie(nx2, ny2, frames2, &gain_small, 13, "movie geometry"),
                     hostSum(frames2, &gain_small, nx2, ny2),
                     "changed geometry under the same generation reused the retained gain");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == (size_t)nx2 * ny2 * sizeof(float),
            "retained byte count did not follow the new geometry");
    require(stale_frees == 0, "double free observed on the geometry change");

    (void)mc_cuda::getWorkerPlanPool().dropAll();
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == 0, "pool still reports retained bytes after dropAll");
    require(buffers.empty(), "device buffers outlived the sessions and the pool");
    active = false;
    std::cout << "  PASS: A -> B -> A, reuse, geometry change" << std::endl;
}

// gain -> no gain -> gain. The middle movie must not leak a session-owned copy
// and must not leave the retained buffer aliased by a dead session.
void testGainThenNoGainThenGain() {
    std::cout << "Testing gain -> no gain -> gain..." << std::endl;
    const int nx = 48, ny = 32;
    reset();
    const std::vector<Image<float> > frames = makeFrames(nx, ny, 2);
    const MultidimArray<float> gain = makeGain(nx, ny, 0.875f);
    watched_gain_sources.insert(gain.data);

    requireSameBytes(runMovie(nx, ny, frames, &gain, 21, "gain movie"),
                     hostSum(frames, &gain, nx, ny), "gain movie produced wrong sum");
    const float *pooled = mc_cuda::getWorkerPlanPool().gain.ptr;
    require(pooled != nullptr, "gain was not retained");

    requireSameBytes(runMovie(nx, ny, frames, nullptr, 0, "no-gain movie"),
                     hostSum(frames, nullptr, nx, ny), "no-gain movie applied a gain");
    require(mc_cuda::getWorkerPlanPool().gain.ptr == pooled,
            "a no-gain movie retired another movie's retained gain");

    requireSameBytes(runMovie(nx, ny, frames, &gain, 21, "gain movie again"),
                     hostSum(frames, &gain, nx, ny), "gain movie after a no-gain movie produced wrong sum");
    require(gain_uploads == 1, "a no-gain movie invalidated the retained gain");
    require(stale_frees == 0, "double free observed across gain -> no gain -> gain");

    // generation 0 with a gain keeps the original upload-every-movie behaviour
    // and must own its copy rather than touch the pool.
    const float *before = mc_cuda::getWorkerPlanPool().gain.ptr;
    requireSameBytes(runMovie(nx, ny, frames, &gain, 0, "unidentified gain movie"),
                     hostSum(frames, &gain, nx, ny), "generation 0 gain produced wrong sum");
    require(mc_cuda::getWorkerPlanPool().gain.ptr == before,
            "generation 0 modified the retained gain pool");
    require(gain_uploads == 2, "generation 0 did not upload its own copy");
    require(stale_frees == 0, "double free observed on the generation 0 path");

    (void)mc_cuda::getWorkerPlanPool().dropAll();
    require(buffers.empty(), "device buffers leaked on the gain/no-gain sequence");
    active = false;
    std::cout << "  PASS: gain -> no gain -> gain, and generation 0" << std::endl;
}

// A session that failed must retire the retained gain rather than hand it on.
void testInvalidationAfterFailure() {
    std::cout << "Testing retained gain invalidation after a session failure..." << std::endl;
    const int nx = 32, ny = 32;
    reset();
    const std::vector<Image<float> > frames = makeFrames(nx, ny, 2);
    const MultidimArray<float> gain = makeGain(nx, ny, 1.25f);
    watched_gain_sources.insert(gain.data);
    requireSameBytes(runMovie(nx, ny, frames, &gain, 31, "healthy movie"),
                     hostSum(frames, &gain, nx, ny), "healthy movie produced wrong sum");
    require(mc_cuda::getWorkerPlanPool().gain.ptr != nullptr, "gain was not retained");
    const size_t retained = mc_cuda::getWorkerPlanPool().retainedBytes();
    require(retained == (size_t)nx * ny * sizeof(float), "retained byte count wrong");

    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, 2, 0, log);
        session.setGainGeneration(31);
        require(session.initialize(), "failing session initialization");
        MultidimArray<float> sum;
        require(session.applyGainDefectsAndSum(frames, &gain, sum, true), "failing session sum");
        // A recoverable code first, then a fatal one: both must survive.
        session.getFailureState().record(cudaErrorMemoryAllocation, "injected recoverable", 1);
        session.getFailureState().record(cudaErrorIllegalAddress, "injected fatal", 2);
        session.release();
        require(session.getFailureState().firstError() == cudaErrorMemoryAllocation,
                "first recoverable cause was displaced");
        require(session.getFailureState().fatalError() == cudaErrorIllegalAddress,
                "fatal cleanup code was not latched");
    }
    require(mc_cuda::getWorkerPlanPool().gain.ptr == nullptr,
            "a failed session left the retained gain available to the next movie");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == 0,
            "retained byte count survived the failed session");
    require(freed_bytes >= retained, "the retired gain bytes were never freed");
    require(stale_frees == 0, "double free observed on the failure path");
    require(buffers.empty(), "device buffers leaked after the failed session");
    active = false;
    std::cout << "  PASS: failed session retires the retained gain" << std::endl;
}

// Logic-only: the retiring device is selected and the caller's device restored.
// Genuine cross-device execution is UNRUN -- it needs two visible devices.
void testDeviceSelectionRestoredAfterDrop() {
    std::cout << "Testing device selection restored after a retained-gain drop..." << std::endl;
    reset();
    mc_cuda::CudaWorkerPlanPool::GainPool &pool = mc_cuda::getWorkerPlanPool().gain;
    void *buffer = nullptr;
    require(cudaMalloc(&buffer, 4096) == cudaSuccess, "selection fixture allocation");
    pool.ptr = (float *)buffer;
    pool.bytes = 4096;
    pool.generation = 99;
    pool.nx = 32;
    pool.ny = 32;
    // A device this pool entry claims to own, which is not the current device.
    pool.device_id = 7;

    require(__real_cudaSetDevice(0) == cudaSuccess, "selection fixture device reset");
    device_selections.clear();
    intercept_set_device = true;
    CudaFailureState failure;
    const bool ok = pool.drop(&failure);
    intercept_set_device = false;
    require(ok, "drop of a foreign-device entry reported failure");
    require(device_selections.size() == 2, "drop did not select and restore a device");
    require(device_selections[0] == 7, "drop did not select the owning device before freeing");
    require(device_selections[1] == 0, "drop did not restore the caller's device");
    require(!failure.hasFailed(), "device selection recorded a spurious failure");
    require(pool.ptr == nullptr && pool.device_id == -1, "drop left the key populated");
    require(stale_frees == 0, "drop double-freed the entry");

    // Same-device entries need no switch at all.
    require(cudaMalloc(&buffer, 4096) == cudaSuccess, "same-device fixture allocation");
    pool.ptr = (float *)buffer;
    pool.bytes = 4096;
    pool.generation = 100;
    pool.device_id = 0;
    device_selections.clear();
    intercept_set_device = true;
    require(pool.drop(&failure), "same-device drop reported failure");
    intercept_set_device = false;
    require(device_selections.empty(), "same-device drop switched devices needlessly");

    require(buffers.empty(), "device selection fixture leaked");
    active = false;
    std::cout << "  PASS: owning device selected, caller's device restored" << std::endl;
}

// Two runners on one host thread must not mint the same gain identity, and the
// identity must not be readable before gainReferenceFor() has resolved it.
void testRunnerGenerationIdentity() {
    std::cout << "Testing runner gain identity ordering and uniqueness..." << std::endl;
    MotioncorrRunner first;
    MotioncorrRunner second;
    first.fn_gain_reference = "gain_a.mrc";
    second.fn_gain_reference = "gain_b.mrc";
    require(!first.gainIdentityResolvedFor(64, 64),
            "an unresolved gain reported a usable identity");
    require(first.gain_cache_generation == 0, "an unresolved gain minted a non-zero generation");

    // Stand in for gainReferenceFor()'s refill, which is the only writer.
    first.gain_cache().reshape(64, 64);
    first.gain_cache_name = first.fn_gain_reference;
    first.gain_cache_nx = 64;
    first.gain_cache_ny = 64;
    first.gain_cache_filled = true;
    first.gain_cache_generation = 1;
    require(first.gainIdentityResolvedFor(64, 64), "a resolved gain reported no identity");
    require(!first.gainIdentityResolvedFor(32, 32),
            "a resolved gain reported an identity for a different geometry");
    first.fn_gain_reference = "gain_c.mrc";
    require(!first.gainIdentityResolvedFor(64, 64),
            "a changed gain path still reported the old identity");

    require(!second.gainIdentityResolvedFor(64, 64),
            "a second runner inherited the first runner's identity");
    require(second.gain_cache_generation == 0,
            "a second runner started with a non-zero generation");
    std::cout << "  PASS: identity is per-resolution, geometry-checked and per-runner" << std::endl;
}

} // namespace

int main() {
    if (__real_cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n";
        return 1;
    }
    try {
        testGainSequenceABA();
        testGainThenNoGainThenGain();
        testInvalidationAfterFailure();
        testDeviceSelectionRestoredAfterDrop();
        testRunnerGenerationIdentity();
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL: unexpected production exception: " << e << '\n';
        return 1;
    }
    std::cout << "PASS: worker-lifetime device gain pool controls" << std::endl;
    return 0;
}
