// Issue #36 diagnostic: replay a saved float CCF spectrum through double cuFFT.
// Build: nvcc -O3 tools/replay_global_ccf_cufft_double.cu -lcufft -o /tmp/replay_global_ccf_cufft_double
// Usage: replay_global_ccf_cufft_double <spectrum.bin> <fresh-image.bin> <even-nx> <ny> <gpu-ordinal>
// Input is native-endian interleaved complex float [ny][nx/2+1]. Double cuFFT
// output is cast to native-endian float [ny][nx], without inverse scaling.
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>
#include <cufft.h>
#include <fcntl.h>
#include <limits>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#define CHECK_CUDA(call) do { cudaError_t error = (call); if (error != cudaSuccess) { \
    std::fprintf(stderr, "CUDA: %s\n", cudaGetErrorString(error)); return 4; } } while (0)
#define CHECK_FFT(call) do { cufftResult error = (call); if (error != CUFFT_SUCCESS) { \
    std::fprintf(stderr, "cuFFT: %d\n", (int)error); return 5; } } while (0)

struct ComplexFloat { float real, imag; };

static bool parseInt(const char *text, int &value, int minimum)
{
    char *end = nullptr;
    errno = 0;
    long parsed = std::strtol(text, &end, 10);
    if (errno || end == text || *end || parsed < minimum || parsed > std::numeric_limits<int>::max())
        return false;
    value = (int)parsed;
    return true;
}

int main(int argc, char **argv)
{
    int nx = 0, ny = 0, gpu = -1;
    if (argc != 6 || !parseInt(argv[3], nx, 2) || !parseInt(argv[4], ny, 2) ||
        !parseInt(argv[5], gpu, 0) || nx % 2) {
        std::fprintf(stderr, "Usage: %s <spectrum.bin> <fresh-image.bin> <even-nx> <ny> <gpu-ordinal>\n", argv[0]);
        return 2;
    }
    const size_t complex_count = (size_t)ny * (nx / 2 + 1);
    const size_t real_count = (size_t)ny * nx;
    if (complex_count > SIZE_MAX / sizeof(cufftDoubleComplex) ||
        real_count > SIZE_MAX / sizeof(double)) return 2;
    const size_t input_bytes = complex_count * sizeof(ComplexFloat);
    struct stat info;
    if (stat(argv[1], &info) != 0 || !S_ISREG(info.st_mode) || (size_t)info.st_size != input_bytes)
        return 3;
    std::vector<ComplexFloat> source(complex_count);
    FILE *file = std::fopen(argv[1], "rb");
    if (!file || std::fread(source.data(), sizeof(ComplexFloat), complex_count, file) != complex_count)
        return 3;
    std::fclose(file);
    std::vector<cufftDoubleComplex> input(complex_count);
    for (size_t i = 0; i < complex_count; ++i) {
        input[i].x = source[i].real;
        input[i].y = source[i].imag;
    }

    CHECK_CUDA(cudaSetDevice(gpu));
    cufftDoubleComplex *device_input = nullptr;
    double *device_output = nullptr;
    CHECK_CUDA(cudaMalloc(&device_input, complex_count * sizeof(cufftDoubleComplex)));
    CHECK_CUDA(cudaMalloc(&device_output, real_count * sizeof(double)));
    CHECK_CUDA(cudaMemcpy(device_input, input.data(), complex_count * sizeof(cufftDoubleComplex), cudaMemcpyHostToDevice));
    cufftHandle plan;
    CHECK_FFT(cufftPlan2d(&plan, ny, nx, CUFFT_Z2D));
    CHECK_FFT(cufftExecZ2D(plan, device_input, device_output));
    CHECK_CUDA(cudaDeviceSynchronize());
    std::vector<double> double_output(real_count);
    CHECK_CUDA(cudaMemcpy(double_output.data(), device_output, real_count * sizeof(double), cudaMemcpyDeviceToHost));
    std::vector<float> output(real_count);
    for (size_t i = 0; i < real_count; ++i) output[i] = (float)double_output[i];

    const size_t output_bytes = real_count * sizeof(float);
    int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return 6;
    const char *bytes = (const char *)output.data();
    size_t written = 0;
    while (written < output_bytes) {
        ssize_t n = write(fd, bytes + written, output_bytes - written);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); unlink(argv[2]); return 7; }
        written += (size_t)n;
    }
    if (close(fd) != 0) { unlink(argv[2]); return 7; }
    cufftDestroy(plan);
    cudaFree(device_input);
    cudaFree(device_output);
    return 0;
}
