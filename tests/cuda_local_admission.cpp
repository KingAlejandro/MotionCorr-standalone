// #226 D2: query the real cuFFT workspace on a small geometry, then exercise
// the exact admission boundary without allocating most of a GPU as a balloon.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_scoped_resources.h"
#include <cuda_runtime.h>
#include <climits>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>

namespace { bool constrained = false; size_t available = 0; }

// Independent allocation census and actual cuFFT query for the retry dispatched
// through cudaAlignPatch. Do not derive the expectation from the production helper
// or its diagnostic: either would let the old spectrum-only bound pass this test.
size_t retryBytes(int pw, int ph, int groups, RFLOAT scaled_B, RFLOAT downsample) {
    int cw = 0, ch = 0;
    patchSpectrumWindow(pw, ph, scaled_B, downsample, cw, ch);
    mc_cuda::ScopedCufftPlan owner;
    cufftHandle plan = 0;
    if (cufftCreate(&plan) != CUFFT_SUCCESS) throw std::runtime_error("test plan creation failed");
    owner.take(plan);
    if (cufftSetAutoAllocation(plan, 0) != CUFFT_SUCCESS)
        throw std::runtime_error("test plan auto-allocation disable failed");
    int n[2] = {ch, cw};
    size_t work = 0;
    if (cufftMakePlanMany(plan, 2, n, nullptr, 1, ch * (cw / 2 + 1),
            nullptr, 1, ch * cw, CUFFT_C2R, groups, &work) != CUFFT_SUCCESS ||
        cufftGetSize(plan, &work) != CUFFT_SUCCESS)
        throw std::runtime_error("test plan sizing failed");
    if (owner.releaseAll() != CUFFT_SUCCESS) throw std::runtime_error("test plan release failed");
    const size_t window = (size_t)ch * (cw / 2 + 1);
    return (size_t)groups * ph * (pw / 2 + 1) * sizeof(cufftComplex) +
        window * sizeof(cufftComplex) + window * sizeof(float) +
        groups * window * sizeof(cufftComplex) +
        (size_t)groups * ch * cw * sizeof(float) + 4 * groups * sizeof(float) + work;
}
extern "C" cudaError_t __real_cudaMemGetInfo(size_t*, size_t*);
extern "C" cudaError_t __wrap_cudaMemGetInfo(size_t *free, size_t *total) {
    const auto err = __real_cudaMemGetInfo(free, total);
    if (err == cudaSuccess && constrained) *free = available;
    return err;
}
int main() {
    try {
        std::ostringstream log;
        CudaMovieSession session(512, 512, 24, 0, log);
        if (!session.initialize()) throw std::runtime_error("session initialization failed");
        constrained = true;
        if (session.admitLocalAlignment(102, 102, 24, 150, 0))
            throw std::runtime_error("zero headroom admitted local alignment");
        const std::string text = log.str();
        const auto pos = text.find("requires ");
        if (pos == std::string::npos) throw std::runtime_error("missing admission diagnostic");
        const size_t required = std::stoull(text.substr(pos + 9));
        if (!required) throw std::runtime_error("empty workspace requirement");
        for (const size_t free : {required - 1, required, required + 1}) {
            available = free;
            if (session.admitLocalAlignment(102, 102, 24, 150, 0) != (free >= required))
                throw std::runtime_error("incorrect admission boundary");
        }
        struct Geometry { int pw, ph, groups; RFLOAT b, downsample; };
        for (const Geometry geo : {Geometry{102, 102, 24, 150, 0},
                                  Geometry{408, 324, 7, 150, 0.5},
                                  Geometry{408, 324, 7, 40, 0}}) {
            const size_t spectrum = (size_t)geo.groups * geo.ph * (geo.pw / 2 + 1) * sizeof(cufftComplex);
            const size_t retry = retryBytes(geo.pw, geo.ph, geo.groups, geo.b, geo.downsample);
            for (const size_t free : {spectrum - 1, spectrum, spectrum + 1,
                                      spectrum + (retry - spectrum) / 2,
                                      retry - 1, retry, retry + 1}) {
                available = free;
                if (session.admitPatchRetry(geo.pw, geo.ph, geo.groups, geo.b, geo.downsample)
                    != (free >= retry))
                    throw std::runtime_error("incorrect complete retry admission boundary");
            }
        }
        available = std::numeric_limits<size_t>::max();
        for (const Geometry geo : {Geometry{0, 102, 24, 150, 0},
                                  Geometry{102, 102, -1, 150, 0},
                                  Geometry{65536, 65536, 1, 150, 0},
                                  Geometry{46340, 46340, INT_MAX, 150, 1}}) {
            if (session.admitPatchRetry(geo.pw, geo.ph, geo.groups, geo.b, geo.downsample))
                throw std::runtime_error("invalid/overflowing retry size admitted");
        }
        constrained = false;
        session.release();
        if (cudaGetLastError() != cudaSuccess) throw std::runtime_error("pending CUDA error");
        std::cout << "PASS: local workspace boundary " << required << " bytes\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    }
}
