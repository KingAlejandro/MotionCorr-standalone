#ifndef CUDA_WORKER_POOL_H_
#define CUDA_WORKER_POOL_H_

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>

#include <cstddef>
#include <ostream>

#include "src/acc/cuda/cuda_failure_state.h"
#include "src/acc/cuda/cuda_scoped_resources.h"

/**
 * Worker-lifetime CUDA resources, and the rules that make reusing them safe.
 *
 * A CudaMovieSession is constructed and destroyed once per movie, so everything
 * it owns is paid for again on every movie even when nothing about it changed:
 * the gain upload, the two whole-frame cuFFT plans and their shared work area,
 * the batched patch plan and the dose-weighting plan. The movie loop in
 * MotioncorrRunner::run() is serial, so at most one movie is in flight at a
 * time and these can outlive the session that uses them.
 *
 * What makes that safe is ownership, not caching. The properties below are the
 * ones the tests in tests/cuda_worker_pool.cpp are written against.
 *
 *  1. One owner. The pool owns every resource here. A session receives a
 *     BORROWED alias with no destroy authority. No handle is ever reachable
 *     from two owners, which is the defect that makes a geometry transition
 *     destroy the same cufftHandle twice.
 *
 *  2. Explicit lease. acquireLease() admits exactly one holder. A second
 *     holder is REFUSED, and a refusal changes nothing: it drops no resource,
 *     invalidates no key and clears no borrow. The first holder keeps running.
 *     thread_local storage alone does not provide this -- two live sessions can
 *     interleave on one thread -- so the lease is an object with a holder
 *     identity rather than an assumption about threads.
 *
 *  3. Keys are published only after complete successful construction. Every
 *     entry is invalidated BEFORE the destructive part of its replacement
 *     begins. A failed owning-device selection keeps an unpublished owned entry
 *     for checked cleanup retry; it cannot serve a hit or be overwritten.
 *
 *  4. Checked release. Every cufftDestroy and cudaFree result is recorded in
 *     the caller's CudaFailureState and returned. A drop that fails FAILS THE
 *     ACQUIRE: the pool does not construct and publish a replacement as though
 *     the cleanup had succeeded, because the original error and any late fatal
 *     cleanup code both have to survive into the caller's retry verdict.
 *
 *  5. Device-correct cleanup. Each entry records the device it was built on.
 *     A drop successfully selects that device before destroying. If selection
 *     fails, no destroy/free is issued and ownership is retained. The requested
 *     device must be selected AGAIN before the replacement is constructed. A
 *     device id in a cache key does not by itself make cleanup context-correct.
 *
 *  6. A fatal context retires the pool. retireForFatalContext() attempts the
 *     same checked release every other path uses -- recording each status
 *     rather than trusting it, exactly as the session's own releaseBuffer()
 *     does on a poisoned context -- then invalidates the entries and refuses every
 *     later acquire for that device. The refusal is sticky and independent of
 *     any session's failure state: the next movie starts with a clean
 *     CudaFailureState, and that must not make handles from a dead context
 *     reusable.
 *
 *  7. Retained bytes are visible and bounded. One entry per resource class,
 *     each with a complete key, so a geometry change replaces rather than
 *     accumulates. retainedBytes() reports what is held, and evictUnused()
 *     releases everything the live lease is not currently using so an admission
 *     failure can be retried once before it is reported as a real failure.
 */
/**
 * Per-mechanism ablation switches, all on by default.
 *
 * Each one disables exactly one acquire site, leaving the pool, the lease and
 * every ownership rule above in place. They exist because "the pool is worth
 * N ms" is not a measurement anyone can act on: the four mechanisms have
 * different costs, different retained bytes and different failure surfaces, and
 * each has to earn its place separately. The arms in the accompanying results
 * were built by setting these at configure time, e.g. -DMC_POOL_GAIN=0.
 *
 * A build that defines none of them is the production configuration.
 */
#ifndef MC_POOL_GAIN
#define MC_POOL_GAIN 1
#endif
#ifndef MC_POOL_GLOBAL_FFT
#define MC_POOL_GLOBAL_FFT 1
#endif
#ifndef MC_POOL_PATCH_PLAN
#define MC_POOL_PATCH_PLAN 1
#endif
#ifndef MC_POOL_DW_PLAN
#define MC_POOL_DW_PLAN 1
#endif

namespace mc_cuda {

// What acquireGlobalFft hands back. Every member is borrowed: the pool destroys
// them, the lease holder only uses them.
struct GlobalFftLease {
    cufftHandle plan_r2c = 0;
    cufftHandle plan_c2r = 0;
    void *work = nullptr;
    cufftComplex *inverse_tile = nullptr;
    size_t r2c_work_bytes = 0;
    size_t c2r_work_bytes = 0;
    size_t work_bytes = 0;
    size_t tile_bytes = 0;
};

struct RetainedBytes {
    size_t gain = 0;
    size_t global_fft = 0;   // shared work area + inverse preservation tile
    size_t patch_plan = 0;   // cuFFT's own work area for the batched patch plan
    size_t dw_plan = 0;      // cuFFT's own work area for the reconstruction plan
    size_t total() const { return gain + global_fft + patch_plan + dw_plan; }
};

class CudaWorkerPool {
public:
    CudaWorkerPool() = default;
    ~CudaWorkerPool() {
        // Best-effort backstop. The checked path is dropAll() with the caller's
        // failure state; by here there is no caller left to report to.
        CudaFailureState sink;
        (void)dropAll(&sink);
    }
    CudaWorkerPool(const CudaWorkerPool &) = delete;
    CudaWorkerPool &operator=(const CudaWorkerPool &) = delete;

    // ---------------------------------------------------------------- lease --

    // Admit @p holder as the single active lease. Returns false, and changes
    // nothing at all, if another holder is already active or @p holder is null.
    bool acquireLease(const void *holder) {
        if (holder == nullptr) return false;
        if (lease_holder_ != nullptr) return false;
        lease_holder_ = holder;
        return true;
    }

    // Give the lease up. Borrowed aliases die with it; the resources stay.
    // Returns false if @p holder is not the current holder, which is a caller
    // bug rather than a resource failure, and leaves the lease alone.
    bool releaseLease(const void *holder) {
        if (holder == nullptr || lease_holder_ != holder) return false;
        clearBorrows();
        lease_holder_ = nullptr;
        return true;
    }

    bool leased() const { return lease_holder_ != nullptr; }
    bool leasedBy(const void *holder) const {
        return holder != nullptr && lease_holder_ == holder;
    }

    // ------------------------------------------------------- fatal contexts --

    // Attempt cleanup and invalidate reuse. An entry whose device cannot be
    // selected remains owned for a later dropAll() retry. Reports whether every
    // release succeeded, which on a poisoned context it generally will not; the caller
    // already has a fatal error and this cannot make it worse. Skipping the
    // release instead would leak the pool's bytes for the life of the process
    // and break the contract every other owner in this codebase keeps.
    bool retireForFatalContext(int device, CudaFailureState *failure) {
        const bool clean = dropAllEntries(failure);
        poisoned_ = true;
        poisoned_device_ = device;
        lease_holder_ = nullptr;
        return clean;
    }
    bool retiredFor(int device) const {
        return poisoned_ && (poisoned_device_ < 0 || poisoned_device_ == device);
    }

    // ------------------------------------------------------------- acquires --

    // Borrowed device gain for (device, nx, ny, generation).
    //
    // @p generation is the caller's identity for the host gain contents; 0 means
    // the caller supplied none, and the pool declines so the caller keeps its own
    // upload-every-movie path. An un-updated caller therefore cannot acquire
    // retention by accident. Returns nullptr on refusal or on any failure.
    float *acquireGain(const void *holder, int device, int nx, int ny,
                       unsigned long long generation, const float *host_gain,
                       CudaFailureState *failure);

    // Borrowed whole-frame R2C/C2R plans, their shared work area and the inverse
    // preservation tile, for (device, nx, ny).
    bool acquireGlobalFft(const void *holder, int device, int nx, int ny, int nfx,
                          GlobalFftLease &out, CudaFailureState *failure);

    // Borrowed batched patch R2C plan for (device, patch_w, patch_h, n_groups).
    bool acquirePatchPlan(const void *holder, int device, int patch_w, int patch_h,
                          int n_groups, cufftHandle &out, CudaFailureState *failure);

    // Borrowed reconstruction C2R plan for (device, nx, ny). @p work_size_out
    // receives cufftGetSize so the caller's VRAM telemetry is unchanged.
    bool acquireDwPlan(const void *holder, int device, int nx, int ny,
                       cufftHandle &out, size_t &work_size_out,
                       CudaFailureState *failure);

    // ------------------------------------------------------------ lifecycle --

    // Release everything the live lease is not currently using. The caller for
    // this is admission pressure: a previous movie's retained buffers must not
    // make a later, smaller movie fail when releasing them would have let it in.
    //
    // The return value is whether every release SUCCEEDED, which is true when
    // there was nothing to release. @p released_any reports whether anything
    // actually went back, so a caller cannot report having freed memory it did
    // not free.
    bool evictUnused(CudaFailureState *failure, bool *released_any = nullptr);

    // Release everything, borrowed or not. Only valid with no live lease.
    bool dropAll(CudaFailureState *failure);

private:
    // Release every entry. dropAll() and retireForFatalContext() are both this,
    // with different bookkeeping around it.
    bool dropAllEntries(CudaFailureState *failure);

public:

    RetainedBytes retainedBytes() const {
        RetainedBytes bytes;
        if (gain_.d_gain) bytes.gain = gain_.bytes;
        if (global_.work || global_.inverse_tile) bytes.global_fft = global_.work_bytes + global_.tile_bytes;
        if (patch_.has_plan) bytes.patch_plan = patch_.work_bytes;
        if (dw_.has_plan) bytes.dw_plan = dw_.work_bytes;
        return bytes;
    }

    // Counters, for tests and for the per-run log line. Hits and misses are what
    // distinguish "the key matched" from "the key was rebuilt every movie", which
    // a wall time cannot.
    struct Counters {
        unsigned gain_hits = 0, gain_builds = 0;
        unsigned global_hits = 0, global_builds = 0;
        unsigned patch_hits = 0, patch_builds = 0;
        unsigned dw_hits = 0, dw_builds = 0;
        unsigned lease_refusals = 0, evictions = 0;
    };
    const Counters &counters() const { return counters_; }
    void noteLeaseRefusal() { ++counters_.lease_refusals; }

    void logRetained(std::ostream &out) const {
        const RetainedBytes bytes = retainedBytes();
        out << "CUDA worker pool: retained " << bytes.total() << " B"
            << " (gain=" << bytes.gain
            << " global_fft=" << bytes.global_fft
            << " patch_plan=" << bytes.patch_plan
            << " dw_plan=" << bytes.dw_plan << ")"
            << " hits gain=" << counters_.gain_hits << "/" << counters_.gain_builds
            << " global=" << counters_.global_hits << "/" << counters_.global_builds
            << " patch=" << counters_.patch_hits << "/" << counters_.patch_builds
            << " dw=" << counters_.dw_hits << "/" << counters_.dw_builds
            << " evictions=" << counters_.evictions
            << " lease_refusals=" << counters_.lease_refusals << std::endl;
    }

private:
    struct GainEntry {
        bool valid = false;
        bool borrowed = false;
        int device = -1;
        int nx = 0, ny = 0;
        unsigned long long generation = 0;
        float *d_gain = nullptr;
        size_t bytes = 0;
    };
    struct GlobalFftEntry {
        bool valid = false;
        bool borrowed = false;
        int device = -1;
        int nx = 0, ny = 0, nfx = 0;
        cufftHandle plan_r2c = 0, plan_c2r = 0;
        bool has_r2c = false, has_c2r = false;
        void *work = nullptr;
        cufftComplex *inverse_tile = nullptr;
        size_t r2c_work_bytes = 0, c2r_work_bytes = 0, work_bytes = 0, tile_bytes = 0;
    };
    struct PatchPlanEntry {
        bool valid = false;
        bool borrowed = false;
        int device = -1;
        int patch_w = 0, patch_h = 0, n_groups = 0;
        cufftHandle plan = 0;
        bool has_plan = false;
        size_t work_bytes = 0;
    };
    struct DwPlanEntry {
        bool valid = false;
        bool borrowed = false;
        int device = -1;
        int nx = 0, ny = 0;
        cufftHandle plan = 0;
        bool has_plan = false;
        size_t work_bytes = 0;
    };

    void clearBorrows() {
        gain_.borrowed = global_.borrowed = patch_.borrowed = dw_.borrowed = false;
    }

    // Select @p device and record the outcome. Called before constructing on a
    // requested device and before destroying on an owning one; those are two
    // different devices in general, which is the whole reason it exists.
    static bool selectDevice(int device, const char *stage, CudaFailureState *failure) {
        const cudaError_t err = cudaSetDevice(device);
        if (failure) failure->record(err, stage, __LINE__);
        return err == cudaSuccess;
    }

    // Each drop invalidates reuse FIRST. Failure to select the owning device
    // retains ownership for checked retry and issues no destroy/free. After
    // successful selection, disown and attempt every checked release.
    bool dropGain(CudaFailureState *failure);
    bool dropGlobalFft(CudaFailureState *failure);
    bool dropPatchPlan(CudaFailureState *failure);
    bool dropDwPlan(CudaFailureState *failure);

    static bool destroyPlan(cufftHandle plan, bool owned, const char *stage,
                            CudaFailureState *failure) {
        if (!owned) return true;
        const cufftResult err = cufftDestroy(plan);
        if (failure) {
            failure->recordCufft(err, stage, __LINE__);
            // A cuFFT status alone cannot name a poisoned context.
            if (err != CUFFT_SUCCESS) failure->record(cudaPeekAtLastError(), stage, __LINE__);
        }
        return err == CUFFT_SUCCESS;
    }
    static bool freeBuffer(void *ptr, const char *stage, CudaFailureState *failure) {
        if (ptr == nullptr) return true;
        const cudaError_t err = cudaFree(ptr);
        if (failure) failure->record(err, stage, __LINE__);
        return err == cudaSuccess;
    }

    const void *lease_holder_ = nullptr;
    bool poisoned_ = false;
    int poisoned_device_ = -1;
    GainEntry gain_;
    GlobalFftEntry global_;
    PatchPlanEntry patch_;
    DwPlanEntry dw_;
    Counters counters_;
};

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_WORKER_POOL_H_
