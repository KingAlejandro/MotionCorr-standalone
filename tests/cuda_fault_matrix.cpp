// Issue #69 -- bounded CUDA fault matrix.
//
// Injects exactly one failure per trial into the real production code paths and
// records, for that trial: which stage was reached, how the call exited, whether every
// owned device allocation was released, whether borrowed host inputs survived, and
// whether an earlier completed product survived.
//
// Technique: link-time interposition with --wrap, the same mechanism
// tests/cuda_wrapper_upload_failure.cpp already uses. The fault switches live in this
// translation unit only. Nothing in src/ knows they exist, so there is no production
// fault switch and none can be active during a timed run.
//
// Requires a real CUDA device. It is registered with the "cuda;hardware" label.
//
// WHAT IT DOES NOT COVER: it cannot synthesise a genuinely poisoned context (an
// illegal address or an ECC fault), so the poisoned-context branch added for #69 is
// exercised only by the classifier's unit behaviour, not by a real fault. That gap is
// stated rather than papered over.

#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/error.h"

#include <cuda_runtime.h>
#include <cufft.h>

#include <cstdio>
#include <set>
#include <sstream>
#include <string>
#include <vector>

// --------------------------------------------------------------------------------
// Interposition state
// --------------------------------------------------------------------------------
namespace {

enum FaultKind {
    FAULT_NONE = 0,
    FAULT_MALLOC,
    FAULT_H2D,
    FAULT_D2H,
    FAULT_D2D,
    FAULT_MEMSET,
    FAULT_SYNC,
    FAULT_CUFFT_CREATE,
    FAULT_CUFFT_MAKEPLAN,
    FAULT_CUFFT_SETWORKAREA,
    FAULT_CUFFT_PLANMANY,
    FAULT_CUFFT_EXEC,
    FAULT_KIND_COUNT
};

const char *faultName(FaultKind k) {
    switch (k) {
    case FAULT_MALLOC:            return "cudaMalloc";
    case FAULT_H2D:               return "cudaMemcpy H2D";
    case FAULT_D2H:               return "cudaMemcpy D2H";
    case FAULT_D2D:               return "cudaMemcpy D2D";
    case FAULT_MEMSET:            return "cudaMemset";
    case FAULT_SYNC:              return "cudaDeviceSynchronize";
    case FAULT_CUFFT_CREATE:      return "cufftCreate";
    case FAULT_CUFFT_MAKEPLAN:    return "cufftMakePlanMany";
    case FAULT_CUFFT_SETWORKAREA: return "cufftSetWorkArea";
    case FAULT_CUFFT_PLANMANY:    return "cufftPlanMany";
    case FAULT_CUFFT_EXEC:        return "cufftExec";
    default:                      return "none";
    }
}

bool        g_active     = false;   // tracking and injection armed
FaultKind   g_fault_kind = FAULT_NONE;
long        g_fault_at   = 0;       // 1-based ordinal of the call to fail; 0 = never
long        g_counts[FAULT_KIND_COUNT];
bool        g_fault_fired = false;

std::set<void *> g_outstanding;     // device allocations made while armed

void resetCounters() {
    for (int i = 0; i < FAULT_KIND_COUNT; i++) g_counts[i] = 0;
    g_fault_fired = false;
}

// Returns true when this call is the one to fail.
bool shouldFail(FaultKind kind) {
    if (!g_active) return false;
    const long n = ++g_counts[kind];
    if (g_fault_kind != kind || g_fault_at == 0 || n != g_fault_at) return false;
    g_fault_fired = true;
    return true;
}

} // namespace

extern "C" {

cudaError_t __real_cudaMalloc(void **ptr, size_t size);
cudaError_t __real_cudaFree(void *ptr);
cudaError_t __real_cudaMemcpy(void *dst, const void *src, size_t size, cudaMemcpyKind kind);
cudaError_t __real_cudaMemset(void *ptr, int value, size_t size);
cudaError_t __real_cudaDeviceSynchronize(void);
cufftResult __real_cufftCreate(cufftHandle *plan);
cufftResult __real_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
                                     int *inembed, int istride, int idist,
                                     int *onembed, int ostride, int odist,
                                     cufftType type, int batch, size_t *workSize);
cufftResult __real_cufftSetWorkArea(cufftHandle plan, void *workArea);
cufftResult __real_cufftPlanMany(cufftHandle *plan, int rank, int *n,
                                 int *inembed, int istride, int idist,
                                 int *onembed, int ostride, int odist,
                                 cufftType type, int batch);
cufftResult __real_cufftExecR2C(cufftHandle plan, cufftReal *idata, cufftComplex *odata);
cufftResult __real_cufftExecC2R(cufftHandle plan, cufftComplex *idata, cufftReal *odata);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t size) {
    if (shouldFail(FAULT_MALLOC)) { *ptr = nullptr; return cudaErrorMemoryAllocation; }
    const cudaError_t result = __real_cudaMalloc(ptr, size);
    if (g_active && result == cudaSuccess) g_outstanding.insert(*ptr);
    return result;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) g_outstanding.erase(ptr);
    return result;
}

cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t size, cudaMemcpyKind kind) {
    FaultKind k = FAULT_NONE;
    if (kind == cudaMemcpyHostToDevice)        k = FAULT_H2D;
    else if (kind == cudaMemcpyDeviceToHost)   k = FAULT_D2H;
    else if (kind == cudaMemcpyDeviceToDevice) k = FAULT_D2D;
    if (k != FAULT_NONE && shouldFail(k)) return cudaErrorInvalidValue;
    return __real_cudaMemcpy(dst, src, size, kind);
}

cudaError_t __wrap_cudaMemset(void *ptr, int value, size_t size) {
    if (shouldFail(FAULT_MEMSET)) return cudaErrorInvalidValue;
    return __real_cudaMemset(ptr, value, size);
}

// Stands in for a launch that did not complete: the production code synchronises after
// its launches precisely so an execution failure surfaces at a known point.
cudaError_t __wrap_cudaDeviceSynchronize(void) {
    if (shouldFail(FAULT_SYNC)) return cudaErrorInvalidValue;
    return __real_cudaDeviceSynchronize();
}

cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (shouldFail(FAULT_CUFFT_CREATE)) return CUFFT_ALLOC_FAILED;
    return __real_cufftCreate(plan);
}

cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
                                     int *inembed, int istride, int idist,
                                     int *onembed, int ostride, int odist,
                                     cufftType type, int batch, size_t *workSize) {
    if (shouldFail(FAULT_CUFFT_MAKEPLAN)) return CUFFT_ALLOC_FAILED;
    return __real_cufftMakePlanMany(plan, rank, n, inembed, istride, idist,
                                    onembed, ostride, odist, type, batch, workSize);
}

cufftResult __wrap_cufftSetWorkArea(cufftHandle plan, void *workArea) {
    if (shouldFail(FAULT_CUFFT_SETWORKAREA)) return CUFFT_INVALID_VALUE;
    return __real_cufftSetWorkArea(plan, workArea);
}

cufftResult __wrap_cufftPlanMany(cufftHandle *plan, int rank, int *n,
                                 int *inembed, int istride, int idist,
                                 int *onembed, int ostride, int odist,
                                 cufftType type, int batch) {
    if (shouldFail(FAULT_CUFFT_PLANMANY)) return CUFFT_ALLOC_FAILED;
    return __real_cufftPlanMany(plan, rank, n, inembed, istride, idist,
                                onembed, ostride, odist, type, batch);
}

cufftResult __wrap_cufftExecR2C(cufftHandle plan, cufftReal *idata, cufftComplex *odata) {
    if (shouldFail(FAULT_CUFFT_EXEC)) return CUFFT_EXEC_FAILED;
    return __real_cufftExecR2C(plan, idata, odata);
}

cufftResult __wrap_cufftExecC2R(cufftHandle plan, cufftComplex *idata, cufftReal *odata) {
    if (shouldFail(FAULT_CUFFT_EXEC)) return CUFFT_EXEC_FAILED;
    return __real_cufftExecC2R(plan, idata, odata);
}

} // extern "C"

// --------------------------------------------------------------------------------
// Scenario
// --------------------------------------------------------------------------------
namespace {

const int NX = 64, NY = 64, NFRAMES = 4;

struct TrialResult {
    std::string last_stage;     // last stage the scenario entered
    std::string exit_mechanism; // "returned false", "threw RelionError", "completed"
    bool        fault_fired = false;
    bool        products_ok = true;
    size_t      leaked = 0;
};

struct HostInputs {
    std::vector<Image<float> > frames;
    MultidimArray<float> gain;
    std::vector<double> frame_checksums;
    double gain_checksum = 0.0;
};

double checksum(const MultidimArray<float> &a) {
    double acc = 0.0;
    FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(a) acc += (double)DIRECT_MULTIDIM_ELEM(a, n) * (n % 97 + 1);
    return acc;
}

void buildHostInputs(HostInputs &in) {
    in.frames.resize(NFRAMES);
    for (int k = 0; k < NFRAMES; k++) {
        in.frames[k]().initZeros(NY, NX);
        for (int y = 0; y < NY; y++)
            for (int x = 0; x < NX; x++)
                DIRECT_A2D_ELEM(in.frames[k](), y, x) =
                    (float)(1.0 + 0.25 * ((x * 7 + y * 13 + k * 31) % 11));
    }
    in.gain.initZeros(NY, NX);
    FOR_ALL_DIRECT_ELEMENTS_IN_MULTIDIMARRAY(in.gain) DIRECT_MULTIDIM_ELEM(in.gain, n) = 1.0f;
    in.frame_checksums.resize(NFRAMES);
    for (int k = 0; k < NFRAMES; k++) in.frame_checksums[k] = checksum(in.frames[k]());
    in.gain_checksum = checksum(in.gain);
}

bool hostInputsIntact(const HostInputs &in) {
    for (int k = 0; k < NFRAMES; k++)
        if (checksum(in.frames[k]()) != in.frame_checksums[k]) return false;
    return checksum(in.gain) == in.gain_checksum;
}

// One full movie through the resident stack. Stops at the first failure, exactly as
// production does, and records where it stopped.
void runOneMovie(HostInputs &in, std::ostream &log, TrialResult &out) {
    std::vector<RFLOAT> doses(NFRAMES, 1.0);
    MultidimArray<float> unaligned_sum;
    Image<float> recon, recon_even, recon_odd;
    recon().initZeros(NY, NX);
    recon_even().initZeros(NY, NX);
    recon_odd().initZeros(NY, NX);

    // Product written before the later stages, so a later fault can be checked against
    // an earlier completed product.
    Image<float> early_product;
    early_product().initZeros(NY, NX);
    double early_checksum = 0.0;
    bool early_written = false;

    CudaMovieSession session(NX, NY, NFRAMES, 0, log);
    float *d_patch_fourier = nullptr;

    struct PatchBufferGuard {
        float **p;
        ~PatchBufferGuard() { if (*p) { cudaFree(*p); *p = nullptr; } }
    } guard{&d_patch_fourier};

#define STAGE(name, expr)                                                  \
    do {                                                                   \
        out.last_stage = (name);                                           \
        if (!(expr)) { out.exit_mechanism = "returned false"; return; }    \
    } while (0)

    STAGE("session initialize", session.initialize());
    STAGE("gain and unaligned sum", session.applyGainDefectsAndSum(in.frames, &in.gain, unaligned_sum, true));

    double sum1 = 0.0, sum_abs = 0.0, sum2 = 0.0;
    STAGE("reduce unaligned sum", session.reduceUnalignedSum(sum1, sum_abs));
    STAGE("reduce unaligned sumsqdev", session.reduceUnalignedSumSqDev(sum1 / (NX * NY), sum2));

    std::vector<int> hits;
    size_t band = 0;
    // A false here is a legitimate documented fallback (hit-buffer overflow), so it is
    // only recorded as a failure when this trial actually injected a fault.
    out.last_stage = "collect above threshold";
    if (!session.collectAboveThreshold(1e30, 0.0, hits, band) && g_fault_fired) {
        out.exit_mechanism = "returned false";
        return;
    }

    std::vector<int> bad_xs(1, 3), bad_ys(1, 4);
    std::vector<float> replacements(NFRAMES, 1.0f);
    STAGE("update defect pixels", session.updateDefectPixels(bad_xs, bad_ys, replacements));
    STAGE("release preprocessing buffers", session.releasePreprocessingBuffers());
    STAGE("global forward FFT", session.computeGlobalForwardFFT());

    {
        out.last_stage = "global alignment";
        std::vector<RFLOAT> xs(NFRAMES, 0.0), ys(NFRAMES, 0.0);
        cudaAlignPatchDevice(session.getDeviceFourierFrames(), NFRAMES, NX, NY, 20.0,
                             xs, ys, 2, 1.0, 0, log, true);
    }

    STAGE("global inverse FFT", session.computeGlobalInverseFFT());

    // An earlier completed product, written before the remaining stages can fail.
    STAGE("unweighted reconstruction", session.reconstructUnweighted(recon, &recon_even, &recon_odd, nullptr));
    early_product() = recon();
    early_checksum = checksum(early_product());
    early_written = true;

    {
        out.last_stage = "patch scratch allocation";
        const int patch_w = 32, patch_h = 32;
        const int patch_nfx = patch_w / 2 + 1;
        const size_t sz = (size_t)NFRAMES * patch_h * patch_nfx * sizeof(cufftComplex);
        if (cudaMalloc((void **)&d_patch_fourier, sz) != cudaSuccess) {
            d_patch_fourier = nullptr;
            out.exit_mechanism = "returned false";
            return;
        }
        std::vector<int> group_start(NFRAMES), group_size(NFRAMES, 1);
        for (int k = 0; k < NFRAMES; k++) group_start[k] = k;
        STAGE("patch preparation", session.preparePatchInVram(0, 0, patch_w, patch_h, NFRAMES,
                                                              group_start.data(), group_size.data(),
                                                              (cufftComplex *)d_patch_fourier));
        out.last_stage = "patch alignment";
        std::vector<RFLOAT> xs(NFRAMES, 0.0), ys(NFRAMES, 0.0);
        cudaAlignPatchDevice((cufftComplex *)d_patch_fourier, NFRAMES, patch_w, patch_h, 20.0,
                             xs, ys, 2, 1.0, 0, log, false);
    }

    STAGE("dose-weighted reconstruction", session.reconstructDoseWeighted(recon, doses, 1.0, nullptr));
#undef STAGE

    out.exit_mechanism = "completed";
    if (early_written && checksum(early_product()) != early_checksum) out.products_ok = false;
}

TrialResult runTrial(FaultKind kind, long ordinal, int n_movies) {
    TrialResult out;
    HostInputs in;
    buildHostInputs(in);
    std::ostringstream log;

    resetCounters();
    g_fault_kind = kind;
    g_fault_at = ordinal;
    g_outstanding.clear();
    g_active = true;

    try {
        for (int movie = 0; movie < n_movies; movie++) {
            TrialResult movie_result;
            runOneMovie(in, log, movie_result);
            out.last_stage = movie_result.last_stage;
            out.exit_mechanism = movie_result.exit_mechanism;
            out.products_ok = out.products_ok && movie_result.products_ok;
        }
    } catch (RelionError &) {
        out.exit_mechanism = "threw RelionError";
    } catch (...) {
        out.exit_mechanism = "threw unexpected exception";
    }

    g_active = false;
    out.fault_fired = g_fault_fired;
    out.leaked = g_outstanding.size();
    // Do not let one trial's leak contaminate the next one's verdict.
    for (std::set<void *>::iterator it = g_outstanding.begin(); it != g_outstanding.end(); ++it)
        __real_cudaFree(*it);
    g_outstanding.clear();

    if (!hostInputsIntact(in)) out.products_ok = false;
    return out;
}

} // namespace

int main() {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::fprintf(stderr, "CUDA device 0 is required for this control\n");
        return 1;
    }

    // How many of each primitive a clean run makes: the matrix sweeps every ordinal.
    const TrialResult clean = runTrial(FAULT_NONE, 0, 1);
    if (clean.exit_mechanism != "completed" || clean.leaked != 0) {
        std::fprintf(stderr,
                     "Baseline is not clean: exit=%s leaked=%zu stage=%s. "
                     "Every verdict below would be meaningless.\n",
                     clean.exit_mechanism.c_str(), clean.leaked, clean.last_stage.c_str());
        return 1;
    }
    long budget[FAULT_KIND_COUNT];
    for (int i = 0; i < FAULT_KIND_COUNT; i++) budget[i] = g_counts[i];

    std::printf("Issue #69 CUDA fault matrix. Clean run uses:");
    for (int k = FAULT_MALLOC; k < FAULT_KIND_COUNT; k++)
        std::printf(" %s=%ld", faultName((FaultKind)k), budget[k]);
    std::printf("\n\n%-24s %-4s %-34s %-22s %-7s %-8s\n",
                "primitive", "n", "stage reached", "exit", "leaked", "products");

    int failures = 0, trials = 0;
    for (int k = FAULT_MALLOC; k < FAULT_KIND_COUNT; k++) {
        for (long n = 1; n <= budget[k]; n++) {
            const TrialResult r = runTrial((FaultKind)k, n, 1);
            trials++;
            const bool ok = r.fault_fired && r.exit_mechanism != "completed" &&
                            r.exit_mechanism != "threw unexpected exception" &&
                            r.leaked == 0 && r.products_ok;
            std::printf("%-24s %-4ld %-34s %-22s %-7zu %-8s %s\n",
                        faultName((FaultKind)k), n, r.last_stage.c_str(),
                        r.exit_mechanism.c_str(), r.leaked,
                        r.products_ok ? "intact" : "DAMAGED", ok ? "" : "  <-- FAIL");
            if (!ok) failures++;
        }
    }

    // Successive movies with the fault on the last one: exposes cross-movie leaks and
    // stale cache state that a single-movie trial cannot see.
    std::printf("\nSuccessive-movie trials (3 movies, fault on the third pass):\n");
    for (int k = FAULT_MALLOC; k <= FAULT_D2H; k++) {
        const long n = budget[k] * 3;
        if (n == 0) continue;
        const TrialResult r = runTrial((FaultKind)k, n, 3);
        trials++;
        const bool ok = r.fault_fired && r.exit_mechanism != "completed" &&
                        r.leaked == 0 && r.products_ok;
        std::printf("%-24s %-4ld %-34s %-22s %-7zu %-8s %s\n",
                    faultName((FaultKind)k), n, r.last_stage.c_str(),
                    r.exit_mechanism.c_str(), r.leaked,
                    r.products_ok ? "intact" : "DAMAGED", ok ? "" : "  <-- FAIL");
        if (!ok) failures++;
    }

    std::printf("\n%d trials, %d failures\n", trials, failures);
    if (failures) return 1;
    std::printf("PASS every injected fault exited without completing, released every "
                "owned allocation and preserved borrowed inputs and earlier products\n");
    return 0;
}
