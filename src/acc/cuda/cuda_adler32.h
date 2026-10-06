// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef CUDA_ADLER32_H_
#define CUDA_ADLER32_H_

#include <cstddef>
#include <cstdint>

#ifdef __CUDACC__
#define MC_ADLER_HD __host__ __device__
#else
#define MC_ADLER_HD
#endif

namespace mc_tiff_adler {
constexpr uint32_t modulus = 65521;

// Closed-form Adler contribution from one strided lane. Every weight is reduced
// modulo 65521 BEFORE multiplication, and sums are reduced every 4096 bytes.
// Including the prior remainder, weighted sum <=65520+4096*65520*255
// = 68,434,395,120 < 2^36; byte sum <=65520+4096*255 = 1,110,000.
// These bounds are independent of strip length.
// Subtraction of the stride modulo 65521 preserves (length-index) modulo 65521.
struct Lane {
    uint64_t sum_d = 0, sum_w = 0;
    uint32_t weight, step, pending = 0;

    MC_ADLER_HD Lane(size_t length, size_t lane, size_t stride)
        : weight((uint32_t)((length % modulus + modulus - lane % modulus) % modulus)),
          step((uint32_t)(stride % modulus)) {}

    MC_ADLER_HD void add(uint8_t d) {
        sum_d += d;
        sum_w += (uint64_t)weight * d;
        weight = weight >= step ? weight - step : weight + modulus - step;
        if (++pending == 4096) {
            sum_d %= modulus;
            sum_w %= modulus;
            pending = 0;
        }
    }
    MC_ADLER_HD uint32_t bytes() const { return (uint32_t)(sum_d % modulus); }
    MC_ADLER_HD uint32_t weighted() const { return (uint32_t)(sum_w % modulus); }
};

// After reduction each lane contributes <65521; 256 lanes sum to <2^24.
MC_ADLER_HD inline uint32_t finish(size_t length, uint64_t bytes, uint64_t weighted) {
    const uint32_t a = (uint32_t)((1 + bytes) % modulus);
    const uint32_t b = (uint32_t)((length % modulus + weighted) % modulus);
    return (b << 16) | a;
}

// Shared with the actual device kernel; status/length must be accepted before
// any decompressed-output byte is read. The caller supplies nvcompSuccess.
template<class Status>
MC_ADLER_HD inline bool accepted(Status status, Status success,
                                 size_t actual, size_t expected) {
    return status == success && actual == expected;
}
} // namespace mc_tiff_adler
#undef MC_ADLER_HD
#endif
