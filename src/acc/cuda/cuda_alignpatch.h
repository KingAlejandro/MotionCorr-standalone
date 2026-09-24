#ifndef CUDA_ALIGNPATCH_H_
#define CUDA_ALIGNPATCH_H_

#include <vector>
#include <ostream>
#include "src/multidim_array.h"
#include "src/complex.h"

#ifdef _CUDA_ENABLED
/**
 * Standalone CUDA implementation of global patch alignment (Issue #16).
 * Performs batched reference calculation, CCF formation, cuFFT inverse transform,
 * peak finding with Jasenko quadratic interpolation, and Fourier shifting on GPU.
 */
bool cudaAlignPatch(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile
);
#endif

#endif // CUDA_ALIGNPATCH_H_
