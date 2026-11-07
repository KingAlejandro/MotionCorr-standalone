#ifndef METAL_RESAMPLE_H_
#define METAL_RESAMPLE_H_

#include <vector>
#include <string>
#include <ostream>
#include "src/multidim_array.h"
#include "src/complex.h"
#include "src/image.h"
#include "src/micrograph_model.h"

#ifdef _METAL_ENABLED

/**
 * GPU bilinear real-space resampling and accumulation across frames
 * using the 18-parameter polynomial motion model:
 *   x_shift(x, y, t) = sum_{i,j,k} c_{i,j,k} x^i y^j t^k
 * Evaluates 4-tap bilinear interpolation (LIN_INTERP) with edge clamping
 * identical to RELION CPU realSpaceInterpolation.
 *
 * Parameters:
 * - Isum: Output accumulated image (ny x nx).
 * - Iframes: Input vector of n_frames real-space images (each ny x nx).
 * - model: ThirdOrderPolynomialModel containing coeffX and coeffY (18 coeffs each).
 * - device_id: Metal device index (default 0).
 * - logfile: Output log stream.
 * - frame_weights: Optional per-frame dose weights (empty if unweighted/uniform).
 *
 * Returns true on success, throws RelionError on failure.
 */
bool metalRealSpaceInterpolation(
    Image<float> &Isum,
    const std::vector<Image<float> > &Iframes,
    const ThirdOrderPolynomialModel &model,
    const int device_id,
    std::ostream &logfile,
    const std::vector<float> &frame_weights = std::vector<float>()
);

/**
 * Vector overload of metalRealSpaceInterpolation:
 * - coeffX, coeffY: 18-element vectors of polynomial coefficients for X and Y shifts.
 */
bool metalRealSpaceInterpolation(
    Image<float> &Isum,
    const std::vector<Image<float> > &Iframes,
    const std::vector<float> &coeffX,
    const std::vector<float> &coeffY,
    const int device_id,
    std::ostream &logfile,
    const std::vector<float> &frame_weights = std::vector<float>()
);

/**
 * Low-level raw buffer interface for metalRealSpaceInterpolation:
 * - h_Iframes: contiguous host buffer of shape [n_frames, ny, nx]
 * - h_Isum: output host buffer of shape [ny, nx]
 * - coeffX: 18 floats
 * - coeffY: 18 floats
 * - nx, ny: frame dimensions
 * - n_frames: number of frames
 * - device_id: Metal device index
 * - logfile: output log stream
 * - frame_weights: optional array of n_frames weights (or nullptr)
 */
bool metalRealSpaceInterpolationRaw(
    const float *h_Iframes,
    float *h_Isum,
    const float *coeffX,
    const float *coeffY,
    const int nx, const int ny, const int n_frames,
    const int device_id,
    std::ostream &logfile,
    const float *frame_weights = nullptr
);

/**
 * Frequency-domain dose weighting filter (Grant & Grigorieff 2015):
 * - Fframes: vector of complex Fourier frames [n_frames, nfy, nfx]
 * - doses: cumulative electron dose after each frame (in e-/A^2)
 * - apix: pixel size in Angstroms
 * - device_id: Metal device index
 * - logfile: output log stream
 */
bool metalDoseWeighting(
    std::vector<MultidimArray<fComplex> > &Fframes,
    const std::vector<float> &doses,
    const float apix,
    const int device_id,
    std::ostream &logfile
);

#endif // _METAL_ENABLED

#endif // METAL_RESAMPLE_H_
