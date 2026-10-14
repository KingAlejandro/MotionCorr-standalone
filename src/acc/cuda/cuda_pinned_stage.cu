#include "src/acc/cuda/cuda_pinned_stage.h"

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>

namespace mc_cuda {
namespace {

constexpr size_t kHugePage = (size_t)2 << 20;

size_t roundUpHuge(size_t bytes) { return (bytes + kHugePage - 1) & ~(kHugePage - 1); }

// An anonymous mapping whose start is 2 MiB aligned, so THP can back all of it.
// The over-allocated head and tail are returned immediately.
void *mapHuge(size_t bytes) {
    const size_t len = roundUpHuge(bytes);
    const size_t span = len + kHugePage;
    void *raw = mmap(nullptr, span, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) return nullptr;
    const uintptr_t base = (uintptr_t)raw;
    const uintptr_t aligned = (base + kHugePage - 1) & ~(uintptr_t)(kHugePage - 1);
    if (aligned > base) munmap(raw, aligned - base);
    const uintptr_t end = base + span;
    if (end > aligned + len) munmap((void *)(aligned + len), end - (aligned + len));
#ifdef MADV_HUGEPAGE
    // Advisory: refused or ignored (THP=never) just means 4 KiB pages.
    madvise((void *)aligned, len, MADV_HUGEPAGE);
#endif
    return (void *)aligned;
}

int unmapHuge(void *ptr, size_t bytes) { return munmap(ptr, roundUpHuge(bytes)); }

cudaError_t systemRegister(void *ptr, size_t bytes) {
    return cudaHostRegister(ptr, bytes, cudaHostRegisterDefault);
}
cudaError_t systemUnregister(void *ptr) { return cudaHostUnregister(ptr); }
cudaError_t systemHostAlloc(void **ptr, size_t bytes) {
    return cudaHostAlloc(ptr, bytes, cudaHostAllocDefault);
}
cudaError_t systemFreeHost(void *ptr) { return cudaFreeHost(ptr); }

}  // namespace

const PinnedBackend &PinnedBackend::system() {
    static const PinnedBackend backend = {mapHuge, unmapHuge, systemRegister, systemUnregister,
                                          systemHostAlloc, systemFreeHost};
    return backend;
}

bool PinnedStage::defaultPreferRegistered() {
    const char *env = std::getenv("MOTIONCORR_PINNED_REGISTER");
    return !(env != nullptr && env[0] == '0' && env[1] == '\0');
}

cudaError_t PinnedStage::acquire(size_t bytes, bool *fell_back) {
    if (fell_back) *fell_back = false;
    if (ptr_ != nullptr || bytes == 0) return cudaErrorInvalidValue;

    if (prefer_registered_) {
        if (void *mapped = backend_->map(bytes)) {
            const cudaError_t reg = backend_->registerHost(mapped, bytes);
            if (reg == cudaSuccess) {
                ptr_ = mapped;
                bytes_ = bytes;
                kind_ = Kind::Registered;
                return cudaSuccess;
            }
            // Registration refused: drop the mapping and fall through to
            // cudaHostAlloc. The refused call left its own status in the runtime's
            // per-thread last-error slot, which the fallback path never raised, so
            // clear it -- but only when it is that status, never an older pending
            // error someone else may still read.
            backend_->unmap(mapped, bytes);
            if (cudaPeekAtLastError() == reg) (void)cudaGetLastError();
        }
        if (fell_back) *fell_back = true;
    }

    void *allocated = nullptr;
    const cudaError_t status = backend_->hostAlloc(&allocated, bytes);
    if (status != cudaSuccess) return status;
    ptr_ = allocated;
    bytes_ = bytes;
    kind_ = Kind::HostAlloc;
    return cudaSuccess;
}

cudaError_t PinnedStage::release(bool force_unmap) {
    if (ptr_ == nullptr) return cudaSuccess;
    cudaError_t status = cudaSuccess;
    if (kind_ == Kind::Registered) {
        status = backend_->unregisterHost(ptr_);
        if (status != cudaSuccess && !force_unmap) return status;
        backend_->unmap(ptr_, bytes_);
    } else {
        status = backend_->freeHost(ptr_);
        if (status != cudaSuccess) return status;
    }
    ptr_ = nullptr;
    bytes_ = 0;
    kind_ = Kind::None;
    return status;
}

}  // namespace mc_cuda
