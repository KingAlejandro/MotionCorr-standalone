#ifndef METAL_ALIGNPATCH_H_
#define METAL_ALIGNPATCH_H_

#include <vector>
#include <string>
#include <ostream>
#include "src/multidim_array.h"
#include "src/complex.h"

#ifdef _METAL_ENABLED

/**
 * Returns the count of available Metal-capable GPU devices on the system.
 */
int metalGetDeviceCount();

/**
 * Returns the device name for a given Metal device ID.
 * Throws RelionError if the device ID is invalid or device cannot be acquired.
 */
std::string metalGetDeviceName(int device_id);

/**
 * Standalone Metal implementation of global patch alignment.
 *
 * Backend Interface Contract for Issue #32:
 * - Fframes: vector of 2D complex Fourier-transformed frames (input/output).
 *            Frames are copied to shared Metal buffers and shifted in place.
 * - pnx, pny: patch dimensions in X and Y (even integers).
 * - scaled_B: B-factor scaling factor for CCF weighting filter.
 * - xshifts, yshifts: output frame drift trajectories (populated by alignment).
 * - max_iter: maximum alignment iterations.
 * - ccf_downsample: cross-correlation map downsampling scale factor.
 * - device_id: selected zero-based Metal device index.
 * - logfile: output stream for logging device profile and progress markers.
 *
 * - Executes weighting, reference accumulation, cross-correlation, MPSGraph
 *   inverse FFT, peak/subpixel interpolation and Fourier phase-shift stages.
 * - Throws RelionError for invalid inputs, command-buffer errors, missing FFT
 *   results, or failure to converge. It never falls back to CPU.
 * - Writes the exact `[Metal Global Alignment Completed]` marker only after
 *   convergence and host output copy; availability/profile markers alone are
 *   not completion evidence.
 */
bool metalAlignPatch(
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

#endif // _METAL_ENABLED

#endif // METAL_ALIGNPATCH_H_
