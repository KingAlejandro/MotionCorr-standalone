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

} // namespace mc_tiff_deflate

#endif // CUDA_DEFLATE_LAYOUT_H_
