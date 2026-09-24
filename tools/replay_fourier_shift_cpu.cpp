// Issue #36 diagnostic: replay one CPU global Fourier shift on a saved frame.
// Build: g++ -O3 -std=gnu++17 tools/replay_fourier_shift_cpu.cpp -o /tmp/replay_fourier_shift_cpu
// Usage: replay_fourier_shift_cpu <input.bin> <fresh-output.bin> <shift-x-px> <shift-y-px> <nx> <ny>
// Binary data is native-endian interleaved complex float [ny][nx/2+1].
#include <cerrno>
#include <cstdint>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <limits>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

struct ComplexFloat { float real, imag; };

static bool parseDimension(const char *text, int &value)
{
    char *end = nullptr;
    errno = 0;
    long parsed = std::strtol(text, &end, 10);
    if (errno || end == text || *end || parsed < 2 || parsed > std::numeric_limits<int>::max())
        return false;
    value = (int)parsed;
    return true;
}

static bool parseShift(const char *text, double &value)
{
    char *end = nullptr;
    errno = 0;
    value = std::strtod(text, &end);
    return !(errno || end == text || *end || !std::isfinite(value));
}

int main(int argc, char **argv)
{
    int nx = 0, ny = 0;
    double shift_x_px = 0, shift_y_px = 0;
    if (argc != 7 || !parseShift(argv[3], shift_x_px) || !parseShift(argv[4], shift_y_px) ||
        !parseDimension(argv[5], nx) || !parseDimension(argv[6], ny) || nx % 2) {
        std::fprintf(stderr, "Usage: %s <input.bin> <fresh-output.bin> <shift-x-px> <shift-y-px> <even-nx> <ny>\n", argv[0]);
        return 2;
    }
    const int nfx = nx / 2 + 1;
    const size_t count = (size_t)ny * nfx;
    if (count > SIZE_MAX / sizeof(ComplexFloat)) return 2;
    const size_t bytes = count * sizeof(ComplexFloat);
    struct stat info;
    if (stat(argv[1], &info) != 0 || !S_ISREG(info.st_mode) || (size_t)info.st_size != bytes)
        return 3;
    std::vector<ComplexFloat> frame(count);
    FILE *source = std::fopen(argv[1], "rb");
    if (!source || std::fread(frame.data(), sizeof(ComplexFloat), count, source) != count)
        return 4;
    std::fclose(source);

    // Match MotioncorrRunner::shiftNonSquareImageInFourierTransform's table and
    // three-multiply complex arithmetic in the default double-RFLOAT build.
    const double shift_x = -shift_x_px / nx, shift_y = -shift_y_px / ny;
    const double two_pi = 2 * 3.14159265358979323846;
    std::vector<double> sinx(nfx), cosx(nfx), siny(ny), cosy(ny);
    for (int y = 0; y < ny; ++y) {
        const int ly = y > ny / 2 ? y - ny : y;
        const double phase_y = two_pi * ly * shift_y;
        sincos(phase_y, &siny[y], &cosy[y]);
    }
    for (int x = 0; x < nfx; ++x) {
        const double phase_x = two_pi * x * shift_x;
        sincos(phase_x, &sinx[x], &cosx[x]);
    }
    for (int y = 0; y < ny; ++y) {
        for (int x = 0; x < nfx; ++x) {
            const size_t i = (size_t)y * nfx + x;
            const double b = sinx[x] * cosy[y] + cosx[x] * siny[y];
            const double a = cosx[x] * cosy[y] - sinx[x] * siny[y];
            const double c = frame[i].real, d = frame[i].imag;
            const double ac = a * c, bd = b * d, ab_cd = (a + b) * (c + d);
            frame[i] = ComplexFloat{(float)(ac - bd), (float)(ab_cd - ac - bd)};
        }
    }

    int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return 5;
    const char *data = (const char *)frame.data();
    size_t written = 0;
    while (written < bytes) {
        ssize_t n = write(fd, data + written, bytes - written);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); unlink(argv[2]); return 6; }
        written += (size_t)n;
    }
    if (close(fd) != 0) { unlink(argv[2]); return 6; }
    return 0;
}
