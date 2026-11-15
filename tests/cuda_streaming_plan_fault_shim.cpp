// #226 D3 test-only cuFFT admission/cleanup controls. Linked only into the named
// test executable. Real successful handles are destroyed exactly once; simulated
// CUDA statuses never poison a device. No impossible allocations or kernels here.
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

extern "C" cufftResult __real_cufftCreate(cufftHandle*);
extern "C" cufftResult __real_cufftSetAutoAllocation(cufftHandle, int);
extern "C" cufftResult __real_cufftMakePlanMany(cufftHandle, int, int*, int*, int,
                                             int, int*, int, int, cufftType, int, size_t*);
extern "C" cufftResult __real_cufftDestroy(cufftHandle);
extern "C" cudaError_t __real_cudaPeekAtLastError();

namespace {
const char *mode = nullptr;
bool selected = false, active = false;
cufftHandle owned = 0;
int creates = 0, destroys = 0;
cudaError_t pending = cudaSuccess;

bool is(const char *value) { return mode && std::strcmp(mode, value) == 0; }
bool admission_caller(void *caller) {
    // Direct runner call distinguishes admission from resident/global FFT plans.
    Dl_info info = {};
    return dladdr(caller, &info) && info.dli_sname &&
           std::strstr(info.dli_sname, "executeOwnMotionCorrection");
}
void summary() {
    std::fprintf(stderr, "[streamplan] creates=%d destroys=%d owned=%d\n",
                 creates, destroys, active ? 1 : 0);
}
cufftResult inject(const char *boundary, cufftResult result, bool fatal) {
    pending = fatal ? cudaErrorIllegalAddress : cudaSuccess;
    std::fprintf(stderr, "[streamplan] %s result=%d simulated-pending=%s\n",
                 boundary, int(result), cudaGetErrorName(pending));
    return result;
}
} // namespace

extern "C" cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    mode = std::getenv("MC_STREAMING_PLAN_FAULT");
    if (!selected && mode && admission_caller(__builtin_return_address(0))) {
        selected = true;
        std::atexit(summary);
        if (is("create-alloc")) return inject("create", CUFFT_ALLOC_FAILED, false);
        if (is("create-error")) return inject("create", CUFFT_INVALID_VALUE, false);
        if (is("create-fatal")) return inject("create", CUFFT_ALLOC_FAILED, true);
        const cufftResult result = __real_cufftCreate(plan);
        if (result == CUFFT_SUCCESS) {
            active = true; owned = *plan; ++creates;
            std::fprintf(stderr, "[streamplan] create-real-ok\n");
        }
        return result;
    }
    return __real_cufftCreate(plan);
}
extern "C" cufftResult __wrap_cufftSetAutoAllocation(cufftHandle plan, int value) {
    if (active && plan == owned) {
        if (is("auto-alloc")) return inject("auto", CUFFT_ALLOC_FAILED, false);
        if (is("auto-error")) return inject("auto", CUFFT_INVALID_VALUE, false);
        if (is("auto-fatal-cleanup-alloc"))
            return inject("auto", CUFFT_ALLOC_FAILED, true);
    }
    return __real_cufftSetAutoAllocation(plan, value);
}
extern "C" cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
        int *inembed, int istride, int idist, int *onembed, int ostride, int odist,
        cufftType type, int batch, size_t *work) {
    if (active && plan == owned) {
        std::fprintf(stderr, "[streamplan] make-enter rank=%d batch=%d\n", rank, batch);
        if (is("make-alloc")) return inject("make", CUFFT_ALLOC_FAILED, false);
        if (is("make-error")) return inject("make", CUFFT_INVALID_VALUE, false);
        if (is("make-fatal-cleanup-success") || is("make-fatal-cleanup-alloc"))
            return inject("make", CUFFT_ALLOC_FAILED, true);
        if (is("make-error-cleanup-alloc"))
            return inject("make", CUFFT_INVALID_VALUE, false);
        if (is("make-alloc-cleanup-fatal"))
            return inject("make", CUFFT_ALLOC_FAILED, false);
    }
    const cufftResult result = __real_cufftMakePlanMany(plan, rank, n, inembed,
        istride, idist, onembed, ostride, odist, type, batch, work);
    if (active && plan == owned && result == CUFFT_SUCCESS)
        std::fprintf(stderr, "[streamplan] make-real-ok work=%zu\n", *work);
    return result;
}
extern "C" cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const cufftResult result = __real_cufftDestroy(plan);
    if (active && plan == owned) {
        ++destroys; active = false;
        std::fprintf(stderr, "[streamplan] destroy-real result=%d; earlier-simulated-pending=%s\n",
                     int(result), cudaGetErrorName(pending));
        // Model a library cleanup that consumes/replaces the thread's earlier
        // status. The caller must latch it BEFORE calling the library again.
        pending = cudaSuccess;
        if (result != CUFFT_SUCCESS) return result;
        if (is("cleanup-alloc") || is("make-fatal-cleanup-alloc") ||
            is("auto-fatal-cleanup-alloc") || is("make-error-cleanup-alloc"))
            return inject("cleanup", CUFFT_ALLOC_FAILED, false);
        if (is("cleanup-error")) return inject("cleanup", CUFFT_INTERNAL_ERROR, false);
        if (is("cleanup-fatal") || is("make-alloc-cleanup-fatal"))
            return inject("cleanup", CUFFT_ALLOC_FAILED, true);
    }
    return result;
}
extern "C" cudaError_t __wrap_cudaPeekAtLastError() {
    const cudaError_t real = __real_cudaPeekAtLastError();
    if (real != cudaSuccess) return real; // Never obscure an actual hardware error.
    if (pending != cudaSuccess) {
        const cudaError_t simulated = pending;
        // Match cudaPeekAtLastError: observation does not consume the slot.
        std::fprintf(stderr, "[streamplan] observed simulated %s (peek)\n",
                     cudaGetErrorName(simulated));
        return simulated;
    }
    return real;
}
