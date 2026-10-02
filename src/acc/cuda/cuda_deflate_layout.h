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

// The two strip-addressing accessors below run both on the host, where the
// device-free control exercises them, and inside the ingest kernel. Annotating
// them is what lets the kernel call the tested code instead of a copy of it.
#if defined(__CUDACC__)
#define MC_TIFF_HOST_DEVICE __host__ __device__
#else
#define MC_TIFF_HOST_DEVICE
#endif

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
 * Decompressed-output geometry of one TIFF frame's strips.
 *
 * A strip is one independent Deflate stream and therefore one nvCOMP chunk, so
 * the number of chunks and the bytes each one produces are set entirely by
 * RowsPerStrip, the width and the sample width. Only strip starts are padded:
 * rows inside a strip are consecutive in the single buffer nvCOMP writes for
 * that chunk.
 *
 * Here rather than inline in the ingest function because every field is a
 * silent-defect site that a successful decode cannot expose. Declaring the full
 * strip length for a short final strip, or padding between rows inside a strip,
 * produces a buffer that still decodes and still passes a status check; the
 * image is simply wrong in the last rows_per_strip rows of every frame, which
 * on a 3838-row movie is under 0.3% of the pixels.
 */
struct StripGeometry {
    int rows_per_strip;      ///< rows in every strip but possibly the last
    int strips_per_frame;    ///< ceil(ny / rows_per_strip)
    int last_strip_rows;     ///< rows in the final strip, in [1, rows_per_strip]
    size_t row_bytes;        ///< nx * bytes_per_sample
    size_t full_strip_bytes; ///< decompressed bytes of a full strip
    size_t last_strip_bytes; ///< decompressed bytes of the final strip
    size_t strip_pitch;      ///< padded distance between strip output slots

    /// Declared decompressed length of chunk @p c, counted within a batch whose
    /// frames each contribute strips_per_frame chunks in order.
    MC_TIFF_HOST_DEVICE size_t chunkBytes(size_t c) const {
        return ((int)(c % (size_t)strips_per_frame) == strips_per_frame - 1)
                   ? last_strip_bytes : full_strip_bytes;
    }

    /// Bytes one frame's strip slots occupy in the output buffer.
    MC_TIFF_HOST_DEVICE size_t frameSlabBytes() const {
        return (size_t)strips_per_frame * strip_pitch;
    }

    /// Byte offset of row @p y within one frame's slab.
    ///
    /// Split from rowOffset so the kernel can hoist it out of its frame loop:
    /// the strip index needs an integer division, which does not depend on the
    /// frame and is expensive enough on the device to show up as a per-movie
    /// cost when it is repeated once per frame per pixel.
    MC_TIFF_HOST_DEVICE size_t rowOffsetInFrame(int y) const {
        const int strip = y / rows_per_strip;
        return (size_t)strip * strip_pitch + (size_t)(y - strip * rows_per_strip) * row_bytes;
    }

    /// Byte offset of row @p y of frame-in-batch @p b from the output base.
    MC_TIFF_HOST_DEVICE size_t rowOffset(int b, int y) const {
        return (size_t)b * frameSlabBytes() + rowOffsetInFrame(y);
    }
};

/**
 * Plan the strip geometry for one movie. @p rows_per_strip is the TIFF tag value
 * already clamped to [1, ny]; @p bytes_per_sample is 1 or 2.
 */
inline StripGeometry planStrips(int nx, int ny, int rows_per_strip, int bytes_per_sample) {
    StripGeometry g;
    g.rows_per_strip = rows_per_strip;
    g.strips_per_frame = (ny + rows_per_strip - 1) / rows_per_strip;
    g.last_strip_rows = ny - (g.strips_per_frame - 1) * rows_per_strip;
    g.row_bytes = (size_t)nx * (size_t)bytes_per_sample;
    g.full_strip_bytes = (size_t)rows_per_strip * g.row_bytes;
    g.last_strip_bytes = (size_t)g.last_strip_rows * g.row_bytes;
    g.strip_pitch = 0;   // set by withOutputAlignment
    return g;
}

/// Apply nvCOMP's reported output alignment to the strip slots.
inline StripGeometry withOutputAlignment(StripGeometry g, size_t out_align) {
    g.strip_pitch = alignUp(g.full_strip_bytes, out_align);
    return g;
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
