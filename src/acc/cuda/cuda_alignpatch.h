#ifndef CUDA_ALIGNPATCH_H_
#define CUDA_ALIGNPATCH_H_

#include <vector>
#include <ostream>
#include "src/multidim_array.h"
#include "src/complex.h"

#ifdef _CUDA_ENABLED
#include <cufft.h>
#include <memory>
#include "src/acc/cuda/cuda_failure_state.h"

/** Resources reused only within one movie's local-patch loop. Each successful call
 * overwrites every input-dependent buffer; only geometry-dependent weights persist.
 * release() is checked before reconstruction, with a destructor backstop on errors.
 */
class PatchAlignmentWorkspace {
public:
    explicit PatchAlignmentWorkspace(CudaFailureState *failure = nullptr);
    ~PatchAlignmentWorkspace();
    PatchAlignmentWorkspace(const PatchAlignmentWorkspace&) = delete;
    PatchAlignmentWorkspace& operator=(const PatchAlignmentWorkspace&) = delete;
    bool release() noexcept;
    bool isValid() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    friend bool cudaAlignPatchDeviceWithWorkspace(
        PatchAlignmentWorkspace&, cufftComplex*, int, int, int, RFLOAT,
        std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
        std::ostream&, bool);
};

bool cudaAlignPatchDeviceWithWorkspace(
    PatchAlignmentWorkspace &workspace,
    cufftComplex *d_Fframes,
    const int n_frames,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile,
    bool is_global = false
);

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
    std::ostream &logfile,
    bool is_global = false
);

/**
 * In-VRAM CUDA implementation of patch alignment (Issue #50).
 * Operates directly on resident d_Fframes / d_Fpatches without host roundtrips.
 */
bool cudaAlignPatchDevice(
    cufftComplex *d_Fframes,
    const int n_frames,
    const int pnx, const int pny,
    const RFLOAT scaled_B,
    std::vector<RFLOAT> &xshifts,
    std::vector<RFLOAT> &yshifts,
    const int max_iter,
    const RFLOAT ccf_downsample,
    const int device_id,
    std::ostream &logfile,
    bool is_global = false
);
#endif

#endif // CUDA_ALIGNPATCH_H_
