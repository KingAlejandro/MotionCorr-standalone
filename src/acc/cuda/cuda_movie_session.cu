#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_settings.h"
#include "src/acc/cuda/cuda_realspace_dw.h"

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <climits>

#undef HANDLE_ERROR
#define HANDLE_ERROR(cmd) do { \
    cudaError_t err = (cmd); \
    if (err != cudaSuccess) { \
        logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << cudaGetErrorString(err) << std::endl; \
        return false; \
    } \
} while (0)

#undef CUFFT_CHECK
#define CUFFT_CHECK(cmd) do { \
    cufftResult res = (cmd); \
    if (res != CUFFT_SUCCESS) { \
        logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << res << std::endl; \
        return false; \
    } \
} while (0)

namespace {

__global__ void fusedGainAndSumKernel(
    float *d_Iframes,
    float *d_Isum,
    const float *d_gain,
    const size_t num_pixels,
    const int n_frames,
    const bool apply_gain
) {
    size_t pixel = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (pixel >= num_pixels) return;

    float gain_val = apply_gain ? d_gain[pixel] : 1.0f;
    float sum = 0.0f;
    for (int iframe = 0; iframe < n_frames; iframe++) {
        size_t offset = (size_t)iframe * num_pixels + pixel;
        float val = d_Iframes[offset];
        if (apply_gain) {
            val *= gain_val;
            d_Iframes[offset] = val;
        }
        sum += val;
    }
    d_Isum[pixel] = sum;
}

// ---------------------------------------------------------------------------
// GPU hot-pixel statistics (Issue #50 addendum: issue_50_gpu_hotpixel_statistics.md)
//
// Fixed-shape two-stage reductions. No floating-point atomics anywhere, so the
// result is deterministic run to run. Addends are formed with __dsub_rn/__dmul_rn
// so nvcc's default -fmad=true cannot contract `acc += d*d` into an FMA and change
// the addend multiset relative to the host expression at motioncorr_runner.cpp:1362.
// ---------------------------------------------------------------------------
#define MC_STATS_BLOCKS  1024
#define MC_STATS_THREADS 256

// Also accumulates sum|x|. The forward error bound on a summation is
// gamma_N * sum|x_i|, NOT gamma_N * |sum x_i| -- those coincide only for
// same-sign data. Carrying sum|x| keeps the guard rigorous under cancellation
// (negative gain entries, dark-subtracted input).
__global__ void sumUnalignedKernel(const float *d_Isum, const size_t num_pixels,
                                   double *d_partials, double *d_partials_abs)
{
    __shared__ double sdata[MC_STATS_THREADS];
    __shared__ double sabs[MC_STATS_THREADS];
    const size_t stride = (size_t)gridDim.x * blockDim.x;
    double acc = 0.0, acc_abs = 0.0;
    for (size_t n = (size_t)blockIdx.x * blockDim.x + threadIdx.x; n < num_pixels; n += stride) {
        const double xv = (double)d_Isum[n];
        acc = __dadd_rn(acc, xv);
        acc_abs = __dadd_rn(acc_abs, fabs(xv));
    }
    sdata[threadIdx.x] = acc;
    sabs[threadIdx.x] = acc_abs;
    __syncthreads();
    for (unsigned int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) {
            sdata[threadIdx.x] = __dadd_rn(sdata[threadIdx.x], sdata[threadIdx.x + s]);
            sabs[threadIdx.x] = __dadd_rn(sabs[threadIdx.x], sabs[threadIdx.x + s]);
        }
        __syncthreads();
    }
    if (threadIdx.x == 0) { d_partials[blockIdx.x] = sdata[0]; d_partials_abs[blockIdx.x] = sabs[0]; }
}

__global__ void sumSqDevUnalignedKernel(const float *d_Isum, const size_t num_pixels,
                                        const double mean, double *d_partials)
{
    __shared__ double sdata[MC_STATS_THREADS];
    const size_t stride = (size_t)gridDim.x * blockDim.x;
    double acc = 0.0;
    for (size_t n = (size_t)blockIdx.x * blockDim.x + threadIdx.x; n < num_pixels; n += stride) {
        const double d = __dsub_rn((double)d_Isum[n], mean);
        acc = __dadd_rn(acc, __dmul_rn(d, d));
    }
    sdata[threadIdx.x] = acc;
    __syncthreads();
    for (unsigned int s = blockDim.x / 2; s > 0; s >>= 1) {
        if (threadIdx.x < s) sdata[threadIdx.x] = __dadd_rn(sdata[threadIdx.x], sdata[threadIdx.x + s]);
        __syncthreads();
    }
    if (threadIdx.x == 0) d_partials[blockIdx.x] = sdata[0];
}

// Sequential final combine in fixed block order, single thread: deterministic.
__global__ void combinePartialsKernel(const double *d_partials, const int n_partials, double *d_out)
{
    double acc = 0.0;
    for (int i = 0; i < n_partials; i++) acc = __dadd_rn(acc, d_partials[i]);
    *d_out = acc;
}

// Emission order is arbitrary (integer atomicAdd); the host sorts ascending.
__global__ void collectAboveThresholdKernel(const float *d_Isum, const size_t num_pixels,
                                            const double threshold, const double guard,
                                            int *d_hits, const unsigned int capacity,
                                            unsigned int *d_count, unsigned int *d_band,
                                            unsigned int *d_overflow)
{
    const size_t stride = (size_t)gridDim.x * blockDim.x;
    for (size_t n = (size_t)blockIdx.x * blockDim.x + threadIdx.x; n < num_pixels; n += stride) {
        const double xv = (double)d_Isum[n];
        if (xv > threshold) {
            const unsigned int slot = atomicAdd(d_count, 1u);
            if (slot < capacity) d_hits[slot] = (int)n;
            else atomicExch(d_overflow, 1u);
        }
        if (fabs(xv - threshold) <= guard) atomicAdd(d_band, 1u);
    }
}

__global__ void updateDefectKernel(
    float *d_Iframes,
    const int *d_bad_xs,
    const int *d_bad_ys,
    const float *d_replacements,
    const int n_bad,
    const int nx,
    const int ny,
    const int n_frames
) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= n_bad) return;

    int x = d_bad_xs[idx];
    int y = d_bad_ys[idx];
    size_t frame_stride = (size_t)ny * nx;
    size_t pix_offset = (size_t)y * nx + x;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        float rep = d_replacements[(size_t)iframe * n_bad + idx];
        d_Iframes[(size_t)iframe * frame_stride + pix_offset] = rep;
    }
}

__global__ void scaleComplexKernel(cufftComplex *d_data, const size_t count, const float scale) {
    size_t idx = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < count) {
        d_data[idx].x *= scale;
        d_data[idx].y *= scale;
    }
}

__global__ void cropAndGroupPatchResidentKernel(
    const float *d_Iframes,
    float *d_Ipatches,
    const int nx, const int ny,
    const int x_start, const int y_start,
    const int patch_w, const int patch_h,
    const int *d_group_start, const int *d_group_size,
    const int n_groups
) {
    int px = blockIdx.x * blockDim.x + threadIdx.x;
    int py = blockIdx.y * blockDim.y + threadIdx.y;
    int igroup = blockIdx.z;

    if (px >= patch_w || py >= patch_h || igroup >= n_groups) return;

    int src_x = x_start + px;
    int src_y = y_start + py;
    size_t frame_stride = (size_t)ny * nx;
    size_t patch_stride = (size_t)patch_h * patch_w;

    int g_start = d_group_start[igroup];
    int g_size  = d_group_size[igroup];

    float sum = 0.0f;
    for (int i = 0; i < g_size; i++) {
        int iframe = g_start + i;
        size_t src_idx = (size_t)iframe * frame_stride + (size_t)src_y * nx + src_x;
        sum += d_Iframes[src_idx];
    }

    size_t dst_idx = (size_t)igroup * patch_stride + (size_t)py * patch_w + px;
    d_Ipatches[dst_idx] = sum;
}

} // anonymous namespace

CudaMovieSession::CudaMovieSession(int nx, int ny, int n_frames, int device_id, std::ostream &log)
    : nx(nx), ny(ny), n_frames(n_frames), device_id(device_id),
      nfx(nx / 2 + 1), logfile(log) {}

CudaMovieSession::~CudaMovieSession() {
    release();
}

bool CudaMovieSession::initialize() {
    if (is_initialized) return true;

    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    if (count_err != cudaSuccess || dev_count == 0) {
        logfile << "ERROR: No CUDA devices found" << std::endl;
        return false;
    }
    if (device_id < 0 || device_id >= dev_count) {
        logfile << "ERROR: Invalid CUDA device ID: " << device_id << std::endl;
        return false;
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t sz_real = (size_t)ny * nx * sizeof(float);
    const size_t sz_comp = (size_t)ny * nfx * sizeof(cufftComplex);
    const size_t total_real_bytes = sz_real * n_frames;
    const size_t total_comp_bytes = sz_comp * n_frames;

    if (nx <= 0 || ny <= 0 || n_frames <= 0 ||
        (size_t)nx * ny > INT_MAX || (size_t)ny * nfx > INT_MAX) {
        logfile << "ERROR: Invalid movie dimensions for cuFFT: "
                << nx << "x" << ny << "x" << n_frames << std::endl;
        return false;
    }

    // Allocate persistent movie buffers
    cudaError_t cuda_result = cudaMalloc((void**)&d_Iframes, total_real_bytes);
    if (cuda_result == cudaSuccess) cuda_result = cudaMalloc((void**)&d_Fframes, total_comp_bytes);
    if (cuda_result == cudaSuccess) cuda_result = cudaMalloc((void**)&d_Isum, sz_real);
    if (cuda_result != cudaSuccess) {
        logfile << "ERROR: Movie buffer allocation failed: " << cudaGetErrorString(cuda_result) << std::endl;
        release();
        return false;
    }

    // cuFFT's automatic allocation must be disabled before either plan is made.
    // Two transforms share one work area because all executions use the default stream
    // and each batch is synchronized before the next execution.
    // A single-frame batch keeps the inverse preservation tile to one frame.
    // The A100 batch-two sample exceeded the whole-process VRAM target.
    fft_batch_size = 1;
    const int tail_size = n_frames % fft_batch_size;
    int n[2] = {ny, nx};
    auto make_plan = [&](cufftHandle &plan, bool &has_plan, size_t &work_bytes,
                         cufftType type, int batch) -> bool {
        cufftResult result = cufftCreate(&plan);
        if (result == CUFFT_SUCCESS) has_plan = true;
        if (result == CUFFT_SUCCESS) result = cufftSetAutoAllocation(plan, 0);
        if (result == CUFFT_SUCCESS) {
            const int input_distance = type == CUFFT_R2C ? nx * ny : ny * nfx;
            const int output_distance = type == CUFFT_R2C ? ny * nfx : nx * ny;
            result = cufftMakePlanMany(plan, 2, n, NULL, 1, input_distance,
                                       NULL, 1, output_distance, type, batch, &work_bytes);
        }
        if (result != CUFFT_SUCCESS) {
            logfile << "ERROR: cuFFT plan failed for " << nx << "x" << ny
                    << " batch=" << batch << " type=" << type
                    << " code=" << result << std::endl;
            return false;
        }
        return true;
    };
    if (!make_plan(plan_r2c, has_plan_r2c, fft_r2c_work_bytes, CUFFT_R2C, fft_batch_size) ||
        !make_plan(plan_c2r, has_plan_c2r, fft_c2r_work_bytes, CUFFT_C2R, fft_batch_size) ||
        (tail_size &&
         (!make_plan(plan_r2c_tail, has_plan_r2c_tail, fft_r2c_tail_work_bytes, CUFFT_R2C, tail_size) ||
          !make_plan(plan_c2r_tail, has_plan_c2r_tail, fft_c2r_tail_work_bytes, CUFFT_C2R, tail_size)))) {
        release();
        return false;
    }

    fft_work_bytes = std::max(std::max(fft_r2c_work_bytes, fft_c2r_work_bytes),
                              std::max(fft_r2c_tail_work_bytes, fft_c2r_tail_work_bytes));
    // cudaMalloc(0) is invalid on some CUDA runtimes even if cuFFT needs no work.
    cuda_result = cudaMalloc(&d_fft_work, std::max((size_t)1, fft_work_bytes));
    if (cuda_result == cudaSuccess)
        cuda_result = cudaMalloc((void**)&d_inverse_tile, sz_comp * fft_batch_size);
    if (cuda_result != cudaSuccess) {
        logfile << "ERROR: Movie FFT scratch allocation failed for batch=" << fft_batch_size
                << " workspace=" << fft_work_bytes << " tile=" << sz_comp * fft_batch_size
                << ": " << cudaGetErrorString(cuda_result) << std::endl;
        release();
        return false;
    }
    auto attach_work = [&](cufftHandle plan, bool has_plan) -> bool {
        if (!has_plan) return true;
        cufftResult result = cufftSetWorkArea(plan, d_fft_work);
        if (result == CUFFT_SUCCESS) return true;
        logfile << "ERROR: cuFFT shared work area association failed with code " << result << std::endl;
        return false;
    };
    if (!attach_work(plan_r2c, has_plan_r2c) || !attach_work(plan_c2r, has_plan_c2r) ||
        !attach_work(plan_r2c_tail, has_plan_r2c_tail) ||
        !attach_work(plan_c2r_tail, has_plan_c2r_tail)) {
        release();
        return false;
    }
    logfile << "Movie FFT: batch=" << fft_batch_size << " tail=" << tail_size
            << " R2C work=" << fft_r2c_work_bytes << " C2R work=" << fft_c2r_work_bytes
            << " tail R2C work=" << fft_r2c_tail_work_bytes
            << " tail C2R work=" << fft_c2r_tail_work_bytes
            << " shared work=" << fft_work_bytes
            << " inverse tile=" << sz_comp * fft_batch_size << " bytes" << std::endl;

    is_initialized = true;
    return true;
}

void CudaMovieSession::release() {
    if (has_plan_r2c || has_plan_c2r || has_plan_r2c_tail || has_plan_c2r_tail) {
        cudaError_t result = cudaDeviceSynchronize();
        if (result != cudaSuccess)
            logfile << "ERROR: CUDA synchronization before movie FFT release: "
                    << cudaGetErrorString(result) << std::endl;
    }
    if (has_plan_r2c) {
        cufftDestroy(plan_r2c);
        plan_r2c = 0;
        has_plan_r2c = false;
    }
    if (has_plan_c2r) {
        cufftDestroy(plan_c2r);
        plan_c2r = 0;
        has_plan_c2r = false;
    }
    if (has_plan_r2c_tail) {
        cufftDestroy(plan_r2c_tail);
        plan_r2c_tail = 0;
        has_plan_r2c_tail = false;
    }
    if (has_plan_c2r_tail) {
        cufftDestroy(plan_c2r_tail);
        plan_c2r_tail = 0;
        has_plan_c2r_tail = false;
    }
    if (d_fft_work) {
        cudaFree(d_fft_work);
        d_fft_work = nullptr;
    }
    if (d_inverse_tile) {
        cudaFree(d_inverse_tile);
        d_inverse_tile = nullptr;
    }
    fft_batch_size = 0;
    fft_r2c_work_bytes = fft_c2r_work_bytes = 0;
    fft_r2c_tail_work_bytes = fft_c2r_tail_work_bytes = fft_work_bytes = 0;
    if (d_Iframes) {
        cudaFree(d_Iframes);
        d_Iframes = nullptr;
    }
    if (d_Fframes) {
        cudaFree(d_Fframes);
        d_Fframes = nullptr;
    }
    if (d_Isum) {
        cudaFree(d_Isum);
        d_Isum = nullptr;
    }
    if (d_gain) {
        cudaFree(d_gain);
        d_gain = nullptr;
    }
    if (has_plan_patch_r2c) {
        cufftDestroy(plan_patch_r2c);
        plan_patch_r2c = 0;
        has_plan_patch_r2c = false;
    }
    if (d_Ipatches) {
        cudaFree(d_Ipatches);
        d_Ipatches = nullptr;
    }
    if (d_group_start) {
        cudaFree(d_group_start);
        d_group_start = nullptr;
    }
    if (d_group_size) {
        cudaFree(d_group_size);
        d_group_size = nullptr;
    }
    cached_patch_w = 0;
    cached_patch_h = 0;
    cached_patch_ngroups = 0;
    sz_cached_Ipatches = 0;
    cached_ngroups_alloc = 0;
    is_initialized = false;
}

bool CudaMovieSession::applyGainDefectsAndSum(
    const std::vector<Image<float> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    if (!is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t num_pixels = (size_t)ny * nx;
    const size_t sz_real = num_pixels * sizeof(float);

    // Upload raw frames
    for (int iframe = 0; iframe < n_frames; iframe++) {
        float *dst = d_Iframes + (size_t)iframe * num_pixels;
        HANDLE_ERROR(cudaMemcpy(dst, raw_frames[iframe]().data, sz_real, cudaMemcpyHostToDevice));
    }

    // Upload gain reference if provided
    bool apply_gain = (gain_ref != nullptr);
    if (apply_gain) {
        if (!d_gain) {
            HANDLE_ERROR(cudaMalloc((void**)&d_gain, sz_real));
        }
        HANDLE_ERROR(cudaMemcpy(d_gain, gain_ref->data, sz_real, cudaMemcpyHostToDevice));
    }

    // Launch fused gain and sum kernel
    const int block = 256;
    const int grid = (int)((num_pixels + block - 1) / block);
    fusedGainAndSumKernel<<<grid, block>>>(d_Iframes, d_Isum, d_gain, num_pixels, n_frames, apply_gain);
    HANDLE_ERROR(cudaGetLastError());

    if (download_sum) {
        // Copy unaligned sum back to host for hot pixel detection. The blocking copy
        // also synchronises the kernel above.
        unaligned_sum.reshape(ny, nx);
        HANDLE_ERROR(cudaMemcpy(unaligned_sum.data, d_Isum, sz_real, cudaMemcpyDeviceToHost));
    } else {
        // Without the D2H there is no other synchronisation point for the kernel, so a
        // fault would otherwise surface at an unrelated later call and bypass the
        // caller's reset-and-fall-back recovery.
        HANDLE_ERROR(cudaDeviceSynchronize());
    }

    return true;
}

bool CudaMovieSession::downloadUnalignedSum(MultidimArray<float> &unaligned_sum) {
    if (!is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    unaligned_sum.reshape(ny, nx);
    HANDLE_ERROR(cudaMemcpy(unaligned_sum.data, d_Isum,
                            (size_t)ny * nx * sizeof(float), cudaMemcpyDeviceToHost));
    return true;
}

namespace {
// RAII scratch so the bare `return false` inside HANDLE_ERROR still frees.
struct StatsScratch {
    double *partials = nullptr;
    double *result = nullptr;
    ~StatsScratch() {
        if (partials) cudaFree(partials);
        if (result) cudaFree(result);
    }
};
} // namespace

bool CudaMovieSession::reduceUnalignedSum(double &sum1, double &sum_abs) {
    if (!is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t num_pixels = (size_t)ny * nx;
    StatsScratch scratch;
    HANDLE_ERROR(cudaMalloc((void**)&scratch.partials, 2 * MC_STATS_BLOCKS * sizeof(double)));
    HANDLE_ERROR(cudaMalloc((void**)&scratch.result, 2 * sizeof(double)));
    sumUnalignedKernel<<<MC_STATS_BLOCKS, MC_STATS_THREADS>>>(
        d_Isum, num_pixels, scratch.partials, scratch.partials + MC_STATS_BLOCKS);
    HANDLE_ERROR(cudaGetLastError());
    combinePartialsKernel<<<1, 1>>>(scratch.partials, MC_STATS_BLOCKS, scratch.result);
    HANDLE_ERROR(cudaGetLastError());
    combinePartialsKernel<<<1, 1>>>(scratch.partials + MC_STATS_BLOCKS, MC_STATS_BLOCKS, scratch.result + 1);
    HANDLE_ERROR(cudaGetLastError());
    double host[2] = {0.0, 0.0};
    HANDLE_ERROR(cudaMemcpy(host, scratch.result, 2 * sizeof(double), cudaMemcpyDeviceToHost));
    sum1 = host[0]; sum_abs = host[1];
    return true;
}

bool CudaMovieSession::reduceUnalignedSumSqDev(double mean, double &sum2) {
    if (!is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t num_pixels = (size_t)ny * nx;
    StatsScratch scratch;
    HANDLE_ERROR(cudaMalloc((void**)&scratch.partials, MC_STATS_BLOCKS * sizeof(double)));
    HANDLE_ERROR(cudaMalloc((void**)&scratch.result, sizeof(double)));
    sumSqDevUnalignedKernel<<<MC_STATS_BLOCKS, MC_STATS_THREADS>>>(d_Isum, num_pixels, mean, scratch.partials);
    HANDLE_ERROR(cudaGetLastError());
    combinePartialsKernel<<<1, 1>>>(scratch.partials, MC_STATS_BLOCKS, scratch.result);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaMemcpy(&sum2, scratch.result, sizeof(double), cudaMemcpyDeviceToHost));
    return true;
}

bool CudaMovieSession::collectAboveThreshold(
    double threshold,
    double guard,
    std::vector<int> &indices_ascending,
    size_t &guard_band_count
) {
    if (!is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t num_pixels = (size_t)ny * nx;

    // Chebyshev: sum (x-m)^2 = N*std^2 and every pixel above m + 6*std contributes
    // more than 36*std^2, so fewer than N/36 pixels can exceed the threshold.
    // Derived from N, never hard-coded, so EER super-resolution grids scale.
    // This assumes hotpixel_sigma == 6. That assumption is fail-safe rather than
    // load-bearing: a smaller sigma admits more hits, which trips the overflow
    // check below and falls back to the host scan. A perf cliff, not a wrong answer.
    const unsigned int capacity = (unsigned int)(num_pixels / 36 + 1);

    struct CollectScratch {
        int *hits = nullptr;
        unsigned int *counters = nullptr;   // [count, band, overflow]
        ~CollectScratch() {
            if (hits) cudaFree(hits);
            if (counters) cudaFree(counters);
        }
    } scratch;

    HANDLE_ERROR(cudaMalloc((void**)&scratch.hits, (size_t)capacity * sizeof(int)));
    HANDLE_ERROR(cudaMalloc((void**)&scratch.counters, 3 * sizeof(unsigned int)));
    HANDLE_ERROR(cudaMemset(scratch.counters, 0, 3 * sizeof(unsigned int)));

    collectAboveThresholdKernel<<<MC_STATS_BLOCKS, MC_STATS_THREADS>>>(
        d_Isum, num_pixels, threshold, guard,
        scratch.hits, capacity,
        scratch.counters, scratch.counters + 1, scratch.counters + 2);
    HANDLE_ERROR(cudaGetLastError());

    unsigned int host_counters[3] = {0, 0, 0};
    HANDLE_ERROR(cudaMemcpy(host_counters, scratch.counters, 3 * sizeof(unsigned int),
                            cudaMemcpyDeviceToHost));

    if (host_counters[2] != 0 || host_counters[0] > capacity) {
        logfile << "WARNING: CUDA hot-pixel hit buffer overflowed (" << host_counters[0]
                << " > " << capacity << "); falling back to host scan." << std::endl;
        return false;
    }

    guard_band_count = (size_t)host_counters[1];
    indices_ascending.resize(host_counters[0]);
    if (host_counters[0] > 0) {
        HANDLE_ERROR(cudaMemcpy(indices_ascending.data(), scratch.hits,
                                (size_t)host_counters[0] * sizeof(int), cudaMemcpyDeviceToHost));
        // Emission order is arbitrary; ascending order is what the host scan produced.
        std::sort(indices_ascending.begin(), indices_ascending.end());
    }
    return true;
}

bool CudaMovieSession::updateDefectPixels(
    const std::vector<int> &bad_xs,
    const std::vector<int> &bad_ys,
    const std::vector<float> &replacements
) {
    if (!is_initialized) return false;
    const int n_bad = (int)bad_xs.size();
    if (n_bad == 0) return true;

    HANDLE_ERROR(cudaSetDevice(device_id));

    struct DefectScratch {
        int *xs = nullptr;
        int *ys = nullptr;
        float *values = nullptr;
        ~DefectScratch() {
            if (xs) cudaFree(xs);
            if (ys) cudaFree(ys);
            if (values) cudaFree(values);
        }
    } scratch;

    HANDLE_ERROR(cudaMalloc((void**)&scratch.xs, n_bad * sizeof(int)));
    HANDLE_ERROR(cudaMalloc((void**)&scratch.ys, n_bad * sizeof(int)));
    HANDLE_ERROR(cudaMalloc((void**)&scratch.values, (size_t)n_bad * n_frames * sizeof(float)));

    HANDLE_ERROR(cudaMemcpy(scratch.xs, bad_xs.data(), n_bad * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(scratch.ys, bad_ys.data(), n_bad * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(scratch.values, replacements.data(), (size_t)n_bad * n_frames * sizeof(float), cudaMemcpyHostToDevice));

    const int block = 256;
    const int grid = (n_bad + block - 1) / block;
    updateDefectKernel<<<grid, block>>>(d_Iframes, scratch.xs, scratch.ys, scratch.values, n_bad, nx, ny, n_frames);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaDeviceSynchronize());

    return true;
}

bool CudaMovieSession::computeGlobalForwardFFT() {
    if (!is_initialized || !has_plan_r2c || fft_batch_size == 0) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t real_stride = (size_t)nx * ny;
    const size_t complex_stride = (size_t)ny * nfx;
    for (int first = 0; first < n_frames; first += fft_batch_size) {
        const int count = std::min(fft_batch_size, n_frames - first);
        cufftHandle plan = count == fft_batch_size ? plan_r2c : plan_r2c_tail;
        if (count != fft_batch_size && !has_plan_r2c_tail) return false;
        CUFFT_CHECK(cufftExecR2C(plan, (cufftReal*)(d_Iframes + (size_t)first * real_stride),
                                 d_Fframes + (size_t)first * complex_stride));
        // The next plan reuses the same work area; execution failures surface here.
        HANDLE_ERROR(cudaDeviceSynchronize());
    }

    const float inv_size = 1.0f / ((float)nx * ny);
    const size_t total_comp_elems = (size_t)n_frames * ny * nfx;
    const int block = 256;
    const int grid = (int)((total_comp_elems + block - 1) / block);
    scaleComplexKernel<<<grid, block>>>(d_Fframes, total_comp_elems, inv_size);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaDeviceSynchronize());

    return true;
}

bool CudaMovieSession::computeGlobalInverseFFT() {
    if (!is_initialized || !has_plan_c2r || !d_inverse_tile || fft_batch_size == 0) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    // C2R can overwrite its input. Preserve each Fourier tile for dose weighting
    // and only reuse the tile after that transform has completed.
    const size_t real_stride = (size_t)nx * ny;
    const size_t complex_stride = (size_t)ny * nfx;
    for (int first = 0; first < n_frames; first += fft_batch_size) {
        const int count = std::min(fft_batch_size, n_frames - first);
        cufftHandle plan = count == fft_batch_size ? plan_c2r : plan_c2r_tail;
        if (count != fft_batch_size && !has_plan_c2r_tail) return false;
        HANDLE_ERROR(cudaMemcpy(d_inverse_tile, d_Fframes + (size_t)first * complex_stride,
                                (size_t)count * complex_stride * sizeof(cufftComplex),
                                cudaMemcpyDeviceToDevice));
        CUFFT_CHECK(cufftExecC2R(plan, d_inverse_tile,
                                 (cufftReal*)(d_Iframes + (size_t)first * real_stride)));
        HANDLE_ERROR(cudaDeviceSynchronize());
    }
    return true;
}

bool CudaMovieSession::preparePatchInVram(
    int x_start, int y_start,
    int patch_w, int patch_h,
    int n_groups, const int *group_start, const int *group_size,
    cufftComplex *d_out_fpatches
) {
    if (!is_initialized || n_groups == 0 || !d_out_fpatches) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const int patch_nfx = patch_w / 2 + 1;
    const size_t sz_all_patch_real = (size_t)n_groups * patch_h * patch_w * sizeof(float);

    // Reuse or allocate cached scratch buffers
    if (!d_Ipatches || sz_cached_Ipatches < sz_all_patch_real) {
        if (d_Ipatches) cudaFree(d_Ipatches);
        HANDLE_ERROR(cudaMalloc((void**)&d_Ipatches, sz_all_patch_real));
        sz_cached_Ipatches = sz_all_patch_real;
    }
    if (!d_group_start || cached_ngroups_alloc < n_groups) {
        if (d_group_start) cudaFree(d_group_start);
        if (d_group_size) cudaFree(d_group_size);
        HANDLE_ERROR(cudaMalloc((void**)&d_group_start, n_groups * sizeof(int)));
        HANDLE_ERROR(cudaMalloc((void**)&d_group_size, n_groups * sizeof(int)));
        cached_ngroups_alloc = n_groups;
    }

    HANDLE_ERROR(cudaMemcpy(d_group_start, group_start, n_groups * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(d_group_size, group_size, n_groups * sizeof(int), cudaMemcpyHostToDevice));

    dim3 block(16, 16);
    dim3 grid((patch_w + 15) / 16, (patch_h + 15) / 16, n_groups);
    cropAndGroupPatchResidentKernel<<<grid, block>>>(
        d_Iframes,
        d_Ipatches,
        nx, ny,
        x_start, y_start,
        patch_w, patch_h,
        d_group_start, d_group_size,
        n_groups
    );
    HANDLE_ERROR(cudaGetLastError());

    // Reuse cached batched cuFFT plan for patch transforms
    if (!has_plan_patch_r2c || cached_patch_w != patch_w || cached_patch_h != patch_h || cached_patch_ngroups != n_groups) {
        if (has_plan_patch_r2c) {
            cufftDestroy(plan_patch_r2c);
            has_plan_patch_r2c = false;
        }
        int n[2] = {patch_h, patch_w};
        CUFFT_CHECK(cufftPlanMany(&plan_patch_r2c, 2, n, NULL, 1, patch_h * patch_w,
                                  NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups));
        has_plan_patch_r2c = true;
        cached_patch_w = patch_w;
        cached_patch_h = patch_h;
        cached_patch_ngroups = n_groups;
    }

    CUFFT_CHECK(cufftExecR2C(plan_patch_r2c, (cufftReal*)d_Ipatches, d_out_fpatches));

    const float inv_patch_size = 1.0f / ((float)patch_w * patch_h);
    const size_t total_comp_elems = (size_t)n_groups * patch_h * patch_nfx;
    const int block_scale = 256;
    const int grid_scale = (int)((total_comp_elems + block_scale - 1) / block_scale);
    scaleComplexKernel<<<grid_scale, block_scale>>>(d_out_fpatches, total_comp_elems, inv_patch_size);
    HANDLE_ERROR(cudaGetLastError());

    return true;
}

bool CudaMovieSession::reconstructDoseWeighted(
    Image<float> &Isum,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model
) {
    if (!is_initialized) return false;
    return cudaDoseWeightAndInterpolateDevice(d_Fframes, Isum, nx, ny, n_frames, doses, apix, model, device_id, logfile);
}

bool CudaMovieSession::reconstructUnweighted(
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const ThirdOrderPolynomialModel *model
) {
    if (!is_initialized) return false;
    return cudaRealSpaceInterpolationDevice(d_Iframes, Isum, Isum_even, Isum_odd, nx, ny, n_frames, model, device_id, logfile);
}

bool CudaMovieSession::downloadFourierFrames(std::vector<MultidimArray<fComplex> > &Fframes) {
    if (!is_initialized || !d_Fframes) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t sz_comp_frame = (size_t)ny * nfx * sizeof(cufftComplex);
    Fframes.resize(n_frames);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        Fframes[iframe].reshape(ny, nfx);
        const cufftComplex *src = d_Fframes + (size_t)iframe * ny * nfx;
        HANDLE_ERROR(cudaMemcpy(Fframes[iframe].data, src, sz_comp_frame, cudaMemcpyDeviceToHost));
    }
    return true;
}

bool CudaMovieSession::downloadRealFrames(std::vector<Image<float> > &Iframes) {
    if (!is_initialized || !d_Iframes) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t sz_real_frame = (size_t)ny * nx * sizeof(float);
    Iframes.resize(n_frames);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        Iframes[iframe]().reshape(ny, nx);
        const float *src = d_Iframes + (size_t)iframe * ny * nx;
        HANDLE_ERROR(cudaMemcpy(Iframes[iframe]().data, src, sz_real_frame, cudaMemcpyDeviceToHost));
    }
    return true;
}

#endif // _CUDA_ENABLED
