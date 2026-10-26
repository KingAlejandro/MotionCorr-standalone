// #226 D2: host-only controls for additional live bytes on resident retry.
#include "src/acc/cuda/cuda_patch_retry_admission.h"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
size_t bytes(int pw, int ph, int groups, int cw, int ch, size_t work) {
    size_t result = 0;
    require(mc_cuda::patchRetryRequiredBytes(pw, ph, groups, cw, ch, work, result),
            "valid retry geometry refused");
    return result;
}
void refused(int pw, int ph, int groups, int cw, int ch, size_t work) {
    size_t result = 123;
    require(!mc_cuda::patchRetryRequiredBytes(pw, ph, groups, cw, ch, work, result),
            "invalid or overflowing requirement accepted");
    require(result == 123, "failed calculation published a partial requirement");
}
}

int main() {
    try {
        // Retained e10216 geometry: independent literal counts from the actual
        // allocations, including one (not two) full-spectrum stacks.
        const size_t spectrum = 158299360;
        const size_t buffers = 22407056;
        const size_t minimum = spectrum + buffers;
        require(bytes(818, 818, 59, 216, 216, 0) == 180706416,
                "e10216 retry allocation census differs");
        const size_t work = 16 * 1024 * 1024;
        const size_t required = bytes(818, 818, 59, 216, 216, work);
        require(required == minimum + work, "cuFFT workspace missing or counted twice");
        for (size_t free : {spectrum, spectrum + 1, size_t(175000000), minimum - 1,
                            minimum, required - 1}) {
            require(spectrum <= free && required > free,
                    "S-fits-but-complete-retry-does-not interval admitted");
        }
        // A full CCF window and a rectangular downsampled one: independently sum
        // upload, reference, weights, complex/real CCFs and four shift arrays.
        require(bytes(102, 102, 24, 102, 102, 17) ==
                size_t(24 * 102 * 52 * 8) + 102 * 52 * 12 +
                24 * 102 * 52 * 8 + 24 * 102 * 102 * 4 + 4 * 24 * 4 + 17,
                "full-window requirement differs");
        require(bytes(408, 324, 7, 216, 192, 31) ==
                size_t(7 * 324 * 205 * 8) + 192 * 109 * 12 +
                7 * 192 * 109 * 8 + 7 * 192 * 216 * 4 + 4 * 7 * 4 + 31,
                "rectangular-window requirement differs");
        require(bytes(408, 324, 7, 408, 324, 31) > bytes(408, 324, 7, 216, 192, 31),
                "retry did not depend on the actual CCF window");

        const size_t max = std::numeric_limits<size_t>::max();
        require(bytes(818, 818, 59, 216, 216, max - minimum) == max,
                "exact size_t boundary refused");
        refused(818, 818, 59, 216, 216, max - minimum + 1);
        refused(818, 818, 59, 216, 216, max);
        // All per-transform plan distances fit int, but the batch totals do not
        // fit size_t (on either a 32- or 64-bit host).
        refused(46340, 46340, INT_MAX, 46340, 46340, 0);
        refused(65536, 65536, 1, 216, 216, 0); // int plan-distance overflow
        refused(0, 818, 59, 216, 216, 0);
        refused(-2, 818, 59, 216, 216, 0);
        refused(818, 818, 0, 216, 216, 0);
        refused(818, 818, -1, 216, 216, 0);
        refused(817, 818, 59, 216, 216, 0);
        refused(818, 817, 59, 216, 216, 0);
        refused(818, 818, 59, 0, 216, 0);
        refused(818, 818, 59, 216, -2, 0);
        refused(818, 818, 59, 217, 216, 0);
        refused(818, 818, 59, 216, 217, 0);
        refused(818, 818, 59, 820, 216, 0);
        refused(818, 818, 59, 216, 820, 0);
        std::cout << "PASS: retry live-byte census, conditional interval, boundaries and overflow\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    }
}
