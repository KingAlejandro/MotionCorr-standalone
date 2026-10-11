// SPDX-License-Identifier: GPL-2.0-or-later
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
#include <cstdlib>
#include <cstring>
#include <iomanip>
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
size_t free_attempts = 0;
// Cumulative ledger survives per-case resets, so --case all cannot hide a leak
// or stale release in an earlier case by clearing its observations.
size_t process_allocated_bytes = 0;
size_t process_freed_bytes = 0;
size_t process_stale_frees = 0;
bool reject_alloc_while_retained = false;
size_t blocked_allocations = 0;
bool virtual_device_mode = false;
int virtual_device = 0;
bool fail_owner_selection = false;
void *fatal_gain_cleanup_pointer = nullptr;
bool fail_gain_cleanup = false;
size_t fatal_gain_cleanup_calls = 0;

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
cudaError_t __real_cudaGetDevice(int *);
cudaError_t __real_cudaMemcpy(void *, const void *, size_t, cudaMemcpyKind);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (reject_alloc_while_retained && mc_cuda::getWorkerPlanPool().gain.ptr != nullptr) {
        ++blocked_allocations;
        *ptr = nullptr;
        return cudaErrorMemoryAllocation;
    }
    const cudaError_t status = __real_cudaMalloc(ptr, bytes);
    if (active && status == cudaSuccess) {
        buffers[*ptr] = bytes;
        allocated_bytes += bytes;
        process_allocated_bytes += bytes;
    }
    return status;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    if (active && ptr != nullptr) ++free_attempts;
    if (active && fail_gain_cleanup && ptr == fatal_gain_cleanup_pointer) {
        // A returned asynchronous fatal code must survive a clean runtime slot.
        // Do not poison the physical device or lose our fixture's allocation:
        // it stays in buffers until this control explicitly releases it.
        ++fatal_gain_cleanup_calls;
        (void)cudaGetLastError();
        return cudaErrorIllegalAddress;
    }
    size_t bytes = 0;
    if (active && ptr != nullptr) {
        std::map<void *, size_t>::iterator it = buffers.find(ptr);
        if (it != buffers.end()) bytes = it->second;
    }
    const cudaError_t status = __real_cudaFree(ptr);
    if (active && ptr != nullptr && status == cudaSuccess) {
        if (buffers.erase(ptr) == 0) { ++stale_frees; ++process_stale_frees; }
        else { freed_bytes += bytes; process_freed_bytes += bytes; }
    }
    return status;
}

cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t bytes, cudaMemcpyKind kind) {
    if (active && kind == cudaMemcpyHostToDevice && watched_gain_sources.count(src) != 0)
        ++gain_uploads;
    return __real_cudaMemcpy(dst, src, bytes, kind);
}

cudaError_t __wrap_cudaGetDevice(int *device) {
    if (virtual_device_mode) { *device = virtual_device; return cudaSuccess; }
    return __real_cudaGetDevice(device);
}

cudaError_t __wrap_cudaSetDevice(int device) {
    if (fail_owner_selection && device == 0) {
        // Returned failure survives even though the runtime last-error slot is clear.
        (void)cudaGetLastError();
        return cudaErrorInvalidDevice;
    }
    if (virtual_device_mode) {
        virtual_device = device;
        return device == 0 ? __real_cudaSetDevice(0) : cudaSuccess;
    }
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
    require(mc_cuda::getWorkerPlanPool().dropAll(), "previous case retained gain cleanup failed");
    require(buffers.empty() && allocated_bytes == freed_bytes && stale_frees == 0,
            "previous case tracked allocation ledger did not close");
    allocated_bytes = freed_bytes = stale_frees = free_attempts = 0;
    blocked_allocations = 0;
    reject_alloc_while_retained = virtual_device_mode = fail_owner_selection = false;
    fatal_gain_cleanup_pointer = nullptr;
    fail_gain_cleanup = false;
    fatal_gain_cleanup_calls = 0;
    watched_gain_sources.clear();
    gain_uploads = 0;
    active = true;
}

void printVisibleDevices() {
    int count = 0;
    require(cudaGetDeviceCount(&count) == cudaSuccess && count > 0,
            "visible device identity enumeration failed");
    const char *mask = std::getenv("CUDA_VISIBLE_DEVICES");
    std::cout << "CUDA_VISIBLE_DEVICES=" << (mask ? mask : "<unset>")
              << " visible_count=" << count << '\n';
    for (int device = 0; device < count; ++device) {
        cudaDeviceProp properties{};
        require(cudaGetDeviceProperties(&properties, device) == cudaSuccess,
                "visible device UUID query failed");
        std::ostringstream uuid;
        uuid << "GPU-" << std::hex << std::setfill('0');
        bool any_nonzero = false;
        for (int byte = 0; byte < 16; ++byte) {
            if (byte == 4 || byte == 6 || byte == 8 || byte == 10) uuid << '-';
            const unsigned value = static_cast<unsigned char>(properties.uuid.bytes[byte]);
            any_nonzero = any_nonzero || value != 0;
            uuid << std::setw(2) << value;
        }
        require(any_nonzero, "visible device UUID is unavailable/zero");
        std::cout << "CUDA device index=" << device << " UUID=" << uuid.str()
                  << " name=" << properties.name << '\n';
    }
}

void requireClosedProcessLedger(const std::string &selector) {
    std::cout << "Tracked allocation ledger selector=" << selector
              << " allocated_bytes=" << process_allocated_bytes
              << " freed_bytes=" << process_freed_bytes
              << " stale_frees=" << process_stale_frees
              << " live_buffers=" << buffers.size() << '\n';
    require(buffers.empty() && process_allocated_bytes == process_freed_bytes &&
            process_stale_frees == 0,
            "final per-process tracked allocation ledger did not close");
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
    require(mc_cuda::getWorkerPlanPool().gain.retainedBytes() == (size_t)nx * ny * sizeof(float),
            "retained byte count does not match the gain size");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() ==
                mc_cuda::getWorkerPlanPool().gain.retainedBytes() +
                mc_cuda::getWorkerPlanPool().geometry.retainedBytes(),
            "pool retained bytes are not the sum of its entries");

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
    require(mc_cuda::getWorkerPlanPool().gain.retainedBytes() == (size_t)nx2 * ny2 * sizeof(float),
            "retained byte count did not follow the new geometry");
    require(stale_frees == 0, "double free observed on the geometry change");

    (void)mc_cuda::getWorkerPlanPool().dropAll();
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == 0, "pool still reports retained bytes after dropAll");
    require(buffers.empty(), "device buffers outlived the sessions and the pool");
    active = false;
    std::cout << "  PASS: A -> B -> A, reuse, geometry change" << std::endl;
}

// gain -> no gain -> gain. No-gain admission intentionally retires an unused
// cached gain before movie allocation; returning to gain uploads again.
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
    require(mc_cuda::getWorkerPlanPool().gain.ptr == nullptr,
            "no-gain admission kept an unused retained gain");

    requireSameBytes(runMovie(nx, ny, frames, &gain, 21, "gain movie again"),
                     hostSum(frames, &gain, nx, ny), "gain movie after a no-gain movie produced wrong sum");
    require(gain_uploads == 2, "gain after no-gain admission was not uploaded again");
    require(stale_frees == 0, "double free observed across gain -> no gain -> gain");

    // generation 0 with a gain keeps the original upload-every-movie behaviour
    // and must own its copy rather than touch the pool.
    requireSameBytes(runMovie(nx, ny, frames, &gain, 0, "unidentified gain movie"),
                     hostSum(frames, &gain, nx, ny), "generation 0 gain produced wrong sum");
    require(mc_cuda::getWorkerPlanPool().gain.ptr == nullptr,
            "generation 0 admission retained an unused gain");
    require(gain_uploads == 3, "generation 0 did not upload its own copy");
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
    const size_t retained = mc_cuda::getWorkerPlanPool().gain.retainedBytes();
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
    std::ostringstream retry_log;
    CudaMovieSession retry(nx, ny, 2, 0, retry_log);
    retry.setGainGeneration(32);
    const size_t allocated_before_retry = allocated_bytes;
    require(!retry.initialize(), "fresh session redispatched after worker fatal retirement");
    require(allocated_bytes == allocated_before_retry, "retired worker attempted fresh buffer allocation");
    require(retry.getFailureState().fatalError() == cudaErrorIllegalAddress,
            "fresh session lost retired worker original fatal code");
    require(mc_cuda::getWorkerPlanPool().retiredFor(1), "retired worker revived on another device identity");
    active = false;
    std::cout << "  PASS: failed session retires the retained gain" << std::endl;
}

// A fatal error first observed while dropping an otherwise recoverable failed
// session must retire the worker before release() returns. Keep that old session
// alive: its destructor must not be the operation that finally closes the gate.
// Run in a separate process because worker retirement intentionally never resets.
void testFatalGainCleanupTransition() {
    std::cout << "Testing recoverable session -> fatal retained-gain cleanup...\n";
    reset();
    const int nx = 32, ny = 24;
    const auto frames = makeFrames(nx, ny, 2);
    const auto gain = makeGain(nx, ny, 1.125f);
    watched_gain_sources.insert(gain.data);
    std::ostringstream failed_log, retry_log;
    CudaMovieSession failed(nx, ny, 2, 0, failed_log);
    failed.setGainGeneration(401);
    require(failed.initialize(), "cleanup-fatal fixture initialization");
    MultidimArray<float> sum;
    require(failed.applyGainDefectsAndSum(frames, &gain, sum, true),
            "cleanup-fatal fixture preprocessing");
    requireSameBytes(sum, hostSum(frames, &gain, nx, ny),
                     "cleanup-fatal healthy fixture changed pixels");
    void *owned_gain = mc_cuda::getWorkerPlanPool().gain.ptr;
    require(owned_gain != nullptr && buffers.count(owned_gain) == 1,
            "cleanup-fatal fixture lacks tracked retained gain");
    // Drain the injected allocation even on a discriminating assertion failure.
    struct FixtureCleanup {
        void *pointer;
        ~FixtureCleanup() {
            fail_gain_cleanup = false;
            fatal_gain_cleanup_pointer = nullptr;
            if (buffers.count(pointer) != 0) (void)cudaFree(pointer);
        }
    } fixture_cleanup{owned_gain};
    failed.getFailureState().record(cudaErrorMemoryAllocation, "recoverable before cleanup", 401);
    fatal_gain_cleanup_pointer = owned_gain;
    fail_gain_cleanup = true;
    failed.release();
    fail_gain_cleanup = false;
    require(fatal_gain_cleanup_calls == 1, "retained gain cleanup fault was not reached exactly once");
    require(cudaPeekAtLastError() == cudaSuccess, "cleanup fatal control left a runtime error slot");
    require(failed.getFailureState().firstError() == cudaErrorMemoryAllocation &&
            failed.getFailureState().fatalError() == cudaErrorIllegalAddress,
            "gain cleanup fatal displaced first failure or lost original fatal");
    require(std::string(failed.getFailureState().fatalStage()) == "dropGain cudaFree",
            "gain cleanup fatal lost its production origin");
    require(mc_cuda::getWorkerPlanPool().retiredErrorFor(0) == cudaErrorIllegalAddress,
            "gain cleanup fatal did not retire worker before release returned");
    require(mc_cuda::getWorkerPlanPool().gain.ptr == nullptr &&
            mc_cuda::getWorkerPlanPool().retainedBytes() == 0,
            "failed gain cleanup advertised reusable bytes");
    require(buffers.size() == 1 && buffers.count(owned_gain) == 1,
            "failed gain cleanup lost fixture ownership or leaked session buffers");
    const size_t allocated_before_retry = allocated_bytes;
    CudaMovieSession retry(nx, ny, 2, 0, retry_log);
    retry.setGainGeneration(402);
    require(!retry.initialize(), "fresh session redispatched after cleanup-origin fatal");
    require(allocated_bytes == allocated_before_retry,
            "cleanup-retired worker allocated fresh movie buffers");
    require(retry.getFailureState().fatalError() == cudaErrorIllegalAddress,
            "fresh session lost original cleanup-origin fatal");
    require(cudaFree(owned_gain) == cudaSuccess, "cleanup-fatal fixture owned gain release failed");
    require(buffers.empty() && stale_frees == 0, "cleanup-fatal fixture leaked or double-freed");
    fatal_gain_cleanup_pointer = nullptr;
    std::cout << "  PASS: cleanup-origin fatal retires before a fresh session; tracked fixture released\n";
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

// Actual production pool drop, owner0/current1. With one visible device, only
// the device-selection identity is simulated; allocation/free still run on GPU0.
void testOwnerSelectionFailure() {
    reset();
    int devices = 0;
    require(cudaGetDeviceCount(&devices) == cudaSuccess, "selection device count");
    require(__real_cudaSetDevice(0) == cudaSuccess, "selection owner reset");
    auto &pool = mc_cuda::getWorkerPlanPool().gain;
    void *buffer = nullptr;
    require(cudaMalloc(&buffer, 4096) == cudaSuccess, "failed-selection gain allocation");
    pool.ptr = static_cast<float *>(buffer); pool.bytes = 4096;
    pool.generation = 91; pool.nx = pool.ny = 32; pool.device_id = 0;
    if (devices >= 2) {
        require(__real_cudaSetDevice(1) == cudaSuccess, "selection caller device1");
        std::cout << "Testing actual two-device gain cleanup owner0/current1...\n";
    } else {
        virtual_device_mode = true; virtual_device = 1;
        std::cout << "Testing one-GPU logic-only selection owner0/current1; actual device1 UNRUN...\n";
    }
    const size_t before = free_attempts;
    fail_owner_selection = true;
    CudaFailureState failure;
    const bool dropped = pool.drop(&failure);
    fail_owner_selection = false;
    require(!dropped && failure.firstError() == cudaErrorInvalidDevice,
            "owning-device selection failure not retained");
    require(cudaPeekAtLastError() == cudaSuccess, "selection control did not clear runtime slot");
    require(free_attempts == before, "failed owner selection issued gain free");
    require(pool.ptr == buffer && pool.bytes == 4096 && pool.generation == 0,
            "failed owner selection lost invalidated gain ownership");
    int current = -1;
    require(cudaGetDevice(&current) == cudaSuccess && current == 1,
            "failed owner selection changed caller device");
    require(pool.drop(&failure), "owning-device checked release retry failed");
    require(cudaGetDevice(&current) == cudaSuccess && current == 1,
            "checked release retry did not restore caller device");
    require(pool.drop(&failure) && free_attempts == before + 1 && pool.retainedBytes() == 0,
            "checked release retry was not idempotent");
    require(failure.firstError() == cudaErrorInvalidDevice, "checked retry erased original failure");
    virtual_device_mode = false;
    require(__real_cudaSetDevice(0) == cudaSuccess, "selection final device reset");
    require(buffers.empty() && stale_frees == 0, "selection retry leaked or freed stale gain");
    active = false;
}

void testInterleavedSessions() {
    std::cout << "Testing interleaved session gain leases...\n";
    const int nx = 32, ny = 24;
    reset();
    const auto frames = makeFrames(nx, ny, 2);
    const auto gain_a = makeGain(nx, ny, 1.25f);
    const auto gain_b = makeGain(nx, ny, -0.875f);
    std::ostringstream log_a, log_b;
    CudaMovieSession a(nx, ny, 2, 0, log_a), b(nx, ny, 2, 0, log_b);
    a.setGainGeneration(201); b.setGainGeneration(202);
    require(a.initialize(), "session A initialization");
    MultidimArray<float> sum_a, sum_b;
    require(a.applyGainDefectsAndSum(frames, &gain_a, sum_a, true), "session A first gain use");
    requireSameBytes(sum_a, hostSum(frames, &gain_a, nx, ny), "session A initial gain sum");
    const float *borrowed = mc_cuda::getWorkerPlanPool().gain.ptr;
    const size_t bytes = mc_cuda::getWorkerPlanPool().retainedBytes();
    require(!b.initialize(), "session B initialized through another live gain lease");
    require(!b.applyGainDefectsAndSum(frames, &gain_b, sum_b, true),
            "refused session B published gain output");
    require(NZYXSIZE(sum_b) == 0, "refused session B changed output array");
    b.release();
    require(mc_cuda::getWorkerPlanPool().gain.ptr == borrowed &&
            mc_cuda::getWorkerPlanPool().retainedBytes() == bytes,
            "refused session B evicted session A gain");
    require(a.applyGainDefectsAndSum(frames, &gain_a, sum_a, true), "session A after refused B");
    requireSameBytes(sum_a, hostSum(frames, &gain_a, nx, ny), "session A stale gain after refused B");
    a.release();
    require(mc_cuda::getWorkerPlanPool().dropAll() && buffers.empty() && stale_frees == 0,
            "interleaved gain lease leaked or freed stale gain");
    active = false;
}

void testStaleGainAdmission() {
    std::cout << "Testing early stale-gain retirement before movie admission...\n";
    reset();
    const auto frames = makeFrames(64, 48, 2);
    const auto gain = makeGain(64, 48, 1.125f);
    (void)runMovie(64, 48, frames, &gain, 301, "old large gain fixture");
    require(mc_cuda::getWorkerPlanPool().gain.ptr != nullptr, "admission fixture lacks stale gain");
    std::ostringstream log;
    CudaMovieSession smaller(32, 24, 2, 0, log);
    smaller.setGainGeneration(302);
    reject_alloc_while_retained = true;
    const bool initialized = smaller.initialize();
    reject_alloc_while_retained = false;
    require(initialized, "unused stale gain denied smaller movie admission");
    require(blocked_allocations == 0 && mc_cuda::getWorkerPlanPool().gain.ptr == nullptr,
            "stale gain was not retired before first movie allocation");
    const auto small_frames = makeFrames(32, 24, 2);
    const auto small_gain = makeGain(32, 24, 0.875f);
    MultidimArray<float> sum;
    require(smaller.applyGainDefectsAndSum(small_frames, &small_gain, sum, true), "smaller gain output");
    requireSameBytes(sum, hostSum(small_frames, &small_gain, 32, 24), "smaller admitted gain sum");
    smaller.release();
    require(mc_cuda::getWorkerPlanPool().dropAll() && buffers.empty() && stale_frees == 0,
            "early admission leaked or freed stale gain");
    active = false;
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

int main(int argc, char **argv) {
    if (__real_cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n";
        return 1;
    }
    try {
        require(argc == 1 || (argc == 3 && std::string(argv[1]) == "--case"),
                "invalid native case arguments");
        const std::string which = argc == 3 && std::string(argv[1]) == "--case"
            ? argv[2] : "all";
        require(which == "all" || which == "selection" || which == "lease" ||
                which == "admission" || which == "fatal" || which == "cleanup-fatal",
                "unknown native case selector");
        printVisibleDevices();
        if (which == "all") {
            testGainSequenceABA();
            testGainThenNoGainThenGain();
            testDeviceSelectionRestoredAfterDrop();
        }
        if (which == "all" || which == "selection") testOwnerSelectionFailure();
        if (which == "all" || which == "lease") testInterleavedSessions();
        if (which == "all" || which == "admission") testStaleGainAdmission();
        if (which == "all") testRunnerGenerationIdentity();
        // Retirement is sticky for the worker lifetime: this test must run last.
        if (which == "all" || which == "fatal") testInvalidationAfterFailure();
        if (which == "cleanup-fatal") testFatalGainCleanupTransition();
        requireClosedProcessLedger(which);
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
