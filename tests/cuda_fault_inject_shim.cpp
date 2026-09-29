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
//
// Issue #85 lane C controls, confined to this test-only binary:
//   MC_U16_FAULT        alloc | h2d | kernel-recoverable | kernel-fatal
//   MC_U16_STAGE_BYTES  exact uint16 frame allocation size to distinguish it from
//                       the session's float buffers (derived from the input TIFF)
// These return controlled error codes at the actual U16 allocation, upload, or
// post-launch status-check boundary. They do not simulate a genuinely poisoned GPU.

#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>

extern "C" cudaError_t __real_cudaMalloc(void **ptr, size_t size);
extern "C" cudaError_t __real_cudaFree(void *ptr);

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
bool  g_poison = false;
bool  g_trace = false;
bool  g_init = false;
const char *g_u16_fault = nullptr;
size_t g_u16_stage_bytes = 0;
void *g_u16_stage_ptr = nullptr;
bool g_u16_fault_injected = false;
bool g_u16_stage_upload_seen = false;

void init_once() {
    if (g_init) return;
    g_init = true;
    std::atexit(report_owned);
    const char *o = std::getenv("MC_FAULT_ORDINAL");
    g_at = o ? std::atol(o) : 0;
    const char *c = std::getenv("MC_FAULT_CODE");
    g_poison = (c && std::strcmp(c, "poison") == 0);
    g_trace = std::getenv("MC_FAULT_TRACE") != nullptr;
    g_u16_fault = std::getenv("MC_U16_FAULT");
    const char *stage = std::getenv("MC_U16_STAGE_BYTES");
    if (stage) g_u16_stage_bytes = (size_t)std::strtoull(stage, nullptr, 10);
}

bool is_u16_fault(const char *name) {
    return g_u16_fault && std::strcmp(g_u16_fault, name) == 0;
}
} // namespace

extern "C" cudaError_t __wrap_cudaMalloc(void **ptr, size_t size) {
    init_once();
    if (g_u16_stage_bytes && size == g_u16_stage_bytes) {
        std::fprintf(stderr, "[u16fault] stage-alloc-request size=%zu\n", size);
        if (!g_u16_fault_injected && is_u16_fault("alloc")) {
            g_u16_fault_injected = true;
            if (ptr) *ptr = nullptr;
            std::fprintf(stderr, "[u16fault] injected stage allocation failure\n");
            return cudaErrorMemoryAllocation;
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
    if (result == cudaSuccess && g_u16_stage_bytes && size == g_u16_stage_bytes) {
        g_u16_stage_ptr = ptr ? *ptr : nullptr;
        std::fprintf(stderr, "[u16fault] stage-alloc-ok ptr=%p size=%zu\n",
                     g_u16_stage_ptr, size);
    }
    return result;
}

extern "C" cudaError_t __real_cudaMemcpy(void *dst, const void *src, size_t count,
                                         cudaMemcpyKind kind);
extern "C" cudaError_t __real_cudaGetLastError(void);

extern "C" cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t count,
                                         cudaMemcpyKind kind) {
    init_once();
    const bool stage_upload = g_u16_stage_ptr && dst == g_u16_stage_ptr &&
                              kind == cudaMemcpyHostToDevice &&
                              count == g_u16_stage_bytes;
    if (stage_upload && !g_u16_fault_injected && is_u16_fault("h2d")) {
        g_u16_fault_injected = true;
        std::fprintf(stderr, "[u16fault] injected stage H2D failure size=%zu\n", count);
        return cudaErrorMemoryAllocation;
    }
    const cudaError_t result = __real_cudaMemcpy(dst, src, count, kind);
    if (stage_upload && result == cudaSuccess) {
        g_u16_stage_upload_seen = true;
        std::fprintf(stderr, "[u16fault] stage-h2d-ok size=%zu\n", count);
    }
    return result;
}

extern "C" cudaError_t __wrap_cudaFree(void *ptr) {
    init_once();
    if (ptr && !g_owned.count(ptr)) ++g_stale;
    const bool stage_free = ptr && ptr == g_u16_stage_ptr;
    if (stage_free) std::fprintf(stderr, "[u16fault] stage-free-request ptr=%p\n", ptr);
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) g_owned.erase(ptr);
    if (stage_free && result == cudaSuccess) {
        std::fprintf(stderr, "[u16fault] stage-free-ok ptr=%p\n", ptr);
        g_u16_stage_ptr = nullptr;
    }
    return result;
}

extern "C" cudaError_t __wrap_cudaGetLastError(void) {
    init_once();
    if (g_u16_stage_upload_seen && !g_u16_fault_injected &&
        (is_u16_fault("kernel-recoverable") || is_u16_fault("kernel-fatal"))) {
        g_u16_fault_injected = true;
        g_u16_stage_upload_seen = false;
        const bool fatal = is_u16_fault("kernel-fatal");
        const cudaError_t code = fatal ? cudaErrorIllegalAddress
                                       : cudaErrorInvalidConfiguration;
        std::fprintf(stderr, "[u16fault] injected post-launch conversion status: %s\n",
                     cudaGetErrorName(code));
        return code;
    }
    return __real_cudaGetLastError();
}
