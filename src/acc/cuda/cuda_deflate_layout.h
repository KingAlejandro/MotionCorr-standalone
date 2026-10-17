#ifndef CUDA_DEFLATE_LAYOUT_H_
#define CUDA_DEFLATE_LAYOUT_H_

#include <cstddef>
#include <cstdint>
#include <cstring>

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
 * ADMISSION POLICY: which TIFF encodings the automatic route hands to nvCOMP.
 *
 * This is the one place that decides it (#138, #134, decision D1 on #198).
 * Everything admitted here is decoded by nvCOMP Deflate, which NVIDIA documents
 * as undefined behaviour on corrupt input; inputs refused here fall back to the
 * compact or float host readers. The remaining checks in the ingest tag scan
 * (predictor, byte order, sample format, planar layout, geometry, strip-size
 * consistency) are format correctness, not policy.
 *
 * Both flags true is #138. Both false reproduces main at 1db86902: 16-bit
 * samples, one full row per strip. A decision for "GPU decoder only by explicit
 * opt-in" would not be made here but at the caller, by refusing every input
 * unless --ingest nvcomp was pinned.
 *
 * Returns nullptr when admitted, else the reason logged for the refusal.
 */
constexpr bool kAdmit8BitSamples = true;
constexpr bool kAdmitMultiRowStrips = true;

inline const char *admissionRefusal(int bits_per_sample, int rows_per_strip) {
    if (bits_per_sample != 16 && !(kAdmit8BitSamples && bits_per_sample == 8))
        return "bits per sample is not 8 or 16";
    if (rows_per_strip != 1 && !kAdmitMultiRowStrips)
        return "strip layout is not one full row per strip";
    return nullptr;
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

/**
 * Parse a strictly positive decimal integer that fits in an int (used for
 * MOTIONCORR_NVCOMP_CHUNK_FRAMES). Same strictness as parsePinnedCapBytes, for
 * the same reason: a silently substituted value hides the cause of a slow run.
 */
inline bool parsePositiveInt(const char *env, int &out) {
    if (env == 0 || *env == 0) return false;
    long long v = 0;
    for (const char *p = env; *p; ++p) {
        if (*p < '0' || *p > '9') return false;
        v = v * 10 + (*p - '0');
        if (v > 0x7FFFFFFFll) return false;
    }
    if (v == 0) return false;
    out = (int)v;
    return true;
}

/**
 * Frames per pipelined ingest chunk when MOTIONCORR_NVCOMP_CHUNK_FRAMES is not
 * set. Four chunks is enough for the strip read of chunk k+1 to hide behind the
 * copy and decode of chunk k; more chunks only add fill/drain and per-call cost.
 */
inline int defaultChunkFrames(int n_frames) {
    if (n_frames <= 1) return 1;
    return (n_frames + 3) / 4;
}

/** Number of pipeline slots for a movie split into chunks of chunk_frames:
 *  two (double buffering) whenever there is more than one chunk, else one. */
inline int pipelineSlots(int n_frames, int chunk_frames) {
    if (chunk_frames <= 0) return 0;
    return ((n_frames + chunk_frames - 1) / chunk_frames) > 1 ? 2 : 1;
}

/**
 * Host (pinned) layout for the pipelined ingest: per slot, the compressed
 * payload, the per-strip input pointer/size tables uploaded with it, the
 * constant output pointer/size tables, and the status/length/Adler-32 readback.
 *
 * Every byte the pipeline pins lives here, so the pinned cap is enforced on
 * total, and the slots are disjoint so one chunk's readback or tables can never
 * alias another's while both are in flight. Pure arithmetic; tested device-free.
 */
struct PinnedChunkLayout {
    int slots = 0;
    size_t chunk_strips = 0;
    size_t slot_payload = 0;
    size_t payload[2] = {0, 0};
    size_t cptr[2] = {0, 0}, csize[2] = {0, 0}, dptr[2] = {0, 0}, dsize[2] = {0, 0};
    size_t status[2] = {0, 0}, asize[2] = {0, 0}, adler[2] = {0, 0};
    size_t total = 0;
};

inline PinnedChunkLayout pinnedChunkLayout(int slots, size_t slot_payload, size_t chunk_strips,
                                           size_t status_bytes) {
    PinnedChunkLayout L;
    if (slots < 1 || slots > 2) return L;
    L.slots = slots;
    L.chunk_strips = chunk_strips;
    L.slot_payload = slot_payload;
    const size_t a = 64;
    size_t cur = 0;
    auto take = [&](size_t bytes) { const size_t o = alignUp(cur, a); cur = o + bytes; return o; };
    for (int j = 0; j < slots; j++) L.payload[j] = take(slot_payload);
    for (int j = 0; j < slots; j++) {
        L.cptr[j]   = take(chunk_strips * sizeof(void *));
        L.csize[j]  = take(chunk_strips * sizeof(size_t));
        L.dptr[j]   = take(chunk_strips * sizeof(void *));
        L.dsize[j]  = take(chunk_strips * sizeof(size_t));
        L.status[j] = take(chunk_strips * status_bytes);
        L.asize[j]  = take(chunk_strips * sizeof(size_t));
        L.adler[j]  = take(chunk_strips * sizeof(uint32_t));
    }
    L.total = alignUp(cur, a);
    return L;
}

/** Bytes of a frame's strips packed back to back: its file span when the
 *  strips are stored contiguously in strip order. */
inline size_t framePackedBytes(const uint32_t *raw_sizes, int n_strips) {
    size_t total = 0;
    for (int s = 0; s < n_strips; s++) total += raw_sizes[s];
    return total;
}

/**
 * Spread a frame read as one packed span into its aligned strip slots, in place.
 *
 * On entry the packed bytes sit at fb + lead, where
 * lead = frameStageBytes(...) - framePackedBytes(...), i.e. the packed span ends
 * exactly where the slotted layout ends. Strip s moves from fb + lead + p_s
 * (p_s = sum of earlier sizes) to fb + slot_s. Because the padding before strip s
 * never exceeds the total padding, slot_s <= lead + p_s: every strip moves left
 * or stays. Strips are moved in increasing order, and an unmoved strip t > s
 * starts at lead + p_t >= lead + p_s + size_s >= slot_s + size_s, so a move never
 * overwrites bytes that are still to be moved. memmove handles a strip's overlap
 * with its own old position. The result equals placing each strip directly.
 */
inline void spreadPackedStrips(uint8_t *fb, const uint32_t *raw_sizes, int n_strips,
                               size_t in_align) {
    const size_t lead = frameStageBytes(raw_sizes, n_strips, in_align)
                      - framePackedBytes(raw_sizes, n_strips);
    if (lead == 0) return;
    size_t cursor = 0, packed = 0;
    for (int s = 0; s < n_strips; s++) {
        const size_t slot = stripSlotOffset(cursor, in_align);
        const size_t src = lead + packed;
        if (slot != src) std::memmove(fb + slot, fb + src, raw_sizes[s]);
        cursor = slot + raw_sizes[s];
        packed += raw_sizes[s];
    }
}

} // namespace mc_tiff_deflate

#endif // CUDA_DEFLATE_LAYOUT_H_
