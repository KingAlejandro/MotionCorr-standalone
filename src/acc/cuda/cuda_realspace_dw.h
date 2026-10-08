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
    void *pinned_stage = nullptr,   // optional caller-owned pinned host buffer for the final download
    size_t pinned_stage_bytes = 0   // its capacity; used only when >= one real frame
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
