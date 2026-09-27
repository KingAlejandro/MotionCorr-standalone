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

/**
 * CUDA implementation of analytical dose weighting, cuFFT inverse transform,
 * and real-space polynomial bilinear interpolation with streaming accumulation.
 *
 * Staging budget: < 200 MiB VRAM (single-frame working buffers + accumulator canvas).
 */
bool cudaDoseWeightAndInterpolate(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    Image<float> &Isum,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile
);

/**
 * In-VRAM CUDA implementation of analytical dose weighting, cuFFT inverse transform,
 * and real-space polynomial bilinear interpolation directly from resident d_Fframes (Issue #50).
 */
bool cudaDoseWeightAndInterpolateDevice(
    const cufftComplex *d_Fframes,
    Image<float> &Isum,
    const int nx, const int ny, const int n_frames,
    const std::vector<RFLOAT> &doses,
    const RFLOAT apix,
    const ThirdOrderPolynomialModel *model, // nullptr if global motion only
    const int device_id,
    std::ostream &logfile
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
    std::ostream &logfile
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
    std::ostream &logfile
);

#endif // _CUDA_ENABLED

#endif // CUDA_REALSPACE_DW_H_
