// Issue #36 diagnostic: replay a saved single-frame CCF spectrum through FFTW.
// Build: g++ -O2 tools/replay_global_ccf_fftw.cpp -lfftw3f -o /tmp/replay_global_ccf_fftw
// Usage: replay_global_ccf_fftw <spectrum.bin> <image.bin> <nx> <ny>
// The binary input is native-endian, interleaved complex float in [ny][nx/2+1]
// layout. The output is native-endian float in [ny][nx] layout. No FFT scaling.
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fftw3.h>
#include <fcntl.h>
#include <limits>
#include <sys/stat.h>
#include <unistd.h>

static bool dimension(const char *text, int &value)
{
    char *end = nullptr;
    errno = 0;
    long parsed = std::strtol(text, &end, 10);
    if (errno || end == text || *end || parsed < 2 || parsed > std::numeric_limits<int>::max())
        return false;
    value = (int)parsed;
    return true;
}

int main(int argc, char **argv)
{
    int nx = 0, ny = 0;
    if (argc != 5 || !dimension(argv[3], nx) || !dimension(argv[4], ny) || nx % 2) {
        std::fprintf(stderr, "Usage: %s <spectrum.bin> <fresh-image.bin> <even-nx> <ny>\n", argv[0]);
        return 2;
    }
    const size_t complex_count = (size_t)ny * (nx / 2 + 1);
    const size_t real_count = (size_t)ny * nx;
    if (complex_count > SIZE_MAX / sizeof(fftwf_complex) || real_count > SIZE_MAX / sizeof(float))
        return 2;
    const size_t input_bytes = complex_count * sizeof(fftwf_complex);
    const size_t output_bytes = real_count * sizeof(float);
    struct stat info;
    if (stat(argv[1], &info) != 0 || !S_ISREG(info.st_mode) || (size_t)info.st_size != input_bytes) {
        std::fprintf(stderr, "Input is missing or has the wrong size\n");
        return 3;
    }
    fftwf_complex *input = (fftwf_complex *)fftwf_malloc(input_bytes);
    float *output = (float *)fftwf_malloc(output_bytes);
    if (!input || !output) return 4;
    FILE *source = std::fopen(argv[1], "rb");
    if (!source || std::fread(input, 1, input_bytes, source) != input_bytes) return 5;
    std::fclose(source);
    fftwf_plan plan = fftwf_plan_dft_c2r_2d(ny, nx, input, output, FFTW_ESTIMATE);
    if (!plan) return 6;
    fftwf_execute(plan);
    fftwf_destroy_plan(plan);
    int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) {
        std::fprintf(stderr, "Refusing existing or unwritable output\n");
        return 7;
    }
    const char *bytes = (const char *)output;
    size_t written = 0;
    while (written < output_bytes) {
        ssize_t count = write(fd, bytes + written, output_bytes - written);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) {
            close(fd);
            unlink(argv[2]);
            return 8;
        }
        written += (size_t)count;
    }
    if (close(fd) != 0) {
        unlink(argv[2]);
        return 8;
    }
    fftwf_free(input);
    fftwf_free(output);
    return 0;
}
