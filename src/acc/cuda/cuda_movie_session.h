#ifndef CUDA_MOVIE_SESSION_H_
#define CUDA_MOVIE_SESSION_H_

#include <vector>
#include <ostream>
#include "src/image.h"
#include "src/multidim_array.h"
#include "src/complex.h"
#include "src/micrograph_model.h"

#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>

/**
 * CudaMovieSession: Manages persistent GPU VRAM allocations across the entire movie lifecycle (Issue #50).
 * Eliminates redundant host<->device PCIe memory transfers by keeping real and Fourier frames
 * resident on the GPU throughout preprocessing, FFT, global alignment, patch alignment, and reconstruction.
 */
class CudaMovieSession {
public:
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
    bool applyGainDefectsAndSum(
        const std::vector<Image<float> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum,
        bool download_sum = true
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

    // In-VRAM Patch Extraction & Batched R2C FFT
    bool preparePatchInVram(
        int x_start, int y_start,
        int patch_w, int patch_h,
        int n_groups, const int *group_start, const int *group_size,
        cufftComplex *d_out_fpatches
    );

    // In-VRAM Dose-weighted reconstruction: applies DW and polynomial interpolation into Isum
    bool reconstructDoseWeighted(
        Image<float> &Isum,
        const std::vector<RFLOAT> &doses,
        const RFLOAT apix,
        const ThirdOrderPolynomialModel *model
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
    int nx;
    int ny;
    int n_frames;
    int device_id;
    int nfx;
    std::ostream &logfile;

    float *d_Iframes = nullptr;
    cufftComplex *d_Fframes = nullptr;
    float *d_Isum = nullptr;
    float *d_gain = nullptr;

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
};

#endif // _CUDA_ENABLED
#endif // CUDA_MOVIE_SESSION_H_
