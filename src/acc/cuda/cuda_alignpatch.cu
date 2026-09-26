#ifdef _CUDA_ENABLED

#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_settings.h"
#include "src/error.h"
#include "src/motioncorr_alignment_weight.h"

#include <cuda_runtime.h>
#include <cufft.h>
#include <cmath>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <vector>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

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
    int n_frames,
    GlobalPeakProbeRecord *d_probe,
    FullPeakRecord *d_full_peaks)
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

        if (d_probe && iframe == d_probe->frame_index) {
            d_probe->peak_x = posx;
            d_probe->peak_y = posy;
            d_probe->peak_value = maxval;
            d_probe->center = maxval;
            d_probe->x_minus = vn_x;
            d_probe->x_plus = vp_x;
            d_probe->y_minus = vn_y;
            d_probe->y_plus = vp_y;
            d_probe->denominator_x = denom_x;
            d_probe->denominator_y = denom_y;
            d_probe->shift_x_unscaled = cur_x;
            d_probe->shift_y_unscaled = cur_y;
            d_probe->shift_x_scaled = cur_x * ccf_scale_x;
            d_probe->shift_y_scaled = cur_y * ccf_scale_y;
            d_probe->x_interpolated = fabsf(denom_x) > EPS;
            d_probe->y_interpolated = fabsf(denom_y) > EPS;
        }

        if (d_full_peaks) {
            FullPeakRecord &r = d_full_peaks[iframe];
            r.value[0] = posx; r.value[1] = posy; r.value[2] = maxval;
            r.value[3] = vn_x; r.value[4] = vp_x;
            r.value[5] = vn_y; r.value[6] = vp_y;
            r.value[7] = denom_x; r.value[8] = denom_y;
            r.value[9] = cur_x; r.value[10] = cur_y;
            r.value[11] = cur_x * ccf_scale_x;
            r.value[12] = cur_y * ccf_scale_y;
            r.value[13] = fabsf(denom_x) > EPS;
            r.value[14] = fabsf(denom_y) > EPS;
            r.value[15] = 0;
        }

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

// This reader is deliberately narrow: it consumes only complete CPU full-trace
// deltas from the same movie, never an arbitrary user supplied trajectory.
struct Issue36CpuTrajectory {
    bool enabled = false;
    std::string directory;
    std::vector<RFLOAT> dx[2], dy[2], total_x, total_y;
};

static std::string readIssue36File(const std::string &path, size_t expected_bytes)
{
    const int fd = open(path.c_str(), O_RDONLY | O_NOFOLLOW);
    struct stat info;
    if (fd < 0 || fstat(fd, &info) != 0 || !S_ISREG(info.st_mode) ||
        info.st_size != (off_t)expected_bytes) {
        if (fd >= 0) close(fd);
        REPORT_ERROR("Invalid or incomplete Issue 36 CPU trajectory file: " + path);
    }
    std::string data(expected_bytes, '\0');
    size_t offset = 0;
    while (offset < expected_bytes) {
        const ssize_t count = read(fd, &data[0] + offset, expected_bytes - offset);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) {
            close(fd);
            REPORT_ERROR("Cannot read Issue 36 CPU trajectory file: " + path);
        }
        offset += (size_t)count;
    }
    if (close(fd) != 0) REPORT_ERROR("Cannot close Issue 36 CPU trajectory file: " + path);
    return data;
}

static Issue36CpuTrajectory readIssue36CpuTrajectory(const std::string &movie,
                                                     int n_frames, int max_iter)
{
    Issue36CpuTrajectory result;
    const char *value = std::getenv("MOTIONCORR_ISSUE36_CPU_GLOBAL_TRACE_DIR");
    if (!value) return result;
    if (!fullTraceEnabled() || !*value || sizeof(RFLOAT) != sizeof(double) ||
        max_iter < 2 || n_frames != 24)
        REPORT_ERROR("Issue 36 trajectory replay requires a nonempty path, double RFLOAT, two iterations and 24 frames");
    struct stat directory_info;
    if (lstat(value, &directory_info) != 0 || !S_ISDIR(directory_info.st_mode))
        REPORT_ERROR("Issue 36 CPU trajectory path must be a real directory");
    const std::string dir(value);
    result.directory = dir;
    const std::string start = "backend=cpu\nmovie=" + movie +
                              "\nformat=motioncorr-full-trace-v1\n";
    if (readIssue36File(dir + "/trace_start", start.size()) != start ||
        readIssue36File(dir + "/trace_complete", 9) != "complete\n")
        REPORT_ERROR("Issue 36 CPU trajectory source is incomplete or belongs to another movie");
    auto read_array = [&](const std::string &key) {
        const size_t bytes = (size_t)n_frames * sizeof(double);
        const std::string meta = "{\"key\":\"" + key + "\",\"dtype\":\"f8\",\"shape\":[" +
                                 integerToString(n_frames) + "],\"bytes\":" +
                                 integerToString(bytes) + ",\"endian\":\"native\"}\n";
        if (readIssue36File(dir + "/" + key + ".json", meta.size()) != meta)
            REPORT_ERROR("Issue 36 CPU trajectory metadata mismatch: " + key);
        const std::string raw = readIssue36File(dir + "/" + key + ".bin", bytes);
        std::vector<RFLOAT> array(n_frames);
        std::memcpy(array.data(), raw.data(), bytes);
        if (array[0] != 0)
            REPORT_ERROR("Issue 36 CPU trajectory frame 0 must be zero: " + key);
        for (RFLOAT v : array)
            if (!std::isfinite(v)) REPORT_ERROR("Nonfinite Issue 36 CPU trajectory: " + key);
        return array;
    };
    for (int i = 0; i < 2; ++i) {
        const std::string prefix = fullTraceKey("g", i + 1, "deltax");
        result.dx[i] = read_array(prefix);
        result.dy[i] = read_array(fullTraceKey("g", i + 1, "deltay"));
    }
    result.total_x = read_array(fullTraceKey("g", 2, "totalx"));
    result.total_y = read_array(fullTraceKey("g", 2, "totaly"));
    for (int f = 0; f < n_frames; ++f) {
        if (result.dx[0][f] + result.dx[1][f] != result.total_x[f] ||
            result.dy[0][f] + result.dy[1][f] != result.total_y[f])
            REPORT_ERROR("Issue 36 CPU trajectory totals disagree with per-iteration deltas");
    }
    for (int i = 0; i < 2; ++i) {
        RFLOAT sumsq = 0;
        for (int f = 0; f < n_frames; ++f)
            sumsq += result.dx[i][f] * result.dx[i][f] +
                     result.dy[i][f] * result.dy[i][f];
        const RFLOAT rmsd = std::sqrt(sumsq / n_frames);
        if ((i == 0 && rmsd < 0.5) || (i == 1 && rmsd >= 0.5))
            REPORT_ERROR("Issue 36 CPU trajectory does not have the expected two-iteration convergence");
    }
    result.enabled = true;
    return result;
}

static void validateIssue36CpuTraceGeometry(const Issue36CpuTrajectory &trajectory,
                                            int nfx, int nfy, int ccf_nfx,
                                            int ccf_nfy, int pnx, int pny)
{
    if (!trajectory.enabled) return;
    if (pnx != 2 * (nfx - 1) || pny != nfy)
        REPORT_ERROR("Issue 36 CPU trajectory geometry differs from current global movie");
    auto check = [&](const std::string &key, int rows, int columns) {
        const int bytes = rows * columns * sizeof(float2);
        const std::string meta = "{\"key\":\"" + key + "\",\"dtype\":\"c8\",\"shape\":[" +
                                 integerToString(rows) + "," + integerToString(columns) +
                                 "],\"bytes\":" + integerToString(bytes) +
                                 ",\"endian\":\"native\"}\n";
        if (readIssue36File(trajectory.directory + "/" + key + ".json", meta.size()) != meta)
            REPORT_ERROR("Issue 36 CPU trajectory source geometry mismatch: " + key);
    };
    check(fullTraceKey("g", 1, "input", 0), nfy, nfx);
    check(fullTraceKey("g", 1, "fref"), ccf_nfy, ccf_nfx);
    check(fullTraceKey("g", 2, "fref"), ccf_nfy, ccf_nfx);
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
    const std::string &movie_identity)
{
    GlobalPeakProbeConfig peak_probe;
    const bool full_trace = fullTraceEnabled();
    const int n_frames = xshifts.size();
    const Issue36CpuTrajectory cpu_trajectory =
        readIssue36CpuTrajectory(movie_identity, n_frames, max_iter);
    if (full_trace && device_id < 0)
        REPORT_ERROR("Full CUDA trace requires an explicit --gpu ordinal");
    readGlobalPeakProbeConfig(peak_probe);
    if (peak_probe.enabled) {
        if (device_id < 0)
            REPORT_ERROR("Global peak CUDA trace requires an explicitly requested GPU ordinal");
        if (peak_probe.frame_index >= (int)xshifts.size() || peak_probe.iteration > max_iter)
            REPORT_ERROR("Global peak trace frame/iteration is outside this alignment pass");
        requireFreshGlobalPeakProbeOutput(peak_probe, "cuda");
    }

    if (device_id >= 0) {
        HANDLE_ERROR(cudaSetDevice(device_id));
    }

    cudaEvent_t ev_start_total, ev_stop_total;
    cudaEvent_t ev_start_h2d, ev_stop_h2d;
    cudaEvent_t ev_start_kernel, ev_stop_kernel;
    cudaEvent_t ev_start_cufft, ev_stop_cufft;
    cudaEvent_t ev_start_d2h, ev_stop_d2h;

    HANDLE_ERROR(cudaEventCreate(&ev_start_total));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_total));
    HANDLE_ERROR(cudaEventCreate(&ev_start_h2d));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_h2d));
    HANDLE_ERROR(cudaEventCreate(&ev_start_kernel));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_kernel));
    HANDLE_ERROR(cudaEventCreate(&ev_start_cufft));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_cufft));
    HANDLE_ERROR(cudaEventCreate(&ev_start_d2h));
    HANDLE_ERROR(cudaEventCreate(&ev_stop_d2h));

    HANDLE_ERROR(cudaEventRecord(ev_start_total));

    if (cpu_trajectory.enabled)
        logfile << " [Issue36 counterfactual: CPU global deltas from "
                << std::getenv("MOTIONCORR_ISSUE36_CPU_GLOBAL_TRACE_DIR") << "]" << std::endl;
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

    const int nfx = XSIZE(Fframes[0]), nfy = YSIZE(Fframes[0]);
    const int nfy_half = nfy / 2;
    validateIssue36CpuTraceGeometry(cpu_trajectory, nfx, nfy, ccf_nfx, ccf_nfy,
                                    pnx, pny);

    // Buffer allocations
    const size_t sz_fframes = (size_t)n_frames * nfy * nfx * sizeof(float2);
    const size_t sz_fref    = (size_t)ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_weight  = (size_t)ccf_nfy * ccf_nfx * sizeof(float);
    const size_t sz_fccs    = (size_t)n_frames * ccf_nfy * ccf_nfx * sizeof(float2);
    const size_t sz_iccs    = (size_t)n_frames * ccf_ny * ccf_nx * sizeof(float);
    const size_t sz_shifts  = (size_t)n_frames * sizeof(float);
    const size_t sz_input_frame = (size_t)nfy * nfx * sizeof(float2);
    const size_t sz_iccs_frame = (size_t)ccf_ny * ccf_nx * sizeof(float);
    if (peak_probe.capture_arrays)
        requireGlobalPeakProbeArrayBudget(peak_probe, "cuda", sz_input_frame,
                                          sz_weight, sz_fref, sz_iccs_frame);

    float2 *d_Fframes = nullptr;
    float2 *d_Fref = nullptr;
    float *d_weight = nullptr;
    float2 *d_Fccs = nullptr;
    float *d_Iccs = nullptr;
    float *d_cur_xshifts = nullptr;
    float *d_cur_yshifts = nullptr;
    float *d_shiftx = nullptr;
    float *d_shifty = nullptr;
    GlobalPeakProbeRecord *d_peak_probe = nullptr;
    FullPeakRecord *d_full_peaks = nullptr;

    HANDLE_ERROR(cudaMalloc(&d_Fframes, sz_fframes));
    HANDLE_ERROR(cudaMalloc(&d_Fref, sz_fref));
    HANDLE_ERROR(cudaMalloc(&d_weight, sz_weight));
    HANDLE_ERROR(cudaMalloc(&d_Fccs, sz_fccs));
    HANDLE_ERROR(cudaMalloc(&d_Iccs, sz_iccs));
    HANDLE_ERROR(cudaMalloc(&d_cur_xshifts, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_cur_yshifts, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_shiftx, sz_shifts));
    HANDLE_ERROR(cudaMalloc(&d_shifty, sz_shifts));
    GlobalPeakProbeRecord h_peak_probe = {};
    if (peak_probe.enabled) {
        h_peak_probe.frame_index = peak_probe.frame_index;
        h_peak_probe.iteration = peak_probe.iteration;
        HANDLE_ERROR(cudaMalloc(&d_peak_probe, sizeof(GlobalPeakProbeRecord)));
        HANDLE_ERROR(cudaMemcpy(d_peak_probe, &h_peak_probe, sizeof(GlobalPeakProbeRecord), cudaMemcpyHostToDevice));
    }
    if (full_trace) HANDLE_ERROR(cudaMalloc(&d_full_peaks, (size_t)n_frames * sizeof(FullPeakRecord)));

    size_t total_vram_allocated = sz_fframes + sz_fref + sz_weight + sz_fccs + sz_iccs + 4 * sz_shifts;

    // Host to Device copy
    HANDLE_ERROR(cudaEventRecord(ev_start_h2d));
    for (int iframe = 0; iframe < n_frames; iframe++) {
        HANDLE_ERROR(cudaMemcpy(
            d_Fframes + (size_t)iframe * nfy * nfx,
            Fframes[iframe].data,
            (size_t)nfy * nfx * sizeof(float2),
            cudaMemcpyHostToDevice
        ));
    }
    HANDLE_ERROR(cudaEventRecord(ev_stop_h2d));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_h2d));

    float h2d_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&h2d_ms, ev_start_h2d, ev_stop_h2d));

    // Initialize cuFFT batched C2R plan
    cufftHandle plan_c2r;
    int n[2] = {ccf_ny, ccf_nx};
    CUFFT_CHECK(cufftPlanMany(&plan_c2r, 2, n, NULL, 1, ccf_nfy * ccf_nfx, NULL, 1, ccf_ny * ccf_nx, CUFFT_C2R, n_frames));
    size_t cufft_work_size = 0;
    CUFFT_CHECK(cufftGetSize(plan_c2r, &cufft_work_size));
    total_vram_allocated += cufft_work_size;

    // Upload the exact host expression used by the CPU alignment path.
    // The original device expf path remains an opt-in counterfactual control.
    const bool legacy_gpu_weight = std::getenv("MOTIONCORR_ISSUE36_LEGACY_GPU_WEIGHT") != nullptr;
    if (legacy_gpu_weight) {
        dim3 blockWeights(16, 16);
        dim3 gridWeights((ccf_nfx + 15) / 16, (ccf_nfy + 15) / 16);
        computeWeightsKernel<<<gridWeights, blockWeights>>>(d_weight, ccf_nfx, ccf_nfy,
                                                              ccf_nfy_half, nfx, nfy,
                                                              (float)scaled_B);
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        logfile << " [Issue36 counterfactual: legacy CUDA expf weight]" << std::endl;
    } else {
        std::vector<float> host_weight(sz_weight / sizeof(float));
        for (int y = 0; y < ccf_nfy; ++y)
            fillMotioncorrAlignmentWeightRow(host_weight.data() + (size_t)y * ccf_nfx,
                                             y, ccf_nfx, ccf_nfy, nfx, nfy, scaled_B);
        HANDLE_ERROR(cudaMemcpy(d_weight, host_weight.data(), sz_weight, cudaMemcpyHostToDevice));
    }
    if (full_trace) {
        std::vector<float> array(sz_weight / sizeof(float));
        HANDLE_ERROR(cudaMemcpy(array.data(), d_weight, sz_weight, cudaMemcpyDeviceToHost));
        fullTraceArray(fullTraceKey("g", 0, "weight"), array.data(), sz_weight, "f4",
                       integerToString(ccf_nfy) + "," + integerToString(ccf_nfx));
    }
    if (peak_probe.capture_arrays) {
        std::vector<float> array(sz_weight / sizeof(float));
        HANDLE_ERROR(cudaMemcpy(array.data(), d_weight, sz_weight, cudaMemcpyDeviceToHost));
        writeGlobalPeakProbeArray(peak_probe, "cuda", "weight", array.data(), sz_weight);
    }

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
    std::vector<float2> full_complex_frame(full_trace ? (size_t)nfy * nfx : 0);
    std::vector<float> full_real_frame(full_trace ? (size_t)ccf_ny * ccf_nx : 0);
    std::vector<FullPeakRecord> full_peaks(full_trace ? n_frames : 0);

    bool converged = false;
    float accumulated_kernel_ms = 0.0f;
    float accumulated_cufft_ms = 0.0f;
    float accumulated_d2h_ms = 0.0f;
    bool peak_trace_written = false;

    for (int iter = 1; iter <= max_iter; iter++) {
        if (full_trace) {
            for (int iframe = 0; iframe < n_frames; ++iframe) {
                HANDLE_ERROR(cudaMemcpy(full_complex_frame.data(), d_Fframes + (size_t)iframe * nfy * nfx,
                                        sz_input_frame, cudaMemcpyDeviceToHost));
                fullTraceArray(fullTraceKey("g", iter, "input", iframe), full_complex_frame.data(),
                               sz_input_frame, "c8", integerToString(nfy) + "," + integerToString(nfx));
            }
        }
        const bool capture_arrays = peak_probe.capture_arrays && iter == peak_probe.iteration;
        if (capture_arrays) {
            std::vector<float2> array(sz_input_frame / sizeof(float2));
            HANDLE_ERROR(cudaMemcpy(array.data(), d_Fframes + (size_t)peak_probe.frame_index * nfy * nfx,
                                    sz_input_frame, cudaMemcpyDeviceToHost));
            writeGlobalPeakProbeArray(peak_probe, "cuda", "input", array.data(), sz_input_frame);
        }
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
        if (full_trace) {
            HANDLE_ERROR(cudaMemcpy(full_complex_frame.data(), d_Fref, sz_fref, cudaMemcpyDeviceToHost));
            fullTraceArray(fullTraceKey("g", iter, "fref"), full_complex_frame.data(), sz_fref,
                           "c8", integerToString(ccf_nfy) + "," + integerToString(ccf_nfx));
            for (int iframe = 0; iframe < n_frames; ++iframe) {
                HANDLE_ERROR(cudaMemcpy(full_complex_frame.data(), d_Fccs + (size_t)iframe * ccf_nfy * ccf_nfx,
                                        sz_fref, cudaMemcpyDeviceToHost));
                fullTraceArray(fullTraceKey("g", iter, "fccs", iframe), full_complex_frame.data(), sz_fref,
                               "c8", integerToString(ccf_nfy) + "," + integerToString(ccf_nfx));
            }
        }
        if (capture_arrays) {
            std::vector<float2> reference(sz_fref / sizeof(float2));
            std::vector<float2> spectrum(sz_fref / sizeof(float2));
            HANDLE_ERROR(cudaMemcpy(reference.data(), d_Fref, sz_fref, cudaMemcpyDeviceToHost));
            HANDLE_ERROR(cudaMemcpy(spectrum.data(), d_Fccs + (size_t)peak_probe.frame_index * ccf_nfy * ccf_nfx,
                                    sz_fref, cudaMemcpyDeviceToHost));
            writeGlobalPeakProbeArray(peak_probe, "cuda", "fref", reference.data(), sz_fref);
            writeGlobalPeakProbeArray(peak_probe, "cuda", "fccs", spectrum.data(), sz_fref);
        }

        // 3. Batched cuFFT C2R (timed separately from custom kernels)
        HANDLE_ERROR(cudaEventRecord(ev_start_cufft));
        CUFFT_CHECK(cufftExecC2R(plan_c2r, (cufftComplex*)d_Fccs, (cufftReal*)d_Iccs));
        HANDLE_ERROR(cudaEventRecord(ev_stop_cufft));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_cufft));
        float iter_cufft_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&iter_cufft_ms, ev_start_cufft, ev_stop_cufft));
        accumulated_cufft_ms += iter_cufft_ms;
        if (full_trace) {
            for (int iframe = 0; iframe < n_frames; ++iframe) {
                HANDLE_ERROR(cudaMemcpy(full_real_frame.data(), d_Iccs + (size_t)iframe * ccf_ny * ccf_nx,
                                        sz_iccs_frame, cudaMemcpyDeviceToHost));
                fullTraceArray(fullTraceKey("g", iter, "iccs", iframe), full_real_frame.data(), sz_iccs_frame,
                               "f4", integerToString(ccf_ny) + "," + integerToString(ccf_nx));
            }
        }
        if (capture_arrays) {
            std::vector<float> image(sz_iccs_frame / sizeof(float));
            HANDLE_ERROR(cudaMemcpy(image.data(), d_Iccs + (size_t)peak_probe.frame_index * ccf_ny * ccf_nx,
                                    sz_iccs_frame, cudaMemcpyDeviceToHost));
            writeGlobalPeakProbeArray(peak_probe, "cuda", "iccs", image.data(), sz_iccs_frame);
        }

        // 4. Peak finding + subpixel quadratic interpolation
        HANDLE_ERROR(cudaEventRecord(ev_start_kernel));
        findPeakAndInterpolateKernel<<<n_frames, 256>>>(
            d_Iccs, d_cur_xshifts, d_cur_yshifts,
            ccf_nx, ccf_ny, search_range,
            (float)ccf_scale_x, (float)ccf_scale_y, n_frames,
            (peak_probe.enabled && iter == peak_probe.iteration) ? d_peak_probe : nullptr,
            full_trace ? d_full_peaks : nullptr
        );
        LAUNCH_HANDLE_ERROR(cudaGetLastError());
        HANDLE_ERROR(cudaEventRecord(ev_stop_kernel));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_kernel));
        float k2_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&k2_ms, ev_start_kernel, ev_stop_kernel));
        accumulated_kernel_ms += k2_ms;

        // Copy shifts back to host
        HANDLE_ERROR(cudaEventRecord(ev_start_d2h));
        HANDLE_ERROR(cudaMemcpy(h_cur_xshifts.data(), d_cur_xshifts, sz_shifts, cudaMemcpyDeviceToHost));
        HANDLE_ERROR(cudaMemcpy(h_cur_yshifts.data(), d_cur_yshifts, sz_shifts, cudaMemcpyDeviceToHost));
        if (full_trace) {
            HANDLE_ERROR(cudaMemcpy(full_peaks.data(), d_full_peaks,
                                    (size_t)n_frames * sizeof(FullPeakRecord), cudaMemcpyDeviceToHost));
            fullTraceArray(fullTraceKey("g", iter, "peaks"), full_peaks.data(),
                           (size_t)n_frames * sizeof(FullPeakRecord), "f8", integerToString(n_frames) + ",16");
            fullTraceArray(fullTraceKey("g", iter, "rawshiftx"), h_cur_xshifts.data(), sz_shifts, "f4", integerToString(n_frames));
            fullTraceArray(fullTraceKey("g", iter, "rawshifty"), h_cur_yshifts.data(), sz_shifts, "f4", integerToString(n_frames));
        }
        if (peak_probe.enabled && iter == peak_probe.iteration) {
            HANDLE_ERROR(cudaMemcpy(&h_peak_probe, d_peak_probe, sizeof(GlobalPeakProbeRecord), cudaMemcpyDeviceToHost));
            h_peak_probe.frame0_shift_x_scaled = h_cur_xshifts[0];
            h_peak_probe.frame0_shift_y_scaled = h_cur_yshifts[0];
            h_peak_probe.frame0_recentered_shift_x = 0.0;
            h_peak_probe.frame0_recentered_shift_y = 0.0;
            h_peak_probe.recentered_shift_x = h_cur_xshifts[peak_probe.frame_index] - h_cur_xshifts[0];
            h_peak_probe.recentered_shift_y = h_cur_yshifts[peak_probe.frame_index] - h_cur_yshifts[0];
            cudaDeviceProp properties;
            int actual_device = -1;
            HANDLE_ERROR(cudaGetDevice(&actual_device));
            HANDLE_ERROR(cudaGetDeviceProperties(&properties, actual_device));
            std::ostringstream device;
            device << "requested ordinal " << device_id << ", resolved CUDA ordinal " << actual_device << ": " << properties.name;
            writeGlobalPeakProbeRecord(peak_probe, "cuda", device.str(), movie_identity, h_peak_probe);
            peak_trace_written = true;
        }
        HANDLE_ERROR(cudaEventRecord(ev_stop_d2h));
        HANDLE_ERROR(cudaEventSynchronize(ev_stop_d2h));
        float iter_d2h_ms = 0.0f;
        HANDLE_ERROR(cudaEventElapsedTime(&iter_d2h_ms, ev_start_d2h, ev_stop_d2h));
        accumulated_d2h_ms += iter_d2h_ms;

        // Keep measured CUDA peaks/raw shifts above, then optionally intervene
        // on the complete per-frame trajectory before shifting Fourier frames.
        RFLOAT x_sumsq = 0.0, y_sumsq = 0.0;
        if (cpu_trajectory.enabled) {
            if (iter > 2) REPORT_ERROR("Issue 36 CPU trajectory source has only two iterations");
            const std::vector<RFLOAT> &dx = cpu_trajectory.dx[iter - 1];
            const std::vector<RFLOAT> &dy = cpu_trajectory.dy[iter - 1];
            std::vector<float> measured_dx = h_cur_xshifts;
            std::vector<float> measured_dy = h_cur_yshifts;
            for (int iframe = n_frames - 1; iframe >= 0; --iframe) {
                measured_dx[iframe] -= measured_dx[0];
                measured_dy[iframe] -= measured_dy[0];
            }
            measured_dx[0] = 0;
            measured_dy[0] = 0;
            fullTraceArray(fullTraceKey("g", iter, "replay_measured_deltax"),
                           measured_dx.data(), sz_shifts, "f4", integerToString(n_frames));
            fullTraceArray(fullTraceKey("g", iter, "replay_measured_deltay"),
                           measured_dy.data(), sz_shifts, "f4", integerToString(n_frames));
            for (int iframe = 0; iframe < n_frames; ++iframe) {
                x_sumsq += dx[iframe] * dx[iframe];
                y_sumsq += dy[iframe] * dy[iframe];
                xshifts[iframe] += dx[iframe];
                yshifts[iframe] += dy[iframe];
                h_shiftx[iframe] = (float)(-dx[iframe] / pnx);
                h_shifty[iframe] = (float)(-dy[iframe] / pny);
            }
            if (iter == 2) {
                for (int iframe = 0; iframe < n_frames; ++iframe) {
                    if (xshifts[iframe] != cpu_trajectory.total_x[iframe] ||
                        yshifts[iframe] != cpu_trajectory.total_y[iframe])
                        REPORT_ERROR("Issue 36 replayed global totals differ from CPU trace");
                    xshifts[iframe] = cpu_trajectory.total_x[iframe];
                    yshifts[iframe] = cpu_trajectory.total_y[iframe];
                }
            }
            if (full_trace) {
                fullTraceArray(fullTraceKey("g", iter, "deltax"), dx.data(),
                               (size_t)n_frames * sizeof(RFLOAT), "f8", integerToString(n_frames));
                fullTraceArray(fullTraceKey("g", iter, "deltay"), dy.data(),
                               (size_t)n_frames * sizeof(RFLOAT), "f8", integerToString(n_frames));
                fullTraceArray(fullTraceKey("g", iter, "replay_phase_shiftx"),
                               h_shiftx.data(), sz_shifts, "f4", integerToString(n_frames));
                fullTraceArray(fullTraceKey("g", iter, "replay_phase_shifty"),
                               h_shifty.data(), sz_shifts, "f4", integerToString(n_frames));
            }
        } else {
            for (int iframe = n_frames - 1; iframe >= 0; iframe--) {
                h_cur_xshifts[iframe] -= h_cur_xshifts[0];
                h_cur_yshifts[iframe] -= h_cur_yshifts[0];
                x_sumsq += (RFLOAT)h_cur_xshifts[iframe] * h_cur_xshifts[iframe];
                y_sumsq += (RFLOAT)h_cur_yshifts[iframe] * h_cur_yshifts[iframe];
            }
            h_cur_xshifts[0] = 0.0f;
            h_cur_yshifts[0] = 0.0f;
            if (full_trace) {
                fullTraceArray(fullTraceKey("g", iter, "deltax"), h_cur_xshifts.data(), sz_shifts, "f4", integerToString(n_frames));
                fullTraceArray(fullTraceKey("g", iter, "deltay"), h_cur_yshifts.data(), sz_shifts, "f4", integerToString(n_frames));
            }
            for (int iframe = 0; iframe < n_frames; iframe++) {
                xshifts[iframe] += h_cur_xshifts[iframe];
                yshifts[iframe] += h_cur_yshifts[iframe];
                h_shiftx[iframe] = -h_cur_xshifts[iframe] / (float)pnx;
                h_shifty[iframe] = -h_cur_yshifts[iframe] / (float)pny;
            }
        }
        if (full_trace) {
            fullTraceArray(fullTraceKey("g", iter, "totalx"), xshifts.data(),
                           (size_t)n_frames * sizeof(RFLOAT), sizeof(RFLOAT) == 8 ? "f8" : "f4", integerToString(n_frames));
            fullTraceArray(fullTraceKey("g", iter, "totaly"), yshifts.data(),
                           (size_t)n_frames * sizeof(RFLOAT), sizeof(RFLOAT) == 8 ? "f8" : "f4", integerToString(n_frames));
        }

        // Apply Fourier phase shifts on GPU (matches CPU motioncorr_runner.cpp line 2476)
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
        if (full_trace) {
            for (int iframe = 0; iframe < n_frames; ++iframe) {
                HANDLE_ERROR(cudaMemcpy(full_complex_frame.data(), d_Fframes + (size_t)iframe * nfy * nfx,
                                        sz_input_frame, cudaMemcpyDeviceToHost));
                fullTraceArray(fullTraceKey("g", iter, "postshift", iframe), full_complex_frame.data(),
                               sz_input_frame, "c8", integerToString(nfy) + "," + integerToString(nfx));
            }
        }

        RFLOAT rmsd = std::sqrt((x_sumsq + y_sumsq) / n_frames);
        logfile << " Iteration " << iter << ": RMSD = " << rmsd << " px" << std::endl;
        if (cpu_trajectory.enabled && ((iter == 1 && rmsd < tolerance) ||
                                       (iter == 2 && rmsd >= tolerance)))
            REPORT_ERROR("Issue 36 CPU trajectory changed the expected two-iteration convergence");

        if (rmsd < tolerance) {
            converged = true;
            break;
        }
    }

    if (peak_probe.enabled && !peak_trace_written)
        REPORT_ERROR("Global peak trace iteration was not reached before alignment converged");

    // Final transfer: copy shifted Fframes back to host
    HANDLE_ERROR(cudaEventRecord(ev_start_d2h));
    for (int iframe = 0; iframe < n_frames; iframe++) {
        HANDLE_ERROR(cudaMemcpy(
            Fframes[iframe].data,
            d_Fframes + (size_t)iframe * nfy * nfx,
            (size_t)nfy * nfx * sizeof(float2),
            cudaMemcpyDeviceToHost
        ));
    }
    HANDLE_ERROR(cudaEventRecord(ev_stop_d2h));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_d2h));
    float final_d2h_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&final_d2h_ms, ev_start_d2h, ev_stop_d2h));
    accumulated_d2h_ms += final_d2h_ms;

    HANDLE_ERROR(cudaEventRecord(ev_stop_total));
    HANDLE_ERROR(cudaEventSynchronize(ev_stop_total));
    float total_ms = 0.0f;
    HANDLE_ERROR(cudaEventElapsedTime(&total_ms, ev_start_total, ev_stop_total));

    // Profile logging per pass criteria in Issue #16
    logfile << " [CUDA Global Alignment Profile]" << std::endl;
    logfile << "   Host-to-Device transfer time: " << std::fixed << std::setprecision(2) << h2d_ms << " ms" << std::endl;
    logfile << "   Custom kernel execution time: " << std::fixed << std::setprecision(2) << accumulated_kernel_ms << " ms" << std::endl;
    logfile << "   cuFFT execution time:         " << std::fixed << std::setprecision(2) << accumulated_cufft_ms << " ms" << std::endl;
    logfile << "   Device-to-Host transfer time: " << std::fixed << std::setprecision(2) << accumulated_d2h_ms << " ms" << std::endl;
    logfile << "   Total GPU alignment time:     " << std::fixed << std::setprecision(2) << total_ms << " ms" << std::endl;
    logfile << "   Buffer VRAM:                  " << std::fixed << std::setprecision(2) << ((total_vram_allocated - cufft_work_size) / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   cuFFT workspace VRAM:         " << std::fixed << std::setprecision(2) << (cufft_work_size / (1024.0 * 1024.0)) << " MiB" << std::endl;
    logfile << "   Peak GPU memory allocated:    " << std::fixed << std::setprecision(2) << (total_vram_allocated / (1024.0 * 1024.0)) << " MiB" << std::endl;

    // Cleanup
    CUFFT_CHECK(cufftDestroy(plan_c2r));
    HANDLE_ERROR(cudaFree(d_Fframes));
    HANDLE_ERROR(cudaFree(d_Fref));
    HANDLE_ERROR(cudaFree(d_weight));
    HANDLE_ERROR(cudaFree(d_Fccs));
    HANDLE_ERROR(cudaFree(d_Iccs));
    HANDLE_ERROR(cudaFree(d_cur_xshifts));
    HANDLE_ERROR(cudaFree(d_cur_yshifts));
    HANDLE_ERROR(cudaFree(d_shiftx));
    HANDLE_ERROR(cudaFree(d_shifty));
    if (d_peak_probe) HANDLE_ERROR(cudaFree(d_peak_probe));
    if (d_full_peaks) HANDLE_ERROR(cudaFree(d_full_peaks));

    HANDLE_ERROR(cudaEventDestroy(ev_start_total));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_total));
    HANDLE_ERROR(cudaEventDestroy(ev_start_h2d));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_h2d));
    HANDLE_ERROR(cudaEventDestroy(ev_start_kernel));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_kernel));
    HANDLE_ERROR(cudaEventDestroy(ev_start_cufft));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_cufft));
    HANDLE_ERROR(cudaEventDestroy(ev_start_d2h));
    HANDLE_ERROR(cudaEventDestroy(ev_stop_d2h));

    return converged;
}

#endif // _CUDA_ENABLED
