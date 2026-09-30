#ifndef CUDA_DEFLATE_LAYOUT_H_
#define CUDA_DEFLATE_LAYOUT_H_

#include <cstddef>
#include <cstdint>

#include "src/acc/cuda/cuda_scratch_arena.h"

/**
 * Host-side staging arithmetic for the nvCOMP Deflate TIFF ingestion path.
 *
 * Separate from cuda_movie_session.cu so it can be exercised without a GPU, an
 * nvCOMP install or a TIFF: everything here is integer layout and header parsing,
 * and it is where a silent defect would be invisible on the device. The alignment
 * rule in particular cannot be checked by observing a successful decompression --
 * a misaligned input pointer is undefined behaviour that happened to work on A100.
 */
namespace mc_tiff_deflate {

using mc_cuda::alignUp;   // single definition, shared with the scratch arena

/**
 * Offset at which a strip must be placed so that its raw Deflate payload, which
 * starts 2 bytes into the stored strip, meets nvCOMP's input alignment.
 * Never less than cursor, so successive slots cannot overlap.
 */
inline size_t stripSlotOffset(size_t cursor, size_t in_align) {
    return alignUp(cursor + 2, in_align) - 2;
}

/** Bytes one frame occupies in the staging buffer once every slot is aligned. */
inline size_t frameStageBytes(const uint32_t *raw_sizes, int n_strips, size_t in_align) {
    size_t cursor = 0;
    for (int s = 0; s < n_strips; s++) {
        cursor = stripSlotOffset(cursor, in_align) + raw_sizes[s];
    }
    return cursor;
}

/**
 * RFC 1950 wrapper check. TIFFReadRawStrip returns the stored bytes verbatim with no
 * inflation, so this is the only point at which a malformed stream can be rejected:
 * nvCOMP's raw Deflate path documents limited validation only, and treats a corrupt
 * buffer as undefined behaviour rather than a reported per-chunk error.
 */
inline bool zlibWrapperIsUsable(const uint8_t *p, size_t n) {
    if (n < 7) return false;                            // 2 header + >=1 payload + 4 Adler32
    const unsigned cmf = p[0];
    const unsigned flg = p[1];
    if ((cmf & 0x0Fu) != 8u) return false;              // CM must be Deflate
    if ((cmf >> 4) > 7u) return false;                  // CINFO: window <= 32 KiB
    if (((cmf << 8) | flg) % 31u != 0u) return false;   // FCHECK
    if ((flg >> 5) & 1u) return false;                  // FDICT: preset dictionaries unsupported
    return true;
}

/**
 * Bytes cudaHostAlloc is actually asked to pin for a request of @p bytes.
 *
 * The pool takes 12.5% headroom and rounds up to a 32 MiB granule, because the
 * compressed size drifts by a few MiB between movies of the same geometry and
 * an exact fit reallocated on 7 of the 24 tutorial movies. Both of those make
 * the reservation strictly larger than the request, so a budget enforced
 * against the request does not bound the memory: a 64 MiB cap admits a 64 MiB
 * payload and then pins 96 MiB, and an 8 MiB cap pins 32 MiB.
 *
 * Production and the device-free test both call THIS function. A restated
 * formula in either place would drift out of agreement with the other and the
 * budget check would stop observing the quantity it claims to bound.
 */
inline size_t pinnedReserveBytes(size_t bytes) {
    return alignUp(bytes + bytes / 8, (size_t)32 << 20);
}

/**
 * Parse MOTIONCORR_NVCOMP_PINNED_MAX_MB into a byte count.
 *
 * Strict on purpose. atol() reports no error and does not say how much of the
 * string it consumed, so "1G" silently became a 1 MiB cap that declines the
 * fast path for a whole run, "abc" and "0" silently became the default, and a
 * value at or above 2^44 shifted past 64 bits to a cap of zero. None of those
 * produced a diagnostic. Returns false for anything that is not a positive
 * decimal integer whose MiB value fits in size_t; the caller reports the
 * rejection rather than quietly substituting a different budget.
 */
inline bool parsePinnedCapBytes(const char *env, size_t &out) {
    if (env == 0 || *env == 0) return false;
    unsigned long long mb = 0;
    for (const char *p = env; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        const unsigned long long digit = (unsigned long long)(*p - '0');
        if (mb > (~0ull - digit) / 10ull) return false;      // decimal overflow
        mb = mb * 10ull + digit;
    }
    if (mb == 0) return false;
    if (mb > ((size_t)-1 >> 20)) return false;               // the << 20 would wrap
    out = (size_t)mb << 20;
    return true;
}

} // namespace mc_tiff_deflate

#endif // CUDA_DEFLATE_LAYOUT_H_
