#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_settings.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/stage_profile.h"

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include <iostream>
#include <vector>
#include <cmath>
#include <algorithm>
#include <climits>
#include "src/acc/cuda/cuda_scoped_resources.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#if defined(_NVCOMP_ENABLED)
#include <tiffio.h>
#include <unistd.h>
#include <cerrno>
#include <cstring>
#include <cstdint>
#include <cstdlib>
#include "nvcomp.h"
#include "nvcomp/deflate.h"
#include "src/acc/cuda/cuda_deflate_layout.h"
#include "src/acc/cuda/cuda_adler32_kernel.cuh"
#include "src/acc/cuda/cuda_reader_pool.h"
#include <atomic>
#include <mutex>
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

// Consecutive --profile sub-stages inside one function: next() closes the open
// sub-stage and opens the following one, the destructor closes the last, so
// early returns stay balanced. One branch per call when profiling is off.
class SubStageSequence {
public:
    SubStageSequence() : on(StageProfile::instance().enabled()) {}
    ~SubStageSequence() { end(); }
    void next(const char *name) {
        if (!on) return;
        if (open) StageProfile::instance().pop();
        StageProfile::instance().push(name);
        open = true;
    }
    void end() {
        if (on && open) StageProfile::instance().pop();
        open = false;
    }
    SubStageSequence(const SubStageSequence &) = delete;
    SubStageSequence &operator=(const SubStageSequence &) = delete;
private:
    bool on;
    bool open = false;
};

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

// Issue #85 lane C: native sample staging. One frame per launch, so only a single
// frame-sized native staging buffer is ever resident instead of a second whole movie.
// T is the file's own unsigned sample type: unsigned short for a 16-bit TIFF,
// unsigned char for an 8-bit one.
//
// Arithmetic is pinned to the fused float kernel above, term for term:
//   (float)T is exact for every value an 8- or 16-bit unsigned sample can hold
//   (binary32 holds every integer up to 2^24), so the converted sample equals the
//   float that castPage2T produced on the host and cudaMemcpy used to deliver.
//   __fmul_rn / __fadd_rn are the same IEEE-754 round-to-nearest operations the
//   compiler emits for `val *= gain` and `sum += val` there. They are written as
//   intrinsics rather than operators so that no -fmad contraction can fuse the
//   multiply into the accumulate: an FFMA rounds once where the reference rounds
//   twice, which would move d_Isum and with it the hot-pixel threshold.
//   d_Isum is memset to zero before frame 0 and accumulated in ascending frame
//   order, so the addend sequence per pixel is identical to the single-kernel
//   float accumulator. Spilling that accumulator to a float array between frames
//   is exact because it is a float there too.
//
// Signed sample types must never reach this kernel: (float)(signed char)0xFF is
// -1.0f where the reader's own cast produces the same -1.0f only because
// castPage2T went through the same signed type. The runner admits UChar and
// UShort by name, not by width, which is what keeps SChar/SShort out.
template <typename T>
__global__ void convertGainAndAccumulateNativeKernel(
    const T *d_src,
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
    : patch_alignment_workspace(&failure_state),
      batched_patch_alignment_workspace(&failure_state),
      nx(nx), ny(ny), n_frames(n_frames), device_id(device_id),
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

    mc_cuda::CudaWorkerPlanPool &gain_pool = mc_cuda::getWorkerPlanPool();
    const cudaError_t retired_error = gain_pool.retiredErrorFor(device_id);
    if (retired_error != cudaSuccess) {
        recordFailure(retired_error, "initialize retired gain cache", __LINE__);
        return false;
    }
    if (gain_generation != 0 && !gain_pool.acquireLease(this, device_id)) {
        recordFailure(cudaErrorNotReady, "initialize gain cache lease busy", __LINE__);
        return false;
    }
    // Discard an unused or mismatching entry BEFORE admitting the new movie.
    // Retiring it only during upload is too late: its bytes could already have
    // denied the movie buffers. A different live lease refuses this eviction.
    const mc_cuda::CudaWorkerPlanPool::GainPool &gain_entry = gain_pool.gain;
    if (gain_entry.ptr != nullptr &&
        (gain_generation == 0 || gain_entry.generation != gain_generation ||
         gain_entry.nx != nx || gain_entry.ny != ny || gain_entry.device_id != device_id)) {
        if (!gain_pool.dropAll(&failure_state, this)) {
            // Cleanup can be the first operation that reports a fatal context.
            // Retire it now, before another session can borrow this worker.
            release();
            return false;
        }
    }

    // Take the worker's retained geometry on an exact key hit. A mismatching or
    // invalidated entry is discarded before allocating, for the same admission
    // reason as the gain above.
    mc_cuda::CudaWorkerPlanPool::GeometryEntry &geometry = gain_pool.geometry;
    const bool took_geometry =
        mc_cuda::CudaWorkerPlanPool::geometryRetentionEnabled() &&
        geometry.matches(device_id, nx, ny, n_frames);
    if (took_geometry) {
        d_Iframes = geometry.iframes;
        d_Fframes = geometry.fframes;
        d_fft_work = geometry.fft_work;
        d_inverse_tile = geometry.inverse_tile;
        plan_r2c = geometry.plan_r2c;
        plan_c2r = geometry.plan_c2r;
        has_plan_r2c = geometry.has_plan_r2c;
        has_plan_c2r = geometry.has_plan_c2r;
        fft_r2c_work_bytes = geometry.r2c_work_bytes;
        fft_c2r_work_bytes = geometry.c2r_work_bytes;
        geometry.iframes = nullptr;
        geometry.fframes = nullptr;
        geometry.fft_work = nullptr;
        geometry.inverse_tile = nullptr;
        geometry.plan_r2c = geometry.plan_c2r = 0;
        geometry.has_plan_r2c = geometry.has_plan_c2r = false;
        geometry.clearKey();
    } else if (geometry.held() && !geometry.drop(&failure_state)) {
        release();
        return false;
    }

    // Allocate persistent movie buffers
    cudaError_t cuda_result = cudaSuccess;
    {
        StageScope alloc_scope("alloc movie buffers");
        if (!took_geometry) {
            cuda_result = cudaMalloc((void**)&d_Iframes, total_real_bytes);
            if (cuda_result == cudaSuccess) cuda_result = cudaMalloc((void**)&d_Fframes, total_comp_bytes);
        }
        if (cuda_result == cudaSuccess) cuda_result = cudaMalloc((void**)&d_Isum, sz_real);
    }
    if (cuda_result != cudaSuccess) {
        recordFailure(cuda_result, "initialize buffers", __LINE__);
        logfile << "ERROR: Movie buffer allocation failed: " << cudaGetErrorString(cuda_result) << std::endl;
        release();
        return false;
    }

    // cuFFT's automatic allocation must be disabled before either plan is made.
    // Two transforms share one work area because all executions use the default stream
    // and each frame is synchronized before the next execution.
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
    if (!took_geometry) {
        StageScope plan_scope("fft plans");
        if (!make_plan(plan_r2c, has_plan_r2c, fft_r2c_work_bytes, CUFFT_R2C) ||
            !make_plan(plan_c2r, has_plan_c2r, fft_c2r_work_bytes, CUFFT_C2R)) {
            release();
            return false;
        }
    }

    fft_work_bytes = std::max(fft_r2c_work_bytes, fft_c2r_work_bytes);
    if (!took_geometry) {
        StageScope scratch_alloc_scope("fft scratch");
        // cudaMalloc(0) is invalid on some CUDA runtimes even if cuFFT needs no work.
        cuda_result = cudaMalloc(&d_fft_work, std::max((size_t)1, fft_work_bytes));
        if (cuda_result == cudaSuccess)
            cuda_result = cudaMalloc((void**)&d_inverse_tile, sz_comp);
    }
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
    // Retained plans keep the work area attached when they were made.
    if (!took_geometry &&
        (!attach_work(plan_r2c, has_plan_r2c) || !attach_work(plan_c2r, has_plan_c2r))) {
        release();
        return false;
    }
    // Test hook shared with FrameBufferPool: a read of a reused buffer before
    // this movie writes it then sees NaN, not the previous movie's pixels.
    if (took_geometry && mc_cuda::CudaWorkerPlanPool::geometryPoisonRequested()) {
        cuda_result = cudaMemset(d_Iframes, 0xFF, total_real_bytes);
        if (cuda_result == cudaSuccess) cuda_result = cudaMemset(d_Fframes, 0xFF, total_comp_bytes);
        if (cuda_result == cudaSuccess)
            cuda_result = cudaMemset(d_fft_work, 0xFF, std::max((size_t)1, fft_work_bytes));
        if (cuda_result == cudaSuccess) cuda_result = cudaMemset(d_inverse_tile, 0xFF, sz_comp);
        if (cuda_result == cudaSuccess) cuda_result = cudaDeviceSynchronize();
        if (cuda_result != cudaSuccess) {
            recordFailure(cuda_result, "initialize poison retained geometry", __LINE__);
            release();
            return false;
        }
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
    // A session that failed or poisoned the context may have left a retained
    // resource in an unknown state, so the worker pool is retired with it
    // rather than handed to the next movie. Runs last, after this session has
    // dropped its own aliases, so nothing still points at a freed buffer.
    struct ReleaseFailureGuard {
        CudaFailureState &failure;
        const void *holder;
        int device;
        ~ReleaseFailureGuard() {
            mc_cuda::CudaWorkerPlanPool &pool = mc_cuda::getWorkerPlanPool();
            if (!failure.isPoisoned() && failure.hasFailed())
                (void)pool.dropAll(&failure, holder);
            // A checked drop may have promoted a recoverable error to fatal.
            // Test the updated state rather than only the state before cleanup.
            if (failure.isPoisoned())
                (void)pool.retire(device, &failure, holder);
        }
    } failure_guard{failure_state, this, device_id};

    // Alignment resources must also unwind after a patch throws. Its owners retain
    // both first-error provenance and any later poisoning cleanup code.
    (void)releasePatchAlignmentWorkspace();
    if (has_plan_r2c || has_plan_c2r || has_plan_patch_r2c)
        recordFailure(cudaDeviceSynchronize(), "release synchronize", __LINE__);
    // Hand the geometry resources to the next movie only from a session with no
    // recorded failure, after the synchronize above: they are idle, and nothing
    // this session did can have left them in an unknown state.
    {
        mc_cuda::CudaWorkerPlanPool &pool = mc_cuda::getWorkerPlanPool();
        mc_cuda::CudaWorkerPlanPool::GeometryEntry &geometry = pool.geometry;
        if (is_initialized && !failure_state.hasFailed() &&
            mc_cuda::CudaWorkerPlanPool::geometryRetentionEnabled() &&
            !pool.retiredFor(device_id) && !geometry.held() &&
            has_plan_r2c && has_plan_c2r && d_fft_work && d_inverse_tile &&
            d_Iframes && d_Fframes) {
            const size_t sz_comp = (size_t)ny * nfx * sizeof(cufftComplex);
            geometry.device_id = device_id;
            geometry.nx = nx;
            geometry.ny = ny;
            geometry.n_frames = n_frames;
            geometry.plan_r2c = plan_r2c;
            geometry.plan_c2r = plan_c2r;
            geometry.has_plan_r2c = geometry.has_plan_c2r = true;
            geometry.r2c_work_bytes = fft_r2c_work_bytes;
            geometry.c2r_work_bytes = fft_c2r_work_bytes;
            geometry.work_bytes = fft_work_bytes;
            geometry.fft_work = d_fft_work;
            geometry.inverse_tile = d_inverse_tile;
            geometry.iframes = d_Iframes;
            geometry.fframes = d_Fframes;
            geometry.bytes = (size_t)n_frames * ny * nx * sizeof(float) +
                             (size_t)n_frames * sz_comp +
                             std::max((size_t)1, fft_work_bytes) + sz_comp;
            geometry.valid = true;
            plan_r2c = plan_c2r = 0;
            has_plan_r2c = has_plan_c2r = false;
            d_fft_work = nullptr;
            d_inverse_tile = nullptr;
            d_Iframes = nullptr;
            d_Fframes = nullptr;
        }
    }
    // Destroy plans before their work areas; attempt all releases, even after error.
    releasePlan(plan_patch_r2c, has_plan_patch_r2c);
    releasePlan(plan_r2c, has_plan_r2c);
    releasePlan(plan_c2r, has_plan_c2r);
    releaseBuffer(d_fft_work);
    releaseBuffer(d_inverse_tile);
    releaseBuffer(d_Iframes);
    releaseBuffer(d_Fframes);
    releaseBuffer(d_Isum);
    // Only free a gain this session owns; a pooled one outlives it.
    if (!d_gain_borrowed) releaseBuffer(d_gain);
    d_gain = nullptr;
    d_gain_borrowed = false;
    releaseBuffer(d_Ipatches);
    releaseBuffer(d_patch_spectrum);
    releaseBuffer(d_group_start);
    releaseBuffer(d_group_size);
    real_frames_invalid_reason = nullptr;
    fft_r2c_work_bytes = fft_c2r_work_bytes = fft_work_bytes = 0;
    cached_patch_w = cached_patch_h = cached_patch_ngroups = 0;
    sz_cached_Ipatches = 0;
    sz_cached_patch_spectrum = 0;
    cached_ngroups_alloc = 0;
    uploaded_group_start.clear();
    uploaded_group_size.clear();
    is_initialized = false;
    (void)mc_cuda::getWorkerPlanPool().releaseLease(this);
}

// Point d_gain at a device copy of gain_ref, reusing the worker-lifetime pooled
// copy when its identity matches.
//
// CudaMovieSession is constructed per movie, so d_gain was cudaMalloc'd,
// uploaded and freed once per movie for an array whose contents cannot change
// unless the host gain cache is refilled. Measured on an A100 with the tutorial
// gain (3710x3838 float = 56,955,920 B), 24 movies, --ingest nvcomp: 24 uploads,
// 719.5 ms, which is 98.5% of all pageable H2D traffic in that arm. The runner
// already knows when the contents could have changed, so a generation counter on
// that refill is an exact identity and costs nothing -- no hashing of 54 MiB.
//
// Returns false on a CUDA error. Failed owning-device selection retains an
// invalidated owned entry for checked retry; it cannot serve a cache hit.
bool CudaMovieSession::ensureDeviceGain(const MultidimArray<float> *gain_ref, size_t sz_real) {
    mc_cuda::CudaWorkerPlanPool::GainPool &pool = mc_cuda::getWorkerPlanPool().gain;

    // Drop any alias this session holds before deciding anything, so a borrowed
    // pointer can never be mistaken for an owned one on the paths below.
    if (d_gain_borrowed) {
        d_gain = nullptr;
        d_gain_borrowed = false;
    }
    (void)mc_cuda::getWorkerPlanPool().releaseLease(this);
    // Releasing a session-owned copy is checked: a free that fails is evidence
    // about the context, not something to discard.
    auto release_owned = [&]() -> bool {
        if (d_gain == nullptr) return true;
        float *owned = d_gain;
        d_gain = nullptr;
        return releaseBuffer(owned) == cudaSuccess;
    };

    if (gain_ref == nullptr) {
        // No gain on this call. A copy this session owns from an earlier call
        // would otherwise stay allocated with nothing pointing at it.
        const bool ok = release_owned();
        d_gain = nullptr;
        d_gain_borrowed = false;
        return ok;
    }

    if (gain_generation == 0) {
        // No identity supplied: keep the original per-movie behaviour exactly.
        if (!d_gain) {
            HANDLE_ERROR(cudaMalloc((void**)&d_gain, sz_real));
        }
        HANDLE_ERROR(cudaMemcpy(d_gain, gain_ref->data, sz_real, cudaMemcpyHostToDevice));
        d_gain_borrowed = false;
        return true;
    }

    if (!mc_cuda::getWorkerPlanPool().acquireLease(this, device_id)) {
        const cudaError_t retired_error = mc_cuda::getWorkerPlanPool().retiredErrorFor(device_id);
        recordFailure(retired_error == cudaSuccess ? cudaErrorNotReady : retired_error,
                      "gain cache lease unavailable", __LINE__);
        return false;
    }

    const bool hit = pool.ptr != nullptr &&
                     pool.generation == gain_generation &&
                     pool.bytes == sz_real &&
                     pool.nx == nx && pool.ny == ny &&
                     pool.device_id == device_id;
    if (!hit) {
        // Retire the stale entry BEFORE allocating the replacement: an old large
        // geometry must not be able to deny a smaller valid movie, and a failure
        // below must not leave a stale buffer advertised under the new key.
        const bool dropped = pool.drop(&failure_state);
        const bool released = release_owned();
        if (!dropped || !released) {
            d_gain = nullptr;
            d_gain_borrowed = false;
            return false;
        }
        float *fresh = nullptr;
        // Not HANDLE_ERROR: the fresh buffer has to be freed before returning.
        const cudaError_t alloc_err = cudaMalloc((void **)&fresh, sz_real);
        if (alloc_err != cudaSuccess) {
            logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : "
                    << cudaGetErrorString(alloc_err) << std::endl;
            recordFailure(alloc_err, __func__, __LINE__);
            return false;
        }
        const cudaError_t copy_err = cudaMemcpy(fresh, gain_ref->data, sz_real, cudaMemcpyHostToDevice);
        if (copy_err != cudaSuccess) {
            logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : "
                    << cudaGetErrorString(copy_err) << std::endl;
            // The original cause is recorded first so it stays the first error;
            // a fatal cleanup code recorded after it still latches separately.
            recordFailure(copy_err, __func__, __LINE__);
            recordFailure(cudaFree(fresh), "ensureDeviceGain cleanup", __LINE__);
            return false;
        }
        pool.ptr = fresh;
        pool.bytes = sz_real;
        pool.generation = gain_generation;
        pool.nx = nx;
        pool.ny = ny;
        pool.device_id = device_id;
    } else if (!release_owned()) {
        d_gain = nullptr;
        d_gain_borrowed = false;
        return false;
    }
    d_gain = pool.ptr;
    d_gain_borrowed = true;
    return true;
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

    // Upload the gain reference if provided, or reuse the retained device copy.
    bool apply_gain = (gain_ref != nullptr);
    if (!ensureDeviceGain(gain_ref, sz_real)) return false;

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

// One definition for both native sample widths; the two public overloads below
// are the only entry points. Written as a template rather than copied because a
// copy would have to restate the memset-then-ascending-accumulate order that is
// what makes the products bit-identical to the float path, and a restated
// invariant drifts without the compiler or any test noticing.
template <typename T>
bool CudaMovieSession::applyGainDefectsAndSumNative(
    const std::vector<Image<T> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    if (failure_state.isPoisoned() || !is_initialized || !d_Isum) return false;
    if ((int)raw_frames.size() != n_frames) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const size_t num_pixels = (size_t)ny * nx;
    const size_t sz_real = num_pixels * sizeof(float);
    const size_t sz_native = num_pixels * sizeof(T);

    // One frame, not one movie. A whole-movie native device buffer would add
    // 0.637 GiB (uint16) to the high-water mark for this geometry and turn a host
    // -memory saving into a VRAM cost; a single frame adds 27 MiB for the duration
    // of this call. Owned locally so the bare `return false` in HANDLE_ERROR frees it.
    T *stage = nullptr;
    mc_cuda::ScopedDeviceMemory<1> stage_owner(&failure_state);
    HANDLE_ERROR(cudaMalloc((void**)&stage, sz_native));
    stage_owner.add(stage);

    bool apply_gain = (gain_ref != nullptr);
    if (!ensureDeviceGain(gain_ref, sz_real)) return false;

    // The accumulator starts at +0.0f exactly as `float sum = 0.0f` does. Seeding
    // frame 0 with a plain store instead would differ for a -0.0f product, which
    // a zero sample against a negative gain entry can produce.
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_real));

    const int block = 256;
    const int grid = (int)((num_pixels + block - 1) / block);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        // Per-frame upload keeps the same failure granularity as the float path:
        // a fault names a frame index and leaves the rest untransferred.
        HANDLE_ERROR(cudaMemcpy(stage, raw_frames[iframe]().data, sz_native,
                                cudaMemcpyHostToDevice));
        convertGainAndAccumulateNativeKernel<T><<<grid, block>>>(
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

bool CudaMovieSession::applyGainDefectsAndSumU16(
    const std::vector<Image<unsigned short> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    return applyGainDefectsAndSumNative<unsigned short>(raw_frames, gain_ref,
                                                        unaligned_sum, download_sum);
}

bool CudaMovieSession::applyGainDefectsAndSumU8(
    const std::vector<Image<unsigned char> > &raw_frames,
    const MultidimArray<float> *gain_ref,
    MultidimArray<float> &unaligned_sum,
    bool download_sum
) {
    return applyGainDefectsAndSumNative<unsigned char>(raw_frames, gain_ref,
                                                       unaligned_sum, download_sum);
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
    if (d_gain && !d_gain_borrowed) {
        float *owned_gain = d_gain;
        d_gain = nullptr;
        free_error = releaseBuffer(owned_gain);
    } else {
        // Pooled: drop the alias, keep the buffer for the next movie.
        d_gain = nullptr;
    }
    d_gain_borrowed = false;
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
    if (ingest_copy_stream) {
        // Uploads from the pinned pool may still be in flight on an early return.
        recordFailure(cudaStreamSynchronize(ingest_copy_stream), "ingest copy stream sync", __LINE__);
        recordFailure(cudaStreamDestroy(ingest_copy_stream), "ingest copy stream", __LINE__);
        ingest_copy_stream = 0;
    }
    if (ingest_stream) {
        // Nothing may still be reading or writing the arena when the FFT phase takes
        // d_Fframes back. There is no host work worth overlapping at this boundary,
        // so this synchronises rather than handing an event to a later stream.
        recordFailure(cudaStreamSynchronize(ingest_stream), "ingest scratch sync", __LINE__);
        recordFailure(cudaStreamDestroy(ingest_stream), "ingest scratch stream", __LINE__);
        ingest_stream = 0;
    }
    // Only after both streams have drained: nothing can still record or wait.
    for (int e = 0; e < kIngestEvents; e++) {
        if (ingest_events[e]) {
            recordFailure(cudaEventDestroy(ingest_events[e]), "ingest event", __LINE__);
            ingest_events[e] = 0;
        }
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

// pread until n bytes have arrived. A short file, an error or EOF is a refusal,
// as a short TIFFReadRawStrip was. pread leaves the descriptor's offset alone,
// so it does not disturb the LibTIFF handle that owns fd.
bool preadFully(int fd, uint8_t *dst, size_t n, uint64_t offset) {
    if (fd < 0) return false;
    while (n > 0) {
        const ssize_t got = pread(fd, dst, n, (off_t)offset);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) return false;
        dst += got;
        n -= (size_t)got;
        offset += (uint64_t)got;
    }
    return true;
}
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
    std::vector<std::vector<uint64_t> > raw_offsets(num_req_frames);
    // A frame whose strips sit back to back in file order, first to last, is
    // read with one pread of its whole span instead of one LibTIFF call per
    // strip; anything else keeps the per-strip TIFFReadRawStrip reader.
    std::vector<char> frame_contiguous(num_req_frames, 0);
    {
        StageScope tag_scope("ingest tag scan");
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
            raw_offsets[f].resize(ny);
            bool contiguous = true;
            for (int s = 0; s < ny; s++) {
                const tmsize_t rs = TIFFRawStripSize(tif, s);
                if (rs < 7 || (uint64_t)rs > 0xFFFFFFFFull) { ok = false; break; }
                raw_sizes[f][s] = (uint32_t)rs;
                // Same offset and byte count TIFFReadRawStrip uses for this strip.
                int err = 0;
                raw_offsets[f][s] = TIFFGetStrileOffsetWithErr(tif, (uint32_t)s, &err);
                if (err || raw_offsets[f][s] == 0) contiguous = false;
                if (s > 0 && raw_offsets[f][s] != raw_offsets[f][s - 1] + raw_sizes[f][s - 1])
                    contiguous = false;
            }
            if (!ok || (int)raw_sizes[f].size() != ny) { ok = false; break; }
            frame_contiguous[f] = contiguous ? 1 : 0;
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
    SubStageSequence phase;
    phase.next("ingest setup");
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

    // ------------------------------------------------------------------
    // Pipelined chunks (docs/nvcomp_ingest_pipeline.md).
    //
    // The movie is split into chunks of chunk_frames frames. With more than one
    // chunk, two slots alternate: while the GPU copies and decodes chunk k from
    // slot k%2, the CPU reads chunk k+1 into the other slot. Two streams let the
    // copy of chunk k+1 overlap the decode of chunk k:
    //
    //   copy stream     wait comp_free[j] -> H2D payload + strip tables -> h2d_done[j]
    //   compute stream  wait h2d_done[j]  -> decode -> comp_free[j] -> Adler-32
    //                   -> D2H status/length/Adler-32 into pinned -> status_ready[j]
    //
    // Chunk k is verified on the host (status and length for every strip of the
    // chunk first, then Adler-32) after status_ready, and only then is its gain,
    // flip and sum kernel launched. A chunk that fails returns false before any of
    // its decoded bytes reach d_Iframes/d_Isum; earlier chunks' contributions are
    // discarded by the caller's fallback, which overwrites both in full, exactly
    // as a failed later batch was before.
    //
    // Slot reuse rules:
    //  - host payload/tables of slot j are rewritten only after h2d_done[j] of the
    //    chunk that last used it (cudaEventSynchronize);
    //  - device payload/tables of slot j are overwritten only after comp_free[j]
    //    (stream wait on the copy stream);
    //  - device decode output of slot j is overwritten by the decode of chunk k+2,
    //    which the compute stream orders after chunk k's gain kernel;
    //  - pinned readback of slot j is rewritten by chunk k+2's D2H, which is
    //    enqueued after chunk k was verified.
    // ------------------------------------------------------------------
    int chunk_req = mc_tiff_deflate::defaultChunkFrames(n_frames);
    if (const char *env = getenv("MOTIONCORR_NVCOMP_CHUNK_FRAMES")) {
        int parsed = 0;
        if (mc_tiff_deflate::parsePositiveInt(env, parsed)) {
            chunk_req = parsed;
        } else {
            logfile << "WARNING: MOTIONCORR_NVCOMP_CHUNK_FRAMES is not a positive whole"
                    << " number; using " << chunk_req << " frames per chunk." << std::endl;
        }
    }
    chunk_req = std::min(chunk_req, n_frames);

    // Views into the arena. None of these owns memory; none may be freed.
    struct SlotViews {
        uint8_t *comp; uint16_t *u16;
        void **cptr; size_t *csize; void **dptr; size_t *dsize; size_t *asize;
        nvcompStatus_t *status; uint32_t *adler;
    };
    SlotViews dv[2];
    std::memset(dv, 0, sizeof(dv));
    void *d_temp = nullptr;
    size_t temp_bytes = 0;
    size_t slot_capacity = 0;
    int chunk_frames = 0;
    mc_tiff_deflate::PinnedChunkLayout layout;

    for (int candidate = chunk_req; candidate >= 1; candidate = (candidate > 1 ? candidate / 2 : 0)) {
        const int slots = mc_tiff_deflate::pipelineSlots(n_frames, candidate);
        const size_t chunks = (size_t)candidate * (size_t)ny;
        size_t cand_temp = 0;
        if (nvcompBatchedDeflateDecompressGetTempSizeAsync(
                chunks, row_bytes, nvcompBatchedDeflateDecompressDefaultOpts,
                &cand_temp, chunks * row_bytes) != nvcompSuccess) {
            break;
        }
        const size_t cap = (size_t)candidate * alignUp(max_frame_stage, in_align);
        const mc_tiff_deflate::PinnedChunkLayout cand_layout =
            mc_tiff_deflate::pinnedChunkLayout(slots, cap, chunks, sizeof(nvcompStatus_t));
        // Against the bytes that will actually be pinned, not the payload: the
        // pool adds 12.5% headroom and rounds up to a 32 MiB granule, so a cap
        // enforced on the payload is overshot by construction. Every pinned byte
        // of the pipeline (both payload slots, tables, readback) is in total.
        if (cand_layout.total == 0 ||
            mc_tiff_deflate::pinnedReserveBytes(cand_layout.total) > pinned_cap) {
            if (candidate == 1) break;
            continue;
        }
        arena.reset();
        SlotViews c[2];
        std::memset(c, 0, sizeof(c));
        bool fits = true;
        for (int j = 0; j < slots && fits; j++) {
            c[j].comp   = (uint8_t *)arena.alloc(cap, in_align);
            c[j].u16    = (uint16_t *)arena.alloc(chunks * row_pitch_bytes, out_align);
            c[j].cptr   = (void **)arena.alloc(chunks * sizeof(void *), sizeof(void *));
            c[j].csize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
            c[j].dptr   = (void **)arena.alloc(chunks * sizeof(void *), sizeof(void *));
            c[j].dsize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
            c[j].asize  = (size_t *)arena.alloc(chunks * sizeof(size_t), sizeof(size_t));
            c[j].status = (nvcompStatus_t *)arena.alloc(chunks * sizeof(nvcompStatus_t), sizeof(nvcompStatus_t));
            c[j].adler  = (uint32_t *)arena.alloc(chunks * sizeof(uint32_t), sizeof(uint32_t));
            fits = c[j].comp && c[j].u16 && c[j].cptr && c[j].csize && c[j].dptr &&
                   c[j].dsize && c[j].asize && c[j].status && c[j].adler;
        }
        // One nvCOMP temp area: every decode runs on the compute stream, in order.
        void *cand_temp_ptr = nullptr;
        if (fits && cand_temp) {
            cand_temp_ptr = arena.alloc(cand_temp, tmp_align);
            fits = (cand_temp_ptr != 0);
        }
        if (fits) {
            dv[0] = c[0]; dv[1] = c[1];
            d_temp = cand_temp_ptr;
            temp_bytes = cand_temp;
            slot_capacity = cap;
            chunk_frames = candidate;
            layout = cand_layout;
            break;
        }
        if (candidate == 1) break;
    }
    if (chunk_frames <= 0) {
        logfile << "nvCOMP ingestion declined: a one-frame chunk fits neither the "
                << arena.capacity() << "-byte pre-FFT scratch arena nor the "
                << pinned_cap << "-byte pinned staging cap"
                << " (MOTIONCORR_NVCOMP_PINNED_MAX_MB); using the host reader." << std::endl;
        return false;
    }
    const int n_slots = layout.slots;
    const int n_chunks = (n_frames + chunk_frames - 1) / chunk_frames;

    // The arena can only honour this because its base came from cudaMalloc. Checked
    // rather than assumed: a misaligned input is undefined behaviour in nvCOMP that
    // decodes correctly often enough to pass a pixel comparison.
    for (int j = 0; j < n_slots; j++)
        if (((uintptr_t)dv[j].comp % in_align) != 0) return false;

    int contiguous_frames = 0;
    for (int f = 0; f < n_frames; f++) contiguous_frames += frame_contiguous[f] ? 1 : 0;
    logfile << "nvCOMP ingestion: chunk=" << chunk_frames << "/" << n_frames
            << " frames x " << n_chunks << " chunks, slots=" << n_slots
            << ", scratch=" << arena.used() << "/" << arena.capacity()
            << " bytes borrowed from the pre-FFT Fourier buffer (additional VRAM: 0)"
            << ", pinned staging=" << mc_tiff_deflate::pinnedReserveBytes(layout.total)
            << "/" << pinned_cap << " reserved, " << layout.total << " used ("
            << n_slots << " x " << slot_capacity << " payload)"
            << ", nvCOMP temp=" << temp_bytes
            << ", input alignment=" << in_align
            << ", span-read frames=" << contiguous_frames << "/" << n_frames << std::endl;

    // ------------------------------------------------------------------
    // Host side: the worker-lifetime pinned pool, laid out as two slots.
    // ------------------------------------------------------------------
    if (!ensurePinnedStage(layout.total)) return false;
    uint8_t *const h_base = (uint8_t *)t_pinned_stage.ptr;
    struct HostSlot {
        uint8_t *payload; void **cptr; size_t *csize; void **dptr; size_t *dsize;
        nvcompStatus_t *status; size_t *asize; uint32_t *adler;
    };
    HostSlot hs[2];
    std::memset(hs, 0, sizeof(hs));
    for (int j = 0; j < n_slots; j++) {
        hs[j].payload = h_base + layout.payload[j];
        hs[j].cptr    = (void **)(h_base + layout.cptr[j]);
        hs[j].csize   = (size_t *)(h_base + layout.csize[j]);
        hs[j].dptr    = (void **)(h_base + layout.dptr[j]);
        hs[j].dsize   = (size_t *)(h_base + layout.dsize[j]);
        hs[j].status  = (nvcompStatus_t *)(h_base + layout.status[j]);
        hs[j].asize   = (size_t *)(h_base + layout.asize[j]);
        hs[j].adler   = (uint32_t *)(h_base + layout.adler[j]);
        // Output descriptors are the same for every chunk that uses this slot.
        for (size_t c = 0; c < layout.chunk_strips; c++) {
            hs[j].dptr[c]  = (uint8_t *)dv[j].u16 + c * row_pitch_bytes;
            hs[j].dsize[c] = row_bytes;
        }
    }
    std::vector<uint32_t> adler_expected[2];
    for (int j = 0; j < n_slots; j++) adler_expected[j].resize(layout.chunk_strips);

    const bool apply_gain = (gain_ref != nullptr);
    if (apply_gain) {
        const size_t sz_real = (size_t)ny * (size_t)nx * sizeof(float);
        if (!ensureDeviceGain(gain_ref, sz_real)) return false;
    }

    // One LibTIFF handle per reader thread, opened once for the movie rather than
    // once per chunk, and a reader team that sleeps between chunks. The team was an
    // OpenMP parallel region per chunk: libgomp's idle threads spin after each
    // region and competed with the thread submitting GPU work
    // (docs/nvcomp_ingest_pipeline.md). Handles are opened here, on the calling
    // thread, so a refused open declines the whole ingest before any chunk is staged.
    const int io_threads = n_threads > 0 ? n_threads : 4;
    struct TiffHandles {
        std::vector<TIFF *> h;
        ~TiffHandles() { for (TIFF *t : h) if (t) TIFFClose(t); }
    } tiffs;
    tiffs.h.assign((size_t)io_threads, nullptr);
    bool all_open = true;
    for (int t = 0; t < io_threads; t++) {
        tiffs.h[t] = TIFFOpen(fn_mic.c_str(), "r");
        if (!tiffs.h[t]) all_open = false;
    }
    if (!all_open) {
        logfile << "WARNING: nvCOMP ingestion could not open a TIFF handle for every reader"
                   " thread; using the host reader." << std::endl;
        return false;
    }
    mc_cuda::ChunkReaderPool readers(io_threads);

    HANDLE_ERROR(cudaStreamCreate(&ingest_stream));
    HANDLE_ERROR(cudaStreamCreate(&ingest_copy_stream));
    for (int e = 0; e < kIngestEvents; e++)
        HANDLE_ERROR(cudaEventCreateWithFlags(&ingest_events[e], cudaEventDisableTiming));
    cudaStream_t stream = ingest_stream;
    cudaStream_t copy_stream = ingest_copy_stream;
    cudaEvent_t *const ev_h2d_done     = ingest_events;       // [2]
    cudaEvent_t *const ev_comp_free    = ingest_events + 2;   // [2]
    cudaEvent_t *const ev_status_ready = ingest_events + 4;   // [2]

    std::vector<size_t> chunk_stage_used(n_chunks, 0);
    bool slot_tables_uploaded[2] = {false, false};

    // Reads chunk k into host slot j and fills its input tables. False refuses.
    auto read_chunk = [&](int k, int j) -> bool {
        const int f0 = k * chunk_frames;
        const int bf = std::min(chunk_frames, n_frames - f0);
        std::vector<size_t> frame_base(bf);
        size_t stage_used = 0;
        for (int i = 0; i < bf; i++) {
            frame_base[i] = alignUp(stage_used, in_align);
            stage_used = frame_base[i] + frame_stage_bytes[f0 + i];
        }
        if (stage_used > slot_capacity) return false;
        chunk_stage_used[k] = stage_used;
        uint8_t *const h_stage = hs[j].payload;
        void **const h_cptr = hs[j].cptr;
        size_t *const h_csize = hs[j].csize;
        uint32_t *const h_adler_expected = adler_expected[j].data();
        uint8_t *const d_comp = dv[j].comp;

        std::vector<char> frame_ok(bf, 1);   // not vector<bool>: concurrent bit writes race
        std::atomic<int> next_frame(0);
        std::mutex log_mutex;
        // Every thread of the team runs this once per chunk and takes frames from a
        // shared counter (the dynamic,1 schedule of the OpenMP loop it replaces). A
        // thread with no usable handle takes nothing; all handles were checked when
        // they were opened, so that cannot happen here.
        auto read_frames = [&](int tid) {
            TIFF *const t = tiffs.h[(size_t)tid];
            for (int i = next_frame.fetch_add(1); i < bf; i = next_frame.fetch_add(1)) {
                    if (!t) { frame_ok[i] = 0; continue; }
                    const int f = f0 + i;
                    uint8_t *fb = h_stage + frame_base[i];
                    const uint32_t *sizes = raw_sizes[f].data();
                    bool ok = true;
                    if (frame_contiguous[f]) {
                        // One read of the frame's whole span, placed so that it ends
                        // where the slotted layout ends, then spread into the
                        // aligned slots in place. Same bytes as one
                        // TIFFReadRawStrip per strip, without ny library calls.
                        const size_t packed = mc_tiff_deflate::framePackedBytes(sizes, ny);
                        const size_t lead = frame_stage_bytes[f] - packed;
                        ok = preadFully(TIFFFileno(t), fb + lead, packed, raw_offsets[f][0]);
                        if (ok) mc_tiff_deflate::spreadPackedStrips(fb, sizes, ny, in_align);
                    } else {
                        if (!TIFFSetDirectory(t, frames[f])) { frame_ok[i] = 0; continue; }
                        size_t cursor = 0;
                        for (int s = 0; s < ny && ok; s++) {
                            const size_t slot = stripSlotOffset(cursor, in_align);
                            if (TIFFReadRawStrip(t, s, fb + slot, (tmsize_t)sizes[s]) != (tmsize_t)sizes[s])
                                ok = false;
                            cursor = slot + sizes[s];
                        }
                    }
                    size_t cursor = 0;
                    for (int s = 0; s < ny && ok; s++) {
                        const size_t raw_sz = sizes[s];
                        const size_t slot = stripSlotOffset(cursor, in_align);
                        if (!zlibWrapperIsUsable(fb + slot, raw_sz)) {
                            // Named, because otherwise the only externally visible
                            // difference between this refusal and a read failure is
                            // that the movie fails -- which makes the guard
                            // impossible to tell apart from the one after it.
                            {
                                std::lock_guard<std::mutex> lock(log_mutex);
                                logfile << "WARNING: strip " << s << " of frame " << f
                                        << " has an unusable zlib wrapper; falling back to"
                                           " the host reader." << std::endl;
                            }
                            ok = false;
                            break;
                        }
                        const size_t chunk = (size_t)i * (size_t)ny + (size_t)s;
                        // Payload only: the 2-byte zlib header and the 4-byte Adler32
                        // trailer are not part of the RFC 1951 stream nvCOMP consumes.
                        h_cptr[chunk]  = d_comp + frame_base[i] + slot + 2;
                        h_csize[chunk] = raw_sz - 6;
                        // Stored Adler-32: the last four bytes of the strip, big-endian.
                        const uint8_t *tr = fb + slot + raw_sz - 4;
                        h_adler_expected[chunk] = ((uint32_t)tr[0] << 24) | ((uint32_t)tr[1] << 16) |
                                                  ((uint32_t)tr[2] << 8)  |  (uint32_t)tr[3];
                        cursor = slot + raw_sz;
                    }
                    if (!ok) frame_ok[i] = 0;
            }
        };
        if (!readers.runTeam(read_frames)) return false;
        for (int i = 0; i < bf; i++) if (!frame_ok[i]) return false;
        return true;
    };

    // Checks chunk k's readback in slot j. Rejects the whole chunk on status or
    // length before consulting any checksum: an earlier checksum mismatch must
    // not mask a later decoder failure.
    auto verify_chunk = [&](int k, int j) -> bool {
        const int f0 = k * chunk_frames;
        const int bf = std::min(chunk_frames, n_frames - f0);
        const size_t chunks = (size_t)bf * (size_t)ny;
        for (size_t c = 0; c < chunks; c++) {
            if (hs[j].status[c] != nvcompSuccess || hs[j].asize[c] != row_bytes) {
                logfile << "WARNING: nvCOMP rejected strip " << c << " of frames ["
                        << f0 << "," << (f0 + bf) << "): status=" << (int)hs[j].status[c]
                        << " bytes=" << hs[j].asize[c] << " expected=" << row_bytes
                        << "; falling back to the host reader." << std::endl;
                return false;
            }
        }
        for (size_t c = 0; c < chunks; c++) {
            if (hs[j].adler[c] != adler_expected[j][c]) {
                logfile << "WARNING: strip " << c << " of frames [" << f0 << ","
                        << (f0 + bf) << ") failed its zlib Adler-32 check: computed 0x"
                        << std::hex << hs[j].adler[c] << " stored 0x"
                        << adler_expected[j][c] << std::dec
                        << "; falling back to the host reader." << std::endl;
                return false;
            }
        }
        return true;
    };

    dim3 gs_block(16, 16);
    dim3 gs_grid((nx + gs_block.x - 1) / gs_block.x, (ny + gs_block.y - 1) / gs_block.y);

    // ------------------------------------------------------------------
    // Pass B: read chunk k while chunk k-1 is on the device; verify chunk k-1
    // and only then convert it.
    // ------------------------------------------------------------------
    for (int k = 0; k <= n_chunks; k++) {
        if (k < n_chunks) {
            const int j = k % n_slots;
            const int f0 = k * chunk_frames;
            const int bf = std::min(chunk_frames, n_frames - f0);
            const size_t chunks = (size_t)bf * (size_t)ny;

            if (k >= n_slots) {
                // The host slot is still the source of chunk k-2's upload.
                phase.next("ingest slot wait");
                HANDLE_ERROR(cudaEventSynchronize(ev_h2d_done[j]));
            }
            phase.next("ingest strip read");
            if (!read_chunk(k, j)) return false;

            phase.next("ingest h2d submit");
            // Device payload/tables of slot j may still be read by chunk k-2's decode.
            if (k >= n_slots) HANDLE_ERROR(cudaStreamWaitEvent(copy_stream, ev_comp_free[j], 0));
            HANDLE_ERROR(cudaMemcpyAsync(dv[j].comp, hs[j].payload, chunk_stage_used[k], cudaMemcpyHostToDevice, copy_stream));
            HANDLE_ERROR(cudaMemcpyAsync(dv[j].cptr, hs[j].cptr, chunks * sizeof(void *), cudaMemcpyHostToDevice, copy_stream));
            HANDLE_ERROR(cudaMemcpyAsync(dv[j].csize, hs[j].csize, chunks * sizeof(size_t), cudaMemcpyHostToDevice, copy_stream));
            if (!slot_tables_uploaded[j]) {
                HANDLE_ERROR(cudaMemcpyAsync(dv[j].dptr, hs[j].dptr, layout.chunk_strips * sizeof(void *), cudaMemcpyHostToDevice, copy_stream));
                HANDLE_ERROR(cudaMemcpyAsync(dv[j].dsize, hs[j].dsize, layout.chunk_strips * sizeof(size_t), cudaMemcpyHostToDevice, copy_stream));
                slot_tables_uploaded[j] = true;
            }
            HANDLE_ERROR(cudaEventRecord(ev_h2d_done[j], copy_stream));

            phase.next("ingest decompress submit");
            HANDLE_ERROR(cudaStreamWaitEvent(stream, ev_h2d_done[j], 0));
            if (nvcompBatchedDeflateDecompressAsync(
                    (const void *const *)dv[j].cptr, dv[j].csize, dv[j].dsize, dv[j].asize,
                    chunks, d_temp, temp_bytes, dv[j].dptr,
                    nvcompBatchedDeflateDecompressDefaultOpts, dv[j].status, stream) != nvcompSuccess) {
                return false;
            }
            HANDLE_ERROR(cudaEventRecord(ev_comp_free[j], stream));
            // Fail closed. Without this the slot's previous contents, or raw
            // cudaMalloc garbage on its first use, would be cast to float,
            // gain-applied and aligned as if it were image data.
            adler32StripsKernel<<<(unsigned)chunks, 256, 0, stream>>>(
                (const unsigned char *)dv[j].u16, row_pitch_bytes, row_bytes, row_bytes, 1,
                dv[j].status, dv[j].asize, dv[j].adler, chunks);
            HANDLE_ERROR(cudaGetLastError());
            HANDLE_ERROR(cudaMemcpyAsync(hs[j].status, dv[j].status, chunks * sizeof(nvcompStatus_t), cudaMemcpyDeviceToHost, stream));
            HANDLE_ERROR(cudaMemcpyAsync(hs[j].asize, dv[j].asize, chunks * sizeof(size_t), cudaMemcpyDeviceToHost, stream));
            HANDLE_ERROR(cudaMemcpyAsync(hs[j].adler, dv[j].adler, chunks * sizeof(uint32_t), cudaMemcpyDeviceToHost, stream));
            HANDLE_ERROR(cudaEventRecord(ev_status_ready[j], stream));
        }
        if (k >= 1) {
            const int kp = k - 1;
            const int jp = kp % n_slots;
            const int f0 = kp * chunk_frames;
            const int bf = std::min(chunk_frames, n_frames - f0);
            phase.next("ingest status d2h and sync");
            HANDLE_ERROR(cudaEventSynchronize(ev_status_ready[jp]));
            phase.next("ingest verify");
            if (!verify_chunk(kp, jp)) return false;
            phase.next("ingest gain sum cast");
            fusedU16FlipGainAndSumKernel<<<gs_grid, gs_block, 0, stream>>>(
                dv[jp].u16, d_Iframes, d_Isum, d_gain, nx, ny, row_pitch_u16,
                f0, bf, f0 == 0, apply_gain);
            HANDLE_ERROR(cudaGetLastError());
        }
    }
    phase.next("ingest drain");
    HANDLE_ERROR(cudaStreamSynchronize(stream));
    phase.end();

    return true;
}
#endif

bool CudaMovieSession::computeGlobalForwardFFT() {
    if (failure_state.isPoisoned() || !is_initialized || !has_plan_r2c) return false;
    if (refuseInvalidRealFrames("the forward FFT")) return false;
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
    // One shared cuFFT work area serves every execution below. All of them run
    // on the default stream, so successive executions (and the scaling kernel)
    // are already ordered; the old per-frame cudaDeviceSynchronize only moved
    // the host's wait, not the GPU's order. Execution errors surface at the one
    // checked drain after the last launch. A failed launch drains first, so
    // work already queued finishes and any asynchronous error is attributed
    // here rather than to a later, unrelated call.
    auto drain_after_failure = [&]() { recordFailure(cudaDeviceSynchronize(), "forward FFT drain", __LINE__); };
    for (int iframe = 0; iframe < n_frames; iframe++) {
        const cufftResult res = cufftExecR2C(plan_r2c, (cufftReal*)(d_Iframes + (size_t)iframe * real_stride),
                                             d_Fframes + (size_t)iframe * complex_stride);
        if (res != CUFFT_SUCCESS) {
            logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ << " : " << res << std::endl;
            recordCufftFailure(res, __func__, __LINE__);
            drain_after_failure();
            return false;
        }
    }

    const float inv_size = 1.0f / ((float)nx * ny);
    const size_t total_comp_elems = (size_t)n_frames * ny * nfx;
    const int block = 256;
    const int grid = (int)((total_comp_elems + block - 1) / block);
    scaleComplexKernel<<<grid, block>>>(d_Fframes, total_comp_elems, inv_size);
    {
        const cudaError_t launch = cudaGetLastError();
        if (launch != cudaSuccess) {
            logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " << cudaGetErrorString(launch) << std::endl;
            recordFailure(launch, __func__, __LINE__);
            drain_after_failure();
            return false;
        }
    }
    HANDLE_ERROR(cudaDeviceSynchronize());

    return true;
}

bool CudaMovieSession::computeGlobalInverseFFT() {
    if (failure_state.isPoisoned() || !is_initialized || !has_plan_c2r || !d_inverse_tile) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    // C2R overwrites its input (measured on this cuFFT for every geometry
    // tried, docs/fft_dw_device_overheads.md), so each Fourier tile is copied
    // to the scratch tile first and the originals stay intact for dose
    // weighting. Copy, transform and the next frame's copy are ordered on the
    // default stream, so the scratch tile is not reused before its transform
    // has read it; there is no per-frame host wait. Errors surface at the one
    // checked drain below.
    const size_t real_stride = (size_t)nx * ny;
    const size_t complex_stride = (size_t)ny * nfx;
    auto drain_after_failure = [&]() { recordFailure(cudaDeviceSynchronize(), "inverse FFT drain", __LINE__); };
    for (int iframe = 0; iframe < n_frames; iframe++) {
        const cudaError_t copy = cudaMemcpy(d_inverse_tile, d_Fframes + (size_t)iframe * complex_stride,
                                            complex_stride * sizeof(cufftComplex),
                                            cudaMemcpyDeviceToDevice);
        if (copy != cudaSuccess) {
            logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " << cudaGetErrorString(copy) << std::endl;
            recordFailure(copy, __func__, __LINE__);
            drain_after_failure();
            return false;
        }
        const cufftResult res = cufftExecC2R(plan_c2r, d_inverse_tile,
                                             (cufftReal*)(d_Iframes + (size_t)iframe * real_stride));
        if (res != CUFFT_SUCCESS) {
            logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ << " : " << res << std::endl;
            recordCufftFailure(res, __func__, __LINE__);
            drain_after_failure();
            return false;
        }
    }
    HANDLE_ERROR(cudaDeviceSynchronize());
    // Every frame of d_Iframes was just rewritten, whatever borrowed it before.
    real_frames_invalid_reason = nullptr;
    return true;
}

bool CudaMovieSession::refuseInvalidRealFrames(const char *operation) {
    if (!real_frames_invalid_reason) return false;
    logfile << "ERROR: refusing " << operation << ": the device real-space movie is no longer valid ("
            << real_frames_invalid_reason << ")." << std::endl;
    return true;
}

void *CudaMovieSession::borrowRealFramesForGlobalAlignment(size_t &bytes) {
    bytes = 0;
    if (failure_state.isPoisoned() || !is_initialized || !d_Iframes) return nullptr;
    bytes = (size_t)n_frames * nx * ny * sizeof(float);
    real_frames_invalid_reason = "global alignment used it as scratch; the inverse FFT has not rewritten it";
    return d_Iframes;
}

bool CudaMovieSession::releasePatchAlignmentWorkspace() {
    const bool single = patch_alignment_workspace.release();
    const bool batched = batched_patch_alignment_workspace.release();
    // Patch preparation is over once alignment is released; its cached buffers
    // and plan would otherwise stay resident through reconstruction. The claims
    // are dropped before freeing (Issue #69) and every release is attempted.
    float *patches = d_Ipatches;
    cufftComplex *spectrum = d_patch_spectrum;
    int *start = d_group_start, *size = d_group_size;
    d_Ipatches = nullptr;
    d_patch_spectrum = nullptr;
    d_group_start = d_group_size = nullptr;
    sz_cached_Ipatches = sz_cached_patch_spectrum = 0;
    cached_ngroups_alloc = 0;
    cached_patch_w = cached_patch_h = cached_patch_ngroups = 0;
    uploaded_group_start.clear();
    uploaded_group_size.clear();
    bool ok = single && batched;
    if (patches || spectrum || start || size || has_plan_patch_r2c) {
        // Patch kernels and transforms may still be queued after a throw.
        const cudaError_t device = cudaSetDevice(device_id);
        const cudaError_t sync = device != cudaSuccess ? device : cudaDeviceSynchronize();
        recordFailure(sync, "patch preparation release synchronize", __LINE__);
        if (sync != cudaSuccess) ok = false;
    }
    if (releasePlan(plan_patch_r2c, has_plan_patch_r2c) != CUFFT_SUCCESS) ok = false;
    if (releaseBuffer(patches) != cudaSuccess) ok = false;
    if (releaseBuffer(spectrum) != cudaSuccess) ok = false;
    if (releaseBuffer(start) != cudaSuccess) ok = false;
    if (releaseBuffer(size) != cudaSuccess) ok = false;
    return ok;
}

bool CudaMovieSession::preparePatchInVram(
    int x_start, int y_start,
    int patch_w, int patch_h,
    int n_groups, const int *group_start, const int *group_size,
    cufftComplex *d_out_fpatches,
    int window_nx, int window_ny
) {
    if (failure_state.isPoisoned() || !is_initialized || n_groups == 0 || !d_out_fpatches) return false;
    if (refuseInvalidRealFrames("patch preparation")) return false;
    HANDLE_ERROR(cudaSetDevice(device_id));

    const int patch_nfx = patch_w / 2 + 1;
    const size_t sz_all_patch_real = (size_t)n_groups * patch_h * patch_w * sizeof(float);
    const bool windowed = window_nx > 0 && window_ny > 0;

    // Reuse or allocate cached scratch buffers.
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
    if (!d_group_start || !d_group_size || cached_ngroups_alloc < n_groups) {
        int *stale_start = d_group_start;
        int *stale_size = d_group_size;
        d_group_start = nullptr;
        d_group_size = nullptr;
        cached_ngroups_alloc = 0;
        uploaded_group_start.clear();
        uploaded_group_size.clear();
        const cudaError_t start_err = releaseBuffer(stale_start);
        const cudaError_t size_err = releaseBuffer(stale_size);
        HANDLE_ERROR(start_err);
        HANDLE_ERROR(size_err);
        int *fresh_start = nullptr;
        int *fresh_size = nullptr;
        HANDLE_ERROR(cudaMalloc((void**)&fresh_start, n_groups * sizeof(int)));
        d_group_start = fresh_start;
        HANDLE_ERROR(cudaMalloc((void**)&fresh_size, n_groups * sizeof(int)));
        d_group_size = fresh_size;
        cached_ngroups_alloc = n_groups;
    }

    // Identical for every patch of a movie; upload only when the content changes.
    // The cache is dropped before a failed upload can leave it describing bytes
    // that are not on the device.
    const bool groups_current =
        (int)uploaded_group_start.size() == n_groups &&
        std::equal(group_start, group_start + n_groups, uploaded_group_start.begin()) &&
        std::equal(group_size, group_size + n_groups, uploaded_group_size.begin());
    if (!groups_current) {
        uploaded_group_start.clear();
        uploaded_group_size.clear();
        HANDLE_ERROR(cudaMemcpy(d_group_start, group_start, n_groups * sizeof(int), cudaMemcpyHostToDevice));
        HANDLE_ERROR(cudaMemcpy(d_group_size, group_size, n_groups * sizeof(int), cudaMemcpyHostToDevice));
        uploaded_group_start.assign(group_start, group_start + n_groups);
        uploaded_group_size.assign(group_size, group_size + n_groups);
    }

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

    const float inv_patch_size = 1.0f / ((float)patch_w * patch_h);
    const size_t total_comp_elems = (size_t)n_groups * patch_h * patch_nfx;
    if (windowed) {
        // The full spectra are only an intermediate. d_inverse_tile is dead
        // between the global inverse FFT and dose weighting
        // (docs/vram_live_ranges.md), so it holds them when large enough.
        cufftComplex *spectrum = d_inverse_tile;
        if (!spectrum || total_comp_elems > (size_t)ny * nfx) {
            const size_t sz_spectrum = total_comp_elems * sizeof(cufftComplex);
            if (!d_patch_spectrum || sz_cached_patch_spectrum < sz_spectrum) {
                cufftComplex *stale = d_patch_spectrum;
                d_patch_spectrum = nullptr;
                sz_cached_patch_spectrum = 0;
                HANDLE_ERROR(releaseBuffer(stale));
                cufftComplex *fresh = nullptr;
                HANDLE_ERROR(cudaMalloc((void**)&fresh, sz_spectrum));
                d_patch_spectrum = fresh;
                sz_cached_patch_spectrum = sz_spectrum;
            }
            spectrum = d_patch_spectrum;
        }
        CUFFT_CHECK(cufftExecR2C(plan_patch_r2c, (cufftReal*)d_Ipatches, spectrum));
        HANDLE_ERROR(cudaExtractPatchWindow(spectrum, d_out_fpatches, n_groups, patch_w, patch_h,
                                            window_nx, window_ny, inv_patch_size));
        return true;
    }

    CUFFT_CHECK(cufftExecR2C(plan_patch_r2c, (cufftReal*)d_Ipatches, d_out_fpatches));
    const int block_scale = 256;
    const int grid_scale = (int)((total_comp_elems + block_scale - 1) / block_scale);
    scaleComplexKernel<<<grid_scale, block_scale>>>(d_out_fpatches, total_comp_elems, inv_patch_size);
    HANDLE_ERROR(cudaGetLastError());

    return true;
}

void CudaMovieSession::alignPatchesBatched(
    const std::vector<PatchBox> &boxes,
    int n_groups, const int *group_start, const int *group_size,
    RFLOAT scaled_B, int max_iter, RFLOAT ccf_downsample, int cap,
    std::vector<PatchBatchOutcome> &outcomes)
{
    const int n_patches = (int)boxes.size();
    outcomes.assign(n_patches, PatchBatchOutcome());
    if (cap <= 0 || n_patches == 0 || n_groups <= 0 || !is_initialized ||
        failure_state.isPoisoned())
        return;
    const int patch_w = boxes[0].width, patch_h = boxes[0].height;
    for (const PatchBox &box : boxes) {
        if (box.width != patch_w || box.height != patch_h) {
            logfile << "Batched patch alignment: patch sizes differ; using per-patch alignment." << std::endl;
            return;
        }
    }
    const cudaError_t device_error = cudaSetDevice(device_id);
    size_t free_bytes = 0, total_bytes = 0;
    const cudaError_t info_error = device_error != cudaSuccess ? device_error
                                                               : cudaMemGetInfo(&free_bytes, &total_bytes);
    if (info_error != cudaSuccess) {
        if (cudaErrorPoisonsContext(info_error)) {
            recordFailure(info_error, "batched patch memory query", __LINE__);
            REPORT_ERROR("Fatal CUDA error before batched patch alignment");
        }
        (void)cudaGetLastError();
        logfile << "Batched patch alignment: device memory query failed ("
                << cudaGetErrorString(info_error) << "); using per-patch alignment." << std::endl;
        return;
    }
    BatchedPatchAlignmentWorkspace &workspace = batched_patch_alignment_workspace;
    const size_t per_patch = BatchedPatchAlignmentWorkspace::bytesPerPatch(
        n_groups, patch_w, patch_h, scaled_B, ccf_downsample);
    int chunk = choosePatchBatchChunk(n_patches, per_patch, free_bytes, total_bytes, cap);
    // The estimate omits allocator granularity and the cuFFT work area, so a
    // declined reservation is retried smaller before giving up.
    while (chunk > 0 && !workspace.reserve(chunk, n_groups, patch_w, patch_h, scaled_B,
                                           ccf_downsample, device_id))
        chunk /= 2;
    const int n_chunks = chunk > 0 ? (n_patches + chunk - 1) / chunk : 0;
    logfile << "Batched patch alignment: " << n_patches << " patches, chunk size " << chunk
            << " (cap " << cap << ", " << n_chunks << " chunk(s)); free device memory "
            << (free_bytes >> 20) << " of " << (total_bytes >> 20) << " MiB";
    if (chunk == 0) {
        logfile << "; workspace does not fit, using per-patch alignment." << std::endl;
        return;
    }
    logfile << "; workspace " << (workspace.bufferBytes() >> 20) << " MiB + cuFFT work "
            << (workspace.cufftWorkBytes() >> 20) << " MiB, retained until alignment release."
            << std::endl;

    // Slots hold only each patch's CCF window (cudaAlignPatchBatchDevice).
    int window_nx = 0, window_ny = 0;
    patchSpectrumWindow(patch_w, patch_h, scaled_B, ccf_downsample, window_nx, window_ny);
    std::vector<std::vector<RFLOAT> > xs(chunk), ys(chunk);
    std::vector<PatchBatchLog> logs(chunk);
    size_t min_free = free_bytes;
    for (int first = 0; first < n_patches; first += chunk) {
        const int count = std::min(chunk, n_patches - first);
        for (int j = 0; j < count; j++) {
            const PatchBox &box = boxes[first + j];
            if (preparePatchInVram(box.x_start, box.y_start, box.width, box.height, n_groups,
                                   group_start, group_size, workspace.patchSlot(j),
                                   window_nx, window_ny))
                continue;
            // preparePatchInVram consumed its code; the preserved state and the
            // pending slot together decide, exactly as for the per-patch retry.
            const CudaRetryDecision decision = cudaRetryDecisionFor(failure_state, cudaGetLastError());
            if (decision.verdict == CUDA_RETRY_FATAL) {
                REPORT_ERROR_STR("CUDA device context is unusable during batched patch preparation (patch "
                                 << first + j + 1 << " of " << n_patches << "): "
                                 << cudaGetErrorString(decision.decisive)
                                 << ". Refusing to retry alignment on a poisoned context.");
            }
            if (!workspace.release())
                REPORT_ERROR("CUDA batched patch workspace cleanup failed after a preparation failure");
            logfile << "WARNING: batched patch preparation did not complete for patch "
                    << first + j + 1 << " of " << n_patches << "; classified recoverable, so "
                    << "patches " << first + 1 << " to " << n_patches
                    << " use per-patch alignment." << std::endl;
            return;
        }
        for (int j = 0; j < count; j++) xs[j].assign(n_groups, (RFLOAT)0), ys[j].assign(n_groups, (RFLOAT)0);
        cudaAlignPatchBatchDevice(workspace, count, n_groups, patch_w, patch_h, scaled_B,
                                  xs.data(), ys.data(), max_iter, ccf_downsample, device_id,
                                  logs.data());
        size_t chunk_free = 0, chunk_total = 0;
        if (cudaMemGetInfo(&chunk_free, &chunk_total) == cudaSuccess)
            min_free = std::min(min_free, chunk_free);
        else
            (void)cudaGetLastError();
        for (int j = 0; j < count; j++) {
            PatchBatchOutcome &out = outcomes[first + j];
            out.done = true;
            out.xshifts.swap(xs[j]);
            out.yshifts.swap(ys[j]);
            out.log = logs[j];
        }
    }
    logfile << "Batched patch alignment: device memory in use rose by at most "
            << ((free_bytes - min_free) >> 20) << " MiB (sampled after each chunk)." << std::endl;
}

bool CudaMovieSession::reconstructDoseWeighted(
    Image<float> &Isum,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model,
    bool consume_real_frames
) {
    if (failure_state.isPoisoned() || !is_initialized || !has_plan_c2r || !d_fft_work ||
        !d_inverse_tile) return false;
    // d_inverse_tile (one complex frame) is dead once the global inverse
    // transform has finished, and holds nothing the reconstruction needs. It
    // becomes the C2R input the out-of-place weight kernel writes.
    DoseWeightScratch scratch;
    scratch.fourier = d_inverse_tile;
    // Dose weighting reads only d_Fframes. When the caller will never read the
    // real-space movie again, its memory also holds the reconstruction scratch.
    if (consume_real_frames && d_Iframes &&
        mc_cuda::doseScratchLayout(nx, ny, n_frames).total_bytes <= (size_t)n_frames * nx * ny * sizeof(float)) {
        scratch.block = reinterpret_cast<char*>(d_Iframes);
        real_frames_invalid_reason = "dose weighting consumed it as scratch";
        logfile << "Dose-weighting scratch borrowed from the consumed real-space movie" << std::endl;
    }
    return cudaDoseWeightAndInterpolateDevice(d_Fframes, Isum, nx, ny, n_frames, doses, apix, model,
                                              device_id, logfile, &failure_state, plan_c2r, &scratch);
}

bool CudaMovieSession::reconstructUnweighted(
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const ThirdOrderPolynomialModel *model
) {
    if (failure_state.isPoisoned() || !is_initialized) return false;
    if (refuseInvalidRealFrames("the unweighted reconstruction")) return false;
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
    if (refuseInvalidRealFrames("the real-space frame download")) return false;
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
