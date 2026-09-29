#ifndef CUDA_SCRATCH_ARENA_H_
#define CUDA_SCRATCH_ARENA_H_

#include <cstddef>

/**
 * Device scratch borrowed from a buffer that a later phase owns.
 *
 * initialize() allocates d_Fframes for the Fourier movie, but nothing writes it
 * until computeGlobalForwardFFT(), and that transform overwrites every element.
 * The ingest phase can therefore use those bytes instead of allocating its own,
 * which is what keeps the nvCOMP path from raising the session's VRAM high-water
 * mark by another movie-scale buffer.
 *
 * Nothing here touches CUDA: an arena is pointer arithmetic over a base someone
 * else owns, and the storage state is a three-value rule. Both are kept device-free
 * so the lifetime contract can be tested in CI, which has no GPU, rather than only
 * being observable as corrupted output on a machine that does.
 */
namespace mc_cuda {

inline size_t alignUp(size_t value, size_t alignment) {
    return alignment <= 1 ? value : ((value + alignment - 1) / alignment) * alignment;
}

/**
 * Bump allocator over a caller-owned device buffer. alloc() hands out views, never
 * ownership: nothing returned here may be passed to cudaFree, and every view dies at
 * the next reset() or when the owning phase reclaims the buffer.
 */
class DeviceScratchArena {
public:
    // cudaMalloc guarantees 256-byte alignment, so that is the coarsest request an
    // arena can satisfy by offsetting from its base. Anything stricter is refused
    // rather than silently returned misaligned.
    static const size_t kMaxAlignment = 256;

    DeviceScratchArena() : base_(0), capacity_(0), used_(0) {}
    DeviceScratchArena(void *base, size_t capacity)
        : base_(static_cast<unsigned char *>(base)), capacity_(base ? capacity : 0), used_(0) {}

    void *alloc(size_t bytes, size_t alignment) {
        if (!base_ || alignment == 0 || alignment > kMaxAlignment) return 0;
        if ((alignment & (alignment - 1)) != 0) return 0;      // power of two only
        const size_t start = alignUp(used_, alignment);
        if (start > capacity_ || bytes > capacity_ - start) return 0;
        used_ = start + bytes;
        return base_ + start;
    }

    void reset() { used_ = 0; }
    bool valid() const { return base_ != 0; }
    size_t used() const { return used_; }
    size_t capacity() const { return capacity_; }
    size_t remaining() const { return capacity_ - used_; }

private:
    unsigned char *base_;
    size_t capacity_;
    size_t used_;
};

/**
 * What d_Fframes currently holds.
 *
 *   ReadyForFFT    nothing lives there; the forward transform may overwrite it
 *   IngestScratch  ingest views are outstanding; the transform must not run
 *   FourierData    the movie spectrum; no further scratch may be handed out
 *
 * The two refusals are the point. Running the forward transform while ingest views
 * are live would corrupt the spectrum with staging bytes; handing out scratch after
 * the transform would corrupt the spectrum with staging bytes. Neither shows up as
 * an error at the point of the mistake, so the state is checked instead of assumed.
 */
enum FourierStorage {
    kFourierReadyForFFT = 0,
    kFourierIngestScratch = 1,
    kFourierData = 2
};

class FourierStorageGuard {
public:
    FourierStorageGuard() : state_(kFourierReadyForFFT) {}

    FourierStorage state() const { return state_; }
    void reset() { state_ = kFourierReadyForFFT; }

    // Claim the buffer as ingest scratch. Fails once the spectrum is in it.
    bool beginIngestScratch() {
        if (state_ != kFourierReadyForFFT) return false;
        state_ = kFourierIngestScratch;
        return true;
    }

    // Declare every ingest view dead. The caller must have synchronised any stream
    // with work still touching the arena before calling this.
    bool finishIngestScratch() {
        if (state_ != kFourierIngestScratch) return false;
        state_ = kFourierReadyForFFT;
        return true;
    }

    // Take the buffer for Fourier output. Fails while ingest scratch is live.
    bool beginFourierWrite() {
        if (state_ == kFourierIngestScratch) return false;
        state_ = kFourierData;
        return true;
    }

private:
    FourierStorage state_;
};

} // namespace mc_cuda

#endif // CUDA_SCRATCH_ARENA_H_
