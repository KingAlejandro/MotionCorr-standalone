// C1 iteration i8 qualification tooling (NOT production source, not registered in CMake): a genuine CUDA context fault
// inside the nvCOMP device-ingest path. No fabricated CUDA return values.
//
// The runner's nvCOMP ingest launches one gain/sum kernel (16x16 blocks, from ingestCompressedTiffStrips) per chunk, after that chunk's
// descriptors were verified. This interposer counts those launches (same detection as tests/cuda_nvcomp_acceptance_shim.cpp). When
// MC_INGEST_STICKY_FAULT=1 and the process-wide ingest launch index equals MC_INGEST_STICKY_LAUNCH (default 1: the second chunk, so chunk 0
// has already been converted), it first launches a kernel that writes through a null pointer, synchronizes (native cudaErrorIllegalAddress,
// 700, usually an Xid 31 in the kernel log), clears the host last-error slot and then performs the real ingest launch, which must observe the
// broken context on its own. Nothing else is altered: no return code is replaced and the product code is the tested binary's core library.
//
// Evidence lines (stderr): per ingest gain launch "[ingeststicky] gain-launch index=N"; on the faulting launch "launch illegal write ...",
// "fault completion=700 ...", "product launch result=..."; any later wrapped launch attempt prints "[ingeststicky] PRODUCT_KERNEL_AFTER_FAULT".
#include <cuda_runtime.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>
#include <mutex>

extern "C" cudaError_t __real_cudaLaunchKernel(const void *, dim3, dim3, void **, size_t, cudaStream_t);

namespace {
std::atomic<unsigned> gain_launches{0};
std::atomic<bool> faulted{false};
std::atomic<bool> reported{false};
thread_local bool inside_fault = false;
std::mutex gate;

__global__ void illegalWrite(volatile int *address) { *address = 213; }

bool from_ingest() {
    void *frames[24];
    const int n = backtrace(frames, 24);
    for (int i = 1; i < n; ++i) {
        Dl_info info{};
        if (dladdr(frames[i], &info) && info.dli_sname &&
            std::strstr(info.dli_sname, "ingestCompressedTiffStrips")) return true;
    }
    return false;
}
bool fault_enabled() {
    const char *v = std::getenv("MC_INGEST_STICKY_FAULT");
    return v && std::strcmp(v, "1") == 0;
}
unsigned target_launch() {
    const char *v = std::getenv("MC_INGEST_STICKY_LAUNCH");
    return v ? (unsigned)std::strtoul(v, nullptr, 10) : 1u;
}
void report() {
    std::fprintf(stderr, "[ingeststicky] exit gain-launches=%u faulted=%d\n", gain_launches.load(), faulted.load() ? 1 : 0);
}
}

extern "C" cudaError_t __wrap_cudaLaunchKernel(const void *function, dim3 grid, dim3 block,
                                              void **args, size_t shared, cudaStream_t stream) {
    if (inside_fault) return __real_cudaLaunchKernel(function, grid, block, args, shared, stream);
    if (!reported.exchange(true)) std::atexit(report);
    if (faulted.load()) std::fprintf(stderr, "[ingeststicky] PRODUCT_KERNEL_AFTER_FAULT\n");
    bool trigger = false;
    if (block.x == 16 && block.y == 16 && block.z == 1 && from_ingest()) {
        const unsigned index = gain_launches.fetch_add(1);
        std::fprintf(stderr, "[ingeststicky] gain-launch index=%u\n", index);
        if (fault_enabled() && index == target_launch()) {
            std::lock_guard<std::mutex> lock(gate);
            trigger = !faulted.load();
            if (trigger) {
                std::fprintf(stderr, "[ingeststicky] launch illegal write before ingest gain launch %u\n", index);
                inside_fault = true;
                illegalWrite<<<1, 1>>>(nullptr);
                inside_fault = false;
                const cudaError_t completion = cudaDeviceSynchronize();
                std::fprintf(stderr, "[ingeststicky] fault completion=%d (%s)\n",
                             int(completion), cudaGetErrorString(completion));
                faulted = true;
                // Deliberately clear the host last-error slot: the real ingest launch below must observe the broken context itself.
                (void)cudaGetLastError();
            }
        }
    }
    const cudaError_t result = __real_cudaLaunchKernel(function, grid, block, args, shared, stream);
    if (trigger)
        std::fprintf(stderr, "[ingeststicky] product launch result=%d (%s), unchanged\n",
                     int(result), cudaGetErrorString(result));
    return result;
}
