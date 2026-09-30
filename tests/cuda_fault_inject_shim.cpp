// Issue #69: link-time fault injection for the REAL motioncorr binary.
//
// Why this exists. The P1c fix -- carrying a consumed CUDA status out of
// cudaPreparePatch so the runner can refuse a re-dispatch onto a poisoned context --
// had no control that exercised it. tests/cuda_error_class.cpp drives the predicate
// with a hand-built CudaFailureState; it never calls cudaPreparePatch and never
// executes the runner's post-prep check, so it passes unchanged against the pre-fix
// source. That was stated in RESULTS §5e as a retraction, and this closes it.
//
// This translation unit is linked ONLY into the test binary motioncorr_faultinject,
// alongside the production src/apps/run_motioncorr.cpp. Nothing in src/ knows it
// exists; there is no production fault switch and none can be active in a real run.
//
// SCOPE, stated plainly: the fault is an INJECTED ERROR CODE returned by an interposed
// cudaMalloc. No hardware is poisoned and no device is reset. It proves that the
// production plumbing carries a poisoning status out of the helper and that the runner
// refuses on it. It does NOT prove behaviour under a genuine illegal-address or ECC
// fault, which remains UNRUN and cannot be synthesised here.
//
//   MC_FAULT_ORDINAL  1-based index of the cudaMalloc call to fail (0/unset = never)
//   MC_FAULT_CODE     "poison" -> cudaErrorIllegalAddress, else cudaErrorMemoryAllocation
//   MC_FAULT_TRACE    if set, log every cudaMalloc ordinal to stderr for ordinal discovery
//   MC_COUNT_FAULT_ORDINAL  1-based cudaGetDeviceCount call to replace
//   MC_COUNT_FAULT_CODE     "poison", "recoverable", or "zero-devices"

#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <dlfcn.h>
#include <execinfo.h>

extern "C" cudaError_t __real_cudaMalloc(void **ptr, size_t size);
extern "C" cudaError_t __real_cudaFree(void *ptr);
extern "C" cudaError_t __real_cudaGetDeviceCount(int *count);

namespace {
// Not atomic, deliberately. Every cudaMalloc on the path under test is issued from the
// main thread -- the OpenMP regions in the fallback do host-side FFT only -- so the
// ordinal is deterministic. The driver re-derives the ordinal on every run regardless,
// so any drift fails loudly rather than silently selecting the wrong call.
std::set<void*> g_owned;
size_t g_stale = 0;
void report_owned() {
    std::fprintf(stderr, "[faultinject] remaining-owned=%zu stale-releases=%zu\n", g_owned.size(), g_stale);
}
long  g_seen = 0;
long  g_at = -1;
long g_count_seen = 0;
long g_count_at = 0;
cudaError_t g_count_error = cudaSuccess;
bool  g_poison = false;
bool  g_trace = false;
bool  g_init = false;

const char *g_preprocess_fault = nullptr;
bool g_preprocess_injected = false;
bool g_preprocess_release_injected = false;

// Test binary only, exported with -rdynamic. Resolve the real production caller
// rather than relying on a fixture-specific allocation ordinal or byte count.
// The driver requires an exact injection witness, so unavailable symbols fail it.
bool called_from(const char *name) {
    void *frames[16];
    const int n = backtrace(frames, 16);
    for (int i = 1; i < n; ++i) {
        Dl_info info = {};
        if (dladdr(frames[i], &info) && info.dli_sname &&
            std::strstr(info.dli_sname, name)) return true;
    }
    return false;
}

bool preprocess_mode(const char *name) {
    return g_preprocess_fault && std::strcmp(g_preprocess_fault, name) == 0;
}

cudaError_t inject_preprocess(bool fatal, const char *boundary) {
    g_preprocess_injected = true;
    // Consume any unrelated launch slot: the returned code alone must survive
    // through the production helper's failure state and session disposal.
    (void)cudaGetLastError();
    const cudaError_t code = fatal ? cudaErrorIllegalAddress : cudaErrorMemoryAllocation;
    std::fprintf(stderr, "[preprocessfault] injected %s at %s; pending slot cleared\n",
                 cudaGetErrorName(code), boundary);
    return code;
}


void init_once() {
    if (g_init) return;
    g_init = true;
    std::atexit(report_owned);
    const char *o = std::getenv("MC_FAULT_ORDINAL");
    g_at = o ? std::atol(o) : 0;
    const char *c = std::getenv("MC_FAULT_CODE");
    g_poison = (c && std::strcmp(c, "poison") == 0);
    g_trace = std::getenv("MC_FAULT_TRACE") != nullptr;
    g_preprocess_fault = std::getenv("MC_PREPROCESS_FAULT");
    const char *count_ordinal = std::getenv("MC_COUNT_FAULT_ORDINAL");
    g_count_at = count_ordinal ? std::atol(count_ordinal) : 0;
    const char *count_code = std::getenv("MC_COUNT_FAULT_CODE");
    if (count_code && std::strcmp(count_code, "poison") == 0)
        g_count_error = cudaErrorIllegalAddress;
    else if (count_code && std::strcmp(count_code, "recoverable") == 0)
        g_count_error = cudaErrorInitializationError;
}
} // namespace

extern "C" cudaError_t __wrap_cudaGetDeviceCount(int *count) {
    init_once();
    const long n = ++g_count_seen;
    if (g_trace) std::fprintf(stderr, "[faultinject] cudaGetDeviceCount #%ld\n", n);
    if (g_count_at > 0 && n == g_count_at) {
        if (count) *count = 0;
        const cudaError_t pending = cudaGetLastError();
        if (pending != cudaSuccess) {
            std::fprintf(stderr, "[faultinject] enumeration precondition failed: pending=%s\n",
                         cudaGetErrorName(pending));
            std::exit(3);
        }
        std::fprintf(stderr, "[faultinject] INJECTING %s at cudaGetDeviceCount #%ld; last-error clean\n",
                     cudaGetErrorName(g_count_error), n);
        return g_count_error;
    }
    return __real_cudaGetDeviceCount(count);
}

extern "C" cudaError_t __wrap_cudaMalloc(void **ptr, size_t size) {
    init_once();
    if (g_preprocess_injected)
        std::fprintf(stderr, "[preprocessfault] later cudaMalloc size=%zu\n", size);
    if (!g_preprocess_injected && g_preprocess_fault) {
        const bool sparse = (preprocess_mode("sparse-recoverable") ||
                             preprocess_mode("sparse-fatal") ||
                             preprocess_mode("sparse-release-fatal")) &&
                            called_from("updateDefectPixels");
        const bool initialize = preprocess_mode("init-fatal") && called_from("initialize");
        if (sparse || initialize) {
            if (ptr) *ptr = nullptr;
            return inject_preprocess(preprocess_mode("sparse-fatal") || initialize,
                                     sparse ? "updateDefectPixels" : "initialize");
        }
    }
    const long n = ++g_seen;
    if (g_trace) std::fprintf(stderr, "[faultinject] cudaMalloc #%ld size=%zu\n", n, size);
    if (g_at > 0 && n == g_at) {
        if (ptr) *ptr = nullptr;
        const cudaError_t code = g_poison ? cudaErrorIllegalAddress
                                          : cudaErrorMemoryAllocation;
        std::fprintf(stderr, "[faultinject] INJECTING %s at cudaMalloc #%ld\n",
                     cudaGetErrorName(code), n);
        return code;
    }
    const cudaError_t result = __real_cudaMalloc(ptr, size);
    if (result == cudaSuccess) g_owned.insert(*ptr);
    return result;
}

extern "C" cudaError_t __wrap_cudaFree(void *ptr) {
    init_once();
    if (ptr && !g_owned.count(ptr)) ++g_stale;
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) g_owned.erase(ptr);
    if (result == cudaSuccess && g_preprocess_injected &&
        !g_preprocess_release_injected && preprocess_mode("sparse-release-fatal") &&
        called_from("CudaMovieSession")) {
        // The real free ran and ownership accounting is updated. Only its status
        // is replaced; this does not leave a real leak or poison the device.
        g_preprocess_release_injected = true;
        std::fprintf(stderr, "[preprocessfault] injected cudaErrorIllegalAddress after real session cudaFree\n");
        return cudaErrorIllegalAddress;
    }
    // Reconstruction cleanup: the real free ran; only its returned status is
    // replaced, after the helper's D2H copy has already succeeded.
    if (result == cudaSuccess && !g_preprocess_injected) {
        const char *stage = nullptr;
        if (preprocess_mode("unweighted-release-fatal") && called_from("cudaRealSpaceInterpolationDevice"))
            stage = "cudaRealSpaceInterpolationDevice";
        else if (preprocess_mode("dw-release-fatal") && called_from("cudaDoseWeightAndInterpolateDevice"))
            stage = "cudaDoseWeightAndInterpolateDevice";
        if (stage) return inject_preprocess(true, stage);
    }
    return result;
}

extern "C" cudaError_t __real_cudaDeviceSynchronize(void);
extern "C" cudaError_t __wrap_cudaDeviceSynchronize(void) {
    init_once();
    const cudaError_t result = __real_cudaDeviceSynchronize();
    if (result == cudaSuccess && !g_preprocess_injected &&
        preprocess_mode("forward-fatal") && called_from("computeGlobalForwardFFT"))
        return inject_preprocess(true, "computeGlobalForwardFFT");
    return result;
}


extern "C" cudaError_t __real_cudaMemcpy(void *dst, const void *src, size_t count,
                                         cudaMemcpyKind kind);
extern "C" cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t count,
                                         cudaMemcpyKind kind) {
    init_once();
    if (!g_preprocess_injected && preprocess_mode("float-gain-fatal") &&
        called_from("applyGainDefectsAndSum"))
        return inject_preprocess(true, "applyGainDefectsAndSum");
    return __real_cudaMemcpy(dst, src, count, kind);
}
