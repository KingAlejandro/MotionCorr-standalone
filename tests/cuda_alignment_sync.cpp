// Native controls of the production alignment path. Returned-code injection is
// test-only; it never physically poisons the GPU. The reference adds the two
// predecessor telemetry waits to the same unchanged arithmetic/kernel path.
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_failure_state.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
enum Fault { NONE, CUFFT_BOUNDARY, D2H_BOUNDARY, CUFFT_IMMEDIATE, D2H_IMMEDIATE,
             H2D_IMMEDIATE, MALLOC_FIRST };
struct Event { int id; unsigned record = 0; unsigned generation = 0; bool read = true; };
bool active = false, reference_waits = false, fired = false, drain_done = false;
bool queued = false, cleanup_before_drain = false;
Fault fault = NONE;
unsigned sequence = 0, completed = 0;
int next_event = 0, kernel_reads = 0, cufft_calls = 0, d2h_calls = 0;
int h2d_calls = 0, launch_checks = 0, device_syncs = 0, allocations = 0;
int syncs[9] = {}, frames = 0;
std::string violation, last_log;
std::map<cudaEvent_t, Event> events;
std::map<cudaEvent_t, int> reference_events;
int reference_next_event = 0, reference_stop_records = 0, reference_wait_count = 0;
std::set<void*> buffers;
std::set<cufftHandle> plans;
void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
bool immediateFault() {
    return fault == CUFFT_IMMEDIATE || fault == D2H_IMMEDIATE || fault == H2D_IMMEDIATE;
}
void cleanupCheck() {
    if (active && fired && immediateFault() && !drain_done) cleanup_before_drain = true;
}
void arm(Fault selected = NONE) {
    fault = selected; fired = drain_done = queued = cleanup_before_drain = false;
    sequence = completed = 0; next_event = (int)events.size();
    kernel_reads = cufft_calls = d2h_calls = h2d_calls = launch_checks = 0;
    device_syncs = allocations = 0; std::memset(syncs, 0, sizeof(syncs));
    violation.clear(); active = true;
    for (auto &entry : events) { entry.second.record = entry.second.generation = 0; entry.second.read = true; }
}
void empty() {
    require(buffers.empty() && events.empty() && plans.empty(), "alignment owners leaked resources");
}
}
extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cudaError_t __real_cudaEventCreate(cudaEvent_t*);
cudaError_t __real_cudaEventDestroy(cudaEvent_t);
cudaError_t __real_cudaEventRecord(cudaEvent_t, cudaStream_t);
cudaError_t __real_cudaEventSynchronize(cudaEvent_t);
cudaError_t __real_cudaEventElapsedTime(float*, cudaEvent_t, cudaEvent_t);
cudaError_t __real_cudaDeviceSynchronize();
cudaError_t __real_cudaGetLastError();
cudaError_t __real_cudaMemcpy(void*, const void*, size_t, cudaMemcpyKind);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftDestroy(cufftHandle);
cufftResult __real_cufftExecC2R(cufftHandle, cufftComplex*, cufftReal*);
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active && ++allocations == 1 && fault == MALLOC_FIRST) {
        *ptr = nullptr; fired = true; return cudaErrorMemoryAllocation;
    }
    const auto status = __real_cudaMalloc(ptr, bytes);
    if (active && status == cudaSuccess) buffers.insert(*ptr);
    return status;
}
cudaError_t __wrap_cudaFree(void *ptr) {
    cleanupCheck();
    const auto status = __real_cudaFree(ptr);
    if (active && ptr && status == cudaSuccess && !buffers.erase(ptr)) violation = "double buffer release";
    return status;
}
cudaError_t __wrap_cudaEventCreate(cudaEvent_t *event) {
    const auto status = __real_cudaEventCreate(event);
    if (active && status == cudaSuccess) events.emplace(*event, Event{++next_event});
    if (reference_waits && status == cudaSuccess) reference_events.emplace(*event, ++reference_next_event);
    return status;
}
cudaError_t __wrap_cudaEventDestroy(cudaEvent_t event) {
    cleanupCheck();
    const auto status = __real_cudaEventDestroy(event);
    if (active && status == cudaSuccess && !events.erase(event)) violation = "double event release";
    if (reference_waits && status == cudaSuccess) reference_events.erase(event);
    return status;
}
cudaError_t __wrap_cudaEventRecord(cudaEvent_t event, cudaStream_t stream) {
    const auto status = __real_cudaEventRecord(event, stream);
    if (reference_waits && status == cudaSuccess && reference_events.at(event) == 4) {
        const int phase = reference_stop_records++ % (frames > 1 ? 3 : 2);
        if (phase < 2) {
            ++reference_wait_count;
            const auto wait = __real_cudaEventSynchronize(event);
            if (wait != cudaSuccess) return wait;
        }
    }
    if (active && status == cudaSuccess) {
        auto &e = events.at(event);
        if (e.id == 3 && e.generation != 0 && !e.read)
            violation = "kernel elapsed generation was overwritten before reading";
        e.record = ++sequence; ++e.generation; e.read = false;
        if (e.id == 3) queued = true;
    }
    return status;
}
cudaError_t __wrap_cudaEventSynchronize(cudaEvent_t event) {
    const auto status = __real_cudaEventSynchronize(event);
    if (!active || status != cudaSuccess) return status;
    auto &e = events.at(event); ++syncs[e.id]; completed = e.record; queued = false;
    if (!fired && ((fault == CUFFT_BOUNDARY && e.id == 6) ||
                   (fault == D2H_BOUNDARY && e.id == 8))) {
        fired = true; (void)__real_cudaGetLastError(); return cudaErrorIllegalAddress;
    }
    return status;
}
cudaError_t __wrap_cudaEventElapsedTime(float *ms, cudaEvent_t start, cudaEvent_t stop) {
    if (active) {
        auto &a = events.at(start); auto &b = events.at(stop);
        if (a.record > completed || b.record > completed || a.generation != b.generation)
            violation = "kernel elapsed was read before checked completion or from mismatched generations";
        if (a.id == 3) {
            const int phase = (int)(a.generation - 1) % (frames > 1 ? 3 : 2);
            const int gate = phase == 0 ? 6 : phase == 1 ? 8 : 4;
            // Completed position alone is insufficient if a mutant inserts an
            // early read after a different wait; require the kept stage gate.
            if (syncs[gate] < (int)((a.generation - 1) / (frames > 1 ? 3 : 2) + 1))
                violation = "kernel elapsed was read before its kept stage boundary";
            ++kernel_reads; a.read = b.read = true;
        }
    }
    // A protocol mutant may make the runtime return NotReady depending on GPU
    // speed. Keep that failure deterministic in the explicit protocol verdict,
    // rather than letting an incidental runtime exception mask its assertion.
    if (active && !violation.empty()) { *ms = 0; return cudaSuccess; }
    return __real_cudaEventElapsedTime(ms, start, stop);
}
cudaError_t __wrap_cudaDeviceSynchronize() {
    const auto status = __real_cudaDeviceSynchronize();
    if (!active) return status;
    ++device_syncs;
    if (fired && immediateFault()) {
        drain_done = queued; queued = false;
        (void)__real_cudaGetLastError();
        return status == cudaSuccess ? cudaErrorIllegalAddress : status;
    }
    queued = false; return status;
}
cudaError_t __wrap_cudaGetLastError() {
    if (active) ++launch_checks;
    return __real_cudaGetLastError();
}
cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t bytes, cudaMemcpyKind kind) {
    if (active && kind == cudaMemcpyDeviceToHost) {
        ++d2h_calls;
        if (!fired && fault == D2H_IMMEDIATE) {
            fired = true; (void)__real_cudaGetLastError(); return cudaErrorMemoryAllocation;
        }
    }
    if (active && kind == cudaMemcpyHostToDevice) {
        ++h2d_calls;
        if (!fired && fault == H2D_IMMEDIATE && h2d_calls == 2) {
            fired = true; (void)__real_cudaGetLastError(); return cudaErrorMemoryAllocation;
        }
        queued = true;
    }
    return __real_cudaMemcpy(dst, src, bytes, kind);
}
cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    const auto status = __real_cufftCreate(plan);
    if (active && status == CUFFT_SUCCESS) plans.insert(*plan);
    return status;
}
cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    cleanupCheck();
    const auto status = __real_cufftDestroy(plan);
    if (active && status == CUFFT_SUCCESS && !plans.erase(plan)) violation = "double plan release";
    return status;
}
cufftResult __wrap_cufftExecC2R(cufftHandle plan, cufftComplex *in, cufftReal *out) {
    if (active) {
        ++cufft_calls;
        if (!fired && fault == CUFFT_IMMEDIATE) {
            fired = true; (void)__real_cudaGetLastError(); return CUFFT_EXEC_FAILED;
        }
    }
    return __real_cufftExecC2R(plan, in, out);
}
}
namespace {
struct Result { bool converged; std::vector<RFLOAT> x, y; std::vector<cufftComplex> data; };
Result align(PatchAlignmentWorkspace &workspace, int nframes, int seed, int maxiter = 4, int device_id = 0) {
    const bool armed = active; active = false;
    const size_t size = (size_t)33 * 64 * nframes;
    std::vector<cufftComplex> input(size);
    unsigned state = (unsigned)seed;
    for (auto &value : input) {
        state = 1664525u * state + 1013904223u;
        value.x = (float)((int)(state & 65535u) - 32768) / 4096.0f;
        state = 1664525u * state + 1013904223u;
        value.y = (float)((int)(state & 65535u) - 32768) / 4096.0f;
    }
    cufftComplex *ptr = nullptr;
    require(cudaMalloc(&ptr, size * sizeof(cufftComplex)) == cudaSuccess, "input allocation failed");
    require(cudaMemcpy(ptr, input.data(), size * sizeof(cufftComplex), cudaMemcpyHostToDevice) == cudaSuccess,
            "input upload failed");
    Result result{false, std::vector<RFLOAT>(nframes, 0), std::vector<RFLOAT>(nframes, 0), input};
    std::ostringstream log; frames = nframes; last_log.clear(); active = armed;
    try {
        result.converged = cudaAlignPatchDeviceWithWorkspace(workspace, ptr, nframes, 64, 64,
            2, result.x, result.y, maxiter, 1, device_id, log);
    } catch (...) {
        last_log = log.str(); active = false; __real_cudaFree(ptr); active = armed; throw;
    }
    last_log = log.str(); active = false;
    require(cudaMemcpy(result.data.data(), ptr, size * sizeof(cufftComplex), cudaMemcpyDeviceToHost) == cudaSuccess,
            "result download failed");
    __real_cudaFree(ptr); active = armed; return result;
}
void exact(const Result &a, const Result &b) {
    require(a.converged == b.converged && a.data.size() == b.data.size() &&
        std::memcmp(a.x.data(), b.x.data(), a.x.size()*sizeof(RFLOAT)) == 0 &&
        std::memcmp(a.y.data(), b.y.data(), a.y.size()*sizeof(RFLOAT)) == 0 &&
        std::memcmp(a.data.data(), b.data.data(), a.data.size()*sizeof(cufftComplex)) == 0,
        "alignment outputs differ from predecessor-wait reference");
}
void protocol() {
    require(violation.empty(), violation.c_str());
    const int iterations = cufft_calls;
    require(syncs[6] == iterations && syncs[8] == iterations && syncs[2] == 1,
            "kept cufft/D2H/total boundary count changed");
    require(syncs[4] == (frames > 1 ? iterations : 0) && device_syncs == 0,
            "telemetry-only kernel waits were retained or healthy device drain added");
    require(kernel_reads == iterations*(frames > 1 ? 3 : 2), "kernel elapsed generation count changed");
}
void healthy() {
    for (int nframes : {1, 4}) {
        CudaFailureState failure; PatchAlignmentWorkspace workspace(&failure);
        int call = 0;
        for (int seed : {11, 12, 11}) {
            arm(); const Result candidate = align(workspace, nframes, seed);
            protocol(); require(workspace.isValid() && !failure.hasFailed(), "healthy workspace invalid or failed");
            require(allocations == (call++ == 0 ? 8 : 0), "warm alignment workspace repeated buffer setup");
            active = false;
            PatchAlignmentWorkspace reference;
            reference_next_event = reference_stop_records = reference_wait_count = 0; reference_waits = true;
            const Result expected = align(reference, nframes, seed);
            require(reference_wait_count == 2*cufft_calls, "reference failed to insert predecessor telemetry waits");
            require(reference.release(), "reference release failed");
            reference_waits = false; require(reference_events.empty(), "reference events leaked");
            exact(candidate, expected);
        }
        active = true; require(workspace.release(), "healthy release failed"); empty(); active = false;
    }
    CudaFailureState failure; PatchAlignmentWorkspace workspace(&failure);
    arm(); const Result single_iteration = align(workspace, 4, 11, 1);
    protocol(); require(!single_iteration.converged, "maxiter1 fixture failed to exercise nonconvergence");
    require(workspace.isValid(), "nonconvergence invalidated healthy workspace");
    require(workspace.release(), "nonconvergence release failed"); empty(); active = false;
    std::cout << "PASS: exact one/multi-frame warm reuse and maxiter1; event generation/read protocol\n";
}
void failureCase(Fault selected) {
    CudaFailureState failure; PatchAlignmentWorkspace workspace(&failure);
    arm(selected); bool threw = false;
    try { (void)align(workspace, 4, 11); } catch (const RelionError &) { threw = true; }
    require(threw && fired && !workspace.isValid(), "fault failed to throw/invalidate");
    require(last_log.find("] completed;") == std::string::npos, "fault emitted completion marker");
    if (selected == CUFFT_BOUNDARY) {
        require(syncs[6] == 1 && syncs[8] == 0 && d2h_calls == 0 && launch_checks == 3,
                "cufft boundary fatal permitted later peak dispatch/data consumption");
        require(std::string(failure.firstStage()).find("ev_stop_cufft") != std::string::npos,
                "cufft boundary original stage lost");
    } else if (selected == D2H_BOUNDARY) {
        require(syncs[8] == 1 && h2d_calls == 0 && launch_checks == 4,
                "D2H boundary fatal permitted later shift dispatch");
        require(std::string(failure.firstStage()).find("ev_stop_d2h") != std::string::npos,
                "D2H boundary original stage lost");
    } else {
        require(drain_done && device_syncs == 1 && !cleanup_before_drain,
                "immediate failure did not check drain before resource cleanup");
        require(std::string(failure.fatalStage()) == "alignment exception drain",
                "cleared-slot late fatal drain status lost");
        if (selected == CUFFT_IMMEDIATE) {
            require(failure.firstCufftError() == CUFFT_EXEC_FAILED && failure.firstError() == cudaSuccess,
                    "immediate cuFFT original cause overwritten");
            require(d2h_calls == 0 && launch_checks == 3, "immediate cuFFT failure permitted peak/shift dispatch");
        } else {
            require(failure.firstError() == cudaErrorMemoryAllocation &&
                    failure.firstCufftError() == CUFFT_SUCCESS, "immediate copy original cause overwritten");
            require(launch_checks == 4, "immediate copy failure permitted phase-shift dispatch");
        }
    }
    require(failure.isPoisoned(), "alignment fault did not retain fatal state");
    require(__real_cudaGetLastError() == cudaSuccess, "injection polluted runtime last-error slot");
    empty(); arm(); bool refused = false;
    try { (void)align(workspace, 4, 11); } catch (const RelionError &) { refused = true; }
    require(refused && allocations == 0 && cufft_calls == 0 && launch_checks == 0 && device_syncs == 0,
            "poisoned alignment workspace redispatched");
    empty(); active = false;
    std::cout << "PASS: selected alignment failure retains cause/fatal, drains before cleanup and refuses retry\n";
}
void guards() {
    for (bool invalid_device : {false, true}) {
        CudaFailureState failure; PatchAlignmentWorkspace workspace(&failure);
        arm(invalid_device ? NONE : MALLOC_FIRST); bool threw = false;
        try { (void)align(workspace, 4, 11, 4, invalid_device ? -1 : 0); }
        catch (const RelionError &) { threw = true; }
        require(threw && device_syncs == 0 && launch_checks == 0,
                "alignment drained without a selected device and submitted work");
        empty(); active = false;
    }
    std::cout << "PASS: invalid-device/pre-submission guards avoid unnecessary drains\n";
}
}
int main(int argc, char **argv) {
    std::string selected = "all";
    if (argc == 3 && std::string(argv[1]) == "--case") selected = argv[2];
    else if (argc != 1) { std::cerr << "Usage: --case SELECTOR\n"; return 1; }
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 required\n"; return 1;
    }
    try {
        bool known = selected == "all";
        if (selected == "all" || selected == "healthy" || selected == "event-order") { known = true; healthy(); }
        const std::pair<const char*, Fault> cases[] = {{"cufft-boundary", CUFFT_BOUNDARY},
            {"d2h-boundary", D2H_BOUNDARY}, {"cufft-immediate", CUFFT_IMMEDIATE},
            {"d2h-immediate", D2H_IMMEDIATE}, {"h2d-immediate", H2D_IMMEDIATE}};
        for (const auto &entry : cases) if (selected == "all" || selected == entry.first) { known = true; failureCase(entry.second); }
        if (selected == "all" || selected == "guard") { known = true; guards(); }
        require(known, "unknown selector"); empty();
    } catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
      catch (RelionError &e) { std::cerr << "FAIL: unexpected production exception: " << e << '\n'; return 1; }
    std::cout << "PASS: actual production alignment synchronization controls (injected codes, not poisoned hardware)\n";
    return 0;
}
