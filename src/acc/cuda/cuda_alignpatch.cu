#ifdef _CUDA_ENABLED

#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_settings.h"
#include "src/error.h"

#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>

#undef HANDLE_ERROR
#define HANDLE_ERROR(cmd) do { \
    cudaError_t err = (cmd); \
    if (err != cudaSuccess) { \
        logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << cudaGetErrorString(err) << std::endl; \
        REPORT_ERROR("CUDA patch alignment failed: " + std::string(cudaGetErrorString(err))); \
    } \
} while (0)

#undef LAUNCH_HANDLE_ERROR
#define LAUNCH_HANDLE_ERROR(cmd) HANDLE_ERROR(cmd)

#define CUFFT_CHECK(cmd) do { \
    cufftResult result = (cmd); \
    if (result != CUFFT_SUCCESS) { \
        logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ \
                << " : code " << result << std::endl; \
        REPORT_ERROR("cuFFT patch alignment failed: code " + integerToString(result)); \
    } \
} while (0)

static int findGoodSizeCuda(int request) {
    const int good_numbers[] = {192, 216, 256, 288, 324,
                                384, 432, 486, 512, 576, 648,
                                768, 800, 864, 972, 1024,
                                1296, 1536, 1728, 1944,
                                2048, 2304, 2592, 3072, 3200,
                                3456, 3888, 4096, 4608, 5000, 5184,
                                6144, 6250, 6400, 6912, 7776, 8192,
                                9216, 10240, 12288, 12500, -1};
    for (int i = 0; good_numbers[i] != -1; i++) {
        if (good_numbers[i] < request) continue;
        else return good_numbers[i];
    }
    return request;
}

namespace {

struct PatchAlignCache {
    bool valid = false;
    int device_id = -1;
    int ccf_nx = 0;
    int ccf_ny = 0;
    int n_frames = 0;
    int nfx = 0;
    int nfy = 0;
    float cached_scaled_B = -1.0f;

    float2 *d_Fref = nullptr;
    float *d_weight = nullptr;
    float2 *d_Fccs = nullptr;
    float *d_Iccs = nullptr;
    float *d_cur_xshifts = nullptr;
    float *d_cur_yshifts = nullptr;
    float *d_shiftx = nullptr;
    float *d_shifty = nullptr;

    cufftHandle plan_c2r = 0;
    bool has_plan = false;
    size_t cufft_work_size = 0;

    void release() {
        valid = false;
        int previous_device = -1;
        cudaGetDevice(&previous_device);
        if (device_id >= 0) {
            cudaSetDevice(device_id);
        }
        if (has_plan) {
            cufftDestroy(plan_c2r);
            has_plan = false;
        }
        if (d_Fref) { cudaFree(d_Fref); d_Fref = nullptr; }
        if (d_weight) { cudaFree(d_weight); d_weight = nullptr; }
        if (d_Fccs) { cudaFree(d_Fccs); d_Fccs = nullptr; }
        if (d_Iccs) { cudaFree(d_Iccs); d_Iccs = nullptr; }
        if (d_cur_xshifts) { cudaFree(d_cur_xshifts); d_cur_xshifts = nullptr; }
        if (d_cur_yshifts) { cudaFree(d_cur_yshifts); d_cur_yshifts = nullptr; }
        if (d_shiftx) { cudaFree(d_shiftx); d_shiftx = nullptr; }
        if (d_shifty) { cudaFree(d_shifty); d_shifty = nullptr; }
        device_id = -1;
        ccf_nx = ccf_ny = nfx = nfy = n_frames = 0;
        cached_scaled_B = -1.0f;
        cufft_work_size = 0;
        if (previous_device >= 0) cudaSetDevice(previous_device);
    }
};

// The runner serializes CUDA movies within each process. Keep scratch local to
// that process, and discard it if an alignment exits before completion.
static PatchAlignCache s_align_cache;

struct AlignCacheFailureCleanup {
    bool completed = false;
    ~AlignCacheFailureCleanup() { if (!completed) s_align_cache.release(); }
};

struct FrameStagingCleanup {
    float2 *frames = nullptr;
    ~FrameStagingCleanup() { if (frames) cudaFree(frames); }
};

struct AlignPatchEvents {
    cudaEvent_t ev_start_total = nullptr;
    cudaEvent_t ev_stop_total = nullptr;
    cudaEvent_t ev_start_kernel = nullptr;
    cudaEvent_t ev_stop_kernel = nullptr;
    cudaEvent_t ev_start_peak = nullptr;
    cudaEvent_t ev_stop_peak = nullptr;
    cudaEvent_t ev_start_shift = nullptr;
    cudaEvent_t ev_stop_shift = nullptr;
    cudaEvent_t ev_start_cufft = nullptr;
    cudaEvent_t ev_stop_cufft = nullptr;
    cudaEvent_t ev_start_d2h = nullptr;
    cudaEvent_t ev_stop_d2h = nullptr;

    bool init() {
        if (cudaEventCreate(&ev_start_total) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_total) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_start_kernel) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_kernel) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_start_peak) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_peak) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_start_shift) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_shift) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_start_cufft) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_cufft) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_start_d2h) != cudaSuccess) return false;
        if (cudaEventCreate(&ev_stop_d2h) != cudaSuccess) return false;
        return true;
    }

    ~AlignPatchEvents() {
        if (ev_start_total) cudaEventDestroy(ev_start_total);
        if (ev_stop_total) cudaEventDestroy(ev_stop_total);
        if (ev_start_kernel) cudaEventDestroy(ev_start_kernel);
        if (ev_stop_kernel) cudaEventDestroy(ev_stop_kernel);
        if (ev_start_peak) cudaEventDestroy(ev_start_peak);
        if (ev_stop_peak) cudaEventDestroy(ev_stop_peak);
        if (ev_start_shift) cudaEventDestroy(ev_start_shift);
        if (ev_stop_shift) cudaEventDestroy(ev_stop_shift);
        if (ev_start_cufft) cudaEventDestroy(ev_start_cufft);
        if (ev_stop_cufft) cudaEventDestroy(ev_stop_cufft);
        if (ev_start_d2h) cudaEventDestroy(ev_start_d2h);
        if (ev_stop_d2h) cudaEventDestroy(ev_stop_d2h);
    }
};

} // anonymous namespace

void cudaReleaseAlignPatchCache() {
    s_align_cache.release();
}

__global__ void computeWeightsKernel(
    float * __restrict__ d_weight,
    int ccf_nfx, int ccf_nfy, int ccf_nfy_half,
    int nfx, int nfy,
    float scaled_B)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x < ccf_nfx && y < ccf_nfy) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy) : y;
        float ly2 = (float)ly * (float)ly / ((float)nfy * (float)nfy);
        float dist2 = ly2 + (float)x * (float)x / ((float)nfx * (float)nfx);
        d_weight[(size_t)y * ccf_nfx + x] = expf(-2.0f * dist2 * scaled_B);
    }
}

__global__ void computeReferenceKernel(
    const float2 * __restrict__ d_Fframes,
    float2 * __restrict__ d_Fref,
    int ccf_nfx, int ccf_nfy, int ccf_nfy_half,
    int nfx, int nfy,
    int n_frames)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x < ccf_nfx && y < ccf_nfy) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        float sum_r = 0.0f;
        float sum_i = 0.0f;
        size_t frame_stride = (size_t)nfy * nfx;
        size_t base_idx = (size_t)ly * nfx + x;
        #pragma unroll 4
        for (int iframe = 0; iframe < n_frames; iframe++) {
            float2 val = __ldg(&d_Fframes[(size_t)iframe * frame_stride + base_idx]);
            sum_r += val.x;
            sum_i += val.y;
        }
        d_Fref[(size_t)y * ccf_nfx + x] = make_float2(sum_r, sum_i);
    }
}

__global__ void computeCCFKernel(
    const float2 * __restrict__ d_Fframes,
    const float2 * __restrict__ d_Fref,
    const float * __restrict__ d_weight,
    float2 * __restrict__ d_Fccs,
    int ccf_nfx, int ccf_nfy, int ccf_nfy_half,
    int nfx, int nfy,
    int n_frames)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    int iframe = blockIdx.z;
    if (x < ccf_nfx && y < ccf_nfy && iframe < n_frames) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        size_t ref_idx = (size_t)y * ccf_nfx + x;
        float2 fref = __ldg(&d_Fref[ref_idx]);
        float2 fframe = __ldg(&d_Fframes[(size_t)iframe * ((size_t)nfy * nfx) + (size_t)ly * nfx + x]);
        float w = __ldg(&d_weight[ref_idx]);

        // diff = Fref - Fframe
        float dr = fref.x - fframe.x;
        float di = fref.y - fframe.y;

        // ccf = diff * conj(fframe) * weight
        float ccf_r = (dr * fframe.x + di * fframe.y) * w;
        float ccf_i = (di * fframe.x - dr * fframe.y) * w;

        d_Fccs[(size_t)iframe * ((size_t)ccf_nfy * ccf_nfx) + ref_idx] = make_float2(ccf_r, ccf_i);
    }
}

__global__ void findPeakAndInterpolateKernel(
    const float * __restrict__ d_Iccs,
    float * __restrict__ d_cur_xshifts,
    float * __restrict__ d_cur_yshifts,
    int ccf_nx, int ccf_ny,
    int search_range,
    float ccf_scale_x, float ccf_scale_y,
    int n_frames)
{
    int iframe = blockIdx.x;
    if (iframe >= n_frames) return;

    size_t frame_offset = (size_t)iframe * ccf_ny * ccf_nx;
    int range_len = 2 * search_range + 1;
    int total_pts = range_len * range_len;

    float local_max = -1e30f;
    int local_posx = 0;
    int local_posy = 0;

    for (int idx = threadIdx.x; idx < total_pts; idx += blockDim.x) {
        int sy = idx / range_len - search_range;
        int sx = idx % range_len - search_range;
        int iy = (sy < 0) ? ccf_ny + sy : sy;
        int ix = (sx < 0) ? ccf_nx + sx : sx;
        float val = __ldg(&d_Iccs[frame_offset + (size_t)iy * ccf_nx + ix]);
        if (val > local_max) {
            local_max = val;
            local_posx = sx;
            local_posy = sy;
        }
    }

    __shared__ float s_max[256];
    __shared__ int s_posx[256];
    __shared__ int s_posy[256];

    s_max[threadIdx.x] = local_max;
    s_posx[threadIdx.x] = local_posx;
    s_posy[threadIdx.x] = local_posy;
    __syncthreads();

    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) {
            if (s_max[threadIdx.x + stride] > s_max[threadIdx.x]) {
                s_max[threadIdx.x] = s_max[threadIdx.x + stride];
                s_posx[threadIdx.x] = s_posx[threadIdx.x + stride];
                s_posy[threadIdx.x] = s_posy[threadIdx.x + stride];
            }
        }
        __syncthreads();
    }

    if (threadIdx.x == 0) {
        float maxval = s_max[0];
        int posx = s_posx[0];
        int posy = s_posy[0];

        int ipx = (posx < 0) ? ccf_nx + posx : posx;
        int ipy = (posy < 0) ? ccf_ny + posy : posy;
        int ipx_n = posx - 1; if (ipx_n < 0) ipx_n = ccf_nx + ipx_n;
        int ipx_p = posx + 1; if (ipx_p < 0) ipx_p = ccf_nx + ipx_p;
        int ipy_n = posy - 1; if (ipy_n < 0) ipy_n = ccf_ny + ipy_n;
        int ipy_p = posy + 1; if (ipy_p < 0) ipy_p = ccf_ny + ipy_p;

        const float EPS = 1e-15f;
        float vp_x = __ldg(&d_Iccs[frame_offset + (size_t)ipy * ccf_nx + ipx_p]);
        float vn_x = __ldg(&d_Iccs[frame_offset + (size_t)ipy * ccf_nx + ipx_n]);
        float denom_x = vp_x + vn_x - 2.0f * maxval;
        float cur_x = (fabsf(denom_x) > EPS) ? (posx - 0.5f * (vp_x - vn_x) / denom_x) : posx;

        float vp_y = __ldg(&d_Iccs[frame_offset + (size_t)ipy_p * ccf_nx + ipx]);
        float vn_y = __ldg(&d_Iccs[frame_offset + (size_t)ipy_n * ccf_nx + ipx]);
        float denom_y = vp_y + vn_y - 2.0f * maxval;
        float cur_y = (fabsf(denom_y) > EPS) ? (posy - 0.5f * (vp_y - vn_y) / denom_y) : posy;

        d_cur_xshifts[iframe] = cur_x * ccf_scale_x;
        d_cur_yshifts[iframe] = cur_y * ccf_scale_y;
    }
}

__global__ void fourierShiftKernel(
    float2 * __restrict__ d_Fframes,
    const float * __restrict__ d_shiftx,
    const float * __restrict__ d_shifty,
    int nfx, int nfy, int nfy_half,
    int n_frames)
{
    __shared__ float s_sx, s_sy;
    int iframe = blockIdx.z + 1; // frames 1 .. n_frames - 1
    if (iframe >= n_frames) return;

    if (threadIdx.x == 0 && threadIdx.y == 0) {
        s_sx = d_shiftx[iframe];
        s_sy = d_shifty[iframe];
    }
    __syncthreads();

    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;

    if (x < nfx && y < nfy) {
        int ly = (y > nfy_half) ? (y - nfy) : y;
        float phase = 2.0f * (float)M_PI * ((float)x * s_sx + (float)ly * s_sy);
        float sin_p, cos_p;
        __sincosf(phase, &sin_p, &cos_p);

        size_t idx = (size_t)iframe * ((size_t)nfy * nfx) + (size_t)y * nfx + x;
        float2 val = d_Fframes[idx];
        d_Fframes[idx] = make_float2(
            cos_p * val.x - sin_p * val.y,
            sin_p * val.x + cos_p * val.y
        );
    }
}

bool cudaAlignPatchDevice(
    cufftComplex *d_Fframes,
    const int n_frames,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile,
    bool is_global)
{
    if (d_Fframes == nullptr) {
        REPORT_ERROR("cudaAlignPatchDevice received null device pointer");
    }
    HANDLE_ERROR(cudaSetDevice(device_id));
    AlignCacheFailureCleanup cache_cleanup;

    if (pny % 2 == 1 || pnx % 2 == 1) {
        REPORT_ERROR("Patch size must be even");
    }

    int search_range = 50;
    const RFLOAT tolerance = 0.5;

    float ccf_requested_scale = ccf_downsample;
    if (ccf_downsample <= 0) {
        ccf_requested_scale = sqrt(-log(1E-8) / (2 * scaled_B));
    }
    int ccf_nx = findGoodSizeCuda(int(pnx * ccf_requested_scale));
    int ccf_ny = findGoodSizeCuda(int(pny * ccf_requested_scale));
    if (ccf_nx > pnx) ccf_nx = pnx;
    if (ccf_ny > pny) ccf_ny = pny;
    if (ccf_nx % 2 == 1) ccf_nx++;
    if (ccf_ny % 2 == 1) ccf_ny++;
    const int ccf_nfx = ccf_nx / 2 + 1, ccf_nfy = ccf_ny;
    const int ccf_nfy_half = ccf_ny / 2;
    const RFLOAT ccf_scale_x = (RFLOAT)pnx / ccf_nx;
    const RFLOAT ccf_scale_y = (RFLOAT)pny / ccf_ny;
    search_range /= (ccf_scale_x > ccf_scale_y) ? ccf_scale_x : ccf_scale_y;
    if (search_range * 2 + 1 > ccf_nx) search_range = ccf_nx / 2 - 1;
    if (search_range * 2 + 1 > ccf_ny) search_range = ccf_ny / 2 - 1;

    const int nfx = pnx / 2 + 1, nfy = pny;
    const int nfy_half = nfy / 2;

    // Buffer allocations / caching across identical patches
    const size_t sz_fframes = (size_t)n_frames * nfy * nfx * sizeof(float2);
    const size_t sz_fref    = (size_t)ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_weight  = (size_t)ccf_nfy * ccf_nfx * sizeof(float);
    const size_t sz_fccs    = (size_t)n_frames * ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_iccs    = (size_t)n_frames * ccf_ny * ccf_nx * sizeof(float);
    const size_t sz_shifts  = (size_t)n_frames * sizeof(float);

    if (!s_align_cache.valid ||
        s_align_cache.device_id != device_id ||
        s_align_cache.ccf_nx != ccf_nx ||
        s_align_cache.ccf_ny != ccf_ny ||
        s_align_cache.n_frames != n_frames)
    {
        s_align_cache.release();
        HANDLE_ERROR(cudaSetDevice(device_id));

        float2 *d_Fref = nullptr;
        float *d_weight = nullptr;
        float2 *d_Fccs = nullptr;
        float *d_Iccs = nullptr;
        float *d_cur_xshifts = nullptr;
        float *d_cur_yshifts = nullptr;
        float *d_shiftx = nullptr;
        float *d_shifty = nullptr;
        cufftHandle plan_c2r = 0;

        auto cleanup_temp = [&]() {
            if (plan_c2r) cufftDestroy(plan_c2r);
            if (d_Fref) cudaFree(d_Fref);
            if (d_weight) cudaFree(d_weight);
            if (d_Fccs) cudaFree(d_Fccs);
            if (d_Iccs) cudaFree(d_Iccs);
            if (d_cur_xshifts) cudaFree(d_cur_xshifts);
            if (d_cur_yshifts) cudaFree(d_cur_yshifts);
            if (d_shiftx) cudaFree(d_shiftx);
            if (d_shifty) cudaFree(d_shifty);
        };

        if (cudaMalloc(&d_Fref, sz_fref) != cudaSuccess ||
            cudaMalloc(&d_weight, sz_weight) != cudaSuccess ||
            cudaMalloc(&d_Fccs, sz_fccs) != cudaSuccess ||
            cudaMalloc(&d_Iccs, sz_iccs) != cudaSuccess ||
            cudaMalloc(&d_cur_xshifts, sz_shifts) != cudaSuccess ||
            cudaMalloc(&d_cur_yshifts, sz_shifts) != cudaSuccess ||
            cudaMalloc(&d_shiftx, sz_shifts) != cudaSuccess ||
            cudaMalloc(&d_shifty, sz_shifts) != cudaSuccess)
        {
            cleanup_temp();
            logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__
                    << " : cudaMalloc failed for patch alignment cache" << std::endl;
            REPORT_ERROR("CUDA allocation failed for patch alignment cache");
        }

        int n[2] = {ccf_ny, ccf_nx};
        if (cufftPlanMany(&plan_c2r, 2, n, NULL, 1, ccf_nfy * ccf_nfx,
                          NULL, 1, ccf_ny * ccf_nx, CUFFT_C2R, n_frames) != CUFFT_SUCCESS)
        {
            cleanup_temp();
            logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__
                    << " : cufftPlanMany failed for patch alignment" << std::endl;
            REPORT_ERROR("cuFFT plan creation failed for patch alignment");
        }

        size_t cufft_work_size = 0;
        const cufftResult size_result = cufftGetSize(plan_c2r, &cufft_work_size);
        if (size_result != CUFFT_SUCCESS) {
            cleanup_temp();
            logfile << "cuFFT error obtaining patch workspace size: " << size_result << std::endl;
            REPORT_ERROR("cuFFT patch workspace query failed: code " + integerToString(size_result));
        }

        // Commit to cache only after all allocations and plan creation succeed
        s_align_cache.d_Fref = d_Fref;
        s_align_cache.d_weight = d_weight;
        s_align_cache.d_Fccs = d_Fccs;
        s_align_cache.d_Iccs = d_Iccs;
        s_align_cache.d_cur_xshifts = d_cur_xshifts;
        s_align_cache.d_cur_yshifts = d_cur_yshifts;
        s_align_cache.d_shiftx = d_shiftx;
        s_align_cache.d_shifty = d_shifty;
        s_align_cache.plan_c2r = plan_c2r;
        s_align_cache.has_plan = true;
        s_align_cache.cufft_work_size = cufft_work_size;

        s_align_cache.device_id = device_id;
        s_align_cache.ccf_nx = ccf_nx;
        s_align_cache.ccf_ny = ccf_ny;
        s_align_cache.n_frames = n_frames;
        s_align_cache.valid = true;
    }

    float2 *d_Fref = s_align_cache.d_Fref;
    float *d_weight = s_align_cache.d_weight;
    float2 *d_Fccs = s_align_cache.d_Fccs;
    float *d_Iccs = s_align_cache.d_Iccs;
    float *d_cur_xshifts = s_align_cache.d_cur_xshifts;
    float *d_cur_yshifts = s_align_cache.d_cur_yshifts;
    float *d_shiftx = s_align_cache.d_shiftx;
    float *d_shifty = s_align_cache.d_shifty;
    cufftHandle plan_c2r = s_align_cache.plan_c2r;
    size_t cufft_work_size = s_align_cache.cufft_work_size;
    // Input frames are caller-owned and may differ even when CCF scratch fits.
    const size_t total_vram_allocated = sz_fframes + sz_fref + sz_weight +
        sz_fccs + sz_iccs + 4 * sz_shifts + cufft_work_size;

    // Weights computation (recalculated only if dimensions or scaled_B changed)
    dim3 blockWeights(32, 8);
    dim3 gridWeights((ccf_nfx + 31) / 32, (ccf_nfy + 7) / 8);
    if (s_align_cache.cached_scaled_B != (float)scaled_B ||
        s_align_cache.nfx != nfx || s_align_cache.nfy != nfy)
    {
        computeWeightsKernel<<<gridWeights, blockWeights>>>(
            d_weight, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, (float)scaled_B
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        s_align_cache.cached_scaled_B = (float)scaled_B;
        s_align_cache.nfx = nfx;
        s_align_cache.nfy = nfy;
    }

    dim3 blockRef(32, 8);
    dim3 gridRef((ccf_nfx + 31) / 32, (ccf_nfy + 7) / 8);
    dim3 blockCCF(32, 8, 1);
    dim3 gridCCF((ccf_nfx + 31) / 32, (ccf_nfy + 7) / 8, n_frames);
    dim3 blockShift(32, 8, 1);
    dim3 gridShift((nfx + 31) / 32, (nfy + 7) / 8, n_frames - 1);

    std::vector<float> h_cur_xshifts(n_frames, 0.0f);
    std::vector<float> h_cur_yshifts(n_frames, 0.0f);
    std::vector<float> h_shiftx(n_frames, 0.0f);
    std::vector<float> h_shifty(n_frames, 0.0f);

    AlignPatchEvents events;
    if (!events.init()) {
        REPORT_ERROR("Failed to initialize CUDA events for patch alignment");
    }

    HANDLE_ERROR(cudaEventRecord(events.ev_start_total));

    bool converged = false;
    float accumulated_kernel_ms = 0.0f;
    float accumulated_cufft_ms = 0.0f;
    float accumulated_d2h_ms = 0.0f;
    bool shift_timing_pending = false;

    for (int iter = 1; iter <= max_iter; iter++) {
        // 1. Reference computation
        HANDLE_ERROR(cudaEventRecord(events.ev_start_kernel));
        computeReferenceKernel<<<gridRef, blockRef>>>(reinterpret_cast<const float2*>(d_Fframes), d_Fref, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        LAUNCH_HANDLE_ERROR(cudaGetLastError());

        // 2. CCF computation
        computeCCFKernel<<<gridCCF, blockCCF>>>(reinterpret_cast<const float2*>(d_Fframes), d_Fref, d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(events.ev_stop_kernel));

        // 3. Batched cuFFT C2R
        HANDLE_ERROR(cudaEventRecord(events.ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));
        HANDLE_ERROR(cudaEventRecord(events.ev_stop_cufft));

        // 4. Peak finding + subpixel quadratic interpolation
        HANDLE_ERROR(cudaEventRecord(events.ev_start_peak));
        findPeakAndInterpolateKernel<<<n_frames, 256>>>(
            d_Iccs, d_cur_xshifts, d_cur_yshifts,
            ccf_nx, ccf_ny, search_range,
            (float)ccf_scale_x, (float)ccf_scale_y, n_frames
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(events.ev_stop_peak));

        // Copy candidate shifts back to host (synchronous D2H)
        HANDLE_ERROR(cudaEventRecord(events.ev_start_d2h));
        HANDLE_ERROR(cudaMemcpy(h_cur_xshifts.data(), d_cur_xshifts, sz_shifts, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaMemcpy(h_cur_yshifts.data(), d_cur_yshifts, sz_shifts, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaEventRecord(events.ev_stop_d2h));
        HANDLE_ERROR(cudaEventSynchronize(events.ev_stop_d2h));
        float iter_d2h_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&iter_d2h_ms, events.ev_start_d2h, events.ev_stop_d2h));
        accumulated_d2h_ms += iter_d2h_ms;

        // Shift values are required by host convergence logic. This mandatory
        // D2H boundary also completes the preceding same-stream work; timing
        // events therefore need no additional kernel/FFT fences.
        float reference_ms = 0.0f, peak_ms = 0.0f, fft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&reference_ms, events.ev_start_kernel, events.ev_stop_kernel));
        HANDLE_ERROR(cudaEventElapsedTime(&peak_ms, events.ev_start_peak, events.ev_stop_peak));
        HANDLE_ERROR(cudaEventElapsedTime(&fft_ms, events.ev_start_cufft, events.ev_stop_cufft));
        accumulated_kernel_ms += reference_ms + peak_ms;
        accumulated_cufft_ms += fft_ms;
        if (shift_timing_pending) {
            float shift_ms = 0.0f;
            HANDLE_ERROR(cudaEventElapsedTime(&shift_ms, events.ev_start_shift, events.ev_stop_shift));
            accumulated_kernel_ms += shift_ms;
            shift_timing_pending = false;
        }

        // Update relative to frame 0
        RFLOAT x_sumsq = 0.0, y_sumsq = 0.0;
        for (int iframe = n_frames - 1; iframe >= 0; iframe--) {
            h_cur_xshifts[iframe] -= h_cur_xshifts[0];
            h_cur_yshifts[iframe] -= h_cur_yshifts[0];
            x_sumsq += (RFLOAT)h_cur_xshifts[iframe] * h_cur_xshifts[iframe];
            y_sumsq += (RFLOAT)h_cur_yshifts[iframe] * h_cur_yshifts[iframe];
        }
        h_cur_xshifts[0] = 0.0f;
        h_cur_yshifts[0] = 0.0f;

        for (int iframe = 0; iframe < n_frames; iframe++) {
            xshifts[iframe] += h_cur_xshifts[iframe];
            yshifts[iframe] += h_cur_yshifts[iframe];
            h_shiftx[iframe] = -h_cur_xshifts[iframe] / (float)pnx;
            h_shifty[iframe] = -h_cur_yshifts[iframe] / (float)pny;
        }

        // Apply Fourier phase shifts on GPU
        if (n_frames > 1) {
            HANDLE_ERROR(cudaMemcpy(d_shiftx, h_shiftx.data(), sz_shifts, cudaMemcpyHostToDevice));
            HANDLE_ERROR(cudaMemcpy(d_shifty, h_shifty.data(), sz_shifts, cudaMemcpyHostToDevice));
            HANDLE_ERROR(cudaEventRecord(events.ev_start_shift));
            fourierShiftKernel<<<gridShift, blockShift>>>(reinterpret_cast<float2*>(d_Fframes), d_shiftx, d_shifty, nfx, nfy, nfy_half, n_frames);
            LAUNCH_HANDLE_ERROR(cudaGetLastError());
            HANDLE_ERROR(cudaEventRecord(events.ev_stop_shift));
            shift_timing_pending = true;
        }

        RFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);
        logfile << " Iteration " << iter << ": RMSD = " << rmsd << " px" << std::endl;

        if (rmsd < tolerance) {
            converged = true;
            break;
        }
    }

    HANDLE_ERROR(cudaEventRecord(events.ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(events.ev_stop_total));

    if (shift_timing_pending) {
        float shift_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&shift_ms, events.ev_start_shift, events.ev_stop_shift));
        accumulated_kernel_ms += shift_ms;
    }
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, events.ev_start_total, events.ev_stop_total));

    const char *stage_name = is_global ? "Global Alignment" : "Patch Alignment";
    logfile << " [CUDA " << stage_name << " Profile]" << std::endl;
    logfile << "   Host-to-Device transfer time: 0.00 ms (Resident VRAM)" << std::endl;
    logfile << "   Custom kernel execution time: " << std::fixed << std::setprecision(2) << accumulated_kernel_ms << " ms" << std::endl;
    logfile << "   cuFFT execution time:         " << std::fixed << std::setprecision(2) << accumulated_cufft_ms << " ms" << std::endl;
    logfile << "   Device-to-Host transfer time: " << std::fixed << std::setprecision(2) << accumulated_d2h_ms << " ms" << std::endl;
    logfile << "   Total GPU alignment time:     " << std::fixed << std::setprecision(2) << total_ms << " ms" << std::endl;
    logfile << "   Buffer VRAM:                  " << std::fixed << std::setprecision(2) << ((total_vram_allocated - cufft_work_size) / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   cuFFT workspace VRAM:         " << std::fixed << std::setprecision(2) << (cufft_work_size / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   Tracked alignment memory:     " << std::fixed << std::setprecision(2) << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << " [CUDA " << stage_name << "] completed; converged="
            << (converged ? "yes" : "no") << std::endl;
    cache_cleanup.completed = true;
    return converged;
}

bool cudaAlignPatch(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile,
    bool is_global)
{
    const int n_frames = (int)xshifts.size();
    if (n_frames == 0) return true;
    const int nfx = XSIZE(Fframes[0]), nfy = YSIZE(Fframes[0]);
    const size_t sz_fframes = (size_t)n_frames * nfy * nfx * sizeof(float2);

    float2 *d_Fframes = nullptr;
    HANDLE_ERROR(cudaSetDevice(device_id));
    HANDLE_ERROR(cudaMalloc(&d_Fframes, sz_fframes));
    FrameStagingCleanup staging_cleanup;
    staging_cleanup.frames = d_Fframes;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        HANDLE_ERROR(cudaMemcpy(
            d_Fframes + (size_t)iframe * nfy * nfx,
            Fframes[iframe].data,
            (size_t)nfy * nfx * sizeof(float2),
            cudaMemcpyHostToDevice
        ));
    }

    bool converged = cudaAlignPatchDevice(
        reinterpret_cast<cufftComplex*>(d_Fframes), n_frames, pnx, pny, scaled_B,
        xshifts, yshifts, max_iter, ccf_downsample, device_id, logfile, is_global
    );

    if (is_global) {
        for (int iframe = 0; iframe < n_frames; iframe++) {
            HANDLE_ERROR(cudaMemcpy(
                Fframes[iframe].data,
                d_Fframes + (size_t)iframe * nfy * nfx,
                (size_t)nfy * nfx * sizeof(float2),
                cudaMemcpyDeviceToHost
            ));
        }
    }
    return converged;
}

#endif // _CUDA_ENABLED
