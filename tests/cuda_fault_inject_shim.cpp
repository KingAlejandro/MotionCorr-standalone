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

void init_once() {
    if (g_init) return;
    g_init = true;
    std::atexit(report_owned);
    const char *o = std::getenv("MC_FAULT_ORDINAL");
    g_at = o ? std::atol(o) : 0;
    const char *c = std::getenv("MC_FAULT_CODE");
    g_poison = (c && std::strcmp(c, "poison") == 0);
    g_trace = std::getenv("MC_FAULT_TRACE") != nullptr;
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
    if (ptr && !g_owned.count(ptr)) ++g_stale;
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) g_owned.erase(ptr);
    return result;
}
