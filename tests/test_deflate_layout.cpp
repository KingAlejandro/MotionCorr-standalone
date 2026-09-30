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

int main() {
    testSlotAlignment(4);
    testSlotAlignment(8);
    testSlotAlignment(16);
    testDensePackingIsRejected(4);
    testDensePackingIsRejected(8);
    testZlibWrapper();
    testArenaFitsTutorialMovie();

    if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
    std::printf("deflate layout: all checks passed\n");
    return 0;
}
