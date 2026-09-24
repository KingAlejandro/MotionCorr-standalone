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

    // Allocate persistent buffers and create batched cuFFT plans
    bool initialize();

    // Release all persistent GPU allocations and plans
    void release();

    // Upload raw frames and gain reference (if present), execute fused gain multiplication
    // and unaligned sum accumulation on GPU, and copy unaligned sum back to host for hot pixel detection.
    bool applyGainDefectsAndSum(
        const std::vector<Image<float> > &raw_frames,
        const MultidimArray<float> *gain_ref,
        MultidimArray<float> &unaligned_sum
    );

    // Apply hot pixel defect replacements directly to resident d_Iframes
    bool updateDefectPixels(
        const std::vector<int> &bad_xs,
        const std::vector<int> &bad_ys,
        const std::vector<float> &replacements // bad_xs.size() * n_frames values
    );

    // In-VRAM batched forward FFT: d_Iframes (R2C) -> d_Fframes with 1/(nx*ny) scaling
    bool computeGlobalForwardFFT();

    // In-VRAM batched inverse FFT: d_Fframes (C2R) -> d_Iframes
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
    bool is_initialized = false;
};

#endif // _CUDA_ENABLED
#endif // CUDA_MOVIE_SESSION_H_
