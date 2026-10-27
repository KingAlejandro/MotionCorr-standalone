// Test-only file mutation at the actual two-pass nvCOMP caller. Healthy Deflate
// files only: this control makes no corrupt-decoder safety claim.
#include <tiffio.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <execinfo.h>
#include <string>
#ifdef MC_TIFF_IDENTITY_CONVERSION_PROBE
#include <cuda_runtime.h>
#include <vector>
extern "C" const void *mc_tiff_identity_conversion_kernel();
extern "C" cudaError_t __real_cudaLaunchKernel(const void *, dim3, dim3, void **,
                                              size_t, cudaStream_t);
#endif

namespace {
bool changed = false;
unsigned opens = 0;
int reader_fd = -1;
std::string movie;
#ifdef MC_TIFF_IDENTITY_CONVERSION_PROBE
unsigned span_reads = 0;
bool converted = false;
#endif
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
void mutate(const char *when) {
    const char *point = std::getenv("MC_TIFF_CHANGE_POINT");
    const char *mode = std::getenv("MC_TIFF_CHANGE_MODE");
    if (changed || !point || !mode || std::strcmp(point, when)) return;
    bool ok = false;
    if (!std::strcmp(mode, "grow")) {
        FILE *f = std::fopen(movie.c_str(), "ab");
        if (f) {
            ok = std::fwrite("identity-control", 1, 16, f) == 16;
            if (std::fclose(f)) ok = false;
        }
    } else if (!std::strcmp(mode, "replace")) {
        const char *replacement = std::getenv("MC_TIFF_REPLACEMENT");
        ok = replacement && std::rename(replacement, movie.c_str()) == 0;
    }
    if (!ok) { std::fprintf(stderr, "[tiffidentity] mutation failed\n"); std::abort(); }
    changed = true;
    std::fprintf(stderr, "[tiffidentity] changed mode=%s point=%s\n", mode, when);
}
void before_read(int fd) {
    if (fd != reader_fd) return;
    mutate("strip-read");
#ifdef MC_TIFF_IDENTITY_CONVERSION_PROBE
    const char *point = std::getenv("MC_TIFF_CHANGE_POINT");
    if (point && !std::strcmp(point, "later-strip-read") && converted && !changed) {
        // Two frames per chunk; the pipeline reads chunks 0 and 1 before
        // converting chunk 0. Its next span read is frame 4 of chunk 2.
        if (span_reads != 4) std::abort();
        std::fprintf(stderr, "[tiffidentity] later-strip-read index=4 converted=2\n");
        mutate("later-strip-read");
    }
    ++span_reads;
#endif
}
}
extern "C" TIFF *__real_TIFFOpen(const char *, const char *);
extern "C" void __real_TIFFClose(TIFF *);
extern "C" ssize_t __real_pread(int, void *, size_t, off_t);
// GCC's fortified CUDA host compilation redirects the actual span read here.
extern "C" ssize_t __real___pread_chk(int, void *, size_t, off_t, size_t);
extern "C" TIFF *__wrap_TIFFOpen(const char *name, const char *mode) {
    const bool ingest = from_ingest();
    if (ingest && opens++ == 0) movie = name;
    TIFF *t = __real_TIFFOpen(name, mode);
    // Mutate after a reader has opened: a rename leaves that handle on the old
    // inode, so checking the handle alone would miss the change of pathname.
    if (ingest && opens == 2 && t) {
        reader_fd = TIFFFileno(t);
        mutate("reader-open");
    }
    return t;
}
extern "C" void __wrap_TIFFClose(TIFF *t) {
    const bool tags = from_ingest() && opens == 1;
    __real_TIFFClose(t);
    if (tags) mutate("tag-close");
}
extern "C" ssize_t __wrap_pread(int fd, void *dst, size_t n, off_t offset) {
    before_read(fd);
    return __real_pread(fd, dst, n, offset);
}

extern "C" ssize_t __wrap___pread_chk(int fd, void *dst, size_t n, off_t offset, size_t capacity) {
    before_read(fd);
    return __real___pread_chk(fd, dst, n, offset, capacity);
}

#ifdef MC_TIFF_IDENTITY_CONVERSION_PROBE
// Compiled only into test executables. A launch count or callback alone does
// not prove consumption: drain the real conversion and read BOTH destinations.
extern "C" cudaError_t __wrap_cudaLaunchKernel(const void *func, dim3 grid, dim3 block,
                                              void **args, size_t shmem, cudaStream_t stream) {
    const bool first = func == mc_tiff_identity_conversion_kernel() &&
                       *static_cast<int *>(args[7]) == 0;
    if (first && (converted || span_reads != 4 ||
                  *static_cast<int *>(args[4]) != 48 || *static_cast<int *>(args[5]) != 40 ||
                  *static_cast<int *>(args[8]) != 2 || !*static_cast<bool *>(args[9]) ||
                  *static_cast<bool *>(args[10]))) std::abort();
    const cudaError_t result = __real_cudaLaunchKernel(func, grid, block, args, shmem, stream);
    if (!first || result != cudaSuccess) return result;
    cudaError_t status = cudaStreamSynchronize(stream);
    if (status != cudaSuccess) return status;
    constexpr size_t pixels = 48 * 40;
    std::vector<float> actual(3 * pixels), expected(3 * pixels);
    status = cudaMemcpy(actual.data(), *static_cast<float **>(args[1]),
                        2 * pixels * sizeof(float), cudaMemcpyDeviceToHost);
    if (status != cudaSuccess) return status;
    status = cudaMemcpy(actual.data() + 2 * pixels, *static_cast<float **>(args[2]),
                        pixels * sizeof(float), cudaMemcpyDeviceToHost);
    if (status != cudaSuccess) return status;
    const char *path = std::getenv("MC_TIFF_CONVERSION_EXPECTED");
    FILE *f = path ? std::fopen(path, "rb") : nullptr;
    if (!f) std::abort();
    const size_t count = std::fread(expected.data(), sizeof(float), expected.size(), f);
    const bool exact_file = count == expected.size() && std::fgetc(f) == EOF;
    std::fclose(f);
    if (!exact_file || actual != expected) {
        std::fprintf(stderr, "[tiffidentity] conversion readback mismatch\n");
        std::abort();
    }
    converted = true;
    std::fprintf(stderr, "[tiffidentity] converted frames=[0,2) frame-pixels=3840 sum-pixels=1920 exact=1\n");
    return result;
}
#endif
