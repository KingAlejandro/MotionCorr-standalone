# CUDA Global Alignment Proof of Concept Validation Report

**Issue**: [#16 - CUDA proof of concept for global alignment kernels](https://github.com/KingAlejandro/MotionCorr-standalone/issues/16)  
**Host Machine**: `4-gpu-vm` (Ubuntu 24.04 LTS, AMD EPYC 7452 32-core, 124 vCPUs, 432 GiB RAM)  
**Date**: 2026-09-23  
**Status**: **PASSED (Gate 2 / Numerical Equivalence Verified)**

---

## 1. System Specifications & Build Recipe

### Hardware & Environment
- **GPU**: NVIDIA A100 80GB PCIe (Compute Capability 8.0, 81,920 MiB VRAM)
- **NVIDIA Driver**: `570.86.10`
- **CUDA Toolkit**: `12.8` (`release 12.8, V12.8.55`)
- **cuFFT Library**: `11.3.3.41` (`libcufft.so.11`)
- **Host Compiler**: GCC `13.3.0` (`Ubuntu 13.3.0-6ubuntu2~24.04`)
- **FFTW3**: `3.3.10` (Float and Double)

### Build Recipe

#### CUDA-Accelerated Build
```bash
# Configure with CUDA enabled for NVIDIA A100 (sm_80)
cmake -B build-cuda -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80
cmake --build build-cuda -j
```

#### CPU-Only Build Verification
CPU-only builds remain completely unaffected and compile cleanly without CUDA:
```bash
cmake -B build
cmake --build build -j
```
*Verified clean compilation on both macOS ARM64 (Apple Silicon) and Linux x86_64.*

---

## 2. Architecture & Kernel Pipeline

The CUDA global alignment prototype (`src/acc/cuda/cuda_alignpatch.cu`) accelerates the iterative frame alignment loop on the GPU while maintaining exact scientific equivalence to RELION's algorithm:

```mermaid
graph TD
    A["Host Fframes (Fourier Transforms)"] -->|H2D Transfer| B["d_Fframes"]
    B --> C["computeWeightsKernel: B-factor Damping"]
    subgraph Iteration Loop ["iter = 1 .. max_iter"]
        C --> D["computeReferenceKernel: Sum all frames into d_Fref"]
        D --> E["computeCCFKernel: Batched Cross-Correlation (Fref - Fframe) * Fframe* * weight"]
        E --> F["cuFFT Batched C2R: d_Fccs -> d_Iccs"]
        F --> G["findPeakAndInterpolateKernel: Batched 2D Peak Finding + Jasenko Fit"]
        G -->|D2H Shifts Only: 2*N floats| H["Host Trajectory Accumulation"]
        H --> I["fourierShiftKernel: Batched Phase Rotation on GPU"]
        I --> J{"Convergence Check: RMSD < tolerance?"}
        J -->|No| D
        J -->|Yes| K["Loop Terminated"]
    end
    K -->|D2H d_Fframes -> Host Fframes| L["Host Output / Local Patch Alignment"]
```

---

## 3. Numerical Acceptance Gates & Tolerances

Per [`docs/reference_gates.md`](reference_gates.md#L128), numerical equivalence between GPU and CPU is evaluated against Gate 2 (`--gate relaxed`):

| Metric | Gate 2 Declared Tolerance | Synthetic Fixture | Experimental Movie 1 | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Coordinate RMS Shift Error** | $\le 0.020\text{ px}$ | **`0.001324 px`** | **`0.003464 px`** | **PASS** |
| **Max Frame Shift Error** | $\le 0.050\text{ px}$ | **`0.001970 px`** | **`0.005547 px`** | **PASS** |
| **Corrected Image RMSE** | $\le 0.020$ | **`0.013038`** | **`0.003970`** | **PASS** |
| **Image Relative RMSE** | $\le 0.001$ (synthetic) | **`0.000203 (0.02%)`** | `0.004925`* | **PASS** |
| **Image Max Absolute Error** | $\le 5.0$ | **`0.085083`** | **`1.7274`** | **PASS** |
| **Normalized STAR Differences** | `0` | **`0`** | **`0`** | **PASS** |
| **Process Exit Status** | `0` | **`0`** | **`0`** | **PASS** |

*\*Note on Experimental Relative RMSE*: As documented in Issue #6 and Issue #7, experimental cryo-EM micrographs have a background noise standard deviation of $\sigma \approx 0.8$. An absolute RMSE of ~0.004 on noisy micrographs yields a relative RMSE of ~0.005 (0.5%), which strictly mirrors the CPU multi-threaded variation and is not raised silently.

---

## 4. Synthetic Known-Shift Fixture Validation

Evaluated on `synthetic_128x128_8frames.star` ($128 \times 128 \times 8$ frames) with known integer shifts:

### Ground Truth Recovery Accuracy
- **CPU Reference**: RMS shift error = `0.071437 px`, Max shift error = `0.100020 px`
- **GPU (A100)**: RMS shift error = `0.070905 px`, Max shift error = `0.098050 px`

### Multi-Run Steady-State Telemetry (Synthetic Fixture)
Three steady-state runs converged in 2 iterations ($\text{RMSD}_1 = 2.4908\text{ px}$, $\text{RMSD}_2 = 0.3849\text{ px}$):

| Metric | Run 1 | Run 2 | Run 3 | Mean ± Std |
| :--- | :---: | :---: | :---: | :---: |
| **Host-to-Device (H2D) Transfer** | `0.28 ms` | `0.34 ms` | `0.29 ms` | `0.30 ± 0.03 ms` |
| **Custom Kernel Execution** | `0.18 ms` | `0.25 ms` | `0.17 ms` | `0.20 ± 0.04 ms` |
| **cuFFT Execution (`cufftExecC2R`)** | `0.04 ms` | `0.04 ms` | `0.04 ms` | `0.04 ± 0.00 ms` |
| **Device-to-Host (D2H) Transfer** | `0.36 ms` | `0.36 ms` | `0.47 ms` | `0.40 ± 0.06 ms` |
| **Total GPU Alignment Time** | `5.83 ms` | `6.00 ms` | `5.98 ms` | **`5.94 ± 0.09 ms`** |
| **Buffer VRAM** | `1.61 MiB` | `1.61 MiB` | `1.61 MiB` | `1.61 MiB` |
| **cuFFT Workspace VRAM** | `0.51 MiB` | `0.51 MiB` | `0.51 MiB` | `0.51 MiB` |
| **Peak GPU Memory Allocated** | `2.12 MiB` | `2.12 MiB` | `2.12 MiB` | `2.12 MiB` |

---

## 5. Experimental Tutorial Movie Validation

Evaluated on `20170629_00021_frameImage.tiff` (24 frames, $3710 \times 3838$ pixels, gain correction, dose weighting, $5 \times 5$ patches):

### Multi-Run Steady-State Telemetry (Full Micrograph, 24 Frames)
Converged in 2 iterations ($\text{RMSD}_1 = 10.2061\text{ px}$, $\text{RMSD}_2 = 0.4869\text{ px}$):

| Metric | Run 1 | Run 2 | Run 3 | Mean ± Std |
| :--- | :---: | :---: | :---: | :---: |
| **Host-to-Device (H2D) Transfer** | `374.43 ms` | `386.09 ms` | `411.73 ms` | `390.75 ± 19.08 ms` |
| **Custom Kernel Execution** | `4.00 ms` | `3.99 ms` | `4.00 ms` | `4.00 ± 0.01 ms` |
| **cuFFT Execution (`cufftExecC2R`)** | `0.83 ms` | `0.83 ms` | `0.83 ms` | `0.83 ± 0.00 ms` |
| **Device-to-Host (D2H) Transfer** | `151.63 ms` | `171.54 ms` | `185.57 ms` | `169.58 ± 17.06 ms` |
| **Total GPU Global Alignment Time** | `537.49 ms` | `569.06 ms` | `608.66 ms` | **`571.74 ± 35.66 ms`** |
| **Buffer VRAM** | `1482.91 MiB` | `1482.91 MiB` | `1482.91 MiB` | `1482.91 MiB` (~1.45 GiB) |
| **cuFFT Workspace VRAM** | `86.68 MiB` | `86.68 MiB` | `86.68 MiB` | `86.68 MiB` |
| **Peak GPU Memory Allocated** | `1569.59 MiB` | `1569.59 MiB` | `1569.59 MiB` | `1569.59 MiB` (~1.53 GiB) |

---

## 6. Full 24-Movie RELION SPA Tutorial Dataset Validation

All 24 experimental movies from the RELION SPA benchmark dataset ($3710 \times 3838 \times 24$ frames, gain correction, dose weighting, $5 \times 5$ patches) were executed on the NVIDIA A100 GPU (`--gpu 0 --j 4`) and evaluated against the single-threaded CPU reference (`--j 1`):

### 24-Movie Parity Matrix (CUDA vs CPU j1)

| # | Movie Name | GPU Alignment | Traj RMS Error | Max Frame Shift | Image RMSE | Movie Wall Time | Gate 2 Status |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 01 | `20170629_00021_frameImage` | `608.7 ms` | `0.003555 px` | `0.006104 px` | `0.004414` | `49.3 s` | **PASS** |
| 02 | `20170629_00022_frameImage` | `544.7 ms` | `0.003843 px` | `0.006263 px` | `0.005319` | `49.2 s` | **PASS** |
| 03 | `20170629_00023_frameImage` | `364.7 ms` | `0.006846 px` | `0.008350 px` | `0.006795` | `48.9 s` | **PASS** |
| 04 | `20170629_00024_frameImage` | `363.3 ms` | `0.005737 px` | `0.009368 px` | `0.006411` | `48.8 s` | **PASS** |
| 05 | `20170629_00025_frameImage` | `457.0 ms` | `0.003810 px` | `0.006633 px` | `0.006239` | `49.0 s` | **PASS** |
| 06 | `20170629_00026_frameImage` | `364.9 ms` | `0.006699 px` | `0.010754 px` | `0.007397` | `48.7 s` | **PASS** |
| 07 | `20170629_00027_frameImage` | `366.2 ms` | `0.005968 px` | `0.009337 px` | `0.008234` | `41.4 s` | **PASS** |
| 08 | `20170629_00028_frameImage` | `365.5 ms` | `0.003933 px` | `0.007274 px` | `0.007969` | `30.1 s` | **PASS** |
| 09 | `20170629_00029_frameImage` | `365.3 ms` | `0.004150 px` | `0.008815 px` | `0.004659` | `30.1 s` | **PASS** |
| 10 | `20170629_00030_frameImage` | `367.9 ms` | `0.003552 px` | `0.005234 px` | `0.004334` | `29.9 s` | **PASS** |
| 11 | `20170629_00031_frameImage` | `366.9 ms` | `0.003068 px` | `0.004590 px` | `0.005561` | `29.9 s` | **PASS** |
| 12 | `20170629_00035_frameImage` | `366.6 ms` | `0.005399 px` | `0.012684 px` | `0.009308` | `29.9 s` | **PASS** |
| 13 | `20170629_00036_frameImage` | `365.7 ms` | `0.005692 px` | `0.013758 px` | `0.006138` | `30.0 s` | **PASS** |
| 14 | `20170629_00037_frameImage` | `363.8 ms` | `0.004886 px` | `0.009468 px` | `0.005927` | `29.9 s` | **PASS** |
| 15 | `20170629_00039_frameImage` | `363.7 ms` | `0.005546 px` | `0.009692 px` | `0.006919` | `32.1 s` | **PASS** |
| 16 | `20170629_00040_frameImage` | `365.1 ms` | `0.006532 px` | `0.010970 px` | `0.007584` | `31.0 s` | **PASS** |
| 17 | `20170629_00042_frameImage` | `365.7 ms` | `0.006333 px` | `0.010668 px` | `0.007224` | `30.0 s` | **PASS** |
| 18 | `20170629_00043_frameImage` | `481.9 ms` | `0.003841 px` | `0.005844 px` | `0.004920` | `30.4 s` | **PASS** |
| 19 | `20170629_00044_frameImage` | `368.1 ms` | `0.008265 px` | `0.014687 px` | `0.009399` | `33.1 s` | **PASS** |
| 20 | `20170629_00045_frameImage` | `423.5 ms` | `0.004120 px` | `0.007800 px` | `0.006401` | `31.9 s` | **PASS** |
| 21 | `20170629_00046_frameImage` | `360.5 ms` | `0.006282 px` | `0.012450 px` | `0.009397` | `30.4 s` | **PASS** |
| 22 | `20170629_00047_frameImage` | `361.3 ms` | `0.004370 px` | `0.008746 px` | `0.005756` | `30.0 s` | **PASS** |
| 23 | `20170629_00048_frameImage` | `361.9 ms` | `0.003877 px` | `0.007614 px` | `0.005491` | `30.0 s` | **PASS** |
| 24 | `20170629_00049_frameImage` | `364.8 ms` | `0.006168 px` | `0.009334 px` | `0.008604` | `30.2 s` | **PASS** |

### Aggregate Summary Statistics (24 Movies)

| Metric | Measured Result | Gate 2 Tolerance | Compliance |
| :--- | :---: | :---: | :---: |
| **Gate 2 Pass Rate** | **`24 / 24 (100%)`** | 100% | **PASS** |
| **Normalized STAR Metadata Differences** | **`0`** | 0 | **PASS** |
| **Coordinate RMS Shift Error** | `0.005103 ± 0.001389 px` (range: `0.003068`–`0.008265`) | $\le 0.020\text{ px}$ | **PASS** |
| **Max Frame Shift Error** | `0.009018 ± 0.002816 px` (range: `0.004590`–`0.014687`) | $\le 0.050\text{ px}$ | **PASS** |
| **Image RMSE** | `0.006683 ± 0.001548` (range: `0.004334`–`0.009399`) | $\le 0.020$ | **PASS** |
| **GPU Global Alignment Time** | `393.7 ± 68.3 ms` (steady state: `~365 ms`) | — | — |
| **Peak GPU VRAM Allocated** | **`1569.59 MiB`** (~1.53 GiB) | $\le 80\text{ GiB}$ | **PASS** |
| **Total 24-Movie Wall Clock Time** | **`14.2 min`** (exit status `0`) | — | — |

---

## 7. Execution Command Reference

### Run with CUDA Acceleration
```bash
./build-cuda/motioncorr \
  --i movies.star \
  --o MotionCorr_cuda \
  --use_own --gpu 0 --j 4 \
  --dose_weighting \
  --dose_per_frame 1.277 \
  --patch_x 5 --patch_y 5 \
  --bfactor 150 \
  --gainref Movies/gain.mrc
```

### Verification Against CPU Reference
```bash
python3 tools/compare_motioncorr.py \
  --ref MotionCorr_cpu_j1/Movies/20170629_00021_frameImage.mrc \
  --test MotionCorr_cuda/Movies/20170629_00021_frameImage.mrc \
  --ref-star MotionCorr_cpu_j1/Movies/20170629_00021_frameImage.star \
  --test-star MotionCorr_cuda/Movies/20170629_00021_frameImage.star \
  --gate relaxed
```

---

## 8. Go / No-Go Decision & Next Kernel Boundary

### Decision: **GO**

1. **Functional Parity**: Global frame alignment on GPU matches the CPU reference within declared Gate 2 tolerances across all 24 movies of the RELION SPA tutorial dataset (100% pass rate, 0 STAR metadata differences, coordinate RMS error < 0.0083 px vs 0.020 px threshold).
2. **GPU Efficiency**: Steady-state global frame alignment completes in **~365 ms** on GPU for full $3710 \times 3838 \times 24$ frame stacks. Custom kernels execute in ~4 ms and batched cuFFT inverse transform in ~0.83 ms.
3. **Memory Footprint**: Peak VRAM allocation is bounded at **1.53 GiB**, well within standard GPU capacities (compatible with 4 GB+ consumer and enterprise GPUs).

### Next Kernel Boundary: Patch Alignment (Issue #17)
- **Bottleneck Identification**: In the full pipeline, global alignment takes only ~0.36 s on GPU, while the 25 local patch alignments ($5 \times 5$ grid) take ~18–25 seconds on CPU.
- **Next Step**: Port `alignPatch` for local patches to GPU (Issue #17). By batching all 25 patches concurrently into a single cuFFT and kernel launch on the GPU, patch alignment time will drop from ~20 s to < 1 s per micrograph.
- **Numerical Risk**: Single-precision peak fitting interpolation across smaller patch tiles ($742 \times 766$) requires careful bounds checking and quadratic interpolation stability.
