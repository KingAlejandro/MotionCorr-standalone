// CUDA hardware control: link with --wrap=cudaMalloc, --wrap=cudaFree and
// --wrap=cudaMemcpy. Inject upload failures into the real production wrappers.
#include "src/acc/cuda/cuda_realspace_dw.h"
#include <cuda_runtime.h>
#include <iostream>
#include <set>
#include <sstream>
#include <vector>

namespace {
bool track_allocations = false;
int fail_upload = 0;
int uploads_seen = 0;
std::set<void *> outstanding;
}

extern "C" cudaError_t __real_cudaMalloc(void **ptr, size_t size);
extern "C" cudaError_t __real_cudaFree(void *ptr);
extern "C" cudaError_t __real_cudaMemcpy(void *dst, const void *src,
                                        size_t size, cudaMemcpyKind kind);

extern "C" cudaError_t __wrap_cudaMalloc(void **ptr, size_t size) {
    const cudaError_t result = __real_cudaMalloc(ptr, size);
    if (track_allocations && result == cudaSuccess) outstanding.insert(*ptr);
    return result;
}

extern "C" cudaError_t __wrap_cudaFree(void *ptr) {
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) outstanding.erase(ptr);
    return result;
}

extern "C" cudaError_t __wrap_cudaMemcpy(void *dst, const void *src,
                                        size_t size, cudaMemcpyKind kind) {
    if (track_allocations && kind == cudaMemcpyHostToDevice &&
        ++uploads_seen == fail_upload)
        return cudaErrorInvalidValue;
    return __real_cudaMemcpy(dst, src, size, kind);
}

int main() {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "CUDA device 0 is required for this control\n";
        return 1;
    }

    constexpr int nx = 8, ny = 8, nframes = 3;
    std::vector<Image<float>> real_frames(nframes);
    std::vector<MultidimArray<fComplex>> fourier_frames(nframes);
    for (int i = 0; i < nframes; ++i) {
        real_frames[i]().initZeros(ny, nx);
        fourier_frames[i].initZeros(ny, nx / 2 + 1);
    }
    Image<float> sum;
    sum().initZeros(ny, nx);
    const std::vector<RFLOAT> doses(nframes, 1.0);

    int failures = 0;
    for (bool dose_weighted : {false, true}) {
        for (int upload = 1; upload <= nframes; ++upload) {
            fail_upload = upload;
            uploads_seen = 0;
            track_allocations = true;
            std::ostringstream log;
            const bool result = dose_weighted
                ? cudaDoseWeightAndInterpolate(fourier_frames, sum, doses,
                                                1.0, nullptr, 0, log)
                : cudaRealSpaceInterpolation(sum, nullptr, nullptr, real_frames,
                                              nullptr, 0, log);
            track_allocations = false;
            if (result || uploads_seen != upload || !outstanding.empty() ||
                log.str().find("CUDA Error") == std::string::npos) {
                std::cerr << "Failed " << (dose_weighted ? "DW" : "unweighted")
                          << " upload " << upload << ": result=" << result
                          << ", observed uploads=" << uploads_seen
                          << ", leaked allocations=" << outstanding.size() << '\n';
                ++failures;
            }
            // Clean up a failing baseline so every injection is evaluated.
            for (void *ptr : outstanding) __real_cudaFree(ptr);
            outstanding.clear();
        }
    }
    if (failures) return 1;
    std::cout << "All six failed uploads returned false and released their allocations\n";
    return 0;
}
