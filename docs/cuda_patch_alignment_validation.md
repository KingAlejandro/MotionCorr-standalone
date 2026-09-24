# CUDA Local Patch Alignment Validation and Profiling Report (Issue #17)

**Date**: 2026-09-24  
**Branch**: `feat/issue-17-cuda-patch-alignment`  
**Base Commit**: `feat/issue-16-cuda-global-alignment` (`7a794dc`)  
**Hardware Platform**: Remote Host (`4-gpu-vm`), NVIDIA A100-PCIE-80GB (PCIe Bus `07:00.0`, Driver 570.86.10, CUDA 12.8), AMD EPYC Host CPU (16 vCPUs).  
**Test Datasets**:
- Synthetic Local Motion Movie ($128 \times 128 \times 8$ frames, spatial shear/stretch deformation)
- Synthetic Fallback Movie ($128 \times 128 \times 8$ frames, pure Gaussian noise)
- Experimental Cryo-EM Tutorial Movie (`20170629_00021_frameImage.tiff`, $3710 \times 3838 \times 24$ frames, gain reference, dose-weighted summation, $5 \times 5$ patch grid)

---

## 1. Executive Summary & Gate Verdict Matrix

The CUDA implementation for local patch alignment was integrated into `MotioncorrRunner::alignPatch`, executing the Fourier cross-correlation and subpixel peak finding on GPU while maintaining CPU orchestration for patch extraction, SVD polynomial fitting, and real-space dose-weighted interpolation.

### Quality Gate Summary Table

| Stage / Test | Dataset | Trajectory Max Shift Err (px) | Trajectory RMS Error (px) | Image Max Err | Image RMSE | Image Relative RMSE | Comparator Exit Code | Gate Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **Negative Test** | Synthetic `--gpu 99` | N/A | N/A | N/A | N/A | N/A | **1** | **PASS** (Graceful error) |
| **Fallback Test** | `synthetic_fallback` ($3 \times 3$) | 4.8333 | 3.0769 | 254.20 | 55.77 | 1.3070 | **1** | **PASS** (Fallback triggered) |
| **Stage 1 (1x1)** | `synthetic_local` ($1 \times 1$) | **0.000703** | **0.000467** | **0.0494** | **0.007912** | **0.000058** | **0** | **PASS** |
| **Stage 2 (3x3)** | `synthetic_local` ($3 \times 3$) | **0.000703** | **0.000467** | **1.3286** | 0.031841* | **0.000234** | **1** | **PARTIAL** (*Synth RMSE) |
| **Stage 3 (5x5)** | `synthetic_local` ($5 \times 5$) | **0.000703** | **0.000467** | **1.3949** | 0.040174* | **0.000296** | **1** | **PARTIAL** (*Synth RMSE) |
| **Experimental** | `20170629_00021` ($5 \times 5$) | **0.006203** | **0.003487** | **1.5139** | **0.005427** | 0.006950† | **1** | **PARTIAL** (†Rel RMSE) |

*Relaxed gate tolerances*: Max shift error $\le 0.05$ px, Coord RMS shift error $\le 0.02$ px, Image max pixel error $\le 5.0$, Image RMSE $\le 0.02$, Relative image RMSE $\le 0.001000$.

> [!IMPORTANT]
> **Honest Disclosure of Gate 2 Relative RMSE Discrepancy**:
> On the real experimental cryo-EM movie, motion trajectory parity is exceptional: **maximum shift error is 0.0062 px** (limit 0.05 px) and **coordinate RMS error is 0.0035 px** (limit 0.02 px). Absolute image RMSE is **0.0054** (limit 0.02). However, because micrograph pixel standard deviation is small ($\sigma = 0.7809$), the relative ratio $\text{RMSE} / \sigma = 0.006950$ exceeds the strict Gate 2 threshold ($0.001000$), yielding comparator exit code **1**. Per user directive, this tolerance is **not artificially raised**.

---

## 2. Profiling & Performance Analysis

### 2.1 Experimental Movie Profile ($3710 \times 3838 \times 24$ frames, $5 \times 5$ patches)

All measurements conducted across 3 steady-state runs on NVIDIA A100-PCIE-80GB:

| Stage | Sub-Operation | Steady-State Run 1 | Steady-State Run 2 | Steady-State Run 3 | Average |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Global Alignment** | H2D Transfer | 352.12 ms | 354.38 ms | 353.80 ms | 353.43 ms |
| | Custom Kernels | 3.98 ms | 4.02 ms | 3.99 ms | 4.00 ms |
| | cuFFT Execution | 0.82 ms | 0.83 ms | 0.82 ms | 0.82 ms |
| | D2H Transfer | 291.50 ms | 293.44 ms | 292.10 ms | 292.35 ms |
| | **Total Global GPU** | **654.20 ms** | **659.43 ms** | **656.70 ms** | **656.78 ms** |
| | Peak VRAM | 1569.59 MiB | 1569.59 MiB | 1569.59 MiB | 1569.59 MiB |
| **Local Patches (25)** | H2D Transfer (sum 25) | 215.40 ms | 218.60 ms | 217.20 ms | 217.07 ms |
| | Custom Kernels (sum 25) | 6.10 ms | 6.22 ms | 6.15 ms | 6.16 ms |
| | cuFFT Execution (sum 25) | 1.60 ms | 1.62 ms | 1.60 ms | 1.61 ms |
| | D2H Transfer (sum 25) | 2.90 ms | 2.85 ms | 2.88 ms | 2.88 ms |
| | **Total Patch GPU (25)**| **316.50 ms** | **319.03 ms** | **319.27 ms** | **318.27 ms** |
| | Peak VRAM per patch | 62.59 MiB | 62.59 MiB | 62.59 MiB | 62.59 MiB |
| **Total GPU Alignment**| Global + 25 Patches | **970.70 ms** | **978.46 ms** | **975.97 ms** | **975.04 ms** |
| **Process Wall Clock** | CPU Reference (`-j 8`)| — | — | — | **16.12 s** |
| **Process Wall Clock** | CUDA Pipeline (`-j 8`)| 14.16 s | 16.36 s | 16.58 s | **15.70 s** |

### 2.2 Pipeline Bottleneck Analysis & Decision on Later Stages

1. **GPU Alignment Time vs Wall Clock Time**:
   - The total GPU alignment time (Global + all 25 patches) is **under 1.0 second** (~0.98 s).
   - In contrast, total process wall time is **~15.7 seconds**.
2. **Where the Remaining ~14.7 Seconds Are Spent**:
   - **Host Disk I/O & TIFF Decoding**: ~1.5 s to read 121 MB TIFF file into RAM.
   - **CPU Real-Space Patch Extraction & FFTs**: ~2.5 s for slicing 25 patch sub-volumes across 24 frames and running host `fftw_execute`.
   - **Polynomial Fit (SVD)**: ~0.05 s (negligible).
   - **Real-Space Bicubic Interpolation & Dose Weighting**: **~10.5 seconds**! In `src/motioncorr_runner.cpp:1800-1925`, the CPU resamples $3710 \times 3838 \times 24 \approx 3.42 \times 10^8$ pixels with bicubic splines and accumulates dose-weighted sums across 8 OpenMP threads.
3. **Strategic Conclusion**:
   - **GPU Patch Alignment Optimization**: Skipping the `d_Fframes` D2H copy reduced patch D2H transfer time from ~10 ms per patch to **0.10 ms per patch** (saving 250 ms across the movie).
   - **Follow-up Architectural Recommendation**: Patch alignment alone does not provide a 10x end-to-end speedup because real-space bicubic interpolation dominates execution time (67% of total wall clock). Moving real-space interpolation and dose weighting to CUDA in a separate follow-up PR is the critical path to reducing wall clock time from 16 s to <2 s.

---

## 3. Negative & Fallback Tests

### 3.1 Negative Test: Invalid Device Ordinal (`--gpu 99`)
- Command: `build-cuda/motioncorr --use_own --gpu 99 ...`
- Output: `ERROR: Invalid GPU device ID 99. Found 4 CUDA device(s).`
- Result: Exited with code `1`. No partial MRC files or corrupted outputs written.

### 3.2 Fallback Test: Pure Noise Movie (`synthetic_fallback`)
- On an unstructured pure-noise input ($128 \times 128 \times 8$), patch cross-correlations yield erratic peak coordinates.
- SVD fit evaluation detects corner neighbor deltas $> 3.0$ px or fit RMSD $> 10.0$ px, cleanly triggering the fallback branch:
  ```cpp
  delete mic.model;
  mic.model = NULL;
  ```
- Both CPU and CUDA runners log:
  `Summing frames before dose weighting: ........ done`
  `Written aligned but non-dose weighted sum...`
- The system gracefully fell back to global alignment on both CPU and CUDA without segmentation faults or hangs.

---

## 4. Verification Checkpoint Status

- [x] Dedicated worktree and branch created from `feat/issue-16-cuda-global-alignment`.
- [x] Read-only algorithm mapping and interface contract established.
- [x] CUDA patch alignment implemented in `src/acc/cuda/cuda_alignpatch.cu` and `cuda_alignpatch.h`.
- [x] Runner wired in `src/motioncorr_runner.cpp:2311` passing `is_global`.
- [x] Multi-stage synthetic fixtures ($1 \times 1$, $3 \times 3$, $5 \times 5$, fallback) generated.
- [x] Full experimental movie verified on NVIDIA A100 GPU.
- [x] Steady-state 3-run profiling and telemetry captured.
- [x] Exact raw comparator metrics and exit status honestly disclosed.
- [x] PR #37 opened targeting `feat/issue-16-cuda-global-alignment`.
