#ifndef CUDA_PLAN_POOL_H_
#define CUDA_PLAN_POOL_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include "src/acc/cuda/cuda_failure_state.h"
#include <algorithm>
#include <cstddef>

namespace mc_cuda {

/**
 * Worker-lifetime CUDA resources that outlive a single CudaMovieSession.
 *
 * CudaMovieSession is constructed per movie, so anything it owns is created and
 * destroyed once per movie even when its contents and geometry cannot have
 * changed. This pool holds the resources whose identity the caller can state
 * exactly, keyed on that identity, for the lifetime of the worker thread.
 *
 * thread_local, for the same reason as the session's PinnedStagePool: movies are
 * dispatched one at a time, but a worker-per-thread arrangement must not share
 * one buffer. One device per process is assumed, which is how --gpu behaves.
 *
 * Every retirement path is checked against CudaFailureState, invalidates the
 * cache key before destroying anything, selects the owning device and restores
 * the caller's device, and is idempotent so a second drop() cannot double-free.
 */

/**
 * Retirement must run on the device that owns the entry, and must leave the
 * caller's device current. A drop() that returned with another device selected
 * would send the caller's replacement allocation, plan creation or transform to
 * the wrong context.
 */
class RetirementContext {
public:
    RetirementContext(int target_device, CudaFailureState *failure, const char *stage)
        : caller_device_(-1), restore_(false), ok_(true), failure_(failure), stage_(stage) {
        if (target_device < 0) return;
        const cudaError_t get_err = cudaGetDevice(&caller_device_);
        if (get_err != cudaSuccess) {
            ok_ = false;
            if (failure_) failure_->record(get_err, stage_, __LINE__);
            return;
        }
        if (caller_device_ == target_device) return;
        const cudaError_t set_err = cudaSetDevice(target_device);
        if (set_err != cudaSuccess) {
            ok_ = false;
            if (failure_) failure_->record(set_err, stage_, __LINE__);
            return;
        }
        restore_ = true;
    }

    // Restores the caller's device and folds the result into the running status.
    bool finish(bool ok) {
        if (!restore_) return ok && ok_;
        restore_ = false;
        const cudaError_t back_err = cudaSetDevice(caller_device_);
        if (back_err != cudaSuccess) {
            ok_ = false;
            if (failure_) failure_->record(back_err, stage_, __LINE__);
        }
        return ok && ok_;
    }

    // Backstop only: finish() is called on every path that can report.
    ~RetirementContext() { if (restore_) (void)cudaSetDevice(caller_device_); }

    bool selected() const { return ok_; }

private:
    RetirementContext(const RetirementContext &);
    RetirementContext &operator=(const RetirementContext &);

    int caller_device_;
    bool restore_;
    bool ok_;
    CudaFailureState *failure_;
    const char *stage_;
};

class CudaWorkerPlanPool {
public:
    /**
     * The device gain copy.
     *
     * The key is (generation, bytes, nx, ny, device). generation==0 means the
     * caller supplied no identity, and retention is then disabled rather than
     * guessed at, so an un-updated caller keeps the upload-every-movie
     * behaviour it had before.
     */
    struct GainPool {
        float *ptr = nullptr;
        size_t bytes = 0;
        unsigned long long generation = 0;
        int nx = 0, ny = 0, device_id = -1;

        // Runs at thread exit, possibly after the context has gone; there is
        // nowhere left to report, which is why the checked form takes a state.
        ~GainPool() { (void)drop(nullptr); }

        size_t retainedBytes() const { return ptr != nullptr ? bytes : (size_t)0; }

        bool drop(CudaFailureState *failure = nullptr) {
            if (ptr == nullptr) {
                bytes = 0; generation = 0; nx = ny = 0; device_id = -1;
                return true;
            }
            const int target_device = device_id;
            float *owned = ptr;
            // Invalidate the key before the free so no later lookup can match a
            // buffer that is being retired.
            ptr = nullptr; bytes = 0; generation = 0; nx = ny = 0; device_id = -1;

            RetirementContext context(target_device, failure, "dropGain");
            bool ok = context.selected();
            const cudaError_t err = cudaFree(owned);
            if (err != cudaSuccess) {
                ok = false;
                if (failure) failure->record(err, "dropGain cudaFree", __LINE__);
            }
            return context.finish(ok);
        }
    } gain;

    ~CudaWorkerPlanPool() { (void)dropAll(nullptr); }

    bool dropAll(CudaFailureState *failure = nullptr) {
        bool ok = true;
        if (!gain.drop(failure)) ok = false;
        return ok;
    }

    // Device bytes this worker keeps resident between movies.
    size_t retainedBytes() const { return gain.retainedBytes(); }
};

inline CudaWorkerPlanPool &getWorkerPlanPool() {
    static thread_local CudaWorkerPlanPool pool;
    return pool;
}

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_PLAN_POOL_H_
