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

#define CUFFT_CHECK(cmd) do { \
    cufftResult err = (cmd); \
    if (err != CUFFT_SUCCESS) { \
        REPORT_ERROR("cuFFT error: code " + integerToString(err)); \
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

__global__ void computeWeightsKernel(
    float *d_weight,
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
        d_weight[y * ccf_nfx + x] = expf(-2.0f * dist2 * scaled_B);
    }
}

__global__ void computeReferenceKernel(
    const float2 *d_Fframes,
    float2 *d_Fref,
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
        for (int iframe = 0; iframe < n_frames; iframe++) {
            float2 val = d_Fframes[iframe * frame_stride + ly * nfx + x];
            sum_r += val.x;
            sum_i += val.y;
        }
        d_Fref[y * ccf_nfx + x] = make_float2(sum_r, sum_i);
    }
}

__global__ void computeCCFKernel(
    const float2 *d_Fframes,
    const float2 *d_Fref,
    const float *d_weight,
    float2 *d_Fccs,
    int ccf_nfx, int ccf_nfy, int ccf_nfy_half,
    int nfx, int nfy,
    int n_frames)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    int iframe = blockIdx.z;
    if (x < ccf_nfx && y < ccf_nfy && iframe < n_frames) {
        int ly = (y > ccf_nfy_half) ? (y - ccf_nfy + nfy) : y;
        float2 fref = d_Fref[y * ccf_nfx + x];
        float2 fframe = d_Fframes[iframe * ((size_t)nfy * nfx) + ly * nfx + x];
        float w = d_weight[y * ccf_nfx + x];

        // diff = Fref - Fframe
        float dr = fref.x - fframe.x;
        float di = fref.y - fframe.y;

        // diff * fframe.conj() = (dr + i*di) * (fframe.x - i*fframe.y)
        float ccf_r = (dr * fframe.x + di * fframe.y) * w;
        float ccf_i = (di * fframe.x - dr * fframe.y) * w;

        d_Fccs[iframe * ((size_t)ccf_nfy * ccf_nfx) + y * ccf_nfx + x] = make_float2(ccf_r, ccf_i);
    }
}

__global__ void findPeakAndInterpolateKernel(
    const float *d_Iccs,
    float *d_cur_xshifts,
    float *d_cur_yshifts,
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
    int local_index = total_pts;

    for (int idx = threadIdx.x; idx < total_pts; idx += blockDim.x) {
        int sy = idx / range_len - search_range;
        int sx = idx % range_len - search_range;
        int iy = (sy < 0) ? ccf_ny + sy : sy;
        int ix = (sx < 0) ? ccf_nx + sx : sx;
        float val = d_Iccs[frame_offset + iy * ccf_nx + ix];
        if (val > local_max) {
            local_max = val;
            local_index = idx;
        }
    }

    __shared__ float s_max[256];
    __shared__ int s_index[256];

    s_max[threadIdx.x] = local_max;
    s_index[threadIdx.x] = local_index;
    __syncthreads();

    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (threadIdx.x < stride) {
            // CPU scans y then x and retains the first equal maximum. Compare
            // raster indices as well as values so the parallel tree keeps that order.
            const int other = threadIdx.x + stride;
            if (s_max[other] > s_max[threadIdx.x] ||
                (s_max[other] == s_max[threadIdx.x] &&
                 s_index[other] < s_index[threadIdx.x])) {
                s_max[threadIdx.x] = s_max[other];
                s_index[threadIdx.x] = s_index[other];
            }
        }
        __syncthreads();
    }

    if (threadIdx.x == 0) {
        float maxval = s_max[0];
        int posx = s_index[0] < total_pts ? s_index[0] % range_len - search_range : 0;
        int posy = s_index[0] < total_pts ? s_index[0] / range_len - search_range : 0;

        int ipx_n = posx - 1; if (ipx_n < 0) ipx_n = ccf_nx + ipx_n;
        int ipx   = posx;     if (ipx < 0)   ipx   = ccf_nx + ipx;
        int ipx_p = posx + 1; if (ipx_p < 0) ipx_p = ccf_nx + ipx_p;
        int ipy_n = posy - 1; if (ipy_n < 0) ipy_n = ccf_ny + ipy_n;
        int ipy   = posy;     if (ipy < 0)   ipy   = ccf_ny + ipy;
        int ipy_p = posy + 1; if (ipy_p < 0) ipy_p = ccf_ny + ipy_p;

        const float EPS = 1e-15f;
        float vp_x = d_Iccs[frame_offset + ipy * ccf_nx + ipx_p];
        float vn_x = d_Iccs[frame_offset + ipy * ccf_nx + ipx_n];
        float denom_x = vp_x + vn_x - 2.0f * maxval;
        float cur_x = (fabsf(denom_x) > EPS) ? (posx - 0.5f * (vp_x - vn_x) / denom_x) : posx;

        float vp_y = d_Iccs[frame_offset + ipy_p * ccf_nx + ipx];
        float vn_y = d_Iccs[frame_offset + ipy_n * ccf_nx + ipx];
        float denom_y = vp_y + vn_y - 2.0f * maxval;
        float cur_y = (fabsf(denom_y) > EPS) ? (posy - 0.5f * (vp_y - vn_y) / denom_y) : posy;

        d_cur_xshifts[iframe] = cur_x * ccf_scale_x;
        d_cur_yshifts[iframe] = cur_y * ccf_scale_y;
    }
}

__global__ void fourierShiftKernel(
    float2 *d_Fframes,
    const float *d_shiftx,
    const float *d_shifty,
    int nfx, int nfy, int nfy_half,
    int n_frames)
{
    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    int iframe = blockIdx.z + 1; // frames 1 .. n_frames - 1

    if (x < nfx && y < nfy && iframe < n_frames) {
        int ly = (y > nfy_half) ? (y - nfy) : y;
        float sx = d_shiftx[iframe];
        float sy = d_shifty[iframe];
        float phase = 2.0f * (float)M_PI * (x * sx + ly * sy);
        float sin_p, cos_p;
        __sincosf(phase, &sin_p, &cos_p);

        size_t idx = iframe * ((size_t)nfy * nfx) + y * nfx + x;
        float2 val = d_Fframes[idx];
        d_Fframes[idx] = make_float2(
            cos_p * val.x - sin_p * val.y,
            sin_p * val.x + cos_p * val.y
        );
    }
}

bool cudaAlignPatchDevice(
    cufftComplex *d_Fframes_in,
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
    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    if (count_err != cudaSuccess || dev_count == 0) {
        REPORT_ERROR("No CUDA capable devices found");
    }
    if (device_id < 0 || device_id >= dev_count) {
        REPORT_ERROR_STR("Invalid CUDA device ID: " << device_id << " (system has " << dev_count << " devices)");
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    cudaEvent_t ev_start_total, ev_stop_total;
    cudaEvent_t ev_start_kernel, ev_stop_kernel;
    cudaEvent_t ev_start_cufft, ev_stop_cufft;
    cudaEvent_t ev_start_d2h, ev_stop_d2h;

    HANDLE_ERROR(cudaEventCreate(&ev_start_total));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_total));
    HANDLE_ERROR(cudaEventCreate(&ev_start_kernel));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_kernel));
    HANDLE_ERROR(cudaEventCreate(&ev_start_cufft));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_cufft));
    HANDLE_ERROR(cudaEventCreate(&ev_start_d2h));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_d2h));

    HANDLE_ERROR(cudaEventRecord(ev_start_total));

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
    float2 *d_Fframes = (float2*)d_Fframes_in;

    // Buffer allocations
    const size_t sz_fframes = (size_t)n_frames * nfy * nfx * sizeof(float2);
    const size_t sz_fref    = (size_t)ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_weight  = (size_t)ccf_nfy * ccf_nfx * sizeof(float);
    const size_t sz_fccs    = (size_t)n_frames * ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_iccs    = (size_t)n_frames * ccf_ny * ccf_nx * sizeof(float);
    const size_t sz_shifts  = (size_t)n_frames * sizeof(float);

    float2 *d_Fref = nullptr;
    float *d_weight = nullptr;
    float2 *d_Fccs = nullptr;
    float *d_Iccs = nullptr;
    float *d_cur_xshifts = nullptr;
    float *d_cur_yshifts = nullptr;
    float *d_shiftx = nullptr;
    float *d_shifty = nullptr;

    HANDLE_ERROR(cudaMalloc(&d_Fref, sz_fref));
    HANDLE_ERROR(cudaMalloc(&d_weight, sz_weight));
    HANDLE_ERROR(cudaMalloc(&d_Fccs, sz_fccs));
    HANDLE_ERROR(cudaMalloc(&d_Iccs, sz_iccs));
    HANDLE_ERROR(cudaMalloc(&d_cur_xshifts, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_cur_yshifts, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_shiftx, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_shifty, sz_shifts));

    size_t total_vram_allocated = sz_fframes + sz_fref + sz_weight + sz_fccs + sz_iccs + 4 * sz_shifts;

    // Initialize cuFFT batched C2R plan
    cufftHandle plan_c2r;
    int n[2] = {ccf_ny, ccf_nx};
    CUFFT_CHECK(cufftPlanMany(&plan_c2r, 2, n, NULL, 1, ccf_nfy * ccf_nfx, NULL, 1, ccf_ny * ccf_nx, CUFFT_C2R, n_frames));
    size_t cufft_work_size = 0;
    CUFFT_CHECK(cufftGetSize(plan_c2r, &cufft_work_size));
    total_vram_allocated += cufft_work_size;

    // Weights computation
    dim3 blockWeights(16, 16);
    dim3 gridWeights((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
    computeWeightsKernel<<<gridWeights, blockWeights>>>(d_weight, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, (float)scaled_B);
    LAUNCH_HANDLE_ERROR(cudaGetLastError());

    dim3 blockRef(16, 16);
    dim3 gridRef((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
    dim3 blockCCF(16, 16, 1);
    dim3 gridCCF((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16, n_frames);
    dim3 blockShift(16, 16, 1);
    dim3 gridShift((nfx + 15) / 16, (nfy + 15) / 16, n_frames - 1);

    std::vector<float> h_cur_xshifts(n_frames, 0.0f);
    std::vector<float> h_cur_yshifts(n_frames, 0.0f);
    std::vector<float> h_shiftx(n_frames, 0.0f);
    std::vector<float> h_shifty(n_frames, 0.0f);

    bool converged = false;
    float accumulated_kernel_ms = 0.0f;
    float accumulated_cufft_ms = 0.0f;
    float accumulated_d2h_ms = 0.0f;

    for (int iter = 1; iter <= max_iter; iter++) {
        // 1. Reference computation
        HANDLE_ERROR(cudaEventRecord(ev_start_kernel));
        computeReferenceKernel<<<gridRef, blockRef>>>(d_Fframes, d_Fref, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        LAUNCH_HANDLE_ERROR(cudaGetLastError());

        // 2. CCF computation
        computeCCFKernel<<<gridCCF, blockCCF>>>(d_Fframes, d_Fref, d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_kernel));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_kernel));
        float k1_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&k1_ms, ev_start_kernel, ev_stop_kernel));
        accumulated_kernel_ms += k1_ms;

        // 3. Batched cuFFT C2R
        HANDLE_ERROR(cudaEventRecord(ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));
        HANDLE_ERROR(cudaEventRecord(ev_stop_cufft));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_cufft));
        float iter_cufft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&iter_cufft_ms, ev_start_cufft, ev_stop_cufft));
        accumulated_cufft_ms += iter_cufft_ms;

        // 4. Peak finding + subpixel quadratic interpolation
        HANDLE_ERROR(cudaEventRecord(ev_start_kernel));
        findPeakAndInterpolateKernel<<<n_frames, 256>>>(
            d_Iccs, d_cur_xshifts, d_cur_yshifts,
            ccf_nx, ccf_ny, search_range,
            (float)ccf_scale_x, (float)ccf_scale_y, n_frames
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_kernel));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_kernel));
        float k2_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&k2_ms, ev_start_kernel, ev_stop_kernel));
        accumulated_kernel_ms += k2_ms;

        // Copy candidate shifts back to host
        HANDLE_ERROR(cudaEventRecord(ev_start_d2h));
        HANDLE_ERROR(cudaMemcpy(h_cur_xshifts.data(), d_cur_xshifts, sz_shifts, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaMemcpy(h_cur_yshifts.data(), d_cur_yshifts, sz_shifts, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaEventRecord(ev_stop_d2h));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_d2h));
        float iter_d2h_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&iter_d2h_ms, ev_start_d2h, ev_stop_d2h));
        accumulated_d2h_ms += iter_d2h_ms;

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
            HANDLE_ERROR(cudaEventRecord(ev_start_kernel));
            fourierShiftKernel<<<gridShift, blockShift>>>(d_Fframes, d_shiftx, d_shifty, nfx, nfy, nfy_half, n_frames);
            LAUNCH_HANDLE_ERROR(cudaGetLastError());
            HANDLE_ERROR(cudaEventRecord(ev_stop_kernel));
            HANDLE_ERROR(cudaEventSynchronize(ev_stop_kernel));
            float shift_kernel_ms = 0.0f;
            HANDLE_ERROR(cudaEventElapsedTime(&shift_kernel_ms, ev_start_kernel, ev_stop_kernel));
            accumulated_kernel_ms += shift_kernel_ms;
        }

        RFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);
        logfile << " Iteration " << iter << ": RMSD = " << rmsd << " px" << std::endl;

        if (rmsd < tolerance) {
            converged = true;
            break;
        }
    }

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    // Profile logging
    const char *stage_name = is_global ? "Global Alignment" : "Patch Alignment";
    logfile << " [CUDA " << stage_name << " Profile]" << std::endl;
    logfile << "   Host-to-Device transfer time: 0.00 ms (Resident VRAM)" << std::endl;
    logfile << "   Custom kernel execution time: " << std::fixed << std::setprecision(2) << accumulated_kernel_ms << " ms" << std::endl;
    logfile << "   cuFFT execution time:         " << std::fixed << std::setprecision(2) << accumulated_cufft_ms << " ms" << std::endl;
    logfile << "   Device-to-Host transfer time: " << std::fixed << std::setprecision(2) << accumulated_d2h_ms << " ms" << std::endl;
    logfile << "   Total GPU alignment time:     " << std::fixed << std::setprecision(2) << total_ms << " ms" << std::endl;
    logfile << "   Buffer VRAM:                  " << std::fixed << std::setprecision(2) << ((total_vram_allocated - cufft_work_size) / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   cuFFT workspace VRAM:         " << std::fixed << std::setprecision(2) << (cufft_work_size / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   Peak GPU memory allocated:    " << std::fixed << std::setprecision(2) << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;

    // Cleanup
    CUFFT_CHECK(cufftDestroy(plan_c2r));
    HANDLE_ERROR(cudaFree(d_Fref));
    HANDLE_ERROR(cudaFree(d_weight));
    HANDLE_ERROR(cudaFree(d_Fccs));
    HANDLE_ERROR(cudaFree(d_Iccs));
    HANDLE_ERROR(cudaFree(d_cur_xshifts));
    HANDLE_ERROR(cudaFree(d_cur_yshifts));
    HANDLE_ERROR(cudaFree(d_shiftx));
    HANDLE_ERROR(cudaFree(d_shifty));

    HANDLE_ERROR(cudaEventDestroy(ev_start_total));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_total));
    HANDLE_ERROR(cudaEventDestroy(ev_start_kernel));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_kernel));
    HANDLE_ERROR(cudaEventDestroy(ev_start_cufft));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_cufft));
    HANDLE_ERROR(cudaEventDestroy(ev_start_d2h));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_d2h));

    logfile << " [CUDA " << stage_name << "] completed; converged="
            << (converged ? "yes" : "no") << std::endl;
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

    for (int iframe = 0; iframe < n_frames; iframe++) {
        HANDLE_ERROR(cudaMemcpy(
            d_Fframes + (size_t)iframe * nfy * nfx,
            Fframes[iframe].data,
            (size_t)nfy * nfx * sizeof(float2),
            cudaMemcpyHostToDevice
        ));
    }

    bool converged = cudaAlignPatchDevice(
        (cufftComplex*)d_Fframes, n_frames, pnx, pny, scaled_B,
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

    HANDLE_ERROR(cudaFree(d_Fframes));
    return converged;
}

#endif // _CUDA_ENABLED
