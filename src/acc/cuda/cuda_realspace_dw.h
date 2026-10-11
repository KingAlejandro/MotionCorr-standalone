#ifndef CUDA_REALSPACE_DW_H_
#define CUDA_REALSPACE_DW_H_

#include <vector>
#include <ostream>
#include "src/image.h"
#include "src/multidim_array.h"
#include "src/complex.h"
#include "src/micrograph_model.h"

#ifdef _CUDA_ENABLED
#include <cufft.h>
#include "src/acc/cuda/cuda_failure_state.h"

/**
 * CUDA implementation of analytical dose weighting, cuFFT inverse transform,
 * and real-space polynomial bilinear interpolation with streaming accumulation.
 *
 * Reconstruction-scoped buffers: one Fourier frame, one real frame, accumulator,
 * dose vector and one float normalization plane (nfy * nfx). The actual owned
 * allocation plus cuFFT workspace is reported in the reconstruction profile.
 */
bool cudaDoseWeightAndInterpolate(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    Image<float> &Isum,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile,
    CudaFailureState *failure = nullptr // receives every consumed CUDA/cuFFT status, cleanup included
);

/**
 * Session mode for cudaDoseWeightAndInterpolateDevice.
 *
 * `fourier` is a caller-owned complex frame (ny*(nx/2+1) cufftComplex, from
 * cudaMalloc) that becomes the C2R input: the weight kernel writes it out of
 * place, so the resident Fourier frames need no per-frame copy. It is only
 * used, never freed here, and must not overlap d_Fframes. The accumulator,
 * real frame, normalization plane and doses share ONE allocation made and
 * checked-freed by the call, so cleanup status still gates success exactly as
 * with the per-buffer allocations. Passing no DoseWeightScratch keeps the
 * original five reconstruction-owned allocations (the non-resident fallback).
 */
struct DoseWeightScratch {
    cufftComplex *fourier = nullptr;
    // Optional caller-owned device memory of at least doseScratchLayout().total_bytes
    // that nothing else uses during the call. When set it replaces the single
    // allocation: nothing is allocated or freed for the four buffers.
    char *block = nullptr;
};

namespace mc_cuda {
/** Offsets inside the single block used in session mode; every region 512-byte aligned. */
struct DoseScratchLayout {
    size_t accumulator_offset, real_offset, normalization_offset, doses_offset, total_bytes;
};
inline DoseScratchLayout doseScratchLayout(int nx, int ny, int n_frames) {
    const size_t align = 512;
    auto up = [align](size_t v) { return (v + align - 1) / align * align; };
    const size_t real_bytes = up((size_t)nx * ny * sizeof(float));
    const size_t plane_bytes = up((size_t)(nx / 2 + 1) * ny * sizeof(float));
    const size_t dose_bytes = up((size_t)(n_frames > 0 ? n_frames : 1) * sizeof(float));
    DoseScratchLayout l;
    l.accumulator_offset = 0;
    l.real_offset = real_bytes;
    l.normalization_offset = 2 * real_bytes;
    l.doses_offset = 2 * real_bytes + plane_bytes;
    l.total_bytes = 2 * real_bytes + plane_bytes + dose_bytes;
    return l;
}
} // namespace mc_cuda

/**
 * In-VRAM CUDA implementation of analytical dose weighting, cuFFT inverse transform,
 * and real-space polynomial bilinear interpolation directly from resident d_Fframes (Issue #50).
 * A nonzero borrowed_c2r must belong to the calling session on device_id, have
 * rank2 dimensions {ny,nx}, contiguous single-precision C2R batch1 and default
 * stream0. Its caller-owned work area remains live through this synchronous
 * call; neither the plan nor work area is rebound, retained or destroyed here.
 * With zero, the original reconstruction-owned plan and cleanup are unchanged.
 */
bool cudaDoseWeightAndInterpolateDevice(
    const cufftComplex *d_Fframes,
    Image<float> &Isum,
    const int nx, const int ny, const int n_frames,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile,
    CudaFailureState *failure = nullptr, // receives every consumed status, cleanup included
    cufftHandle borrowed_c2r = 0, // matching session-owned batch-one C2R; never destroyed here
    const DoseWeightScratch *scratch = nullptr // session mode when non-null; null keeps the original ownership
);

/**
 * CUDA implementation of real-space polynomial bilinear interpolation and accumulation
 * for non-dose-weighted frames (e.g. !do_dose_weighting or save_noDW).
 *
 * Supports optional even/odd frame splitting when Isum_even and Isum_odd are non-null.
 */
bool cudaRealSpaceInterpolation(
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const std::vector<Image<float> > &Iframes,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile,
    CudaFailureState *failure = nullptr // receives every consumed CUDA/cuFFT status, cleanup included
);

/**
 * In-VRAM CUDA implementation of real-space polynomial bilinear interpolation and accumulation
 * directly from resident d_Iframes (Issue #50).
 */
bool cudaRealSpaceInterpolationDevice(
    const float *d_Iframes,
    Image<float> &Isum,
    Image<float> *Isum_even,
    Image<float> *Isum_odd,
    const int nx, const int ny, const int n_frames,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile,
    CudaFailureState *failure = nullptr // receives every consumed CUDA/cuFFT status, cleanup included
);

#endif // _CUDA_ENABLED

#endif // CUDA_REALSPACE_DW_H_
