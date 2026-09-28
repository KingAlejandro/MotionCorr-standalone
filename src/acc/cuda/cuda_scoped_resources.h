#ifndef CUDA_SCOPED_RESOURCES_H_
#define CUDA_SCOPED_RESOURCES_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>

/**
 * Issue #69: scoped owners for CUDA resources with a statically proved maximum.
 *
 * These replace std::vector-backed registries. PR107 review P2: the registries are
 * constructed afresh for every global and local-patch alignment, and growing an
 * initially empty vector performs host heap allocations on every healthy call, inside
 * the patch loop. The maxima are known and provable by counting call sites -- eight
 * device buffers, eight events and one plan in cudaAlignPatchDevice, one buffer in the
 * cudaAlignPatch wrapper, with no add() inside any loop -- so fixed storage plus a
 * counter keeps the RAII behaviour with no allocation at all.
 *
 * Capacity is a hard error rather than a silent drop. If a future edit adds a ninth
 * resource, add() refuses it and sets the overflow flag, and the caller is expected to
 * check overflowed() and fail. Silently dropping it would reintroduce exactly the leak
 * this whole issue is about, which is why the flag exists instead of an assert that
 * compiles out in Release.
 *
 * releaseAll() keeps going after the first failure so one bad handle cannot strand the
 * rest, reports the first error, and is idempotent so the destructor is a harmless
 * backstop on throwing paths. Null slots are skipped, which also lets the counter and
 * capacity behaviour be exercised without any CUDA call.
 */
namespace mc_cuda {

template <int Capacity>
class ScopedDeviceMemory {
public:
    ScopedDeviceMemory() : count_(0), overflowed_(false) {}
    ~ScopedDeviceMemory() { (void)releaseAll(); }

    bool add(void *allocation) {
        if (count_ >= Capacity) { overflowed_ = true; return false; }
        slots_[count_++] = allocation;
        return true;
    }

    bool overflowed() const { return overflowed_; }
    int count() const { return count_; }

    cudaError_t releaseAll() {
        cudaError_t first_error = cudaSuccess;
        for (int i = 0; i < count_; ++i) {
            if (slots_[i] == nullptr) continue;
            const cudaError_t err = cudaFree(slots_[i]);
            if (err != cudaSuccess && first_error == cudaSuccess) first_error = err;
        }
        count_ = 0;
        return first_error;
    }

private:
    ScopedDeviceMemory(const ScopedDeviceMemory &);
    ScopedDeviceMemory &operator=(const ScopedDeviceMemory &);

    void *slots_[Capacity];
    int count_;
    bool overflowed_;
};

template <int Capacity>
class ScopedCudaEvents {
public:
    ScopedCudaEvents() : count_(0), overflowed_(false) {}
    ~ScopedCudaEvents() { (void)releaseAll(); }

    bool add(cudaEvent_t event) {
        if (count_ >= Capacity) { overflowed_ = true; return false; }
        slots_[count_++] = event;
        return true;
    }

    bool overflowed() const { return overflowed_; }
    int count() const { return count_; }

    cudaError_t releaseAll() {
        cudaError_t first_error = cudaSuccess;
        for (int i = 0; i < count_; ++i) {
            if (slots_[i] == nullptr) continue;
            const cudaError_t err = cudaEventDestroy(slots_[i]);
            if (err != cudaSuccess && first_error == cudaSuccess) first_error = err;
        }
        count_ = 0;
        return first_error;
    }

private:
    ScopedCudaEvents(const ScopedCudaEvents &);
    ScopedCudaEvents &operator=(const ScopedCudaEvents &);

    cudaEvent_t slots_[Capacity];
    int count_;
    bool overflowed_;
};

// One handle, so no storage question arises; kept here so the three owners read alike.
class ScopedCufftPlan {
public:
    ScopedCufftPlan() : plan_(0), owns_plan_(false) {}
    ~ScopedCufftPlan() { (void)releaseAll(); }

    void take(cufftHandle handle) {
        // Re-taking the handle already held would otherwise destroy it and then mark
        // the dangling value owned, so that case is skipped rather than released.
        if (owns_plan_ && plan_ == handle) return;
        (void)releaseAll();
        plan_ = handle;
        owns_plan_ = true;
    }

    cufftResult releaseAll() {
        if (!owns_plan_) return CUFFT_SUCCESS;
        owns_plan_ = false;
        return cufftDestroy(plan_);
    }

private:
    ScopedCufftPlan(const ScopedCufftPlan &);
    ScopedCufftPlan &operator=(const ScopedCufftPlan &);

    cufftHandle plan_;
    bool owns_plan_;
};

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_SCOPED_RESOURCES_H_
