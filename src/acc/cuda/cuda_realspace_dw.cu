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

// Dose weighting kernel implementing Grant & Grigorieff (2015) model
__global__ void applyDoseWeightKernel(
    float2 * __restrict__ d_Fframe,
    int nfx, int nfy, int nfy_half,
    float nfx2, float nfy2, float apix,
    const float * __restrict__ d_doses,
    int n_frames, int iframe)
{
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
    for (int j = 0; j < n_frames; j++) {
        float w = expf(-d_doses[j] / Ne);
        sum_weight_sq += w * w;
    }

    float cur_weight = expf(-d_doses[iframe] / Ne);
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
    if (y0 < 0 || y1 < 0) { y0 = 0; valid = false; }
    if (x1 >= nx || x0 >= nx - 1) { x0 = nx - 1; valid = false; }
    if (y1 >= ny || y0 >= ny - 1) { y0 = ny - 1; valid = false; }

    float val;
    if (!valid) {
        val = d_Iframe[(size_t)y0 * nx + x0];
    } else {
        float fx = x_target - (float)x0;
        float fy = y_target - (float)y0;

        float d00 = d_Iframe[(size_t)y0 * nx + x0];
        float d01 = d_Iframe[(size_t)y0 * nx + x1];
        float d10 = d_Iframe[(size_t)y1 * nx + x0];
        float d11 = d_Iframe[(size_t)y1 * nx + x1];

        float dx0 = d00 + (d01 - d00) * fx;
        float dx1 = d10 + (d11 - d10) * fx;
        val = dx0 + (dx1 - dx0) * fy;
    }

    size_t out_idx = (size_t)iy * nx + ix;
    d_Isum[out_idx] += val;
    if (d_Isum_sub != nullptr) {
        d_Isum_sub[out_idx] += val;
    }
}

// Direct accumulation kernel for MOTION_MODEL_NULL
__global__ void accumulateDirectKernel(
    float * __restrict__ d_Isum,
    float * __restrict__ d_Isum_sub,
    const float * __restrict__ d_Iframe,
    size_t total_pixels)
{
    size_t idx = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < total_pixels) {
        float val = d_Iframe[idx];
        d_Isum[idx] += val;
        if (d_Isum_sub != nullptr) {
            d_Isum_sub[idx] += val;
        }
    }
}

bool cudaDoseWeightAndInterpolate(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    Image<float> &Isum,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model,
    const int device_id,
    std::ostream &logfile)
{
    const int n_frames = Fframes.size();
    if (n_frames == 0) return true;

    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    if (count_err != cudaSuccess || dev_count == 0) {
        REPORT_ERROR("No CUDA capable devices found");
    }
    if (device_id < 0 || device_id >= dev_count) {
        REPORT_ERROR_STR("Invalid CUDA device ID: " << device_id << " (system has " << dev_count << " devices)");
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    CudaMemoryCleanup memory_cleanup;
    CudaEventCleanup event_cleanup;
    CufftPlanCleanup plan_cleanup;

    const int nfx = XSIZE(Fframes[0]), nfy = YSIZE(Fframes[0]);
    const int nx = (nfx - 1) * 2, ny = nfy;
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

    // Allocate working buffers: single frame Fourier, single frame real, single accumulator
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

    // Initialize cuFFT 2D C2R plan for single frame
    cufftHandle plan_c2r;
    int n[2] = {ny, nx};
    CUFFT_CHECK(cufftPlanMany(&plan_c2r, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1));
    plan_cleanup.take(plan_c2r);
    size_t cufft_work_size = 0;
    CUFFT_CHECK(cufftGetSize(plan_c2r, &cufft_work_size));
    total_vram_allocated += cufft_work_size;

    dim3 blockDW(16, 16);
    dim3 gridDW((nfx + 15) / 16, (nfy + 15) / 16);

    dim3 blockInterp(16, 16);
    dim3 gridInterp((nx + 15) / 16, (ny + 15) / 16);

    float total_dw_ms = 0.0f;
    float total_cufft_ms = 0.0f;
    float total_interp_ms = 0.0f;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        // 1. Upload frame to d_Fframe
        HANDLE_ERROR(cudaMemcpy(d_Fframe, Fframes[iframe].data, sz_fframe, cudaMemcpyHostToDevice));

        // 2. Apply dose weighting
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

        // 3. Inverse FFT to real space (unnormalized, matching FFTW)
        HANDLE_ERROR(cudaEventRecord(ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fframe, (cufftReal*)d_Iframe));
        HANDLE_ERROR(cudaEventRecord(ev_stop_cufft));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_cufft));
        float cufft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&cufft_ms, ev_start_cufft, ev_stop_cufft));
        total_cufft_ms += cufft_ms;

        // 4. Interpolate and accumulate into d_Isum
        HANDLE_ERROR(cudaEventRecord(ev_start_interp));
        if (model != nullptr) {
            const float z = (float)iframe, z2 = z * z, z3 = z * z2;
            const Matrix1D<RFLOAT> &coeffX = model->coeffX;
            const Matrix1D<RFLOAT> &coeffY = model->coeffY;

            float x_C0 = (float)(coeffX(0)  * z + coeffX(1)  * z2 + coeffX(2)  * z3);
            float x_C1 = (float)(coeffX(3)  * z + coeffX(4)  * z2 + coeffX(5)  * z3);
            float x_C2 = (float)(coeffX(6)  * z + coeffX(7)  * z2 + coeffX(8)  * z3);
            float x_C3 = (float)(coeffX(9)  * z + coeffX(10) * z2 + coeffX(11) * z3);
            float x_C4 = (float)(coeffX(12) * z + coeffX(13) * z2 + coeffX(14) * z3);
            float x_C5 = (float)(coeffX(15) * z + coeffX(16) * z2 + coeffX(17) * z3);

            float y_C0 = (float)(coeffY(0)  * z + coeffY(1)  * z2 + coeffY(2)  * z3);
            float y_C1 = (float)(coeffY(3)  * z + coeffY(4)  * z2 + coeffY(5)  * z3);
            float y_C2 = (float)(coeffY(6)  * z + coeffY(7)  * z2 + coeffY(8)  * z3);
            float y_C3 = (float)(coeffY(9)  * z + coeffY(10) * z2 + coeffY(11) * z3);
            float y_C4 = (float)(coeffY(12) * z + coeffY(13) * z2 + coeffY(14) * z3);
            float y_C5 = (float)(coeffY(15) * z + coeffY(16) * z2 + coeffY(17) * z3);

            interpolateAndAccumulatePolynomialKernel<<<gridInterp, blockInterp>>>(
                d_Isum, nullptr, d_Iframe, nx, ny,
                x_C0, x_C1, x_C2, x_C3, x_C4, x_C5,
                y_C0, y_C1, y_C2, y_C3, y_C4, y_C5
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

    // 5. Download final accumulated micrograph to host Isum
    HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    // Telemetry logging
    logfile << " [CUDA Reconstruction Profile]" << std::endl;
    logfile << "  Device: " << device_id << ", Frames: " << n_frames << ", Size: " << nx << "x" << ny << std::endl;
    logfile << "  Peak VRAM: " << std::fixed << std::setprecision(2)
            << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "  Analytical Dose Weighting: " << total_dw_ms << " ms" << std::endl;
    logfile << "  cuFFT Inverse C2R: " << total_cufft_ms << " ms" << std::endl;
    logfile << "  Real-space Interpolation & Accumulation: " << total_interp_ms << " ms" << std::endl;
    logfile << "  Total Reconstruction Time: " << total_ms << " ms" << std::endl;

    return true;
}

bool cudaRealSpaceInterpolation(
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const std::vector<Image<float> > &Iframes,
    const ThirdOrderPolynomialModel *model,
    const int device_id,
    std::ostream &logfile)
{
    const int n_frames = Iframes.size();
    if (n_frames == 0) return true;

    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    if (count_err != cudaSuccess || dev_count == 0) {
        REPORT_ERROR("No CUDA capable devices found");
    }
    if (device_id < 0 || device_id >= dev_count) {
        REPORT_ERROR_STR("Invalid CUDA device ID: " << device_id << " (system has " << dev_count << " devices)");
    }
    HANDLE_ERROR(cudaSetDevice(device_id));

    CudaMemoryCleanup memory_cleanup;
    CudaEventCleanup event_cleanup;

    const int nx = XSIZE(Iframes[0]()), ny = YSIZE(Iframes[0]());
    const size_t sz_iframe = (size_t)ny * nx * sizeof(float);

    cudaEvent_t ev_start_total, ev_stop_total;
    HANDLE_ERROR(cudaEventCreate(&ev_start_total));
    event_cleanup.add(ev_start_total);
    HANDLE_ERROR(cudaEventCreate(&ev_stop_total));
    event_cleanup.add(ev_stop_total);
    HANDLE_ERROR(cudaEventRecord(ev_start_total));

    float *d_Iframe = nullptr;
    float *d_Isum = nullptr;
    float *d_Isum_even = nullptr;
    float *d_Isum_odd = nullptr;

    size_t total_vram_allocated = 0;
    HANDLE_ERROR(cudaMalloc((void**)&d_Iframe, sz_iframe));
    memory_cleanup.add(d_Iframe);
    total_vram_allocated += sz_iframe;

    HANDLE_ERROR(cudaMalloc((void**)&d_Isum, sz_iframe));
    memory_cleanup.add(d_Isum);
    total_vram_allocated += sz_iframe;
    HANDLE_ERROR(cudaMemset(d_Isum, 0, sz_iframe));

    if (Isum_even != nullptr && Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMalloc((void**)&d_Isum_even, sz_iframe));
        memory_cleanup.add(d_Isum_even);
        total_vram_allocated += sz_iframe;
        HANDLE_ERROR(cudaMemset(d_Isum_even, 0, sz_iframe));

        HANDLE_ERROR(cudaMalloc((void**)&d_Isum_odd, sz_iframe));
        memory_cleanup.add(d_Isum_odd);
        total_vram_allocated += sz_iframe;
        HANDLE_ERROR(cudaMemset(d_Isum_odd, 0, sz_iframe));
    }

    dim3 blockInterp(16, 16);
    dim3 gridInterp((nx + 15) / 16, (ny + 15) / 16);

    for (int iframe = 0; iframe < n_frames; iframe++) {
        // Stream frame to GPU
        HANDLE_ERROR(cudaMemcpy(d_Iframe, Iframes[iframe]().data, sz_iframe, cudaMemcpyHostToDevice));

        float *d_sub = nullptr;
        if (d_Isum_even != nullptr && d_Isum_odd != nullptr) {
            d_sub = (iframe % 2 == 0) ? d_Isum_even : d_Isum_odd;
        }

        if (model != nullptr) {
            const float z = (float)iframe, z2 = z * z, z3 = z * z2;
            const Matrix1D<RFLOAT> &coeffX = model->coeffX;
            const Matrix1D<RFLOAT> &coeffY = model->coeffY;

            float x_C0 = (float)(coeffX(0)  * z + coeffX(1)  * z2 + coeffX(2)  * z3);
            float x_C1 = (float)(coeffX(3)  * z + coeffX(4)  * z2 + coeffX(5)  * z3);
            float x_C2 = (float)(coeffX(6)  * z + coeffX(7)  * z2 + coeffX(8)  * z3);
            float x_C3 = (float)(coeffX(9)  * z + coeffX(10) * z2 + coeffX(11) * z3);
            float x_C4 = (float)(coeffX(12) * z + coeffX(13) * z2 + coeffX(14) * z3);
            float x_C5 = (float)(coeffX(15) * z + coeffX(16) * z2 + coeffX(17) * z3);

            float y_C0 = (float)(coeffY(0)  * z + coeffY(1)  * z2 + coeffY(2)  * z3);
            float y_C1 = (float)(coeffY(3)  * z + coeffY(4)  * z2 + coeffY(5)  * z3);
            float y_C2 = (float)(coeffY(6)  * z + coeffY(7)  * z2 + coeffY(8)  * z3);
            float y_C3 = (float)(coeffY(9)  * z + coeffY(10) * z2 + coeffY(11) * z3);
            float y_C4 = (float)(coeffY(12) * z + coeffY(13) * z2 + coeffY(14) * z3);
            float y_C5 = (float)(coeffY(15) * z + coeffY(16) * z2 + coeffY(17) * z3);

            interpolateAndAccumulatePolynomialKernel<<<gridInterp, blockInterp>>>(
                d_Isum, d_sub, d_Iframe, nx, ny,
                x_C0, x_C1, x_C2, x_C3, x_C4, x_C5,
                y_C0, y_C1, y_C2, y_C3, y_C4, y_C5
            );
        } else {
            size_t total_pixels = (size_t)ny * nx;
            int block1D = 256;
            int grid1D = (total_pixels + block1D - 1) / block1D;
            accumulateDirectKernel<<<grid1D, block1D>>>(d_Isum, d_sub, d_Iframe, total_pixels);
        }
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
    }

    // Download final sum
    HANDLE_ERROR(cudaMemcpy(Isum().data, d_Isum, sz_iframe, cudaMemcpyDeviceToHost));
    if (Isum_even != nullptr && Isum_odd != nullptr) {
        HANDLE_ERROR(cudaMemcpy((*Isum_even)().data, d_Isum_even, sz_iframe, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaMemcpy((*Isum_odd)().data, d_Isum_odd, sz_iframe, cudaMemcpyDeviceToHost));
    }

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    logfile << " [CUDA Unweighted Reconstruction Profile]" << std::endl;
    logfile << "  Device: " << device_id << ", Frames: " << n_frames << ", Size: " << nx << "x" << ny << std::endl;
    logfile << "  Peak VRAM: " << std::fixed << std::setprecision(2)
            << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "  Total Unweighted Reconstruction Time: " << total_ms << " ms" << std::endl;

    return true;
}

#endif // _CUDA_ENABLED
