// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef CUDA_PLAN_POOL_H_
#define CUDA_PLAN_POOL_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include "src/acc/cuda/cuda_failure_state.h"
#include <algorithm>
#include <cstddef>
#include <cstdlib>

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
 * One gain entry and one movie-geometry entry are retained. Retirement
 * invalidates their keys, selects the owning device before
 * releasing, and restores the caller's device. Failed selection retains owned
 * bytes for checked retry. A live session lease excludes replacement by another
 * session, and a fatal worker remains retired even after cleanup succeeds.
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
        if (target_device < 0) {
            ok_ = false;
            if (failure_) failure_->record(cudaErrorInvalidDevice, stage_, __LINE__);
            return;
        }
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
    CudaWorkerPlanPool() = default;
    CudaWorkerPlanPool(const CudaWorkerPlanPool &) = delete;
    CudaWorkerPlanPool &operator=(const CudaWorkerPlanPool &) = delete;
    /**
     * The device gain copy.
     *
     * The key is (generation, bytes, nx, ny, device). generation==0 means the
     * caller supplied no identity, and retention is then disabled rather than
     * guessed at, so an un-updated caller keeps the upload-every-movie
     * behaviour it had before.
     */
    struct GainPool {
        GainPool() = default;
        GainPool(const GainPool &) = delete;
        GainPool &operator=(const GainPool &) = delete;
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
            // Invalidate reuse, but keep ownership and byte accounting until the
            // owning device is selected. A failed selection must not free on an
            // unrelated context or lose the only handle for checked retry.
            generation = 0;
            RetirementContext context(target_device, failure, "dropGain");
            if (!context.selected()) return false;
            ptr = nullptr; bytes = 0; nx = ny = 0; device_id = -1;
            bool ok = true;
            const cudaError_t err = cudaFree(owned);
            if (err != cudaSuccess) {
                ok = false;
                if (failure) failure->record(err, "dropGain cudaFree", __LINE__);
            }
            return context.finish(ok);
        }
    } gain;

    /**
     * The movie-geometry resources a session allocates in initialize() and
     * holds until release(): the frame buffers, both whole-frame cuFFT plans,
     * their shared work area and the inverse tile.
     *
     * The key is (device, nx, ny, n_frames); every size and both plans are a
     * function of it. Unlike the gain, the entry is taken, not borrowed: a
     * session moves the resources out on a key hit and the slot stays empty
     * until a healthy session returns them, so no two sessions can alias one
     * buffer and no lease is needed. The contents are not part of the key and
     * carry nothing across movies: initialize() hands out the same undefined
     * contents a fresh cudaMalloc would.
     */
    struct GeometryEntry {
        GeometryEntry() = default;
        GeometryEntry(const GeometryEntry &) = delete;
        GeometryEntry &operator=(const GeometryEntry &) = delete;
        int device_id = -1, nx = 0, ny = 0, n_frames = 0;
        // Cleared before a checked drop; an owned but invalid entry is never taken.
        bool valid = false;
        cufftHandle plan_r2c = 0, plan_c2r = 0;
        bool has_plan_r2c = false, has_plan_c2r = false;
        size_t r2c_work_bytes = 0, c2r_work_bytes = 0, work_bytes = 0;
        void *fft_work = nullptr;
        cufftComplex *inverse_tile = nullptr;
        float *iframes = nullptr;
        cufftComplex *fframes = nullptr;
        size_t bytes = 0;

        ~GeometryEntry() { (void)drop(nullptr); }

        bool held() const {
            return has_plan_r2c || has_plan_c2r || fft_work != nullptr ||
                   inverse_tile != nullptr || iframes != nullptr || fframes != nullptr;
        }
        bool matches(int device, int x, int y, int frames) const {
            return valid && held() && device_id == device && nx == x && ny == y &&
                   n_frames == frames;
        }
        size_t retainedBytes() const { return held() ? bytes : (size_t)0; }

        void clearKey() {
            valid = false; device_id = -1; nx = ny = n_frames = 0;
            r2c_work_bytes = c2r_work_bytes = work_bytes = 0; bytes = 0;
        }

        // Plans before their work area, as in CudaMovieSession::release(). The
        // resources are idle here: release() synchronized before returning them.
        bool drop(CudaFailureState *failure = nullptr) {
            if (!held()) { clearKey(); return true; }
            valid = false;
            RetirementContext context(device_id, failure, "dropGeometry");
            // A failed selection keeps ownership for a checked retry, as for the gain.
            if (!context.selected())
                return false;
            bool ok = true;
            auto destroy = [&](cufftHandle &plan, bool &has_plan) {
                if (!has_plan) return;
                const cufftResult res = cufftDestroy(plan);
                plan = 0; has_plan = false;
                if (res != CUFFT_SUCCESS) {
                    ok = false;
                    if (failure) {
                        failure->recordCufft(res, "dropGeometry cufftDestroy", __LINE__);
                        failure->record(cudaPeekAtLastError(), "dropGeometry cufftDestroy", __LINE__);
                    }
                }
            };
            auto free_one = [&](void *owned) {
                if (owned == nullptr) return;
                const cudaError_t err = cudaFree(owned);
                if (err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(err, "dropGeometry cudaFree", __LINE__);
                }
            };
            destroy(plan_r2c, has_plan_r2c);
            destroy(plan_c2r, has_plan_c2r);
            void *owned[4] = {fft_work, inverse_tile, iframes, fframes};
            fft_work = nullptr; inverse_tile = nullptr; iframes = nullptr; fframes = nullptr;
            for (void *p : owned) free_one(p);
            clearKey();
            return context.finish(ok);
        }
    } geometry;

    // MOTIONCORR_RETAIN_GEOMETRY=0 restores per-movie allocation of the geometry entry.
    static bool geometryRetentionEnabled() {
        const char *env = std::getenv("MOTIONCORR_RETAIN_GEOMETRY");
        return !(env != nullptr && env[0] == '0' && env[1] == '\0');
    }

    // The FrameBufferPool test hook also poisons a taken geometry entry.
    static bool geometryPoisonRequested() {
        const char *env = std::getenv("MOTIONCORR_FRAME_POOL_POISON");
        return env != nullptr && env[0] == '1' && env[1] == '\0';
    }

    // One live session may borrow this worker's single gain entry. Thread-local
    // storage alone does not prevent two sessions interleaving on one thread.
    bool acquireLease(const void *holder, int device) {
        if (holder == nullptr || retiredFor(device)) return false;
        if (lease_holder_ != nullptr && lease_holder_ != holder) return false;
        lease_holder_ = holder;
        return true;
    }
    bool releaseLease(const void *holder) {
        if (holder == nullptr || lease_holder_ != holder) return false;
        lease_holder_ = nullptr;
        return true;
    }
    bool retiredFor(int device) const {
        // The static worker has one device/context ownership domain. Once any
        // fatal context was observed it must restart, not forget that retirement
        // after a later session supplies another device number.
        (void)device;
        return retired_;
    }
    cudaError_t retiredErrorFor(int device) const {
        return retiredFor(device) ? retired_error_ : cudaSuccess;
    }
    bool retire(int device, CudaFailureState *failure, const void *holder) {
        if (!retired_) {
            retired_ = true;
            retired_device_ = device;
            retired_error_ = failure && failure->isPoisoned()
                ? failure->fatalError() : cudaErrorContextIsDestroyed;
        }
        return dropAll(failure, holder);
    }

    ~CudaWorkerPlanPool() { (void)dropAll(nullptr); }

    bool dropAll(CudaFailureState *failure = nullptr, const void *holder = nullptr) {
        if (lease_holder_ != nullptr && lease_holder_ != holder) {
            if (failure) failure->record(cudaErrorNotReady, "gain cache lease busy", __LINE__);
            return false;
        }
        bool ok = true;
        if (!gain.drop(failure)) ok = false;
        if (!geometry.drop(failure)) ok = false;
        return ok;
    }

    // Device bytes this worker keeps resident between movies.
    size_t retainedBytes() const { return gain.retainedBytes() + geometry.retainedBytes(); }

private:
    const void *lease_holder_ = nullptr;
    bool retired_ = false;
    int retired_device_ = -1;
    cudaError_t retired_error_ = cudaSuccess;
};

inline CudaWorkerPlanPool &getWorkerPlanPool() {
    static thread_local CudaWorkerPlanPool pool;
    return pool;
}

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_PLAN_POOL_H_
