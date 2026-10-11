// Device-free control for the nvCOMP Deflate ingestion staging layout.
//
// The two properties tested here are the ones a successful run on the device cannot
// establish. A misaligned nvCOMP input pointer is undefined behaviour that decoded
// correctly on A100, so "all pixels matched" is not evidence the alignment rule
// holds; and an unvalidated zlib wrapper only matters on input that never reached
// the benchmark. Both are pure integer/byte logic, so they are checked here rather
// than behind a GPU and an nvCOMP install.

#include "src/acc/cuda/cuda_deflate_layout.h"

#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>

using namespace mc_tiff_deflate;

static int failures = 0;

static void check(bool cond, const char *what) {
    if (!cond) { std::printf("FAIL: %s\n", what); failures++; }
}

// Tutorial movie geometry: 3838 rows of one strip each, ~1.3 kB per compressed row.
static std::vector<uint32_t> tutorialStripSizes(int n_strips, unsigned seed) {
    std::vector<uint32_t> sizes(n_strips);
    unsigned st = seed;
    for (int i = 0; i < n_strips; i++) {
        st = st * 1103515245u + 12345u;
        sizes[i] = 1200u + (st >> 16) % 600u;   // odd and even lengths both occur
    }
    return sizes;
}

static void testSlotAlignment(size_t in_align) {
    const int n_strips = 3838;
    const std::vector<uint32_t> sizes = tutorialStripSizes(n_strips, 7u);

    size_t cursor = 0;
    size_t prev_end = 0;
    int misaligned = 0, overlapping = 0;
    for (int s = 0; s < n_strips; s++) {
        const size_t slot = stripSlotOffset(cursor, in_align);
        const size_t payload = slot + 2;             // raw Deflate begins after the zlib header
        if (payload % in_align != 0) misaligned++;
        if (slot < prev_end) overlapping++;
        prev_end = slot + sizes[s];
        cursor = prev_end;
    }
    char msg[128];
    std::snprintf(msg, sizeof(msg), "every payload aligned to %zu", in_align);
    check(misaligned == 0, msg);
    std::snprintf(msg, sizeof(msg), "no slot overlap at alignment %zu", in_align);
    check(overlapping == 0, msg);

    check(frameStageBytes(sizes.data(), n_strips, in_align) == cursor,
          "frameStageBytes matches the walked layout");

    // Padding must stay negligible: the whole point is to avoid inflating the
    // compressed working set that the PCIe saving depends on.
    size_t dense = 0;
    for (int s = 0; s < n_strips; s++) dense += sizes[s];
    const size_t padded = frameStageBytes(sizes.data(), n_strips, in_align);
    check(padded >= dense, "aligned layout is never smaller than the dense one");
    check(padded - dense <= (size_t)n_strips * in_align, "padding bounded by align per strip");
}

// Negative control: the scheme this replaces packed strips densely and handed nvCOMP
// base+2. If that were still in use the alignment assertion above must fail, or the
// assertion is not observing anything.
static void testDensePackingIsRejected(size_t in_align) {
    const int n_strips = 3838;
    const std::vector<uint32_t> sizes = tutorialStripSizes(n_strips, 7u);
    size_t cursor = 0;
    int misaligned = 0;
    for (int s = 0; s < n_strips; s++) {
        if ((cursor + 2) % in_align != 0) misaligned++;
        cursor += sizes[s];
    }
    check(misaligned > n_strips / 2,
          "dense packing misaligns most payloads (control for the alignment check)");
}

static void testZlibWrapper() {
    // 0x78 0x9C: CM=8, CINFO=7, FCHECK valid, FDICT clear. What libtiff writes.
    const uint8_t good[8] = {0x78, 0x9C, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
    check(zlibWrapperIsUsable(good, sizeof(good)), "accepts a well-formed zlib strip");

    const uint8_t too_short[6] = {0x78, 0x9C, 0x01, 0x02, 0x03, 0x04};
    check(!zlibWrapperIsUsable(too_short, sizeof(too_short)),
          "rejects a strip with no room for payload plus Adler32");

    uint8_t bad_cm[8]; std::memcpy(bad_cm, good, 8);
    bad_cm[0] = 0x7A;  // CM=10, not Deflate
    check(!zlibWrapperIsUsable(bad_cm, 8), "rejects a non-Deflate compression method");

    uint8_t big_window[8]; std::memcpy(big_window, good, 8);
    big_window[0] = 0x88; big_window[1] = 0x1C;   // CINFO=8, FCHECK made valid
    check(((big_window[0] << 8) | big_window[1]) % 31 == 0, "control header is FCHECK-valid");
    check(!zlibWrapperIsUsable(big_window, 8), "rejects a window larger than 32 KiB");

    uint8_t fdict[8]; std::memcpy(fdict, good, 8);
    fdict[1] = 0x20;   // FDICT set, FCHECK valid: 0x7820 % 31 == 0
    check(((fdict[0] << 8) | fdict[1]) % 31 == 0, "FDICT control header is FCHECK-valid");
    check(!zlibWrapperIsUsable(fdict, 8), "rejects a preset-dictionary stream");

    uint8_t bad_fcheck[8]; std::memcpy(bad_fcheck, good, 8);
    bad_fcheck[1] = 0x9D;
    check(!zlibWrapperIsUsable(bad_fcheck, 8), "rejects a corrupt FCHECK");
}

// The arena is d_Fframes: n_frames * ny * nfx * sizeof(cufftComplex). The batch must
// be chosen so the working set fits inside it, or the path costs extra VRAM.
static void testArenaFitsTutorialMovie() {
    const size_t nx = 3710, ny = 3838, n_frames = 24;
    const size_t nfx = nx / 2 + 1;
    const size_t arena = n_frames * ny * nfx * 8;      // sizeof(cufftComplex)
    const size_t in_align = 8, out_align = 8;
    const size_t row_pitch = alignUp(nx * 2, out_align);

    const std::vector<uint32_t> sizes = tutorialStripSizes((int)ny, 7u);
    const size_t per_frame_comp = alignUp(frameStageBytes(sizes.data(), (int)ny, in_align), in_align);

    // Whole movie in one batch, the largest case the selector can pick.
    const size_t chunks = n_frames * ny;
    const size_t need = n_frames * per_frame_comp
                      + n_frames * ny * row_pitch
                      + chunks * (2 * sizeof(void *) + 3 * sizeof(size_t) + sizeof(int))
                      + 64u * 1024u * 1024u;           // generous nvCOMP scratch allowance
    check(need < arena, "whole-movie working set fits in the borrowed Fourier buffer");

    // A single frame must fit even on a movie whose spectrum buffer is small.
    const size_t one_frame = per_frame_comp + ny * row_pitch
                           + ny * (2 * sizeof(void *) + 3 * sizeof(size_t) + sizeof(int));
    check(one_frame < arena / n_frames * 2, "a one-frame batch fits within two frame slabs");
}

// The pinned budget must bound the bytes that are actually pinned.
//
// MOTIONCORR_NVCOMP_PINNED_MAX_MB used to be compared against the compressed
// payload of the candidate batch, while the pool reserved that payload plus
// 12.5% rounded up to a 32 MiB granule. A 64 MiB cap therefore admitted a
// 64 MiB payload and pinned 96 MiB; an 8 MiB cap pinned 32 MiB. Under a
// process-per-GPU layout each worker has its own pool, so the overshoot
// multiplies by the worker count.
//
// This calls the same pinnedReserveBytes() production calls. A formula
// restated here would drift and the check would stop observing the quantity
// it claims to bound.
static void testPinnedBudgetBoundsWhatIsPinned() {
    const size_t caps[] = { (size_t)1 << 20, (size_t)8 << 20, (size_t)64 << 20,
                            (size_t)256 << 20, (size_t)1024 << 20 };
    for (size_t i = 0; i < sizeof(caps) / sizeof(caps[0]); i++) {
        const size_t cap = caps[i];
        // Largest payload the selector may admit under this cap, by bisection
        // on the same predicate the selector uses.
        size_t lo = 0, hi = cap;
        while (lo < hi) {
            const size_t mid = lo + (hi - lo + 1) / 2;
            if (pinnedReserveBytes(mid) <= cap) lo = mid; else hi = mid - 1;
        }
        check(lo == 0 || pinnedReserveBytes(lo) <= cap,
              "an admitted batch never reserves more pinned bytes than the cap");
    }
    // The property the old code got wrong, stated directly.
    check(pinnedReserveBytes((size_t)64 << 20) > ((size_t)64 << 20),
          "the reservation really is larger than the payload, so the two are not interchangeable");
}

// The cap parse must reject what it cannot represent, and say so, rather than
// silently installing a different budget.
static void testPinnedCapParsing() {
    size_t out = 0;
    check(parsePinnedCapBytes("64", out) && out == ((size_t)64 << 20), "plain MiB value accepted");
    check(parsePinnedCapBytes("1024", out) && out == ((size_t)1024 << 20), "four-digit value accepted");
    out = 0;
    // atol("1G") == 1, which installed a 1 MiB cap and declined the fast path
    // for the whole run with no message naming the cause.
    check(!parsePinnedCapBytes("1G", out), "a suffixed size is rejected, not truncated to its digits");
    check(!parsePinnedCapBytes("0.5", out), "a fractional value is rejected");
    check(!parsePinnedCapBytes("abc", out), "a non-numeric value is rejected");
    check(!parsePinnedCapBytes("", out), "an empty value is rejected");
    check(!parsePinnedCapBytes("0", out), "zero is rejected rather than meaning the default");
    check(!parsePinnedCapBytes("-8", out), "a negative value is rejected");
    check(!parsePinnedCapBytes(" 64", out), "a leading space is rejected");
    check(!parsePinnedCapBytes("64 ", out), "a trailing space is rejected");
    // 2^44 MiB shifts past 64 bits; atol + unchecked << 20 produced a cap of 0.
    check(!parsePinnedCapBytes("17592186044416", out), "a value that overflows the MiB shift is rejected");
    check(!parsePinnedCapBytes("99999999999999999999999", out), "a value that overflows decimal parsing is rejected");
}

// The span reader places one pread of a frame's packed strips at the end of the
// slotted frame and spreads it in place. The result must equal placing every
// strip directly at its slot, which is what the per-strip reader does. Checked
// on adversarial sizes too: every padding amount, tiny and large strips.
static void testSpreadEqualsDirectPlacement(size_t in_align, unsigned seed, int n_strips) {
    std::vector<uint32_t> sizes(n_strips);
    unsigned st = seed;
    for (int i = 0; i < n_strips; i++) {
        st = st * 1103515245u + 12345u;
        sizes[i] = 7u + (st >> 16) % (i % 5 == 0 ? 2000u : 13u);
    }
    const size_t frame = frameStageBytes(sizes.data(), n_strips, in_align);
    const size_t packed = framePackedBytes(sizes.data(), n_strips);
    check(frame >= packed, "slotted frame is never smaller than its packed span");
    std::vector<uint8_t> packed_bytes(packed);
    for (size_t i = 0; i < packed; i++) packed_bytes[i] = (uint8_t)((i * 131u + seed) & 0xFFu);

    std::vector<uint8_t> direct(frame, 0xEE), spread(frame, 0xEE);
    size_t cursor = 0, p = 0;
    for (int s = 0; s < n_strips; s++) {
        const size_t slot = stripSlotOffset(cursor, in_align);
        std::memcpy(direct.data() + slot, packed_bytes.data() + p, sizes[s]);
        cursor = slot + sizes[s];
        p += sizes[s];
    }
    std::memcpy(spread.data() + (frame - packed), packed_bytes.data(), packed);
    spreadPackedStrips(spread.data(), sizes.data(), n_strips, in_align);
    // Padding bytes are never read (nvCOMP gets pointer + size per strip), so only
    // the strip bytes are compared.
    bool same = true;
    cursor = 0;
    for (int s = 0; s < n_strips && same; s++) {
        const size_t slot = stripSlotOffset(cursor, in_align);
        same = std::memcmp(direct.data() + slot, spread.data() + slot, sizes[s]) == 0;
        cursor = slot + sizes[s];
    }
    check(same, "in-place spread of a packed span equals per-strip placement");
}

// Every pinned byte the pipeline uses is inside one layout whose total is what
// the cap is checked against; slots must not overlap or one chunk's readback
// would alias the other's while both are in flight.
static void testPinnedChunkLayout() {
    const size_t strips = 6 * 3838, payload = 33u << 20;
    for (int slots = 1; slots <= 2; slots++) {
        const PinnedChunkLayout L = pinnedChunkLayout(slots, payload, strips, 4);
        check(L.slots == slots, "layout keeps the slot count");
        struct R { size_t o, n; };
        std::vector<R> r;
        for (int j = 0; j < slots; j++) {
            r.push_back({L.payload[j], payload});
            r.push_back({L.cptr[j], strips * sizeof(void *)});
            r.push_back({L.csize[j], strips * sizeof(size_t)});
            r.push_back({L.dptr[j], strips * sizeof(void *)});
            r.push_back({L.dsize[j], strips * sizeof(size_t)});
            r.push_back({L.status[j], strips * 4});
            r.push_back({L.asize[j], strips * sizeof(size_t)});
            r.push_back({L.adler[j], strips * sizeof(uint32_t)});
        }
        bool disjoint = true, inside = true, aligned = true;
        for (size_t a = 0; a < r.size(); a++) {
            if (r[a].o + r[a].n > L.total) inside = false;
            if (r[a].o % 8) aligned = false;
            for (size_t b = a + 1; b < r.size(); b++)
                if (r[a].o < r[b].o + r[b].n && r[b].o < r[a].o + r[a].n) disjoint = false;
        }
        check(disjoint, "pinned chunk regions are disjoint");
        check(inside, "every pinned chunk region lies inside the checked total");
        check(aligned, "pinned descriptor tables are naturally aligned");
    }
    check(pinnedChunkLayout(0, payload, strips, 4).total == 0, "zero slots is refused");
    check(pinnedChunkLayout(3, payload, strips, 4).total == 0, "three slots is refused");
    // Tutorial movie at the default chunking stays inside the default 256 MiB cap:
    // two 6-frame slots of ~33 MiB payload plus tables, reserved with headroom.
    const PinnedChunkLayout T = pinnedChunkLayout(2, (size_t)6 * 5480000u, strips, 4);
    check(pinnedReserveBytes(T.total) <= ((size_t)256 << 20),
          "default chunking of the tutorial movie fits the default pinned cap");
}

static void testChunkParameters() {
    check(defaultChunkFrames(24) == 6, "24 frames -> 6-frame chunks");
    check(defaultChunkFrames(1) == 1, "1 frame -> 1-frame chunk");
    check(defaultChunkFrames(6) == 2, "6 frames -> 2-frame chunks");
    check(pipelineSlots(24, 6) == 2, "several chunks use two slots");
    check(pipelineSlots(24, 24) == 1, "one chunk uses one slot");
    check(pipelineSlots(5, 0) == 0, "zero chunk size is refused");
    int v = 0;
    check(parsePositiveInt("6", v) && v == 6, "chunk env parses 6");
    check(!parsePositiveInt("0", v), "chunk env refuses 0");
    check(!parsePositiveInt("6x", v), "chunk env refuses junk");
    check(!parsePositiveInt("", v), "chunk env refuses empty");
    check(!parsePositiveInt("99999999999", v), "chunk env refuses overflow");
}

int main() {
    testSlotAlignment(4);
    testSlotAlignment(8);
    testSlotAlignment(16);
    testDensePackingIsRejected(4);
    testDensePackingIsRejected(8);
    testZlibWrapper();
    testArenaFitsTutorialMovie();
    testPinnedBudgetBoundsWhatIsPinned();
    testPinnedCapParsing();
    for (size_t a : {(size_t)1, (size_t)4, (size_t)8, (size_t)16})
        for (unsigned seed : {1u, 7u, 99u})
            testSpreadEqualsDirectPlacement(a, seed, 600);
    testSpreadEqualsDirectPlacement(4, 3u, 3838);
    testPinnedChunkLayout();
    testChunkParameters();

    if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
    std::printf("deflate layout: all checks passed\n");
    return 0;
}
