#ifdef _CUDA_ENABLED

#include "src/acc/cuda/cuda_realspace_dw.h"
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
        return false; \
    } \
} while (0)

#undef LAUNCH_HANDLE_ERROR
#define LAUNCH_HANDLE_ERROR(cmd) HANDLE_ERROR(cmd)

#define CUFFT_CHECK(cmd) do { \
    cufftResult result = (cmd); \
    if (result != CUFFT_SUCCESS) { \
        logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ \
                << " : code " << result << std::endl; \
        return false; \
    } \
} while (0)

class CudaMemoryCleanup {
public:
    ~CudaMemoryCleanup() {
        for (size_t i = 0; i < allocations.size(); ++i) {
            if (allocations[i] != nullptr) cudaFree(allocations[i]);
        }
    }
    void add(void *allocation) { allocations.push_back(allocation); }

private:
    std::vector<void *> allocations;
};

class CudaEventCleanup {
public:
    ~CudaEventCleanup() {
        for (size_t i = 0; i < events.size(); ++i) cudaEventDestroy(events[i]);
    }
    void add(cudaEvent_t event) { events.push_back(event); }

private:
    std::vector<cudaEvent_t> events;
};

class CufftPlanCleanup {
public:
    CufftPlanCleanup() : owns_plan(false) {}
    ~CufftPlanCleanup() { if (owns_plan) cufftDestroy(plan); }
    void take(cufftHandle handle) { plan = handle; owns_plan = true; }

private:
    cufftHandle plan;
    bool owns_plan;
};

namespace {
struct FramePolynomial {
    float x[6];
    float y[6];
};

FramePolynomial polynomialForFrame(const ThirdOrderPolynomialModel &model, int iframe) {
    const float z = (float)iframe, z2 = z * z, z3 = z * z2;
    FramePolynomial result;
    for (int i = 0; i < 6; ++i) {
        const int c = 3 * i;
        // Preserve RFLOAT coefficient arithmetic and cast only the completed sum.
        result.x[i] = (float)(model.coeffX(c) * z + model.coeffX(c + 1) * z2 + model.coeffX(c + 2) * z3);
        result.y[i] = (float)(model.coeffY(c) * z + model.coeffY(c + 1) * z2 + model.coeffY(c + 2) * z3);
    }
    return result;
}
} // namespace

// Dose weighting kernel implementing Grant & Grigorieff (2015) model
// Preserves exact IEEE-754 reference arithmetic with (32, 8) warp coalescing & shared-memory staging
__global__ void applyDoseWeightKernel(
    float2 * __restrict__ d_Fframe,
    int nfx, int nfy, int nfy_half,
    float nfx2, float nfy2, float apix,
    const float * __restrict__ d_doses,
    int n_frames, int iframe)
{
    __shared__ float s_doses[64];

    int tid = threadIdx.y * blockDim.x + threadIdx.x;
    if (tid < n_frames && tid < 64) {
        s_doses[tid] = d_doses[tid];
    }
    __syncthreads();

    int x = blockIdx.x * blockDim.x + threadIdx.x;
    int y = blockIdx.y * blockDim.y + threadIdx.y;
    if (x >= nfx || y >= nfy) return;

    size_t idx = (size_t)y * nfx + x;
    int ly = (y > nfy_half) ? (y - nfy) : y;

    if (x == 0 && ly == 0) {
        float norm_weight = 1.0f / sqrtf((float)n_frames);
        d_Fframe[idx].x *= norm_weight;
        d_Fframe[idx].y *= norm_weight;
        return;
    }

    float ly2 = (float)ly * (float)ly / nfy2;
    float dinv2 = ly2 + (float)x * (float)x / nfx2;
    float dinv = sqrtf(dinv2) / apix;
    float Ne = (0.245f * powf(dinv, -1.665f) + 2.81f) * 2.0f;

    float sum_weight_sq = 0.0f;
    const float *doses_ptr = (n_frames <= 64) ? s_doses : d_doses;
    for (int j = 0; j < n_frames; j++) {
        float w = expf(-doses_ptr[j] / Ne);
        sum_weight_sq += w * w;
    }

    float cur_weight = expf(-doses_ptr[iframe] / Ne);
    float norm_weight = cur_weight / sqrtf(sum_weight_sq);

    d_Fframe[idx].x *= norm_weight;
    d_Fframe[idx].y *= norm_weight;
}

// Polynomial real-space bilinear interpolation & accumulation kernel
__global__ void interpolateAndAccumulatePolynomialKernel(
    float * __restrict__ d_Isum,
    float * __restrict__ d_Isum_sub,
    const float * __restrict__ d_Iframe,
    int nx, int ny,
    float x_C0, float x_C1, float x_C2, float x_C3, float x_C4, float x_C5,
    float y_C0, float y_C1, float y_C2, float y_C3, float y_C4, float y_C5)
{
    int ix = blockIdx.x * blockDim.x + threadIdx.x;
    int iy = blockIdx.y * blockDim.y + threadIdx.y;
    if (ix >= nx || iy >= ny) return;

    float x = (float)ix / (float)nx - 0.5f;
    float y = (float)iy / (float)ny - 0.5f;

    float x_fitted = x_C0 + (x_C1 + x_C2 * x) * x + (x_C3 + x_C4 * y + x_C5 * x) * y;
    float y_fitted = y_C0 + (y_C1 + y_C2 * x) * x + (y_C3 + y_C4 * y + y_C5 * x) * y;

    float x_target = (float)ix - x_fitted;
    float y_target = (float)iy - y_fitted;

    int x0 = (int)floorf(x_target);
    int y0 = (int)floorf(y_target);
    int x1 = x0 + 1;
    int y1 = y0 + 1;

    bool valid = true;
    if (x0 < 0 || x1 < 0) { x0 = 0; valid = false; }
    if (x0 >= nx || x1 >= nx) { x0 = nx - 1; valid = false; }
    if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
    if (y0 >= ny || y1 >= ny) { y0 = ny - 1; valid = false; }

    float val;
    if (!valid) {
        val = __ldg(&d_Iframe[(size_t)y0 * nx + x0]);
    } else {
        float fx = x_target - (float)x0;
        float fy = y_target - (float)y0;

        size_t row0 = (size_t)y0 * nx;
        size_t row1 = (size_t)y1 * nx;
        float d00 = __ldg(&d_Iframe[row0 + x0]);
        float d01 = __ldg(&d_Iframe[row0 + x1]);
        float d10 = __ldg(&d_Iframe[row1 + x0]);
        float d11 = __ldg(&d_Iframe[row1 + x1]);

        float dx0 = d00 + (d01 - d00) * fx;
        float dx1 = d10 + (d11 - d10) * fx;
        val = dx0 + (dx1 - dx0) * fy;
    }

    size_t idx = (size_t)iy * nx + ix;
    d_Isum[idx] += val;
    if (d_Isum_sub != nullptr) {
        d_Isum_sub[idx] += val;
    }
}

__global__ void accumulateDirectKernel(
    float * __restrict__ d_Isum,
    float * __restrict__ d_Isum_sub,
    const float * __restrict__ d_Iframe,
    size_t total_pixels)
{
    size_t idx = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < total_pixels) {
        float val = __ldg(&d_Iframe[idx]);
        d_Isum[idx] += val;
        if (d_Isum_sub != nullptr) {
            d_Isum_sub[idx] += val;
        }
    }
}

bool cudaDoseWeightAndInterpolateDevice(
    Image<RFLOAT> &Isum,
    const void *d_Fframes,
    int nx, int ny,
    int n_frames,
    double apix,
    const std::vector<double> &doses,
    const ThirdOrderPolynomialModel *model,
    int device_id,
    std::ostream &logfile)
{
    if (device_id < 0) {
        cudaGetDevice(&device_id);
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    Isum.resize(ny, nx);
    Isum.initZeros();

    CudaMemoryCleanup memory_cleanup;
    CudaEventCleanup event_cleanup;
    CufftPlanCleanup plan_cleanup;

    const int nfx = nx / 2 + 1, nfy = ny;
    const int nfy_half = nfy / 2;
    const float nfy2 = (float)nfy * (float)nfy;
    const float nfx2 = (float)(nfx - 1) * (float)(nfx - 1) * 4.0f;
    const size_t sz_fframe = (size_t)nfy * nfx * sizeof(float2);
    const size_t sz_iframe = (size_t)ny * nx * sizeof(float);

    cudaEvent_t ev_start_total, ev_stop_total;
    cudaEvent_t ev_start_dw, ev_stop_dw;
    cudaEvent_t ev_start_cufft, ev_stop_cufft;
    cudaEvent_t ev_start_interp, ev_stop_interp;

    HANDLE_ERROR(cudaEventCreate(&ev_start_total));
    event_cleanup.add(ev_start_total);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_total));
    event_cleanup.add(ev_stop_total);
    HANDLE_ERROR(cudaEventCreate(&ev_start_dw));
    event_cleanup.add(ev_start_dw);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_dw));
    event_cleanup.add(ev_stop_dw);
    HANDLE_ERROR(cudaEventCreate(&ev_start_cufft));
    event_cleanup.add(ev_start_cufft);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_cufft));
    event_cleanup.add(ev_stop_cufft);
    HANDLE_ERROR(cudaEventCreate(&ev_start_interp));
    event_cleanup.add(ev_start_interp);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_interp));
    event_cleanup.add(ev_stop_interp);

    HANDLE_ERROR(cudaEventRecord(ev_start_total));

    float2 *d_Fframe = nullptr;
    float *d_Iframe = nullptr;
    float *d_Isum = nullptr;
    float *d_doses = nullptr;

    size_t total_vram_allocated = 0;
    HANDLE_ERROR(cudaMalloc((void**)&d_Fframe, sz_fframe));
    memory_cleanup.add(d_Fframe);
    total_vram_allocated += sz_fframe;

    HANDLE_ERROR(cudaMalloc((void**)&d_Iframe, sz_iframe));
    memory_cleanup.add(d_Iframe);
    total_vram_allocated += sz_iframe;

    HANDLE_ERROR(cudaMalloc((void**)&d_Isum, sz_iframe));
    memory_cleanup.add(d_Isum);
    total_vram_allocated += sz_iframe;
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_iframe));

    HANDLE_ERROR(cudaMalloc((void**)&d_doses, n_frames * sizeof(float)));
    memory_cleanup.add(d_doses);
    total_vram_allocated += n_frames * sizeof(float);

    std::vector<float> h_doses(n_frames);
    for (int i = 0; i < n_frames; i++) h_doses[i] = (float)doses[i];
    HANDLE_ERROR(cudaMemcpy(d_doses, h_doses.data(), n_frames * sizeof(float), cudaMemcpyHostToDevice));

    cufftHandle plan_c2r;
    int n[2] = {ny, nx};
    CUFFT_CHECK(cufftPlanMany(&plan_c2r, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1));
    plan_cleanup.take(plan_c2r);
    size_t cufft_work_size = 0;
    CUFFT_CHECK(cufftGetSize(plan_c2r, &cufft_work_size));
    total_vram_allocated += cufft_work_size;

    dim3 blockDW(32, 8);
    dim3 gridDW((nfx + 31) / 32, (nfy + 7) / 8);

    dim3 blockInterp(32, 8);
    dim3 gridInterp((nx + 31) / 32, (ny + 7) / 8);

    float total_dw_ms = 0.0f;
    float total_cufft_ms = 0.0f;
    float total_interp_ms = 0.0f;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        // Copy frame from resident buffer in VRAM
        const float2 *src_frame = (const float2*)d_Fframes + (size_t)iframe * nfy * nfx;
        HANDLE_ERROR(cudaMemcpy(d_Fframe, src_frame, sz_fframe, cudaMemcpyDeviceToDevice));

        // Dose weighting
        HANDLE_ERROR(cudaEventRecord(ev_start_dw));
        applyDoseWeightKernel<<<gridDW, blockDW>>>(
            d_Fframe, nfx, nfy, nfy_half, nfx2, nfy2, (float)apix, d_doses, n_frames, iframe
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_dw));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_dw));
        float dw_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&dw_ms, ev_start_dw, ev_stop_dw));
        total_dw_ms += dw_ms;

        // Inverse FFT
        HANDLE_ERROR(cudaEventRecord(ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fframe, (cufftReal*)d_Iframe));
        HANDLE_ERROR(cudaEventRecord(ev_stop_cufft));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_cufft));
        float cufft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&cufft_ms, ev_start_cufft, ev_stop_cufft));
        total_cufft_ms += cufft_ms;

        // Interpolate and accumulate
        HANDLE_ERROR(cudaEventRecord(ev_start_interp));
        if (model != nullptr) {
            const FramePolynomial coeff = polynomialForFrame(*model, iframe);

            interpolateAndAccumulatePolynomialKernel<<<gridInterp, blockInterp>>>(
                d_Isum, nullptr, d_Iframe, nx, ny,
                coeff.x[0], coeff.x[1], coeff.x[2], coeff.x[3], coeff.x[4], coeff.x[5],
                coeff.y[0], coeff.y[1], coeff.y[2], coeff.y[3], coeff.y[4], coeff.y[5]
            );
        } else {
            size_t total_pixels = (size_t)ny * nx;
            int block1D = 256;
            int grid1D = (total_pixels + block1D - 1) / block1D;
            accumulateDirectKernel<<<grid1D, block1D>>>(d_Isum, nullptr, d_Iframe, total_pixels);
        }
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_interp));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_interp));
        float interp_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&interp_ms, ev_start_interp, ev_stop_interp));
        total_interp_ms += interp_ms;
    }

    // Single D2H download of reconstructed image
    HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    logfile << " [CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]" << std::endl;
    logfile << "  Device: " << device_id << ", Frames: " << n_frames << ", Size: " << nx << "x" << ny << std::endl;
    logfile << "  Peak VRAM: " << std::fixed << std::setprecision(2)
            << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "  Dose Weighting Kernel: " << total_dw_ms << " ms" << std::endl;
    logfile << "  cuFFT C2R Execution:   " << total_cufft_ms << " ms" << std::endl;
    logfile << "  Interpolation & Accum: " << total_interp_ms << " ms" << std::endl;
    logfile << "  Total DW Reconstruction Time: " << total_ms << " ms" << std::endl;

    return true;
}

bool cudaDoseWeightAndInterpolate(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    Image<RFLOAT> &Isum,
    Image<RFLOAT> *Isum_odd,
    int nx, int ny,
    double apix,
    const std::vector<double> &doses,
    const ThirdOrderPolynomialModel *model,
    int device_id,
    std::ostream &logfile)
{
    if (device_id < 0) {
        cudaGetDevice(&device_id);
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    int n_frames = (int)Fframes.size();
    Isum.resize(ny, nx);
    Isum.initZeros();
    if (Isum_odd != nullptr) {
        Isum_odd->resize(ny, nx);
        Isum_odd->initZeros();
    }

    CudaMemoryCleanup memory_cleanup;
    CudaEventCleanup event_cleanup;
    CufftPlanCleanup plan_cleanup;

    const int nfx = nx / 2 + 1, nfy = ny;
    const int nfy_half = nfy / 2;
    const float nfy2 = (float)nfy * (float)nfy;
    const float nfx2 = (float)(nfx - 1) * (float)(nfx - 1) * 4.0f;
    const size_t sz_fframe = (size_t)nfy * nfx * sizeof(float2);
    const size_t sz_iframe = (size_t)ny * nx * sizeof(float);

    cudaEvent_t ev_start_total, ev_stop_total;
    cudaEvent_t ev_start_h2d, ev_stop_h2d;
    cudaEvent_t ev_start_dw, ev_stop_dw;
    cudaEvent_t ev_start_cufft, ev_stop_cufft;
    cudaEvent_t ev_start_interp, ev_stop_interp;

    HANDLE_ERROR(cudaEventCreate(&ev_start_total));
    event_cleanup.add(ev_start_total);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_total));
    event_cleanup.add(ev_stop_total);
    HANDLE_ERROR(cudaEventCreate(&ev_start_h2d));
    event_cleanup.add(ev_start_h2d);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_h2d));
    event_cleanup.add(ev_stop_h2d);
    HANDLE_ERROR(cudaEventCreate(&ev_start_dw));
    event_cleanup.add(ev_start_dw);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_dw));
    event_cleanup.add(ev_stop_dw);
    HANDLE_ERROR(cudaEventCreate(&ev_start_cufft));
    event_cleanup.add(ev_start_cufft);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_cufft));
    event_cleanup.add(ev_stop_cufft);
    HANDLE_ERROR(cudaEventCreate(&ev_start_interp));
    event_cleanup.add(ev_start_interp);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_interp));
    event_cleanup.add(ev_stop_interp);

    HANDLE_ERROR(cudaEventRecord(ev_start_total));

    float2 *d_Fframe = nullptr;
    float *d_Iframe = nullptr;
    float *d_Isum = nullptr;
    float *d_Isum_odd = nullptr;
    float *d_doses = nullptr;

    size_t total_vram_allocated = 0;
    HANDLE_ERROR(cudaMalloc((void**)&d_Fframe, sz_fframe));
    memory_cleanup.add(d_Fframe);
    total_vram_allocated += sz_fframe;

    HANDLE_ERROR(cudaMalloc((void**)&d_Iframe, sz_iframe));
    memory_cleanup.add(d_Iframe);
    total_vram_allocated += sz_iframe;

    HANDLE_ERROR(cudaMalloc((void**)&d_Isum, sz_iframe));
    memory_cleanup.add(d_Isum);
    total_vram_allocated += sz_iframe;
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_iframe));

    if (Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMalloc((void**)&d_Isum_odd, sz_iframe));
        memory_cleanup.add(d_Isum_odd);
        total_vram_allocated += sz_iframe;
        HANDLE_ERROR(cudaMemset(d_Isum_odd, 0, sz_iframe));
    }

    HANDLE_ERROR(cudaMalloc((void**)&d_doses, n_frames * sizeof(float)));
    memory_cleanup.add(d_doses);
    total_vram_allocated += n_frames * sizeof(float);

    std::vector<float> h_doses(n_frames);
    for (int i = 0; i < n_frames; i++) h_doses[i] = (float)doses[i];
    HANDLE_ERROR(cudaMemcpy(d_doses, h_doses.data(), n_frames * sizeof(float), cudaMemcpyHostToDevice));

    cufftHandle plan_c2r;
    int n[2] = {ny, nx};
    CUFFT_CHECK(cufftPlanMany(&plan_c2r, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1));
    plan_cleanup.take(plan_c2r);
    size_t cufft_work_size = 0;
    CUFFT_CHECK(cufftGetSize(plan_c2r, &cufft_work_size));
    total_vram_allocated += cufft_work_size;

    dim3 blockDW(32, 8);
    dim3 gridDW((nfx + 31) / 32, (nfy + 7) / 8);

    dim3 blockInterp(32, 8);
    dim3 gridInterp((nx + 31) / 32, (ny + 7) / 8);

    float total_h2d_ms = 0.0f;
    float total_dw_ms = 0.0f;
    float total_cufft_ms = 0.0f;
    float total_interp_ms = 0.0f;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        // Upload frame to GPU
        HANDLE_ERROR(cudaEventRecord(ev_start_h2d));
        HANDLE_ERROR(cudaMemcpy(d_Fframe, Fframes[iframe].data, sz_fframe, cudaMemcpyHostToDevice));
        HANDLE_ERROR(cudaEventRecord(ev_stop_h2d));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_h2d));
        float h2d_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&h2d_ms, ev_start_h2d, ev_stop_h2d));
        total_h2d_ms += h2d_ms;

        // Dose weighting
        HANDLE_ERROR(cudaEventRecord(ev_start_dw));
        applyDoseWeightKernel<<<gridDW, blockDW>>>(
            d_Fframe, nfx, nfy, nfy_half, nfx2, nfy2, (float)apix, d_doses, n_frames, iframe
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_dw));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_dw));
        float dw_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&dw_ms, ev_start_dw, ev_stop_dw));
        total_dw_ms += dw_ms;

        // Inverse FFT
        HANDLE_ERROR(cudaEventRecord(ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fframe, (cufftReal*)d_Iframe));
        HANDLE_ERROR(cudaEventRecord(ev_stop_cufft));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_cufft));
        float cufft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&cufft_ms, ev_start_cufft, ev_stop_cufft));
        total_cufft_ms += cufft_ms;

        // Interpolate and accumulate
        HANDLE_ERROR(cudaEventRecord(ev_start_interp));
        float *cur_Isum_sub = ((iframe % 2 != 0) && (d_Isum_odd != nullptr)) ? d_Isum_odd : nullptr;

        if (model != nullptr) {
            const FramePolynomial coeff = polynomialForFrame(*model, iframe);

            interpolateAndAccumulatePolynomialKernel<<<gridInterp, blockInterp>>>(
                d_Isum, cur_Isum_sub, d_Iframe, nx, ny,
                coeff.x[0], coeff.x[1], coeff.x[2], coeff.x[3], coeff.x[4], coeff.x[5],
                coeff.y[0], coeff.y[1], coeff.y[2], coeff.y[3], coeff.y[4], coeff.y[5]
            );
        } else {
            size_t total_pixels = (size_t)ny * nx;
            int block1D = 256;
            int grid1D = (total_pixels + block1D - 1) / block1D;
            accumulateDirectKernel<<<grid1D, block1D>>>(d_Isum, cur_Isum_sub, d_Iframe, total_pixels);
        }
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_interp));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_interp));
        float interp_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&interp_ms, ev_start_interp, ev_stop_interp));
        total_interp_ms += interp_ms;
    }

    // Download reconstructed images
    HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));
    if (Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMemcpy((*Isum_odd)().data, d_Isum_odd, sz_iframe, cudaMemcpyDeviceToHost));
    }

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    logfile << " [CUDA Dose-Weighted Reconstruction Profile]" << std::endl;
    logfile << "  Device: " << device_id << ", Frames: " << n_frames << ", Size: " << nx << "x" << ny << std::endl;
    logfile << "  Peak VRAM: " << std::fixed << std::setprecision(2)
            << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "  Host-to-Device transfer time: " << total_h2d_ms << " ms" << std::endl;
    logfile << "  Dose Weighting Kernel: " << total_dw_ms << " ms" << std::endl;
    logfile << "  cuFFT C2R Execution:   " << total_cufft_ms << " ms" << std::endl;
    logfile << "  Interpolation & Accum: " << total_interp_ms << " ms" << std::endl;
    logfile << "  Total DW Reconstruction Time: " << total_ms << " ms" << std::endl;

    return true;
}

bool cudaRealSpaceInterpolationDevice(
    Image<RFLOAT> &Isum,
    Image<RFLOAT> *Isum_odd,
    const float *d_Iframes,
    int nx, int ny,
    int n_frames,
    const ThirdOrderPolynomialModel *model,
    int device_id,
    std::ostream &logfile)
{
    if (device_id < 0) {
        cudaGetDevice(&device_id);
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    Isum.resize(ny, nx);
    Isum.initZeros();
    if (Isum_odd != nullptr) {
        Isum_odd->resize(ny, nx);
        Isum_odd->initZeros();
    }

    CudaMemoryCleanup memory_cleanup;
    const size_t sz_iframe = (size_t)ny * nx * sizeof(float);

    float *d_Isum = nullptr;
    float *d_Isum_odd = nullptr;

    HANDLE_ERROR(cudaMalloc((void**)&d_Isum, sz_iframe));
    memory_cleanup.add(d_Isum);
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_iframe));

    if (Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMalloc((void**)&d_Isum_odd, sz_iframe));
        memory_cleanup.add(d_Isum_odd);
        HANDLE_ERROR(cudaMemset(d_Isum_odd, 0, sz_iframe));
    }

    dim3 blockInterp(32, 8);
    dim3 gridInterp((nx + 31) / 32, (ny + 7) / 8);

    for (int iframe = 0; iframe < n_frames; iframe++) {
        const float *d_Iframe = d_Iframes + (size_t)iframe * ny * nx;
        float *cur_Isum_sub = ((iframe % 2 != 0) && (d_Isum_odd != nullptr)) ? d_Isum_odd : nullptr;

        if (model != nullptr) {
            const FramePolynomial coeff = polynomialForFrame(*model, iframe);

            interpolateAndAccumulatePolynomialKernel<<<gridInterp, blockInterp>>>(
                d_Isum, cur_Isum_sub, d_Iframe, nx, ny,
                coeff.x[0], coeff.x[1], coeff.x[2], coeff.x[3], coeff.x[4], coeff.x[5],
                coeff.y[0], coeff.y[1], coeff.y[2], coeff.y[3], coeff.y[4], coeff.y[5]
            );
        } else {
            size_t total_pixels = (size_t)ny * nx;
            int block1D = 256;
            int grid1D = (total_pixels + block1D - 1) / block1D;
            accumulateDirectKernel<<<grid1D, block1D>>>(d_Isum, cur_Isum_sub, d_Iframe, total_pixels);
        }
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
    }

    HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));
    if (Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMemcpy((*Isum_odd)().data, d_Isum_odd, sz_iframe, cudaMemcpyDeviceToHost));
    }

    return true;
}

#endif // _CUDA_ENABLED
