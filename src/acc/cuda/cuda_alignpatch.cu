#ifdef _CUDA_ENABLED

#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_settings.h"
#include "src/error.h"
#include "src/acc/cuda/cuda_scoped_resources.h"
#include "src/stage_profile.h"

#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <vector>
#include <cstring>
#include <algorithm>

#define CUFFT_CHECK(cmd) do { \
    cufftResult err = (cmd); \
    if (err != CUFFT_SUCCESS) { \
        REPORT_ERROR("cuFFT error: code " + integerToString(err)); \
    } \
} while (0)

// Issue #69. Every error macro in this translation unit leaves by exception:
// HANDLE_ERROR here is the cuda_settings.h variant, i.e. CRITICAL(ERRGPUKERN) ->
// REPORT_ERROR -> throw RelionError, and CUFFT_CHECK throws directly. run() catches
// RelionError per movie and continues with the remaining movies, so any resource this
// file owns and does not unwind is leaked for the lifetime of the process, once per
// failing global alignment and once per failing patch.
//
// The owners live in cuda_scoped_resources.h with statically proved capacities, so the
// hot patch loop performs no host heap allocation for them (PR107 review P2).

namespace {
// Proved by counting the cold workspace initialization below: eight cudaMalloc,
// eight cudaEventCreate and one plan. The fixed owners check every registration.
const int ALIGN_MAX_BUFFERS = 8;
const int ALIGN_MAX_EVENTS  = 8;
} // namespace

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
const RFLOAT PATCH_TOLERANCE = 0.5;

struct PatchCcfGeometry {
    int ccf_nx, ccf_ny, search_range;
    RFLOAT ccf_scale_x, ccf_scale_y;
};

// Shared by the per-patch and batched entry points, so the two cannot drift.
PatchCcfGeometry patchCcfGeometry(int pnx, int pny, RFLOAT scaled_B, RFLOAT ccf_downsample) {
    int search_range = 50;
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
    const RFLOAT ccf_scale_x = (RFLOAT)pnx / ccf_nx;
    const RFLOAT ccf_scale_y = (RFLOAT)pny / ccf_ny;
    search_range /= (ccf_scale_x > ccf_scale_y) ? ccf_scale_x : ccf_scale_y;
    if (search_range * 2 + 1 > ccf_nx) search_range = ccf_nx / 2 - 1;
    if (search_range * 2 + 1 > ccf_ny) search_range = ccf_ny / 2 - 1;
    return {ccf_nx, ccf_ny, search_range, ccf_scale_x, ccf_scale_y};
}

// The host half of one iteration, shared by both entry points: re-reference the
// candidate shifts to frame 0, accumulate them and form the phase shifts.
// Returns the RMSD the convergence test and the log use.
RFLOAT updatePatchShifts(float *cur_x, float *cur_y, float *shift_x, float *shift_y,
                         std::vector<RFLOAT> &xshifts, std::vector<RFLOAT> &yshifts,
                         int n_frames, int pnx, int pny) {
    RFLOAT x_sumsq = 0.0, y_sumsq = 0.0;
    for (int iframe = n_frames - 1; iframe >= 0; iframe--) {
        cur_x[iframe] -= cur_x[0];
        cur_y[iframe] -= cur_y[0];
        x_sumsq += (RFLOAT)cur_x[iframe] * cur_x[iframe];
        y_sumsq += (RFLOAT)cur_y[iframe] * cur_y[iframe];
    }
    cur_x[0] = 0.0f;
    cur_y[0] = 0.0f;

    for (int iframe = 0; iframe < n_frames; iframe++) {
        xshifts[iframe] += cur_x[iframe];
        yshifts[iframe] += cur_y[iframe];
        shift_x[iframe] = -cur_x[iframe] / (float)pnx;
        shift_y[iframe] = -cur_y[iframe] / (float)pny;
    }
    return std::sqrt((x_sumsq + y_sumsq) / n_frames);
}
} // namespace

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
    int local_posx = 0;
    int local_posy = 0;

    for (int idx = threadIdx.x; idx < total_pts; idx += blockDim.x) {
        int sy = idx / range_len - search_range;
        int sx = idx % range_len - search_range;
        int iy = (sy < 0) ? ccf_ny + sy : sy;
        int ix = (sx < 0) ? ccf_nx + sx : sx;
        float val = d_Iccs[frame_offset + iy * ccf_nx + ix];
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

// The implementation is allocated once per movie, never per local patch. The
// existing fixed-capacity owners are the only release mechanism, including partial
// initialization and exception paths; their failure sink is the movie's state.
struct PatchAlignmentWorkspace::Impl {
    struct Key {
        int device, pnx, pny, n_frames, ccf_nx, ccf_ny, search_range;
        RFLOAT scaled_B, downsample;
        bool equals(const Key &other) const {
            return device == other.device && pnx == other.pnx && pny == other.pny &&
                n_frames == other.n_frames && ccf_nx == other.ccf_nx &&
                ccf_ny == other.ccf_ny && search_range == other.search_range &&
                std::memcmp(&scaled_B, &other.scaled_B, sizeof(RFLOAT)) == 0 &&
                std::memcmp(&downsample, &other.downsample, sizeof(RFLOAT)) == 0;
        }
    } key = {};
    CudaFailureState local_failure;
    CudaFailureState *failure;
    mc_cuda::ScopedDeviceMemory<ALIGN_MAX_BUFFERS> memory;
    mc_cuda::ScopedCudaEvents<ALIGN_MAX_EVENTS> events;
    mc_cuda::ScopedCufftPlan plan;
    bool valid = false;
    // The ephemeral entry point reports completion only after checked teardown.
    bool defer_completion = false;
    int resource_device = -1;
    float2 *d_Fref = nullptr, *d_Fccs = nullptr;
    float *d_weight = nullptr, *d_Iccs = nullptr;
    float *d_cur_xshifts = nullptr, *d_cur_yshifts = nullptr;
    float *d_shiftx = nullptr, *d_shifty = nullptr;
    cudaEvent_t ev_start_total = nullptr, ev_stop_total = nullptr;
    cudaEvent_t ev_start_kernel = nullptr, ev_stop_kernel = nullptr;
    cudaEvent_t ev_start_cufft = nullptr, ev_stop_cufft = nullptr;
    cudaEvent_t ev_start_d2h = nullptr, ev_stop_d2h = nullptr;
    cufftHandle plan_c2r = 0;
    size_t cufft_work_size = 0;
    explicit Impl(CudaFailureState *state)
        : failure(state ? state : &local_failure), memory(failure),
          events(failure), plan(failure) {}

    bool release() noexcept {
        valid = false; // No exception/failure can leave an old key published.
        cudaError_t device_error = cudaSuccess;
        // A changed-device call must destroy events/plans in their owning context.
        // On the usual session path the current device is already this device.
        if (resource_device >= 0) {
            device_error = cudaSetDevice(resource_device);
            failure->record(device_error, "patch workspace release device", __LINE__);
        }
        const cufftResult plan_error = plan.releaseAll();
        const cudaError_t memory_error = memory.releaseAll();
        const cudaError_t event_error = events.releaseAll();
        resource_device = -1;
        d_Fref = d_Fccs = nullptr;
        d_weight = d_Iccs = d_cur_xshifts = d_cur_yshifts = d_shiftx = d_shifty = nullptr;
        ev_start_total = ev_stop_total = ev_start_kernel = ev_stop_kernel = nullptr;
        ev_start_cufft = ev_stop_cufft = ev_start_d2h = ev_stop_d2h = nullptr;
        plan_c2r = 0;
        cufft_work_size = 0;
        return device_error == cudaSuccess && plan_error == CUFFT_SUCCESS &&
            memory_error == cudaSuccess && event_error == cudaSuccess;
    }
};

PatchAlignmentWorkspace::PatchAlignmentWorkspace(CudaFailureState *failure)
    : impl_(new Impl(failure)) {}
PatchAlignmentWorkspace::~PatchAlignmentWorkspace() { (void)release(); }
bool PatchAlignmentWorkspace::release() noexcept { return impl_->release(); }
bool PatchAlignmentWorkspace::isValid() const { return impl_->valid; }

// Preserve consumed statuses before the existing handlers throw. A later clean
// last-error slot cannot permit a retry after a fatal initialization/execution fault.
#define ALIGN_CUDA(cmd) do { \
    const cudaError_t err = (cmd); \
    w.failure->record(err, #cmd, __LINE__); \
    HandleError(err, __FILE__, __LINE__); \
} while (0)
#define ALIGN_LAUNCH(cmd) do { \
    const cudaError_t err = (cmd); \
    w.failure->record(err, #cmd, __LINE__); \
    LaunchHandleError(err, __FILE__, __LINE__); \
} while (0)
#define ALIGN_CUFFT(cmd) do { \
    const cufftResult err = (cmd); \
    w.failure->recordCufft(err, #cmd, __LINE__); \
    if (err != CUFFT_SUCCESS) { \
        w.failure->record(cudaPeekAtLastError(), #cmd, __LINE__); \
        REPORT_ERROR("cuFFT error: code " + integerToString(err)); \
    } \
} while (0)

bool cudaAlignPatchDeviceWithWorkspace(
    PatchAlignmentWorkspace &workspace,
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
    auto &w = *workspace.impl_;
    if (w.failure->isPoisoned())
        REPORT_ERROR("Fatal CUDA state refuses patch workspace reuse");
    try {
    int dev_count = 0;
    cudaError_t count_err = cudaGetDeviceCount(&dev_count);
    w.failure->record(count_err, "patch alignment device count", __LINE__);
    if (count_err != cudaSuccess || dev_count == 0) {
        REPORT_ERROR("No CUDA capable devices found");
    }
    if (device_id < 0 || device_id >= dev_count) {
        REPORT_ERROR_STR("Invalid CUDA device ID: " << device_id << " (system has " << dev_count << " devices)");
    }
    ALIGN_CUDA(cudaSetDevice(device_id));

    if (pny % 2 == 1 || pnx % 2 == 1) {
        REPORT_ERROR("Patch size must be even");
    }
    const RFLOAT tolerance = PATCH_TOLERANCE;

    const PatchCcfGeometry geo = patchCcfGeometry(pnx, pny, scaled_B, ccf_downsample);
    const int ccf_nx = geo.ccf_nx, ccf_ny = geo.ccf_ny, search_range = geo.search_range;
    const int ccf_nfx = ccf_nx / 2 + 1, ccf_nfy = ccf_ny;
    const int ccf_nfy_half = ccf_ny / 2;
    const RFLOAT ccf_scale_x = geo.ccf_scale_x, ccf_scale_y = geo.ccf_scale_y;

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

    const PatchAlignmentWorkspace::Impl::Key requested = {device_id, pnx, pny, n_frames, ccf_nx,
        ccf_ny, search_range, scaled_B, ccf_downsample};
    const bool setup_required = !w.valid || !w.key.equals(requested);
    if (setup_required) {
        if (!w.release()) REPORT_ERROR("CUDA patch workspace replacement cleanup failed");
        // release() may have switched to the old resource device.
        ALIGN_CUDA(cudaSetDevice(device_id));
        w.resource_device = device_id;
        ALIGN_CUDA(cudaEventCreate(&w.ev_start_total)); w.events.add(w.ev_start_total);
        ALIGN_CUDA(cudaEventCreate(&w.ev_stop_total)); w.events.add(w.ev_stop_total);
        ALIGN_CUDA(cudaEventCreate(&w.ev_start_kernel)); w.events.add(w.ev_start_kernel);
        ALIGN_CUDA(cudaEventCreate(&w.ev_stop_kernel)); w.events.add(w.ev_stop_kernel);
        ALIGN_CUDA(cudaEventCreate(&w.ev_start_cufft)); w.events.add(w.ev_start_cufft);
        ALIGN_CUDA(cudaEventCreate(&w.ev_stop_cufft)); w.events.add(w.ev_stop_cufft);
        ALIGN_CUDA(cudaEventCreate(&w.ev_start_d2h)); w.events.add(w.ev_start_d2h);
        ALIGN_CUDA(cudaEventCreate(&w.ev_stop_d2h)); w.events.add(w.ev_stop_d2h);
    }
    // Includes initial allocations, planning and weights, as the predecessor did.
    // Reused calls omit those operations, so this is per-call telemetry, not a
    // setup-exclusive performance comparison. Complete unprofiled wall is the gate.
    ALIGN_CUDA(cudaEventRecord(w.ev_start_total));
    if (setup_required) {
        ALIGN_CUDA(cudaMalloc(&w.d_Fref, sz_fref)); w.memory.add(w.d_Fref);
        ALIGN_CUDA(cudaMalloc(&w.d_weight, sz_weight)); w.memory.add(w.d_weight);
        ALIGN_CUDA(cudaMalloc(&w.d_Fccs, sz_fccs)); w.memory.add(w.d_Fccs);
        ALIGN_CUDA(cudaMalloc(&w.d_Iccs, sz_iccs)); w.memory.add(w.d_Iccs);
        ALIGN_CUDA(cudaMalloc(&w.d_cur_xshifts, sz_shifts)); w.memory.add(w.d_cur_xshifts);
        ALIGN_CUDA(cudaMalloc(&w.d_cur_yshifts, sz_shifts)); w.memory.add(w.d_cur_yshifts);
        ALIGN_CUDA(cudaMalloc(&w.d_shiftx, sz_shifts)); w.memory.add(w.d_shiftx);
        ALIGN_CUDA(cudaMalloc(&w.d_shifty, sz_shifts)); w.memory.add(w.d_shifty);
        int n[2] = {ccf_ny, ccf_nx};
        ALIGN_CUFFT(cufftCreate(&w.plan_c2r)); w.plan.take(w.plan_c2r);
        size_t plan_work_bytes = 0;
        ALIGN_CUFFT(cufftMakePlanMany(w.plan_c2r, 2, n, NULL, 1,
            ccf_nfy * ccf_nfx, NULL, 1, ccf_ny * ccf_nx, CUFFT_C2R,
            n_frames, &plan_work_bytes));
        ALIGN_CUFFT(cufftGetSize(w.plan_c2r, &w.cufft_work_size));
        dim3 blockWeights(16, 16);
        dim3 gridWeights((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
        computeWeightsKernel<<<gridWeights, blockWeights>>>(w.d_weight,
            ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, (float)scaled_B);
        ALIGN_LAUNCH(cudaGetLastError());
    }
    // Borrow aliases; only the workspace's scoped owners can release them.
    float2 *d_Fref = w.d_Fref, *d_Fccs = w.d_Fccs;
    float *d_weight = w.d_weight, *d_Iccs = w.d_Iccs;
    float *d_cur_xshifts = w.d_cur_xshifts, *d_cur_yshifts = w.d_cur_yshifts;
    float *d_shiftx = w.d_shiftx, *d_shifty = w.d_shifty;
    const cudaEvent_t ev_start_total = w.ev_start_total, ev_stop_total = w.ev_stop_total;
    const cudaEvent_t ev_start_kernel = w.ev_start_kernel, ev_stop_kernel = w.ev_stop_kernel;
    const cudaEvent_t ev_start_cufft = w.ev_start_cufft, ev_stop_cufft = w.ev_stop_cufft;
    const cudaEvent_t ev_start_d2h = w.ev_start_d2h, ev_stop_d2h = w.ev_stop_d2h;
    const cufftHandle plan_c2r = w.plan_c2r;
    const size_t cufft_work_size = w.cufft_work_size;
    const size_t total_vram_allocated = sz_fframes + sz_fref + sz_weight +
        sz_fccs + sz_iccs + 4 * sz_shifts + cufft_work_size;

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
    // Device event timing exists only for the log. Each pair forces the host to
    // wait for the GPU; under --profile the timings are kept, otherwise every
    // telemetry-only wait is skipped. The blocking shift download below remains
    // the one synchronisation the convergence loop actually depends on.
    const bool timed = StageProfile::instance().deviceTiming();
    float accumulated_kernel_ms = 0.0f;
    float accumulated_cufft_ms = 0.0f;
    float accumulated_d2h_ms = 0.0f;

    for (int iter = 1; iter <= max_iter; iter++) {
        // 1. Reference computation
        if (timed) ALIGN_CUDA(cudaEventRecord(ev_start_kernel));
        computeReferenceKernel<<<gridRef, blockRef>>>(d_Fframes, d_Fref, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        ALIGN_LAUNCH(cudaGetLastError());

        // 2. CCF computation
        computeCCFKernel<<<gridCCF, blockCCF>>>(d_Fframes, d_Fref, d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
        ALIGN_LAUNCH(cudaGetLastError());
        if (timed) {
            ALIGN_CUDA(cudaEventRecord(ev_stop_kernel));
            ALIGN_CUDA(cudaEventSynchronize(ev_stop_kernel));
            float k1_ms = 0.0f;
            ALIGN_CUDA(cudaEventElapsedTime(&k1_ms, ev_start_kernel, ev_stop_kernel));
            accumulated_kernel_ms += k1_ms;
        }

        // 3. Batched cuFFT C2R
        if (timed) ALIGN_CUDA(cudaEventRecord(ev_start_cufft));
        ALIGN_CUFFT(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));
        if (timed) {
            ALIGN_CUDA(cudaEventRecord(ev_stop_cufft));
            ALIGN_CUDA(cudaEventSynchronize(ev_stop_cufft));
            float iter_cufft_ms = 0.0f;
            ALIGN_CUDA(cudaEventElapsedTime(&iter_cufft_ms, ev_start_cufft, ev_stop_cufft));
            accumulated_cufft_ms += iter_cufft_ms;
        }

        // 4. Peak finding + subpixel quadratic interpolation
        if (timed) ALIGN_CUDA(cudaEventRecord(ev_start_kernel));
        findPeakAndInterpolateKernel<<<n_frames, 256>>>(
            d_Iccs, d_cur_xshifts, d_cur_yshifts,
            ccf_nx, ccf_ny, search_range,
            (float)ccf_scale_x, (float)ccf_scale_y, n_frames
        );
        ALIGN_LAUNCH(cudaGetLastError());
        if (timed) {
            ALIGN_CUDA(cudaEventRecord(ev_stop_kernel));
            ALIGN_CUDA(cudaEventSynchronize(ev_stop_kernel));
            float k2_ms = 0.0f;
            ALIGN_CUDA(cudaEventElapsedTime(&k2_ms, ev_start_kernel, ev_stop_kernel));
            accumulated_kernel_ms += k2_ms;
        }

        // Copy candidate shifts back to host
        // The blocking copies on stream 0 are the loop's one real wait: they
        // complete only after every kernel above, and the host needs the result.
        if (timed) ALIGN_CUDA(cudaEventRecord(ev_start_d2h));
        ALIGN_CUDA(cudaMemcpy(h_cur_xshifts.data(), d_cur_xshifts, sz_shifts, cudaMemcpyDeviceToHost));
        ALIGN_CUDA(cudaMemcpy(h_cur_yshifts.data(), d_cur_yshifts, sz_shifts, cudaMemcpyDeviceToHost));
        if (timed) {
            ALIGN_CUDA(cudaEventRecord(ev_stop_d2h));
            ALIGN_CUDA(cudaEventSynchronize(ev_stop_d2h));
            float iter_d2h_ms = 0.0f;
            ALIGN_CUDA(cudaEventElapsedTime(&iter_d2h_ms, ev_start_d2h, ev_stop_d2h));
            accumulated_d2h_ms += iter_d2h_ms;
        }

        const RFLOAT rmsd = updatePatchShifts(h_cur_xshifts.data(), h_cur_yshifts.data(),
            h_shiftx.data(), h_shifty.data(), xshifts, yshifts, n_frames, pnx, pny);

        // Apply Fourier phase shifts on GPU
        if (n_frames > 1) {
            ALIGN_CUDA(cudaMemcpy(d_shiftx, h_shiftx.data(), sz_shifts, cudaMemcpyHostToDevice));
            ALIGN_CUDA(cudaMemcpy(d_shifty, h_shifty.data(), sz_shifts, cudaMemcpyHostToDevice));
            if (timed) ALIGN_CUDA(cudaEventRecord(ev_start_kernel));
            fourierShiftKernel<<<gridShift, blockShift>>>(d_Fframes, d_shiftx, d_shifty, nfx, nfy, nfy_half, n_frames);
            ALIGN_LAUNCH(cudaGetLastError());
            if (timed) {
                ALIGN_CUDA(cudaEventRecord(ev_stop_kernel));
                ALIGN_CUDA(cudaEventSynchronize(ev_stop_kernel));
                float shift_kernel_ms = 0.0f;
                ALIGN_CUDA(cudaEventElapsedTime(&shift_kernel_ms, ev_start_kernel, ev_stop_kernel));
                accumulated_kernel_ms += shift_kernel_ms;
            }
        }

        logfile << " Iteration " << iter << ": RMSD = " << rmsd << " px" << std::endl;

        if (rmsd < tolerance) {
            converged = true;
            break;
        }
    }

    ALIGN_CUDA(cudaEventRecord(ev_stop_total));
    ALIGN_CUDA(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    ALIGN_CUDA(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    // Profile logging
    const char *stage_name = is_global ? "Global Alignment" : "Patch Alignment";
    logfile << " [CUDA " << stage_name << " Profile]" << std::endl;
    if (timed) {
        logfile << "   Host-to-Device transfer time: 0.00 ms (Resident VRAM)" << std::endl;
        logfile << "   Custom kernel execution time: " << std::fixed << std::setprecision(2) << accumulated_kernel_ms << " ms" << std::endl;
        logfile << "   cuFFT execution time:         " << std::fixed << std::setprecision(2) << accumulated_cufft_ms << " ms" << std::endl;
        logfile << "   Device-to-Host transfer time: " << std::fixed << std::setprecision(2) << accumulated_d2h_ms << " ms" << std::endl;
    } else {
        // Not printed as 0.00: unmeasured is not zero. --profile restores them.
        logfile << "   Per-kernel timing:            not measured (enable with --profile)" << std::endl;
    }
    logfile << "   Total GPU alignment time:     " << std::fixed << std::setprecision(2) << total_ms << " ms" << std::endl;
    logfile << "   Buffer VRAM:                  " << std::fixed << std::setprecision(2) << ((total_vram_allocated - cufft_work_size) / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   cuFFT workspace VRAM:         " << std::fixed << std::setprecision(2) << (cufft_work_size / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   Peak GPU memory allocated:    " << std::fixed << std::setprecision(2) << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;

    // Publish only after all initialization and the complete alignment succeeded.
    // The input-dependent scratch is overwritten by the next call's unchanged
    // kernels; the weights are invariant under the full key above.
    w.key = requested;
    w.valid = true;

    if (!w.defer_completion)
        logfile << " [CUDA " << stage_name << "] completed; converged="
                << (converged ? "yes" : "no") << std::endl;
    return converged;
    } catch (...) {
        // Failure invalidates the cache before cleanup. Any late fatal cleanup
        // status remains latched in the same failure state as the original error.
        (void)workspace.release();
        throw;
    }
}

// ---------------------------------------------------------------------------
// Batched local patch alignment (docs/batched_patch_alignment.md).
//
// Exactness is by construction: every patch runs the same kernels, launch
// geometry and batch-n_frames C2R plan configuration as the per-patch path, on
// its own slot, in the same order. Only the host waits change: one shift
// download and one phase-shift upload per iteration for all active patches.
// Measured on cuFFT 11.3 (A100): a single plan over K*n_frames transforms is
// not bit-identical to batch n_frames (256x256, n=4, K=25: all outputs differ),
// whereas the batch-n_frames plan executed at slot offsets was identical in all
// 13 geometries tried. Slots are still padded to the allocation alignment so
// each transform sees the same pointer alignment as a fresh allocation.

namespace {
// Seven cudaMalloc and two events in reserve(); no add() in any loop.
const int BATCH_MAX_BUFFERS = 7;
const int BATCH_MAX_EVENTS = 2;
const size_t SLOT_ALIGN_BYTES = 512;

size_t paddedElements(size_t elements, size_t element_bytes) {
    const size_t per = SLOT_ALIGN_BYTES / element_bytes;
    return (elements + per - 1) / per * per;
}

struct BatchSlots {
    size_t fframes, fref, fccs, iccs; // elements per patch, padded
};

BatchSlots batchSlots(int n_frames, int pnx, int pny, const PatchCcfGeometry &geo) {
    const size_t nfx = pnx / 2 + 1, ccf_nfx = geo.ccf_nx / 2 + 1;
    BatchSlots s;
    s.fframes = paddedElements((size_t)n_frames * pny * nfx, sizeof(float2));
    s.fref = paddedElements((size_t)geo.ccf_ny * ccf_nfx, sizeof(float2));
    s.fccs = paddedElements((size_t)n_frames * geo.ccf_ny * ccf_nfx, sizeof(float2));
    s.iccs = paddedElements((size_t)n_frames * geo.ccf_ny * geo.ccf_nx, sizeof(float));
    return s;
}
} // namespace

struct BatchedPatchAlignmentWorkspace::Impl {
    CudaFailureState local_failure;
    CudaFailureState *failure;
    mc_cuda::ScopedDeviceMemory<BATCH_MAX_BUFFERS> memory;
    mc_cuda::ScopedCudaEvents<BATCH_MAX_EVENTS> events;
    mc_cuda::ScopedCufftPlan plan;
    bool valid = false;
    int resource_device = -1;
    int capacity = 0, device = -1, pnx = 0, pny = 0, n_frames = 0;
    RFLOAT scaled_B = 0, downsample = 0;
    PatchCcfGeometry geo = {};
    BatchSlots slots = {};
    float2 *d_Fpatches = nullptr, *d_Fref = nullptr, *d_Fccs = nullptr;
    float *d_weight = nullptr, *d_Iccs = nullptr;
    float *d_cur = nullptr, *d_shift = nullptr; // [x of all patches | y of all patches]
    cudaEvent_t ev_start = nullptr, ev_stop = nullptr;
    cufftHandle plan_c2r = 0;
    size_t cufft_work_size = 0, buffer_bytes = 0;
    std::vector<float> h_cur, h_shift;
    explicit Impl(CudaFailureState *state)
        : failure(state ? state : &local_failure), memory(failure),
          events(failure), plan(failure) {}

    bool release() noexcept {
        valid = false;
        cudaError_t device_error = cudaSuccess;
        if (resource_device >= 0) {
            device_error = cudaSetDevice(resource_device);
            failure->record(device_error, "batched patch workspace release device", __LINE__);
        }
        const cufftResult plan_error = plan.releaseAll();
        const cudaError_t memory_error = memory.releaseAll();
        const cudaError_t event_error = events.releaseAll();
        resource_device = -1;
        capacity = 0;
        d_Fpatches = d_Fref = d_Fccs = nullptr;
        d_weight = d_Iccs = d_cur = d_shift = nullptr;
        ev_start = ev_stop = nullptr;
        plan_c2r = 0;
        cufft_work_size = buffer_bytes = 0;
        return device_error == cudaSuccess && plan_error == CUFFT_SUCCESS &&
            memory_error == cudaSuccess && event_error == cudaSuccess;
    }

    // A declined reservation is not a failure the per-patch path would have had:
    // clear the slot the declined call set, keep nothing, record nothing. A
    // poisoning code is never declined.
    bool decline() {
        const cudaError_t pending = cudaPeekAtLastError();
        if (cudaErrorPoisonsContext(pending)) {
            failure->record(pending, "batched patch workspace reserve", __LINE__);
            REPORT_ERROR("Fatal CUDA error reserving the batched patch workspace");
        }
        (void)cudaGetLastError();
        if (!release()) REPORT_ERROR("CUDA batched patch workspace cleanup failed");
        return false;
    }
    // True on success; false when the allocation was declined for lack of memory.
    template <class T> bool allocate(T *&slot, size_t bytes) {
        void *fresh = nullptr;
        const cudaError_t err = cudaMalloc(&fresh, bytes);
        if (err == cudaSuccess) {
            memory.add(fresh);
            slot = static_cast<T*>(fresh);
            buffer_bytes += bytes;
            return true;
        }
        if (cudaErrorPoisonsContext(err)) {
            failure->record(err, "batched patch workspace cudaMalloc", __LINE__);
            REPORT_ERROR("Fatal CUDA error allocating the batched patch workspace");
        }
        return false;
    }
};

BatchedPatchAlignmentWorkspace::BatchedPatchAlignmentWorkspace(CudaFailureState *failure)
    : impl_(new Impl(failure)) {}
BatchedPatchAlignmentWorkspace::~BatchedPatchAlignmentWorkspace() { (void)release(); }
bool BatchedPatchAlignmentWorkspace::release() noexcept { return impl_->release(); }
bool BatchedPatchAlignmentWorkspace::isValid() const { return impl_->valid; }
int BatchedPatchAlignmentWorkspace::capacity() const { return impl_->valid ? impl_->capacity : 0; }
size_t BatchedPatchAlignmentWorkspace::bufferBytes() const { return impl_->buffer_bytes; }
size_t BatchedPatchAlignmentWorkspace::cufftWorkBytes() const { return impl_->cufft_work_size; }
cufftComplex *BatchedPatchAlignmentWorkspace::patchSlot(int index) const {
    const Impl &w = *impl_;
    if (!w.valid || index < 0 || index >= w.capacity)
        REPORT_ERROR("Batched patch slot outside the reservation");
    return (cufftComplex*)(w.d_Fpatches + (size_t)index * w.slots.fframes);
}

size_t BatchedPatchAlignmentWorkspace::bytesPerPatch(int n_frames, int pnx, int pny,
    RFLOAT scaled_B, RFLOAT ccf_downsample) {
    const BatchSlots s = batchSlots(n_frames, pnx, pny,
        patchCcfGeometry(pnx, pny, scaled_B, ccf_downsample));
    return (s.fframes + s.fref + s.fccs) * sizeof(float2) + s.iccs * sizeof(float) +
        4 * (size_t)n_frames * sizeof(float);
}

int choosePatchBatchChunk(int n_patches, size_t bytes_per_patch, size_t free_bytes,
                          size_t total_bytes, int cap) {
    if (n_patches < 1 || cap < 1 || bytes_per_patch == 0) return 0;
    const size_t headroom = std::max<size_t>((size_t)1 << 30, total_bytes / 10);
    if (free_bytes <= headroom) return 0;
    const size_t fit = (free_bytes - headroom) / bytes_per_patch;
    return (int)std::min<size_t>(fit, (size_t)std::min(n_patches, cap));
}

bool BatchedPatchAlignmentWorkspace::reserve(int capacity, int n_frames, int pnx, int pny,
    RFLOAT scaled_B, RFLOAT ccf_downsample, int device_id) {
    Impl &w = *impl_;
    if (w.failure->isPoisoned())
        REPORT_ERROR("Fatal CUDA state refuses batched patch workspace");
    if (capacity < 1 || n_frames < 1) REPORT_ERROR("Invalid batched patch reservation");
    if (pny % 2 == 1 || pnx % 2 == 1) REPORT_ERROR("Patch size must be even");
    if (!w.release()) REPORT_ERROR("CUDA batched patch workspace replacement cleanup failed");
    try {
        ALIGN_CUDA(cudaSetDevice(device_id));
        w.resource_device = device_id;
        w.geo = patchCcfGeometry(pnx, pny, scaled_B, ccf_downsample);
        w.slots = batchSlots(n_frames, pnx, pny, w.geo);
        const size_t K = capacity, n = n_frames;
        const int ccf_nx = w.geo.ccf_nx, ccf_ny = w.geo.ccf_ny;
        const int ccf_nfx = ccf_nx / 2 + 1, ccf_nfy = ccf_ny;
        if (!w.allocate(w.d_Fpatches, K * w.slots.fframes * sizeof(float2)) ||
            !w.allocate(w.d_Fref, K * w.slots.fref * sizeof(float2)) ||
            !w.allocate(w.d_weight, (size_t)ccf_nfy * ccf_nfx * sizeof(float)) ||
            !w.allocate(w.d_Fccs, K * w.slots.fccs * sizeof(float2)) ||
            !w.allocate(w.d_Iccs, K * w.slots.iccs * sizeof(float)) ||
            !w.allocate(w.d_cur, 2 * K * n * sizeof(float)) ||
            !w.allocate(w.d_shift, 2 * K * n * sizeof(float)))
            return w.decline();
        if (cudaEventCreate(&w.ev_start) != cudaSuccess) return w.decline();
        w.events.add(w.ev_start);
        if (cudaEventCreate(&w.ev_stop) != cudaSuccess) return w.decline();
        w.events.add(w.ev_stop);
        // The per-patch plan configuration, unchanged.
        if (cufftCreate(&w.plan_c2r) != CUFFT_SUCCESS) return w.decline();
        w.plan.take(w.plan_c2r);
        int dims[2] = {ccf_ny, ccf_nx};
        size_t plan_work_bytes = 0;
        if (cufftMakePlanMany(w.plan_c2r, 2, dims, NULL, 1, ccf_nfy * ccf_nfx, NULL, 1,
                ccf_ny * ccf_nx, CUFFT_C2R, n_frames, &plan_work_bytes) != CUFFT_SUCCESS ||
            cufftGetSize(w.plan_c2r, &w.cufft_work_size) != CUFFT_SUCCESS)
            return w.decline();
        dim3 blockWeights(16, 16);
        dim3 gridWeights((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
        computeWeightsKernel<<<gridWeights, blockWeights>>>(w.d_weight,
            ccf_nfx, ccf_nfy, ccf_ny / 2, pnx / 2 + 1, pny, (float)scaled_B);
        ALIGN_LAUNCH(cudaGetLastError());
        w.h_cur.assign(2 * K * n, 0.0f);
        w.h_shift.assign(2 * K * n, 0.0f);
        w.capacity = capacity; w.device = device_id; w.pnx = pnx; w.pny = pny;
        w.n_frames = n_frames; w.scaled_B = scaled_B; w.downsample = ccf_downsample;
        w.valid = true;
        return true;
    } catch (...) {
        (void)release();
        throw;
    }
}

void cudaAlignPatchBatchDevice(
    BatchedPatchAlignmentWorkspace &workspace,
    const int n_patches, const int n_frames, const int pnx, const int pny,
    const RFLOAT scaled_B, std::vector<RFLOAT> *xshifts, std::vector<RFLOAT> *yshifts,
    const int max_iter, const RFLOAT ccf_downsample, const int device_id,
    PatchBatchLog *logs)
{
    auto &w = *workspace.impl_;
    if (w.failure->isPoisoned())
        REPORT_ERROR("Fatal CUDA state refuses batched patch alignment");
    if (!w.valid || w.device != device_id || w.pnx != pnx || w.pny != pny ||
        w.n_frames != n_frames || n_patches < 1 || n_patches > w.capacity ||
        std::memcmp(&w.scaled_B, &scaled_B, sizeof(RFLOAT)) != 0 ||
        std::memcmp(&w.downsample, &ccf_downsample, sizeof(RFLOAT)) != 0)
        REPORT_ERROR("Batched patch alignment without a matching reservation");
    try {
    ALIGN_CUDA(cudaSetDevice(device_id));
    const RFLOAT tolerance = PATCH_TOLERANCE;
    const int ccf_nx = w.geo.ccf_nx, ccf_ny = w.geo.ccf_ny, search_range = w.geo.search_range;
    const int ccf_nfx = ccf_nx / 2 + 1, ccf_nfy = ccf_ny;
    const int ccf_nfy_half = ccf_ny / 2;
    const int nfx = pnx / 2 + 1, nfy = pny;
    const int nfy_half = nfy / 2;
    const size_t n = n_frames, K = w.capacity;

    dim3 blockRef(16, 16);
    dim3 gridRef((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
    dim3 blockCCF(16, 16, 1);
    dim3 gridCCF((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16, n_frames);
    dim3 blockShift(16, 16, 1);
    dim3 gridShift((nfx + 15) / 16, (nfy + 15) / 16, n_frames - 1);

    float *d_cur_x = w.d_cur, *d_cur_y = w.d_cur + K * n;
    float *d_shift_x = w.d_shift, *d_shift_y = w.d_shift + K * n;
    float *h_cur_x = w.h_cur.data(), *h_cur_y = w.h_cur.data() + K * n;
    float *h_shift_x = w.h_shift.data(), *h_shift_y = w.h_shift.data() + K * n;
    const size_t sz_all_shifts = 2 * K * n * sizeof(float);

    std::vector<int> active(n_patches);
    for (int p = 0; p < n_patches; p++) {
        active[p] = p;
        logs[p] = PatchBatchLog();
    }
    ALIGN_CUDA(cudaEventRecord(w.ev_start));
    for (int iter = 1; iter <= max_iter && !active.empty(); iter++) {
        for (const int p : active) {
            float2 *d_Fframes = w.d_Fpatches + p * w.slots.fframes;
            float2 *d_Fref = w.d_Fref + p * w.slots.fref;
            float2 *d_Fccs = w.d_Fccs + p * w.slots.fccs;
            float *d_Iccs = w.d_Iccs + p * w.slots.iccs;
            computeReferenceKernel<<<gridRef, blockRef>>>(d_Fframes, d_Fref, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
            ALIGN_LAUNCH(cudaGetLastError());
            computeCCFKernel<<<gridCCF, blockCCF>>>(d_Fframes, d_Fref, w.d_weight, d_Fccs, ccf_nfx, ccf_nfy, ccf_nfy_half, nfx, nfy, n_frames);
            ALIGN_LAUNCH(cudaGetLastError());
            ALIGN_CUFFT(cufftExecC2R(w.plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));
            findPeakAndInterpolateKernel<<<n_frames, 256>>>(
                d_Iccs, d_cur_x + p * n, d_cur_y + p * n,
                ccf_nx, ccf_ny, search_range,
                (float)w.geo.ccf_scale_x, (float)w.geo.ccf_scale_y, n_frames
            );
            ALIGN_LAUNCH(cudaGetLastError());
        }
        // The iteration's one wait, for every active patch at once.
        ALIGN_CUDA(cudaMemcpy(w.h_cur.data(), w.d_cur, sz_all_shifts, cudaMemcpyDeviceToHost));
        for (const int p : active) {
            const RFLOAT rmsd = updatePatchShifts(h_cur_x + p * n, h_cur_y + p * n,
                h_shift_x + p * n, h_shift_y + p * n, xshifts[p], yshifts[p],
                n_frames, pnx, pny);
            logs[p].rmsd.push_back(rmsd);
            if (rmsd < tolerance) logs[p].converged = true;
        }
        // Patches converging now are still shifted: the per-patch loop applies
        // the shift before its convergence test.
        if (n_frames > 1) {
            ALIGN_CUDA(cudaMemcpy(w.d_shift, w.h_shift.data(), sz_all_shifts, cudaMemcpyHostToDevice));
            for (int j = 0; j < (int)active.size(); ++j) { const int p = active[j];
                fourierShiftKernel<<<gridShift, blockShift>>>(w.d_Fpatches + p * w.slots.fframes,
                    d_shift_x + p * n, d_shift_y + p * n, nfx, nfy, nfy_half, n_frames);
                ALIGN_LAUNCH(cudaGetLastError());
            }
        }
        // Retired patches are never launched or shifted again.
        active.erase(std::remove_if(active.begin(), active.end(),
            [&](int p) { return logs[p].converged; }), active.end());
    }
    ALIGN_CUDA(cudaEventRecord(w.ev_stop));
    ALIGN_CUDA(cudaEventSynchronize(w.ev_stop));
    float total_ms = 0.0f;
    ALIGN_CUDA(cudaEventElapsedTime(&total_ms, w.ev_start, w.ev_stop));
    for (int p = 0; p < n_patches; p++) {
        logs[p].chunk_patches = n_patches;
        logs[p].chunk_gpu_ms = total_ms;
        logs[p].buffer_bytes = w.buffer_bytes;
        logs[p].cufft_work_bytes = w.cufft_work_size;
    }
    } catch (...) {
        (void)workspace.release();
        throw;
    }
}

void writePatchBatchLog(std::ostream &logfile, const PatchBatchLog &log) {
    for (size_t k = 0; k < log.rmsd.size(); k++)
        logfile << " Iteration " << (int)(k + 1) << ": RMSD = " << log.rmsd[k] << " px" << std::endl;
    const size_t total = log.buffer_bytes + log.cufft_work_bytes;
    logfile << " [CUDA Patch Alignment Profile]" << std::endl;
    logfile << "   Batched alignment:            " << log.chunk_patches
            << " patches together; time and VRAM below are for all of them" << std::endl;
    logfile << "   Total GPU alignment time:     " << std::fixed << std::setprecision(2) << log.chunk_gpu_ms << " ms" << std::endl;
    logfile << "   Buffer VRAM:                  " << std::fixed << std::setprecision(2) << (log.buffer_bytes / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   cuFFT workspace VRAM:         " << std::fixed << std::setprecision(2) << (log.cufft_work_bytes / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   Peak GPU memory allocated:    " << std::fixed << std::setprecision(2) << (total / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << " [CUDA Patch Alignment] completed; converged="
            << (log.converged ? "yes" : "no") << std::endl;
}

#undef ALIGN_CUDA
#undef ALIGN_LAUNCH
#undef ALIGN_CUFFT

// Keep the existing signature/symbol for global alignment, host fallback and the
// retry interposition ABI. These callers retain the original per-call lifetime.
bool cudaAlignPatchDevice(
    cufftComplex *d_Fframes, const int n_frames, const int pnx, const int pny,
    const RFLOAT scaled_B, std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts, const int max_iter,
    const RFLOAT ccf_downsample, const int device_id, std::ostream &logfile,
    bool is_global)
{
    PatchAlignmentWorkspace workspace;
    workspace.impl_->defer_completion = true;
    const bool converged = cudaAlignPatchDeviceWithWorkspace(workspace, d_Fframes,
        n_frames, pnx, pny, scaled_B, xshifts, yshifts, max_iter,
        ccf_downsample, device_id, logfile, is_global);
    if (!workspace.release()) REPORT_ERROR("CUDA patch alignment cleanup failed");
    const char *stage_name = is_global ? "Global Alignment" : "Patch Alignment";
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

    // Issue #69: this staging buffer is owned by the wrapper, and every step below --
    // the uploads, the device call and the global copyback -- can leave by exception.
    // Register it before the first of them can throw.
    mc_cuda::ScopedDeviceMemory<1> memory_cleanup;
    float2 *d_Fframes = nullptr;
    HANDLE_ERROR(cudaSetDevice(device_id));
    HANDLE_ERROR(cudaMalloc(&d_Fframes, sz_fframes));
    memory_cleanup.add(d_Fframes);
    if (memory_cleanup.overflowed()) {
        REPORT_ERROR("Internal error: CUDA alignment staging registry exceeded its "
                     "fixed capacity; a resource would not have been released");
    }

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

    HANDLE_ERROR(memory_cleanup.releaseAll());
    return converged;
}

#endif // _CUDA_ENABLED
