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
// WHAT IT DOES NOT COVER, stated rather than papered over:
//   * It cannot synthesise a genuinely poisoned context -- an illegal address or an
//     ECC fault. The predicate that drives the poisoned-context branch is unit tested
//     in tests/cuda_error_class.cpp, but the production branch itself is exercised by
//     argument only, never by a real fault.
//   * It drives CudaMovieSession and cudaAlignPatchDevice directly, not
//     motioncorr_runner.cpp, so the two behaviour-changing fixes (the retry shift
//     reset and the poisoned-context refusal) get nothing from it. The retry fix's
//     end-to-end witness is item 4 of docs/issue69/gpu_plan.md.
//   * cuFFT allocates its own workspace inside libcufft, below the interposed
//     cudaMalloc, so that memory is outside the leak accounting here.

#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/acc/cuda/cuda_fft_prep.h"
#include "src/error.h"

#include <cuda_runtime.h>
#include <cufft.h>

#include <cstdio>
#include <cerrno>
#include <cstdlib>
#include <spawn.h>
#include <sys/wait.h>

extern char **environ;
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
    FAULT_FREE,
    FAULT_EVENT_CREATE,
    FAULT_EVENT_DESTROY,
    FAULT_PLAN_DESTROY,
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
    case FAULT_FREE:              return "cudaFree (after release)";
    case FAULT_EVENT_CREATE:      return "cudaEventCreate";
    case FAULT_EVENT_DESTROY:     return "cudaEventDestroy (after release)";
    case FAULT_PLAN_DESTROY:      return "cufftDestroy (after release)";
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
size_t g_stale_releases = 0;
bool g_free_sequence = false;
int g_free_sequence_count = 0;
bool g_count_armed = false;
bool g_count_fired = false;
cudaError_t g_count_error = cudaSuccess;
long g_count_calls = 0;

// Set while the session destructor runs. CudaMovieSession::release() performs a
// deliberately non-fatal cudaDeviceSynchronize and only logs on failure, so a fault
// injected there is expected to be survived, not to abort. Scoring it as a failure
// would report a test-oracle artefact as a production defect.
bool        g_in_teardown       = false;
bool        g_fault_in_teardown = false;

// Outstanding owned resources. Device memory alone is not enough: the leak this issue
// is mostly about in cudaAlignPatchDevice is eight cudaEvent_t and one cufftHandle,
// none of which pass through cudaMalloc. cuFFT's *internal* workspace still allocates
// inside libcufft and is not visible here -- stated, not papered over.
std::set<void *>      g_outstanding;         // cudaMalloc
std::set<cudaEvent_t> g_outstanding_events;  // cudaEventCreate
std::set<int>         g_outstanding_plans;   // cufftCreate / cufftPlanMany

size_t totalOutstanding() {
    return g_outstanding.size() + g_outstanding_events.size() + g_outstanding_plans.size();
}

void resetCounters() {
    for (int i = 0; i < FAULT_KIND_COUNT; i++) g_counts[i] = 0;
    g_fault_fired = false;
    g_stale_releases = 0;
    g_fault_in_teardown = false;
}

// Returns true when this call is the one to fail.
bool shouldFail(FaultKind kind) {
    if (!g_active) return false;
    const long n = ++g_counts[kind];
    if (g_fault_kind != kind || g_fault_at == 0 || n != g_fault_at) return false;
    g_fault_fired = true;
    if (g_in_teardown) g_fault_in_teardown = true;
    return true;
}

} // namespace

extern "C" {

cudaError_t __real_cudaGetDeviceCount(int *count);
cudaError_t __real_cudaMalloc(void **ptr, size_t size);
cudaError_t __real_cudaFree(void *ptr);
cudaError_t __real_cudaMemcpy(void *dst, const void *src, size_t size, cudaMemcpyKind kind);
cudaError_t __real_cudaMemset(void *ptr, int value, size_t size);
cudaError_t __real_cudaDeviceSynchronize(void);
cudaError_t __real_cudaEventCreate(cudaEvent_t *event);
cudaError_t __real_cudaEventDestroy(cudaEvent_t event);
cufftResult __real_cufftDestroy(cufftHandle plan);
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

cudaError_t __wrap_cudaGetDeviceCount(int *count) {
    ++g_count_calls;
    if (g_count_armed) {
        g_count_armed = false;
        g_count_fired = true;
        *count = 0;
        // Returned status only: leave the runtime last-error slot clean.
        return g_count_error;
    }
    return __real_cudaGetDeviceCount(count);
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const bool inject = shouldFail(FAULT_FREE);
    if (g_active && ptr && !g_outstanding.count(ptr)) ++g_stale_releases;
    const cudaError_t result = __real_cudaFree(ptr);
    if (result == cudaSuccess) g_outstanding.erase(ptr);
    if (g_free_sequence && result == cudaSuccess) {
        const int n = ++g_free_sequence_count;
        if (n == 1) return cudaErrorInvalidValue;
        if (n == 2) return cudaErrorIllegalAddress;
    }
    return inject && result == cudaSuccess ? cudaErrorInvalidValue : result;
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

cudaError_t __wrap_cudaEventCreate(cudaEvent_t *event) {
    if (shouldFail(FAULT_EVENT_CREATE)) { *event = nullptr; return cudaErrorMemoryAllocation; }
    const cudaError_t result = __real_cudaEventCreate(event);
    if (g_active && result == cudaSuccess) g_outstanding_events.insert(*event);
    return result;
}

// Both destroy wrappers erase only on success, which is the right default -- a failed
// destroy has not released anything. Known undercount: if a destroy fails and the
// runtime later recycles the same cudaEvent_t pointer or cufftHandle value, the
// re-insert collapses two lifetimes into one set entry and hides a leak. Neither
// destroy is faulted here, so it needs a genuine runtime failure to reach.
cudaError_t __wrap_cudaEventDestroy(cudaEvent_t event) {
    const bool inject = shouldFail(FAULT_EVENT_DESTROY);
    if (g_active && event && !g_outstanding_events.count(event)) ++g_stale_releases;
    const cudaError_t result = __real_cudaEventDestroy(event);
    if (result == cudaSuccess) g_outstanding_events.erase(event);
    return inject && result == cudaSuccess ? cudaErrorInvalidValue : result;
}

cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const bool inject = shouldFail(FAULT_PLAN_DESTROY);
    if (g_active && !g_outstanding_plans.count((int)plan)) ++g_stale_releases;
    const cufftResult result = __real_cufftDestroy(plan);
    if (result == CUFFT_SUCCESS) g_outstanding_plans.erase((int)plan);
    return inject && result == CUFFT_SUCCESS ? CUFFT_INTERNAL_ERROR : result;
}

cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (shouldFail(FAULT_CUFFT_CREATE)) return CUFFT_ALLOC_FAILED;
    const cufftResult result = __real_cufftCreate(plan);
    if (g_active && result == CUFFT_SUCCESS) g_outstanding_plans.insert((int)*plan);
    return result;
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
    const cufftResult result = __real_cufftPlanMany(plan, rank, n, inembed, istride, idist,
                                                    onembed, ostride, odist, type, batch);
    if (g_active && result == CUFFT_SUCCESS) g_outstanding_plans.insert((int)*plan);
    return result;
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
    bool        fault_in_teardown = false;
    bool        products_ok = true;
    size_t      leaked = 0;
};

struct HostInputs {
    std::vector<Image<float> > frames;
    MultidimArray<float> gain;
    // Element-wise reference copies. A single scalar checksum standing in for
    // NFRAMES*NY*NX elements is a weaker claim than an exact compare that costs the
    // same at this size.
    std::vector<std::vector<float> > frame_reference;
    std::vector<float> gain_reference;
};

bool sameAs(const MultidimArray<float> &a, const std::vector<float> &reference) {
    if (a.nzyxdim != (long)reference.size()) return false;
    for (size_t n = 0; n < reference.size(); n++)
        if (DIRECT_MULTIDIM_ELEM(a, n) != reference[n]) return false;
    return true;
}

std::vector<float> snapshot(const MultidimArray<float> &a) {
    std::vector<float> out((size_t)a.nzyxdim);
    for (size_t n = 0; n < out.size(); n++) out[n] = DIRECT_MULTIDIM_ELEM(a, n);
    return out;
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
    in.frame_reference.resize(NFRAMES);
    for (int k = 0; k < NFRAMES; k++) in.frame_reference[k] = snapshot(in.frames[k]());
    in.gain_reference = snapshot(in.gain);
}

// Note honestly what this is worth: the production signatures take these as
// const references, so the compiler already forbids mutation. This is a cheap standing
// guard against a future const_cast or a stray D2H into a borrowed buffer -- not a
// demonstration that the code could have corrupted them and did not.
bool hostInputsIntact(const HostInputs &in) {
    for (int k = 0; k < NFRAMES; k++)
        if (!sameAs(in.frames[k](), in.frame_reference[k])) return false;
    return sameAs(in.gain, in.gain_reference);
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

    // There is deliberately no "an earlier in-memory product survived" check here.
    // An Image<float> local to this function cannot be reached by anything downstream,
    // so such a check could not fail and would be a green guard for a property it
    // cannot observe. Survival of *prior on-disk artifacts across movies* is a real
    // requirement, and it belongs to the end-to-end runs in docs/issue69/gpu_plan.md
    // and to #99/#53's completion contract, not to this harness.

    CudaMovieSession session(NX, NY, NFRAMES, 0, log);
    float *d_patch_fourier = nullptr;

    struct PatchBufferGuard {
        float **p;
        ~PatchBufferGuard() { if (*p) { cudaFree(*p); *p = nullptr; } }
    } guard{&d_patch_fourier};

    // Declared after the session, so it is destroyed *before* it: ~CudaMovieSession
    // then runs with g_in_teardown set, on the normal path and during unwinding alike.
    // release() performs a deliberately non-fatal cudaDeviceSynchronize that only
    // logs on failure, so a fault landing there is expected to be survived; without
    // this the last cudaDeviceSynchronize ordinal of a clean run would be scored as a
    // production failure when it is a documented best-effort path.
    struct MarkTeardown {
        ~MarkTeardown() { g_in_teardown = true; }
    } mark_teardown;

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

    {
        std::vector<MultidimArray<fComplex> > fourier;
        STAGE("download wrapper input", session.downloadFourierFrames(fourier));
        out.last_stage = "host staging alignment";
        std::vector<RFLOAT> xs(NFRAMES, 0.0), ys(NFRAMES, 0.0);
        cudaAlignPatch(fourier, NX, NY, 20.0, xs, ys, 2, 1.0, 0, log, true);
    }

    STAGE("global inverse FFT", session.computeGlobalInverseFFT());

    STAGE("unweighted reconstruction", session.reconstructUnweighted(recon, &recon_even, &recon_odd, nullptr));

    {
        out.last_stage = "patch scratch allocation";
        const int patch_w = 48, patch_h = 48;
        const int patch_nfx = patch_w / 2 + 1;
        const size_t sz = (size_t)NFRAMES * patch_h * patch_nfx * sizeof(cufftComplex);
        if (cudaMalloc((void **)&d_patch_fourier, sz) != cudaSuccess) {
            d_patch_fourier = nullptr;
            out.exit_mechanism = "returned false";
            return;
        }
        std::vector<int> group_start(NFRAMES), group_size(NFRAMES, 1);
        for (int k = 0; k < NFRAMES; k++) group_start[k] = k;
        std::vector<int> small_start{0, 2}, small_size{2, 2};
        STAGE("small patch cache", session.preparePatchInVram(0, 0, 32, 32, 2,
                small_start.data(), small_size.data(), (cufftComplex *)d_patch_fourier));
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
    g_outstanding_events.clear();
    g_outstanding_plans.clear();
    g_in_teardown = false;
    g_active = true;

    // Declared outside the try. Faults inside cuda_alignpatch.cu leave by exception --
    // that is the whole premise of F1 -- and a result object scoped inside the try
    // would be destroyed by the unwind, blanking the stage column for exactly the
    // trials that matter most.
    TrialResult movie_result;
    try {
        for (int movie = 0; movie < n_movies; movie++) {
            // Reset both, not just the exit: a movie that throws before its first
            // STAGE -- in the CudaMovieSession constructor, say -- would otherwise
            // report the previous movie's stage.
            movie_result.exit_mechanism = "";
            movie_result.last_stage = "";
            g_in_teardown = false;
            runOneMovie(in, log, movie_result);
            g_in_teardown = false;
        }
    } catch (RelionError &) {
        movie_result.exit_mechanism = "threw RelionError";
    } catch (...) {
        movie_result.exit_mechanism = "threw unexpected exception";
    }
    out.last_stage = movie_result.last_stage;
    out.exit_mechanism = movie_result.exit_mechanism;

    g_in_teardown = false;
    g_active = false;
    out.fault_fired = g_fault_fired;
    out.fault_in_teardown = g_fault_in_teardown;
    out.leaked = totalOutstanding() + g_stale_releases;
    // Do not let one trial's leak contaminate the next one's verdict.
    for (std::set<void *>::iterator it = g_outstanding.begin(); it != g_outstanding.end(); ++it)
        __real_cudaFree(*it);
    for (std::set<cudaEvent_t>::iterator it = g_outstanding_events.begin();
         it != g_outstanding_events.end(); ++it)
        __real_cudaEventDestroy(*it);
    for (std::set<int>::iterator it = g_outstanding_plans.begin();
         it != g_outstanding_plans.end(); ++it)
        __real_cufftDestroy((cufftHandle)*it);
    g_outstanding.clear();
    g_outstanding_events.clear();
    g_outstanding_plans.clear();

    if (!hostInputsIntact(in)) out.products_ok = false;
    return out;
}

// Production session controls that re-enter after replacement failed, rather than
// merely asking a hand-built classifier what it would do.
int runOwnershipControls(int selected_mode) {
    int failures = 0;
    HostInputs in; buildHostInputs(in);
    for (int mode = selected_mode; mode == selected_mode; ++mode) {
        resetCounters(); g_fault_kind = FAULT_NONE; g_fault_at = 0;
        g_active = true; g_in_teardown = false;
        std::ostringstream log;
        {
            CudaMovieSession session(NX, NY, NFRAMES, 0, log);
            MultidimArray<float> sum;
            bool ok = session.initialize() && session.applyGainDefectsAndSum(in.frames, &in.gain, sum);
            if (mode == 0) {
                g_free_sequence = true; g_free_sequence_count = 0;
                ok = ok && !session.releasePreprocessingBuffers();
                g_free_sequence = false;
                ok = ok && g_free_sequence_count == 2 &&
                    session.getFailureState().firstError() == cudaErrorInvalidValue &&
                    session.getFailureState().fatalError() == cudaErrorIllegalAddress &&
                    cudaGetLastError() == cudaSuccess;
                const long calls_before = g_counts[FAULT_MALLOC];
                const int start[1] = {0}, size[1] = {1};
                ok = ok && !session.computeGlobalForwardFFT() &&
                    !session.preparePatchInVram(0,0,32,32,1,start,size,
                                              session.getDeviceFourierFrames()) &&
                    g_counts[FAULT_MALLOC] == calls_before;
                session.release(); session.release();
                ok = ok && !session.initialize(); // poison is sticky after release
            } else {
                cufftComplex *out = nullptr;
                const size_t bytes = (size_t)NFRAMES * 48 * 25 * sizeof(cufftComplex);
                ok = ok && cudaMalloc((void**)&out, bytes) == cudaSuccess;
                const int gs[4] = {0,1,2,3}, gz[4] = {1,1,1,1};
                const int small_gs[2] = {0,2}, small_gz[2] = {2,2};
                ok = ok && session.preparePatchInVram(0,0,32,32,2,small_gs,small_gz,out);
                g_fault_kind = mode == 1 ? FAULT_MALLOC : mode == 2 ? FAULT_FREE : FAULT_CUFFT_MAKEPLAN;
                // Grow real scratch, then start/size arrays: fail the size allocation.
                g_fault_at = g_counts[g_fault_kind] + (mode == 1 ? 3 : 1);
                ok = ok && !session.preparePatchInVram(0,0,48,48,4,gs,gz,out) && g_fault_fired;
                g_fault_kind = FAULT_NONE; g_fault_at = 0;
                ok = ok && session.preparePatchInVram(0,0,48,48,4,gs,gz,out);
                if (out) cudaFree(out);
                session.release(); session.release();
            }
            if (!ok) { ++failures; std::fprintf(stderr,"FAIL ownership re-entry mode=%d\n",mode); }
        }
        g_active = false;
        if (totalOutstanding() || g_stale_releases) {
            ++failures; std::fprintf(stderr,"FAIL re-entry resources=%zu stale=%zu\n",totalOutstanding(),g_stale_releases);
        }
    }
    std::printf("Ownership control: one production session sequence, failures=%d\n",failures);
    return failures;
}

int runEnumerationControls(int selected_boundary, int selected_mode) {
    int failures = 0;
    HostInputs in; buildHostInputs(in);
    const std::vector<int> starts{0, 2}, sizes{2, 2};
    for (int boundary = selected_boundary; boundary == selected_boundary; ++boundary) {
        for (int mode = selected_mode; mode == selected_mode; ++mode) {
            resetCounters(); g_fault_kind = FAULT_NONE; g_fault_at = 0;
            g_active = true; g_count_fired = false;
            g_count_error = mode == 0 ? cudaErrorIllegalAddress :
                            mode == 1 ? cudaErrorInitializationError : cudaSuccess;
            bool ok = cudaGetLastError() == cudaSuccess;
            g_count_armed = true;
            std::ostringstream log;
            if (boundary == 0) {
                CudaMovieSession session(NX, NY, NFRAMES, 0, log);
                const bool initialized = session.initialize();
                const CudaFailureState &state = session.getFailureState();
                ok = ok && !initialized && g_count_fired &&
                     state.firstError() == g_count_error &&
                     state.isPoisoned() == (mode == 0) && cudaGetLastError() == cudaSuccess;
                if (mode == 0) {
                    const long calls = g_count_calls;
                    ok = ok && std::string(state.fatalStage()) == "initialize" &&
                         !session.initialize() && g_count_calls == calls;
                } else {
                    ok = ok && session.initialize();
                }
                session.release();
            } else {
                CudaFailureState state;
                std::vector<MultidimArray<fComplex> > output;
                const bool prepared = cudaPreparePatch(in.frames, 0, 32, 0, 32,
                    2, starts, sizes, output, 0, log, &state);
                const cudaError_t pending = cudaGetLastError();
                const CudaRetryDecision decision = cudaRetryDecisionFor(state, pending);
                ok = ok && !prepared && g_count_fired && pending == cudaSuccess &&
                     state.firstError() == g_count_error &&
                     (decision.verdict == CUDA_RETRY_FATAL) == (mode == 0);
                if (mode == 0) {
                    ok = ok && std::string(state.fatalStage()) == "cudaPreparePatch";
                } else {
                    ok = ok && cudaPreparePatch(in.frames, 0, 32, 0, 32,
                        2, starts, sizes, output, 0, log, &state);
                }
            }
            g_count_armed = false; g_active = false;
            ok = ok && totalOutstanding() == 0 && g_stale_releases == 0 && hostInputsIntact(in);
            if (!ok) {
                ++failures;
                std::fprintf(stderr, "FAIL enumeration boundary=%s mode=%s\n",
                    boundary == 0 ? "initialize" : "cudaPreparePatch",
                    mode == 0 ? "fatal" : mode == 1 ? "recoverable" : "zero-devices");
            }
        }
    }
    std::printf("Enumeration control: one production boundary case, failures=%d\n", failures);
    return failures;
}

} // namespace

// A fatal control intentionally retires the process-wide worker cache. A later
// independent trial must use a fresh executable process; clearing runtime errors
// or resetting the CUDA context cannot unretire the production ownership state.
// Spawn before this parent's CUDA initialization and exec (never fork CUDA work).
int runFreshControl(const char *executable, const char *kind, int first, int second = -1) {
    std::string a = std::to_string(first), b = std::to_string(second);
    char *args[] = {const_cast<char *>(executable), const_cast<char *>(kind),
                    &a[0], second < 0 ? nullptr : &b[0], nullptr};
    pid_t pid;
    const int error = posix_spawnp(&pid, executable, nullptr, nullptr, args, environ);
    if (error) {
        std::fprintf(stderr, "FAIL isolated control spawn error=%d\n", error);
        return 1;
    }
    int status = 0;
    pid_t result;
    do { result = waitpid(pid, &status, 0); } while (result < 0 && errno == EINTR);
    if (result != pid || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        std::fprintf(stderr, "FAIL isolated control kind=%s first=%d second=%d status=%d\n",
                     kind, first, second, status);
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    // Strict selectors keep unknown/malformed controls from accidentally running
    // the default matrix and reporting an unrelated success.
    int selected_mode = -1, selected_boundary = -1;
    const bool ownership = argc == 3 && std::string(argv[1]) == "--ownership-control";
    const bool enumeration = argc == 4 && std::string(argv[1]) == "--enumeration-control";
    if (ownership) {
        if (std::string(argv[2]).size() != 1 || argv[2][0] < '0' || argv[2][0] > '3') return 1;
        selected_mode = argv[2][0] - '0';
    } else if (enumeration) {
        if (std::string(argv[2]).size() != 1 || argv[2][0] < '0' || argv[2][0] > '1' ||
            std::string(argv[3]).size() != 1 || argv[3][0] < '0' || argv[3][0] > '2') return 1;
        selected_boundary = argv[2][0] - '0'; selected_mode = argv[3][0] - '0';
    } else if (argc != 1) {
        std::fprintf(stderr, "Unknown fault-matrix control selector\n");
        return 1;
    }
    int failures = 0;
    if (argc == 1) {
        for (int mode = 0; mode < 4; ++mode)
            failures += runFreshControl(argv[0], "--ownership-control", mode);
        for (int boundary = 0; boundary < 2; ++boundary)
            for (int mode = 0; mode < 3; ++mode)
                failures += runFreshControl(argv[0], "--enumeration-control", boundary, mode);
    }
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::fprintf(stderr, "CUDA device 0 is required for this control\n");
        return 1;
    }

    if (ownership) return runOwnershipControls(selected_mode);
    if (enumeration) return runEnumerationControls(selected_boundary, selected_mode);

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
                "primitive", "n", "stage reached", "exit", "owned", "inputs");

    // One oracle for both sweeps.
    //
    // Normal case: the fault must have fired, the scenario must NOT have completed, it
    // must not have escaped as an unexpected exception type, nothing owned may be
    // outstanding, and borrowed inputs must be unchanged.
    //
    // Teardown case: the fault landed in CudaMovieSession::release()'s deliberately
    // non-fatal synchronise. Production documents that as survivable, so completing is
    // the correct outcome there -- but nothing may leak.
    struct Oracle {
        static bool ok(const TrialResult &r, std::string &why) {
            if (!r.fault_fired)                              { why = "site not reached"; return false; }
            if (r.exit_mechanism == "threw unexpected exception") { why = "unexpected exception type"; return false; }
            if (r.leaked != 0)                               { why = "leaked owned resources"; return false; }
            if (!r.products_ok)                              { why = "borrowed inputs changed"; return false; }
            if (r.fault_in_teardown) {
                if (r.exit_mechanism != "completed") { why = "best-effort teardown fault was not survived"; return false; }
                why = "teardown (best-effort, survived)";
                return true;
            }
            if (r.exit_mechanism == "completed")             { why = "fault fired but the run completed"; return false; }
            why = "";
            return true;
        }
    };

    int trials = 0;
    for (int k = FAULT_MALLOC; k < FAULT_KIND_COUNT; k++) {
        for (long n = 1; n <= budget[k]; n++) {
            const TrialResult r = runTrial((FaultKind)k, n, 1);
            trials++;
            std::string why;
            const bool ok = Oracle::ok(r, why);
            std::printf("%-24s %-4ld %-34s %-22s %-7zu %-8s %s%s\n",
                        faultName((FaultKind)k), n,
                        r.last_stage.empty() ? "(not entered)" : r.last_stage.c_str(),
                        r.exit_mechanism.empty() ? "(none)" : r.exit_mechanism.c_str(),
                        r.leaked, r.products_ok ? "intact" : "DAMAGED",
                        ok ? "" : "  <-- FAIL: ", why.c_str());
            if (!ok) failures++;
        }
    }

    // Successive movies with the fault on the last one: exposes cross-movie leaks and
    // stale cache state that a single-movie trial cannot see.
    // Counters are cumulative across the three movies in a trial, so ordinal
    // budget[k]*3 is the LAST call of that kind in the third movie -- late enough that
    // two whole movies have already completed, which is what exposes cross-movie leaks
    // and stale cache state. If a movie ever issues a different number of calls than
    // the baseline the site is simply not reached, and the oracle says so rather than
    // failing for an unexplained reason.
    std::printf("\nSuccessive-movie trials (3 movies, fault on the last call of that\n"
                "kind in the third movie):\n");
    for (int k = FAULT_MALLOC; k <= FAULT_D2H; k++) {
        const long n = budget[k] * 3;
        if (n == 0) continue;
        const TrialResult r = runTrial((FaultKind)k, n, 3);
        trials++;
        std::string why;
        const bool ok = Oracle::ok(r, why);
        std::printf("%-24s %-4ld %-34s %-22s %-7zu %-8s %s%s\n",
                    faultName((FaultKind)k), n,
                    r.last_stage.empty() ? "(not entered)" : r.last_stage.c_str(),
                    r.exit_mechanism.empty() ? "(none)" : r.exit_mechanism.c_str(),
                    r.leaked, r.products_ok ? "intact" : "DAMAGED",
                    ok ? "" : "  <-- FAIL: ", why.c_str());
        if (!ok) failures++;
    }

    std::printf("\n%d trials, %d failures\n", trials, failures);
    if (failures) return 1;
    std::printf("PASS every injected fault left the scenario without completing (or was\n"
                "     survived, where production documents the path as best-effort), and\n"
                "     released every tracked device allocation, cuFFT plan and CUDA event.\n"
                "     NOT covered: cuFFT's internal workspace allocations happen inside\n"
                "     libcufft and never reach the interposed cudaMalloc, so they are\n"
                "     outside this leak accounting. Borrowed-input immutability is\n"
                "     already enforced by const in the production signatures; the check\n"
                "     here is a standing guard, not a demonstration.\n");
    return 0;
}
