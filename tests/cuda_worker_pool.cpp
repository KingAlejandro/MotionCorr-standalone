// Native controls for worker-lifetime CUDA resource reuse.
//
// Every control drives the production entry points -- CudaMovieSession and
// mc_cuda::CudaWorkerPool -- on a real device. Interposition is confined to this
// executable and injects RETURNED STATUS only: it does not poison real hardware,
// and cuFFT's own internal allocations are outside this accounting.
//
// Two things each control has to establish, not one: that the healthy path still
// computes the same bytes, and that the failing path leaves no resource owned by
// nobody, no key attached to something that no longer exists, and no verdict that
// says "retry" after a context has died.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_worker_pool.h"
#include "src/acc/cuda/cuda_error_class.h"
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

namespace {

enum Boundary { NONE, MALLOC, FREE, PLAN_CREATE, PLAN_MAKE, PLAN_DESTROY,
                SET_WORK_AREA, MEMCPY, SET_DEVICE, BOUNDARIES };

bool active = false, fired = false, fatal = false;
Boundary fault = NONE;
int ordinal = 0, counts[BOUNDARIES] = {};
std::set<void *> buffers;
std::set<cufftHandle> plans;
size_t stale = 0;
bool fatal_free_once = false;
std::vector<int> device_selections;

bool fail(Boundary boundary) {
    if (!active) return false;
    const int seen = ++counts[boundary];
    if (boundary != fault || seen != ordinal) return false;
    fired = true;
    return true;
}
cudaError_t code() { return fatal ? cudaErrorIllegalAddress : cudaErrorMemoryAllocation; }
void arm(Boundary boundary = NONE, int at = 0, bool poison = false) {
    std::memset(counts, 0, sizeof(counts));
    fault = boundary; ordinal = at; fatal = poison; fired = false;
    fatal_free_once = false;
    device_selections.clear();
    active = true;
}
size_t outstanding() { return buffers.size() + plans.size(); }
void disarm() { active = false; }
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
void requireEmpty(const char *where) {
    if (!buffers.empty() || !plans.empty() || stale != 0) {
        std::ostringstream m;
        m << where << ": " << buffers.size() << " buffer(s) and " << plans.size()
          << " plan(s) outstanding, " << stale << " stale release(s)";
        throw std::runtime_error(m.str());
    }
}

} // namespace

extern "C" {
cudaError_t __real_cudaMalloc(void **, size_t);
cudaError_t __real_cudaFree(void *);
cudaError_t __real_cudaMemcpy(void *, const void *, size_t, cudaMemcpyKind);
cudaError_t __real_cudaSetDevice(int);
cufftResult __real_cufftCreate(cufftHandle *);
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int *, int *, int, int,
                                     int *, int, int, cufftType, int, size_t *);
cufftResult __real_cufftDestroy(cufftHandle);
cufftResult __real_cufftSetWorkArea(cufftHandle, void *);

// The ledger is ALWAYS on; only injection is gated by arm()/disarm(). An
// allocation made with injection off and freed with it on would otherwise be
// counted as a double free, and a resource retained across a disarmed window
// would be invisible. Everything the harness itself allocates uses __real_*, so
// only production allocations are in here.
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (fail(MALLOC)) { *ptr = nullptr; return code(); }
    const cudaError_t result = __real_cudaMalloc(ptr, bytes);
    if (result == cudaSuccess) buffers.insert(*ptr);
    return result;
}
cudaError_t __wrap_cudaFree(void *ptr) {
    const bool inject = fail(FREE);
    const cudaError_t result = __real_cudaFree(ptr);
    // A pointer this harness never saw allocated is either a double free or a
    // free of something another owner still believes it holds. Either is the
    // defect, so count it rather than letting the call look clean.
    if (ptr && result == cudaSuccess && !buffers.erase(ptr)) ++stale;
    if (active && fatal_free_once) { fatal_free_once = false; return cudaErrorIllegalAddress; }
    return inject && result == cudaSuccess ? code() : result;
}
cudaError_t __wrap_cudaMemcpy(void *dst, const void *src, size_t bytes, cudaMemcpyKind kind) {
    if (fail(MEMCPY)) return code();
    return __real_cudaMemcpy(dst, src, bytes, kind);
}
cudaError_t __wrap_cudaSetDevice(int device) {
    if (active) device_selections.push_back(device);
    if (fail(SET_DEVICE)) {
        (void)cudaGetLastError();
        return cudaErrorInvalidDevice; // No real selection: current device stays put.
    }
    return __real_cudaSetDevice(device);
}
cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (fail(PLAN_CREATE)) return CUFFT_ALLOC_FAILED;
    const cufftResult result = __real_cufftCreate(plan);
    if (result == CUFFT_SUCCESS) plans.insert(*plan);
    return result;
}
cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n, int *inembed,
                                     int istride, int idist, int *onembed, int ostride,
                                     int odist, cufftType type, int batch, size_t *work) {
    if (fail(PLAN_MAKE)) return CUFFT_ALLOC_FAILED;
    return __real_cufftMakePlanMany(plan, rank, n, inembed, istride, idist,
                                    onembed, ostride, odist, type, batch, work);
}
cufftResult __wrap_cufftSetWorkArea(cufftHandle plan, void *area) {
    if (fail(SET_WORK_AREA)) return CUFFT_INTERNAL_ERROR;
    return __real_cufftSetWorkArea(plan, area);
}
cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const bool inject = fail(PLAN_DESTROY);
    const cufftResult result = __real_cufftDestroy(plan);
    if (result == CUFFT_SUCCESS && !plans.erase(plan)) ++stale;
    return inject && result == CUFFT_SUCCESS ? CUFFT_INTERNAL_ERROR : result;
}
} // extern "C"

namespace {

// ------------------------------------------------------------------ fixture --

struct Movie {
    int nx = 0, ny = 0, n_frames = 0, n_groups = 0;
    unsigned seed = 1;
    bool with_gain = true;
    unsigned long long gain_generation = 1;
    // Record a recoverable, non-poisoning failure early in the movie and carry
    // on, which is the shape of the nvCOMP ingest declining and falling back to
    // the host reader. Everything after it runs with a sticky hasFailed().
    bool early_recoverable_failure = false;
    int device = 0;
};

// Everything one session produces, for byte comparison against another session.
struct Products {
    bool ok = false;
    std::vector<float> unaligned_sum;
    std::vector<cufftComplex> fourier;
    std::vector<cufftComplex> patch;
    std::vector<float> reconstruction;
};

std::vector<float> syntheticFrames(const Movie &m) {
    std::vector<float> data((size_t)m.nx * m.ny * m.n_frames);
    unsigned state = m.seed;
    for (auto &v : data) {
        state = 1664525u * state + 1013904223u;
        v = (float)((int)(state >> 16 & 65535u) - 32768) / 256.0f;
    }
    return data;
}

MultidimArray<float> syntheticGain(const Movie &m, unsigned salt) {
    MultidimArray<float> gain;
    gain.reshape(m.ny, m.nx);
    unsigned state = 7919u + salt;
    for (long int i = 0; i < (long int)((size_t)m.nx * m.ny); ++i) {
        state = 1664525u * state + 1013904223u;
        DIRECT_MULTIDIM_ELEM(gain, i) = 0.75f + (float)(state >> 20 & 1023u) / 2048.0f;
    }
    return gain;
}

// Drive one movie through the production session, pool or no pool, and return
// every product it computed. Interposition is off during fixture setup and
// teardown so the harness's own allocations never enter the accounting.
Products runMovie(const Movie &m, mc_cuda::CudaWorkerPool *pool, unsigned gain_salt,
                  std::ostringstream &log, CudaFailureState *out_failure = nullptr) {
    const bool armed = active;
    disarm();
    const std::vector<float> host = syntheticFrames(m);
    const MultidimArray<float> gain = syntheticGain(m, gain_salt);
    std::vector<Image<float> > frames(m.n_frames);
    for (int f = 0; f < m.n_frames; ++f) {
        frames[f]().reshape(m.ny, m.nx);
        std::memcpy(frames[f]().data, host.data() + (size_t)f * m.nx * m.ny,
                    (size_t)m.nx * m.ny * sizeof(float));
    }
    const int patch_w = m.nx / 2, patch_h = m.ny / 2;
    const int patch_nfx = patch_w / 2 + 1;
    std::vector<int> group_start(m.n_groups), group_size(m.n_groups);
    for (int g = 0; g < m.n_groups; ++g) {
        group_start[g] = g * (m.n_frames / m.n_groups);
        group_size[g] = m.n_frames / m.n_groups;
    }
    const size_t patch_elems = (size_t)m.n_groups * patch_h * patch_nfx;
    require(__real_cudaSetDevice(m.device) == cudaSuccess, "harness setDevice");
    cufftComplex *d_patch = nullptr;
    require(__real_cudaMalloc((void **)&d_patch, patch_elems * sizeof(cufftComplex)) == cudaSuccess,
            "harness patch buffer");

    Products out;
    MultidimArray<float> sum;
    Image<float> reconstructed;
    reconstructed().reshape(m.ny, m.nx);
    std::vector<RFLOAT> doses(m.n_frames);
    for (int f = 0; f < m.n_frames; ++f) doses[f] = 1.0 + 0.25 * f;

    {
        CudaMovieSession session(m.nx, m.ny, m.n_frames, m.device, log, pool);
        session.setGainIdentity(m.gain_generation);
        active = armed;
        bool ok = session.initialize();
        if (ok && m.early_recoverable_failure) {
            // One failing device-to-host copy, recorded and recovered from.
            MultidimArray<float> scratch;
            (void)session.downloadUnalignedSum(scratch);
        }
        if (ok) ok = session.applyGainDefectsAndSum(frames, m.with_gain ? &gain : nullptr, sum, true);
        if (ok) ok = session.releasePreprocessingBuffers();
        if (ok) ok = session.computeGlobalForwardFFT();
        std::vector<MultidimArray<fComplex> > fframes;
        if (ok) ok = session.downloadFourierFrames(fframes);
        if (ok) ok = session.preparePatchInVram(0, 0, patch_w, patch_h, m.n_groups,
                                                group_start.data(), group_size.data(), d_patch);
        if (ok) ok = session.reconstructDoseWeighted(reconstructed, doses, 0.885, nullptr);
        if (ok) require(session.releasePatchAlignmentWorkspace(), "workspace release");
        out.ok = ok;
        if (ok) {
            out.unaligned_sum.assign(sum.data, sum.data + (size_t)m.nx * m.ny);
            for (const auto &f : fframes)
                for (long int i = 0; i < (long int)((size_t)m.ny * (m.nx / 2 + 1)); ++i) {
                    cufftComplex c;
                    c.x = DIRECT_MULTIDIM_ELEM(f, i).real;
                    c.y = DIRECT_MULTIDIM_ELEM(f, i).imag;
                    out.fourier.push_back(c);
                }
            out.patch.resize(patch_elems);
            const bool was = active;
            disarm();
            require(__real_cudaMemcpy(out.patch.data(), d_patch,
                                      patch_elems * sizeof(cufftComplex),
                                      cudaMemcpyDeviceToHost) == cudaSuccess, "patch download");
            active = was;
            out.reconstruction.assign(reconstructed().data,
                                      reconstructed().data + (size_t)m.nx * m.ny);
        }
        if (out_failure) *out_failure = session.getFailureState();
        // session destructor runs here, still armed: its release path is part of
        // what every control is checking.
    }
    disarm();
    __real_cudaFree(d_patch);
    active = armed;
    return out;
}

template <class T>
bool sameBytes(const std::vector<T> &a, const std::vector<T> &b) {
    return a.size() == b.size() &&
           (a.empty() || std::memcmp(a.data(), b.data(), a.size() * sizeof(T)) == 0);
}
void exact(const Products &a, const Products &b, const char *what) {
    require(a.ok && b.ok, what);
    require(sameBytes(a.unaligned_sum, b.unaligned_sum) &&
            sameBytes(a.fourier, b.fourier) &&
            sameBytes(a.patch, b.patch) &&
            sameBytes(a.reconstruction, b.reconstruction), what);
}
void differs(const Products &a, const Products &b, const char *what) {
    require(a.ok && b.ok, what);
    require(!sameBytes(a.unaligned_sum, b.unaligned_sum), what);
}

int passed = 0;
void pass(const std::string &label) { ++passed; std::cout << "PASS: " << label << "\n"; }

const Movie GEOM_A = {64, 48, 4, 2, 11, true, 1};
const Movie GEOM_B = {80, 64, 4, 2, 23, true, 1};

// ------------------------------------------------------------------ controls --

// Cold worker, warm worker, repeated identical geometry. The key must be hit,
// and a hit must produce the same bytes a cold build does.
void warmReuseIsExact() {
    std::ostringstream log;
    disarm();
    const Products cold = runMovie(GEOM_A, nullptr, 0, log);
    require(cold.ok, "cold reference movie failed");

    mc_cuda::CudaWorkerPool pool;
    arm();
    const Products first = runMovie(GEOM_A, &pool, 0, log);
    const Products second = runMovie(GEOM_A, &pool, 0, log);
    const Products third = runMovie(GEOM_A, &pool, 0, log);
    disarm();
    exact(cold, first, "pooled first movie differs from unpooled");
    exact(cold, second, "warm movie 2 differs from unpooled");
    exact(cold, third, "warm movie 3 differs from unpooled");

    const auto &c = pool.counters();
    require(c.gain_builds == 1 && c.gain_hits == 2, "gain was not retained across movies");
    require(c.global_builds == 1 && c.global_hits == 2, "global plans were not retained");
    require(c.patch_builds == 1 && c.patch_hits == 2, "patch plan was not retained");
    require(c.dw_builds == 1 && c.dw_hits == 2, "reconstruction plan was not retained");
    require(pool.retainedBytes().gain > 0, "retained bytes do not report the gain");
    arm();
    require(pool.dropAll(nullptr), "dropAll failed on a healthy pool");
    requireEmpty("warm reuse teardown");
    disarm();
    pass("cold/warm/repeated geometry: 3 movies exact, 1 build + 2 hits per resource class");
}

// A -> B -> A. A complete key means the B movie replaces rather than silently
// reuses, and the second A is still exactly the first A.
void geometryTransition() {
    std::ostringstream log;
    disarm();
    const Products ref_a = runMovie(GEOM_A, nullptr, 0, log);
    const Products ref_b = runMovie(GEOM_B, nullptr, 0, log);

    mc_cuda::CudaWorkerPool pool;
    arm();
    const Products a1 = runMovie(GEOM_A, &pool, 0, log);
    const Products b1 = runMovie(GEOM_B, &pool, 0, log);
    const Products a2 = runMovie(GEOM_A, &pool, 0, log);
    disarm();
    exact(ref_a, a1, "A1 differs from unpooled A");
    exact(ref_b, b1, "B differs from unpooled B");
    exact(ref_a, a2, "A2 after a B geometry differs from unpooled A");
    const auto &c = pool.counters();
    require(c.global_builds == 3 && c.global_hits == 0, "global key matched across geometries");
    require(c.patch_builds == 3 && c.patch_hits == 0, "patch key matched across geometries");
    require(c.dw_builds == 3 && c.dw_hits == 0, "reconstruction key matched across geometries");
    arm();
    require(pool.dropAll(nullptr), "dropAll after transitions");
    requireEmpty("geometry transition teardown");
    disarm();
    pass("A -> B -> A geometry: 3 exact results, every key rebuilt, nothing left over");
}

// Changed frame count must NOT invalidate the whole-frame plans (they are batch
// one, so n_frames is not part of what they describe) and MUST be exact anyway.
// Changed group count MUST invalidate the batched patch plan.
void frameAndGroupCounts() {
    std::ostringstream log;
    Movie four = GEOM_A; four.n_frames = 4; four.n_groups = 2;
    Movie six = GEOM_A;  six.n_frames = 6;  six.n_groups = 2;
    Movie three = GEOM_A; three.n_frames = 6; three.n_groups = 3;
    disarm();
    const Products r4 = runMovie(four, nullptr, 0, log);
    const Products r6 = runMovie(six, nullptr, 0, log);
    const Products r3 = runMovie(three, nullptr, 0, log);

    mc_cuda::CudaWorkerPool pool;
    arm();
    const Products p4 = runMovie(four, &pool, 0, log);
    const unsigned global_after_first = pool.counters().global_builds;
    const Products p6 = runMovie(six, &pool, 0, log);
    const Products p3 = runMovie(three, &pool, 0, log);
    disarm();
    exact(r4, p4, "4-frame movie differs");
    exact(r6, p6, "6-frame movie differs");
    exact(r3, p3, "3-group movie differs");
    const auto &c = pool.counters();
    require(global_after_first == 1 && c.global_builds == 1 && c.global_hits == 2,
            "frame count wrongly invalidated the batch-1 whole-frame plans");
    require(c.patch_builds == 2 && c.patch_hits == 1,
            "group count did not invalidate the batched patch plan");
    arm(); require(pool.dropAll(nullptr), "dropAll"); requireEmpty("counts teardown"); disarm();
    pass("changed frame count reuses the batch-1 plans; changed group count rebuilds the patch plan");
}

// gain A, gain A again, gain B, gain A again, no gain, gain A, failed
// replacement. No stale gain may survive any of them.
void gainIdentity() {
    std::ostringstream log;
    Movie a1 = GEOM_A; a1.gain_generation = 1;
    Movie a2 = GEOM_A; a2.gain_generation = 1;
    Movie b  = GEOM_A; b.gain_generation = 2;
    Movie none = GEOM_A; none.with_gain = false; none.gain_generation = 1;

    disarm();
    const Products ref_gain_a = runMovie(a1, nullptr, 0, log);
    const Products ref_gain_b = runMovie(b, nullptr, 1, log);   // salt 1 == different gain
    const Products ref_nogain = runMovie(none, nullptr, 0, log);
    differs(ref_gain_a, ref_gain_b, "the two test gains produce the same sum; control is blind");
    differs(ref_gain_a, ref_nogain, "gain and no-gain produce the same sum; control is blind");

    mc_cuda::CudaWorkerPool pool;
    arm();
    exact(ref_gain_a, runMovie(a1, &pool, 0, log), "gain A");
    exact(ref_gain_a, runMovie(a2, &pool, 0, log), "gain A repeated");
    require(pool.counters().gain_hits == 1, "identical gain generation did not hit");
    exact(ref_gain_b, runMovie(b, &pool, 1, log), "gain B after gain A");
    exact(ref_gain_a, runMovie(a1, &pool, 0, log), "gain A after gain B");
    exact(ref_nogain, runMovie(none, &pool, 0, log), "no gain after gain A");
    exact(ref_gain_a, runMovie(a1, &pool, 0, log), "gain A after no gain");
    disarm();

    // Failed replacement: the upload for generation 3 fails. Nothing may be
    // published under generation 3, and generation 1 must not survive either --
    // the pool invalidated and freed it before the replacement was attempted.
    Movie c = GEOM_A; c.gain_generation = 3;
    CudaFailureState failure;
    // applyGainDefectsAndSum uploads the frames first, so the gain upload is
    // memcpy n_frames+1. Getting the ordinal wrong would fail an earlier copy
    // and leave the gain untouched, so the retained-bytes assertion below is
    // what proves the injection landed where this control claims.
    arm(MEMCPY, c.n_frames + 1);
    const Products failed = runMovie(c, &pool, 2, log, &failure);
    require(fired && !failed.ok, "injected gain upload failure did not fail the movie");
    require(failure.hasFailed(), "failed gain upload left a clean failure state");
    disarm();
    require(pool.retainedBytes().gain == 0, "a failed gain replacement left a retained gain");
    arm();
    // A later movie under the ORIGINAL generation must re-upload, not match a
    // key that outlived its buffer.
    const unsigned builds_before = pool.counters().gain_builds;
    exact(ref_gain_a, runMovie(a1, &pool, 0, log), "gain A after a failed replacement");
    require(pool.counters().gain_builds == builds_before + 1,
            "stale generation-1 key survived a failed generation-3 replacement");
    require(pool.dropAll(nullptr), "dropAll");
    requireEmpty("gain identity teardown");
    disarm();
    pass("gain A/A/B/A/none/A plus a failed replacement: 7 exact results, no stale gain");
}

// A -> failed B -> A for the plan classes. Each construction step that can fail
// after a handle exists is injected separately: the handle must be destroyed by
// its temporary owner, nothing may be published, and the next healthy movie must
// produce the reference bytes.
void constructionFailures() {
    std::ostringstream log;
    disarm();
    const Products ref_a = runMovie(GEOM_A, nullptr, 0, log);
    int trials = 0;
    // Enough ordinals to cover the global r2c, global c2r, patch and DW plans.
    for (Boundary boundary : {PLAN_CREATE, PLAN_MAKE, SET_WORK_AREA, MALLOC}) {
        const int limit = boundary == SET_WORK_AREA ? 2 : 4;
        for (int at = 1; at <= limit; ++at) {
            mc_cuda::CudaWorkerPool pool;
            arm();
            const Products warm = runMovie(GEOM_A, &pool, 0, log);
            exact(ref_a, warm, "warm-up movie before injection");
            disarm();

            CudaFailureState failure;
            const unsigned evictions_before = pool.counters().evictions;
            arm(boundary, at);
            const Products broken = runMovie(GEOM_B, &pool, 0, log, &failure);
            const bool injected = fired;
            disarm();
            if (!injected) continue;   // that ordinal is not reached for this geometry
            if (broken.ok) {
                // Exactly one path may absorb an injected failure and still
                // succeed: the admission retry, and only by evicting first.
                // Anything else swallowing one is a silent failure.
                require(pool.counters().evictions > evictions_before,
                        "an injected construction failure was absorbed without an eviction");
                exact(ref_a, runMovie(GEOM_A, &pool, 0, log), "movie after an absorbed failure");
                arm(); require(pool.dropAll(nullptr), "dropAll"); disarm();
                continue;              // counted by admissionEviction() instead
            }
            require(failure.hasFailed(), "injected construction failure left a clean state");

            // The pool must not be advertising anything built from the broken
            // construction, and the next movie must be exact.
            arm();
            const Products recovered = runMovie(GEOM_A, &pool, 0, log);
            exact(ref_a, recovered, "movie after an injected construction failure");
            require(pool.dropAll(nullptr), "dropAll after recovery");
            requireEmpty("construction failure teardown");
            disarm();
            ++trials;
        }
    }
    require(trials >= 8, "too few construction-failure ordinals were actually reached");
    std::ostringstream label;
    label << trials << " create/plan/work-area/alloc construction failures: "
             "no leaked handle, no published key, exact recovery";
    pass(label.str());
}

// A drop that fails must fail the acquire. The pool may not construct and
// publish a replacement as though the cleanup had succeeded.
void dropFailuresFailClosed() {
    std::ostringstream log;
    disarm();
    const Products ref_b = runMovie(GEOM_B, nullptr, 0, log);
    const Products ref_a_for_fatal = runMovie(GEOM_A, nullptr, 0, log);

    // Geometry transition with each pooled plan's destroy failing in turn. One
    // ordinal would only ever reach whichever class is dropped first, so the
    // other three acquires would be unobserved.
    int drop_trials = 0;
    for (int at = 1; at <= 4; ++at) {
        mc_cuda::CudaWorkerPool pool;
        arm();
        require(runMovie(GEOM_A, &pool, 0, log).ok, "warm-up");
        disarm();
        CudaFailureState failure;
        arm(PLAN_DESTROY, at);
        const Products broken = runMovie(GEOM_B, &pool, 0, log, &failure);
        const bool injected = fired;
        disarm();
        if (!injected) continue;
        require(!broken.ok, "a failed drop still produced a published replacement");
        require(failure.hasFailed(), "a failed drop left a clean failure state");
        arm();
        require(pool.dropAll(nullptr), "dropAll after a failed-drop transition");
        requireEmpty("failed drop teardown");
        disarm();
        ++drop_trials;
    }
    require(drop_trials >= 3, "too few pooled plan drops were actually exercised");

    // Late fatal cleanup: the free that releases the retained gain returns a
    // poisoning code. The verdict must be "do not retry", and the pool must be
    // retired rather than left holding handles from a dead context.
    mc_cuda::CudaWorkerPool fatal_pool;
    arm();
    require(runMovie(GEOM_A, &fatal_pool, 0, log).ok, "warm-up for the late fatal control");
    disarm();
    CudaFailureState fatal_failure;
    arm();
    fatal_free_once = true;
    const Products after_fatal = runMovie(GEOM_B, &fatal_pool, 0, log, &fatal_failure);
    disarm();
    require(fatal_failure.isPoisoned(), "a poisoning cleanup code was not latched");
    require(cudaRetryDecisionFor(fatal_failure, cudaSuccess).verdict == CUDA_RETRY_FATAL,
            "a poisoned context still permitted a retry");
    (void)after_fatal;
    require(fatal_pool.retiredFor(0), "a poisoned context did not retire the pool");
    require(fatal_pool.retainedBytes().total() == 0, "a retired pool still advertises bytes");
    // Retirement attempts the same checked release as every other path, so the
    // pool's bytes go back even though the context is dead. Skipping it would
    // leak them for the life of the process.
    requireEmpty("retired pool did not release what it was holding");

    // A fresh session's clean failure state must not resurrect the retired pool.
    const unsigned hits_before = fatal_pool.counters().gain_hits +
                                 fatal_pool.counters().global_hits +
                                 fatal_pool.counters().patch_hits +
                                 fatal_pool.counters().dw_hits;
    arm();
    const Products reuse = runMovie(GEOM_A, &fatal_pool, 0, log);
    disarm();
    const unsigned hits_after = fatal_pool.counters().gain_hits +
                                fatal_pool.counters().global_hits +
                                fatal_pool.counters().patch_hits +
                                fatal_pool.counters().dw_hits;
    require(hits_after == hits_before,
            "a retired pool served a retained resource to a later clean session");
    require(reuse.ok, "a session could not fall back to owning everything after a retired pool");
    exact(ref_a_for_fatal, reuse, "the fallback session after a retired pool is not exact");
    requireEmpty("fallback session after a retired pool");
    (void)ref_b;
    std::ostringstream dl;
    dl << drop_trials << " pooled plan drops fail the acquire closed; "
          "a late fatal free retires the pool and refuses retry";
    pass(dl.str());
}

// One active lease. A refused second holder must change nothing, and the first
// holder must keep working across the refusal.
void leaseExclusion() {
    std::ostringstream log;
    mc_cuda::CudaWorkerPool pool;
    const int a_holder = 0, b_holder = 0;
    const void *A = &a_holder, *B = &b_holder;

    require(pool.acquireLease(A), "first lease refused");
    require(!pool.acquireLease(B), "second lease admitted");
    require(pool.leasedBy(A) && !pool.leasedBy(B), "lease holder wrong after refusal");

    // A builds and uses resources under its lease.
    cufftHandle plan = 0;
    size_t work = 0;
    arm();
    require(pool.acquireDwPlan(A, 0, 64, 48, plan, work, nullptr), "A could not acquire");
    const cufftHandle a_plan = plan;
    require(a_plan != 0, "A got a null plan");

    // B is refused everything, repeatedly, and its refusal drops nothing of A's.
    for (int attempt = 0; attempt < 3; ++attempt) {
        cufftHandle b_plan = 0; size_t b_work = 0;
        require(!pool.acquireDwPlan(B, 0, 80, 64, b_plan, b_work, nullptr),
                "B acquired a plan without the lease");
        require(pool.acquireGain(B, 0, 64, 48, 1, nullptr, nullptr) == nullptr,
                "B acquired the gain without the lease");
        mc_cuda::GlobalFftLease b_lease;
        require(!pool.acquireGlobalFft(B, 0, 80, 64, 41, b_lease, nullptr),
                "B acquired global resources without the lease");
        require(!pool.releaseLease(B), "B released a lease it does not hold");
    }
    require(pool.retainedBytes().dw_plan == work, "B's refusals changed A's retained bytes");

    // A executes a REAL transform on its plan after the refusals.
    auto execute = [&](cufftHandle p) {
        const bool was = active; disarm();
        cufftComplex *in = nullptr; float *out = nullptr;
        require(__real_cudaMalloc((void **)&in, (size_t)48 * 33 * sizeof(cufftComplex)) == cudaSuccess, "in");
        require(__real_cudaMalloc((void **)&out, (size_t)48 * 64 * sizeof(float)) == cudaSuccess, "out");
        require(cudaMemset(in, 0, (size_t)48 * 33 * sizeof(cufftComplex)) == cudaSuccess, "memset");
        const cufftResult r = cufftExecC2R(p, in, out);
        const cudaError_t s = cudaDeviceSynchronize();
        __real_cudaFree(in); __real_cudaFree(out);
        active = was;
        return r == CUFFT_SUCCESS && s == cudaSuccess;
    };
    require(execute(a_plan), "A's plan stopped working after B was refused");

    // A releases; only now may B acquire, and its plan must work too.
    require(pool.releaseLease(A), "A could not release its own lease");
    require(pool.acquireLease(B), "B could not acquire the freed lease");
    cufftHandle b_plan = 0; size_t b_work = 0;
    require(pool.acquireDwPlan(B, 0, 64, 48, b_plan, b_work, nullptr), "B acquire after handover");
    require(b_plan == a_plan, "B rebuilt a plan the pool already held at the same key");
    require(execute(b_plan), "B's plan does not execute after the handover");
    require(pool.releaseLease(B), "B release");
    require(pool.dropAll(nullptr), "dropAll");
    requireEmpty("lease teardown");
    disarm();
    require(pool.counters().lease_refusals == 0, "refusals counted without a session reporting them");
    pass("exclusive lease: B refused 9 times, A keeps and executes its resources, B works after handover");
}

// A session that cannot take the lease must still work -- owning everything
// itself -- and must not disturb the holder.
void refusedSessionFallsBack() {
    std::ostringstream log;
    disarm();
    const Products reference = runMovie(GEOM_A, nullptr, 0, log);
    mc_cuda::CudaWorkerPool pool;
    const int token = 0;
    require(pool.acquireLease(&token), "pre-lease");
    arm();
    const Products refused = runMovie(GEOM_A, &pool, 0, log);
    disarm();
    exact(reference, refused, "a lease-refused session produced different bytes");
    require(pool.counters().lease_refusals == 1, "the refusal was not counted");
    require(pool.retainedBytes().total() == 0, "a refused session published into the pool");
    require(pool.leasedBy(&token), "a refused session stole or cleared the lease");
    require(pool.releaseLease(&token), "release");
    requireEmpty("refused session teardown");
    pass("a lease-refused session owns its own resources, is exact, and leaves the holder's lease intact");
}

// Admission pressure: the first attempt at the movie buffers fails, the pool
// releases what nobody is using, and the retry succeeds.
void admissionEviction() {
    std::ostringstream log;
    disarm();
    const Products reference = runMovie(GEOM_A, nullptr, 0, log);
    mc_cuda::CudaWorkerPool pool;
    arm();
    require(runMovie(GEOM_A, &pool, 0, log).ok, "warm-up");
    disarm();
    require(pool.retainedBytes().total() > 0, "nothing retained before the pressure control");

    // First cudaMalloc of the next session is d_Iframes.
    arm(MALLOC, 1);
    const Products recovered = runMovie(GEOM_A, &pool, 0, log);
    const bool injected = fired;
    disarm();
    require(injected, "the admission failure was never injected");
    exact(reference, recovered, "the movie admitted after eviction differs");
    require(pool.counters().evictions == 1, "no eviction happened on admission pressure");
    arm(); require(pool.dropAll(nullptr), "dropAll"); requireEmpty("eviction teardown"); disarm();

    // Negative control: the same injection with no pool must still fail, so the
    // control above is observing the retry and not a harmless injection.
    arm(MALLOC, 1);
    const Products no_pool = runMovie(GEOM_A, nullptr, 0, log);
    disarm();
    require(!no_pool.ok, "the injected admission failure is not fatal without a pool; "
                         "the eviction control proves nothing");
    pass("admission pressure evicts unused retained resources and retries once; "
         "the same injection without a pool still fails");
}

// A recoverable failure earlier in the movie must not turn a later pool DECLINE
// into a movie failure. The session's failure state is sticky for the whole
// movie, so "did the pool fail?" cannot be answered by reading it: it has to be
// compared across the acquire.
void declineAfterRecoverableFailure() {
    std::ostringstream log;
    Movie no_identity = GEOM_A;
    no_identity.gain_generation = 0;   // the pool declines the gain, by contract
    disarm();
    const Products reference = runMovie(no_identity, nullptr, 0, log);
    require(reference.ok, "reference movie with no gain identity failed");

    mc_cuda::CudaWorkerPool pool;
    arm();
    require(runMovie(no_identity, &pool, 0, log).ok, "warm-up");
    disarm();
    require(pool.retainedBytes().gain == 0, "the pool retained a gain with no identity");
    require(pool.retainedBytes().total() > 0, "nothing retained to evict");

    // One failing D2H copy, recorded and recovered from, before anything that
    // consults the pool. The injection is consumed by that one call, so the rest
    // of the movie runs on a healthy device with a sticky hasFailed().
    Movie carrying = no_identity;
    carrying.early_recoverable_failure = true;
    CudaFailureState failure;
    arm(MEMCPY, 1);
    const Products recovered = runMovie(carrying, &pool, 0, log, &failure);
    const bool injected = fired;
    disarm();
    require(injected, "the recoverable failure was never injected");
    require(failure.hasFailed() && !failure.isPoisoned(),
            "the control needs a recorded, non-poisoning failure to be meaningful");
    exact(reference, recovered,
          "a pool decline after a recoverable failure was treated as a pool failure");

    // The pool half of the same invariant: a decline must record nothing, so the
    // session's comparison has something to compare against.
    CudaFailureState probe;
    const int token = 0;
    require(pool.acquireLease(&token), "probe lease");
    const float host = 1.0f;
    require(pool.acquireGain(&token, 0, 1, 1, 0, &host, &probe) == nullptr,
            "the pool served a gain with no identity");
    require(!probe.hasFailed(), "a pool DECLINE recorded a failure");
    require(pool.releaseLease(&token), "probe release");

    arm(); require(pool.dropAll(nullptr), "dropAll"); requireEmpty("decline teardown"); disarm();
    pass("a pool decline after an earlier recoverable failure still completes the movie exactly, "
         "and a decline records no failure");
}

// The admission retry allocates after an eviction that selected the OWNING
// device of whatever it released. If the retry does not re-select the device
// this movie asked for, it allocates on the wrong one. Needs two devices.
void admissionRetryOnAnotherDevice(int device_count) {
    if (device_count < 2) {
        std::cout << "SKIP: cross-device admission-retry control needs 2 visible "
                     "devices, found " << device_count << "\n";
        return;
    }
    std::ostringstream log;
    Movie on_one = GEOM_A; on_one.device = 1;
    disarm();
    const Products reference = runMovie(on_one, nullptr, 0, log);
    require(reference.ok, "device-1 reference movie failed");

    // Warm the pool on device 0, so the eviction below has device-0 entries to
    // destroy and therefore selects device 0 part-way through.
    mc_cuda::CudaWorkerPool pool;
    arm();
    require(runMovie(GEOM_A, &pool, 0, log).ok, "device-0 warm-up");
    disarm();
    require(pool.retainedBytes().total() > 0, "nothing retained on device 0");

    arm(MALLOC, 1);
    const Products recovered = runMovie(on_one, &pool, 0, log);
    const bool injected = fired;
    disarm();
    require(injected, "the admission failure was never injected");
    exact(reference, recovered,
          "the movie admitted after a cross-device eviction differs");
    require(pool.counters().evictions == 1, "no eviction happened");
    arm(); require(pool.dropAll(nullptr), "dropAll");
    requireEmpty("cross-device admission teardown"); disarm();
    require(__real_cudaSetDevice(0) == cudaSuccess, "restore device 0");
    pass("admission retry after an eviction that selected another device still "
         "allocates on the requested one");
}

// Device-correct cleanup. Requires two devices to be discriminating; with one
// visible device it is reported as skipped rather than passed.
void deviceRestoration(int device_count) {
    if (device_count < 2) {
        std::cout << "SKIP: cross-device cleanup/restoration control needs 2 visible "
                     "devices, found " << device_count << "\n";
        return;
    }
    std::ostringstream log;
    mc_cuda::CudaWorkerPool pool;
    const int token = 0;
    require(pool.acquireLease(&token), "lease");
    cufftHandle plan = 0; size_t work = 0;
    require(pool.acquireDwPlan(&token, 0, 64, 48, plan, work, nullptr), "device 0 build");

    // Same key, different device: the pool must drop on device 0 and then build
    // on device 1, in that order.
    arm();
    cufftHandle plan1 = 0; size_t work1 = 0;
    require(pool.acquireDwPlan(&token, 1, 64, 48, plan1, work1, nullptr), "device 1 build");
    disarm();
    require(!device_selections.empty(), "no device selection at all across the transition");
    require(device_selections.front() == 0, "cleanup did not select the owning device");
    require(device_selections.back() == 1, "construction did not re-select the requested device");
    int current = -1;
    require(cudaGetDevice(&current) == cudaSuccess && current == 1,
            "the pool left the wrong current device after building on another one");
    require(pool.releaseLease(&token), "release");
    arm(); require(pool.dropAll(nullptr), "dropAll"); requireEmpty("device teardown"); disarm();
    require(__real_cudaSetDevice(0) == cudaSuccess, "restore device 0");
    pass("cross-device replacement: cleanup selects the owning device, construction re-selects the requested one");
}

// Selection failure must not destroy under the unrelated current context or
// abandon owned handles. One device powers the returned-status boundary; with
// two devices the current context is physically distinct from the owner.
void failedDeviceSelectionRetainsOwnership(int device_count) {
    std::vector<float> gain(80 * 64, 1.0f);
    int trials = 0;
    for (int resource = 0; resource < 4; ++resource) {
        for (int action = 0; action < 4; ++action) {
            mc_cuda::CudaWorkerPool pool;
            const int token = 0;
            auto acquire = [&](bool replacement, CudaFailureState *failure) {
                const int nx = replacement ? 80 : 64, ny = replacement ? 64 : 48;
                cufftHandle plan = 0; size_t work = 0;
                mc_cuda::GlobalFftLease global;
                if (resource == 0) return pool.acquireGain(&token, 0, nx, ny,
                    replacement ? 2 : 1, gain.data(), failure) != nullptr;
                if (resource == 1) return pool.acquireGlobalFft(&token, 0, nx, ny,
                    nx / 2 + 1, global, failure);
                if (resource == 2) return pool.acquirePatchPlan(&token, 0, nx / 2,
                    ny / 2, 3, plan, failure);
                return pool.acquireDwPlan(&token, 0, nx, ny, plan, work, failure);
            };
            arm();
            require(pool.acquireLease(&token) && acquire(false, nullptr), "selection-fault warm-up");
            require(pool.releaseLease(&token), "selection-fault warm lease release");
            const auto owned_buffers = buffers;
            const auto owned_plans = plans;
            const size_t retained = pool.retainedBytes().total();
            require(!owned_buffers.empty() || !owned_plans.empty(),
                    "selection-fault needs an owned resource");
            const int current = device_count > 1 ? 1 : 0;
            require(__real_cudaSetDevice(current) == cudaSuccess, "set unrelated current device");
            CudaFailureState failure;
            bool released = false, clean = false;
            arm(SET_DEVICE, 1);
            if (action == 0) {
                require(pool.acquireLease(&token), "replacement lease");
                clean = acquire(true, &failure);
                require(pool.releaseLease(&token), "replacement lease release");
            } else if (action == 1) clean = pool.evictUnused(&failure, &released);
            else if (action == 2) clean = pool.dropAll(&failure);
            else {
                failure.record(cudaErrorIllegalAddress, "injected fatal before retirement", 1);
                clean = pool.retireForFatalContext(0, &failure);
                require(pool.retiredFor(0), "selection-failed retirement not sticky");
            }
            require(fired && !clean, "owning-device selection failure did not fail cleanup");
            require(counts[FREE] == 0 && counts[PLAN_DESTROY] == 0,
                    "selection failure issued wrong-context release");
            require(buffers == owned_buffers && plans == owned_plans &&
                    pool.retainedBytes().total() == retained,
                    "selection failure discarded pending ownership");
            require(!released && pool.counters().evictions == 0,
                    "selection failure falsely reported eviction");
            require(failure.hasFailed(), "selection failure status lost");
            int actual = -1;
            require(cudaGetDevice(&actual) == cudaSuccess && actual == current,
                    "failure control accidentally selected the owning device");
            // An invalidated old key must not serve a hit even while its
            // resources are still owned and a fresh caller's state is clean.
            if (action != 3) {
                require(pool.acquireLease(&token), "pending ownership lease");
                CudaFailureState retry_failure;
                arm(SET_DEVICE, 1);
                require(!acquire(false, &retry_failure) && fired,
                        "selection failure left a reusable published key");
                require(counts[FREE] == 0 && counts[PLAN_DESTROY] == 0 &&
                        counts[MALLOC] == 0 && counts[PLAN_CREATE] == 0,
                        "pending ownership was overwritten or released without selection");
                require(pool.releaseLease(&token), "pending ownership lease release");
            }
            arm();
            if (action == 1) {
                require(pool.evictUnused(nullptr, &released) && released,
                        "eviction did not retry unpublished owned entry");
            } else require(pool.dropAll(nullptr), "checked pending-owner retry failed");
            requireEmpty("selection-failure checked retry");
            require(pool.retainedBytes().total() == 0, "retry left retained bytes");
            if (action == 3) require(pool.retiredFor(0), "cleanup retry resurrected retired pool");
            require(pool.dropAll(nullptr), "pending cleanup retry not idempotent");
            require(__real_cudaSetDevice(0) == cudaSuccess, "restore device0");
            disarm(); ++trials;
        }
    }
    std::ostringstream result;
    result << trials << " owning-device selection failures retain ownership, refuse reuse, "
              "and retry checked cleanup; " << (device_count > 1 ? "two real device contexts" : "one-device returned-status control");
    pass(result.str());
}

} // namespace

int main(int argc, char **argv) {
    const bool cleanup_only = argc == 3 && std::string(argv[1]) == "--case" &&
                              std::string(argv[2]) == "device-cleanup";
    if (argc != 1 && !cleanup_only) {
        std::cerr << "Usage: cuda_worker_pool [--case device-cleanup]\n"; return 1;
    }
    int device_count = 0;
    if (cudaGetDeviceCount(&device_count) != cudaSuccess || device_count == 0) {
        std::cerr << "FAIL: no CUDA device; these controls assert nothing without one\n";
        return 1;
    }
    if (cudaSetDevice(0) != cudaSuccess) {
        std::cerr << "FAIL: cannot select device 0\n";
        return 1;
    }
    // Warm the context so the first measured allocation is not a context create.
    void *warm = nullptr;
    if (cudaMalloc(&warm, 1024) != cudaSuccess) {
        std::cerr << "FAIL: device 0 is not usable\n";
        return 1;
    }
    cudaFree(warm);

    try {
        failedDeviceSelectionRetainsOwnership(device_count);
        if (cleanup_only) {
            std::cout << "ALL PASS: owning-device cleanup control\n"; return 0;
        }
        warmReuseIsExact();
        geometryTransition();
        frameAndGroupCounts();
        gainIdentity();
        constructionFailures();
        dropFailuresFailClosed();
        leaseExclusion();
        refusedSessionFallsBack();
        admissionEviction();
        declineAfterRecoverableFailure();
        deviceRestoration(device_count);
        admissionRetryOnAnotherDevice(device_count);
    } catch (RelionError &e) {
        disarm();
        std::cerr << "FAIL (RelionError): " << e;
        std::cerr << "\n";
        return 1;
    } catch (const std::exception &e) {
        disarm();
        std::cerr << "FAIL: " << e.what() << "\n";
        return 1;
    }
    std::cout << "ALL PASS: " << passed << " worker-pool control groups\n";
    return 0;
}
