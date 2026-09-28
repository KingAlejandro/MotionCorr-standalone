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

#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" cudaError_t __real_cudaMalloc(void **ptr, size_t size);

namespace {
// Not atomic, deliberately. Every cudaMalloc on the path under test is issued from the
// main thread -- the OpenMP regions in the fallback do host-side FFT only -- so the
// ordinal is deterministic. The driver re-derives the ordinal on every run regardless,
// so any drift fails loudly rather than silently selecting the wrong call.
long  g_seen = 0;
long  g_at = -1;
bool  g_poison = false;
bool  g_trace = false;
bool  g_init = false;

void init_once() {
    if (g_init) return;
    g_init = true;
    const char *o = std::getenv("MC_FAULT_ORDINAL");
    g_at = o ? std::atol(o) : 0;
    const char *c = std::getenv("MC_FAULT_CODE");
    g_poison = (c && std::strcmp(c, "poison") == 0);
    g_trace = std::getenv("MC_FAULT_TRACE") != nullptr;
}
} // namespace

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
    return __real_cudaMalloc(ptr, size);
}
