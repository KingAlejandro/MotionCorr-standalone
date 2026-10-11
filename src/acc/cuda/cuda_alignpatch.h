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
    /** Window mode: the d_Fframes given to cudaAlignPatchDeviceWithWorkspace hold
     * only each frame's CCF window (cudaExtractPatchWindow) instead of the full
     * patch spectrum. Every value the alignment reads is the same, so shifts and
     * logs are bit-identical. Not part of the cache key: no buffer depends on it. */
    void setSpectrumWindowed(bool windowed);
    bool spectrumWindowed() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    friend bool cudaAlignPatchDeviceInArena(
        cufftComplex*, int, int, int, RFLOAT, std::vector<RFLOAT>&,
        std::vector<RFLOAT>&, int, RFLOAT, int, std::ostream&, void*, size_t, bool);
    friend bool cudaAlignPatchDeviceWithWorkspace(
        PatchAlignmentWorkspace&, cufftComplex*, int, int, int, RFLOAT,
        std::vector<RFLOAT>&, std::vector<RFLOAT>&, int, RFLOAT, int,
        std::ostream&, bool);
    friend bool cudaAlignPatchDevice(
        cufftComplex*, int, int, int, RFLOAT, std::vector<RFLOAT>&,
        std::vector<RFLOAT>&, int, RFLOAT, int, std::ostream&, bool);
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

/** CCF size the alignment of a pnx x pny patch uses. Its half-spectrum,
 * ccf_ny rows of ccf_nx/2+1, is the only part of the patch spectrum the
 * alignment ever reads: the patch "window". */
void patchSpectrumWindow(int pnx, int pny, RFLOAT scaled_B, RFLOAT ccf_downsample,
                         int &ccf_nx, int &ccf_ny);

/** Copy the window of n_frames full patch half-spectra (pny rows of pnx/2+1)
 * into d_window, multiplying each value by `scale` exactly as
 * scaleComplexKernel does. Row y of the window is spectrum row y for
 * y <= ccf_ny/2 and row y - ccf_ny + pny above it, the remap of the
 * reference and CCF kernels. Asynchronous; returns the launch status. */
cudaError_t cudaExtractPatchWindow(const cufftComplex *d_full, cufftComplex *d_window,
                                   int n_frames, int pnx, int pny, int ccf_nx, int ccf_ny,
                                   float scale);

/** What one patch of a batched call produced, kept so the caller can write that
 * patch's log lines in patch order and with the stream state of that moment
 * (the per-patch path leaves std::fixed/setprecision(2) set, which formats the
 * next patch's RMSD lines). See docs/batched_patch_alignment.md.
 */
struct PatchBatchLog {
    std::vector<RFLOAT> rmsd; // one entry per iteration run, in order
    bool converged = false;
    int chunk_patches = 0;    // patches aligned together with this one
    float chunk_gpu_ms = 0.0f;
    size_t buffer_bytes = 0, cufft_work_bytes = 0;
};

/** Device resources for aligning up to capacity() equally sized patches together.
 * Owns the patch window stacks (patchSlot: n_frames CCF windows per patch, see
 * cudaExtractPatchWindow), CCF scratch, one batch-n_frames C2R
 * plan (the per-patch configuration, executed once per patch: a single plan over
 * capacity*n_frames transforms is not bit-identical on cuFFT 11.3) and one host
 * staging area for all patches' shifts.
 */
class BatchedPatchAlignmentWorkspace {
public:
    explicit BatchedPatchAlignmentWorkspace(CudaFailureState *failure = nullptr);
    ~BatchedPatchAlignmentWorkspace();
    BatchedPatchAlignmentWorkspace(const BatchedPatchAlignmentWorkspace&) = delete;
    BatchedPatchAlignmentWorkspace& operator=(const BatchedPatchAlignmentWorkspace&) = delete;
    /** Allocate for `capacity` patches. Returns false with nothing retained when
     * an allocation or the plan is declined (not enough memory); the pending
     * error slot is cleared and nothing is recorded, because nothing failed that
     * the per-patch path would have run. A context-poisoning code is recorded
     * and thrown. Replaces any previous reservation. */
    bool reserve(int capacity, int n_frames, int pnx, int pny, RFLOAT scaled_B,
                 RFLOAT ccf_downsample, int device_id);
    cufftComplex *patchSlot(int index) const;
    int capacity() const;
    size_t bufferBytes() const;
    size_t cufftWorkBytes() const;
    bool release() noexcept;
    bool isValid() const;
    /** Device bytes reserve() allocates per patch, excluding the cuFFT work area. */
    static size_t bytesPerPatch(int n_frames, int pnx, int pny, RFLOAT scaled_B,
                                RFLOAT ccf_downsample);
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    friend void cudaAlignPatchBatchDevice(BatchedPatchAlignmentWorkspace&, int, int,
        int, int, RFLOAT, std::vector<RFLOAT>*, std::vector<RFLOAT>*, int, RFLOAT,
        int, PatchBatchLog*);
};

/** Align the patch stacks in slots [0, n_patches) together. Per iteration every
 * still-active patch runs the per-patch kernels and plan on its own slot, then one
 * D2H returns all shifts, the host applies the per-patch update unchanged, and one
 * H2D plus one shift kernel per active patch follows. A patch that converged or
 * reached max_iter is retired exactly where the per-patch loop would have stopped.
 * xshifts/yshifts/logs have n_patches entries; shifts accumulate as in
 * cudaAlignPatchDeviceWithWorkspace. Errors throw, as there.
 */
void cudaAlignPatchBatchDevice(
    BatchedPatchAlignmentWorkspace &workspace,
    int n_patches, int n_frames, int pnx, int pny, RFLOAT scaled_B,
    std::vector<RFLOAT> *xshifts, std::vector<RFLOAT> *yshifts,
    int max_iter, RFLOAT ccf_downsample, int device_id, PatchBatchLog *logs);

/** Write a batched patch's iteration, profile and completion lines with the same
 * statements, in the same order, as cudaAlignPatchDeviceWithWorkspace. */
void writePatchBatchLog(std::ostream &logfile, const PatchBatchLog &log);

/** Chunk size for batched patch alignment: as many patches as fit in free device
 * memory after `headroom = max(1 GiB, total/10)`, at most `cap` and n_patches.
 * Returns 0 when not even one patch fits. Pure host arithmetic. */
int choosePatchBatchChunk(int n_patches, size_t bytes_per_patch, size_t free_bytes,
                          size_t total_bytes, int cap);

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

/** cudaAlignPatchDevice with its scratch buffers and cuFFT work area carved from
 * `arena`: caller-owned device memory that nothing reads or writes during the
 * call (global alignment borrows the real-space movie, which the inverse FFT
 * overwrites afterwards). Same kernels, plan configuration, results and log,
 * plus one placement line. When the buffers do not fit, it allocates exactly as
 * cudaAlignPatchDevice does; a work area that does not fit is allocated alone. */
bool cudaAlignPatchDeviceInArena(
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
    void *arena, size_t arena_bytes,
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
