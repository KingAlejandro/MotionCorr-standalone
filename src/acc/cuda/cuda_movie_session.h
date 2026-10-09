#ifndef CUDA_MOVIE_SESSION_H_
#define CUDA_MOVIE_SESSION_H_

#include <vector>
#include <string>
#include <ostream>
#include <memory>
#include "src/image.h"
#include "src/multidim_array.h"
#include "src/acc/cuda/cuda_scratch_arena.h"
#include "src/complex.h"
#include "src/micrograph_model.h"

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include "src/acc/cuda/cuda_failure_state.h"
#include "src/acc/cuda/cuda_alignpatch.h"

/**
 * CudaMovieSession: Manages persistent GPU VRAM allocations across the entire movie lifecycle (Issue #50).
 * Eliminates redundant host<->device PCIe memory transfers by keeping real and Fourier frames
 * resident on the GPU throughout preprocessing, FFT, global alignment, patch alignment, and reconstruction.
 */
// Outcome of an attempted device ingest, as the caller must act on it.
//
// A bare bool conflated three different situations that need three different
// responses: "this build/encoding never uses the fast path" (use the fallback,
// nothing happened), "the fast path tried and failed but the device is fine"
// (use the fallback), and "the context is dead" (do not dispatch CUDA again).
// It also could not express a failure discovered AFTER the success value was
// chosen, which the ingest-scratch teardown can produce.
enum class MovieIngestStatus
{
	NotApplicable,        // no nvCOMP, no session, or an encoding this path declines
	Success,              // d_Iframes and d_Isum hold the whole movie
	RecoverableFailure,   // fall back to a host reader; the device is still usable
	FatalDeviceFailure    // the CUDA context is poisoned; no redispatch
};

// There is deliberately no InvalidInput state.
//
// It was declared, and the runner handled it, but no code path could produce
// it -- a documented contract that nothing implements is worse than a smaller
// one. The question is whether this path can ever know that a movie is bad
// rather than merely unsuitable for it, and it cannot:
//
//   Unsupported encodings (predictor, byte order, bits per sample, a zlib
//   wrapper this path does not accept) say nothing about the movie's validity.
//   The ordinary reader handles all of them. That is NotApplicable.
//
//   An Adler-32 mismatch looks like proof of corrupt input, and it is the one
//   case that tempted the state. But that checksum is computed over the output
//   of OUR OWN decompression, so a mismatch is equally consistent with a defect
//   in this path. Classifying it as bad input would skip the fallback, turn a
//   bug here into a reported data error, and lose the run that the host reader
//   would have completed correctly. It is RecoverableFailure: fall back, and
//   let the reader that verifies the same checksum for itself decide.

// Lookahead for the next movie's compressed TIFF strips (docs/movie_overlap.md).
//
// One background host thread runs the nvCOMP ingest's tag scan and reads every
// strip of movie N+1 into its own pinned buffer while movie N is still being
// processed. Movie N+1's ingest then uploads from that buffer instead of reading
// the file on the main thread. The thread makes no CUDA calls and never touches a
// CudaMovieSession; the buffer is allocated and freed on the main thread.
//
// A lookahead is used only when it describes exactly the movie being ingested
// (path, frame list, geometry, nvCOMP input alignment) and every strip was read.
// Anything else is discarded and the ingest runs its ordinary serial path, which
// owns every refusal and diagnostic. The zlib wrapper and Adler-32 checks run on
// the prefetched bytes exactly as on serially read ones.
//
// Opt-in: MOTIONCORR_MOVIE_PREFETCH=1. MOTIONCORR_MOVIE_PREFETCH_CPUS (e.g.
// "88-91") pins the thread. Without nvCOMP every call is a no-op.
class MovieStripPrefetch
{
public:
	static bool enabledByEnvironment();

	MovieStripPrefetch();
	~MovieStripPrefetch();   // joins the thread, then frees the buffer
	MovieStripPrefetch(const MovieStripPrefetch &) = delete;
	MovieStripPrefetch &operator=(const MovieStripPrefetch &) = delete;

	// Main thread. Waits for and discards any earlier lookahead, makes the pinned
	// buffer at least pinnedReserveBytes(stage_bytes_hint), then starts reading.
	// The caller guarantees that no copy from the buffer is still in flight.
	void start(const std::string &fn_mic, const std::vector<int> &frames, int nx, int ny,
	           size_t in_align, size_t stage_bytes_hint, std::ostream &log);
	// Main thread. Waits for the thread if one is running. Idempotent.
	void join();

	struct Impl;
	Impl *impl() { return d.get(); }

private:
	std::unique_ptr<Impl> d;
};

class CudaMovieSession {
public:
    CudaMovieSession(const CudaMovieSession&) = delete;
    CudaMovieSession& operator=(const CudaMovieSession&) = delete;
    CudaMovieSession(int nx, int ny, int n_frames, int device_id, std::ostream &log);
    ~CudaMovieSession();

    // Allocate persistent buffers and single-frame cuFFT plans
    bool initialize();

    // Release all persistent GPU allocations and plans
    void release();

    // Upload raw frames and gain reference (if present), execute fused gain multiplication
    // and unaligned sum accumulation on GPU, and copy unaligned sum back to host for hot pixel detection.
    // download_sum=false keeps the sum resident; the caller must then obtain the
    // statistics through reduceUnalignedSum/reduceUnalignedSumSqDev/collectAboveThreshold,
    // or copy it later via downloadUnalignedSum() when falling back.
    //
    // Identity of the host gain array, for worker-lifetime device retention.
    // The caller passes a value that changes whenever the gain contents could
    // have changed; 0 (the default) means "unknown" and disables retention, so
    // an un-updated caller keeps the old upload-every-movie behaviour.
    void setGainGeneration(unsigned long long generation) { gain_generation = generation; }

    bool applyGainDefectsAndSum(
        const std::vector<Image<float> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum,
        bool download_sum = true
    );

    // Issue #85 lane C: same contract as applyGainDefectsAndSum, but the host movie
    // is held in its native unsigned 16-bit form and the uint16 -> float expansion
    // happens on the device while the gain is applied. Halves the host payload and
    // the PCIe bytes for unsigned-16-bit TIFF input. Products are bit-identical:
    // uint16 -> float32 is exact, and the gain multiply, the store into d_Iframes
    // and the ascending per-pixel accumulation are the same operations in the same
    // order. Callers with any other input type must keep using the float overload.
    bool applyGainDefectsAndSumU16(
        const std::vector<Image<unsigned short> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum,
        bool download_sum = true
    );

    // Same contract for an 8-bit unsigned TIFF. (float)uint8 is exact, so the
    // products are bit-identical to the float path for the same file, and the
    // host payload and the PCIe bytes are a quarter of the float movie's rather
    // than a half. Signed 8-bit samples are a different conversion and must not
    // reach this overload; the runner admits UChar by name.
    bool applyGainDefectsAndSumU8(
        const std::vector<Image<unsigned char> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum,
        bool download_sum = true
    );

    // Attempt the device ingest and report what actually happened.
    //
    // This is the boundary the runner uses. It wraps the worker below and adds
    // the two things a bool cannot carry:
    //
    //  - classification. A decline on an unsupported encoding is not the same
    //    event as a cudaMalloc failure, and neither is the same as a poisoned
    //    context, but all three were "false".
    //
    //  - late failures. The worker's scratch scope synchronises and destroys
    //    the ingest stream in its destructor, which runs AFTER the return value
    //    has been chosen, and records any error into the session's failure
    //    state. A stream synchronise that failed there would have been reported
    //    as a successful ingest with a possibly incomplete d_Iframes. This
    //    compares the failure state across the call and refuses to call that
    //    success.
    //
    // Returns NotApplicable when the build has no nvCOMP, so the caller needs
    // no #if of its own.
    //
    // prefetch, when not null, may hold this movie's strips already read by a
    // MovieStripPrefetch; it is consumed (used or discarded) by this call.
    MovieIngestStatus ingestMovie(
        const std::string &fn_mic,
        const std::vector<int> &frames,
        const MultidimArray<float> *gain_ref,
        int n_threads,
        MovieStripPrefetch *prefetch = nullptr
    );

    // Set by a successful device ingest: the nvCOMP input alignment it used and
    // the bytes the whole movie occupies in the per-frame aligned staging layout.
    // Zero otherwise. What MovieStripPrefetch::start needs for the next movie.
    size_t ingestInputAlignment() const { return ingest_in_align; }
    size_t ingestMovieStageBytes() const { return ingest_movie_stage_bytes; }

#if defined(_NVCOMP_ENABLED)
    // Direct GPU TIFF ingestion via nvCOMP Batched Deflate: reads compressed strips
    // from disk, uploads only the compressed bytes over PCIe, decompresses on the
    // device, and fuses the row flip, gain application and unaligned sum straight
    // into the resident d_Iframes/d_Isum.
    //
    // Allocates no device memory for staging. Frames are processed in bounded
    // batches whose entire working set -- compressed inputs, uint16 outputs, chunk
    // descriptor arrays and the nvCOMP scratch -- is carved out of d_Fframes, which
    // initialize() has already allocated and which holds nothing until
    // computeGlobalForwardFFT() overwrites every element of it. The session's VRAM
    // high-water mark is therefore unchanged from the host-read path. (d_gain is
    // still allocated on demand, exactly as applyGainDefectsAndSum() does.)
    //
    // Claims the buffer through fourier_guard, so it is refused once the spectrum
    // is in there, and the forward transform is refused while these views are live.
    //
    // Returns false on any geometry, I/O, zlib-wrapper or per-chunk nvCOMP failure,
    // leaving the caller to fall back to the host reader. A partially written
    // d_Iframes/d_Isum is safe: applyGainDefectsAndSum() overwrites both in full.
    bool ingestCompressedTiffStrips(
        const std::string &fn_mic,
        const std::vector<int> &frames,
        const MultidimArray<float> *gain_ref,
        int n_threads,
        MovieStripPrefetch *prefetch
    );
#endif

    // Fetch individual d_Iframes pixels: one neighbour value per (defect, frame).
    // Replaces downloading the whole movie for hot-pixel replacement, which cost a
    // fresh movie-sized host allocation plus a full device-to-host copy on every
    // movie. sample_y[k] < 0 marks an entry the caller fills itself (the Gaussian
    // branch) and leaves out[k] at zero. Uses the pre-FFT scratch arena, so it adds
    // no device allocation.
    bool gatherFrameSamples(
        const std::vector<int> &sample_frame,
        const std::vector<int> &sample_y,
        const std::vector<int> &sample_x,
        std::vector<float> &out
    );

    // Copy the resident unaligned sum to the host. Used by the hot-pixel fallback
    // path, which re-runs the original host scan verbatim.
    bool downloadUnalignedSum(MultidimArray<float> &unaligned_sum);

    // Sum_n (double)d_Isum[n] and Sum_n |(double)d_Isum[n]|, fixed-shape deterministic
    // tree (no FP atomics). sum_abs is required because the forward error bound is
    // gamma_N * sum|x|, which exceeds gamma_N * |sum x| whenever the data changes sign.
    bool reduceUnalignedSum(double &sum1, double &sum_abs);

    // Sum_n ((double)d_Isum[n] - mean)^2. Addends are formed with __dsub_rn/__dmul_rn so
    // they are bit-identical to the host's `d = x - mean; d * d`.
    bool reduceUnalignedSumSqDev(double mean, double &sum2);

    // Emit every n with (double)d_Isum[n] > threshold, ascending, and count the pixels
    // lying within `guard` of the threshold. A non-zero count means the threshold
    // decision is not provably order-independent and the caller must fall back.
    // Returns false on CUDA error or hit-buffer overflow.
    bool collectAboveThreshold(
        double threshold,
        double guard,
        std::vector<int> &indices_ascending,
        size_t &guard_band_count
    );

    // Apply hot pixel defect replacements directly to resident d_Iframes
    bool updateDefectPixels(
        const std::vector<int> &bad_xs,
        const std::vector<int> &bad_ys,
        const std::vector<float> &replacements // bad_xs.size() * n_frames values
    );

    // End preprocessing after all hot-pixel decisions and sparse updates. Release
    // gain/sum scratch; movie frames and the caller's host recovery data survive.
    // Preprocessing methods cannot be used again until release()/initialize().
    bool releasePreprocessingBuffers();

    // In-VRAM framewise forward FFT: d_Iframes (R2C) -> d_Fframes with 1/(nx*ny) scaling
    bool computeGlobalForwardFFT();

    // In-VRAM framewise inverse FFT: d_Fframes (C2R) -> d_Iframes
    bool computeGlobalInverseFFT();

    // In-VRAM Patch Extraction & Batched R2C FFT. With window_nx/window_ny
    // nonzero (patchSpectrumWindow), d_out_fpatches receives only each group's
    // CCF window (n_groups * window_ny rows of window_nx/2+1, see
    // cudaExtractPatchWindow) with the same values the full spectrum holds there;
    // the full spectrum goes to session scratch.
    bool preparePatchInVram(
        int x_start, int y_start,
        int patch_w, int patch_h,
        int n_groups, const int *group_start, const int *group_size,
        cufftComplex *d_out_fpatches,
        int window_nx = 0, int window_ny = 0
    );

    PatchAlignmentWorkspace& getPatchAlignmentWorkspace() { return patch_alignment_workspace; }
    BatchedPatchAlignmentWorkspace& getBatchedPatchAlignmentWorkspace() { return batched_patch_alignment_workspace; }
    // Must succeed before any reconstruction or output publication. Releases both
    // the per-patch and the batched workspace and the cached patch preparation
    // buffers and plan, attempting each.
    bool releasePatchAlignmentWorkspace();

    // Global alignment scratch (docs/vram_live_ranges.md): d_Iframes is dead from
    // the end of the forward FFT until computeGlobalInverseFFT overwrites every
    // frame. Returns it (bytes = its size) and marks the real-space frames
    // invalid until that inverse transform succeeds. Null when there is none.
    void *borrowRealFramesForGlobalAlignment(size_t &bytes);

    struct PatchBox { int x_start, y_start, width, height; };
    struct PatchBatchOutcome {
        bool done = false;
        std::vector<RFLOAT> xshifts, yshifts;
        PatchBatchLog log;
    };
    /** Batched local alignment (docs/batched_patch_alignment.md). Aligns the
     * patches in chunks of up to `cap` (fewer if device memory is short) and marks
     * each aligned patch done; the caller runs every other patch through its
     * per-patch path and writes each done patch's log in patch order. Declines,
     * leaving all patches not done, when cap <= 0, patch sizes differ, or no chunk
     * fits. A recoverable preparation failure releases the workspace and leaves
     * that chunk and later ones not done; a fatal one throws with no retry. Any
     * alignment error throws, as in the per-patch path. Writes only its own
     * summary/fallback lines to the log. */
    void alignPatchesBatched(
        const std::vector<PatchBox> &boxes,
        int n_groups, const int *group_start, const int *group_size,
        RFLOAT scaled_B, int max_iter, RFLOAT ccf_downsample, int cap,
        std::vector<PatchBatchOutcome> &outcomes);

    // In-VRAM Dose-weighted reconstruction: applies DW and polynomial interpolation into Isum
    // consume_real_frames: nothing reads d_Iframes after this call (the caller
    // needs no pre-dose-weighting sum), so the reconstruction's own scratch is
    // carved from it instead of allocated, and the real-space frames become
    // permanently invalid for this movie.
    bool reconstructDoseWeighted(
        Image<float> &Isum,
        const std::vector<RFLOAT> &doses,
        const RFLOAT apix,
        const ThirdOrderPolynomialModel *model,
        bool consume_real_frames = false
    );

    // In-VRAM Unweighted real-space reconstruction: applies polynomial interpolation into Isum
    bool reconstructUnweighted(
        Image<float> &Isum,
        Image<float> *Isum_even,
        Image<float> *Isum_odd,
        const ThirdOrderPolynomialModel *model
    );

    // Download Fourier frames to host (used e.g. when grouping_for_ps > 0 or CPU fallback)
    bool downloadFourierFrames(std::vector<MultidimArray<fComplex> > &Fframes);

    // Download real frames to host (used e.g. for fallback)
    bool downloadRealFrames(std::vector<Image<float> > &Iframes);

    // Issue #69: the failure state this session observed, preserved across the helper
    // boundary. The internal error handlers consume the CUDA error when they return
    // false, so a later cudaGetLastError() reports cudaSuccess and proves nothing about
    // context health. A caller deciding whether a retry is safe must use this, not a
    // fresh last-error read. It carries both the first failure (diagnostic provenance)
    // and a monotonically latched poisoning code that no later or earlier record can
    // displace -- see CudaFailureState.
    const CudaFailureState& getFailureState() const { return failure_state; }
    // Non-const access exists so a control can drive the session through a
    // recorded failure without a poisoned physical device.
    CudaFailureState& getFailureState() { return failure_state; }

    // Accessors
    float* getDeviceRealFrames() { return d_Iframes; }
    cufftComplex* getDeviceFourierFrames() { return d_Fframes; }
    float* getDeviceUnalignedSum() { return d_Isum; }
    int getNx() const { return nx; }
    int getNy() const { return ny; }
    int getNfx() const { return nfx; }
    int getNFrames() const { return n_frames; }
    int getDeviceId() const { return device_id; }
    bool isInitialized() const { return is_initialized; }

private:
    // The shared body of the two native-sample overloads above. Private: callers
    // name the sample type through the overloads, which is what keeps SChar and
    // SShort from instantiating it by accident.
    template <typename T>
    bool applyGainDefectsAndSumNative(
        const std::vector<Image<T> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum,
        bool download_sum
    );

    cudaError_t releaseBuffer(void *&slot) noexcept;
    template<class T> cudaError_t releaseBuffer(T *&slot) noexcept;
    cufftResult releasePlan(cufftHandle &slot, bool &owned) noexcept;
    void recordFailure(cudaError_t err, const char *stage, int line);
    void recordCufftFailure(cufftResult res, const char *stage, int line);

    // Sticky for the life of the session. Not reset by release(): a movie that failed
    // stays failed for reporting purposes, and a poisoned context never un-poisons.
    CudaFailureState failure_state;
    PatchAlignmentWorkspace patch_alignment_workspace;
    BatchedPatchAlignmentWorkspace batched_patch_alignment_workspace;

    int nx;
    int ny;
    int n_frames;
    int device_id;
    int nfx;
    std::ostream &logfile;

    float *d_Iframes = nullptr;
    cufftComplex *d_Fframes = nullptr;
    float *d_Isum = nullptr;
    // Borrowed from the worker-lifetime gain pool when the identity key matches,
    // owned by this session otherwise. release() and
    // releasePreprocessingBuffers() may only free it in the owned case.
    float *d_gain = nullptr;
    bool d_gain_borrowed = false;
    unsigned long long gain_generation = 0;

    // Points d_gain at a device copy of gain_ref, reusing the worker-lifetime
    // pooled copy when (generation, bytes, nx, ny, device) matches. A failed
    // owning-device selection retains invalidated ownership for checked retry;
    // no stale cache hit or replacement is allowed. A null gain_ref releases
    // any session-owned copy and leaves d_gain null.
    bool ensureDeviceGain(const MultidimArray<float> *gain_ref, size_t sz_real);

    cufftHandle plan_r2c = 0;
    cufftHandle plan_c2r = 0;
    bool has_plan_r2c = false;
    bool has_plan_c2r = false;
    size_t fft_r2c_work_bytes = 0;
    size_t fft_c2r_work_bytes = 0;
    size_t fft_work_bytes = 0;
    void *d_fft_work = nullptr;
    cufftComplex *d_inverse_tile = nullptr;
    bool is_initialized = false;

    // What d_Fframes currently holds. The ingest path borrows that allocation as
    // scratch instead of allocating its own staging, so the transition out of
    // IngestScratch is what makes the forward transform safe to run.
    mc_cuda::FourierStorageGuard fourier_guard;
    cudaStream_t ingest_stream = 0;
    // Pipelined nvCOMP ingest: uploads run on their own stream so chunk k+1's
    // copy overlaps chunk k's decode; slot reuse is ordered by these events
    // (h2d_done[2], comp_free[2], status_ready[2]). Destroyed by endIngestScratch.
    cudaStream_t ingest_copy_stream = 0;
    size_t ingest_in_align = 0;
    size_t ingest_movie_stage_bytes = 0;
    static const int kIngestEvents = 6;
    cudaEvent_t ingest_events[kIngestEvents] = {};
    // Points the ingest at the worker-lifetime pinned staging pool, growing it if
    // this movie needs more. The pool deliberately outlives the session, which is
    // constructed and destroyed once per movie.
#if defined(_NVCOMP_ENABLED)
    // Genuinely nvCOMP-only: this is the pinned staging pool for compressed
    // strips and has no caller outside ingestCompressedTiffStrips. Declared
    // under the same guard as its definition, so the two cannot drift apart
    // the way endIngestScratch's did.
    bool ensurePinnedStage(size_t bytes);
#endif
    // Synchronises and tears down the ingest stream, then declares every scratch
    // view dead. Idempotent; called from a scope guard so it also runs on the
    // HANDLE_ERROR early-return paths.
    void endIngestScratch();

    // Cached patch resources to avoid allocations and plan recreation in patch loop
    cufftHandle plan_patch_r2c = 0;
    bool has_plan_patch_r2c = false;
    int cached_patch_w = 0;
    int cached_patch_h = 0;
    int cached_patch_ngroups = 0;
    float *d_Ipatches = nullptr;
    int *d_group_start = nullptr;
    int *d_group_size = nullptr;
    size_t sz_cached_Ipatches = 0;
    int cached_ngroups_alloc = 0;
    // Host copy of the group tables last uploaded, so the 25 patches of a movie
    // upload them once instead of twice per patch. Cleared with the buffers.
    std::vector<int> uploaded_group_start, uploaded_group_size;
    // Full patch spectra for windowed preparation when d_inverse_tile is too small.
    cufftComplex *d_patch_spectrum = nullptr;
    size_t sz_cached_patch_spectrum = 0;

    // Non-null while d_Iframes holds no valid real-space movie because it was
    // lent out as scratch; every reader of d_Iframes refuses while it is set.
    const char *real_frames_invalid_reason = nullptr;
    bool refuseInvalidRealFrames(const char *operation);
};

#endif // _CUDA_ENABLED
#endif // CUDA_MOVIE_SESSION_H_
