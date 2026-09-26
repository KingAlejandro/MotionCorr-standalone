# Architectural Design Specification: #50 - End-to-End GPU Residency and Fused Preprocessing

- **Issue Reference**: #50 - CUDA: End-to-end GPU residency and fused preprocessing to eliminate PCIe transfer overhead
- **Track**: `track:cuda`, `track:optimization`
- **Priority**: P1
- **Architect**: MotionCorr Architecture Agent
- **Estimated Difficulty**: High (4/5)
- **Dependencies**: #17, #44, #47, PR #49
- **Status**: Approved
- **Target Release / Milestone**: v1.0.0

---

## 1. Executive Summary & Problem Statement

In Issue #47, GPU acceleration of global forward FFT, global inverse FFT, and local patch preparation reduced the full movie runtime on an NVIDIA A100 from **28.53 s (CPU)** down to **6.57 s (CUDA)**. However, fine-grained profiling (`-DTIMING`) revealed that **~75% of the remaining 6.57 s is consumed by non-compute overheads**:

1. **Redundant Host-Device PCIe Transfers (~3.8 s)**:
   Because each algorithmic stage was originally isolated for verification, 24 full-resolution frames ($3710 \times 3838 \times 4\text{ bytes} \approx 1.37\text{ GB}$) ping-pong back and forth across PCIe 8 to 10 times in unpinned pageable memory:
   - `cudaForwardFFT2D`: H2D `Iframes` (1.37 GB) $\rightarrow$ D2H `Fframes` (1.37 GB)
   - `cudaAlignPatch` (Global): H2D `Fframes` (1.37 GB) $\rightarrow$ D2H rotated `Fframes` (1.37 GB)
   - `cudaInverseFFT2D`: H2D `Fframes` (1.37 GB) $\rightarrow$ D2H `Iframes` (1.37 GB)
   - `cudaPreparePatch` & `cudaAlignPatch` (Local): D2H `Fpatches` $\rightarrow$ H2D `Fpatches`
   - `cudaDoseWeightAndInterpolate`: H2D `Fframes` (1.37 GB)

2. **CPU Preprocessing Bottleneck (~0.98 s)**:
   - `apply gain and initial sum` (**0.75 s**) and `detect hot pixels` / `fix defects` (**0.24 s**) run on the CPU with OpenMP threads across 340 million pixels per movie.

In contrast, the actual CUDA kernel compute time across the entire pipeline is **under 1.0 second**.

This specification defines **End-to-End GPU Residency** and a **GPU Fused Preprocessing Kernel**:
- Keep `d_Iframes` and `d_Fframes` resident in GPU VRAM across the entire movie pipeline.
- Fuse gain reference multiplication, defect replacement, and initial summation into a single GPU kernel executing in $< 15\text{ ms}$.
- Eliminate all intermediate full-frame host-device transfers, transferring only the final 2D reconstructed image (57 MB) and motion trajectory shifts back to host memory.
- Target: reduce total full-movie wall-clock time from **6.57 s** to **~1.0 – 1.3 s** on NVIDIA A100.

---

## 2. Architectural Objectives & Constraints

### 2.1 Functional Objectives
1. **GPU-Resident State (`CudaMovieSession`)**:
   - Allocate device memory for `d_Iframes` (real) and `d_Fframes` (Fourier) once per movie.
   - Maintain data in GPU memory throughout Global FFT, Global Alignment, Global IFFT, Patch Slicing, Patch Alignment, and Dose-Weighted Reconstruction.
2. **Fused GPU Preprocessing (`cudaApplyGainDefectsAndSum`)**:
   - Upload raw frame pixels to GPU once.
   - Apply gain multiplication: $I_{gain}(x, y) = I_{raw}(x, y) \cdot G(x, y)$.
   - Fix defective/hot pixels in-place on GPU.
   - Accumulate into unaligned sum image directly in VRAM.
3. **Zero Host Transfer on Intermediate Stages**:
   - Global FFT computes `d_Fframes` directly from `d_Iframes` in VRAM.
   - Global Alignment operates directly on `d_Fframes` in VRAM.
   - Global IFFT reconstructs `d_Iframes` directly in VRAM.
   - Patch Slicing crops `d_Iframes` directly into `d_Ipatches` and transforms to `d_Fpatches` in VRAM.
   - Patch Alignment operates directly on `d_Fpatches` in VRAM.
   - Dose Weighting and Real-Space Interpolation accumulate into `d_Isum` in VRAM.
   - Only a single 57 MB download of `d_Isum` is performed at the very end of the movie.
4. **Preserve Exact CPU Fallback**:
   - Zero regression when `--gpu` is omitted or device memory allocation fails.
   - Clean RAII deallocation between movies.

### 2.2 Scientific & Non-Functional Constraints
- **Numerical Parity**: Must satisfy Gate 2 reference tolerances:
  - Coordinate RMS shift error $\le 0.02\text{ px}$.
  - Max shift error $\le 0.05\text{ px}$.
  - Image absolute RMSE $\le 0.02$.
  - Image relative RMSE $\le 0.001$.
  - Image maximum pixel error $\le 5.0$.
  - STAR metadata field identity for local and global motion trajectories.
- **VRAM Memory Ceiling**:
  - Peak VRAM footprint $\le 3.5\text{ GiB}$ for a 24-frame 4K movie, fitting comfortably on 8 GB consumer GPUs and enterprise GPUs alike.
- **Portability**:
  - Must compile cleanly with C++17 on Linux (GCC/Clang) and macOS (AppleClang) without CUDA dependencies when `CUDA=OFF`.

---

## 3. Component Architecture & Data Flow

```mermaid
flowchart TD
    RawDisk["Raw Movie Frames (Disk)"] --> HostRAM["Host RAM (Raw Frames)"]
    HostRAM -->|Single Upload| VRAM_Raw["d_Iframes (Raw GPU Memory)"]
    
    subgraph GPU_Resident_Lifecycle ["GPU-Resident Pipeline (Zero Host Ping-Pong)"]
        VRAM_Raw --> FusedPrep["cudaApplyGainDefectsAndSum (<15 ms)"]
        FusedPrep --> d_Iframes["d_Iframes (Gain Corrected)"]
        FusedPrep --> d_Isum_init["d_Isum_unaligned"]
        
        d_Iframes -->|Batched cuFFT R2C| d_Fframes["d_Fframes (Fourier Frames)"]
        d_Fframes --> GAlign["cudaAlignPatch (Global, In-VRAM)"]
        GAlign -->|In-place Fourier Rotation| d_Fframes_aligned["d_Fframes (Globally Shifted)"]
        
        d_Fframes_aligned -->|Batched cuFFT C2R| d_Iframes_aligned["d_Iframes (Globally Real)"]
        d_Iframes_aligned --> PCrop["cropAndGroupPatchKernel (In-VRAM)"]
        PCrop --> d_Fpatches["d_Fpatches (In-VRAM)"]
        d_Fpatches --> PAlign["cudaAlignPatch (Local Patches, In-VRAM)"]
        
        PAlign -->|Trajectory Shifts (1.6 KB)| HostPoly["Host Polynomial Fit (0.006 s)"]
        HostPoly -->|Coefficients| DWInterp["cudaDoseWeightAndInterpolate (In-VRAM)"]
        d_Fframes_aligned --> DWInterp
        DWInterp --> d_Isum_final["d_Isum_final (Reconstructed Image)"]
    end
    
    d_Isum_final -->|Single Download (57 MB, 5 ms)| HostOut["Final Aligned Micrograph (MRC)"]
```

---

## 4. Detailed Interface Contracts & Data Structures

### 4.1 `CudaMovieSession` (`src/acc/cuda/cuda_movie_session.h`)

```cpp
#pragma once
#ifdef _CUDA_ENABLED
#include <cuda_runtime.h>
#include <cufft.h>
#include <vector>
#include <iostream>

class CudaMovieSession {
public:
    CudaMovieSession(int nx, int ny, int n_frames, int device_id, std::ostream &log);
    ~CudaMovieSession();

    bool initialize();
    void release();

    // In-VRAM Preprocessing
    bool applyGainDefectsAndSum(
        const float *h_raw_frames,
        const float *h_gain,
        float *h_unaligned_sum
    );

    // In-VRAM Global Forward FFT
    bool computeGlobalForwardFFT();

    // In-VRAM Global Inverse FFT
    bool computeGlobalInverseFFT();

    // In-VRAM Patch Extraction & FFT
    bool preparePatchInVram(
        int x_start, int x_end, int y_start, int y_end,
        int n_groups, const int *group_start, const int *group_size,
        cufftComplex *d_out_fpatches
    );

    // Pointers to persistent VRAM buffers
    float* getDeviceRealFrames() { return d_Iframes; }
    cufftComplex* getDeviceFourierFrames() { return d_Fframes; }
    float* getDeviceUnalignedSum() { return d_Isum; }

private:
    int nx, ny, n_frames, device_id;
    int nfx;
    std::ostream &logfile;

    float *d_Iframes = nullptr;
    cufftComplex *d_Fframes = nullptr;
    float *d_Isum = nullptr;
    float *d_gain = nullptr;
    
    cufftHandle plan_r2c = 0;
    cufftHandle plan_c2r = 0;
    bool is_initialized = false;
};
#endif
```

---

## 5. File Whitelist & Affected Components

| File | Purpose | Scope |
|:---|:---|:---|
| `src/acc/cuda/cuda_movie_session.h` | Persistent GPU session interface | New Header |
| `src/acc/cuda/cuda_movie_session.cu` | GPU residency, fused preprocessing, and in-VRAM orchestration | New Source |
| `src/acc/cuda/cuda_alignpatch.h` | Overload to accept device pointers directly | Modified |
| `src/acc/cuda/cuda_alignpatch.cu` | Device pointer implementation for patch alignment | Modified |
| `src/acc/cuda/cuda_fft_prep.h` | Streamlined in-VRAM transforms | Modified |
| `src/acc/cuda/cuda_fft_prep.cu` | In-VRAM transform kernels | Modified |
| `src/acc/cuda/cuda_realspace_dw.h` | Overload to accept device pointers for resident reconstruction | Modified |
| `src/acc/cuda/cuda_realspace_dw.cu` | Device pointer implementation for real space interpolation and dose weighting | Modified |
| `src/motioncorr_runner.h` | Add device helper declarations and session integration | Modified |
| `src/motioncorr_runner.cpp` | Connect `CudaMovieSession` to main pipeline | Modified |
| `CMakeLists.txt` | Add `cuda_movie_session.cu` to build target | Modified |

---

## 6. Verification and Acceptance Criteria

- [x] Implement persistent `CudaMovieSession` lifecycle managing resident VRAM buffers (`d_Iframes`, `d_Fframes`, `d_Isum`, `d_gain`).
- [x] Implement fused preprocessing kernel for gain application and initial unaligned summation on GPU (`applyGainDefectsAndSum`), with deterministic RNG defect replacement handling and GPU update (`updateDefectPixels`).
- [x] Eliminate intermediate host-device transfers across global FFT, global alignment, global IFFT, and patch alignment.
- [x] Implement resident in-VRAM dose weighting and real-space interpolation directly writing to device output buffer.
- [ ] Pass Gate 2 numerical equivalence: Coordinate RMS shift error $\le 0.02\text{ px}$, Max shift error $\le 0.05\text{ px}$, Corrected-image absolute RMSE $\le 0.02$, Corrected-image relative RMSE $\le 0.001$, and identical STAR metadata. The relative-image-RMSE gate remains failed.
- [ ] Maintain full numerical parity and safe, deterministic fallback to CPU when CUDA is disabled, out of memory, or upon step failure. Some resident-stage failures can still abort instead of falling back; this remains unverified as an end-to-end acceptance criterion.
