#include "src/acc/cuda/cuda_adler32.h"
#include <iostream>
#include <stdexcept>
#include <vector>

static void require(bool ok, const char *why) {
    if (!ok) throw std::runtime_error(why);
}
static uint32_t serial(const std::vector<uint8_t> &v) {
    uint32_t a = 1, b = 0;
    for (uint8_t d : v) { a = (a + d) % 65521; b = (b + a) % 65521; }
    return (b << 16) | a;
}
template<class Byte>
static uint32_t parallel(size_t n, Byte byte) {
    uint64_t a = 0, b = 0;
    for (size_t t = 0; t < 256; ++t) {
        mc_tiff_adler::Lane lane(n, t, 256);
        for (size_t i = t; i < n; i += 256) lane.add(byte(i));
        a += lane.bytes(); b += lane.weighted();
    }
    return mc_tiff_adler::finish(n, a, b);
}
int main() {
    try {
        for (size_t n : {size_t(0), size_t(1), size_t(255), size_t(256),
                         size_t(257), size_t(65521), size_t(1048833)}) {
            std::vector<uint8_t> v(n);
            for (size_t i = 0; i < n; ++i) v[i] = uint8_t(i * 37 + (i >> 9));
            require(parallel(n, [&](size_t i) { return v[i]; }) == serial(v),
                    "normal/short/nonuniform Adler mismatch");
        }
        // No large fixture/allocation. This exercises the SAME production Lane
        // add/reduction for every one of 512 MiB logical bytes, using constant ff.
        const size_t n = size_t(512) << 20;
        const uint32_t got = parallel(n, [](size_t) { return uint8_t(255); });
        // Independent constant-byte formula: divide an even factor BEFORE
        // modulo/multiply, so the oracle itself cannot wrap a length-squared sum.
        const uint64_t x = n / 2, y = n + 1;
        const uint64_t tri = ((x % 65521) * (y % 65521)) % 65521;
        const uint32_t expected = uint32_t((((n % 65521 + tri * 255) % 65521) << 16)
                                         | ((1 + (n % 65521) * 255) % 65521));
        require(expected == 0x2a2a3c03u && got == expected, "512MiB Adler mismatch");
        // Frozen predecessor arithmetic MODEL: the kernel's final 256-lane
        // uint64 reduction wraps modulo 2^64 before applying modulo 65521.
        const uint64_t old_weighted = uint64_t(n) * (n + 1) / 2 * 255;
        const uint32_t predecessor = uint32_t((((n + old_weighted) % 65521) << 16)
                                              | ((1 + uint64_t(n) * 255) % 65521));
        require(predecessor == 0x645a3c03u && predecessor != got,
                "predecessor overflow control did not discriminate");
        std::cout << "PASS: 7 ordinary lengths, actual production arithmetic over "
                     "512MiB logical ff bytes; old uint64 model fails 645a3c03 vs 2a2a3c03\n";
    } catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
}
