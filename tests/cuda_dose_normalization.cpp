// Native exact-byte oracle against the frozen pre-prototype CUDA kernels.
// Original formulas below are deliberately independent of the new plane helper.
// Returned-code faults are test-only, not physically poisoned GPU contexts.
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_failure_state.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

__global__ void computeDoseNormalizationKernel(float*, int, int, int, float, float,
                                               float, const float*, int);
__global__ void applyDoseWeightKernel(float2*, int, int, int, float, float, float,
                                     const float*, int, int, const float*);

// Dose weighting kernel implementing Grant & Grigorieff (2015) model
__global__ void originalDoseWeightKernel(
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
__global__ void originalPolynomialKernel(
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
__global__ void originalDirectKernel(
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

namespace {
enum Fault { NONE, ALLOCATION, LAUNCH, COMPLETION, CLEANUP, LAUNCH_LATE_FATAL };
bool active = false, fired = false;
Fault fault = NONE;
int allocations = 0, frees = 0, launch_checks = 0, syncs = 0, execs = 0, frame_copies = 0;
int plan_creates = 0, plan_destroys = 0;
cufftHandle executed_plan = 0;
bool observe_session_plans = false;
std::vector<cufftHandle> session_created, session_destroyed;
void *plane = nullptr;
size_t plane_bytes = 0;
bool plane_freed = false;
std::set<void*> buffers;
std::set<cudaEvent_t> events;
std::set<cufftHandle> plans;
std::string violation;
void require(bool condition, const char *message) {
    if (!condition) throw std::runtime_error(message);
}
void gpu(cudaError_t code, const char *message) { require(code == cudaSuccess, message); }
void fft(cufftResult code, const char *message) { require(code == CUFFT_SUCCESS, message); }
void arm(Fault selected = NONE) {
    fault = selected; fired = plane_freed = false; plane = nullptr; plane_bytes = 0;
    allocations = frees = launch_checks = syncs = execs = frame_copies = 0;
    plan_creates = plan_destroys = 0; executed_plan = 0;
    violation.clear(); active = true;
}
void empty() {
    require(buffers.empty() && events.empty() && plans.empty() && violation.empty(),
            "dose reconstruction leaked or double-released owned resources");
}
}
extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cudaError_t __real_cudaGetLastError();
cudaError_t __real_cudaEventSynchronize(cudaEvent_t);
cudaError_t __real_cudaEventCreate(cudaEvent_t*);
cudaError_t __real_cudaEventDestroy(cudaEvent_t);
cudaError_t __real_cudaMemcpy(void*, const void*, size_t, cudaMemcpyKind);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftDestroy(cufftHandle);
cufftResult __real_cufftExecC2R(cufftHandle, cufftComplex*, cufftReal*);
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active && ++allocations == 5 && fault == ALLOCATION) {
        *ptr = nullptr; fired = true; return cudaErrorMemoryAllocation;
    }
    const auto status = __real_cudaMalloc(ptr, bytes);
    if (active && status == cudaSuccess) {
        buffers.insert(*ptr);
        if (allocations == 5) { plane = *ptr; plane_bytes = bytes; }
    }
    return status;
}
cudaError_t __wrap_cudaFree(void *ptr) {
    const auto status = __real_cudaFree(ptr);
    if (active && ptr && status == cudaSuccess) {
        ++frees;
        if (!buffers.erase(ptr)) violation = "double release";
        if (ptr == plane) plane_freed = true;
        if ((fault == CLEANUP && ptr == plane) || (fault == LAUNCH_LATE_FATAL && frees == 1)) {
            fired = true; (void)__real_cudaGetLastError(); return cudaErrorIllegalAddress;
        }
    }
    return status;
}
cudaError_t __wrap_cudaGetLastError() {
    const auto status = __real_cudaGetLastError();
    if (active && ++launch_checks == 1 && (fault == LAUNCH || fault == LAUNCH_LATE_FATAL)) {
        fired = true; return cudaErrorMemoryAllocation;
    }
    return status;
}
cudaError_t __wrap_cudaEventSynchronize(cudaEvent_t event) {
    const auto status = __real_cudaEventSynchronize(event);
    if (active && ++syncs == 1 && fault == COMPLETION && status == cudaSuccess) {
        fired = true; (void)__real_cudaGetLastError(); return cudaErrorIllegalAddress;
    }
    return status;
}
cudaError_t __wrap_cudaEventCreate(cudaEvent_t *event) {
    const auto status = __real_cudaEventCreate(event);
    if (active && status == cudaSuccess) events.insert(*event);
    return status;
}
cudaError_t __wrap_cudaEventDestroy(cudaEvent_t event) {
    const auto status = __real_cudaEventDestroy(event);
    if (active && status == cudaSuccess && !events.erase(event)) violation = "double event release";
    return status;
}
cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t bytes, cudaMemcpyKind kind) {
    if (active && kind == cudaMemcpyDeviceToDevice) {
        ++frame_copies;
        if (syncs == 0) violation = "dose frame consumed before checked normalization completion";
    }
    return __real_cudaMemcpy(dst, src, bytes, kind);
}
cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    const auto status = __real_cufftCreate(plan);
    if (active && status == CUFFT_SUCCESS) { plans.insert(*plan); ++plan_creates; }
    if (observe_session_plans && status == CUFFT_SUCCESS) session_created.push_back(*plan);
    return status;
}
cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const auto status = __real_cufftDestroy(plan);
    if (active && status == CUFFT_SUCCESS) { ++plan_destroys; if (!plans.erase(plan)) violation = "double plan release"; }
    if (observe_session_plans && status == CUFFT_SUCCESS) session_destroyed.push_back(plan);
    return status;
}
cufftResult __wrap_cufftExecC2R(cufftHandle plan, cufftComplex *in, cufftReal *out) {
    if (active) { ++execs; executed_plan = plan; }
    return __real_cufftExecC2R(plan, in, out);
}
}
namespace {
struct Input {
    int nx, ny, count;
    RFLOAT apix;
    std::vector<RFLOAT> doses;
    std::vector<cufftComplex> values;
};
Input inputFor(int nx, int ny, int count, int variant, RFLOAT apix) {
    Input in{nx, ny, count, apix, std::vector<RFLOAT>(count),
             std::vector<cufftComplex>((size_t)(nx/2+1)*ny*count)};
    for (int j = 0; j < count; ++j) {
        // Include positive/negative zero and irregular finite cumulative values.
        in.doses[j] = variant == 0 ? (j % 2 ? -0.0 : 0.0) :
            (RFLOAT)(j * .37 + (j % 5) * .19 + variant * .23);
    }
    unsigned state = 123u + variant;
    for (auto &value : in.values) {
        state = 1664525u*state+1013904223u;
        value.x = (float)((int)(state&65535u)-32768)/4096.0f;
        state = 1664525u*state+1013904223u;
        value.y = (float)((int)(state&65535u)-32768)/4096.0f;
    }
    const size_t tile = (size_t)(nx/2+1)*ny;
    for (int j = 0; j < count; ++j) {
        if (variant == 0 || (variant == 1 && j%2 == 1)) {
            in.values[j*tile].x = j%2 ? -0.0f : 0.0f;
            in.values[j*tile].y = variant == 0 && j%2 ? -0.0f : 0.0f;
        } else {
            // Nonzero real/imaginary DC powers the original 1/sqrt(F) rule;
            // all-zero DC alone cannot discriminate a missing normalization.
            in.values[j*tile].x = 1.25f + (float)j*.01f;
            in.values[j*tile].y = -.375f;
        }
    }
    return in;
}
ThirdOrderPolynomialModel polynomial() {
    ThirdOrderPolynomialModel model;
    model.coeffX.resize(18); model.coeffY.resize(18);
    for (int k = 0; k < 18; ++k) {
        const RFLOAT factor = k%3 == 0 ? 0.0007 : k%3 == 1 ? 0.0000008 : 0.000000001;
        model.coeffX(k) = (k%2 ? -1 : 1)*factor;
        model.coeffY(k) = (k%2 ? 1 : -1)*factor*.7;
    }
    return model;
}
void coefficients(const ThirdOrderPolynomialModel &model, int iframe, float *x, float *y) {
    const float z = (float)iframe, z2 = z*z, z3 = z*z2;
    for (int i = 0; i < 6; ++i) {
        const int c = 3*i;
        x[i] = (float)(model.coeffX(c)*z + model.coeffX(c+1)*z2 + model.coeffX(c+2)*z3);
        y[i] = (float)(model.coeffY(c)*z + model.coeffY(c+1)*z2 + model.coeffY(c+2)*z3);
    }
}
std::vector<float> oracle(const Input &in, const ThirdOrderPolynomialModel *model) {
    const int nfx = in.nx/2+1;
    const size_t tile = (size_t)nfx*in.ny, pixels = (size_t)in.nx*in.ny;
    float2 *frame = nullptr; float *real = nullptr, *sum = nullptr, *doses = nullptr;
    gpu(cudaMalloc(&frame, tile*sizeof(float2)), "oracle Fourier allocation");
    gpu(cudaMalloc(&real, pixels*sizeof(float)), "oracle real allocation");
    gpu(cudaMalloc(&sum, pixels*sizeof(float)), "oracle sum allocation");
    gpu(cudaMalloc(&doses, in.count*sizeof(float)), "oracle doses allocation");
    std::vector<float> hd(in.doses.begin(), in.doses.end());
    gpu(cudaMemcpy(doses, hd.data(), hd.size()*sizeof(float), cudaMemcpyHostToDevice), "oracle doses upload");
    gpu(cudaMemset(sum, 0, pixels*sizeof(float)), "oracle sum reset");
    cufftHandle plan; int n[2] = {in.ny, in.nx}; size_t work = 0;
    fft(cufftCreate(&plan), "oracle plan creation");
    fft(cufftMakePlanMany(plan, 2, n, nullptr, 1, 0, nullptr, 1, 0, CUFFT_C2R, 1, &work), "oracle plan setup");
    const dim3 block(16,16), grid((nfx+15)/16,(in.ny+15)/16);
    const dim3 real_grid((in.nx+15)/16,(in.ny+15)/16);
    const float nx2 = (float)(nfx-1)*(float)(nfx-1)*4.0f;
    const float ny2 = (float)in.ny*(float)in.ny;
    for (int j = 0; j < in.count; ++j) {
        gpu(cudaMemcpy(frame, in.values.data()+j*tile, tile*sizeof(float2), cudaMemcpyHostToDevice), "oracle frame upload");
        originalDoseWeightKernel<<<grid,block>>>(frame,nfx,in.ny,in.ny/2,nx2,ny2,(float)in.apix,doses,in.count,j);
        gpu(cudaGetLastError(), "oracle dose launch"); gpu(cudaDeviceSynchronize(), "oracle dose completion");
        fft(cufftExecC2R(plan,(cufftComplex*)frame,real), "oracle inverse FFT");
        gpu(cudaDeviceSynchronize(), "oracle inverse completion");
        if (model) {
            float x[6], y[6]; coefficients(*model,j,x,y);
            originalPolynomialKernel<<<real_grid,block>>>(sum,nullptr,real,in.nx,in.ny,
                x[0],x[1],x[2],x[3],x[4],x[5],y[0],y[1],y[2],y[3],y[4],y[5]);
        } else {
            originalDirectKernel<<<(pixels+255)/256,256>>>(sum,nullptr,real,pixels);
        }
        gpu(cudaGetLastError(), "oracle accumulate launch"); gpu(cudaDeviceSynchronize(), "oracle accumulate completion");
    }
    std::vector<float> output(pixels);
    gpu(cudaMemcpy(output.data(),sum,pixels*sizeof(float),cudaMemcpyDeviceToHost), "oracle result download");
    fft(cufftDestroy(plan), "oracle plan release");
    gpu(cudaFree(frame), "oracle frame release"); gpu(cudaFree(real), "oracle real release");
    gpu(cudaFree(sum), "oracle sum release"); gpu(cudaFree(doses), "oracle dose release");
    return output;
}
void exactFourier(const Input &in) {
    const int nfx = in.nx/2+1;
    const size_t tile = (size_t)nfx*in.ny;
    float2 *current = nullptr, *old = nullptr; float *denom = nullptr, *doses = nullptr;
    gpu(cudaMalloc(&current,tile*sizeof(float2)), "weighted Fourier allocation");
    gpu(cudaMalloc(&old,tile*sizeof(float2)), "original Fourier allocation");
    gpu(cudaMalloc(&denom,tile*sizeof(float)), "denominator allocation");
    gpu(cudaMalloc(&doses,in.count*sizeof(float)), "dose allocation");
    std::vector<float> hd(in.doses.begin(),in.doses.end());
    gpu(cudaMemcpy(doses,hd.data(),hd.size()*sizeof(float),cudaMemcpyHostToDevice), "dose upload");
    const dim3 block(16,16), grid((nfx+15)/16,(in.ny+15)/16);
    const float nx2 = (float)(nfx-1)*(float)(nfx-1)*4.0f, ny2 = (float)in.ny*(float)in.ny;
    computeDoseNormalizationKernel<<<grid,block>>>(denom,nfx,in.ny,in.ny/2,nx2,ny2,(float)in.apix,doses,in.count);
    gpu(cudaGetLastError(), "normalization launch"); gpu(cudaDeviceSynchronize(), "normalization completion");
    std::vector<float2> a(tile), b(tile);
    for (int j = 0; j < in.count; ++j) {
        gpu(cudaMemcpy(current,in.values.data()+j*tile,tile*sizeof(float2),cudaMemcpyHostToDevice), "candidate Fourier upload");
        gpu(cudaMemcpy(old,in.values.data()+j*tile,tile*sizeof(float2),cudaMemcpyHostToDevice), "original Fourier upload");
        applyDoseWeightKernel<<<grid,block>>>(current,nfx,in.ny,in.ny/2,nx2,ny2,(float)in.apix,doses,in.count,j,denom);
        gpu(cudaGetLastError(), "candidate Fourier dose launch"); gpu(cudaDeviceSynchronize(), "candidate Fourier completion");
        originalDoseWeightKernel<<<grid,block>>>(old,nfx,in.ny,in.ny/2,nx2,ny2,(float)in.apix,doses,in.count,j);
        gpu(cudaGetLastError(), "original Fourier dose launch"); gpu(cudaDeviceSynchronize(), "original Fourier completion");
        gpu(cudaMemcpy(a.data(),current,tile*sizeof(float2),cudaMemcpyDeviceToHost), "candidate Fourier download");
        gpu(cudaMemcpy(b.data(),old,tile*sizeof(float2),cudaMemcpyDeviceToHost), "original Fourier download");
        require(std::memcmp(a.data(),b.data(),tile*sizeof(float2)) == 0,
                "dose-normalized Fourier bytes differ from frozen original kernel");
    }
    gpu(cudaFree(current), "candidate Fourier release"); gpu(cudaFree(old), "original Fourier release");
    gpu(cudaFree(denom), "denominator release"); gpu(cudaFree(doses), "doses release");
}
bool actual(const Input &in, Image<float> &output, CudaFailureState &failure, std::string &log) {
    const bool armed = active; active = false;
    cufftComplex *resident = nullptr;
    gpu(cudaMalloc(&resident,in.values.size()*sizeof(cufftComplex)), "resident input allocation");
    gpu(cudaMemcpy(resident,in.values.data(),in.values.size()*sizeof(cufftComplex),cudaMemcpyHostToDevice), "resident input upload");
    output().resize(in.ny,in.nx);
    for (size_t i = 0; i < (size_t)in.ny*in.nx; ++i) output().data[i] = -12345.0f;
    std::ostringstream stream; active = armed;
    const bool ok = cudaDoseWeightAndInterpolateDevice(resident,output,in.nx,in.ny,in.count,in.doses,in.apix,
                                                     nullptr,0,stream,&failure);
    log = stream.str(); active = false; gpu(__real_cudaFree(resident), "resident release"); active = armed;
    return ok;
}
void exactCases() {
    const auto model = polynomial(); int cases = 0, weighted_frames = 0;
    for (int count : {1,8,24,80,160}) for (int variant : {0,1,2,3,4}) {
        const Input in = inputFor(variant == 1 ? 35 : 32,variant == 2 ? 29 : 24,count,variant,
                                  variant == 2 || variant == 4 ? 2.73 : 1.12);
        active = false; exactFourier(in); weighted_frames += count;
        const size_t bytes = (size_t)in.nx*in.ny*sizeof(float);
        for (bool poly : {false,true}) {
            const auto expected = oracle(in,poly ? &model : nullptr);
            cufftComplex *resident = nullptr;
            gpu(cudaMalloc(&resident,in.values.size()*sizeof(cufftComplex)), "exact resident allocation");
            gpu(cudaMemcpy(resident,in.values.data(),in.values.size()*sizeof(cufftComplex),cudaMemcpyHostToDevice), "exact resident upload");
            Image<float> output; output().resize(in.ny,in.nx);
            CudaFailureState failure; std::ostringstream log; arm();
            const bool ok = cudaDoseWeightAndInterpolateDevice(resident,output,in.nx,in.ny,in.count,in.doses,in.apix,
                                                              poly ? &model : nullptr,0,log,&failure);
            require(ok && !failure.hasFailed(), "healthy dose reconstruction returned failure");
            require(allocations == 5 && plane_bytes == (size_t)(in.nx/2+1)*in.ny*sizeof(float) && plane_freed,
                    "reconstruction denominator plane allocation/ownership wrong");
            require(violation.empty(), violation.c_str());
            require(launch_checks == 1+2*count && syncs == 1+3*count+1 && execs == count && frame_copies == count,
                    "dose precompute/per-frame launch or boundary count changed");
            empty(); active = false;
            require(std::memcmp(output().data,expected.data(),bytes) == 0,
                    "dose reconstruction pixels differ from frozen original frame loop");
            gpu(__real_cudaFree(resident), "exact resident release"); ++cases;
        }
    }
    std::cout << "PASS: " << cases << " exact null/polynomial reconstructions; " << weighted_frames
              << " exact weighted Fourier frames; consecutive changed dose/apix/geometry calls\n";
}
void borrowedCase(int nx, int ny, bool poly, Fault selected = NONE) {
    const Input in = inputFor(nx,ny,8,1,1.12);
    const auto model = polynomial();
    active = false;
    const auto expected = oracle(in,poly ? &model : nullptr);
    session_created.clear(); session_destroyed.clear(); observe_session_plans = true;
    std::ostringstream log;
    CudaMovieSession session(in.nx,in.ny,in.count,0,log);
    require(session.initialize(), "borrowed test session initialization failed");
    require(session_created.size() == 2, "session did not create exactly global R2C/C2R pair");
    const cufftHandle c2r = session_created.back();
    gpu(cudaMemcpy(session.getDeviceFourierFrames(),in.values.data(),in.values.size()*sizeof(cufftComplex),
                   cudaMemcpyHostToDevice), "borrowed resident upload");
    Image<float> output; output().resize(in.ny,in.nx); output().initConstant(-12345.0f);
    arm(selected);
    const bool ok = session.reconstructDoseWeighted(output,in.doses,in.apix,poly ? &model : nullptr);
    require(plan_creates == 0 && plan_destroys == 0,
            "resident reconstruction created/destroyed a plan instead of borrowing session owner");
    require(violation.empty(), violation.c_str()); empty();
    if (selected == NONE) {
        require(ok && !session.getFailureState().hasFailed() && execs == in.count && executed_plan == c2r,
                "resident reconstruction did not execute the actual session C2R plan");
        require(std::memcmp(output().data,expected.data(),expected.size()*sizeof(float)) == 0,
                "borrowed C2R changed dose reconstruction pixels");
    } else {
        require(!ok && fired && session.getFailureState().hasFailed(), "borrowed reconstruction fault did not refuse success");
        require(session.getFailureState().firstError() == cudaErrorMemoryAllocation,
                "borrowed failure lost first recoverable cause");
        require(session.getFailureState().isPoisoned() == (selected == LAUNCH_LATE_FATAL),
                "borrowed cleanup lost fatal retirement state");
    }
    active = false;
    std::vector<cufftComplex> after(in.values.size());
    gpu(cudaMemcpy(after.data(),session.getDeviceFourierFrames(),after.size()*sizeof(cufftComplex),
                   cudaMemcpyDeviceToHost), "borrowed resident preservation read");
    require(std::memcmp(after.data(),in.values.data(),after.size()*sizeof(cufftComplex)) == 0,
            "dose C2R aliased/destroyed resident Fourier input");
    const size_t before_retirement = session_destroyed.size();
    require(before_retirement == 0, "borrower destroyed the session plan owner");
    if (selected == LAUNCH_LATE_FATAL) {
        arm();
        require(!session.reconstructDoseWeighted(output,in.doses,in.apix,nullptr) && execs == 0 && allocations == 0,
                "fatal borrowed cleanup permitted another CUDA reconstruction");
        empty(); active = false;
    } else {
        // A real transform after borrow/refusal powers ownership: accidentally
        // destroying the loan in helper cleanup makes this owner reuse fail.
        // A separately allocated output stays aligned for odd widths. The
        // existing multi-frame inverse method has a distinct odd output-stride
        // restriction; it is not the ownership contract this test exercises.
        float *owner_output = nullptr;
        gpu(cudaMalloc(&owner_output, (size_t)in.nx*in.ny*sizeof(float)), "owner output allocation");
        fft(cufftExecC2R(c2r,session.getDeviceFourierFrames(),owner_output),
            "session C2R owner unusable after borrowed call");
        gpu(cudaDeviceSynchronize(), "owner C2R completion");
        gpu(cudaFree(owner_output), "owner output release");
        require(session_destroyed.empty(), "borrower retired session plan during reuse");
    }
    session.release();
    require(session_destroyed.size() == 2 &&
            std::set<cufftHandle>(session_destroyed.begin(),session_destroyed.end()) ==
            std::set<cufftHandle>(session_created.begin(),session_created.end()),
            "session owner did not destroy each global plan exactly once");
    observe_session_plans = false;
    std::cout << "PASS borrowed session C2R " << nx << 'x' << ny << " polynomial=" << poly
              << " fault=" << selected << "; no extra plans, resident input preserved, owner checked\n";
}
void borrowedCases() {
    const std::pair<int,int> geometries[] = {{32,24},{35,29}};
    for (bool poly : {false,true}) for (const auto &geometry : geometries)
        borrowedCase(geometry.first,geometry.second,poly);
    borrowedCase(32,24,false,LAUNCH);
    // Keep the sticky returned-code fatal case last in this separate process.
    borrowedCase(32,24,false,LAUNCH_LATE_FATAL);
}
void faultCase(Fault selected) {
    const Input in = inputFor(32,24,8,1,1.12);
    CudaFailureState failure; Image<float> output; std::string log; arm(selected);
    const bool ok = actual(in,output,failure,log);
    require(!ok && fired && failure.hasFailed(), "dose fault did not refuse reconstruction success");
    if (selected == ALLOCATION) {
        require(allocations == 5 && frees == 4 && launch_checks == 0 && execs == 0,
                "fifth plane allocation fault escaped cleanup or entered frame loop");
        require(failure.firstError() == cudaErrorMemoryAllocation, "plane allocation original cause lost");
    } else if (selected == LAUNCH || selected == LAUNCH_LATE_FATAL) {
        require(launch_checks == 1 && syncs == 0 && execs == 0 && frame_copies == 0,
                "precompute launch fault permitted denominator consumption");
        require(failure.firstError() == cudaErrorMemoryAllocation, "precompute launch original cause lost");
    } else if (selected == COMPLETION) {
        require(syncs == 1 && launch_checks == 1 && execs == 0 && frame_copies == 0,
                "precompute completion fault permitted denominator consumption");
        require(failure.firstError() == cudaErrorIllegalAddress && failure.isPoisoned(),
                "precompute completion cleared-slot fatal lost");
    } else {
        require(plane_freed && frees == 5 && execs == in.count && failure.isPoisoned(),
                "checked plane cleanup fatal permitted success or leaked owners");
    }
    if (selected != ALLOCATION) require(plane_freed && frees == 5, "new denominator plane was not released");
    if (selected == LAUNCH_LATE_FATAL)
        require(failure.firstError() == cudaErrorMemoryAllocation && failure.fatalError() == cudaErrorIllegalAddress,
                "late cleanup fatal masked by original precompute launch cause");
    if (selected != CLEANUP) for (size_t i = 0; i < (size_t)in.nx*in.ny; ++i)
        require(output().data[i] == -12345.0f, "failed precompute altered host reconstruction output");
    require(__real_cudaGetLastError() == cudaSuccess, "fault injection left uncleared runtime slot");
    empty(); active = false;
    std::cout << "PASS: selected actual-path dose fault refused success and released all owners\n";
}
}
int main(int argc, char **argv) {
    std::string selected = "all";
    if (argc == 3 && std::string(argv[1]) == "--case") selected = argv[2];
    else if (argc != 1) { std::cerr << "Usage: --case exact|borrowed|allocation|launch|completion|cleanup|late-fatal\n"; return 1; }
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 required\n"; return 1;
    }
    try {
        bool known = selected == "all";
        if (selected == "borrowed") { known = true; borrowedCases(); }
        if (selected == "all" || selected == "exact") { known = true; exactCases(); }
        const std::pair<const char*,Fault> cases[] = {{"allocation",ALLOCATION},{"launch",LAUNCH},
            {"completion",COMPLETION},{"cleanup",CLEANUP},{"late-fatal",LAUNCH_LATE_FATAL}};
        for (const auto &entry : cases) if (selected == "all" || selected == entry.first) {
            known = true; faultCase(entry.second);
        }
        require(known,"unknown selector"); empty();
    } catch (const std::exception &e) { std::cerr << "FAIL: " << e.what() << '\n'; return 1; }
      catch (RelionError &e) { std::cerr << "FAIL: unexpected production exception: " << e << '\n'; return 1; }
    std::cout << "PASS: exact reconstruction-scoped dose normalization controls (injected codes, not poisoned hardware)\n";
    return 0;
}
