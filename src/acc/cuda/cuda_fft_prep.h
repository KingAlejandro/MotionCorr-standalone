#ifndef CUDA_FFT_PREP_H_
#define CUDA_FFT_PREP_H_

#include <vector>
#include <ostream>
#include "src/image.h"
#include "src/multidim_array.h"
#include "src/complex.h"

#ifdef _CUDA_ENABLED

/**
 * CUDA 2D forward Real-to-Complex FFT for full-resolution movie frames.
 * Uses cuFFT R2C and applies 1.0f / (nx * ny) scaling to match NewFFT::FourierTransform FwdOnly.
 */
bool cudaForwardFFT2D(
    const std::vector<Image<float> > &Iframes,
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile
);

/**
 * CUDA 2D inverse Complex-to-Real FFT for full-resolution movie frames.
 * Uses cuFFT C2R to restore real-space frames after global alignment.
 * If keep_on_gpu is true, retains d_Iframes in device memory for subsequent fast patch extraction.
 */
bool cudaInverseFFT2D(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    std::vector<Image<float> > &Iframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile,
    bool keep_on_gpu = false
);

/**
 * CUDA Patch Extraction, temporal group summation, and forward 2D R2C FFT.
 * If d_Iframes is retained in device memory from cudaInverseFFT2D, extracts and groups
 * directly on device with zero host memory copies, then executes batched cuFFT R2C.
 */
bool cudaPreparePatch(
    const std::vector<Image<float> > &Iframes,
    const int x_start, const int x_end,
    const int y_start, const int y_end,
    const int n_groups,
    const std::vector<int> &group_start,
    const std::vector<int> &group_size,
    std::vector<MultidimArray<fComplex> > &Fpatches,
    const int device_id,
    std::ostream &logfile
);

/**
 * Release any retained movie frame buffers from device memory.
 */
void cudaReleaseCachedFrames();

#endif // _CUDA_ENABLED

#endif // CUDA_FFT_PREP_H_
