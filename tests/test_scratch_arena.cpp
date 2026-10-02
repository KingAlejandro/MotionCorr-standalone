// Device-free control for the pre-FFT scratch arena and the d_Fframes storage rule.
//
// The nvCOMP ingest path does not allocate: it carves compressed, uint16 and
// descriptor views out of d_Fframes, which initialize() has already allocated for
// the spectrum and which nothing writes until computeGlobalForwardFFT(). Two
// mistakes are possible and neither reports an error where it is made -- running
// the transform while ingest views are live, and handing out scratch after the
// transform. Both corrupt the spectrum silently. The rule is therefore a checked
// state machine, and this is where it is exercised, since CI has no GPU.

#include "src/acc/cuda/cuda_scratch_arena.h"

#include <cstdio>
#include <cstdint>
#include <vector>

using namespace mc_cuda;

static int failures = 0;
static void check(bool cond, const char *what) {
    if (!cond) { std::printf("FAIL: %s\n", what); failures++; }
}

// Stand-in for a cudaMalloc base: 256-byte aligned, as the runtime guarantees.
static unsigned char *alignedBase(std::vector<unsigned char> &backing) {
    backing.assign(8192 + 256, 0);
    uintptr_t p = (uintptr_t)backing.data();
    return backing.data() + (size_t)((256 - (p % 256)) % 256);
}

static void testArenaAlignmentAndPacking() {
    std::vector<unsigned char> backing;
    unsigned char *base = alignedBase(backing);
    DeviceScratchArena arena(base, 8192);

    check(arena.valid() && arena.capacity() == 8192 && arena.used() == 0, "fresh arena state");

    unsigned char *a = (unsigned char *)arena.alloc(10, 4);
    unsigned char *b = (unsigned char *)arena.alloc(10, 4);
    unsigned char *c = (unsigned char *)arena.alloc(1, 256);
    check(a && b && c, "three allocations succeed");
    check(((uintptr_t)a % 4) == 0 && ((uintptr_t)b % 4) == 0, "4-byte requests are 4-aligned");
    check(((uintptr_t)c % 256) == 0, "256-byte request is 256-aligned");
    check(b >= a + 10, "second allocation does not overlap the first");
    check(c >= b + 10, "third allocation does not overlap the second");
    check(arena.used() == (size_t)(c + 1 - base), "used() tracks the high-water offset");
    check(arena.used() + arena.remaining() == arena.capacity(), "used + remaining == capacity");
}

static void testArenaRefusesRatherThanOverruns() {
    std::vector<unsigned char> backing;
    unsigned char *base = alignedBase(backing);
    DeviceScratchArena arena(base, 1024);

    check(arena.alloc(1025, 1) == 0, "refuses a request larger than capacity");
    check(arena.used() == 0, "a refused request consumes nothing");

    check(arena.alloc(1024, 1) != 0, "exact-capacity request succeeds");
    check(arena.alloc(1, 1) == 0, "refuses once full");

    arena.reset();
    check(arena.used() == 0, "reset returns the whole arena");
    check(arena.alloc(1024, 1) != 0, "the same bytes are reusable after reset");

    arena.reset();
    check(arena.alloc(8, 512) == 0, "refuses alignment coarser than cudaMalloc guarantees");
    check(arena.alloc(8, 3) == 0, "refuses a non-power-of-two alignment");
    check(arena.alloc(8, 0) == 0, "refuses a zero alignment");

    // Overflow must be detected on the aligned start, not the raw offset.
    arena.reset();
    check(arena.alloc(1020, 1) != 0, "fill to 1020 of 1024");
    check(arena.alloc(8, 8) == 0, "refuses when padding pushes the request past the end");

    DeviceScratchArena empty;
    check(!empty.valid() && empty.alloc(1, 1) == 0, "a default arena hands out nothing");
    DeviceScratchArena null_base(0, 4096);
    check(!null_base.valid() && null_base.capacity() == 0, "a null base yields no capacity");
}

static void testFourierStorageRule() {
    FourierStorageGuard g;
    check(g.state() == kFourierReadyForFFT, "starts ready for the transform");

    // Host-read path: no scratch is ever taken, the transform still runs.
    check(g.beginFourierWrite(), "transform allowed when no scratch was taken");
    check(g.state() == kFourierData, "buffer is marked as holding the spectrum");

    // After the spectrum exists, ingest scratch must be refused.
    check(!g.beginIngestScratch(), "scratch refused once the spectrum is in the buffer");
    check(g.state() == kFourierData, "a refused claim does not change the state");

    // nvCOMP path.
    FourierStorageGuard h;
    check(h.beginIngestScratch(), "scratch claimed from the ready state");
    check(h.state() == kFourierIngestScratch, "buffer is marked as ingest scratch");
    check(!h.beginIngestScratch(), "scratch cannot be claimed twice");

    // The refusal that matters: transform while views are live.
    check(!h.beginFourierWrite(), "transform refused while ingest scratch is live");
    check(h.state() == kFourierIngestScratch, "a refused transform does not change the state");

    check(h.finishIngestScratch(), "scratch released");
    check(h.state() == kFourierReadyForFFT, "buffer is ready for the transform again");
    check(!h.finishIngestScratch(), "releasing twice is refused");
    check(h.beginFourierWrite(), "transform allowed after release");

    h.reset();
    check(h.state() == kFourierReadyForFFT, "reset returns to the initial state");
}

int main() {
    testArenaAlignmentAndPacking();
    testArenaRefusesRatherThanOverruns();
    testFourierStorageRule();
    if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
    std::printf("scratch arena: all checks passed\n");
    return 0;
}
