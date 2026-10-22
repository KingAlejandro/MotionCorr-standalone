// SPDX-License-Identifier: GPL-2.0-or-later
// Fake CUDA: checks shim ordering and readback rejection without any GPU claim.
#include "cuda_runtime.h"
#include <tiffio.h>
#include <unistd.h>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" TIFF *__wrap_TIFFOpen(const char *, const char *);
extern "C" void __wrap_TIFFClose(TIFF *);
extern "C" ssize_t __wrap_pread(int, void *, size_t, off_t);
extern "C" ssize_t __wrap___pread_chk(int, void *, size_t, off_t, size_t);
extern "C" cudaError_t __wrap_cudaLaunchKernel(const void *, dim3, dim3, void **, size_t, cudaStream_t);
extern "C" TIFF *__real_TIFFOpen(const char *name, const char *mode) { return TIFFOpen(name, mode); }
extern "C" void __real_TIFFClose(TIFF *t) { TIFFClose(t); }
extern "C" ssize_t __real_pread(int fd, void *p, size_t n, off_t off) { return pread(fd, p, n, off); }
extern "C" ssize_t __real___pread_chk(int fd, void *p, size_t n, off_t off, size_t cap) {
    if (n > cap) std::abort();
    return pread(fd, p, n, off);
}
namespace {
int kernel_token, other_token;
const char *mode;
constexpr size_t pixels = 48 * 40;
std::vector<float> oracle(3 * pixels), frames(2 * pixels, -1), sum(pixels, -1);
bool pending = false;
}
extern "C" const void *mc_tiff_identity_conversion_kernel() { return &kernel_token; }
extern "C" cudaError_t __real_cudaLaunchKernel(const void *, dim3, dim3, void **, size_t, cudaStream_t) {
    if (!std::strcmp(mode, "launch-error")) return cudaErrorUnknown;
    pending = true;
    return cudaSuccess;
}
cudaError_t cudaStreamSynchronize(cudaStream_t) {
    if (!std::strcmp(mode, "sync-error")) return cudaErrorUnknown;
    if (pending && std::strcmp(mode, "no-consumption")) {
        std::copy_n(oracle.data(), 2 * pixels, frames.data());
        std::copy_n(oracle.data() + 2 * pixels, pixels, sum.data());
        if (!std::strcmp(mode, "frame-mismatch")) frames.back() += 1;
        if (!std::strcmp(mode, "sum-mismatch")) sum.back() += 1;
    }
    pending = false;
    return cudaSuccess;
}
cudaError_t cudaMemcpy(void *dst, const void *src, size_t n, cudaMemcpyKind) {
    if (!std::strcmp(mode, "copy-error")) return cudaErrorUnknown;
    std::memcpy(dst, src, n);
    return cudaSuccess;
}
// Export a caller matching the existing backtrace selector. No test override of
// from_ingest(): this exercises the same TIFFOpen/close selection as native.
extern "C" __attribute__((noinline)) int ingestCompressedTiffStrips_host_control(const char *movie) {
    TIFF *tags = __wrap_TIFFOpen(movie, "r");
    if (!tags) return 2;
    __wrap_TIFFClose(tags);
    TIFF *reader = __wrap_TIFFOpen(movie, "r");
    if (!reader) return 3;
    char byte;
    for (int i = 0; i < 4; ++i) {
        if (__wrap_pread(TIFFFileno(reader), &byte, 1, 0) != 1) return 4;
    }
    int nx = 48, ny = 40, f0 = 0, bf = 2;
    bool first = true, gain = false;
    float *fp = frames.data(), *sp = sum.data();
    void *args[] = {nullptr, &fp, &sp, nullptr, &nx, &ny, nullptr, &f0, &bf, &first, &gain};
    const void *kernel = !std::strcmp(mode, "wrong-kernel") ? &other_token : &kernel_token;
    cudaError_t result = __wrap_cudaLaunchKernel(kernel, dim3(3, 3), dim3(16, 16), args, 0, nullptr);
    if (result != cudaSuccess) return 5;
    if (!std::strcmp(mode, "fortified"))
        __wrap___pread_chk(TIFFFileno(reader), &byte, 1, 0, 1);
    else
        __wrap_pread(TIFFFileno(reader), &byte, 1, 0);
    __wrap_TIFFClose(reader);
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 3) return 1;
    mode = argv[2];
    FILE *f = std::fopen(std::getenv("MC_TIFF_CONVERSION_EXPECTED"), "rb");
    if (!f || std::fread(oracle.data(), sizeof(float), oracle.size(), f) != oracle.size()) return 6;
    std::fclose(f);
    return ingestCompressedTiffStrips_host_control(argv[1]);
}
