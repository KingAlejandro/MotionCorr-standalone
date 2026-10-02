#ifdef _CUDA_ENABLED

#include "src/acc/cuda/cuda_worker_pool.h"

#include <algorithm>

namespace mc_cuda {

// ---------------------------------------------------------------- drops -----
//
// Shape shared by all four: copy out what the entry owns, reset the entry so no
// key can match a resource that is about to stop existing, select the device
// that resource belongs to, then destroy and report. An entry is never left
// describing something half-destroyed, whatever any individual destroy returns.

bool CudaWorkerPool::dropGain(CudaFailureState *failure)
{
    float *owned = gain_.d_gain;
    const int device = gain_.device;
    gain_ = GainEntry();
    if (owned == nullptr) return true;
    const bool selected = selectDevice(device, "worker pool gain drop setDevice", failure);
    const bool freed = freeBuffer(owned, "worker pool gain cudaFree", failure);
    return selected && freed;
}

bool CudaWorkerPool::dropGlobalFft(CudaFailureState *failure)
{
    const GlobalFftEntry owned = global_;
    global_ = GlobalFftEntry();
    if (!owned.has_r2c && !owned.has_c2r && owned.work == nullptr &&
        owned.inverse_tile == nullptr)
        return true;
    bool ok = selectDevice(owned.device, "worker pool global drop setDevice", failure);
    // Plans before the work area they point at, and keep going after the first
    // failure so one bad handle cannot strand the rest.
    ok &= destroyPlan(owned.plan_r2c, owned.has_r2c, "worker pool global r2c destroy", failure);
    ok &= destroyPlan(owned.plan_c2r, owned.has_c2r, "worker pool global c2r destroy", failure);
    ok &= freeBuffer(owned.work, "worker pool global work cudaFree", failure);
    ok &= freeBuffer(owned.inverse_tile, "worker pool inverse tile cudaFree", failure);
    return ok;
}

bool CudaWorkerPool::dropPatchPlan(CudaFailureState *failure)
{
    const PatchPlanEntry owned = patch_;
    patch_ = PatchPlanEntry();
    if (!owned.has_plan) return true;
    const bool selected = selectDevice(owned.device, "worker pool patch drop setDevice", failure);
    const bool destroyed = destroyPlan(owned.plan, owned.has_plan,
                                       "worker pool patch plan destroy", failure);
    return selected && destroyed;
}

bool CudaWorkerPool::dropDwPlan(CudaFailureState *failure)
{
    const DwPlanEntry owned = dw_;
    dw_ = DwPlanEntry();
    if (!owned.has_plan) return true;
    const bool selected = selectDevice(owned.device, "worker pool dw drop setDevice", failure);
    const bool destroyed = destroyPlan(owned.plan, owned.has_plan,
                                       "worker pool dw plan destroy", failure);
    return selected && destroyed;
}

bool CudaWorkerPool::dropAllEntries(CudaFailureState *failure)
{
    bool ok = dropGain(failure);
    ok &= dropGlobalFft(failure);
    ok &= dropPatchPlan(failure);
    ok &= dropDwPlan(failure);
    return ok;
}

bool CudaWorkerPool::dropAll(CudaFailureState *failure)
{
    // A retired pool has already released and discarded its entries, so these
    // drops are all no-ops; going through them anyway keeps one path.
    return dropAllEntries(failure);
}

bool CudaWorkerPool::evictUnused(CudaFailureState *failure, bool *released_any)
{
    if (released_any) *released_any = false;
    if (poisoned_) return false;
    bool ok = true;
    bool released_anything = false;
    if (gain_.valid && !gain_.borrowed) { released_anything = true; ok &= dropGain(failure); }
    if (global_.valid && !global_.borrowed) { released_anything = true; ok &= dropGlobalFft(failure); }
    if (patch_.valid && !patch_.borrowed) { released_anything = true; ok &= dropPatchPlan(failure); }
    if (dw_.valid && !dw_.borrowed) { released_anything = true; ok &= dropDwPlan(failure); }
    if (released_anything) ++counters_.evictions;
    if (released_any) *released_any = released_anything;
    return ok;
}

// ------------------------------------------------------------- acquires -----

float *CudaWorkerPool::acquireGain(const void *holder, int device, int nx, int ny,
                                   unsigned long long generation,
                                   const float *host_gain, CudaFailureState *failure)
{
    if (!leasedBy(holder) || retiredFor(device)) return nullptr;
    // An already-poisoned caller must not be handed a resource, and the pool's
    // own handles belong to the context that just died.
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return nullptr;
    }
    if (generation == 0 || host_gain == nullptr || nx <= 0 || ny <= 0) return nullptr;

    if (gain_.valid && gain_.device == device && gain_.nx == nx && gain_.ny == ny &&
        gain_.generation == generation) {
        gain_.borrowed = true;
        ++counters_.gain_hits;
        return gain_.d_gain;
    }

    // Miss. Invalidate and destroy before anything new exists.
    if (!dropGain(failure)) return nullptr;
    // dropGain selected the OLD entry's device.
    if (!selectDevice(device, "worker pool gain build setDevice", failure)) return nullptr;

    const size_t bytes = (size_t)nx * (size_t)ny * sizeof(float);
    ScopedDeviceBuffer fresh(failure);
    void *raw = nullptr;
    const cudaError_t alloc_err = cudaMalloc(&raw, bytes);
    if (alloc_err != cudaSuccess) {
        if (failure) failure->record(alloc_err, "worker pool gain cudaMalloc", __LINE__);
        return nullptr;
    }
    fresh.take(raw);
    const cudaError_t copy_err = cudaMemcpy(raw, host_gain, bytes, cudaMemcpyHostToDevice);
    if (copy_err != cudaSuccess) {
        if (failure) failure->record(copy_err, "worker pool gain upload", __LINE__);
        return nullptr;  // fresh frees it; nothing was published
    }

    gain_.d_gain = (float *)fresh.disown();
    gain_.device = device;
    gain_.nx = nx;
    gain_.ny = ny;
    gain_.generation = generation;
    gain_.bytes = bytes;
    gain_.valid = true;
    gain_.borrowed = true;
    ++counters_.gain_builds;
    return gain_.d_gain;
}

bool CudaWorkerPool::acquireGlobalFft(const void *holder, int device, int nx, int ny,
                                      int nfx, GlobalFftLease &out,
                                      CudaFailureState *failure)
{
    if (!leasedBy(holder) || retiredFor(device)) return false;
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return false;
    }
    if (nx <= 0 || ny <= 0 || nfx <= 0) return false;

    auto publish = [&](const GlobalFftEntry &e) {
        out.plan_r2c = e.plan_r2c;
        out.plan_c2r = e.plan_c2r;
        out.work = e.work;
        out.inverse_tile = e.inverse_tile;
        out.r2c_work_bytes = e.r2c_work_bytes;
        out.c2r_work_bytes = e.c2r_work_bytes;
        out.work_bytes = e.work_bytes;
        out.tile_bytes = e.tile_bytes;
    };

    if (global_.valid && global_.device == device && global_.nx == nx &&
        global_.ny == ny && global_.nfx == nfx) {
        global_.borrowed = true;
        ++counters_.global_hits;
        publish(global_);
        return true;
    }

    if (!dropGlobalFft(failure)) return false;
    if (!selectDevice(device, "worker pool global build setDevice", failure)) return false;

    // Every created handle and allocation is adopted by a scoped owner on the
    // line after it exists. Ownership moves to the pool only once the LAST
    // fallible step of the construction has succeeded.
    ScopedCufftPlan r2c_owner(failure);
    ScopedCufftPlan c2r_owner(failure);
    ScopedDeviceBuffer work_owner(failure);
    ScopedDeviceBuffer tile_owner(failure);

    int n[2] = {ny, nx};
    GlobalFftEntry built;
    built.device = device;
    built.nx = nx;
    built.ny = ny;
    built.nfx = nfx;

    auto make_plan = [&](ScopedCufftPlan &owner, cufftType type, size_t &work_bytes,
                         const char *stage) -> bool {
        cufftHandle plan = 0;
        cufftResult res = cufftCreate(&plan);
        if (res != CUFFT_SUCCESS) {
            if (failure) {
                failure->recordCufft(res, stage, __LINE__);
                failure->record(cudaPeekAtLastError(), stage, __LINE__);
            }
            return false;
        }
        owner.take(plan);   // adopted before anything else can fail
        res = cufftSetAutoAllocation(plan, 0);
        if (res == CUFFT_SUCCESS) {
            const int input_distance = type == CUFFT_R2C ? nx * ny : ny * nfx;
            const int output_distance = type == CUFFT_R2C ? ny * nfx : nx * ny;
            res = cufftMakePlanMany(plan, 2, n, NULL, 1, input_distance,
                                    NULL, 1, output_distance, type, 1, &work_bytes);
        }
        if (res != CUFFT_SUCCESS) {
            if (failure) {
                failure->recordCufft(res, stage, __LINE__);
                failure->record(cudaPeekAtLastError(), stage, __LINE__);
            }
            return false;   // owner destroys the created handle
        }
        return true;
    };

    if (!make_plan(r2c_owner, CUFFT_R2C, built.r2c_work_bytes, "worker pool global r2c plan"))
        return false;
    if (!make_plan(c2r_owner, CUFFT_C2R, built.c2r_work_bytes, "worker pool global c2r plan"))
        return false;

    built.work_bytes = std::max(built.r2c_work_bytes, built.c2r_work_bytes);
    built.tile_bytes = (size_t)ny * (size_t)nfx * sizeof(cufftComplex);

    void *raw_work = nullptr;
    // cudaMalloc(0) is invalid on some CUDA runtimes even if cuFFT needs no work.
    cudaError_t err = cudaMalloc(&raw_work, std::max((size_t)1, built.work_bytes));
    if (err != cudaSuccess) {
        if (failure) failure->record(err, "worker pool global work cudaMalloc", __LINE__);
        return false;
    }
    work_owner.take(raw_work);

    void *raw_tile = nullptr;
    err = cudaMalloc(&raw_tile, built.tile_bytes);
    if (err != cudaSuccess) {
        if (failure) failure->record(err, "worker pool inverse tile cudaMalloc", __LINE__);
        return false;
    }
    tile_owner.take(raw_tile);

    for (int i = 0; i < 2; ++i) {
        const cufftHandle plan = i == 0 ? r2c_owner.get() : c2r_owner.get();
        const cufftResult res = cufftSetWorkArea(plan, raw_work);
        if (res != CUFFT_SUCCESS) {
            if (failure) {
                failure->recordCufft(res, "worker pool global work area", __LINE__);
                failure->record(cudaPeekAtLastError(), "worker pool global work area", __LINE__);
            }
            return false;
        }
    }

    built.plan_r2c = r2c_owner.disown();
    built.has_r2c = true;
    built.plan_c2r = c2r_owner.disown();
    built.has_c2r = true;
    built.work = work_owner.disown();
    built.inverse_tile = (cufftComplex *)tile_owner.disown();
    built.valid = true;
    built.borrowed = true;
    global_ = built;
    ++counters_.global_builds;
    publish(global_);
    return true;
}

bool CudaWorkerPool::acquirePatchPlan(const void *holder, int device, int patch_w,
                                      int patch_h, int n_groups, cufftHandle &out,
                                      CudaFailureState *failure)
{
    if (!leasedBy(holder) || retiredFor(device)) return false;
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return false;
    }
    if (patch_w <= 0 || patch_h <= 0 || n_groups <= 0) return false;

    if (patch_.valid && patch_.device == device && patch_.patch_w == patch_w &&
        patch_.patch_h == patch_h && patch_.n_groups == n_groups) {
        patch_.borrowed = true;
        ++counters_.patch_hits;
        out = patch_.plan;
        return true;
    }

    if (!dropPatchPlan(failure)) return false;
    if (!selectDevice(device, "worker pool patch build setDevice", failure)) return false;

    ScopedCufftPlan owner(failure);
    cufftHandle plan = 0;
    cufftResult res = cufftCreate(&plan);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool patch cufftCreate", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool patch cufftCreate", __LINE__);
        }
        return false;
    }
    owner.take(plan);

    const int patch_nfx = patch_w / 2 + 1;
    int n[2] = {patch_h, patch_w};
    size_t work_bytes = 0;
    res = cufftMakePlanMany(plan, 2, n, NULL, 1, patch_h * patch_w,
                            NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups,
                            &work_bytes);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool patch cufftMakePlanMany", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool patch cufftMakePlanMany", __LINE__);
        }
        return false;
    }

    patch_.plan = owner.disown();
    patch_.has_plan = true;
    patch_.device = device;
    patch_.patch_w = patch_w;
    patch_.patch_h = patch_h;
    patch_.n_groups = n_groups;
    patch_.work_bytes = work_bytes;
    patch_.valid = true;
    patch_.borrowed = true;
    ++counters_.patch_builds;
    out = patch_.plan;
    return true;
}

bool CudaWorkerPool::acquireDwPlan(const void *holder, int device, int nx, int ny,
                                   cufftHandle &out, size_t &work_size_out,
                                   CudaFailureState *failure)
{
    if (!leasedBy(holder) || retiredFor(device)) return false;
    if (failure != nullptr && failure->isPoisoned()) {
        (void)retireForFatalContext(device, failure);
        return false;
    }
    if (nx <= 0 || ny <= 0) return false;

    if (dw_.valid && dw_.device == device && dw_.nx == nx && dw_.ny == ny) {
        dw_.borrowed = true;
        ++counters_.dw_hits;
        out = dw_.plan;
        work_size_out = dw_.work_bytes;
        return true;
    }

    if (!dropDwPlan(failure)) return false;
    if (!selectDevice(device, "worker pool dw build setDevice", failure)) return false;

    ScopedCufftPlan owner(failure);
    cufftHandle plan = 0;
    cufftResult res = cufftCreate(&plan);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool dw cufftCreate", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool dw cufftCreate", __LINE__);
        }
        return false;
    }
    owner.take(plan);

    int n[2] = {ny, nx};
    size_t plan_work_bytes = 0;
    res = cufftMakePlanMany(plan, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1,
                            &plan_work_bytes);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool dw cufftMakePlanMany", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool dw cufftMakePlanMany", __LINE__);
        }
        return false;
    }
    size_t cufft_work_size = 0;
    res = cufftGetSize(plan, &cufft_work_size);
    if (res != CUFFT_SUCCESS) {
        if (failure) {
            failure->recordCufft(res, "worker pool dw cufftGetSize", __LINE__);
            failure->record(cudaPeekAtLastError(), "worker pool dw cufftGetSize", __LINE__);
        }
        return false;
    }

    dw_.plan = owner.disown();
    dw_.has_plan = true;
    dw_.device = device;
    dw_.nx = nx;
    dw_.ny = ny;
    dw_.work_bytes = cufft_work_size;
    dw_.valid = true;
    dw_.borrowed = true;
    ++counters_.dw_builds;
    out = dw_.plan;
    work_size_out = cufft_work_size;
    return true;
}

} // namespace mc_cuda

#endif // _CUDA_ENABLED
