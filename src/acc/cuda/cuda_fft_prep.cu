#include "cuda_fft_prep.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <iostream>
#include <vector>
#include <chrono>

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

class CufftPlanCleanup {
public:
    CufftPlanCleanup() : owns_plan(false) {}
    ~CufftPlanCleanup() { if (owns_plan) cufftDestroy(plan); }
    void take(cufftHandle handle) { plan = handle; owns_plan = true; }

private:
    cufftHandle plan;
    bool owns_plan;
};

#define HANDLE_ERROR(err) do { \
    cudaError_t e = (err); \
    if (e != cudaSuccess) { \
        logfile << "CUDA Error in " << __FILE__ << ":" << __LINE__ << " : " \
                << cudaGetErrorString(e) << std::endl; \
        return false; \
    } \
} while(0)

#define CUFFT_CHECK(call) do { \
    cufftResult r = (call); \
    if (r != CUFFT_SUCCESS) { \
        logfile << "cuFFT Error in " << __FILE__ << ":" << __LINE__ << " : code " \
                << r << std::endl; \
        return false; \
    } \
} while(0)

static float *s_d_cached_Iframes = nullptr;
static size_t s_cached_bytes = 0;
static int s_cached_nx = 0;
static int s_cached_ny = 0;
static int s_cached_n_frames = 0;
static int s_cached_device_id = -1;

class CachedFramesCleanup {
public:
    CachedFramesCleanup() : preserve(false) {}
    ~CachedFramesCleanup() { if (!preserve) cudaReleaseCachedFrames(); }
    void keep() { preserve = true; }

private:
    bool preserve;
};

void cudaReleaseCachedFrames() {
    if (s_d_cached_Iframes != nullptr) {
        if (s_cached_device_id >= 0) {
            cudaSetDevice(s_cached_device_id);
        }
        cudaFree(s_d_cached_Iframes);
        s_d_cached_Iframes = nullptr;
        s_cached_bytes = 0;
        s_cached_nx = 0;
        s_cached_ny = 0;
        s_cached_n_frames = 0;
        s_cached_device_id = -1;
    }
}

__global__ void scaleComplexKernel(cufftComplex *d_data, size_t count, float scale) {
    size_t idx = (size_t)blockIdx.x * blockDim.x + threadIdx.x;
    if (idx < count) {
        d_data[idx].x *= scale;
        d_data[idx].y *= scale;
    }
}

__global__ void cropAndGroupPatchKernel(
    const float * __restrict__ d_Iframes,
    float * __restrict__ d_Ipatches,
    int nx, int ny,
    int x_start, int y_start,
    int patch_w, int patch_h,
    const int * __restrict__ d_group_start,
    const int * __restrict__ d_group_size,
    int n_groups
) {
    int px = blockIdx.x * blockDim.x + threadIdx.x;
    int py = blockIdx.y * blockDim.y + threadIdx.y;
    int g  = blockIdx.z;

    if (px < patch_w && py < patch_h && g < n_groups) {
        int g_start = d_group_start[g];
        int g_size  = d_group_size[g];
        int full_x = x_start + px;
        int full_y = y_start + py;
        size_t full_frame_stride = (size_t)ny * nx;
        size_t full_pix_offset = (size_t)full_y * nx + full_x;

        float sum = 0.0f;
        for (int t = 0; t < g_size; t++) {
            int iframe = g_start + t;
            sum += d_Iframes[(size_t)iframe * full_frame_stride + full_pix_offset];
        }

        size_t patch_stride = (size_t)patch_h * patch_w;
        size_t patch_pix_offset = (size_t)py * patch_w + px;
        d_Ipatches[(size_t)g * patch_stride + patch_pix_offset] = sum;
    }
}

bool cudaForwardFFT2D(
    const std::vector<Image<float> > &Iframes,
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile
) {
    const int n_frames = (int)Iframes.size();
    if (n_frames == 0) return true;

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

    const int nfx = nx / 2 + 1;
    const size_t sz_real = (size_t)ny * nx * sizeof(float);
    const size_t sz_comp = (size_t)ny * nfx * sizeof(cufftComplex);

    float *d_real = nullptr;
    cufftComplex *d_comp = nullptr;
    CudaMemoryCleanup memory_cleanup;
    HANDLE_ERROR(cudaMalloc((void**)&d_real, sz_real));
    memory_cleanup.add(d_real);
    cudaError_t comp_err = cudaMalloc((void**)&d_comp, sz_comp);
    if (comp_err != cudaSuccess) {
        logfile << "ERROR: Failed to allocate GPU Fourier buffer for forward FFT" << std::endl;
        return false;
    }
    memory_cleanup.add(d_comp);

    cufftHandle plan_r2c;
    CufftPlanCleanup plan_cleanup;
    int n[2] = {ny, nx};
    cufftResult plan_res = cufftPlanMany(&plan_r2c, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_R2C, 1);
    if (plan_res != CUFFT_SUCCESS) {
        logfile << "ERROR: cufftPlanMany R2C failed" << std::endl;
        return false;
    }
    plan_cleanup.take(plan_r2c);

    const float inv_size = 1.0f / ((float)nx * ny);
    const size_t n_comp_elems = (size_t)ny * nfx;
    const int block = 256;
    const int grid = (int)((n_comp_elems + block - 1) / block);

    Fframes.resize(n_frames);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        Fframes[iframe].resizeNoCp(2, 1, ny, nfx);
        HANDLE_ERROR(cudaMemcpy(d_real, MULTIDIM_ARRAY(Iframes[iframe]()), sz_real, cudaMemcpyHostToDevice));
        CUFFT_CHECK(cufftExecR2C(plan_r2c, (cufftReal*)d_real, d_comp));
        scaleComplexKernel<<<grid, block>>>(d_comp, n_comp_elems, inv_size);
        HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaMemcpy(MULTIDIM_ARRAY(Fframes[iframe]), d_comp, sz_comp, cudaMemcpyDeviceToHost));
    }

    return true;
}

bool cudaInverseFFT2D(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    std::vector<Image<float> > &Iframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile,
    bool keep_on_gpu
) {
    const int n_frames = (int)Fframes.size();
    if (n_frames == 0) return true;

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

    // Clear any prior movie's cache before preparing the cache for this run.
    cudaReleaseCachedFrames();
    CachedFramesCleanup cached_frames_cleanup;

    const int nfx = nx / 2 + 1;
    const size_t sz_real = (size_t)ny * nx * sizeof(float);
    const size_t sz_comp = (size_t)ny * nfx * sizeof(cufftComplex);
    const size_t total_real_bytes = sz_real * n_frames;

    // Check if caching on GPU is requested
    if (keep_on_gpu) {
        cudaError_t alloc_cache = cudaMalloc((void**)&s_d_cached_Iframes, total_real_bytes);
        if (alloc_cache == cudaSuccess) {
            s_cached_bytes = total_real_bytes;
            s_cached_nx = nx;
            s_cached_ny = ny;
            s_cached_n_frames = n_frames;
            s_cached_device_id = device_id;
        } else {
            logfile << " [CUDA] Notice: insufficient VRAM to cache all real frames ("
                    << (total_real_bytes / 1024 / 1024) << " MiB). Falling back to streaming." << std::endl;
            s_d_cached_Iframes = nullptr;
        }
    }

    cufftComplex *d_comp = nullptr;
    float *d_real_single = nullptr;
    CudaMemoryCleanup memory_cleanup;
    HANDLE_ERROR(cudaMalloc((void**)&d_comp, sz_comp));
    memory_cleanup.add(d_comp);
    if (s_d_cached_Iframes == nullptr) {
        HANDLE_ERROR(cudaMalloc((void**)&d_real_single, sz_real));
        memory_cleanup.add(d_real_single);
    }

    cufftHandle plan_c2r;
    CufftPlanCleanup plan_cleanup;
    int n[2] = {ny, nx};
    cufftResult plan_res = cufftPlanMany(&plan_c2r, 2, n, NULL, 1, 0, NULL, 1, 0, CUFFT_C2R, 1);
    if (plan_res != CUFFT_SUCCESS) {
        logfile << "ERROR: cufftPlanMany C2R failed" << std::endl;
        return false;
    }
    plan_cleanup.take(plan_c2r);

    Iframes.resize(n_frames);
    for (int iframe = 0; iframe < n_frames; iframe++) {
        Iframes[iframe]().reshape(ny, nx);
        HANDLE_ERROR(cudaMemcpy(d_comp, MULTIDIM_ARRAY(Fframes[iframe]), sz_comp, cudaMemcpyHostToDevice));

        float *target_d_real = (s_d_cached_Iframes != nullptr)
            ? (s_d_cached_Iframes + (size_t)iframe * ny * nx)
            : d_real_single;

        CUFFT_CHECK(cufftExecC2R(plan_c2r, d_comp, (cufftReal*)target_d_real));
        HANDLE_ERROR(cudaMemcpy(MULTIDIM_ARRAY(Iframes[iframe]()), target_d_real, sz_real, cudaMemcpyDeviceToHost));
    }

    if (s_d_cached_Iframes != nullptr) cached_frames_cleanup.keep();
    return true;
}

bool cudaPreparePatch(
    const std::vector<Image<float> > &Iframes,
    const int x_start, const int x_end,
    const int y_start, const int y_end,
    const int n_groups,
    const std::vector<int> &group_start,
    const std::vector<int> &group_size,
    std::vector<MultidimArray<fComplex> > &Fpatches,
    const int device_id,
    std::ostream &logfile
) {
    if (n_groups == 0) return true;
    if (Iframes.empty() || group_start.size() < (size_t)n_groups ||
        group_size.size() < (size_t)n_groups) {
        logfile << "ERROR: Invalid frame or group metadata for CUDA patch preparation" << std::endl;
        return false;
    }

    const int nx = XSIZE(Iframes[0]());
    const int ny = YSIZE(Iframes[0]());
    if (x_start < 0 || y_start < 0 || x_end > nx || y_end > ny ||
        x_end <= x_start || y_end <= y_start ||
        ((x_end - x_start) % 2) != 0 || ((y_end - y_start) % 2) != 0) {
        logfile << "ERROR: Invalid patch bounds for CUDA patch preparation" << std::endl;
        return false;
    }
    for (int igroup = 0; igroup < n_groups; igroup++) {
        if (group_start[igroup] < 0 || group_size[igroup] < 0 ||
            group_start[igroup] + group_size[igroup] > (int)Iframes.size()) {
            logfile << "ERROR: Invalid frame group for CUDA patch preparation" << std::endl;
            return false;
        }
    }

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

    const int patch_w = x_end - x_start;
    const int patch_h = y_end - y_start;
    const int patch_nfx = patch_w / 2 + 1;
    const size_t sz_patch_real = (size_t)patch_h * patch_w * sizeof(float);
    const size_t sz_patch_comp = (size_t)patch_h * patch_nfx * sizeof(cufftComplex);
    const size_t sz_all_patch_real = sz_patch_real * n_groups;
    const size_t sz_all_patch_comp = sz_patch_comp * n_groups;

    float *d_Ipatches = nullptr;
    cufftComplex *d_Fpatches = nullptr;
    CudaMemoryCleanup memory_cleanup;
    HANDLE_ERROR(cudaMalloc((void**)&d_Ipatches, sz_all_patch_real));
    memory_cleanup.add(d_Ipatches);
    HANDLE_ERROR(cudaMalloc((void**)&d_Fpatches, sz_all_patch_comp));
    memory_cleanup.add(d_Fpatches);

    int *d_group_start = nullptr;
    int *d_group_size = nullptr;
    HANDLE_ERROR(cudaMalloc((void**)&d_group_start, n_groups * sizeof(int)));
    memory_cleanup.add(d_group_start);
    HANDLE_ERROR(cudaMalloc((void**)&d_group_size, n_groups * sizeof(int)));
    memory_cleanup.add(d_group_size);
    HANDLE_ERROR(cudaMemcpy(d_group_start, group_start.data(), n_groups * sizeof(int), cudaMemcpyHostToDevice));
    HANDLE_ERROR(cudaMemcpy(d_group_size, group_size.data(), n_groups * sizeof(int), cudaMemcpyHostToDevice));

    const bool cache_compatible =
        s_d_cached_Iframes != nullptr &&
        s_cached_device_id == device_id &&
        s_cached_nx == nx && s_cached_ny == ny &&
        s_cached_n_frames == (int)Iframes.size();
    if (cache_compatible) {
        dim3 block(16, 16);
        dim3 grid((patch_w + 15) / 16, (patch_h + 15) / 16, n_groups);
        cropAndGroupPatchKernel<<<grid, block>>>(
            s_d_cached_Iframes,
            d_Ipatches,
            nx, ny,
            x_start, y_start,
            patch_w, patch_h,
            d_group_start, d_group_size,
            n_groups
        );
        HANDLE_ERROR(cudaGetLastError());
    } else {
        // Fallback: sum on host across groups and copy to d_Ipatches
        const size_t patch_pixels = (size_t)patch_h * patch_w;
        std::vector<float> h_grouped((size_t)n_groups * patch_pixels, 0.0f);
        for (int igroup = 0; igroup < n_groups; igroup++) {
            float *grp_ptr = h_grouped.data() + (size_t)igroup * patch_pixels;
            for (int iframe = group_start[igroup]; iframe < group_start[igroup] + group_size[igroup]; iframe++) {
                for (int py = 0; py < patch_h; py++) {
                    for (int px = 0; px < patch_w; px++) {
                        grp_ptr[py * patch_w + px] += DIRECT_A2D_ELEM(Iframes[iframe](), y_start + py, x_start + px);
                    }
                }
            }
        }
        HANDLE_ERROR(cudaMemcpy(d_Ipatches, h_grouped.data(), sz_all_patch_real, cudaMemcpyHostToDevice));
    }

    // Batched cuFFT 2D R2C across n_groups
    cufftHandle plan_batched;
    CufftPlanCleanup plan_cleanup;
    int n[2] = {patch_h, patch_w};
    CUFFT_CHECK(cufftPlanMany(&plan_batched, 2, n, NULL, 1, patch_h * patch_w,
                              NULL, 1, patch_h * patch_nfx, CUFFT_R2C, n_groups));
    plan_cleanup.take(plan_batched);

    CUFFT_CHECK(cufftExecR2C(plan_batched, (cufftReal*)d_Ipatches, d_Fpatches));

    // Scale by 1 / (patch_w * patch_h) to match NewFFT FwdOnly normalization
    const float inv_patch_size = 1.0f / ((float)patch_w * patch_h);
    const size_t total_comp_elems = (size_t)n_groups * patch_h * patch_nfx;
    const int block = 256;
    const int grid = (int)((total_comp_elems + block - 1) / block);
    scaleComplexKernel<<<grid, block>>>(d_Fpatches, total_comp_elems, inv_patch_size);
    HANDLE_ERROR(cudaGetLastError());

    // Copy to host Fpatches
    Fpatches.resize(n_groups);
    for (int igroup = 0; igroup < n_groups; igroup++) {
        Fpatches[igroup].resizeNoCp(2, 1, patch_h, patch_nfx);
        cufftComplex *src_ptr = d_Fpatches + (size_t)igroup * patch_h * patch_nfx;
        HANDLE_ERROR(cudaMemcpy(MULTIDIM_ARRAY(Fpatches[igroup]), src_ptr, sz_patch_comp, cudaMemcpyDeviceToHost));
    }

    return true;
}
