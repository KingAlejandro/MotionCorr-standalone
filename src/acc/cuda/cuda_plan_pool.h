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
 * Worker-lifetime pooled cuFFT plans and shared Fourier scratch.
 *
 * Scoped to thread_local lifetime with an exclusive lease per CudaMovieSession.
 * All release/drop methods are checked against CudaFailureState, preserve
 * context selection, invalidate cache keys before handle destruction, and
 * ensure that handles are never destroyed multiple times or leaked on planning failure.
 */
class CudaWorkerPlanPool {
public:
    const void *active_session = nullptr;

    bool acquireLease(const void *session) {
        if (active_session != nullptr && active_session != session) {
            return false;
        }
        active_session = session;
        return true;
    }

    void releaseLease(const void *session) {
        if (active_session == session) {
            active_session = nullptr;
        }
    }

    struct GlobalPool {
        cufftHandle plan_r2c = 0;
        cufftHandle plan_c2r = 0;
        void *d_fft_work = nullptr;
        cufftComplex *d_inverse_tile = nullptr;
        size_t fft_r2c_work_bytes = 0;
        size_t fft_c2r_work_bytes = 0;
        size_t fft_work_bytes = 0;
        size_t sz_comp = 0;
        int nx = 0, ny = 0, device_id = -1;
        bool valid = false;

        ~GlobalPool() { drop(nullptr); }

        bool drop(CudaFailureState *failure = nullptr) {
            if (!valid && plan_r2c == 0 && plan_c2r == 0 && d_fft_work == nullptr && d_inverse_tile == nullptr) {
                return true;
            }
            bool ok = true;
            const int target_device = device_id;
            // Invalidate keys before destruction so subsequent calls cannot match
            valid = false;
            nx = ny = 0;
            device_id = -1;
            fft_r2c_work_bytes = fft_c2r_work_bytes = fft_work_bytes = sz_comp = 0;

            if (target_device >= 0) {
                const cudaError_t set_err = cudaSetDevice(target_device);
                if (set_err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(set_err, "dropGlobal cudaSetDevice", __LINE__);
                }
            }
            if (plan_r2c != 0) {
                const cufftHandle h = plan_r2c;
                plan_r2c = 0;
                const cufftResult res = cufftDestroy(h);
                if (res != CUFFT_SUCCESS) {
                    ok = false;
                    if (failure) {
                        failure->recordCufft(res, "dropGlobal plan_r2c", __LINE__);
                        failure->record(cudaPeekAtLastError(), "dropGlobal plan_r2c", __LINE__);
                    }
                }
            }
            if (plan_c2r != 0) {
                const cufftHandle h = plan_c2r;
                plan_c2r = 0;
                const cufftResult res = cufftDestroy(h);
                if (res != CUFFT_SUCCESS) {
                    ok = false;
                    if (failure) {
                        failure->recordCufft(res, "dropGlobal plan_c2r", __LINE__);
                        failure->record(cudaPeekAtLastError(), "dropGlobal plan_c2r", __LINE__);
                    }
                }
            }
            if (d_fft_work != nullptr) {
                void *p = d_fft_work;
                d_fft_work = nullptr;
                const cudaError_t err = cudaFree(p);
                if (err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(err, "dropGlobal d_fft_work", __LINE__);
                }
            }
            if (d_inverse_tile != nullptr) {
                void *p = d_inverse_tile;
                d_inverse_tile = nullptr;
                const cudaError_t err = cudaFree(p);
                if (err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(err, "dropGlobal d_inverse_tile", __LINE__);
                }
            }
            return ok;
        }
    } global;

    struct PatchPool {
        cufftHandle plan_patch_r2c = 0;
        int patch_w = 0, patch_h = 0, n_groups = 0, device_id = -1;
        bool valid = false;

        ~PatchPool() { drop(nullptr); }

        bool drop(CudaFailureState *failure = nullptr) {
            if (!valid && plan_patch_r2c == 0) return true;
            bool ok = true;
            const int target_device = device_id;
            valid = false;
            patch_w = patch_h = n_groups = 0;
            device_id = -1;

            if (target_device >= 0) {
                const cudaError_t set_err = cudaSetDevice(target_device);
                if (set_err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(set_err, "dropPatch cudaSetDevice", __LINE__);
                }
            }
            if (plan_patch_r2c != 0) {
                const cufftHandle h = plan_patch_r2c;
                plan_patch_r2c = 0;
                const cufftResult res = cufftDestroy(h);
                if (res != CUFFT_SUCCESS) {
                    ok = false;
                    if (failure) {
                        failure->recordCufft(res, "dropPatch plan_patch_r2c", __LINE__);
                        failure->record(cudaPeekAtLastError(), "dropPatch plan_patch_r2c", __LINE__);
                    }
                }
            }
            return ok;
        }
    } patch;

    struct DwPool {
        cufftHandle plan_c2r = 0;
        int nx = 0, ny = 0, device_id = -1;
        bool valid = false;

        ~DwPool() { drop(nullptr); }

        bool drop(CudaFailureState *failure = nullptr) {
            if (!valid && plan_c2r == 0) return true;
            bool ok = true;
            const int target_device = device_id;
            valid = false;
            nx = ny = 0;
            device_id = -1;

            if (target_device >= 0) {
                const cudaError_t set_err = cudaSetDevice(target_device);
                if (set_err != cudaSuccess) {
                    ok = false;
                    if (failure) failure->record(set_err, "dropDw cudaSetDevice", __LINE__);
                }
            }
            if (plan_c2r != 0) {
                const cufftHandle h = plan_c2r;
                plan_c2r = 0;
                const cufftResult res = cufftDestroy(h);
                if (res != CUFFT_SUCCESS) {
                    ok = false;
                    if (failure) {
                        failure->recordCufft(res, "dropDw plan_c2r", __LINE__);
                        failure->record(cudaPeekAtLastError(), "dropDw plan_c2r", __LINE__);
                    }
                }
            }
            return ok;
        }
    } dw;

    ~CudaWorkerPlanPool() {
        dropAll(nullptr);
    }

    bool dropAll(CudaFailureState *failure = nullptr) {
        bool ok = true;
        if (!global.drop(failure)) ok = false;
        if (!patch.drop(failure)) ok = false;
        if (!dw.drop(failure)) ok = false;
        return ok;
    }
};

inline CudaWorkerPlanPool &getWorkerPlanPool() {
    static thread_local CudaWorkerPlanPool pool;
    return pool;
}

} // namespace mc_cuda

#endif // _CUDA_ENABLED
#endif // CUDA_PLAN_POOL_H_
