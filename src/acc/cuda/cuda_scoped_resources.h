#ifndef CUDA_SCOPED_RESOURCES_H_
#define CUDA_SCOPED_RESOURCES_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include "src/error.h"
#include "src/acc/cuda/cuda_failure_state.h"
#include <vector>

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
 * resource, add() releases the incoming resource and throws after setting the
 * overflow flag. Silently dropping it would reintroduce exactly the leak
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
    explicit ScopedDeviceMemory(CudaFailureState *failure = nullptr)
        : count_(0), overflowed_(false), failure_(failure) {}
    ~ScopedDeviceMemory() { (void)releaseAll(); }

    bool add(void *allocation) {
        if (count_ >= Capacity) {
            overflowed_ = true;
            if (allocation) {
                const cudaError_t err = cudaFree(allocation);
                if (failure_) failure_->record(err, "resource registry overflow", __LINE__);
            }
            REPORT_ERROR("CUDA memory owner capacity exceeded");
        }
        slots_[count_++] = allocation;
        return true;
    }

    bool overflowed() const { return overflowed_; }
    int count() const { return count_; }

    cudaError_t releaseAll() {
        cudaError_t first_error = cudaSuccess;
        for (int i = 0; i < count_; ++i) {
            if (slots_[i] == nullptr) continue;
            void *owned = slots_[i];
            slots_[i] = nullptr;
            const cudaError_t err = cudaFree(owned);
            if (failure_) failure_->record(err, "scoped cudaFree", __LINE__);
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
    CudaFailureState *failure_;
};

template <int Capacity>
class ScopedCudaEvents {
public:
    explicit ScopedCudaEvents(CudaFailureState *failure = nullptr)
        : count_(0), overflowed_(false), failure_(failure) {}
    ~ScopedCudaEvents() { (void)releaseAll(); }

    bool add(cudaEvent_t event) {
        if (count_ >= Capacity) {
            overflowed_ = true;
            if (event) {
                const cudaError_t err = cudaEventDestroy(event);
                if (failure_) failure_->record(err, "event registry overflow", __LINE__);
            }
            REPORT_ERROR("CUDA event owner capacity exceeded");
        }
        slots_[count_++] = event;
        return true;
    }

    bool overflowed() const { return overflowed_; }
    int count() const { return count_; }

    cudaError_t releaseAll() {
        cudaError_t first_error = cudaSuccess;
        for (int i = 0; i < count_; ++i) {
            if (slots_[i] == nullptr) continue;
            cudaEvent_t owned = slots_[i];
            slots_[i] = nullptr;
            const cudaError_t err = cudaEventDestroy(owned);
            if (failure_) failure_->record(err, "scoped cudaEventDestroy", __LINE__);
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
    CudaFailureState *failure_;
};

// Same contract as ScopedCudaEvents, but the count is only known at run time.
//
// ScopedCudaEvents fixes its capacity at compile time, which is right when the
// event set is a fixed list. The dose-weighting path registers 2 + 6*n_frames
// events, and n_frames is an input. Sizing the template to a worst case would
// be a silent cap: exceeding it is a REPORT_ERROR that fails the movie, and
// "enough for the movies we tried" is not a bound.
//
// Semantics are deliberately identical to the fixed-capacity owner: every event
// is attempted even after one fails, the first error is returned, each
// destroy is recorded against the failure state, and releaseAll() is
// idempotent so the destructor stays a backstop for throwing paths rather than
// a second release mechanism.
class ScopedCudaEventList {
public:
    explicit ScopedCudaEventList(CudaFailureState *failure = nullptr,
                                 size_t reserve = 0)
        : failure_(failure) { if (reserve) slots_.reserve(reserve); }
    ~ScopedCudaEventList() { (void)releaseAll(); }

    bool add(cudaEvent_t event) {
        slots_.push_back(event);
        return true;
    }

    bool overflowed() const { return false; }  // no capacity to exceed
    int count() const { return (int)slots_.size(); }

    cudaError_t releaseAll() {
        cudaError_t first_error = cudaSuccess;
        for (size_t i = 0; i < slots_.size(); ++i) {
            if (slots_[i] == nullptr) continue;
            cudaEvent_t owned = slots_[i];
            slots_[i] = nullptr;
            const cudaError_t err = cudaEventDestroy(owned);
            if (failure_) failure_->record(err, "scoped cudaEventDestroy", __LINE__);
            if (err != cudaSuccess && first_error == cudaSuccess) first_error = err;
        }
        slots_.clear();
        return first_error;
    }

private:
    ScopedCudaEventList(const ScopedCudaEventList &);
    ScopedCudaEventList &operator=(const ScopedCudaEventList &);

    std::vector<cudaEvent_t> slots_;
    CudaFailureState *failure_;
};

// One handle, so no storage question arises; kept here so the three owners read alike.
class ScopedCufftPlan {
public:
    explicit ScopedCufftPlan(CudaFailureState *failure = nullptr)
        : plan_(0), owns_plan_(false), failure_(failure) {}
    ~ScopedCufftPlan() { (void)releaseAll(); }

    void take(cufftHandle handle) {
        // Re-taking the handle already held would otherwise destroy it and then mark
        // the dangling value owned, so that case is skipped rather than released.
        if (owns_plan_ && plan_ == handle) return;
        if (owns_plan_) REPORT_ERROR("CUDA plan owner already occupied");
        plan_ = handle;
        owns_plan_ = true;
    }

    cufftResult releaseAll() {
        if (!owns_plan_) return CUFFT_SUCCESS;
        owns_plan_ = false;
        const cufftHandle owned = plan_;
        plan_ = 0;
        const cufftResult err = cufftDestroy(owned);
        if (failure_) {
            failure_->recordCufft(err, "scoped cufftDestroy", __LINE__);
            if (err != CUFFT_SUCCESS)
                failure_->record(cudaPeekAtLastError(), "scoped cufftDestroy", __LINE__);
        }
        return err;
    }

private:
    ScopedCufftPlan(const ScopedCufftPlan &);
    ScopedCufftPlan &operator=(const ScopedCufftPlan &);

    cufftHandle plan_;
    bool owns_plan_;
    CudaFailureState *failure_;
};

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_SCOPED_RESOURCES_H_
