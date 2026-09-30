// Native, actual-entry-point controls for movie-scoped patch alignment reuse.
// Interposition is confined to this executable. Error-code injection does not
// poison real hardware; cuFFT's internal allocations remain outside accounting.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_alignpatch.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {
enum Boundary { NONE, MALLOC, FREE, EVENT_CREATE, EVENT_DESTROY, PLAN_CREATE,
                PLAN_MAKE, PLAN_DESTROY, BOUNDARIES };
bool active = false, fired = false, fatal = false;
Boundary fault = NONE;
int ordinal = 0, counts[BOUNDARIES] = {};
std::set<void*> buffers;
std::set<cudaEvent_t> events;
std::set<cufftHandle> plans;
size_t stale = 0;
bool late_fatal_free = false;
std::string last_log;
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
    stale = 0; late_fatal_free = false; active = true;
}
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
void requireEmpty() {
    require(buffers.empty() && events.empty() && plans.empty() && stale == 0,
            "owned resources leaked or released twice");
}
}

extern "C" {
cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cudaError_t __real_cudaEventCreate(cudaEvent_t*);
cudaError_t __real_cudaEventDestroy(cudaEvent_t);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int*, int*, int, int,
                                    int*, int, int, cufftType, int, size_t*);
cufftResult __real_cufftDestroy(cufftHandle);
cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (fail(MALLOC)) { *ptr = nullptr; return code(); }
    const cudaError_t result = __real_cudaMalloc(ptr, bytes);
    if (active && result == cudaSuccess) buffers.insert(*ptr);
    return result;
}
cudaError_t __wrap_cudaFree(void *ptr) {
    const bool inject = fail(FREE);
    const cudaError_t result = __real_cudaFree(ptr);
    if (active && ptr && result == cudaSuccess && !buffers.erase(ptr)) ++stale;
    if (active && late_fatal_free && counts[FREE] == 1) return cudaErrorIllegalAddress;
    return inject && result == cudaSuccess ? code() : result;
}
cudaError_t __wrap_cudaEventCreate(cudaEvent_t *event) {
    if (fail(EVENT_CREATE)) { *event = nullptr; return code(); }
    const cudaError_t result = __real_cudaEventCreate(event);
    if (active && result == cudaSuccess) events.insert(*event);
    return result;
}
cudaError_t __wrap_cudaEventDestroy(cudaEvent_t event) {
    const bool inject = fail(EVENT_DESTROY);
    const cudaError_t result = __real_cudaEventDestroy(event);
    if (active && result == cudaSuccess && !events.erase(event)) ++stale;
    return inject && result == cudaSuccess ? code() : result;
}
cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    if (fail(PLAN_CREATE)) return CUFFT_ALLOC_FAILED;
    const cufftResult result = __real_cufftCreate(plan);
    if (active && result == CUFFT_SUCCESS) plans.insert(*plan);
    return result;
}
cufftResult __wrap_cufftMakePlanMany(cufftHandle plan, int rank, int *n,
    int *inembed, int istride, int idist, int *onembed, int ostride, int odist,
    cufftType type, int batch, size_t *work) {
    if (fail(PLAN_MAKE)) return CUFFT_ALLOC_FAILED;
    return __real_cufftMakePlanMany(plan, rank, n, inembed, istride, idist,
                                  onembed, ostride, odist, type, batch, work);
}
cufftResult __wrap_cufftDestroy(cufftHandle plan) {
    const bool inject = fail(PLAN_DESTROY);
    const cufftResult result = __real_cufftDestroy(plan);
    if (active && result == CUFFT_SUCCESS && !plans.erase(plan)) ++stale;
    return inject && result == CUFFT_SUCCESS ? CUFFT_INTERNAL_ERROR : result;
}
}

namespace {
struct Geometry { int x, y, groups; RFLOAT B, downsample; int seed; };
struct Result {
    bool converged;
    std::vector<RFLOAT> x, y;
    std::vector<cufftComplex> fourier;
};
Result align(const Geometry &g, PatchAlignmentWorkspace *workspace) {
    const bool armed = active;
    active = false;
    const size_t n = (size_t)(g.x / 2 + 1) * g.y * g.groups;
    std::vector<cufftComplex> input(n);
    // Distinct frames, including non-zero shifts/nonconvergence; repeated-key
    // controls use different inputs so stale input-dependent scratch is exposed.
    unsigned state = (unsigned)g.seed;
    for (auto &v : input) {
        state = 1664525u * state + 1013904223u;
        v.x = (float)((int)(state & 65535u) - 32768) / 4096.0f;
        state = 1664525u * state + 1013904223u;
        v.y = (float)((int)(state & 65535u) - 32768) / 4096.0f;
    }
    cufftComplex *device = nullptr;
    require(cudaMalloc(&device, n * sizeof(cufftComplex)) == cudaSuccess, "input allocation");
    require(cudaMemcpy(device, input.data(), n * sizeof(cufftComplex),
                       cudaMemcpyHostToDevice) == cudaSuccess, "input upload");
    Result result = {false, std::vector<RFLOAT>(g.groups, 0),
                      std::vector<RFLOAT>(g.groups, 0), std::vector<cufftComplex>(n)};
    std::ostringstream log;
    last_log.clear();
    active = armed;
    try {
        result.converged = workspace
            ? cudaAlignPatchDeviceWithWorkspace(*workspace, device, g.groups,
                g.x, g.y, g.B, result.x, result.y, 4, g.downsample, 0, log)
            : cudaAlignPatchDevice(device, g.groups, g.x, g.y, g.B,
                result.x, result.y, 4, g.downsample, 0, log);
    } catch (...) {
        last_log = log.str();
        active = false;
        __real_cudaFree(device);
        active = armed;
        throw;
    }
    last_log = log.str();
    active = false;
    require(cudaMemcpy(result.fourier.data(), device, n * sizeof(cufftComplex),
                       cudaMemcpyDeviceToHost) == cudaSuccess, "result download");
    __real_cudaFree(device);
    active = armed;
    return result;
}
void exact(const Result &a, const Result &b) {
    require(a.converged == b.converged && a.x.size() == b.x.size() &&
            a.fourier.size() == b.fourier.size(), "result structure differs");
    require(std::memcmp(a.x.data(), b.x.data(), a.x.size()*sizeof(RFLOAT)) == 0 &&
            std::memcmp(a.y.data(), b.y.data(), a.y.size()*sizeof(RFLOAT)) == 0 &&
            std::memcmp(a.fourier.data(), b.fourier.data(),
                        a.fourier.size()*sizeof(cufftComplex)) == 0,
            "workspace shifts or Fourier payload differ from ephemeral entry point");
}
void healthyAndKeys() {
    std::ostringstream log;
    CudaMovieSession movie(64, 64, 4, 0, log);
    auto &workspace = movie.getPatchAlignmentWorkspace();
    const Geometry sequence[] = {
        {64,64,4,2,1,1}, {64,64,4,2,1,2}, // reuse, changing inputs
        {80,64,4,2,1,3}, {80,72,4,2,1,4}, // independent X/Y geometry
        {80,72,3,2,1,5}, {80,72,3,5,1,6}, // group count, B-factor
        {80,72,3,5,.6,7}, {80,72,3,5,0,8}, // explicit and inferred downsample
        {80,72,3,5,0,9},
        {320,256,3,5,1,10}, {320,256,3,5,.6,11}, // actual CCF/search dimensions change
        {320,256,3,5,.6,12}
    };
    for (size_t i = 0; i < sizeof(sequence)/sizeof(sequence[0]); ++i) {
        arm();
        const Result candidate = align(sequence[i], &workspace);
        const bool reuse = i == 1 || i == 8 || i == 11;
        require(workspace.isValid(), "successful path did not publish valid key");
        require(counts[MALLOC] == (reuse ? 0 : 8) &&
                counts[EVENT_CREATE] == (reuse ? 0 : 8) &&
                counts[PLAN_CREATE] == (reuse ? 0 : 1) &&
                counts[PLAN_MAKE] == (reuse ? 0 : 1), "cache key/reuse allocation counts wrong");
        active = false;
        exact(candidate, align(sequence[i], nullptr));
    }
    active = true;
    require(movie.releasePatchAlignmentWorkspace(), "checked movie release failed");
    require(!workspace.isValid(), "release left a published key");
    requireEmpty();
    require(movie.releasePatchAlignmentWorkspace(), "release is not idempotent");
    active = false;
    // A second movie has its own cache even at identical geometry.
    CudaMovieSession second(64, 64, 4, 0, log);
    arm();
    const auto second_result = align(sequence[0], &second.getPatchAlignmentWorkspace());
    require(counts[MALLOC] == 8 && counts[PLAN_CREATE] == 1, "second movie reused first movie state");
    require(second.releasePatchAlignmentWorkspace(), "second movie release failed");
    requireEmpty(); active = false;
    exact(second_result, align(sequence[0], nullptr));
    std::cout << "PASS: 13 exact actual-path input/key/movie controls; 3 reuse calls had zero setup resources\n";
}
void initializationFailures() {
    const Geometry g = {64,64,4,2,1,11};
    int trials = 0;
    for (Boundary boundary : {MALLOC, EVENT_CREATE, PLAN_CREATE, PLAN_MAKE}) {
        const int limit = (boundary == MALLOC || boundary == EVENT_CREATE) ? 8 : 1;
        for (int at = 1; at <= limit; ++at) {
            CudaFailureState failure;
            PatchAlignmentWorkspace workspace(&failure);
            arm(boundary, at);
            bool threw = false;
            try { (void)align(g, &workspace); } catch (const RelionError &) { threw = true; }
            require(threw && fired && failure.hasFailed() && !workspace.isValid(),
                    "partial initialization fault did not invalidate/retain/throw");
            requireEmpty();
            arm();
            const Result recovered = align(g, &workspace);
            require(counts[MALLOC] == 8 && workspace.isValid(), "partial failure left stale cache");
            require(workspace.release(), "recovered release failed");
            requireEmpty(); active = false;
            exact(recovered, align(g, nullptr));
            ++trials;
        }
    }
    std::cout << "PASS: " << trials << " initialization failures and exact recovery controls\n";
}
void populatedReplacementFailures() {
    const Geometry a = {64,64,4,2,1,17}, b = {80,72,3,5,.6,18};
    {
        CudaFailureState failure;
        PatchAlignmentWorkspace workspace(&failure);
        arm(); (void)align(a, &workspace);
        arm(MALLOC, 3); bool threw = false;
        try { (void)align(b, &workspace); } catch (const RelionError &) { threw = true; }
        require(threw && fired && failure.hasFailed() && !failure.isPoisoned() &&
                !workspace.isValid(), "populated replacement partial fault left valid state");
        requireEmpty();
        require(counts[FREE] == 10 && counts[EVENT_DESTROY] == 16 &&
                counts[PLAN_DESTROY] == 1, "replacement did not release old and partial new resources");
        arm();
        const Result recovered = align(b, &workspace);
        require(workspace.isValid() && counts[MALLOC] == 8 && counts[PLAN_MAKE] == 1,
                "replacement recovery used stale geometry/resources");
        require(workspace.release(), "replacement recovery cleanup failed");
        requireEmpty(); active = false;
        exact(recovered, align(b, nullptr));
    }
    {
        CudaFailureState failure;
        PatchAlignmentWorkspace workspace(&failure);
        arm(); (void)align(a, &workspace);
        arm(FREE, 1, true); bool threw = false;
        try { (void)align(b, &workspace); } catch (const RelionError &) { threw = true; }
        require(threw && fired && failure.isPoisoned() && !workspace.isValid(),
                "populated replacement failed to retain fatal release status");
        require(counts[MALLOC] == 0 && counts[EVENT_CREATE] == 0 &&
                counts[PLAN_CREATE] == 0 && counts[FREE] == 8 &&
                counts[EVENT_DESTROY] == 8 && counts[PLAN_DESTROY] == 1,
                "replacement initialized B after fatal cleanup of A");
        requireEmpty();
        arm(); bool refused = false;
        try { (void)align(b, &workspace); } catch (const RelionError &) { refused = true; }
        require(refused && counts[MALLOC] == 0 && counts[EVENT_CREATE] == 0 &&
                counts[PLAN_CREATE] == 0, "fatal replacement allowed later redispatch");
        require(workspace.release(), "fatal replacement left stale owners");
        active = false;
    }
    std::cout << "PASS: populated A->B partial-init exact recovery and fatal-release/no-redispatch controls\n";
}
void ephemeralCleanupMarkers() {
    const Geometry g = {64,64,4,2,1,19};
    for (Boundary boundary : {FREE, EVENT_DESTROY, PLAN_DESTROY}) {
        arm(boundary, 1); bool threw = false;
        try { (void)align(g, nullptr); } catch (const RelionError &) { threw = true; }
        require(threw && fired, "ephemeral cleanup control did not fire/throw");
        require(last_log.find("[CUDA Patch Alignment] completed;") == std::string::npos,
                "ephemeral entry point emitted completion before failed cleanup");
        requireEmpty(); active = false;
    }
    arm(); (void)align(g, nullptr);
    require(last_log.find("[CUDA Patch Alignment] completed;") != std::string::npos,
            "healthy ephemeral entry point omitted completion marker");
    requireEmpty(); active = false;
    std::cout << "PASS: 3 ephemeral cleanup failures withheld completion marker; healthy cleanup emitted it\n";
}
void releaseAndFatalFailures() {
    const Geometry g = {64,64,4,2,1,12};
    for (Boundary boundary : {FREE, EVENT_DESTROY, PLAN_DESTROY}) {
        CudaFailureState failure;
        PatchAlignmentWorkspace workspace(&failure);
        arm(); (void)align(g, &workspace);
        arm(boundary, 1, boundary != PLAN_DESTROY);
        require(!workspace.release() && fired && failure.hasFailed() && !workspace.isValid(),
                "cleanup error was not checked/retained/invalidated");
        requireEmpty();
        require(counts[FREE] == 8 && counts[EVENT_DESTROY] == 8 && counts[PLAN_DESTROY] == 1,
                "cleanup stopped at first failure");
        if (boundary != PLAN_DESTROY) {
            require(failure.isPoisoned(), "cleanup lost fatal return code");
            arm(); bool refused = false;
            try { (void)align(g, &workspace); } catch (const RelionError &) { refused = true; }
            require(refused && counts[MALLOC] == 0 && counts[EVENT_CREATE] == 0 &&
                    counts[PLAN_CREATE] == 0, "poisoned workspace redispatched");
        }
        require(workspace.release(), "cleanup failure re-released stale resources");
        active = false;
    }
    for (bool late : {false, true}) {
        CudaFailureState failure;
        PatchAlignmentWorkspace workspace(&failure);
        arm(MALLOC, late ? 3 : 1, !late);
        late_fatal_free = late;
        bool threw = false;
        try { (void)align(g, &workspace); } catch (const RelionError &) { threw = true; }
        require(threw && fired && failure.isPoisoned() && !workspace.isValid(),
                "initialization/late cleanup fatal error lost");
        require(failure.firstError() == (late ? cudaErrorMemoryAllocation : cudaErrorIllegalAddress),
                "first failure provenance overwritten");
        requireEmpty();
        arm(); bool refused = false;
        try { (void)align(g, &workspace); } catch (const RelionError &) { refused = true; }
        require(refused && counts[MALLOC] == 0 && counts[EVENT_CREATE] == 0 &&
                counts[PLAN_CREATE] == 0, "fatal path reused/reallocated resources");
        active = false;
    }
    std::cout << "PASS: 3 checked cleanup failures and 4 fatal reuse refusals (injected codes, not poisoned hardware)\n";
}
}
int main() {
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n"; return 1;
    }
    try {
        healthyAndKeys(); initializationFailures(); populatedReplacementFailures();
        ephemeralCleanupMarkers(); releaseAndFatalFailures();
        requireEmpty();
    } catch (const std::exception &e) {
        std::cerr << "FAIL: " << e.what() << '\n'; return 1;
    } catch (RelionError &e) {
        std::cerr << "Unexpected production exception: " << e << '\n'; return 1;
    }
    std::cout << "PASS: movie-scoped patch workspace actual-path matrix\n";
    return 0;
}
