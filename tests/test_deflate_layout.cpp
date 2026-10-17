// Device-free control for the nvCOMP Deflate ingestion staging layout.
//
// The two properties tested here are the ones a successful run on the device cannot
// establish. A misaligned nvCOMP input pointer is undefined behaviour that decoded
// correctly on A100, so "all pixels matched" is not evidence the alignment rule
// holds; and an unvalidated zlib wrapper only matters on input that never reached
// the benchmark. Both are pure integer/byte logic, so they are checked here rather
// than behind a GPU and an nvCOMP install.

#include "src/acc/cuda/cuda_checked_arith.h"
#include "src/acc/cuda/cuda_deflate_layout.h"

#include <climits>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <limits>
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


// ---------------------------------------------------------------------------
// Checked arithmetic (#134 item 2 / RC0 T3).
//
// Sizes and offsets on the nvCOMP admission path come from the TIFF tags, and the
// scratch arena's capacity test cannot see a size that already wrapped. Each
// hardened computation is checked at the largest value that fits (accepted, and
// equal to the exact result) and one past it (declined, destination untouched).
// The compiled mutants in CMakeLists.txt remove each check in turn and must turn
// this red, so a check that the boundaries below do not reach is not left behind.
// ---------------------------------------------------------------------------
#ifndef __SIZEOF_INT128__
#error "the boundary oracle needs a 128-bit integer type"
#endif
typedef unsigned __int128 u128;
// Upper midpoint offset of a span, without the span + 1 that wraps when the span is 2^64 - 1.
static size_t upperMid(size_t span) { return span / 2 + span % 2; }
static const size_t SZ_MAX = std::numeric_limits<size_t>::max();
static const uint64_t U64_MAX = std::numeric_limits<uint64_t>::max();

static void testCheckedAddMulAlign() {
    using namespace mc_checked;
    size_t r = 7;
    check(addSize(SZ_MAX - 5, 5, r) && r == SZ_MAX, "addSize accepts a sum equal to SIZE_MAX");
    r = 7;
    check(!addSize(SZ_MAX - 5, 6, r) && r == 7, "addSize declines SIZE_MAX + 1 and leaves out untouched");
    check(!addSize(SZ_MAX, 1, r) && addSize(SZ_MAX, 0, r) && r == SZ_MAX, "addSize at SIZE_MAX");
    check(!addSize(SZ_MAX / 2 + 1, SZ_MAX / 2 + 1, r), "addSize declines a sum that wraps to a small value");

    uint64_t u = 7;
    check(addU64(U64_MAX - 5, 5, u) && u == U64_MAX, "addU64 accepts a sum equal to UINT64_MAX");
    u = 7;
    check(!addU64(U64_MAX - 5, 6, u) && u == 7, "addU64 declines UINT64_MAX + 1");
    check(!addU64(U64_MAX, U64_MAX, u), "addU64 declines a doubling");

    r = 7;
    check(mulSize((size_t)1 << 32, ((size_t)1 << 32) - 1, r) && r == SZ_MAX - ((size_t)1 << 32) + 1,
          "mulSize accepts 2^32 * (2^32 - 1)");
    r = 7;
    check(!mulSize((size_t)1 << 32, (size_t)1 << 32, r) && r == 7, "mulSize declines 2^64, which wraps to 0");
    check(mulSize(SZ_MAX, 1, r) && r == SZ_MAX && mulSize(0, SZ_MAX, r) && r == 0 && mulSize(SZ_MAX, 0, r) && r == 0,
          "mulSize with 0 and 1 never declines");
    check(!mulSize(SZ_MAX, 2, r), "mulSize declines SIZE_MAX * 2");
    for (size_t b : {(size_t)3, (size_t)8, (size_t)48, (size_t)4096, (size_t)5480000u, (size_t)1 << 31}) {
        const size_t a = SZ_MAX / b;      // largest factor that still fits
        r = 0;
        check(mulSize(a, b, r) && (u128)r == (u128)a * b, "mulSize accepts the largest fitting factor");
        check(!mulSize(a + 1, b, r), "mulSize declines one past the largest fitting factor");
    }

    // alignment: the largest multiple of 64 below 2^64 is SIZE_MAX - 63.
    r = 7;
    check(alignUpChecked(SZ_MAX - 63, 64, r) && r == SZ_MAX - 63, "alignUpChecked keeps the largest aligned value");
    check(!alignUpChecked(SZ_MAX - 62, 64, r) && r == SZ_MAX - 63, "alignUpChecked declines a round-up past 2^64 and leaves out untouched");
    check(!alignUpChecked(SZ_MAX, 256, r), "alignUpChecked declines SIZE_MAX at 256");
    check(alignUpChecked(SZ_MAX, 1, r) && r == SZ_MAX && alignUpChecked(SZ_MAX, 0, r) && r == SZ_MAX,
          "alignment 0 and 1 are the identity, even at SIZE_MAX");
    check(alignUpChecked(0, 64, r) && r == 0 && alignUpChecked(1, 64, r) && r == 64 && alignUpChecked(64, 64, r) && r == 64 &&
          alignUpChecked(65, 64, r) && r == 128, "alignUpChecked agrees with the exact round-up on ordinary values");
    // Control: the unchecked helper really does wrap here, so the case above is a
    // property of the check and not of the value chosen.
    check(mc_cuda::alignUp(SZ_MAX - 62, 64) == 0, "control: the unchecked alignUp wraps to 0");
}

static void testConvertExact() {
    using namespace mc_checked;
    int i = 7; unsigned u32 = 7; int64_t i64 = 7; uint64_t u64 = 7; int16_t i16 = 7; uint16_t u16 = 7;
    check(convertExact((size_t)INT_MAX, i) && i == INT_MAX, "size_t INT_MAX -> int accepted");
    i = 7;
    check(!convertExact((size_t)INT_MAX + 1, i) && i == 7, "size_t INT_MAX+1 -> int declined, out untouched");
    // 2^32 + 5 truncates to 5: a plain (int) cast would turn this into a valid-looking 5.
    check(!convertExact(((size_t)1 << 32) + 5, i), "size_t 2^32+5 -> int declined (a cast would give 5)");
    check(!convertExact((size_t)UINT32_MAX, i), "size_t UINT32_MAX -> int declined");
    check(convertExact((size_t)UINT32_MAX, u32) && u32 == UINT32_MAX, "size_t UINT32_MAX -> uint32 accepted");
    check(!convertExact((size_t)UINT32_MAX + 1, u32), "size_t UINT32_MAX+1 -> uint32 declined");
    // Sign changes whose bit pattern survives the round trip.
    check(!convertExact(-1, u32), "int -1 -> unsigned declined");
    check(!convertExact((int64_t)-1, u64), "int64 -1 -> uint64 declined");
    check(!convertExact(INT_MIN, u64), "int INT_MIN -> uint64 declined");
    check(convertExact((int64_t)0, u64) && u64 == 0, "int64 0 -> uint64 accepted");
    check(!convertExact((uint64_t)1 << 63, i64), "uint64 2^63 -> int64 declined");
    check(convertExact(((uint64_t)1 << 63) - 1, i64) && i64 == INT64_MAX, "uint64 2^63-1 -> int64 accepted");
    check(!convertExact(U64_MAX, i64), "uint64 UINT64_MAX -> int64 declined");
    check(convertExact((int64_t)INT_MIN, i) && i == INT_MIN, "int64 INT_MIN -> int accepted");
    check(!convertExact((int64_t)INT_MIN - 1, i), "int64 INT_MIN-1 -> int declined");
    check(convertExact((uint32_t)65535, u16) && u16 == 65535, "uint32 65535 -> uint16 accepted");
    check(!convertExact((uint32_t)65536, u16), "uint32 65536 -> uint16 declined");
    check(convertExact(32767, i16) && !convertExact(32768, i16), "int -> int16 boundary");
    off_t o = 7;
    check(convertExact((uint64_t)std::numeric_limits<off_t>::max(), o) && o == std::numeric_limits<off_t>::max(),
          "uint64 off_t max -> off_t accepted");
    o = 7;
    check(!convertExact((uint64_t)std::numeric_limits<off_t>::max() + 1, o) && o == 7,
          "uint64 off_t max + 1 -> off_t declined: the (off_t) cast would give a negative position");
}

static void testFileSpanFitsOffT() {
    using namespace mc_checked;
    const uint64_t omax = (uint64_t)std::numeric_limits<off_t>::max();
    check(fileSpanFitsOffT(0, 0) && fileSpanFitsOffT(1000, 1300), "an ordinary strip span fits");
    check(fileSpanFitsOffT(omax - 100, 100), "a span ending exactly at the off_t maximum fits");
    check(!fileSpanFitsOffT(omax - 100, 101), "a span ending one past the off_t maximum is declined");
    check(fileSpanFitsOffT(omax, 0) && !fileSpanFitsOffT(omax, 1), "start at the off_t maximum");
    check(!fileSpanFitsOffT(omax + 1, 0), "a start above the off_t maximum is declined even with no bytes");
    // Wrapping end: offset + n wraps to a small, perfectly valid-looking number.
    check(!fileSpanFitsOffT(U64_MAX - 9, 20), "offset 2^64-10 + 20 wraps to 9 and is declined");
    check(!fileSpanFitsOffT(5, U64_MAX - 3), "a length that wraps the end past 2^64 is declined");
    // Start representable, sum does not wrap, but the end is not an off_t.
    check(!fileSpanFitsOffT(1, omax + 1), "start fine, end past the off_t maximum, no 64-bit wrap");
}

static void testCeilDivInt() {
    using namespace mc_checked;
    // volatile: the original (a + b - 1) / b is signed overflow at these values, and
    // a constant-folded call would let the compiler choose what it means.
    volatile int vmax = INT_MAX, v1 = 1, v2 = 2, v4 = 4, vhalf = 1 << 30;
    check(ceilDivInt(vmax, v4) == 536870912, "ceilDivInt(INT_MAX, 4)");
    check(ceilDivInt(vmax, v2) == 1073741824, "ceilDivInt(INT_MAX, 2)");
    check(ceilDivInt(vmax, v1) == INT_MAX, "ceilDivInt(INT_MAX, 1)");
    check(ceilDivInt(vmax, vmax) == 1, "ceilDivInt(INT_MAX, INT_MAX)");
    check(ceilDivInt(24, 6) == 4 && ceilDivInt(25, 6) == 5 && ceilDivInt(0, 3) == 0 && ceilDivInt(1, 3) == 1,
          "ceilDivInt ordinary values");
    check(ceilDivInt(5, 0) == 0 && ceilDivInt(-1, 2) == 0, "ceilDivInt refuses a non-positive divisor or negative dividend");
    check(defaultChunkFrames(vmax) == 536870912, "defaultChunkFrames at INT_MAX frames (was signed overflow)");
    // n + 3 first exceeds INT_MAX at n = INT_MAX - 2.
    check(defaultChunkFrames(vmax - 2) == 536870912 && defaultChunkFrames(vmax - 3) == 536870911,
          "defaultChunkFrames agrees with exact ceil(n/4) around the old overflow point");
    check(pipelineSlots(vmax, vmax) == 1, "one chunk of INT_MAX frames uses one slot");
    check(pipelineSlots(vmax, vhalf) == 2, "two chunks at INT_MAX frames use two slots (was signed overflow)");
    check(pipelineSlots(vmax, vmax - 1) == 2, "chunk of INT_MAX-1 frames out of INT_MAX uses two slots");
}

// The pipeline loop visits k = 0..n_chunks inclusive. At n_chunks == INT_MAX the old
// `k <= n_chunks; k++` incremented past INT_MAX; the step helper must stop there.
static void testAdvancePipelineStep() {
    using namespace mc_checked;
    volatile int vmax = INT_MAX;
    int k = vmax - 1;
    check(advancePipelineStep(k, vmax) && k == INT_MAX, "step reaches INT_MAX from INT_MAX-1");
    check(!advancePipelineStep(k, vmax) && k == INT_MAX, "step stops at INT_MAX without incrementing past it");
    k = 0;
    check(advancePipelineStep(k, 1) && k == 1 && !advancePipelineStep(k, 1) && k == 1, "one chunk: steps 0 and 1");
    k = 0;
    check(!advancePipelineStep(k, 0) && k == 0, "zero chunks: only step 0");
    for (int n : {1, 2, 4, 5}) {
        int visits = 0;
        // Bounded: a helper that never stops must fail this check, not hang the test.
        for (int i = 0; visits <= n + 2; ) { visits++; if (!advancePipelineStep(i, n)) break; }
        check(visits == n + 1, "the loop visits exactly n_chunks + 1 steps");
    }
}

static void testCheckedStripSlotAndFrameStage() {
    size_t r = 7;
    // Largest cursor that fits at alignment 8: cursor+2 must round up to <= SIZE_MAX - 7.
    check(checkedStripSlotOffset(SZ_MAX - 9, 8, r) && r == SZ_MAX - 9, "slot offset at the largest fitting cursor");
    r = 7;
    check(!checkedStripSlotOffset(SZ_MAX - 8, 8, r) && r == 7, "slot offset one past it is declined (round-up wraps)");
    check(!checkedStripSlotOffset(SZ_MAX - 1, 1, r), "cursor + 2 wrapping is declined even with no alignment");
    check(checkedStripSlotOffset(SZ_MAX - 2, 1, r) && r == SZ_MAX - 2, "cursor + 2 == SIZE_MAX is accepted at alignment 1");
    check(!checkedStripSlotOffset(SZ_MAX, 4, r), "cursor SIZE_MAX is declined");

    // Agrees with the unchecked replay everywhere the latter is valid.
    bool agree = true;
    for (size_t align : {(size_t)1, (size_t)2, (size_t)4, (size_t)8, (size_t)16, (size_t)256})
        for (size_t c = 0; c < 600 && agree; c++) {
            size_t got = 0;
            agree = checkedStripSlotOffset(c, align, got) && got == stripSlotOffset(c, align);
        }
    check(agree, "checkedStripSlotOffset equals stripSlotOffset on ordinary cursors");

    // Frame sum, driven past 2^64 with synthetic 64-bit sizes (a real frame cannot
    // hold 2^32 strips of 2^32 bytes).
    auto fixed = [](const std::vector<size_t> &v) { return [&v](size_t s) { return v[s]; }; };
    {
        std::vector<size_t> ok2 = { (size_t)1 << 63, ((size_t)1 << 63) - 1 };
        r = 7;
        check(checkedFrameStageBytesFrom(fixed(ok2), 2, 1, r) && r == SZ_MAX, "stage sum reaching SIZE_MAX exactly is accepted");
        std::vector<size_t> over2 = { (size_t)1 << 63, (size_t)1 << 63 };
        r = 7;
        check(!checkedFrameStageBytesFrom(fixed(over2), 2, 1, r) && r == 7, "stage sum of 2^64 is declined and out untouched");
        // Overflow caused only by the alignment padding of the second slot.
        std::vector<size_t> pad = { SZ_MAX - 100 };
        check(checkedFrameStageBytesFrom(fixed(pad), 1, 8, r) && r == SZ_MAX - 94, "one huge strip plus 6 bytes of slot padding fits");
        std::vector<size_t> pad_over = { SZ_MAX - 4 };
        check(!checkedFrameStageBytesFrom(fixed(pad_over), 1, 8, r), "one huge strip whose slot padding wraps the sum is declined");
        // The running cursor, not just the final add, must be checked at every strip.
        // Strip 0 ends at SIZE_MAX - 3 without wrapping; strip 1's slot offset does.
        std::vector<size_t> mid = { SZ_MAX - 9, 0 };
        check(!checkedFrameStageBytesFrom(fixed(mid), 2, 8, r), "a later slot offset that wraps is declined");
    }
    // Production wrapper, uint32 sizes.
    const std::vector<uint32_t> sizes = tutorialStripSizes(3838, 7u);
    for (size_t align : {(size_t)1, (size_t)4, (size_t)8, (size_t)16}) {
        size_t got = 0;
        check(checkedFrameStageBytes(sizes.data(), 3838, align, got) &&
              got == frameStageBytes(sizes.data(), 3838, align),
              "checkedFrameStageBytes equals frameStageBytes on a tutorial-sized frame");
        check(got >= framePackedBytes(sizes.data(), 3838),
              "the staged size bounds the packed size, so framePackedBytes cannot wrap after it is accepted");
    }
    size_t got = 7;
    check(checkedFrameStageBytes(sizes.data(), 0, 8, got) && got == 0, "an empty frame stages zero bytes");
    check(!checkedFrameStageBytes(sizes.data(), -1, 8, got), "a negative strip count is declined");
    const uint32_t maxes[3] = { UINT32_MAX, UINT32_MAX, UINT32_MAX };
    check(checkedFrameStageBytes(maxes, 3, 8, got) && got == frameStageBytes(maxes, 3, 8),
          "three 4 GiB strips are accepted and equal the unchecked sum");
}

static void testCheckedPinnedReserve() {
    size_t r = 7;
    const size_t gran = (size_t)32 << 20;
    // Largest request whose 12.5% headroom and 32 MiB round-up are both representable.
    size_t lo = 0, hi = SZ_MAX;
    while (lo < hi) {
        const size_t mid = lo + upperMid(hi - lo);
        const u128 padded = (u128)mid + mid / 8;
        const u128 rounded = (padded + gran - 1) / gran * gran;
        if (rounded <= (u128)SZ_MAX) lo = mid; else hi = mid - 1;
    }
    r = 7;
    check(checkedPinnedReserveBytes(lo, r) && r % gran == 0 && (u128)r >= (u128)lo + lo / 8,
          "reservation at the largest fitting request is accepted");
    r = 7;
    check(!checkedPinnedReserveBytes(lo + 1, r) && r == 7, "one byte more is declined and out untouched");
    check(pinnedReserveBytes(lo + 1) == SZ_MAX, "the saturating form returns SIZE_MAX, which no pinned cap admits");
    check(!checkedPinnedReserveBytes(SZ_MAX - 10, r), "bytes + bytes/8 wrapping is declined");
    check(!checkedPinnedReserveBytes(SZ_MAX, r), "SIZE_MAX is declined");
    // Ordinary values: identical to the formula the pool has always used.
    bool same = true;
    for (size_t b : {(size_t)0, (size_t)1, (size_t)1000, (size_t)33u << 20, (size_t)256 << 20, (size_t)5 << 30}) {
        size_t got = 0;
        const size_t want = ((b + b / 8) + gran - 1) / gran * gran;
        same = same && checkedPinnedReserveBytes(b, got) && got == want && pinnedReserveBytes(b) == want;
    }
    check(same, "reservation equals ceil((b + b/8) / 32 MiB) * 32 MiB on ordinary requests");
}

// Independent oracle for the pinned layout: the same sequence of slots, computed
// in 128 bits, so "fits in size_t" is decided by arithmetic and not by the code
// under test. Returns false if any offset or the total exceeds SIZE_MAX.
static bool oracleLayout(int slots, size_t payload, size_t strips, size_t status_bytes,
                         std::vector<u128> &offs, u128 &total) {
    u128 cur = 0;
    offs.clear();
    auto take = [&](u128 bytes) { const u128 o = (cur + 63) / 64 * 64; cur = o + bytes; offs.push_back(o); };
    for (int j = 0; j < slots; j++) take(payload);
    for (int j = 0; j < slots; j++) {
        take((u128)strips * sizeof(void *));   take((u128)strips * sizeof(size_t));
        take((u128)strips * sizeof(void *));   take((u128)strips * sizeof(size_t));
        take((u128)strips * status_bytes);     take((u128)strips * sizeof(size_t));
        take((u128)strips * sizeof(uint32_t));
    }
    total = (cur + 63) / 64 * 64;
    for (u128 o : offs) if (o > (u128)SZ_MAX) return false;
    return total <= (u128)SZ_MAX;
}

static void checkLayoutAgainstOracle(int slots, size_t payload, size_t strips, size_t status_bytes,
                                     const char *what) {
    std::vector<u128> offs; u128 total = 0;
    const bool fits = oracleLayout(slots, payload, strips, status_bytes, offs, total);
    PinnedChunkLayout L;
    const bool ok = checkedPinnedChunkLayout(slots, payload, strips, status_bytes, L);
    char msg[160];
    std::snprintf(msg, sizeof(msg), "layout fits == oracle (%s)", what);
    check(ok == fits, msg);
    if (!ok) {
        std::snprintf(msg, sizeof(msg), "a declined layout is empty (%s)", what);
        check(L.total == 0 && L.slots == 0, msg);
        const PinnedChunkLayout W = pinnedChunkLayout(slots, payload, strips, status_bytes);
        check(W.total == 0, "pinnedChunkLayout reports a declined layout as total == 0");
        return;
    }
    size_t k = 0;
    bool same = (u128)L.total == total;
    for (int j = 0; j < slots; j++) same = same && (u128)L.payload[j] == offs[k++];
    for (int j = 0; j < slots; j++) {
        same = same && (u128)L.cptr[j] == offs[k++] && (u128)L.csize[j] == offs[k++] &&
               (u128)L.dptr[j] == offs[k++] && (u128)L.dsize[j] == offs[k++] &&
               (u128)L.status[j] == offs[k++] && (u128)L.asize[j] == offs[k++] &&
               (u128)L.adler[j] == offs[k++];
    }
    std::snprintf(msg, sizeof(msg), "an accepted layout holds the exact offsets (%s)", what);
    check(same, msg);
}

static void testCheckedPinnedChunkLayout() {
    // Ordinary and tutorial layouts are unchanged: exact offsets from the oracle.
    for (int slots = 1; slots <= 2; slots++) {
        checkLayoutAgainstOracle(slots, 0, 0, 4, "empty");
        checkLayoutAgainstOracle(slots, (size_t)33 << 20, (size_t)6 * 3838, 4, "tutorial");
        checkLayoutAgainstOracle(slots, 12345, 7, 4, "odd sizes");
    }
    // Table product wraps on its own: strips * 8 == 2^64.
    checkLayoutAgainstOracle(1, 0, (size_t)1 << 61, 4, "strips*8 == 2^64");
    checkLayoutAgainstOracle(2, 0, SZ_MAX / 8 + 1, 4, "strips just past SIZE_MAX/8");
    // The status table is the one whose element size is a parameter.
    checkLayoutAgainstOracle(1, 0, SZ_MAX / 4 + 1, 4, "status table wraps");
    checkLayoutAgainstOracle(1, 0, 1000, SZ_MAX, "status element size wraps");
    // Payload so large that its slot, or the alignment after it, passes 2^64.
    checkLayoutAgainstOracle(1, SZ_MAX - 10, 1, 4, "payload round-up wraps");
    checkLayoutAgainstOracle(2, SZ_MAX / 2 + 100, 1, 4, "two payload slots wrap the cursor");
    checkLayoutAgainstOracle(2, SZ_MAX / 2 - 100, 1, 4, "two payload slots near the limit");
    // Largest payload that fits, found by bisection against the oracle itself, and one more.
    for (int slots = 1; slots <= 2; slots++) {
        std::vector<u128> offs; u128 total;
        size_t lo = 0, hi = SZ_MAX;
        while (lo < hi) {
            const size_t mid = lo + upperMid(hi - lo);
            if (oracleLayout(slots, mid, 5, 4, offs, total)) lo = mid; else hi = mid - 1;
        }
        PinnedChunkLayout L;
        check(checkedPinnedChunkLayout(slots, lo, 5, 4, L) && L.total != 0, "largest fitting payload is accepted");
        check(!checkedPinnedChunkLayout(slots, lo + 1, 5, 4, L), "payload one byte larger is declined");
        checkLayoutAgainstOracle(slots, lo, 5, 4, "largest fitting payload");
        checkLayoutAgainstOracle(slots, lo + 1, 5, 4, "largest fitting payload + 1");
        // Same for the strip count, which scales seven tables per slot.
        lo = 0; hi = SZ_MAX;
        while (lo < hi) {
            const size_t mid = lo + upperMid(hi - lo);
            if (oracleLayout(slots, 4096, mid, 4, offs, total)) lo = mid; else hi = mid - 1;
        }
        check(checkedPinnedChunkLayout(slots, 4096, lo, 4, L), "largest fitting strip count is accepted");
        check(!checkedPinnedChunkLayout(slots, 4096, lo + 1, 4, L), "strip count one larger is declined");
        checkLayoutAgainstOracle(slots, 4096, lo, 4, "largest fitting strip count");
        checkLayoutAgainstOracle(slots, 4096, lo + 1, 4, "largest fitting strip count + 1");
    }
    // An unsupported slot count is a refusal, not an overflow: ok with total == 0.
    PinnedChunkLayout L;
    check(checkedPinnedChunkLayout(3, 100, 100, 4, L) && L.total == 0, "three slots: not an overflow, total == 0");
    check(checkedPinnedChunkLayout(0, 100, 100, 4, L) && L.total == 0, "zero slots: not an overflow, total == 0");
}

// Arena: an aligned start that wraps past 2^64 must not come back as offset 0.
static void testArenaAlignedStartCannotWrap() {
    // A fake base, never dereferenced: only offsets are compared.
    mc_cuda::DeviceScratchArena arena((void *)(uintptr_t)256, SZ_MAX);
    check(arena.alloc(SZ_MAX - 100, 1) != 0 && arena.used() == SZ_MAX - 100,
          "a near-SIZE_MAX first allocation is handed out");
    check(arena.alloc(1, 256) == 0 && arena.used() == SZ_MAX - 100,
          "the next aligned start would wrap to 0: refused, not returned as the arena base");
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
    testCheckedAddMulAlign();
    testConvertExact();
    testFileSpanFitsOffT();
    testCeilDivInt();
    testAdvancePipelineStep();
    testCheckedStripSlotAndFrameStage();
    testCheckedPinnedReserve();
    testCheckedPinnedChunkLayout();
    testArenaAlignedStartCannotWrap();

    if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
    std::printf("deflate layout: all checks passed\n");
    return 0;
}
