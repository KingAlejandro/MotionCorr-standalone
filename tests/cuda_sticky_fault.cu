// Test-only genuine context fault (#213). No fabricated CUDA return values.
// The existing retry-caller shim reaches downloadPatchSpectra deterministically.
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>

namespace {
bool faulted = false;
bool launching_fault = false;

bool inRetryPreparation() {
    void *frames[16];
    const int n = backtrace(frames, 16);
    for (int i = 1; i < n; ++i) {
        Dl_info info{};
        if (dladdr(frames[i], &info) && info.dli_sname &&
            std::strstr(info.dli_sname, "downloadPatchSpectra")) return true;
    }
    return false;
}

__global__ void illegalWrite(volatile int *address) { *address = 213; }
}

extern "C" cudaError_t __real_cudaMalloc(void **, size_t);
extern "C" cudaError_t __real_cudaLaunchKernel(const void *, dim3, dim3, void **,
                                               size_t, cudaStream_t);

extern "C" cudaError_t __wrap_cudaLaunchKernel(const void *function, dim3 grid,
        dim3 block, void **args, size_t shared, cudaStream_t stream) {
    if (faulted && !launching_fault)
        std::fprintf(stderr, "[sticky] PRODUCT_KERNEL_AFTER_FAULT\n");
    return __real_cudaLaunchKernel(function, grid, block, args, shared, stream);
}

extern "C" cudaError_t __wrap_cudaMalloc(void **pointer, size_t bytes) {
    const char *enabled = std::getenv("MC_STICKY_FAULT");
    const bool trigger = !faulted && enabled && std::strcmp(enabled, "1") == 0 &&
                         inRetryPreparation();
    if (trigger) {
        std::fprintf(stderr, "[sticky] launch illegal write in downloadPatchSpectra\n");
        launching_fault = true;
        illegalWrite<<<1, 1>>>(nullptr);
        launching_fault = false;
        const cudaError_t completion = cudaDeviceSynchronize();
        std::fprintf(stderr, "[sticky] fault completion=%d (%s)\n",
                     int(completion), cudaGetErrorString(completion));
        faulted = true;
        // Deliberately clear the host last-error slot. The next real product
        // operation must still observe the broken context, independently of it.
        (void)cudaGetLastError();
    }
    const cudaError_t result = __real_cudaMalloc(pointer, bytes);
    if (trigger)
        std::fprintf(stderr, "[sticky] product cudaMalloc=%d (%s), unchanged\n",
                     int(result), cudaGetErrorString(result));
    return result;
}
