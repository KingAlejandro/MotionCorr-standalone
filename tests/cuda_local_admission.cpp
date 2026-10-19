// #226 D2: query the real cuFFT workspace on a small geometry, then exercise
// the exact admission boundary without allocating most of a GPU as a balloon.
#include "src/acc/cuda/cuda_movie_session.h"
#include <cuda_runtime.h>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace { bool constrained = false; size_t available = 0; }
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
        const size_t retry = (size_t)24 * 102 * (102 / 2 + 1) * sizeof(cufftComplex);
        for (const size_t free : {retry - 1, retry, retry + 1}) {
            available = free;
            if (session.admitPatchRetry(102, 102, 24) != (free >= retry))
                throw std::runtime_error("incorrect conditional retry admission boundary");
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
