# Architectural Design Specification: #47 - Eliminate CPU FFT Bottlenecks (Global Forward FFT, Global IFFT, and Patch Preparation)

- **Issue Reference**: #47 - CUDA: eliminate CPU FFT bottlenecks (global forward FFT, global IFFT, and patch preparation)
- **Track**: `track:cuda`, `track:optimization`
- **Priority**: P1
- **Architect**: MotionCorr Architecture Agent
- **Estimated Difficulty**: Medium-High (4/5)
- **Dependencies**: #16, #17, #44, PR #25, PR #37, PR #45
- **Status**: Approved
- **Target Release / Milestone**: v1.0.0

---

## 1. Executive Summary & Problem Statement

Detailed wall-clock instrumentation (`-DTIMING`) on an NVIDIA A100 GPU host (tutorial movie `20170629_00021_frameImage.tiff`, $3710 \times 3838 \times 24$, 5x5 patches, 8 host threads) revealed that while all CUDA kernels (global alignment, 25-patch local alignment, analytical dose weighting, and bilinear interpolation) execute in **$<0.75\text{ seconds}$ total**, the overall process runtime remains **$\approx 11.0\text{ seconds}$**.

The remaining time is overwhelmingly dominated by host CPU Fourier transforms and patch extraction:
1. **`global FFT`**: **3.495 s (31.8%)** — 24 CPU forward 2D FFTW transforms of full-resolution frames.
2. **`global iFFT`**: **3.384 s (30.8%)** — 24 CPU inverse 2D FFTW transforms solely to reconstruct real-space frames after global alignment.
3. **`prepare patch`**: **2.827 s (25.7%)** — CPU real-space patch cropping + 200 CPU forward 2D FFTW transforms.

**Together, CPU FFTs and patch preparation consume $9.71\text{ seconds}$ (88.3% of total execution time).**

This specification defines the GPU-accelerated pipeline to offload forward global transforms, inverse global transforms, and local patch extraction/FFTs to CUDA and cuFFT, reducing the 9.71 s bottleneck to $<0.15\text{ seconds}$ and achieving an end-to-end execution time of $<2.0\text{ seconds}$ (>7x speedup over the CPU baseline).

---

## 2. Architectural Objectives & Constraints

### 2.1 Functional Objectives
1. **CUDA Global Forward FFT (`cudaForwardFFT2D`)**:
   - Offload 24 full-resolution real-to-complex 2D transforms (`cufftExecR2C`) to GPU with proper FFTW-compatible Hermitian packing.
2. **CUDA Global Inverse FFT (`cudaInverseFFT2D`)**:
   - Offload 24 full-resolution complex-to-real 2D inverse transforms (`cufftExecC2R`) to GPU, eliminating the 3.38 s CPU bottleneck.
3. **CUDA Patch Extraction, Grouping & Batched FFT (`cudaPreparePatches`)**:
   - Extract $P_x \times P_y$ patches, accumulate frame groupings, and compute forward 2D R2C transforms directly in GPU device memory using batched `cufftExecR2C`.
4. **Preserve Bit-Exact Scientific Decisions**:
   - Preserve identical patch bounding boxes, even-dimension rounding, Jasenko subpixel peak finding, SVD polynomial fitting, and Grant & Grigorieff dose weighting.
5. **Pass test suite without regressions**:
   - Verify full synthetic regression suite (`tests/test_synthetic_regression.py`) passes with zero drift on CPU path.

### 2.2 Scientific & Non-Functional Constraints
- **Numerical Parity**: Must satisfy Gate 2 reference tolerances:
  - Trajectory shift error $\le 0.05$ px.
  - Image absolute RMSE $\le 0.02$.
  - Image maximum pixel error $\le 5.0$.
- **VRAM Budget**:
  - Keep peak VRAM strictly $\le 3.5\text{ GiB}$ across the entire movie pipeline.
- **Fail-Closed CPU Fallback**:
  - Pure CPU builds (`-DCUDA=OFF`) remain 100% operational with identical baseline outputs.
  - When `--gpu` is omitted or device allocation fails, the pipeline cleanly falls back to the host CPU path.

---

## 3. Mathematical & Algorithmic Formulation

### 3.1 2D Discrete Fourier Transforms & Normalization
For real image frame $I(y, x)$ of dimensions $N_y \times N_x$:
$$F(k_y, k_x) = \sum_{y=0}^{N_y-1} \sum_{x=0}^{N_x-1} I(y, x) e^{-i 2\pi (k_y y / N_y + k_x x / N_x)}$$
where $k_y \in [0, N_y-1]$ and $k_x \in [0, \lfloor N_x/2 \rfloor]$ due to Hermitian conjugate symmetry:
$$F(N_y - k_y, -k_x) = F^*(k_y, k_x)$$
In cuFFT, `cufftExecR2C` computes unnormalized forward DFTs matching FFTW. In inverse transforms `cufftExecC2R`, the output is scaled by $1 / (N_x N_y)$ to restore true real-space intensity amplitude.

### 3.2 Patch Extraction and Temporal Grouping in Device Memory
For patch index $p = (i_y, i_x)$ with bounding box $[x_{\text{start}}, x_{\text{end}}) \times [y_{\text{start}}, y_{\text{end}})$ of dimensions $h = y_{\text{end}} - y_{\text{start}}$ and $w = x_{\text{end}} - x_{\text{start}}$:
For each temporal group $g \in [0, n_{\text{groups}}-1]$ spanning frames $t \in [\text{group\_start}[g], \text{group\_start}[g] + \text{group\_size}[g] - 1]$:
$$I_{\text{patch}}(g, y, x) = \sum_{t=\text{group\_start}[g]}^{\text{group\_start}[g] + \text{group\_size}[g] - 1} I_{\text{frame}}(t, y_{\text{start}} + y, x_{\text{start}} + x)$$
The forward DFT $F_{\text{patch}}(g, k_y, k_x)$ is evaluated via 2D R2C FFT of dimensions $h \times w$.
Executing this directly in GPU device memory avoids extracting individual sub-images on CPU threads and eliminates $25 \times 8 = 200$ individual CPU FFTW calls.

---

## 4. Component Architecture & Data Flow

```mermaid
flowchart TD
    RawFrames["Iframes (Host RAM)"] -->|H2D Stream| GpuReal["d_Iframes (VRAM)"]
    GpuReal -->|cufftExecR2C (20 ms)| GpuFourier["d_Fframes (VRAM)"]
    GpuFourier --> GlobalAlign["cudaAlignPatch (Global CCF, 0.4 s)"]
    GlobalAlign -->|In-place Fourier Shifts| ShiftedFourier["d_Fframes Shifted"]
    ShiftedFourier -->|cufftExecC2R (20 ms)| ShiftedReal["d_Iframes Shifted"]
    ShiftedReal -->|GPU Patch Crop & Group| PatchImages["d_Ipatches (VRAM)"]
    PatchImages -->|Batched cufftExecR2C (10 ms)| PatchFourier["d_Fpatches (VRAM)"]
    PatchFourier --> PatchAlign["cudaAlignPatch (Local Patches, 0.3 s)"]
    PatchAlign --> PolyFit["SVD 3rd-Order Polynomial Fit (Host)"]
    PolyFit --> CUDA_DW["cudaDoseWeightAndInterpolate (Issue #44, 0.35 s)"]
    CUDA_DW --> FinalMicrograph["Final Corrected Micrograph"]
```

---

## 5. Interface Contracts & Header Definition

### `src/acc/cuda/cuda_fft_prep.h`:
```cpp
#pragma once
#include <vector>
#include <iostream>
#include "src/image.h"
#include "src/multidim_array.h"
#include "src/complex.h"

// Execute batched or streaming 2D real-to-complex forward FFT on GPU
bool cudaForwardFFT2D(
    const std::vector<Image<float> > &Iframes,
    std::vector<MultidimArray<fComplex> > &Fframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile
);

// Execute batched 2D complex-to-real inverse FFT on GPU
bool cudaInverseFFT2D(
    const std::vector<MultidimArray<fComplex> > &Fframes,
    std::vector<Image<float> > &Iframes,
    const int nx, const int ny,
    const int device_id,
    std::ostream &logfile
);

// Extract patches, sum temporal groups, and compute forward 2D FFTs on GPU
bool cudaPreparePatches(
    const std::vector<Image<float> > &Iframes,
    const int patch_x, const int patch_y,
    const int nx, const int ny,
    const std::vector<int> &group_start,
    const std::vector<int> &group_size,
    std::vector<std::vector<MultidimArray<fComplex> > > &all_Fpatches,
    const int device_id,
    std::ostream &logfile
);
```

---

## 6. Memory Staging & Allocation Strategy

- **Global Frames**: $24 \times 3710 \times 3838 \times 4\text{ bytes} \approx 1.37\text{ GiB}$.
- **Complex Fourier Frames**: $24 \times 3710 \times 1920 \times 8\text{ bytes} \approx 1.37\text{ GiB}$.
- To prevent peak VRAM exceeding 3.5 GiB, real-to-complex forward transforms can stream frame-by-frame or chunk-by-chunk if necessary, or use in-place cuFFT layouts.
- Patch workspaces: $8 \times 880 \times 912 \times 4\text{ bytes} \approx 25.6\text{ MiB}$ per patch.

---

## 7. Defensive Failure Modes & Fallback Behavior

| Condition / Trigger | Detection Mechanism | Fallback / Recovery Action | User Diagnostic Visibility |
| :--- | :--- | :--- | :--- |
| Invalid GPU device ID | Range check against `cudaGetDeviceCount` | Exit code 1 with clear error | `Invalid CUDA device ID` |
| Out of GPU Memory (OOM) | `cudaErrorMemoryAllocation` check | Fall back to CPU FFTW / OpenMP | Warning logged to `logfile` |
| cuFFT Plan Failure | `cufftResult != CUFFT_SUCCESS` | Fall back to CPU FFTW | Error logged to `logfile` |

---

## 8. Affected Files & Artifacts (Whitelist)

- `src/acc/cuda/cuda_fft_prep.h`: CUDA header defining accelerated FFT and patch prep contracts.
- `src/acc/cuda/cuda_fft_prep.cu`: CUDA implementation with cuFFT plans, crop/group kernels, and streaming transfers.
- `src/motioncorr_runner.cpp`: Runner integration dispatching CUDA FFTs and patch preparation with CPU fallback.
- `CMakeLists.txt`: Build target configuration for `cuda_fft_prep.cu`.
- `tools/run_cuda_fft_prep_validation.py`: Verification harness for Gate 2 parity and profiling.
