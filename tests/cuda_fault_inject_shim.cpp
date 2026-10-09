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
#include <tiffio.h>
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
const char *g_u16_fault = nullptr;
size_t g_u16_stage_bytes = 0;
void *g_u16_stage_ptr = nullptr;
bool g_u16_fault_injected = false;
bool g_u16_stage_upload_seen = false;
const char *g_preprocess_fault = nullptr;
bool g_preprocess_injected = false;
bool g_preprocess_release_injected = false;
bool g_workspace_cleanup_injected = false;

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
    g_u16_fault = std::getenv("MC_U16_FAULT");
    const char *stage = std::getenv("MC_U16_STAGE_BYTES");
    if (stage) g_u16_stage_bytes = (size_t)std::strtoull(stage, nullptr, 10);
    g_preprocess_fault = std::getenv("MC_PREPROCESS_FAULT");
    const char *count_ordinal = std::getenv("MC_COUNT_FAULT_ORDINAL");
    g_count_at = count_ordinal ? std::atol(count_ordinal) : 0;
    const char *count_code = std::getenv("MC_COUNT_FAULT_CODE");
    if (count_code && std::strcmp(count_code, "poison") == 0)
        g_count_error = cudaErrorIllegalAddress;
    else if (count_code && std::strcmp(count_code, "recoverable") == 0)
        g_count_error = cudaErrorInitializationError;
}

long g_tiff_open_seen = 0;

bool is_u16_fault(const char *name) {
    return g_u16_fault && std::strcmp(g_u16_fault, name) == 0;
}
} // namespace

extern "C" cudaError_t __real_cudaStreamSynchronize(cudaStream_t);
extern "C" cudaError_t __wrap_cudaStreamSynchronize(cudaStream_t s) {
    init_once();
    const cudaError_t result = __real_cudaStreamSynchronize(s);
    // The ingest scratch scope synchronises and destroys its stream in a
    // destructor, i.e. AFTER ingestCompressedTiffStrips has already chosen
    // true. Failing here is the only way to reach the case where the decode
    // reported success and the teardown did not.
    if (result == cudaSuccess && !g_preprocess_injected &&
        preprocess_mode("ingest-teardown-fatal") && called_from("endIngestScratch"))
        return inject_preprocess(false, "endIngestScratch");
    return result;
}

extern "C" TIFF *__real_TIFFOpen(const char *, const char *);
extern "C" TIFF *__wrap_TIFFOpen(const char *name, const char *mode) {
    init_once();
    // Fail every TIFFOpen after the first, so a multi-threaded ingest has some
    // threads with a handle and some without. That is the state that used to
    // deadlock the OpenMP team, because the worksharing region sat inside the
    // else arm and the threads without a handle never encountered it.
    if (preprocess_mode("tiff-open-partial") && called_from("ingestCompressedTiffStrips")) {
        const long n = ++g_tiff_open_seen;
        if (n > 1) {
            std::fprintf(stderr, "[preprocessfault] refused TIFFOpen #%ld inside the ingest\n", n);
            return nullptr;
        }
    }
    return __real_TIFFOpen(name, mode);
}

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
        // Forces device_prep_ok == false, which is the only way into the patch
        // retry arm. On the nvCOMP arm that arm has to fetch the movie back from
        // the device first; before the fix it read zero-size host frames.
        if (!g_preprocess_injected && preprocess_mode("patch-prep-recoverable") &&
            called_from("preparePatchInVram"))
            return inject_preprocess(false, "preparePatchInVram");
        // --fft_size_policy fast fallbacks (docs/fft_size_policy.md): a recoverable
        // dose-weighting scratch failure sends the padded spectra to the CPU.
        if (!g_preprocess_injected && preprocess_mode("dw-alloc-recoverable") &&
            called_from("cudaDoseWeightAndInterpolateDevice")) {
            if (ptr) *ptr = nullptr;
            return inject_preprocess(false, "cudaDoseWeightAndInterpolateDevice");
        }
        if (sparse || initialize) {
            if (ptr) *ptr = nullptr;
            return inject_preprocess(preprocess_mode("sparse-fatal") || initialize,
                                     sparse ? "updateDefectPixels" : "initialize");
        }
    }
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
    if (!g_preprocess_injected && preprocess_mode("float-gain-fatal") &&
        called_from("applyGainDefectsAndSum") && !called_from("applyGainDefectsAndSumU16"))
        return inject_preprocess(true, "applyGainDefectsAndSum");
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
    // Test-only returned status after an actual free at the movie-owned
    // workspace boundary. Ephemeral global calls are deliberately excluded.
    const char *workspace_fault = std::getenv("MC_WORKSPACE_CLEANUP_FAULT");
    if (result == cudaSuccess && ptr && workspace_fault &&
        !g_workspace_cleanup_injected && called_from("PatchAlignmentWorkspace") &&
        !called_from("cudaAlignPatchDevice")) {
        g_workspace_cleanup_injected = true;
        (void)cudaGetLastError();
        const cudaError_t code = std::strcmp(workspace_fault, "fatal") == 0
            ? cudaErrorIllegalAddress : cudaErrorMemoryAllocation;
        std::fprintf(stderr, "[workspacefault] after real movie-workspace cudaFree: %s; slot cleared\n",
                     cudaGetErrorName(code));
        return code;
    }
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
    // The padded inverse checks its crop launch here; a recoverable status sends
    // the padded spectra to the CPU inverse (--fft_size_policy fast only).
    if (!g_preprocess_injected && preprocess_mode("ifft-crop-recoverable") &&
        called_from("computeGlobalInverseFFT")) {
        g_preprocess_injected = true;
        (void)__real_cudaGetLastError();
        std::fprintf(stderr, "[preprocessfault] injected cudaErrorInvalidConfiguration at "
                     "computeGlobalInverseFFT; pending slot cleared\n");
        return cudaErrorInvalidConfiguration;
    }
    return __real_cudaGetLastError();
}
