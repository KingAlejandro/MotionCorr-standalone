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
 *            Issue #32 will upload frame Fourier data to Metal buffers.
 * - pnx, pny: patch dimensions in X and Y (even integers).
 * - scaled_B: B-factor scaling factor for CCF weighting filter.
 * - xshifts, yshifts: output frame drift trajectories (populated by alignment).
 * - max_iter: maximum alignment iterations.
 * - ccf_downsample: cross-correlation map downsampling scale factor.
 * - device_id: selected zero-based Metal device index.
 * - logfile: output stream for logging device profile and progress markers.
 *
 * Smoke Dispatch Behavior (Issue #30):
 * - Validates device_id and acquires MTLDevice.
 * - Creates MTLCommandQueue and allocates test MTLBuffer to verify device operation.
 * - Dispatches a command buffer and waits for completion to prove device execution.
 * - Emits startup and profile markers:
 *     stdout: "[Metal] Executed Metal dispatch smoke on device: <name>"
 *     logfile: "[Metal Global Alignment Profile]"
 *              "Device: <name>"
 *              "Stage: Dispatch smoke verification (Issue #30 interface contract for Issue #32)"
 *              "Total Metal Alignment Time: 0.000 s"
 * - Throws RelionError on device/command queue failure. Never falls back to CPU.
 * - Returns true on success.
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
