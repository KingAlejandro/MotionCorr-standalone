// Unit tests for mc_cuda::CudaWorkerPlanPool and cuFFT plan lifetime controls.
// Interposition is confined to this test executable via linker --wrap flags.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#include "src/acc/cuda/cuda_realspace_dw.h"
#include "src/acc/cuda/cuda_failure_state.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstring>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace {

enum Boundary {
    NONE,
    MALLOC,
    FREE,
    PLAN_CREATE,
    PLAN_MAKE,
    PLAN_DESTROY,
    BOUNDARIES
};

bool active = false;
bool fired = false;
Boundary fault = NONE;
int ordinal = 0;
int counts[BOUNDARIES] = {};
std::set<void*> buffers;
std::set<cufftHandle> plans;
size_t stale = 0;

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
    active = true;
}

void disarm() {
    active = false;
    fault = NONE;
    ordinal = 0;
    fired = false;
}

void require(bool ok, const char *message) {
    if (!ok) {
        std::cerr << "Assertion failed: " << message << std::endl;
        throw std::runtime_error(message);
    }
}

} // namespace

extern "C" {

cudaError_t __real_cudaMalloc(void**, size_t);
cudaError_t __real_cudaFree(void*);
cufftResult __real_cufftCreate(cufftHandle*);
cufftResult __real_cufftMakePlanMany(cufftHandle, int, int*, int*, int, int,
                                    int*, int, int, cufftType, int, size_t*);
cufftResult __real_cufftDestroy(cufftHandle);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    if (fail(MALLOC)) {
        *ptr = nullptr;
        return cudaErrorMemoryAllocation;
    }
    const cudaError_t result = __real_cudaMalloc(ptr, bytes);
    if (active && result == cudaSuccess) buffers.insert(*ptr);
    return result;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const bool inject = fail(FREE);
    const cudaError_t result = __real_cudaFree(ptr);
    if (active && ptr && result == cudaSuccess) {
        if (!buffers.erase(ptr)) { ++stale; }
    }
    return inject && result == cudaSuccess ? cudaErrorMemoryAllocation : result;
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
        if (!plans.erase(plan)) { ++stale; }
    }
    return inject && result == CUFFT_SUCCESS ? CUFFT_INTERNAL_ERROR : result;
}

} // extern "C"

namespace {

void testSessionLease() {
    std::cout << "Testing session lease exclusivity on same thread..." << std::endl;
    std::ostringstream log1, log2;
    CudaMovieSession s1(64, 64, 2, 0, log1);
    require(s1.initialize(), "s1 initialization failed");

    CudaMovieSession s2(64, 64, 2, 0, log2);
    // Concurrent session lease on the same thread must be denied
    require(!s2.initialize(), "s2 concurrent lease was unexpectedly granted");

    s1.release();
    // After s1 releases, s2 should be able to acquire the lease
    require(s2.initialize(), "s2 failed to acquire lease after s1 release");
    s2.release();
    std::cout << "  PASS: session lease exclusivity" << std::endl;
}

void testPatchPlanReplacementNoDoubleFree() {
    std::cout << "Testing patch plan replacement double-free prevention..." << std::endl;
    stale = 0;
    mc_cuda::getWorkerPlanPool().dropAll();
    buffers.clear();
    plans.clear();

    arm();
    std::ostringstream log;
    CudaMovieSession session(128, 128, 4, 0, log);
    require(session.initialize(), "session initialization failed");

    const int group_start[2] = {0, 2};
    const int group_size[2] = {2, 2};

    // First patch geometry (32x32, 2 groups)
    cufftComplex *d_out_fpatches = nullptr;
    require(cudaMalloc((void**)&d_out_fpatches, (size_t)2 * 32 * (32 / 2 + 1) * sizeof(cufftComplex)) == cudaSuccess, "alloc out");
    bool ok1 = session.preparePatchInVram(0, 0, 32, 32, 2, group_start, group_size, d_out_fpatches);
    require(ok1, "preparePatchInVram geom 1 failed");
    require(stale == 0, "stale free/destroy detected during geom 1");

    // Second patch geometry (48x48, 2 groups) -> replaces cached patch plan
    cudaFree(d_out_fpatches);
    require(cudaMalloc((void**)&d_out_fpatches, (size_t)2 * 48 * (48 / 2 + 1) * sizeof(cufftComplex)) == cudaSuccess, "alloc out 2");
    bool ok2 = session.preparePatchInVram(0, 0, 48, 48, 2, group_start, group_size, d_out_fpatches);
    require(ok2, "preparePatchInVram geom 2 failed");
    require(stale == 0, "stale free/destroy detected during geom 2 replacement (double-destroy regression)");

    cudaFree(d_out_fpatches);
    session.release();
    require(stale == 0, "stale free/destroy detected during session release");

    // Pool cleanup must also be clean and not double-free
    mc_cuda::getWorkerPlanPool().dropAll();
    require(stale == 0, "stale free/destroy detected during pool dropAll");
    require(plans.empty(), "plans remaining after pool dropAll");
    require(buffers.empty(), "buffers remaining after session release and pool dropAll");
    disarm();
    std::cout << "  PASS: patch plan replacement has zero double-destroys (stale == 0)" << std::endl;
}

void testPatchPlanMakeFailureNoLeak() {
    std::cout << "Testing patch plan planning failure leak prevention..." << std::endl;
    mc_cuda::getWorkerPlanPool().dropAll();

    std::ostringstream log;
    CudaMovieSession session(128, 128, 4, 0, log);
    require(session.initialize(), "session initialization failed");

    const int group_start[2] = {0, 2};
    const int group_size[2] = {2, 2};
    cufftComplex *d_out = nullptr;
    require(cudaMalloc((void**)&d_out, (size_t)2 * 32 * (32 / 2 + 1) * sizeof(cufftComplex)) == cudaSuccess, "alloc out");

    // Clear tracked plans and arm failure at cufftMakePlanMany
    plans.clear();
    arm(PLAN_MAKE, 1);
    bool ok = session.preparePatchInVram(0, 0, 32, 32, 2, group_start, group_size, d_out);
    require(!ok, "preparePatchInVram should fail on plan make failure");
    disarm();

    // Verify that the handle allocated by cufftCreate was destroyed and not leaked
    require(plans.empty(), "cuFFT handle was leaked when cufftMakePlanMany failed in patch prep");
    cudaFree(d_out);
    session.release();
    std::cout << "  PASS: patch plan planning failure leaks no handles" << std::endl;
}

void testGlobalPlanMakeFailureNoLeak() {
    std::cout << "Testing global plan planning failure leak prevention..." << std::endl;
    mc_cuda::getWorkerPlanPool().dropAll();

    std::ostringstream log;
    CudaMovieSession session(64, 64, 2, 0, log);

    // Fail cufftMakePlanMany on first global plan (R2C)
    plans.clear();
    arm(PLAN_MAKE, 1);
    bool ok = session.initialize();
    require(!ok, "session initialization should fail on plan make failure");
    disarm();

    require(plans.empty(), "cuFFT handle was leaked when cufftMakePlanMany failed in global plan");
    session.release();
    std::cout << "  PASS: global plan planning failure leaks no handles" << std::endl;
}

void testDoseWeightPlanMakeFailureNoLeak() {
    std::cout << "Testing dose-weight plan planning failure leak prevention..." << std::endl;
    mc_cuda::getWorkerPlanPool().dropAll();

    cufftComplex *d_Fframes = nullptr;
    require(cudaMalloc((void**)&d_Fframes, (size_t)2 * 64 * 33 * sizeof(cufftComplex)) == cudaSuccess, "alloc Fframes");
    Image<float> Isum;
    std::vector<RFLOAT> doses = {1.0, 2.0};
    std::ostringstream log;
    CudaFailureState failure;

    plans.clear();
    arm(PLAN_MAKE, 1);
    bool ok = cudaDoseWeightAndInterpolateDevice(d_Fframes, Isum, 64, 64, 2, doses, 1.0, nullptr, 0, log, &failure);
    require(!ok, "cudaDoseWeightAndInterpolateDevice should fail on plan make failure");
    disarm();

    require(plans.empty(), "cuFFT handle was leaked when cufftMakePlanMany failed in DW plan");
    cudaFree(d_Fframes);
    std::cout << "  PASS: DW plan planning failure leaks no handles" << std::endl;
}

void testPoisonDropAll() {
    std::cout << "Testing worker plan pool dropAll on session poisoning..." << std::endl;
    mc_cuda::getWorkerPlanPool().dropAll();

    std::ostringstream log;
    CudaMovieSession session(64, 64, 2, 0, log);
    require(session.initialize(), "session init failed");

    require(mc_cuda::getWorkerPlanPool().global.valid, "global pool should be valid");

    // Simulate fatal error / poisoning during session
    session.getFailureState().record(cudaErrorIllegalAddress, "simulated fatal error", 42);

    session.release();
    require(!mc_cuda::getWorkerPlanPool().global.valid, "global pool should be dropped on fatal release");
    require(!mc_cuda::getWorkerPlanPool().patch.valid, "patch pool should be dropped on fatal release");
    require(!mc_cuda::getWorkerPlanPool().dw.valid, "dw pool should be dropped on fatal release");
    std::cout << "  PASS: all worker pools dropped on session release under fatal context" << std::endl;
}

} // namespace

int main() {
    int dev_count = 0;
    if (cudaGetDeviceCount(&dev_count) != cudaSuccess || dev_count == 0) {
        std::cout << "No CUDA devices available, skipping cuda_plan_pool test." << std::endl;
        return 0;
    }

    try {
        testSessionLease();
        testPatchPlanReplacementNoDoubleFree();
        testPatchPlanMakeFailureNoLeak();
        testGlobalPlanMakeFailureNoLeak();
        testDoseWeightPlanMakeFailureNoLeak();
        testPoisonDropAll();
    } catch (const std::exception &e) {
        std::cerr << "Test failed with exception: " << e.what() << std::endl;
        return 1;
    }

    std::cout << "All cuda_plan_pool tests passed successfully!" << std::endl;
    return 0;
}
