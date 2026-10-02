// Native controls for mc_cuda::CudaWorkerPlanPool: the session lease, retained
// global cuFFT plans and their shared work area.
//
// Interposition is confined to this executable by the linker --wrap flags.
// Injected return codes do not poison real hardware. The oracle for "the pool
// still works" is an executed transform compared byte-for-byte, not a pointer:
// cudaMalloc readily returns the address just freed, so pointer identity alone
// cannot tell a live buffer from a recycled one.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/acc/cuda/cuda_failure_state.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {

enum Boundary { NONE, MALLOC, FREE, PLAN_CREATE, PLAN_MAKE, PLAN_DESTROY, BOUNDARIES };

bool active = false;
bool fired = false;
Boundary fault = NONE;
int ordinal = 0;
// Independent of the recoverable fault above, so one retirement can be made to
// report a recoverable cuFFT code and then a fatal CUDA code.
int fatal_free_at = 0;
// Fail a cudaMalloc of exactly this many bytes rather than by call ordinal:
// cuFFT's own internal allocations go through the same wrapper, so an ordinal
// would not name a specific allocation.
size_t malloc_fault_bytes = 0;
int counts[BOUNDARIES] = {};
std::set<void *> buffers;
std::set<cufftHandle> plans;
size_t stale = 0;

// Ordered record of the retirement-versus-allocation question: a stale large
// geometry must be retired BEFORE the next movie's buffers are allocated.
enum EventKind { EV_MALLOC, EV_FREE, EV_PLAN_DESTROY };
struct Event { EventKind kind; size_t value; };
bool recording = false;
std::vector<Event> events;

bool intercept_set_device = false;
std::vector<int> device_selections;

bool fail(Boundary boundary) {
    if (!active) return false;
    const int seen = ++counts[boundary];
    if (boundary != fault || seen != ordinal) return false;
    fired = true;
    return true;
}


void arm(Boundary boundary = NONE, int at = 0) {
    std::memset(counts, 0, sizeof(counts));
    fault = boundary;
    ordinal = at;
    fired = false;
    fatal_free_at = 0;
    malloc_fault_bytes = 0;
    active = true;
}

void disarm() {
    active = false;
    fault = NONE;
    ordinal = 0;
    fired = false;
    fatal_free_at = 0;
    malloc_fault_bytes = 0;
}

void require(bool ok, const char *message) {
    if (!ok) {
        std::cerr << "Assertion failed: " << message << std::endl;
        throw std::runtime_error(message);
    }
}

} // namespace

extern "C" {
cudaError_t __real_cudaMalloc(void **, size_t);
cudaError_t __real_cudaFree(void *);
cudaError_t __real_cudaSetDevice(int);
cufftResult __real_cufftCreate(cufftHandle *);
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int *, int *, int, int,
                                     int *, int, int, cufftType, int, size_t *);
cufftResult __real_cufftDestroy(cufftHandle);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (active && malloc_fault_bytes != 0 && bytes == malloc_fault_bytes) {
        malloc_fault_bytes = 0;
        fired = true;
        *ptr = nullptr;
        return cudaErrorMemoryAllocation;
    }
    if (fail(MALLOC)) {
        *ptr = nullptr;
        return cudaErrorMemoryAllocation;
    }
    const cudaError_t result = __real_cudaMalloc(ptr, bytes);
    if (active && result == cudaSuccess) buffers.insert(*ptr);
    if (recording && result == cudaSuccess) events.push_back(Event{EV_MALLOC, bytes});
    return result;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const bool inject = fail(FREE);
    const bool make_fatal = active && fatal_free_at != 0 && counts[FREE] == fatal_free_at;
    const cudaError_t result = __real_cudaFree(ptr);
    if (active && ptr && result == cudaSuccess) {
        if (!buffers.erase(ptr)) ++stale;
    }
    if (recording && ptr && result == cudaSuccess)
        events.push_back(Event{EV_FREE, (size_t)(uintptr_t)ptr});
    if (make_fatal && result == cudaSuccess) {
        fired = true;
        return cudaErrorIllegalAddress;
    }
    if (inject && result == cudaSuccess) return cudaErrorMemoryAllocation;
    return result;
}

cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (fail(PLAN_CREATE)) return CUFFT_ALLOC_FAILED;
    const cufftResult result = __real_cufftCreate(plan);
    if (active && result == CUFFT_SUCCESS) plans.insert(*plan);
    return result;
}

cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
                                     int *inembed, int istride, int idist,
                                     int *onembed, int ostride, int odist,
                                     cufftType type, int batch, size_t *work) {
    if (fail(PLAN_MAKE)) return CUFFT_ALLOC_FAILED;
    return __real_cufftMakePlanMany(plan, rank, n, inembed, istride, idist,
                                    onembed, ostride, odist, type, batch, work);
}

cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const bool inject = fail(PLAN_DESTROY);
    const cufftResult result = __real_cufftDestroy(plan);
    if (active && result == CUFFT_SUCCESS) {
        if (!plans.erase(plan)) ++stale;
    }
    if (recording && result == CUFFT_SUCCESS)
        events.push_back(Event{EV_PLAN_DESTROY, (size_t)plan});
    return inject && result == CUFFT_SUCCESS ? CUFFT_INTERNAL_ERROR : result;
}

cudaError_t __wrap_cudaSetDevice(int device) {
    if (intercept_set_device) {
        device_selections.push_back(device);
        return device == 0 ? __real_cudaSetDevice(0) : cudaSuccess;
    }
    return __real_cudaSetDevice(device);
}
} // extern "C"

namespace {

void resetPool() {
    disarm();
    (void)mc_cuda::getWorkerPlanPool().dropAll();
    buffers.clear();
    plans.clear();
    events.clear();
    stale = 0;
}

std::vector<Image<float> > makeFrames(int nx, int ny, int n_frames) {
    std::vector<Image<float> > frames(n_frames);
    for (int f = 0; f < n_frames; ++f) {
        frames[f]().reshape(ny, nx);
        for (int i = 0; i < ny; ++i)
            for (int j = 0; j < nx; ++j)
                DIRECT_A2D_ELEM(frames[f](), i, j) =
                    0.25f * (float)(f + 1) + 0.5f * (float)((i * 7 + j * 3) % 11) - 2.0f;
    }
    return frames;
}

// One movie through the retained global R2C plan and its shared work area.
std::vector<float> transform(CudaMovieSession &session,
                             const std::vector<Image<float> > &frames,
                             const char *what) {
    MultidimArray<float> sum;
    require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), what);
    require(session.computeGlobalForwardFFT(), what);
    std::vector<MultidimArray<fComplex> > out;
    require(session.downloadFourierFrames(out), what);
    std::vector<float> flat;
    for (size_t f = 0; f < out.size(); ++f) {
        const float *p = (const float *)out[f].data;
        flat.insert(flat.end(), p, p + 2 * NZYXSIZE(out[f]));
    }
    require(!flat.empty(), what);
    return flat;
}

// Cross-movie reuse, and the retirement ordering on a geometry change.
void testGlobalReuseAndRetirementOrder() {
    std::cout << "Testing retained global plans across movies..." << std::endl;
    resetPool();
    const int nx = 64, ny = 64, n_frames = 3;
    const std::vector<Image<float> > frames = makeFrames(nx, ny, n_frames);

    std::vector<float> first;
    cufftHandle pooled_r2c = 0, pooled_c2r = 0;
    void *pooled_work = nullptr;
    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "first session initialization");
        require(mc_cuda::getWorkerPlanPool().global.valid, "global pool not populated");
        pooled_r2c = mc_cuda::getWorkerPlanPool().global.plan_r2c;
        pooled_c2r = mc_cuda::getWorkerPlanPool().global.plan_c2r;
        pooled_work = mc_cuda::getWorkerPlanPool().global.d_fft_work;
        first = transform(session, frames, "first movie transform");
        session.release();
    }
    require(mc_cuda::getWorkerPlanPool().global.valid,
            "releasing a healthy session retired the pooled plans");
    require(mc_cuda::getWorkerPlanPool().global.plan_r2c == pooled_r2c,
            "the pooled R2C plan did not survive the session");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() > 0,
            "retained byte count is zero with a populated global pool");

    // Same geometry: no new plan, and the same bytes out.
    {
        arm();
        plans.clear();
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "second session initialization");
        require(plans.empty(), "a pooled geometry still created a cuFFT plan");
        require(mc_cuda::getWorkerPlanPool().global.plan_r2c == pooled_r2c,
                "a pooled geometry replaced the retained R2C plan");
        require(mc_cuda::getWorkerPlanPool().global.plan_c2r == pooled_c2r,
                "a pooled geometry replaced the retained C2R plan");
        require(mc_cuda::getWorkerPlanPool().global.d_fft_work == pooled_work,
                "a pooled geometry replaced the retained work area");
        const std::vector<float> second = transform(session, frames, "second movie transform");
        require(second.size() == first.size() &&
                std::memcmp(second.data(), first.data(), first.size() * sizeof(float)) == 0,
                "the reused plan produced different bytes from the first movie");
        session.release();
        disarm();
    }

    // Changed geometry: the stale entry must be retired BEFORE this movie's
    // buffers are allocated, or an old large geometry could deny a smaller one.
    {
        const int nx2 = 96, ny2 = 96, frames2 = 2;
        events.clear();
        recording = true;
        std::ostringstream log;
        CudaMovieSession session(nx2, ny2, frames2, 0, log);
        require(session.initialize(), "geometry change initialization");
        recording = false;
        long destroy_at = -1, movie_alloc_at = -1;
        const size_t movie_bytes = (size_t)nx2 * ny2 * sizeof(float) * frames2;
        for (size_t k = 0; k < events.size(); ++k) {
            if (events[k].kind == EV_PLAN_DESTROY && destroy_at < 0) destroy_at = (long)k;
            if (events[k].kind == EV_MALLOC && events[k].value >= movie_bytes && movie_alloc_at < 0)
                movie_alloc_at = (long)k;
        }
        require(destroy_at >= 0, "the stale pooled plans were never retired on a geometry change");
        require(movie_alloc_at >= 0, "the new movie buffers were never allocated");
        require(destroy_at < movie_alloc_at,
                "the stale geometry was retired only after the new movie's buffers were allocated");
        require(mc_cuda::getWorkerPlanPool().global.nx == nx2 &&
                mc_cuda::getWorkerPlanPool().global.ny == ny2,
                "the pool key did not follow the new geometry");
        session.release();
    }
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the pool");
    std::cout << "  PASS: reuse, identical bytes, retire-before-allocate" << std::endl;
}

// (A) A refused lease must not retire the active owner's resources. The owner
// is asked to execute after every refusal, so a use-after-free shows up as
// wrong bytes or a CUDA error rather than as a silent pass.
void testRejectedLeaseLeavesOwnerIntact() {
    std::cout << "Testing a refused lease against the active owner..." << std::endl;
    resetPool();
    const int nx = 64, ny = 64, n_frames = 2;
    const std::vector<Image<float> > frames = makeFrames(nx, ny, n_frames);

    std::ostringstream log_a;
    CudaMovieSession a(nx, ny, n_frames, 0, log_a);
    require(a.initialize(), "owner initialization");
    const std::vector<float> baseline = transform(a, frames, "owner baseline transform");

    const cufftHandle owner_r2c = mc_cuda::getWorkerPlanPool().global.plan_r2c;
    const cufftHandle owner_c2r = mc_cuda::getWorkerPlanPool().global.plan_c2r;
    void *const owner_work = mc_cuda::getWorkerPlanPool().global.d_fft_work;
    void *const owner_tile = mc_cuda::getWorkerPlanPool().global.d_inverse_tile;
    require(owner_r2c != 0 && owner_work != nullptr, "owner did not populate the pool");

    for (int attempt = 0; attempt < 2; ++attempt) {
        std::ostringstream log_b;
        CudaMovieSession b(nx, ny, n_frames, 0, log_b);
        require(!b.initialize(), "a concurrent lease was granted");
        require(mc_cuda::getWorkerPlanPool().global.valid,
                "a refused session retired the owner's pooled entry");
        require(mc_cuda::getWorkerPlanPool().global.plan_r2c == owner_r2c &&
                mc_cuda::getWorkerPlanPool().global.plan_c2r == owner_c2r &&
                mc_cuda::getWorkerPlanPool().global.d_fft_work == owner_work &&
                mc_cuda::getWorkerPlanPool().global.d_inverse_tile == owner_tile,
                "a refused session replaced the owner's pooled resources");
        // Explicit release, then the destructor's release, both while A is alive.
        b.release();
        require(mc_cuda::getWorkerPlanPool().global.valid,
                "releasing a refused session retired the owner's pooled entry");

        const std::vector<float> after = transform(a, frames, "owner transform after a refused lease");
        require(after.size() == baseline.size() &&
                std::memcmp(after.data(), baseline.data(), baseline.size() * sizeof(float)) == 0,
                "the owner's transform changed after a refused lease (use-after-free)");
        require(!a.getFailureState().hasFailed(), "the owner recorded a failure after a refused lease");
    }

    // Once the owner releases, the next session takes the lease and works.
    a.release();
    require(!a.getFailureState().hasFailed(), "the owner failed during release");
    {
        std::ostringstream log_c;
        CudaMovieSession c(nx, ny, n_frames, 0, log_c);
        require(c.initialize(), "a session could not take the freed lease");
        const std::vector<float> taken = transform(c, frames, "successor transform");
        require(taken.size() == baseline.size() &&
                std::memcmp(taken.data(), baseline.data(), baseline.size() * sizeof(float)) == 0,
                "the successor produced different bytes from the owner");
        c.release();
    }
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the lease sequence");
    std::cout << "  PASS: refused lease leaves the owner executable and exact" << std::endl;
}

// (B) A cleanup that reports failure must not be followed by a replacement, and
// a fatal code recorded during that cleanup must not displace the first cause.
void testDropFailureBlocksRebuild() {
    std::cout << "Testing a failed retirement before a rebuild..." << std::endl;

    auto seed = [](int nx, int ny, const char *what) {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, 2, 0, log);
        require(session.initialize(), what);
        session.release();
        require(mc_cuda::getWorkerPlanPool().global.valid, what);
    };

    // A geometry change retires the seeded entry; its first cufftDestroy fails.
    resetPool();
    seed(64, 64, "retirement seed");
    {
        arm(PLAN_DESTROY, 1);
        std::ostringstream log;
        CudaMovieSession session(48, 48, 2, 0, log);
        require(!session.initialize(), "initialization continued after a failed retirement");
        require(fired, "the retirement fault never fired");
        require(counts[PLAN_CREATE] == 0,
                "a replacement plan was created after a failed retirement");
        require(!mc_cuda::getWorkerPlanPool().global.valid,
                "a failed retirement left the pool advertised as valid");
        require(session.getFailureState().firstCufftError() == CUFFT_INTERNAL_ERROR,
                "the retirement failure was not recorded");
        disarm();
        session.release();
    }

    // The same retirement, with a recoverable cuFFT code on the plan destroy
    // and a fatal CUDA code on the work-area free that follows it. Both must
    // survive: the first as the diagnostic cause, the second as the poisoning.
    resetPool();
    seed(64, 64, "fatal retirement seed");
    {
        CudaFailureState state;
        arm(PLAN_DESTROY, 1);
        fatal_free_at = 1;
        const bool ok = mc_cuda::getWorkerPlanPool().global.drop(&state);
        disarm();
        require(!ok, "a failing retirement reported success");
        require(state.firstCufftError() == CUFFT_INTERNAL_ERROR,
                "the original recoverable cleanup cause was lost");
        require(state.fatalError() == cudaErrorIllegalAddress,
                "the later fatal cleanup code was not latched");
        require(state.isPoisoned(), "a fatal cleanup code did not poison the state");
        require(!mc_cuda::getWorkerPlanPool().global.valid,
                "a failing retirement left the entry advertised as valid");
    }
    resetPool();
    std::cout << "  PASS: failed retirement blocks the rebuild and preserves both codes" << std::endl;
}

// Create succeeds, planning fails: no handle leaks and nothing is published.
void testGlobalPlanMakeFailureNoLeak() {
    std::cout << "Testing global plan planning failure..." << std::endl;
    for (int which = 1; which <= 2; ++which) {
        resetPool();
        arm(PLAN_MAKE, which);
        plans.clear();
        std::ostringstream log;
        CudaMovieSession session(64, 64, 2, 0, log);
        require(!session.initialize(), "initialization succeeded despite a planning failure");
        require(fired, "the planning fault never fired");
        require(plans.empty(), "a cuFFT handle leaked when planning failed");
        require(!mc_cuda::getWorkerPlanPool().global.valid,
                "a failed plan build was published to the pool");
        require(mc_cuda::getWorkerPlanPool().global.plan_r2c == 0 &&
                mc_cuda::getWorkerPlanPool().global.plan_c2r == 0,
                "a failed plan build left handles in the pool");
        disarm();
        session.release();
        require(stale == 0, "a failed plan build double-destroyed a handle");
    }

    // The inverse tile failing after both plans and the work area exist must
    // release the plans AND the work area already taken, and publish nothing.
    resetPool();
    {
        const int nx = 64, ny = 64, nfx = nx / 2 + 1;
        std::ostringstream log;
        CudaMovieSession session(nx, ny, 2, 0, log);
        arm();
        // Named by size, not by call ordinal: cuFFT's own allocations go
        // through the same wrapper and would shift any ordinal.
        malloc_fault_bytes = (size_t)ny * nfx * sizeof(cufftComplex);
        plans.clear();
        const size_t tracked_before = buffers.size();
        require(!session.initialize(), "initialization succeeded despite a scratch failure");
        require(fired, "the scratch fault never fired");
        require(plans.empty(), "a cuFFT handle leaked when the inverse tile allocation failed");
        require(!mc_cuda::getWorkerPlanPool().global.valid,
                "a failed scratch build was published to the pool");
        disarm();
        session.release();
        require(buffers.size() == tracked_before,
                "the work area survived a failed inverse tile allocation");
    }
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the planning failures");
    std::cout << "  PASS: planning and scratch failures leak nothing and publish nothing" << std::endl;
}

// The pooled batched patch plan: reuse across movies, retirement ordering on a
// geometry change, and the failure paths. The oracle is the transformed patch
// block downloaded from the device, so a wrong or dead plan is visible.
void testPatchPlanPooling() {
    std::cout << "Testing retained patch plans across movies..." << std::endl;
    const int nx = 128, ny = 128, n_frames = 4;
    const std::vector<Image<float> > frames = makeFrames(nx, ny, n_frames);
    const int group_start[2] = {0, 2};
    const int group_size[2] = {2, 2};

    auto runPatch = [&](CudaMovieSession &session, int pw, int ph, const char *what) {
        MultidimArray<float> sum;
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), what);
        const size_t elems = (size_t)2 * ph * (pw / 2 + 1);
        cufftComplex *d_out = nullptr;
        require(__real_cudaMalloc((void **)&d_out, elems * sizeof(cufftComplex)) == cudaSuccess, what);
        const bool ok = session.preparePatchInVram(0, 0, pw, ph, 2, group_start, group_size, d_out);
        std::vector<cufftComplex> host(elems);
        if (ok)
            require(cudaMemcpy(host.data(), d_out, elems * sizeof(cufftComplex),
                               cudaMemcpyDeviceToHost) == cudaSuccess, what);
        require(__real_cudaFree(d_out) == cudaSuccess, what);
        require(ok, what);
        return host;
    };

    resetPool();
    std::vector<cufftComplex> first;
    cufftHandle pooled = 0;
    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "patch movie 1 initialization");
        first = runPatch(session, 32, 32, "patch movie 1");
        require(mc_cuda::getWorkerPlanPool().patch.valid, "patch pool not populated");
        pooled = mc_cuda::getWorkerPlanPool().patch.plan_patch_r2c;
        require(mc_cuda::getWorkerPlanPool().patch.retainedBytes() ==
                mc_cuda::getWorkerPlanPool().patch.work_bytes,
                "patch retained byte count does not report the plan work area");
        session.release();
    }
    require(mc_cuda::getWorkerPlanPool().patch.valid,
            "releasing a healthy session retired the pooled patch plan");

    {
        arm();
        plans.clear();
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "patch movie 2 initialization");
        const int creates_at_init = (int)plans.size();
        const std::vector<cufftComplex> second = runPatch(session, 32, 32, "patch movie 2");
        require((int)plans.size() == creates_at_init,
                "a pooled patch geometry still created a cuFFT plan");
        require(mc_cuda::getWorkerPlanPool().patch.plan_patch_r2c == pooled,
                "a pooled patch geometry replaced the retained plan");
        require(second.size() == first.size() &&
                std::memcmp(second.data(), first.data(), first.size() * sizeof(cufftComplex)) == 0,
                "the reused patch plan produced different bytes");
        disarm();
        session.release();
    }

    // Geometry change: retire the stale plan before this movie's patch scratch.
    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "patch geometry change initialization");
        MultidimArray<float> sum;
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), "patch geometry sum");
        const size_t scratch_bytes = (size_t)2 * 48 * 48 * sizeof(float);
        const size_t elems = (size_t)2 * 48 * (48 / 2 + 1);
        cufftComplex *d_out = nullptr;
        require(__real_cudaMalloc((void **)&d_out, elems * sizeof(cufftComplex)) == cudaSuccess,
                "patch geometry output allocation");
        events.clear();
        recording = true;
        const bool ok = session.preparePatchInVram(0, 0, 48, 48, 2, group_start, group_size, d_out);
        recording = false;
        require(ok, "patch geometry change preparation");
        long destroy_at = -1, scratch_at = -1;
        for (size_t k = 0; k < events.size(); ++k) {
            if (events[k].kind == EV_PLAN_DESTROY && destroy_at < 0) destroy_at = (long)k;
            if (events[k].kind == EV_MALLOC && events[k].value >= scratch_bytes && scratch_at < 0)
                scratch_at = (long)k;
        }
        require(destroy_at >= 0, "the stale patch plan was never retired on a geometry change");
        require(scratch_at >= 0, "the new patch scratch was never allocated");
        require(destroy_at < scratch_at,
                "the stale patch plan was retired only after the new scratch was allocated");
        require(__real_cudaFree(d_out) == cudaSuccess, "patch geometry output release");
        session.release();
    }

    // Create succeeds, planning fails: no handle leaks and nothing is published.
    resetPool();
    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "patch planning failure initialization");
        MultidimArray<float> sum;
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), "patch planning sum");
        cufftComplex *d_out = nullptr;
        const size_t elems = (size_t)2 * 32 * 17;
        require(__real_cudaMalloc((void **)&d_out, elems * sizeof(cufftComplex)) == cudaSuccess,
                "patch planning output allocation");
        arm(PLAN_MAKE, 1);
        plans.clear();
        require(!session.preparePatchInVram(0, 0, 32, 32, 2, group_start, group_size, d_out),
                "patch preparation succeeded despite a planning failure");
        require(fired, "the patch planning fault never fired");
        require(plans.empty(), "a cuFFT handle leaked when patch planning failed");
        require(!mc_cuda::getWorkerPlanPool().patch.valid,
                "a failed patch plan build was published to the pool");
        require(mc_cuda::getWorkerPlanPool().patch.plan_patch_r2c == 0,
                "a failed patch plan build left a handle in the pool");
        disarm();
        require(__real_cudaFree(d_out) == cudaSuccess, "patch planning output release");
        session.release();
        require(stale == 0, "a failed patch plan build double-destroyed a handle");
    }

    // A retirement that reports failure must not be followed by a replacement.
    resetPool();
    {
        std::ostringstream log;
        CudaMovieSession session(nx, ny, n_frames, 0, log);
        require(session.initialize(), "patch retirement failure initialization");
        MultidimArray<float> sum;
        require(session.applyGainDefectsAndSum(frames, nullptr, sum, true), "patch retirement sum");
        cufftComplex *d_out = nullptr;
        require(__real_cudaMalloc((void **)&d_out, (size_t)2 * 32 * 17 * sizeof(cufftComplex)) == cudaSuccess,
                "patch retirement output allocation");
        require(session.preparePatchInVram(0, 0, 32, 32, 2, group_start, group_size, d_out),
                "patch retirement seed preparation");
        require(__real_cudaFree(d_out) == cudaSuccess, "patch retirement output release");

        cufftComplex *d_out2 = nullptr;
        require(__real_cudaMalloc((void **)&d_out2, (size_t)2 * 48 * 25 * sizeof(cufftComplex)) == cudaSuccess,
                "patch retirement second output allocation");
        arm(PLAN_DESTROY, 1);
        require(!session.preparePatchInVram(0, 0, 48, 48, 2, group_start, group_size, d_out2),
                "patch preparation continued after a failed retirement");
        require(fired, "the patch retirement fault never fired");
        require(counts[PLAN_CREATE] == 0,
                "a replacement patch plan was created after a failed retirement");
        require(!mc_cuda::getWorkerPlanPool().patch.valid,
                "a failed patch retirement left the pool advertised as valid");
        require(session.getFailureState().firstCufftError() == CUFFT_INTERNAL_ERROR,
                "the patch retirement failure was not recorded");
        disarm();
        require(__real_cudaFree(d_out2) == cudaSuccess, "patch retirement second output release");
        session.release();
    }
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the patch controls");
    std::cout << "  PASS: patch plan reuse, retire-before-allocate, failure paths" << std::endl;
}

// The pooled dose-weighting C2R plan: reuse across reconstructions, retirement
// ordering on a geometry change, and the failure paths. The oracle is the
// reconstructed image, so a dead or wrong plan is visible rather than inferred.
void testDoseWeightPlanPooling() {
    std::cout << "Testing retained dose-weighting plan across movies..." << std::endl;

    auto reconstruct = [](int nx, int ny, int n_frames, std::vector<float> &out,
                          CudaFailureState &failure, const char *what, bool expect_ok) {
        const int nfx = nx / 2 + 1;
        const size_t tile = (size_t)nfx * ny;
        std::vector<cufftComplex> host(tile * n_frames);
        unsigned state = 7u;
        for (size_t i = 0; i < host.size(); ++i) {
            state = 1664525u * state + 1013904223u;
            host[i].x = (float)((int)(state & 65535u) - 32768) / 4096.0f;
            state = 1664525u * state + 1013904223u;
            host[i].y = (float)((int)(state & 65535u) - 32768) / 4096.0f;
        }
        cufftComplex *resident = nullptr;
        require(__real_cudaMalloc((void **)&resident, host.size() * sizeof(cufftComplex)) == cudaSuccess, what);
        require(cudaMemcpy(resident, host.data(), host.size() * sizeof(cufftComplex),
                           cudaMemcpyHostToDevice) == cudaSuccess, what);
        Image<float> image;
        image().resize(ny, nx);
        std::vector<RFLOAT> doses(n_frames);
        for (int f = 0; f < n_frames; ++f) doses[f] = 1.277 * (f + 1);
        std::ostringstream log;
        const bool ok = cudaDoseWeightAndInterpolateDevice(resident, image, nx, ny, n_frames,
                                                           doses, 1.12, nullptr, 0, log, &failure);
        if (ok) {
            out.assign(image().data, image().data + (size_t)nx * ny);
            require(log.str().find("retained across movies:") != std::string::npos,
                    "the reconstruction profile did not report retained residency");
        }
        require(__real_cudaFree(resident) == cudaSuccess, what);
        require(ok == expect_ok, what);
    };

    resetPool();
    std::vector<float> first, second;
    cufftHandle pooled = 0;
    {
        CudaFailureState failure;
        reconstruct(64, 48, 3, first, failure, "dw reconstruction 1", true);
        require(!failure.hasFailed(), "dw reconstruction 1 recorded a failure");
        require(mc_cuda::getWorkerPlanPool().dw.valid, "dw pool not populated");
        require(mc_cuda::getWorkerPlanPool().dw.retainedBytes() ==
                mc_cuda::getWorkerPlanPool().dw.work_bytes,
                "dw retained byte count does not report the plan work area");
        pooled = mc_cuda::getWorkerPlanPool().dw.plan_c2r;
    }
    {
        arm();
        plans.clear();
        CudaFailureState failure;
        reconstruct(64, 48, 3, second, failure, "dw reconstruction 2", true);
        require(plans.empty(), "a pooled dw geometry still created a cuFFT plan");
        require(mc_cuda::getWorkerPlanPool().dw.plan_c2r == pooled,
                "a pooled dw geometry replaced the retained plan");
        require(second.size() == first.size() &&
                std::memcmp(second.data(), first.data(), first.size() * sizeof(float)) == 0,
                "the reused dw plan produced different pixels");
        disarm();
    }

    // Geometry change: retire the stale plan before this reconstruction's buffers.
    {
        events.clear();
        recording = true;
        CudaFailureState failure;
        std::vector<float> third;
        reconstruct(96, 64, 2, third, failure, "dw geometry change", true);
        recording = false;
        const size_t frame_bytes = (size_t)96 * 64 * sizeof(float);
        long destroy_at = -1, alloc_at = -1;
        for (size_t k = 0; k < events.size(); ++k) {
            if (events[k].kind == EV_PLAN_DESTROY && destroy_at < 0) destroy_at = (long)k;
            if (events[k].kind == EV_MALLOC && events[k].value >= frame_bytes && alloc_at < 0)
                alloc_at = (long)k;
        }
        require(destroy_at >= 0, "the stale dw plan was never retired on a geometry change");
        require(alloc_at >= 0, "the new dw buffers were never allocated");
        require(destroy_at < alloc_at,
                "the stale dw plan was retired only after the new buffers were allocated");
    }

    // Create succeeds, planning fails: no handle leaks and nothing is published.
    resetPool();
    {
        arm(PLAN_MAKE, 1);
        plans.clear();
        CudaFailureState failure;
        std::vector<float> unused;
        reconstruct(64, 48, 2, unused, failure, "dw planning failure", false);
        require(fired, "the dw planning fault never fired");
        require(plans.empty(), "a cuFFT handle leaked when dw planning failed");
        require(!mc_cuda::getWorkerPlanPool().dw.valid,
                "a failed dw plan build was published to the pool");
        require(mc_cuda::getWorkerPlanPool().dw.plan_c2r == 0,
                "a failed dw plan build left a handle in the pool");
        require(failure.hasFailed(), "a dw planning failure was not recorded");
        disarm();
        require(stale == 0, "a failed dw plan build double-destroyed a handle");
    }

    // A retirement that reports failure must not be followed by a replacement.
    resetPool();
    {
        CudaFailureState seed_failure;
        std::vector<float> seed;
        reconstruct(64, 48, 2, seed, seed_failure, "dw retirement seed", true);
        require(mc_cuda::getWorkerPlanPool().dw.valid, "dw retirement seed did not populate the pool");

        arm(PLAN_DESTROY, 1);
        CudaFailureState failure;
        std::vector<float> unused;
        reconstruct(48, 32, 2, unused, failure, "dw retirement failure", false);
        require(fired, "the dw retirement fault never fired");
        require(counts[PLAN_CREATE] == 0,
                "a replacement dw plan was created after a failed retirement");
        require(!mc_cuda::getWorkerPlanPool().dw.valid,
                "a failed dw retirement left the pool advertised as valid");
        require(failure.firstCufftError() == CUFFT_INTERNAL_ERROR,
                "the dw retirement failure was not recorded");
        disarm();
    }

    // A reconstruction that failed must not hand its plan to the next movie.
    resetPool();
    {
        CudaFailureState failure;
        std::vector<float> seed;
        reconstruct(64, 48, 2, seed, failure, "dw failure retirement seed", true);
        require(mc_cuda::getWorkerPlanPool().dw.valid, "dw pool not populated before the failure");
        failure.record(cudaErrorIllegalAddress, "injected fatal", 7);
        std::vector<float> unused;
        reconstruct(64, 48, 2, unused, failure, "dw reconstruction on a poisoned state", true);
        require(!mc_cuda::getWorkerPlanPool().dw.valid,
                "a poisoned reconstruction left its plan in the pool");
    }
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the dw controls");
    std::cout << "  PASS: dw plan reuse, retire-before-allocate, failure paths" << std::endl;
}

// Logic only: the owning device is selected for the retirement and the caller's
// device is restored. Genuine cross-device retirement is UNRUN here -- it needs
// two visible devices, and gpu_id is a single process-wide value.
void testGlobalDropRestoresDevice() {
    std::cout << "Testing device selection around a global retirement..." << std::endl;
    resetPool();
    {
        std::ostringstream log;
        CudaMovieSession seed(64, 64, 2, 0, log);
        require(seed.initialize(), "device selection seed initialization");
        seed.release();
    }
    mc_cuda::CudaWorkerPlanPool::GlobalPool &pool = mc_cuda::getWorkerPlanPool().global;
    require(pool.valid, "device selection seed did not populate the pool");
    pool.device_id = 7; // a device this entry claims to own but which is not current

    require(__real_cudaSetDevice(0) == cudaSuccess, "device selection fixture reset");
    device_selections.clear();
    intercept_set_device = true;
    CudaFailureState state;
    const bool ok = pool.drop(&state);
    intercept_set_device = false;
    require(ok, "retiring a foreign-device entry reported failure");
    require(device_selections.size() == 2, "retirement did not select and restore a device");
    require(device_selections[0] == 7, "retirement did not select the owning device");
    require(device_selections[1] == 0, "retirement did not restore the caller's device");
    require(!state.hasFailed(), "device selection recorded a spurious failure");
    resetPool();
    std::cout << "  PASS: owning device selected, caller's device restored" << std::endl;
}

// A failed or poisoned session retires every retained resource, including the
// device gain, rather than handing an unknown-state buffer to the next movie.
void testPoisonRetiresEverything() {
    std::cout << "Testing pool retirement on a poisoned session..." << std::endl;
    resetPool();
    std::ostringstream log;
    CudaMovieSession session(64, 64, 2, 0, log);
    require(session.initialize(), "poison test initialization");
    MultidimArray<float> gain(64, 64);
    gain.initConstant(1.0f);
    MultidimArray<float> sum;
    session.setGainGeneration(4242);
    require(session.applyGainDefectsAndSum(makeFrames(64, 64, 2), &gain, sum, true),
            "poison test sum");
    require(mc_cuda::getWorkerPlanPool().global.valid, "global pool not populated");
    require(mc_cuda::getWorkerPlanPool().gain.ptr != nullptr, "gain pool not populated");

    session.getFailureState().record(cudaErrorIllegalAddress, "simulated fatal error", 42);
    session.release();
    require(!mc_cuda::getWorkerPlanPool().global.valid,
            "the global pool survived a poisoned session");
    require(mc_cuda::getWorkerPlanPool().gain.ptr == nullptr,
            "the retained gain survived a poisoned session");
    require(mc_cuda::getWorkerPlanPool().retainedBytes() == 0,
            "retained bytes survived a poisoned session");
    resetPool();
    require(buffers.empty() && plans.empty(), "resources outlived the poisoned session");
    std::cout << "  PASS: a poisoned session retires every retained resource" << std::endl;
}

} // namespace

int main() {
    if (__real_cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n";
        return 1;
    }
    try {
        testGlobalReuseAndRetirementOrder();
        testRejectedLeaseLeavesOwnerIntact();
        testDropFailureBlocksRebuild();
        testGlobalPlanMakeFailureNoLeak();
        testPatchPlanPooling();
        testDoseWeightPlanPooling();
        testGlobalDropRestoresDevice();
        testPoisonRetiresEverything();
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    } catch (RelionError &e) {
        std::cerr << "FAIL: unexpected production exception: " << e << '\n';
        return 1;
    }
    std::cout << "PASS: worker plan pool lease and global retention controls" << std::endl;
    return 0;
}
