// Device-free ownership controls for mc_cuda::PinnedStage, the worker-lifetime
// pinned staging buffer (hugepage mapping + cudaHostRegister, with a
// cudaHostAlloc fallback). Every OS and CUDA call goes through a counting fake,
// so the test sees each buffer's whole life: one owner, one free path, freed
// exactly once, and a clean ledger at the end.
//
//   test_pinned_stage                    all checks must pass
//   test_pinned_stage --expect-mismatch  exit 0 only if a check fails (compiled mutants)
#include "src/acc/cuda/cuda_pinned_stage.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>

using mc_cuda::PinnedBackend;
using mc_cuda::PinnedStage;

namespace {
int g_failures = 0;
void check(bool ok, const char *what) {
    if (!ok) {
        std::fprintf(stderr, "FAIL: %s\n", what);
        ++g_failures;
    }
}

// Ledger of the fake. Addresses are real heap blocks so each is distinct.
enum class State { Mapped, Registered, HostAllocated };
struct Ledger {
    std::map<void *, State> live;
    int maps = 0, unmaps = 0, registers = 0, unregisters = 0, host_allocs = 0, free_hosts = 0;
    int bad_frees = 0;          // a free on something not live, or via the wrong path
    bool fail_map = false, fail_register = false, fail_host_alloc = false;
    int fail_unregister_times = 0;
    void reset() { *this = Ledger(); }
} L;

void *fakeMap(size_t bytes) {
    ++L.maps;
    if (L.fail_map) return nullptr;
    void *p = std::malloc(bytes ? bytes : 1);
    L.live[p] = State::Mapped;
    return p;
}
int fakeUnmap(void *p, size_t) {
    ++L.unmaps;
    auto it = L.live.find(p);
    // Legal from Mapped (registration refused) and from Registered (after unpin).
    if (it == L.live.end() || it->second == State::HostAllocated) { ++L.bad_frees; return -1; }
    L.live.erase(it);
    std::free(p);
    return 0;
}
cudaError_t fakeRegister(void *p, size_t) {
    ++L.registers;
    if (L.fail_register) return cudaErrorHostMemoryAlreadyRegistered;
    auto it = L.live.find(p);
    if (it == L.live.end() || it->second != State::Mapped) return cudaErrorInvalidValue;
    it->second = State::Registered;
    return cudaSuccess;
}
cudaError_t fakeUnregister(void *p) {
    ++L.unregisters;
    auto it = L.live.find(p);
    if (it == L.live.end() || it->second != State::Registered) { ++L.bad_frees; return cudaErrorHostMemoryNotRegistered; }
    if (L.fail_unregister_times > 0) { --L.fail_unregister_times; return cudaErrorIllegalAddress; }
    it->second = State::Mapped;
    return cudaSuccess;
}
cudaError_t fakeHostAlloc(void **pp, size_t bytes) {
    ++L.host_allocs;
    if (L.fail_host_alloc) { *pp = nullptr; return cudaErrorMemoryAllocation; }
    void *p = std::malloc(bytes ? bytes : 1);
    L.live[p] = State::HostAllocated;
    *pp = p;
    return cudaSuccess;
}
cudaError_t fakeFreeHost(void *p) {
    ++L.free_hosts;
    auto it = L.live.find(p);
    if (it == L.live.end() || it->second != State::HostAllocated) { ++L.bad_frees; return cudaErrorInvalidValue; }
    L.live.erase(it);
    std::free(p);
    return cudaSuccess;
}
const PinnedBackend kFake = {fakeMap, fakeUnmap, fakeRegister, fakeUnregister, fakeHostAlloc, fakeFreeHost};

bool balanced() { return L.live.empty() && L.bad_frees == 0; }

void registeredLifecycle() {
    L.reset();
    {
        PinnedStage stage(kFake, true);
        bool fell_back = true;
        check(stage.acquire(64, &fell_back) == cudaSuccess, "registered: acquire succeeds");
        check(!fell_back && stage.kind() == PinnedStage::Kind::Registered, "registered: used the registered path");
        check(stage.data() != nullptr && stage.bytes() == 64, "registered: owns the requested bytes");
        check(L.maps == 1 && L.registers == 1 && L.host_allocs == 0, "registered: one map, one register, no hostAlloc");
        check(stage.release() == cudaSuccess && stage.data() == nullptr && stage.bytes() == 0,
              "registered: release clears ownership");
        check(L.unregisters == 1 && L.unmaps == 1 && L.free_hosts == 0,
              "registered: freed by unregister + unmap, not freeHost");
        check(stage.release() == cudaSuccess && L.unregisters == 1 && L.unmaps == 1,
              "registered: a second release frees nothing");
    }
    check(L.unregisters == 1 && L.unmaps == 1 && balanced(), "registered: destructor after release frees nothing more");
}

void destructorFreesHeldBufferOnce() {
    L.reset();
    {
        PinnedStage stage(kFake, true);
        stage.acquire(64);
    }
    check(L.unregisters == 1 && L.unmaps == 1 && balanced(), "destructor: a held registered buffer is freed once");
    L.reset();
    {
        PinnedStage stage(kFake, false);
        stage.acquire(64);
    }
    check(L.free_hosts == 1 && L.unmaps == 0 && balanced(), "destructor: a held hostAlloc buffer is freed once via freeHost");
}

void registrationRefusedFallsBack() {
    L.reset();
    L.fail_register = true;
    PinnedStage stage(kFake, true);
    bool fell_back = false;
    check(stage.acquire(64, &fell_back) == cudaSuccess, "fallback: acquire still succeeds");
    check(fell_back && stage.kind() == PinnedStage::Kind::HostAlloc, "fallback: reports and uses cudaHostAlloc");
    check(L.unmaps == 1 && L.host_allocs == 1, "fallback: the refused mapping was returned, then one hostAlloc");
    check(stage.release() == cudaSuccess, "fallback: release ok");
    check(L.free_hosts == 1 && L.unregisters == 0 && L.unmaps == 1, "fallback: freed via freeHost only, mapping not unmapped twice");
    check(balanced(), "fallback: ledger clean");
}

void mapFailureFallsBack() {
    L.reset();
    L.fail_map = true;
    PinnedStage stage(kFake, true);
    bool fell_back = false;
    check(stage.acquire(64, &fell_back) == cudaSuccess && fell_back, "map failure: falls back to hostAlloc");
    check(L.registers == 0 && L.unmaps == 0 && L.host_allocs == 1, "map failure: nothing to register or unmap");
    stage.release();
    check(balanced(), "map failure: ledger clean");
}

void registeredPinningCanBeDisabled() {
    L.reset();
    PinnedStage stage(kFake, false);
    bool fell_back = true;
    check(stage.acquire(64, &fell_back) == cudaSuccess && !fell_back, "disabled: reports no fallback");
    check(L.maps == 0 && L.registers == 0 && L.host_allocs == 1 && stage.kind() == PinnedStage::Kind::HostAlloc,
          "disabled: today's cudaHostAlloc path only");
    stage.release();
    check(balanced(), "disabled: ledger clean");
}

void oneOwnerAtATime() {
    L.reset();
    PinnedStage stage(kFake, true);
    stage.acquire(64);
    void *first = stage.data();
    const int maps = L.maps;
    check(stage.acquire(128) == cudaErrorInvalidValue, "single owner: acquire while held is refused");
    check(stage.data() == first && stage.bytes() == 64 && L.maps == maps && L.host_allocs == 0,
          "single owner: the held buffer and the backend are untouched");
    stage.release();
    check(balanced(), "single owner: ledger clean");
}

void growReleasesThenAcquires() {
    L.reset();
    PinnedStage stage(kFake, true);
    stage.acquire(64);
    check(stage.release() == cudaSuccess && stage.acquire(256) == cudaSuccess && stage.bytes() == 256,
          "grow: release then acquire a larger buffer");
    check(L.maps == 2 && L.unmaps == 1 && L.registers == 2 && L.unregisters == 1, "grow: the old buffer is gone before the new one counts");
    stage.release();
    check(balanced() && L.maps == L.unmaps && L.registers == L.unregisters, "grow: every buffer freed exactly once");
}

void allocationFailureHoldsNothing() {
    L.reset();
    L.fail_map = true;
    L.fail_host_alloc = true;
    PinnedStage stage(kFake, true);
    check(stage.acquire(64) == cudaErrorMemoryAllocation, "alloc failure: status returned");
    check(stage.data() == nullptr && stage.bytes() == 0 && stage.kind() == PinnedStage::Kind::None,
          "alloc failure: nothing is owned");
    check(stage.release() == cudaSuccess && L.free_hosts == 0 && L.unmaps == 0, "alloc failure: release frees nothing");
}

void failedUnpinKeepsOwnershipUntilRetried() {
    L.reset();
    PinnedStage stage(kFake, true);
    stage.acquire(64);
    L.fail_unregister_times = 1;
    check(stage.release() == cudaErrorIllegalAddress, "unpin failure: status returned");
    check(stage.data() != nullptr && stage.kind() == PinnedStage::Kind::Registered && L.unmaps == 0,
          "unpin failure: still owned, mapping not dropped under a live pin");
    check(stage.release() == cudaSuccess && L.unmaps == 1 && stage.data() == nullptr, "unpin failure: retry frees once");
    check(balanced(), "unpin failure: ledger clean");
}

void destructorUnmapsEvenIfUnpinFails() {
    L.reset();
    {
        PinnedStage stage(kFake, true);
        stage.acquire(64);
        L.fail_unregister_times = 1;
    }
    // On thread exit the context may be gone; the mapping must still be returned.
    check(L.unmaps == 1 && L.unregisters == 1, "destructor: mapping returned although the unpin failed");
}
}  // namespace

int main(int argc, char **argv) {
    const bool expect_mismatch = argc > 1 && std::strcmp(argv[1], "--expect-mismatch") == 0;
    registeredLifecycle();
    destructorFreesHeldBufferOnce();
    registrationRefusedFallsBack();
    mapFailureFallsBack();
    registeredPinningCanBeDisabled();
    oneOwnerAtATime();
    growReleasesThenAcquires();
    allocationFailureHoldsNothing();
    failedUnpinKeepsOwnershipUntilRetried();
    destructorUnmapsEvenIfUnpinFails();
    if (expect_mismatch) {
        std::printf("%s: %d check(s) failed as the mutant should\n", g_failures ? "OK" : "MUTANT SURVIVED",
                    g_failures);
        return g_failures ? 0 : 1;
    }
    if (g_failures) return 1;
    std::printf("PASS pinned stage ownership\n");
    return 0;
}
