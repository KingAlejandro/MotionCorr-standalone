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
// memcmp keys the patch-descriptor cache below and is not nvCOMP-specific, so
// <cstring> is included unconditionally rather than inside the guard.
#include <cstring>
#include "src/acc/cuda/cuda_scoped_resources.h"
#if defined(_NVCOMP_ENABLED)
#include <tiffio.h>
#include <cstdint>
#include <cstdlib>
#include "nvcomp.h"
#include "nvcomp/deflate.h"
#include "src/acc/cuda/cuda_deflate_layout.h"
#endif


// Issue #69. These handlers CONSUME the error: they read it, log it, and return false.
// By the time the caller regains control, cudaGetLastError() has been reset and reports
// cudaSuccess, which is not a certificate that the context is healthy -- it only means
// nobody has recorded anything since. So each handler also records the code and the
// stage on the session, and the caller decides from that recorded status rather than
// from a later last-error read.
#undef HANDLE_ERROR
#define HANDLE_ERROR(cmd) do { \
    cudaError_t err = (cmd); \
    if (err != cudaSuccess) { \
        logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << cudaGetErrorString(err) << std::endl; \
        recordFailure(err, __func__, __LINE__); \
        return false; \
    } \
} while (0)

#undef CUFFT_CHECK
#define CUFFT_CHECK(cmd) do { \
    cufftResult res = (cmd); \
    if (res != CUFFT_SUCCESS) { \
        logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << res << std::endl; \
        recordCufftFailure(res, __func__, __LINE__); \
        return false; \
    } \
} while (0)

namespace {

__global__ void fusedGainAndSumKernel(
    float * __restrict__ d_Iframes,
    float * __restrict__ d_Isum,
    const float * __restrict__ d_gain,
    const size_t num_pixels,
    const int n_frames,
    const bool apply_gain
) {
    size_t pixel = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (pixel >= num_pixels) return;

    float gain_val = apply_gain ? __ldg(&d_gain[pixel]) : 1.0f;
    float sum = 0.0f;
    #pragma unroll 4
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

// Issue #85 lane C: native uint16 staging. One frame per launch, so only a single
// frame-sized uint16 staging buffer is ever resident instead of a second whole movie.
//
// Arithmetic is pinned to the fused float kernel above, term for term:
//   (float)u16 is exact for every value in [0, 65535] (binary32 holds every integer
//   up to 2^24), so the converted sample equals the float that castPage2T produced
//   on the host and cudaMemcpy used to deliver.
//   __fmul_rn / __fadd_rn are the same IEEE-754 round-to-nearest operations the
//   compiler emits for `val *= gain` and `sum += val` there. They are written as
//   intrinsics rather than operators so that no -fmad contraction can fuse the
//   multiply into the accumulate: an FFMA rounds once where the reference rounds
//   twice, which would move d_Isum and with it the hot-pixel threshold.
//   d_Isum is memset to zero before frame 0 and accumulated in ascending frame
//   order, so the addend sequence per pixel is identical to the single-kernel
//   float accumulator. Spilling that accumulator to a float array between frames
//   is exact because it is a float there too.
__global__ void convertGainAndAccumulateU16Kernel(
    const unsigned short *d_src,
    float *d_frame_dst,
    float *d_Isum,
    const float *d_gain,
    const size_t num_pixels,
    const bool apply_gain
) {
    size_t pixel = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (pixel >= num_pixels) return;

    float val = (float)d_src[pixel];
    if (apply_gain) val = __fmul_rn(val, d_gain[pixel]);
    // Unconditional, unlike the float kernel: there the H2D copy had already
    // deposited the frame, so a no-gain movie needed no store. Here the device
    // buffer holds nothing until this line runs.
    d_frame_dst[pixel] = val;
    d_Isum[pixel] = __fadd_rn(d_Isum[pixel], val);
}

#if defined(_NVCOMP_ENABLED)
// Batched counterpart of fusedGainAndSumKernel for the nvCOMP ingestion path.
//
// Reads one batch of freshly decompressed uint16 rows out of the staging arena,
// applies the TIFF->MRC row flip and the gain, writes float frames into their final
// slots in the resident d_Iframes, and accumulates the unaligned sum.
//
// The sum is carried in d_Isum between batches rather than reduced per batch: each
// pixel is owned by exactly one thread per launch and launches are ordered on the
// stream, so reading d_Isum, adding this batch's frames in frame order and writing
// back reproduces the same left-to-right float accumulation order as the
// single-launch whole-movie kernel. Re-associating it per batch would not.
//
// src_row_stride_u16 is the padded row pitch of the staging arena in uint16 elements,
// not nx: nvCOMP requires each per-chunk output pointer to meet its own alignment,
// and nx*2 bytes is not guaranteed to be a multiple of it.
__global__ void fusedU16FlipGainAndSumKernel(
    const uint16_t *src_u16,
    float *dst_Iframes,
    float *dst_Isum,
    const float *d_gain,
    int nx,
    int ny,
    size_t src_row_stride_u16,
    int frame_offset,
    int batch_frames,
    bool first_batch,
    bool apply_gain
) {
    size_t x = (size_t)blockDim.x * (size_t)blockIdx.x + threadIdx.x;
    size_t dest_y = (size_t)blockDim.y * (size_t)blockIdx.y + threadIdx.y;
    if (x >= (size_t)nx || dest_y >= (size_t)ny) return;

    const size_t dest_pixel = dest_y * (size_t)nx + x;
    const size_t src_y = (size_t)(ny - 1 - dest_y);
    const float gain_val = apply_gain ? d_gain[dest_pixel] : 1.0f;
    float sum = first_batch ? 0.0f : dst_Isum[dest_pixel];

    for (int b = 0; b < batch_frames; b++) {
        const size_t src_idx = ((size_t)b * (size_t)ny + src_y) * src_row_stride_u16 + x;
        const float val = (float)src_u16[src_idx] * gain_val;
        dst_Iframes[((size_t)(frame_offset + b) * (size_t)ny + dest_y) * (size_t)nx + x] = val;
        sum += val;
    }
    dst_Isum[dest_pixel] = sum;
}
#endif

// RFC 1950 Adler-32 over each decompressed strip.
//
// Handing nvCOMP only bytes [2, n-4) discards the checksum LibTIFF's zlib path
// verifies for free. Per-chunk status and decompressed length do not replace it: a
// corruption that still inflates to the right number of bytes is reported as
// success. Recomputing it here restores the integrity semantics the fast path would
// otherwise silently weaken relative to the reader it replaces.
//
// One block per strip. The serial recurrence is avoided by using the closed forms
//   A = 1 + sum(d_i),   B = n + sum((n - i) * d_i)
// which are ordinary reductions; the modulo is applied once at the end. The
// weighted sum needs 64 bits: for a 7420-byte row it reaches ~1.4e10.
__global__ void adler32StripsKernel(
    const unsigned char *decomp_base,
    size_t row_pitch_bytes,
    size_t row_bytes,
    uint32_t *out_adler,
    size_t n_chunks
) {
    const size_t chunk = blockIdx.x;
    if (chunk >= n_chunks) return;
    const unsigned char *row = decomp_base + chunk * row_pitch_bytes;

    unsigned long long sum_d = 0, sum_w = 0;
    for (size_t i = threadIdx.x; i < row_bytes; i += blockDim.x) {
        const unsigned long long d = row[i];
        sum_d += d;
        sum_w += (unsigned long long)(row_bytes - i) * d;
    }
    __shared__ unsigned long long s_d[256];
    __shared__ unsigned long long s_w[256];
    s_d[threadIdx.x] = sum_d;
    s_w[threadIdx.x] = sum_w;
    __syncthreads();
    for (unsigned stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) {
            s_d[threadIdx.x] += s_d[threadIdx.x + stride];
            s_w[threadIdx.x] += s_w[threadIdx.x + stride];
        }
        __syncthreads();
    }
    if (threadIdx.x == 0) {
        const unsigned long long a = (1ull + s_d[0]) % 65521ull;
        const unsigned long long b = ((unsigned long long)row_bytes + s_w[0]) % 65521ull;
        out_adler[chunk] = (uint32_t)((b << 16) | a);
    }
}

// Sparse read-back for hot-pixel replacement. One thread per (defect, frame)
// sample. A negative y marks the Gaussian branch, which the host fills itself; the
// slot is still written so nothing uninitialised is copied back.
__global__ void gatherFrameSamplesKernel(
    const float *d_Iframes,
    int nx,
    int ny,
    const int *sample_frame,
    const int *sample_y,
    const int *sample_x,
    float *out,
    size_t n_samples
) {
    size_t i = (size_t)blockDim.x * (size_t)blockIdx.x + threadIdx.x;
    if (i >= n_samples) return;
    const int y = sample_y[i];
    if (y < 0) { out[i] = 0.0f; return; }
    out[i] = d_Iframes[((size_t)sample_frame[i] * (size_t)ny + (size_t)y) * (size_t)nx
                       + (size_t)sample_x[i]];
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

__global__ void scaleComplexKernel(cufftComplex * __restrict__ d_data, const size_t count, const float scale) {
    size_t idx = ((size_t)blockIdx.x * blockDim.x + threadIdx.x) * 2;
    if (idx + 1 < count) {
        float4 v = *reinterpret_cast<const float4*>(&d_data[idx]);
        v.x *= scale;
        v.y *= scale;
        v.z *= scale;
        v.w *= scale;
        *reinterpret_cast<float4*>(&d_data[idx]) = v;
    } else if (idx < count) {
        float2 v = *reinterpret_cast<const float2*>(&d_data[idx]);
        v.x *= scale;
        v.y *= scale;
        *reinterpret_cast<float2*>(&d_data[idx]) = v;
    }
}

__global__ void cropAndGroupPatchResidentKernel(
    const float * __restrict__ d_Iframes,
    float * __restrict__ d_Ipatches,
    const int nx, const int ny,
    const int x_start, const int y_start,
    const int patch_w, const int patch_h,
    const int * __restrict__ d_group_start,
    const int * __restrict__ d_group_size,
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

    size_t base_pixel = (size_t)src_y * nx + src_x;
    float sum = 0.0f;
    #pragma unroll 4
    for (int i = 0; i < g_size; i++) {
        int iframe = g_start + i;
        sum += __ldg(&d_Iframes[(size_t)iframe * frame_stride + base_pixel]);
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

// Delegates to CudaFailureState, which keeps the first failure for diagnostics AND
// latches any poisoning code monotonically. An earlier version of this function kept
// only the first failure, so a recoverable allocation miss on one patch suppressed the
// recording of a fatal fault on a later one -- PR107 review P1.
void CudaMovieSession::recordFailure(cudaError_t err, const char *stage, int line) {
    failure_state.record(err, stage, line);
}

void CudaMovieSession::recordCufftFailure(cufftResult res, const char *stage, int line) {
    failure_state.recordCufft(res, stage, line);
}

cudaError_t CudaMovieSession::releaseBuffer(void *&slot) noexcept {
    void *owned = slot;
    slot = nullptr;
    const cudaError_t err = owned ? cudaFree(owned) : cudaSuccess;
    recordFailure(err, "releaseBuffer", __LINE__);
    return err;
}

template<class T> cudaError_t CudaMovieSession::releaseBuffer(T *&slot) noexcept {
    void *owned = slot;
    slot = nullptr;
    return releaseBuffer(owned);
}

cufftResult CudaMovieSession::releasePlan(cufftHandle &slot, bool &owned) noexcept {
    const cufftHandle handle = slot;
    const bool release = owned;
    slot = 0;
    owned = false;
    const cufftResult err = release ? cufftDestroy(handle) : CUFFT_SUCCESS;
    recordCufftFailure(err, "releasePlan", __LINE__);
    // A cuFFT status alone does not certify context health.
    if (err != CUFFT_SUCCESS) recordFailure(cudaPeekAtLastError(), "releasePlan", __LINE__);
    return err;
}

bool CudaMovieSession::initialize() {
    if (failure_state.isPoisoned()) return false;
    if (is_initialized) return true;
    release();
    if (failure_state.isPoisoned()) return false;

    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    recordFailure(count_err, __func__, __LINE__);
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
        recordFailure(cuda_result, "initialize buffers", __LINE__);
        logfile << "ERROR: Movie buffer allocation failed: " << cudaGetErrorString(cuda_result) << std::endl;
        release();
        return false;
    }

    // cuFFT's automatic allocation must be disabled before either plan is made.
    // Two transforms share one work area because no plan here is ever given a stream,
    // so every execution runs on the default stream and the next one cannot start
    // until the previous has finished with the work area. That, not the per-frame
    // cudaDeviceSynchronize the forward loop used to do, is what makes sharing safe.
    // A single-frame batch keeps the inverse preservation tile to one frame.
    // The A100 batch-two sample exceeded the whole-process VRAM target.
    int n[2] = {ny, nx};
    auto make_plan = [&](cufftHandle &plan, bool &has_plan, size_t &work_bytes,
                         cufftType type) -> bool {
        cufftResult result = cufftCreate(&plan);
        if (result == CUFFT_SUCCESS) has_plan = true;
        if (result == CUFFT_SUCCESS) result = cufftSetAutoAllocation(plan, 0);
        if (result == CUFFT_SUCCESS) {
            const int input_distance = type == CUFFT_R2C ? nx * ny : ny * nfx;
            const int output_distance = type == CUFFT_R2C ? ny * nfx : nx * ny;
            result = cufftMakePlanMany(plan, 2, n, NULL, 1, input_distance,
                                       NULL, 1, output_distance, type, 1, &work_bytes);
        }
        if (result != CUFFT_SUCCESS) {
            recordCufftFailure(result, "initialize plan", __LINE__);
            recordFailure(cudaPeekAtLastError(), "initialize plan", __LINE__);
            logfile << "ERROR: cuFFT plan failed for " << nx << "x" << ny
                    << " batch=1 type=" << type
                    << " code=" << result << std::endl;
            return false;
        }
        return true;
    };
    if (!make_plan(plan_r2c, has_plan_r2c, fft_r2c_work_bytes, CUFFT_R2C) ||
        !make_plan(plan_c2r, has_plan_c2r, fft_c2r_work_bytes, CUFFT_C2R)) {
        release();
        return false;
    }

    fft_work_bytes = std::max(fft_r2c_work_bytes, fft_c2r_work_bytes);
    // cudaMalloc(0) is invalid on some CUDA runtimes even if cuFFT needs no work.
    cuda_result = cudaMalloc(&d_fft_work, std::max((size_t)1, fft_work_bytes));
    if (cuda_result == cudaSuccess)
        cuda_result = cudaMalloc((void**)&d_inverse_tile, sz_comp);
    if (cuda_result != cudaSuccess) {
        recordFailure(cuda_result, "initialize scratch", __LINE__);
        logfile << "ERROR: Movie FFT scratch allocation failed for batch=1"
                << " workspace=" << fft_work_bytes << " tile=" << sz_comp
                << ": " << cudaGetErrorString(cuda_result) << std::endl;
        release();
        return false;
    }
    auto attach_work = [&](cufftHandle plan, bool has_plan) -> bool {
        if (!has_plan) return true;
        cufftResult result = cufftSetWorkArea(plan, d_fft_work);
        if (result == CUFFT_SUCCESS) return true;
        recordCufftFailure(result, "initialize work area", __LINE__);
        recordFailure(cudaPeekAtLastError(), "initialize work area", __LINE__);
        logfile << "ERROR: cuFFT shared work area association failed with code " << result << std::endl;
        return false;
    };
    if (!attach_work(plan_r2c, has_plan_r2c) || !attach_work(plan_c2r, has_plan_c2r)) {
        release();
        return false;
    }
    logfile << "Movie FFT: batch=1"
            << " R2C work=" << fft_r2c_work_bytes << " C2R work=" << fft_c2r_work_bytes
            << " shared work=" << fft_work_bytes
            << " inverse tile=" << sz_comp << " bytes" << std::endl;

    fourier_guard.reset();
    is_initialized = true;
    return true;
}

void CudaMovieSession::release() {
    if (has_plan_r2c || has_plan_c2r || has_plan_patch_r2c)
        recordFailure(cudaDeviceSynchronize(), "release synchronize", __LINE__);
    // Destroy plans before their work areas; attempt all releases, even after error.
    releasePlan(plan_patch_r2c, has_plan_patch_r2c);
    releasePlan(plan_r2c, has_plan_r2c);
    releasePlan(plan_c2r, has_plan_c2r);
    releaseBuffer(d_fft_work);
    releaseBuffer(d_inverse_tile);
    releaseBuffer(d_Iframes);
    releaseBuffer(d_Fframes);
    releaseBuffer(d_Isum);
    releaseBuffer(d_gain);
    releaseBuffer(d_Ipatches);
    releaseBuffer(d_group_start);
    releaseBuffer(d_group_size);
    fft_r2c_work_bytes = fft_c2r_work_bytes = fft_work_bytes = 0;
    cached_patch_w = cached_patch_h = cached_patch_ngroups = 0;
    sz_cached_Ipatches = 0;
    cached_ngroups_alloc = 0;
    cached_group_start.clear();
    cached_group_size.clear();
    is_initialized = false;
}

bool CudaMovieSession::applyGainDefectsAndSum(
    const std::vector<Image<float> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
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

bool CudaMovieSession::applyGainDefectsAndSumU16(
    const std::vector<Image<unsigned short> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
    if ((int)raw_frames.size() != n_frames) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t num_pixels = (size_t)ny * nx;
    const size_t sz_real = num_pixels * sizeof(float);
    const size_t sz_u16 = num_pixels * sizeof(unsigned short);

    // One frame, not one movie. A whole-movie uint16 device buffer would add
    // 0.637 GiB to the high-water mark for this geometry and turn a host-memory
    // saving into a VRAM cost; a single frame adds 27 MiB for the duration of
    // this call. Owned locally so the bare `return false` in HANDLE_ERROR frees it.
    unsigned short *stage = nullptr;
    mc_cuda::ScopedDeviceMemory<1> stage_owner(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&stage, sz_u16));
    stage_owner.add(stage);

    bool apply_gain = (gain_ref != nullptr);
    if (apply_gain) {
        if (!d_gain) {
            HANDLE_ERROR(cudaMalloc((void**)&d_gain, sz_real));
        }
        HANDLE_ERROR(cudaMemcpy(d_gain, gain_ref->data, sz_real, cudaMemcpyHostToDevice));
    }

    // The accumulator starts at +0.0f exactly as `float sum = 0.0f` does. Seeding
    // frame 0 with a plain store instead would differ for a -0.0f product, which
    // a zero sample against a negative gain entry can produce.
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_real));

    const int block = 256;
    const int grid = (int)((num_pixels + block - 1) / block);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        // Per-frame upload keeps the same failure granularity as the float path:
        // a fault names a frame index and leaves the rest untransferred.
        HANDLE_ERROR(cudaMemcpy(stage, raw_frames[iframe]().data, sz_u16,
                                cudaMemcpyHostToDevice));
        convertGainAndAccumulateU16Kernel<<<grid, block>>>(
            stage, d_Iframes + (size_t)iframe * num_pixels, d_Isum, d_gain,
            num_pixels, apply_gain);
        HANDLE_ERROR(cudaGetLastError());
        // The blocking cudaMemcpy above is the reuse barrier for stage.ptr: it is
        // issued on the same (default) stream as the kernel, so frame i+1's copy
        // cannot start writing the buffer until frame i's kernel has retired.
    }

    if (download_sum) {
        unaligned_sum.reshape(ny, nx);
        HANDLE_ERROR(cudaMemcpy(unaligned_sum.data, d_Isum, sz_real, cudaMemcpyDeviceToHost));
    } else {
        // Same argument as the float path: without the D2H there is no other
        // synchronisation point, so a fault would surface at an unrelated later
        // call and bypass the caller's reset-and-fall-back recovery.
        HANDLE_ERROR(cudaDeviceSynchronize());
    }

    HANDLE_ERROR(stage_owner.releaseAll());
    return true;
}

bool CudaMovieSession::downloadUnalignedSum(MultidimArray<float> &unaligned_sum) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
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
};
} // namespace

bool CudaMovieSession::reduceUnalignedSum(double &sum1, double &sum_abs) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t num_pixels = (size_t)ny * nx;
    StatsScratch scratch;
    mc_cuda::ScopedDeviceMemory<3> memory_cleanup(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.partials, 2 * MC_STATS_BLOCKS * sizeof(double)));
    memory_cleanup.add(scratch.partials);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.result, 2 * sizeof(double)));
    memory_cleanup.add(scratch.result);
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
    HANDLE_ERROR(memory_cleanup.releaseAll());
    return true;
}

bool CudaMovieSession::reduceUnalignedSumSqDev(double mean, double &sum2) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    const size_t num_pixels = (size_t)ny * nx;
    StatsScratch scratch;
    mc_cuda::ScopedDeviceMemory<3> memory_cleanup(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.partials, MC_STATS_BLOCKS * sizeof(double)));
    memory_cleanup.add(scratch.partials);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.result, sizeof(double)));
    memory_cleanup.add(scratch.result);
    sumSqDevUnalignedKernel<<<MC_STATS_BLOCKS, MC_STATS_THREADS>>>(d_Isum, num_pixels, mean, scratch.partials);
    HANDLE_ERROR(cudaGetLastError());
    combinePartialsKernel<<<1, 1>>>(scratch.partials, MC_STATS_BLOCKS, scratch.result);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaMemcpy(&sum2, scratch.result, sizeof(double), cudaMemcpyDeviceToHost));
    HANDLE_ERROR(memory_cleanup.releaseAll());
    return true;
}

bool CudaMovieSession::collectAboveThreshold(
    double threshold,
    double guard,
    std::vector<int> &indices_ascending,
    size_t &guard_band_count
) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
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
    } scratch;

    mc_cuda::ScopedDeviceMemory<3> memory_cleanup(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.hits, (size_t)capacity * sizeof(int)));
    memory_cleanup.add(scratch.hits);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.counters, 3 * sizeof(unsigned int)));
    memory_cleanup.add(scratch.counters);
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
    HANDLE_ERROR(memory_cleanup.releaseAll());
    return true;
}

bool CudaMovieSession::updateDefectPixels(
    const std::vector<int> &bad_xs,
    const std::vector<int> &bad_ys,
    const std::vector<float> &replacements
) {
    if (failure_state.isPoisoned() || !is_initialized) return false;
    const int n_bad = (int)bad_xs.size();
    if (n_bad == 0) return true;

    HANDLE_ERROR(cudaSetDevice(device_id));

    struct DefectScratch {
        int *xs = nullptr;
        int *ys = nullptr;
        float *values = nullptr;
    } scratch;

    mc_cuda::ScopedDeviceMemory<3> memory_cleanup(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.xs, n_bad * sizeof(int)));
    memory_cleanup.add(scratch.xs);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.ys, n_bad * sizeof(int)));
    memory_cleanup.add(scratch.ys);
    HANDLE_ERROR(cudaMalloc((void**)&scratch.values, (size_t)n_bad * n_frames * sizeof(float)));
    memory_cleanup.add(scratch.values);

    HANDLE_ERROR(cudaMemcpy(scratch.xs, bad_xs.data(), n_bad * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(scratch.ys, bad_ys.data(), n_bad * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(scratch.values, replacements.data(), (size_t)n_bad * n_frames * sizeof(float), cudaMemcpyHostToDevice));

    const int block = 256;
    const int grid = (n_bad + block - 1) / block;
    updateDefectKernel<<<grid, block>>>(d_Iframes, scratch.xs, scratch.ys, scratch.values, n_bad, nx, ny, n_frames);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaDeviceSynchronize());

    HANDLE_ERROR(memory_cleanup.releaseAll());
    return true;
}

bool CudaMovieSession::releasePreprocessingBuffers() {
    if (failure_state.isPoisoned() || !is_initialized) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));
    HANDLE_ERROR(cudaDeviceSynchronize());
    // Issue #69: clear the member before the free, not after. HANDLE_ERROR returns on a
    // failing cudaFree, and leaving the pointer set would have release() free it a
    // second time at the end of the movie. A free that fails here means the context is
    // already unusable; freeing the same pointer again cannot repair that.
    cudaError_t free_error = cudaSuccess;
    if (d_gain) {
        float *owned_gain = d_gain;
        d_gain = nullptr;
        free_error = releaseBuffer(owned_gain);
    }
    if (d_Isum) {
        float *owned_sum = d_Isum;
        d_Isum = nullptr;
        const cudaError_t sum_error = releaseBuffer(owned_sum);
        if (free_error == cudaSuccess) free_error = sum_error;
    }
    HANDLE_ERROR(free_error);
    return true;
}

// Ingest-scratch teardown. Outside the nvCOMP guard for the same reason
// gatherFrameSamples is: gatherFrameSamples calls it, the declaration in the
// header is unconditional, and nothing in it touches nvCOMP -- it is a CUDA
// stream and the Fourier-storage guard. Leaving it inside the guard is what
// made the CUDA-without-nvCOMP link fail on CI run 317 after the previous
// commit moved its only unguarded caller out.
void CudaMovieSession::endIngestScratch() {
    if (ingest_stream) {
        // Nothing may still be reading or writing the arena when the FFT phase takes
        // d_Fframes back. There is no host work worth overlapping at this boundary,
        // so this synchronises rather than handing an event to a later stream.
        recordFailure(cudaStreamSynchronize(ingest_stream), "ingest scratch sync", __LINE__);
        recordFailure(cudaStreamDestroy(ingest_stream), "ingest scratch stream", __LINE__);
        ingest_stream = 0;
    }
    fourier_guard.finishIngestScratch();
}

MovieIngestStatus CudaMovieSession::ingestMovie(
    const std::string &fn_mic,
    const std::vector<int> &frames,
    const MultidimArray<float> *gain_ref,
    int n_threads
) {
#if !defined(_NVCOMP_ENABLED)
    (void)fn_mic; (void)frames; (void)gain_ref; (void)n_threads;
    return MovieIngestStatus::NotApplicable;
#else
    if (!is_initialized) return MovieIngestStatus::NotApplicable;
    if (failure_state.isPoisoned()) return MovieIngestStatus::FatalDeviceFailure;

    // Snapshot, because CudaFailureState keeps the FIRST failure: without this
    // a benign error recorded earlier in the movie would be read as this
    // call's, and an error this call recorded would be invisible if one was
    // already there.
    const bool       was_poisoned = failure_state.isPoisoned();
    const cudaError_t before_err  = failure_state.firstError();
    const cufftResult before_cufft = failure_state.firstCufftError();

    const bool worker_ok = ingestCompressedTiffStrips(fn_mic, frames, gain_ref, n_threads);

    // By here the worker's ScratchScope has run: cudaStreamSynchronize and
    // cudaStreamDestroy have been attempted and anything they returned is in
    // the failure state. That is the whole reason this comparison happens
    // after the call rather than inside it.
    const bool now_poisoned = failure_state.isPoisoned();
    const bool new_cuda_error  = (before_err == cudaSuccess &&
                                  failure_state.firstError() != cudaSuccess);
    const bool new_cufft_error = (before_cufft == CUFFT_SUCCESS &&
                                  failure_state.firstCufftError() != CUFFT_SUCCESS);

    if (now_poisoned && !was_poisoned) {
        logfile << "ERROR: the CUDA context became unusable during device ingestion of "
                << fn_mic << "; refusing to report a successful ingest." << std::endl;
        return MovieIngestStatus::FatalDeviceFailure;
    }
    if (worker_ok && (new_cuda_error || new_cufft_error)) {
        // The decode itself reported success, but the teardown did not. The
        // resident movie cannot be trusted, so this is a failure even though
        // every per-chunk check passed.
        logfile << "WARNING: device ingestion of " << fn_mic << " reported success but its"
                << " scratch teardown recorded an error (" 
                << cudaGetErrorString(failure_state.firstError()) << " at "
                << failure_state.firstStage() << ":" << failure_state.firstLine()
                << "); treating the ingest as failed and using the host reader."
                << std::endl;
        return MovieIngestStatus::RecoverableFailure;
    }
    if (worker_ok) return MovieIngestStatus::Success;

    // Declined. A CUDA error recorded during the attempt means the fast path
    // tried and failed on the device; no new error means it refused the
    // encoding, the pinned budget or the arena before touching anything, which
    // is an ordinary "not applicable for this movie" and not a fault.
    return (new_cuda_error || new_cufft_error) ? MovieIngestStatus::RecoverableFailure
                                               : MovieIngestStatus::NotApplicable;
#endif
}

// Sparse device read-back for hot-pixel replacement. Deliberately OUTSIDE the
// nvCOMP guard: the declaration in the header is unconditional and the call site
// in motioncorr_runner.cpp is guarded by _CUDA_ENABLED, not _NVCOMP_ENABLED, so a
// CUDA build without nvCOMP must still provide this symbol. It previously sat
// inside the guard and that configuration only linked because the optimiser could
// prove nvcomp_ingested was always false and dropped the call; adding code near
// the call site was enough to stop it doing so, and the link then failed.
// Nothing here uses nvCOMP -- it is the shared pre-FFT arena and one plain kernel.
bool CudaMovieSession::gatherFrameSamples(
    const std::vector<int> &sample_frame,
    const std::vector<int> &sample_y,
    const std::vector<int> &sample_x,
    std::vector<float> &out
) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Iframes || !d_Fframes) return false;
    const size_t n = sample_frame.size();
    if (sample_y.size() != n || sample_x.size() != n) return false;
    out.assign(n, 0.0f);
    if (n == 0) return true;
    HANDLE_ERROR(cudaSetDevice(device_id));

    // Bounds are checked here rather than in the kernel: an out-of-range coordinate
    // means the caller's mask and the device geometry disagree, which is a defect in
    // the caller, not an input to tolerate with a clamp.
    for (size_t i = 0; i < n; i++) {
        if (sample_y[i] < 0) continue;
        if (sample_frame[i] < 0 || sample_frame[i] >= n_frames ||
            sample_y[i] >= ny || sample_x[i] < 0 || sample_x[i] >= nx) {
            logfile << "ERROR: defect neighbour sample " << i << " out of range: frame="
                    << sample_frame[i] << " y=" << sample_y[i] << " x=" << sample_x[i]
                    << std::endl;
            return false;
        }
    }

    // Same borrowed arena as the ingest: still pre-FFT here, so no allocation.
    if (!fourier_guard.beginIngestScratch()) return false;
    struct ScratchScope {
        CudaMovieSession *session;
        ~ScratchScope() { session->endIngestScratch(); }
    } scratch_scope = { this };

    mc_cuda::DeviceScratchArena arena(
        d_Fframes, (size_t)n_frames * (size_t)ny * (size_t)nfx * sizeof(cufftComplex));
    int *d_f = (int *)arena.alloc(n * sizeof(int), sizeof(int));
    int *d_y = (int *)arena.alloc(n * sizeof(int), sizeof(int));
    int *d_x = (int *)arena.alloc(n * sizeof(int), sizeof(int));
    float *d_out = (float *)arena.alloc(n * sizeof(float), sizeof(float));
    if (!d_f || !d_y || !d_x || !d_out) {
        logfile << "ERROR: " << n << " defect neighbour samples do not fit the "
                << arena.capacity() << "-byte pre-FFT scratch arena." << std::endl;
        return false;
    }

    HANDLE_ERROR(cudaStreamCreate(&ingest_stream));
    cudaStream_t stream = ingest_stream;
    HANDLE_ERROR(cudaMemcpyAsync(d_f, sample_frame.data(), n * sizeof(int), cudaMemcpyHostToDevice, stream));
    HANDLE_ERROR(cudaMemcpyAsync(d_y, sample_y.data(), n * sizeof(int), cudaMemcpyHostToDevice, stream));
    HANDLE_ERROR(cudaMemcpyAsync(d_x, sample_x.data(), n * sizeof(int), cudaMemcpyHostToDevice, stream));
    const int block = 256;
    const int grid = (int)((n + block - 1) / block);
    gatherFrameSamplesKernel<<<grid, block, 0, stream>>>(
        d_Iframes, nx, ny, d_f, d_y, d_x, d_out, n);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaMemcpyAsync(out.data(), d_out, n * sizeof(float), cudaMemcpyDeviceToHost, stream));
    HANDLE_ERROR(cudaStreamSynchronize(stream));
    return true;
}

#if defined(_NVCOMP_ENABLED)
using mc_tiff_deflate::alignUp;
using mc_tiff_deflate::stripSlotOffset;
using mc_tiff_deflate::frameStageBytes;
using mc_tiff_deflate::zlibWrapperIsUsable;

namespace {
// Worker-lifetime pinned staging for the compressed strips.
//
// CudaMovieSession is constructed and destroyed once per movie
// (motioncorr_runner.cpp), so a session-owned buffer would pay cudaHostAlloc and
// cudaFreeHost on every movie: measured at ~110 ms and ~43 ms for 126 MiB on an
// A100 host, which is most of what the faster ingest buys back. The pool outlives
// the session and is grown, never shrunk.
//
// thread_local, not a shared static: movies are dispatched one at a time here, but
// a worker-per-thread arrangement must not share one pinned buffer. One device per
// process is assumed, which is already how --gpu behaves.
struct PinnedStagePool {
    void *ptr = nullptr;
    size_t bytes = 0;
    // Destroyed at thread exit, possibly after the CUDA context has gone; the
    // status is deliberately ignored because there is nowhere left to report it.
    ~PinnedStagePool() { if (ptr) cudaFreeHost(ptr); }
};
thread_local PinnedStagePool t_pinned_stage;
} // namespace

bool CudaMovieSession::ensurePinnedStage(size_t bytes) {
    if (t_pinned_stage.ptr && t_pinned_stage.bytes >= bytes) return true;
    if (t_pinned_stage.ptr) {
        HANDLE_ERROR(cudaFreeHost(t_pinned_stage.ptr));
        t_pinned_stage.ptr = nullptr;
        t_pinned_stage.bytes = 0;
    }
    // Headroom, rounded to 32 MiB. Compressed size drifts by a few MiB between
    // movies of the same geometry, so an exact fit reallocated on 7 of 24 tutorial
    // movies; with slack the pool is allocated once for the run.
    const size_t reserve = mc_tiff_deflate::pinnedReserveBytes(bytes);
    HANDLE_ERROR(cudaHostAlloc(&t_pinned_stage.ptr, reserve, cudaHostAllocDefault));
    t_pinned_stage.bytes = reserve;
    // Logged only when the pool actually grows, so "allocated once across the run"
    // is something the log can show rather than something the design merely claims.
    logfile << "nvCOMP ingestion: pinned staging pool grown to " << reserve
            << " bytes for a " << bytes << "-byte request (worker lifetime)" << std::endl;
    return true;
}



bool CudaMovieSession::ingestCompressedTiffStrips(
    const std::string &fn_mic,
    const std::vector<int> &frames,
    const MultidimArray<float> *gain_ref,
    int n_threads
) {
    if (failure_state.isPoisoned() || !is_initialized) return false;
    if (!d_Iframes || !d_Isum || !d_Fframes) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const int num_req_frames = (int)frames.size();
    if (num_req_frames != n_frames || n_frames <= 0 || nx <= 0 || ny <= 0) return false;

    // ------------------------------------------------------------------
    // Pass A: geometry and per-strip compressed sizes. Tag reads only; no
    // payload leaves the disk here, so the whole layout can be planned before
    // a single byte is staged.
    // ------------------------------------------------------------------
    std::vector<std::vector<uint32_t> > raw_sizes(num_req_frames);
    {
        TIFF *tif = TIFFOpen(fn_mic.c_str(), "r");
        if (!tif) return false;
        bool ok = true;
        const char *reject = nullptr;
        // Raw Deflate decompression reproduces only what LibTIFF would do for one
        // exactly-specified encoding. Everything outside that subset must fall back
        // rather than be decoded with the wrong semantics, so the eligible encoding
        // is enumerated positively: any tag this path does not implement is a
        // refusal, not a default.
        if (TIFFIsByteSwapped(tif)) reject = "non-native byte order";
        for (int f = 0; f < num_req_frames && ok && !reject; f++) {
            if (!TIFFSetDirectory(tif, frames[f])) { ok = false; break; }
            uint32_t width = 0, height = 0;
            uint16_t bits = 0, compression = 0, planar = PLANARCONFIG_CONTIG, samples = 1;
            uint16_t predictor = PREDICTOR_NONE, sample_format = SAMPLEFORMAT_UINT;
            uint16_t fill_order = FILLORDER_MSB2LSB;
            TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &width);
            TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &height);
            TIFFGetField(tif, TIFFTAG_BITSPERSAMPLE, &bits);
            TIFFGetField(tif, TIFFTAG_COMPRESSION, &compression);
            TIFFGetFieldDefaulted(tif, TIFFTAG_PLANARCONFIG, &planar);
            TIFFGetFieldDefaulted(tif, TIFFTAG_SAMPLESPERPIXEL, &samples);
            TIFFGetFieldDefaulted(tif, TIFFTAG_PREDICTOR, &predictor);
            TIFFGetFieldDefaulted(tif, TIFFTAG_SAMPLEFORMAT, &sample_format);
            TIFFGetFieldDefaulted(tif, TIFFTAG_FILLORDER, &fill_order);
            // Horizontal differencing is undone by LibTIFF after inflation; this
            // path hands the inflated bytes straight to the cast, so predictor 2
            // would silently produce differences instead of samples.
            if (predictor != PREDICTOR_NONE)             reject = "TIFFTAG_PREDICTOR != 1";
            // The cast kernel reads uint16. Signed or float samples of the same
            // width would be reinterpreted rather than converted.
            else if (sample_format != SAMPLEFORMAT_UINT) reject = "TIFFTAG_SAMPLEFORMAT != UINT";
            else if (fill_order != FILLORDER_MSB2LSB)    reject = "non-native TIFFTAG_FILLORDER";
            else if ((int)width != nx || (int)height != ny) reject = "frame geometry differs";
            else if (bits != 16)                         reject = "bits per sample != 16";
            else if (samples != 1)                       reject = "samples per pixel != 1";
            else if (planar != PLANARCONFIG_CONTIG)      reject = "planar configuration not contiguous";
            else if (compression != COMPRESSION_DEFLATE &&
                     compression != COMPRESSION_ADOBE_DEFLATE) reject = "compression is not Deflate";
            if (reject) break;
            // One row per strip is what makes a strip a self-contained Deflate stream
            // of exactly nx uint16 samples. Anything else changes the chunk geometry.
            if ((int)TIFFNumberOfStrips(tif) != ny ||
                TIFFStripSize(tif) != (tmsize_t)((size_t)nx * sizeof(uint16_t))) {
                reject = "strip layout is not one full row per strip";
                break;
            }
            raw_sizes[f].resize(ny);
            for (int s = 0; s < ny; s++) {
                const tmsize_t rs = TIFFRawStripSize(tif, s);
                if (rs < 7 || (uint64_t)rs > 0xFFFFFFFFull) { ok = false; break; }
                raw_sizes[f][s] = (uint32_t)rs;
            }
            if (!ok || (int)raw_sizes[f].size() != ny) { ok = false; break; }
        }
        TIFFClose(tif);
        if (reject) {
            // Named, so an unexpected fallback is diagnosable from the log rather
            // than showing up only as the slower path being taken.
            logfile << "nvCOMP ingestion declined (" << reject
                    << "); using the host reader." << std::endl;
            return false;
        }
        if (!ok) return false;
    }

    // ------------------------------------------------------------------
    // Staging geometry. Both the compressed inputs and the decompressed outputs
    // must satisfy the alignment nvCOMP reports for this build of the library;
    // the previous revision passed base+2 pointers, which is outside the API
    // contract. Query rather than assume.
    // ------------------------------------------------------------------
    nvcompAlignmentRequirements_t align_req;
    std::memset(&align_req, 0, sizeof(align_req));
    if (nvcompBatchedDeflateDecompressGetRequiredAlignments(
            nvcompBatchedDeflateDecompressDefaultOpts, &align_req) != nvcompSuccess) {
        return false;
    }
    const size_t in_align  = std::max<size_t>((size_t)align_req.input, 1);
    const size_t out_align = std::max<size_t>((size_t)align_req.output, sizeof(uint16_t));
    const size_t tmp_align = std::max<size_t>((size_t)align_req.temp, 256);

    const size_t row_bytes = (size_t)nx * sizeof(uint16_t);
    const size_t row_pitch_bytes = alignUp(row_bytes, out_align);
    if (row_pitch_bytes % sizeof(uint16_t) != 0) return false;
    const size_t row_pitch_u16 = row_pitch_bytes / sizeof(uint16_t);

    // Compressed bytes a single frame occupies once every payload is placed so that
    // its raw Deflate start (strip start + 2) is in_align-aligned.
    std::vector<size_t> frame_stage_bytes(num_req_frames, 0);
    size_t max_frame_stage = 0;
    for (int f = 0; f < num_req_frames; f++) {
        const size_t cursor = frameStageBytes(raw_sizes[f].data(), ny, in_align);
        frame_stage_bytes[f] = cursor;
        max_frame_stage = std::max(max_frame_stage, cursor);
    }

    // ------------------------------------------------------------------
    // Claim d_Fframes as ingest scratch. initialize() already allocated it for the
    // spectrum, nothing writes it until computeGlobalForwardFFT(), and that
    // transform overwrites every element -- so the whole ingest working set can
    // live there and the session's VRAM high-water mark does not move. Then take
    // the largest frame batch that fits.
    // ------------------------------------------------------------------
    if (!fourier_guard.beginIngestScratch()) {
        logfile << "WARNING: nvCOMP ingestion refused: the Fourier buffer is not free."
                << std::endl;
        return false;
    }
    // Local class: has the enclosing member function's access, so no friend needed.
    struct ScratchScope {
        CudaMovieSession *session;
        ~ScratchScope() { session->endIngestScratch(); }
    } scratch_scope = { this };

    mc_cuda::DeviceScratchArena arena(
        d_Fframes, (size_t)n_frames * (size_t)ny * (size_t)nfx * sizeof(cufftComplex));

    // Pinned host memory is a per-worker resource, not a per-session one, and under
    // a process-per-GPU layout the pools add up across workers. Cap it and let the
    // cap bound the batch as the arena does, rather than letting a large movie size
    // the pool by itself.
    size_t pinned_cap = (size_t)256 << 20;
    if (const char *env = getenv("MOTIONCORR_NVCOMP_PINNED_MAX_MB")) {
        size_t parsed = 0;
        if (mc_tiff_deflate::parsePinnedCapBytes(env, parsed)) {
            pinned_cap = parsed;
        } else {
            // Say so. Silently substituting the default is how "1G" became a
            // 1 MiB cap that turned the fast path off for a whole run with no
            // message naming the cause.
            logfile << "WARNING: MOTIONCORR_NVCOMP_PINNED_MAX_MB is not a positive"
                    << " whole number of MiB; using the default " << pinned_cap
                    << " bytes." << std::endl;
        }
    }
    // The pool is never shrunk, so a cap lowered mid-run cannot be honoured by
    // declining a batch: those bytes are already pinned. Refuse rather than
    // report a budget the worker is not inside.
    if (t_pinned_stage.ptr && t_pinned_stage.bytes > pinned_cap) {
        logfile << "nvCOMP ingestion declined: this worker already holds "
                << t_pinned_stage.bytes << " pinned bytes, above the "
                << pinned_cap << "-byte cap; using the host reader." << std::endl;
        return false;
    }

    // Views into the arena. None of these owns memory; none may be freed.
    struct BatchViews {
        uint8_t *comp; uint16_t *u16;
        void **cptr; size_t *csize; void **dptr; size_t *dsize; size_t *asize;
        nvcompStatus_t *status; uint32_t *adler; void *temp;
        size_t comp_capacity, temp_bytes;
    };
    BatchViews v;
    std::memset(&v, 0, sizeof(v));
    int batch_frames = 0;

    for (int candidate = n_frames; candidate >= 1; candidate = (candidate > 1 ? candidate / 2 : 0)) {
        const size_t chunks = (size_t)candidate * (size_t)ny;
        size_t temp_bytes = 0;
        if (nvcompBatchedDeflateDecompressGetTempSizeAsync(
                chunks, row_bytes, nvcompBatchedDeflateDecompressDefaultOpts,
                &temp_bytes, (size_t)candidate * (size_t)ny * row_bytes) != nvcompSuccess) {
            break;
        }
        arena.reset();
        BatchViews c;
        std::memset(&c, 0, sizeof(c));
        c.comp_capacity = (size_t)candidate * alignUp(max_frame_stage, in_align);
        // Against the bytes that will actually be pinned, not the payload: the
        // pool adds 12.5% headroom and rounds up to a 32 MiB granule, so a cap
        // enforced on the payload is overshot by construction.
        if (mc_tiff_deflate::pinnedReserveBytes(c.comp_capacity) > pinned_cap) {
            if (candidate == 1) break;
            continue;
        }
        c.temp_bytes = temp_bytes;
        c.comp   = (uint8_t *)arena.alloc(c.comp_capacity, in_align);
        c.u16    = (uint16_t *)arena.alloc((size_t)candidate * (size_t)ny * row_pitch_bytes, out_align);
        c.cptr   = (void **)arena.alloc(chunks * sizeof(void *), sizeof(void *));
        c.csize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
        c.dptr   = (void **)arena.alloc(chunks * sizeof(void *), sizeof(void *));
        c.dsize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
        c.asize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
        c.status = (nvcompStatus_t *)arena.alloc(chunks * sizeof(nvcompStatus_t), sizeof(nvcompStatus_t));
        c.adler  = (uint32_t *)arena.alloc(chunks * sizeof(uint32_t), sizeof(uint32_t));
        bool fits = c.comp && c.u16 && c.cptr && c.csize && c.dptr && c.dsize && c.asize
                    && c.status && c.adler;
        if (fits && temp_bytes) {
            c.temp = arena.alloc(temp_bytes, tmp_align);
            fits = (c.temp != 0);
        }
        if (fits) { v = c; batch_frames = candidate; break; }
        if (candidate == 1) break;
    }
    if (batch_frames <= 0) {
        logfile << "nvCOMP ingestion declined: a one-frame batch fits neither the "
                << arena.capacity() << "-byte pre-FFT scratch arena nor the "
                << pinned_cap << "-byte pinned staging cap"
                << " (MOTIONCORR_NVCOMP_PINNED_MAX_MB); using the host reader." << std::endl;
        return false;
    }

    // The arena can only honour this because its base came from cudaMalloc. Checked
    // rather than assumed: a misaligned input is undefined behaviour in nvCOMP that
    // decodes correctly often enough to pass a pixel comparison.
    if (((uintptr_t)v.comp % in_align) != 0) return false;

    logfile << "nvCOMP ingestion: batch=" << batch_frames << "/" << n_frames
            << " frames, scratch=" << arena.used() << "/" << arena.capacity()
            << " bytes borrowed from the pre-FFT Fourier buffer (additional VRAM: 0)"
            << ", pinned staging=" << mc_tiff_deflate::pinnedReserveBytes(v.comp_capacity)
            << "/" << pinned_cap << " reserved, " << v.comp_capacity << " payload"
            << ", nvCOMP temp=" << v.temp_bytes
            << ", input alignment=" << in_align << std::endl;

    // ------------------------------------------------------------------
    // Host side: one pinned staging buffer sized for the worst batch, reused.
    // ------------------------------------------------------------------
    if (!ensurePinnedStage(v.comp_capacity)) return false;
    uint8_t *const h_stage = (uint8_t *)t_pinned_stage.ptr;

    const size_t max_chunks = (size_t)batch_frames * (size_t)ny;
    std::vector<void *>         h_comp_ptrs(max_chunks);
    std::vector<size_t>         h_comp_size(max_chunks);
    std::vector<void *>         h_dec_ptrs(max_chunks);
    std::vector<size_t>         h_dec_size(max_chunks, row_bytes);
    std::vector<size_t>         h_act_size(max_chunks);
    std::vector<nvcompStatus_t> h_statuses(max_chunks);
    std::vector<uint32_t>       h_adler_expected(max_chunks);
    std::vector<uint32_t>       h_adler_actual(max_chunks);

    const bool apply_gain = (gain_ref != nullptr);
    if (apply_gain) {
        const size_t sz_real = (size_t)ny * (size_t)nx * sizeof(float);
        if (!d_gain) HANDLE_ERROR(cudaMalloc((void **)&d_gain, sz_real));
        HANDLE_ERROR(cudaMemcpy(d_gain, gain_ref->data, sz_real, cudaMemcpyHostToDevice));
    }

    HANDLE_ERROR(cudaStreamCreate(&ingest_stream));
    cudaStream_t stream = ingest_stream;
    const int io_threads = n_threads > 0 ? n_threads : 4;

    // ------------------------------------------------------------------
    // Pass B: read, upload, decompress, verify and convert one batch at a time.
    // ------------------------------------------------------------------
    for (int f0 = 0; f0 < n_frames; f0 += batch_frames) {
        const int bf = std::min(batch_frames, n_frames - f0);
        const size_t chunks = (size_t)bf * (size_t)ny;

        std::vector<size_t> frame_base(bf);
        size_t stage_used = 0;
        for (int i = 0; i < bf; i++) {
            frame_base[i] = alignUp(stage_used, in_align);
            stage_used = frame_base[i] + frame_stage_bytes[f0 + i];
        }
        if (stage_used > v.comp_capacity) return false;

        std::vector<char> frame_ok(bf, 1);   // not vector<bool>: concurrent bit writes race
        #pragma omp parallel num_threads(io_threads)
        {
            TIFF *t = TIFFOpen(fn_mic.c_str(), "r");
            if (!t) {
                #pragma omp critical
                { for (int i = 0; i < bf; i++) frame_ok[i] = 0; }
            }
            // The worksharing construct is encountered by every thread of the
            // team, not just the ones that got a handle. OpenMP requires that,
            // and libgomp implements the loop's implicit barrier and the
            // parallel region's final barrier as the same team barrier: with
            // the `omp for` inside the else arm, a thread whose TIFFOpen failed
            // skipped one arrival, the barrier released a generation early, and
            // the threads that did stage frames then blocked forever on
            // arrivals that had already left. A failing thread has already
            // zeroed every frame_ok[i], so the batch is refused below whatever
            // its iterations would have done.
            #pragma omp for schedule(dynamic, 1)
            for (int i = 0; i < bf; i++) {
                    if (!t) continue;
                    const int f = f0 + i;
                    if (!TIFFSetDirectory(t, frames[f])) { frame_ok[i] = 0; continue; }
                    uint8_t *fb = h_stage + frame_base[i];
                    size_t cursor = 0;
                    bool ok = true;
                    for (int s = 0; s < ny && ok; s++) {
                        const size_t raw_sz = raw_sizes[f][s];
                        const size_t slot = stripSlotOffset(cursor, in_align);
                        if (TIFFReadRawStrip(t, s, fb + slot, (tmsize_t)raw_sz) != (tmsize_t)raw_sz) {
                            ok = false; break;
                        }
                        if (!zlibWrapperIsUsable(fb + slot, raw_sz)) {
                            // Named, because otherwise the only externally visible
                            // difference between this refusal and a read failure is
                            // that the movie fails -- which makes the guard
                            // impossible to tell apart from the one after it.
                            #pragma omp critical
                            logfile << "WARNING: strip " << s << " of frame " << f
                                    << " has an unusable zlib wrapper; falling back to"
                                       " the host reader." << std::endl;
                            ok = false;
                            break;
                        }
                        const size_t chunk = (size_t)i * (size_t)ny + (size_t)s;
                        // Payload only: the 2-byte zlib header and the 4-byte Adler32
                        // trailer are not part of the RFC 1951 stream nvCOMP consumes.
                        h_comp_ptrs[chunk] = v.comp + frame_base[i] + slot + 2;
                        h_comp_size[chunk] = raw_sz - 6;
                        h_dec_ptrs[chunk]  = (uint8_t *)v.u16 + chunk * row_pitch_bytes;
                        // Stored Adler-32: the last four bytes of the strip, big-endian.
                        const uint8_t *tr = fb + slot + raw_sz - 4;
                        h_adler_expected[chunk] = ((uint32_t)tr[0] << 24) | ((uint32_t)tr[1] << 16) |
                                                  ((uint32_t)tr[2] << 8)  |  (uint32_t)tr[3];
                        cursor = slot + raw_sz;
                    }
                    if (!ok) frame_ok[i] = 0;
            }
            if (t) TIFFClose(t);
        }
        for (int i = 0; i < bf; i++) if (!frame_ok[i]) return false;

        HANDLE_ERROR(cudaMemcpyAsync(v.comp, h_stage, stage_used, cudaMemcpyHostToDevice, stream));
        HANDLE_ERROR(cudaMemcpyAsync(v.cptr, h_comp_ptrs.data(), chunks * sizeof(void *), cudaMemcpyHostToDevice, stream));
        HANDLE_ERROR(cudaMemcpyAsync(v.csize, h_comp_size.data(), chunks * sizeof(size_t), cudaMemcpyHostToDevice, stream));
        HANDLE_ERROR(cudaMemcpyAsync(v.dptr,  h_dec_ptrs.data(),  chunks * sizeof(void *), cudaMemcpyHostToDevice, stream));
        HANDLE_ERROR(cudaMemcpyAsync(v.dsize,  h_dec_size.data(),  chunks * sizeof(size_t), cudaMemcpyHostToDevice, stream));

        if (nvcompBatchedDeflateDecompressAsync(
                (const void *const *)v.cptr, v.csize, v.dsize, v.asize,
                chunks, v.temp, v.temp_bytes, v.dptr,
                nvcompBatchedDeflateDecompressDefaultOpts, v.status, stream) != nvcompSuccess) {
            return false;
        }

        // Fail closed. Without this the batch buffer's previous contents, or raw
        // cudaMalloc garbage on the first batch, would be cast to float, gain-applied
        // and aligned as if it were image data, and the function would return success.
        adler32StripsKernel<<<(unsigned)chunks, 256, 0, stream>>>(
            (const unsigned char *)v.u16, row_pitch_bytes, row_bytes, v.adler, chunks);
        HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaMemcpyAsync(h_statuses.data(), v.status, chunks * sizeof(nvcompStatus_t), cudaMemcpyDeviceToHost, stream));
        HANDLE_ERROR(cudaMemcpyAsync(h_act_size.data(), v.asize, chunks * sizeof(size_t), cudaMemcpyDeviceToHost, stream));
        HANDLE_ERROR(cudaMemcpyAsync(h_adler_actual.data(), v.adler, chunks * sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
        HANDLE_ERROR(cudaStreamSynchronize(stream));
        for (size_t c = 0; c < chunks; c++) {
            if (h_adler_actual[c] != h_adler_expected[c]) {
                logfile << "WARNING: strip " << c << " of frames [" << f0 << ","
                        << (f0 + bf) << ") failed its zlib Adler-32 check: computed 0x"
                        << std::hex << h_adler_actual[c] << " stored 0x"
                        << h_adler_expected[c] << std::dec
                        << "; falling back to the host reader." << std::endl;
                return false;
            }
            if (h_statuses[c] != nvcompSuccess || h_act_size[c] != row_bytes) {
                logfile << "WARNING: nvCOMP rejected strip " << c << " of frames ["
                        << f0 << "," << (f0 + bf) << "): status=" << (int)h_statuses[c]
                        << " bytes=" << h_act_size[c] << " expected=" << row_bytes
                        << "; falling back to the host reader." << std::endl;
                return false;
            }
        }

        dim3 block(16, 16);
        dim3 grid((nx + block.x - 1) / block.x, (ny + block.y - 1) / block.y);
        fusedU16FlipGainAndSumKernel<<<grid, block, 0, stream>>>(
            v.u16, d_Iframes, d_Isum, d_gain, nx, ny, row_pitch_u16,
            f0, bf, f0 == 0, apply_gain);
        HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaStreamSynchronize(stream));
    }

    return true;
}
#endif

bool CudaMovieSession::computeGlobalForwardFFT() {
    if (failure_state.isPoisoned() || !is_initialized || !has_plan_r2c) return false;
    // Takes d_Fframes for the spectrum. Refused while ingest scratch views into the
    // same allocation are still live: the transform would otherwise overwrite
    // staging bytes that something is still reading, with no error anywhere.
    if (!fourier_guard.beginFourierWrite()) {
        logfile << "ERROR: forward FFT refused: the Fourier buffer still holds live "
                   "ingest scratch." << std::endl;
        return false;
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t real_stride = (size_t)nx * ny;
    const size_t complex_stride = (size_t)ny * nfx;
    for (int iframe = 0; iframe < n_frames; iframe++) {
        CUFFT_CHECK(cufftExecR2C(plan_r2c, (cufftReal*)(d_Iframes + (size_t)iframe * real_stride),
                                 d_Fframes + (size_t)iframe * complex_stride));
    }

    const float inv_size = 1.0f / ((float)nx * ny);
    const size_t total_comp_elems = (size_t)n_frames * ny * nfx;
    const size_t num_pairs = (total_comp_elems + 1) / 2;
    const int block = 256;
    const int grid = (int)((num_pairs + block - 1) / block);
    scaleComplexKernel<<<grid, block>>>(d_Fframes, total_comp_elems, inv_size);
    HANDLE_ERROR(cudaGetLastError());
    HANDLE_ERROR(cudaDeviceSynchronize());

    return true;
}

bool CudaMovieSession::computeGlobalInverseFFT() {
    if (failure_state.isPoisoned() || !is_initialized || !has_plan_c2r || !d_inverse_tile) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    // C2R can overwrite its input. Copies and transforms use the same default
    // stream, so each transform finishes before the next copy reuses its tile.
    const size_t real_stride = (size_t)nx * ny;
    const size_t complex_stride = (size_t)ny * nfx;
    for (int iframe = 0; iframe < n_frames; iframe++) {
        HANDLE_ERROR(cudaMemcpyAsync(d_inverse_tile, d_Fframes + (size_t)iframe * complex_stride,
                                     complex_stride * sizeof(cufftComplex),
                                     cudaMemcpyDeviceToDevice, 0));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, d_inverse_tile,
                                 (cufftReal*)(d_Iframes + (size_t)iframe * real_stride)));
    }
    HANDLE_ERROR(cudaDeviceSynchronize());
    return true;
}

bool CudaMovieSession::preparePatchInVram(
    int x_start, int y_start,
    int patch_w, int patch_h,
    int n_groups, const int *group_start, const int *group_size,
    cufftComplex *d_out_fpatches
) {
    // isPoisoned() first: a cached buffer or plan from an earlier patch must never be
    // handed to a dead context. n_groups <= 0 and the two descriptor pointers are
    // checked because the cache key below dereferences group_start/group_size.
    if (failure_state.isPoisoned() || !is_initialized || n_groups <= 0 ||
        !d_out_fpatches || !group_start || !group_size) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const int patch_nfx = patch_w / 2 + 1;
    const size_t sz_all_patch_real = (size_t)n_groups * patch_h * patch_w * sizeof(float);

    // Reuse or allocate the cached patch scratch.
    //
    // Issue #69. These members outlive the call: release() frees whatever they point at
    // when the movie ends. So the cache must never describe a buffer that does not
    // exist. Drop the claim (pointer and its size/count) before freeing, allocate into
    // a local, and publish only after the allocation succeeded. A failure exit then
    // leaves "no buffer, no claim" instead of a freed pointer release() would free a
    // second time, or a stale size that makes the next patch in this movie skip the
    // reallocation and copy into a null pointer.
    if (!d_Ipatches || sz_cached_Ipatches < sz_all_patch_real) {
        float *stale_patches = d_Ipatches;
        d_Ipatches = nullptr;
        sz_cached_Ipatches = 0;
        HANDLE_ERROR(releaseBuffer(stale_patches));
        float *fresh_patches = nullptr;
        HANDLE_ERROR(cudaMalloc((void**)&fresh_patches, sz_all_patch_real));
        d_Ipatches = fresh_patches;
        sz_cached_Ipatches = sz_all_patch_real;
    }

    // Group descriptors. Allocation is folded into the upload below rather than done
    // separately, so the common case -- the same grouping for every patch of a movie --
    // performs neither the allocation nor the two H2D copies.
    //
    // PR93's cross-call reuse: cached_group_start/cached_group_size are the host-side
    // key for what the device pair already holds. They are assigned ONLY after both
    // copies have returned cudaSuccess and are cleared before any copy starts, so a
    // skipped upload is licensed by a completed one, never by a partial one. A size
    // mismatch forces the upload before either memcmp runs, so an exact-length
    // comparison is what the skip rests on.
    //
    // Issue #69 ownership, adapted to PR93's allocate-then-free order: cudaMalloc and
    // cudaMemcpy results are recorded on the session rather than discarded, every free
    // goes through releaseBuffer() so its status is recorded too, and the members are
    // republished before the stale pair is freed -- so d_group_start/d_group_size never
    // name a buffer that does not exist, on any exit from this block.
    const size_t group_bytes = (size_t)n_groups * sizeof(int);
    const bool replace_groups = !d_group_start || !d_group_size || cached_ngroups_alloc < n_groups;
    const bool upload_groups = replace_groups ||
        cached_group_start.size() != (size_t)n_groups ||
        cached_group_size.size() != (size_t)n_groups ||
        memcmp(cached_group_start.data(), group_start, group_bytes) != 0 ||
        memcmp(cached_group_size.data(), group_size, group_bytes) != 0;
    if (upload_groups) {
        int *new_start = d_group_start;
        int *new_size = d_group_size;
        if (replace_groups) {
            new_start = nullptr;
            new_size = nullptr;
            cudaError_t alloc_error = cudaMalloc((void**)&new_start, group_bytes);
            if (alloc_error == cudaSuccess)
                alloc_error = cudaMalloc((void**)&new_size, group_bytes);
            if (alloc_error != cudaSuccess) {
                recordFailure(alloc_error, __func__, __LINE__);
                // Locals only. The members still own the previous pair, which is intact,
                // and cached_ngroups_alloc and the host key still describe it.
                releaseBuffer(new_start);
                releaseBuffer(new_size);
                logfile << "CUDA group allocation failed: " << cudaGetErrorString(alloc_error) << std::endl;
                return false;
            }
        }
        // Invalidate before either upload. A failed second copy must not leave
        // the old host key describing a partially overwritten device pair.
        cached_group_start.clear();
        cached_group_size.clear();
        cudaError_t copy_error = cudaMemcpy(new_start, group_start, group_bytes, cudaMemcpyHostToDevice);
        if (copy_error == cudaSuccess)
            copy_error = cudaMemcpy(new_size, group_size, group_bytes, cudaMemcpyHostToDevice);
        if (copy_error != cudaSuccess) {
            recordFailure(copy_error, __func__, __LINE__);
            if (replace_groups) { releaseBuffer(new_start); releaseBuffer(new_size); }
            logfile << "CUDA group upload failed: " << cudaGetErrorString(copy_error) << std::endl;
            return false;
        }
        if (replace_groups) {
            // Publish first, then free the stale pair: at no point do the members name
            // freed memory, and the host key is already empty, so an early return from
            // a failing free leaves "real buffers, no key" and the next patch re-uploads.
            int *stale_start = d_group_start;
            int *stale_size = d_group_size;
            d_group_start = new_start;
            d_group_size = new_size;
            cached_ngroups_alloc = n_groups;
            const cudaError_t start_free = releaseBuffer(stale_start);
            const cudaError_t size_free = releaseBuffer(stale_size);
            HANDLE_ERROR(start_free);
            HANDLE_ERROR(size_free);
        }
        cached_group_start.assign(group_start, group_start + n_groups);
        cached_group_size.assign(group_size, group_size + n_groups);
    }

    dim3 block(32, 8);
    dim3 grid((patch_w + 31) / 32, (patch_h + 7) / 8, n_groups);
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
        // Same rule as the buffers above: drop the geometry the cache claims before
        // destroying the plan, and publish the new one only once it exists.
        cached_patch_w = cached_patch_h = cached_patch_ngroups = 0;
        CUFFT_CHECK(releasePlan(plan_patch_r2c, has_plan_patch_r2c));
        CUFFT_CHECK(cufftCreate(&plan_patch_r2c));
        has_plan_patch_r2c = true;
        int n[2] = {patch_h, patch_w};
        size_t work_bytes = 0;
        CUFFT_CHECK(cufftMakePlanMany(plan_patch_r2c, 2, n, NULL, 1, patch_h * patch_w,
                                   NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups,
                                   &work_bytes));
        cached_patch_w = patch_w;
        cached_patch_h = patch_h;
        cached_patch_ngroups = n_groups;
    }

    CUFFT_CHECK(cufftExecR2C(plan_patch_r2c, (cufftReal*)d_Ipatches, d_out_fpatches));

    const float inv_patch_size = 1.0f / ((float)patch_w * patch_h);
    const size_t total_comp_elems = (size_t)n_groups * patch_h * patch_nfx;
    const size_t num_pairs = (total_comp_elems + 1) / 2;
    const int block_scale = 256;
    const int grid_scale = (int)((num_pairs + block_scale - 1) / block_scale);
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
    if (failure_state.isPoisoned() || !is_initialized) return false;
    return cudaDoseWeightAndInterpolateDevice(d_Fframes, Isum, nx, ny, n_frames, doses, apix, model, device_id, logfile, &failure_state);
}

bool CudaMovieSession::reconstructUnweighted(
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const ThirdOrderPolynomialModel *model
) {
    if (failure_state.isPoisoned() || !is_initialized) return false;
    return cudaRealSpaceInterpolationDevice(d_Iframes, Isum, Isum_even, Isum_odd, nx, ny, n_frames, model, device_id, logfile, &failure_state);
}

bool CudaMovieSession::downloadFourierFrames(std::vector<MultidimArray<fComplex> > &Fframes) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Fframes) return false;
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
    if (failure_state.isPoisoned() || !is_initialized || !d_Iframes) return false;
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
