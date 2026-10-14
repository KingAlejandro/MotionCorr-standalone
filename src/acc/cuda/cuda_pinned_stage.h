/***************************************************************************
 * Worker-lifetime pinned host staging buffer, with one owner and one free path.
 *
 * Pinning a fresh buffer with cudaHostAlloc costs ~120 ms for 128 MiB on a host
 * with THP=madvise (cudaFreeHost another ~46 ms). A hugepage-advised anonymous
 * mapping pinned in place with cudaHostRegister costs ~26 ms (unregister ~7 ms)
 * for the same bytes, because the kernel builds it from 2 MiB pages.
 *
 * PinnedStage owns exactly one buffer at a time. It is either
 *   - Registered : an mmap'd region pinned with cudaHostRegister, released by
 *                  cudaHostUnregister then munmap; or
 *   - HostAlloc  : cudaHostAlloc memory, released by cudaFreeHost
 * and release() frees it through the path that created it, exactly once. If
 * registration is unavailable or fails, acquire() unmaps and falls back to
 * cudaHostAlloc, which is the path before this class existed.
 *
 * The CUDA and OS calls go through PinnedBackend so a device-free test can
 * count them.
 *
 * This file is part of MotionCorr, distributed under the GNU General Public
 * License version 2 or later. See LICENSE.
 ***************************************************************************/
#ifndef CUDA_PINNED_STAGE_H_
#define CUDA_PINNED_STAGE_H_

#include <cuda_runtime.h>
#include <cstddef>

namespace mc_cuda {

struct PinnedBackend {
    void *(*map)(size_t bytes);   // 2 MiB-aligned, hugepage-advised; nullptr on failure
    int (*unmap)(void *ptr, size_t bytes);
    cudaError_t (*registerHost)(void *ptr, size_t bytes);
    cudaError_t (*unregisterHost)(void *ptr);
    cudaError_t (*hostAlloc)(void **ptr, size_t bytes);
    cudaError_t (*freeHost)(void *ptr);

    // mmap/munmap and the CUDA runtime.
    static const PinnedBackend &system();
};

class PinnedStage {
public:
    enum class Kind { None, Registered, HostAlloc };

    explicit PinnedStage(const PinnedBackend &backend = PinnedBackend::system(),
                         bool prefer_registered = defaultPreferRegistered())
        : backend_(&backend), prefer_registered_(prefer_registered) {}
    PinnedStage(const PinnedStage &) = delete;
    PinnedStage &operator=(const PinnedStage &) = delete;
    // Runs on thread exit, possibly after the CUDA context has gone, so the
    // status is deliberately dropped; the mapping is returned regardless.
    ~PinnedStage() { (void)release(true); }

    // Registered pinning unless MOTIONCORR_PINNED_REGISTER=0.
    static bool defaultPreferRegistered();

    void *data() const { return ptr_; }
    size_t bytes() const { return bytes_; }
    Kind kind() const { return kind_; }

    // Pins @p bytes. Precondition: nothing is held (cudaErrorInvalidValue and no
    // effect otherwise), so the caller's release-then-acquire order is explicit.
    // @p fell_back is set when registered pinning was preferred but cudaHostAlloc
    // supplied the buffer. Returns the failing status; nothing is held on failure.
    cudaError_t acquire(size_t bytes, bool *fell_back = nullptr);

    // Frees the held buffer through the path that created it, exactly once.
    // On failure to unpin, ownership is retained (the caller may retry or let the
    // destructor run) and the status is returned. @p force_unmap drops a
    // registered mapping even if unpinning failed: only the destructor, where
    // there is nowhere left to retry.
    cudaError_t release(bool force_unmap = false);

private:
    const PinnedBackend *backend_;
    bool prefer_registered_;
    void *ptr_ = nullptr;
    size_t bytes_ = 0;
    Kind kind_ = Kind::None;
};

}  // namespace mc_cuda

#endif  // CUDA_PINNED_STAGE_H_
