// SPDX-License-Identifier: GPL-2.0-or-later
// Native controls for the worker-retained movie geometry (frame buffers,
// whole-frame cuFFT plans, their work area and the inverse tile).
//
// Two oracles. The products -- sum, forward spectra, inverse frames -- must be
// byte-identical between a fresh session, a session that took the retained
// entry, and one that took it poisoned. The allocation and plan-creation
// ledger shows the entry was actually taken, was never aliased by a second
// live session, and was never handed on by a failed session.
//
// --expect-mismatch inverts the verdict for the compiled mutants.
#include "src/acc/cuda/cuda_movie_session.h"
#include "src/acc/cuda/cuda_plan_pool.h"
#include "src/error.h"
#include <cuda_runtime.h>
#include <cufft.h>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::map<void *, size_t> buffers;
size_t mallocs = 0;
size_t stale_frees = 0;
size_t plan_creates = 0;
size_t failures = 0;
// The allocation count at which a watched pointer was freed.
const void *watched = nullptr;
long watched_freed_at = -1;

void check(bool ok, const char *message) {
    if (ok) return;
    ++failures;
    std::cerr << "CHECK FAILED: " << message << std::endl;
}

} // namespace

extern "C" {
cudaError_t __real_cudaMalloc(void **, size_t);
cudaError_t __real_cudaFree(void *);
cufftResult __real_cufftCreate(cufftHandle *);

cudaError_t __wrap_cudaMalloc(void **ptr, size_t bytes) {
    const cudaError_t status = __real_cudaMalloc(ptr, bytes);
    if (status == cudaSuccess) { buffers[*ptr] = bytes; ++mallocs; }
    return status;
}

cudaError_t __wrap_cudaFree(void *ptr) {
    const cudaError_t status = __real_cudaFree(ptr);
    if (ptr != nullptr && ptr == watched && status == cudaSuccess) watched_freed_at = (long)mallocs;
    if (ptr != nullptr && status == cudaSuccess && buffers.erase(ptr) == 0) ++stale_frees;
    return status;
}

cufftResult __wrap_cufftCreate(cufftHandle *plan) {
    ++plan_creates;
    return __real_cufftCreate(plan);
}
} // extern "C"

namespace {

struct Products {
    MultidimArray<float> sum;
    std::vector<MultidimArray<fComplex> > spectra;
    std::vector<Image<float> > frames;
};

std::vector<Image<float> > makeFrames(int nx, int ny, int n_frames) {
    std::vector<Image<float> > frames(n_frames);
    for (int f = 0; f < n_frames; ++f) {
        frames[f]().reshape(ny, nx);
        for (int i = 0; i < ny; ++i)
            for (int j = 0; j < nx; ++j)
                DIRECT_A2D_ELEM(frames[f](), i, j) =
                    (float)(f + 1) * 0.5f + 0.25f * (float)((j * 7 + i * 3) % 11) - 0.125f * (float)i;
    }
    return frames;
}

bool same(const void *a, const void *b, size_t bytes) { return std::memcmp(a, b, bytes) == 0; }

bool sameProducts(const Products &a, const Products &b) {
    if (NZYXSIZE(a.sum) != NZYXSIZE(b.sum) || a.spectra.size() != b.spectra.size() ||
        a.frames.size() != b.frames.size() || NZYXSIZE(a.sum) == 0)
        return false;
    if (!same(a.sum.data, b.sum.data, NZYXSIZE(a.sum) * sizeof(float))) return false;
    for (size_t f = 0; f < a.spectra.size(); ++f) {
        if (NZYXSIZE(a.spectra[f]) != NZYXSIZE(b.spectra[f]) ||
            !same(a.spectra[f].data, b.spectra[f].data, NZYXSIZE(a.spectra[f]) * sizeof(fComplex)))
            return false;
        if (NZYXSIZE(a.frames[f]()) != NZYXSIZE(b.frames[f]()) ||
            !same(a.frames[f]().data, b.frames[f]().data, NZYXSIZE(a.frames[f]()) * sizeof(float)))
            return false;
    }
    return true;
}

// The steps that read and write every retained resource: d_Iframes (sum, R2C
// input, C2R output), d_Fframes, both plans, the shared work area and the tile.
bool runPipeline(CudaMovieSession &session, const std::vector<Image<float> > &input, Products &out) {
    return session.applyGainDefectsAndSum(input, nullptr, out.sum, true) &&
           session.releasePreprocessingBuffers() &&
           session.computeGlobalForwardFFT() &&
           session.downloadFourierFrames(out.spectra) &&
           session.computeGlobalInverseFFT() &&
           session.downloadRealFrames(out.frames);
}

struct MovieLedger { size_t init_mallocs = 0, init_plans = 0; const void *iframes = nullptr; };

bool runMovie(int nx, int ny, const std::vector<Image<float> > &input, Products &out,
              MovieLedger &ledger) {
    std::ostringstream log;
    CudaMovieSession session(nx, ny, (int)input.size(), 0, log);
    const size_t m0 = mallocs, p0 = plan_creates;
    if (!session.initialize()) return false;
    ledger.init_mallocs = mallocs - m0;
    ledger.init_plans = plan_creates - p0;
    ledger.iframes = session.getDeviceRealFrames();
    const bool ok = runPipeline(session, input, out);
    session.release();
    return ok && !session.getFailureState().hasFailed();
}

mc_cuda::CudaWorkerPlanPool &pool() { return mc_cuda::getWorkerPlanPool(); }

void testReuse() {
    std::cout << "Testing retained geometry reuse..." << std::endl;
    const int nx = 64, ny = 48;
    const auto input = makeFrames(nx, ny, 3);
    unsetenv("MOTIONCORR_FRAME_POOL_POISON");

    setenv("MOTIONCORR_RETAIN_GEOMETRY", "0", 1);
    Products fresh;
    MovieLedger l0;
    check(runMovie(nx, ny, input, fresh, l0), "fresh movie failed");
    check(!pool().geometry.held() && pool().retainedBytes() == 0,
          "MOTIONCORR_RETAIN_GEOMETRY=0 still retained the geometry");
    check(l0.init_plans == 2 && l0.init_mallocs == 5, "a fresh session did not allocate its geometry");
    unsetenv("MOTIONCORR_RETAIN_GEOMETRY");

    Products first, second, poisoned;
    MovieLedger l1, l2, l3;
    check(runMovie(nx, ny, input, first, l1), "first retained movie failed");
    check(l1.init_plans == 2, "an empty pool did not create both plans");
    check(pool().geometry.matches(0, nx, ny, 3), "a healthy session did not return its geometry");
    const size_t sz_comp = (size_t)ny * (nx / 2 + 1) * sizeof(cufftComplex);
    const size_t floor_bytes = 3 * (size_t)nx * ny * sizeof(float) + 3 * sz_comp + sz_comp;
    check(pool().retainedBytes() == pool().geometry.retainedBytes() &&
          pool().geometry.retainedBytes() > floor_bytes,
          "retained geometry byte count wrong");
    check(buffers.count(pool().geometry.iframes) == 1 && buffers.count(pool().geometry.fframes) == 1 &&
          buffers.count(pool().geometry.fft_work) == 1 && buffers.count(pool().geometry.inverse_tile) == 1,
          "retained geometry does not own live allocations");

    check(runMovie(nx, ny, input, second, l2), "second retained movie failed");
    // Only d_Isum, which preprocessing frees mid-movie, is allocated again.
    check(l2.init_mallocs == 1, "a key hit still allocated the movie buffers");
    check(l2.init_plans == 0, "a key hit still created cuFFT plans");
    check(l2.iframes == l1.iframes, "a key hit did not hand out the retained frame buffer");

    setenv("MOTIONCORR_FRAME_POOL_POISON", "1", 1);
    check(runMovie(nx, ny, input, poisoned, l3), "poisoned retained movie failed");
    unsetenv("MOTIONCORR_FRAME_POOL_POISON");
    check(l3.init_plans == 0, "the poisoned movie did not take the entry");

    check(sameProducts(fresh, first), "first retained movie changed products");
    check(sameProducts(fresh, second), "a retained geometry changed products");
    check(sameProducts(fresh, poisoned), "a poisoned retained geometry changed products");
}

void testGeometryChange() {
    std::cout << "Testing a geometry change discards the entry before allocating..." << std::endl;
    const int nx = 64, ny = 48;
    Products a, b;
    MovieLedger la, lb;
    check(runMovie(nx, ny, makeFrames(nx, ny, 3), a, la), "geometry fixture movie failed");
    const void *old_iframes = pool().geometry.iframes;
    check(old_iframes != nullptr, "geometry fixture did not retain");
    // n_frames alone changes the key.
    watched = old_iframes;
    watched_freed_at = -1;
    const long mallocs_before = (long)mallocs;
    check(runMovie(nx, ny, makeFrames(nx, ny, 4), b, lb), "changed-geometry movie failed");
    watched = nullptr;
    check(lb.init_plans == 2 && lb.init_mallocs == 5,
          "a changed key reused the old plans or buffers");
    check(watched_freed_at == mallocs_before,
          "the mismatching entry was not freed before the new movie allocated");
    check(pool().geometry.matches(0, nx, ny, 4), "the changed geometry was not retained");
}

void testFailedSessionDoesNotReturn() {
    std::cout << "Testing a failed session frees instead of returning..." << std::endl;
    const int nx = 64, ny = 48;
    const auto input = makeFrames(nx, ny, 3);
    Products out;
    MovieLedger l;
    check(runMovie(nx, ny, input, out, l), "failure fixture movie failed");
    std::ostringstream log;
    CudaMovieSession failed(nx, ny, 3, 0, log);
    check(failed.initialize(), "failure fixture initialization");
    check(!pool().geometry.held(), "a taken entry stayed in the pool slot");
    Products partial;
    check(runPipeline(failed, input, partial), "failure fixture pipeline");
    failed.getFailureState().record(cudaErrorMemoryAllocation, "recoverable fixture failure", 1);
    const void *taken = failed.getDeviceRealFrames();
    failed.release();
    check(!pool().geometry.held() && pool().retainedBytes() == 0,
          "a failed session returned its geometry to the pool");
    check(buffers.count(const_cast<void *>(taken)) == 0, "a failed session leaked its frame buffer");

    // The release guard's dropAll would also discard a wrongly returned entry,
    // except when another live session holds the gain lease and it is refused.
    // Session A holds that lease (its gain is not uploaded yet, so B's admission
    // does not need to evict it); B fails with A still live.
    check(runMovie(nx, ny, input, out, l), "lease fixture movie failed");
    std::ostringstream log_a, log_b;
    CudaMovieSession a(nx, ny, 3, 0, log_a), b(nx, ny, 3, 0, log_b);
    a.setGainGeneration(41);
    check(a.initialize(), "lease holder initialization");
    check(b.initialize(), "failing session admitted beside the lease holder");
    check(runPipeline(b, input, partial), "lease fixture pipeline");
    b.getFailureState().record(cudaErrorMemoryAllocation, "recoverable fixture failure", 2);
    b.release();
    check(!pool().geometry.held(),
          "a failed session returned its geometry while the guard's drop was refused");
    a.release();
}

void testInterleavedSessions() {
    std::cout << "Testing two live sessions never share the entry..." << std::endl;
    const int nx = 64, ny = 48;
    const auto input = makeFrames(nx, ny, 3);
    Products seed;
    MovieLedger l;
    check(runMovie(nx, ny, input, seed, l), "interleave fixture movie failed");
    std::ostringstream log_a, log_b;
    CudaMovieSession a(nx, ny, 3, 0, log_a), b(nx, ny, 3, 0, log_b);
    check(a.initialize(), "session A initialization");
    const void *a_frames = a.getDeviceRealFrames();
    check(a_frames == l.iframes, "session A did not take the entry");
    check(b.initialize(), "session B initialization");
    check(b.getDeviceRealFrames() != a_frames, "session B aliased session A's frame buffer");
    check(buffers.count(const_cast<void *>(a_frames)) == 1, "session B freed session A's live buffer");
    Products pa, pb;
    check(runPipeline(a, input, pa) && runPipeline(b, input, pb), "interleaved pipelines");
    check(sameProducts(seed, pa) && sameProducts(seed, pb), "interleaved sessions changed products");
    a.release();
    check(pool().geometry.iframes == a_frames, "session A did not return its geometry");
    b.release();
    check(pool().geometry.iframes == a_frames, "session B displaced the returned entry");
}

} // namespace

int main(int argc, char **argv) {
    const bool expect_mismatch = argc == 2 && std::string(argv[1]) == "--expect-mismatch";
    if (argc > 2 || (argc == 2 && !expect_mismatch)) {
        std::cerr << "usage: cuda_geometry_retention [--expect-mismatch]\n";
        return 2;
    }
    if (cudaSetDevice(0) != cudaSuccess || cudaFree(nullptr) != cudaSuccess) {
        std::cerr << "Native CUDA device 0 is required\n";
        return 1;
    }
    try {
        testReuse();
        testGeometryChange();
        testFailedSessionDoesNotReturn();
        testInterleavedSessions();
        check(pool().dropAll(), "final pool drop failed");
        check(buffers.empty() && stale_frees == 0, "allocation ledger did not close");
    } catch (RelionError &e) {
        std::cerr << "unexpected production exception: " << e << '\n';
        ++failures;
    } catch (const std::exception &e) {
        std::cerr << "unexpected exception: " << e.what() << '\n';
        ++failures;
    }
    if (expect_mismatch) {
        std::cout << (failures > 0 ? "PASS: mutant detected (" : "FAIL: mutant survived (")
                  << failures << " failed checks)" << std::endl;
        return failures > 0 ? 0 : 1;
    }
    std::cout << (failures == 0 ? "PASS" : "FAIL") << ": retained geometry controls ("
              << failures << " failed checks)" << std::endl;
    return failures == 0 ? 0 : 1;
}
