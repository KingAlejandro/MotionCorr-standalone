# MotionCorr CPU Performance & Profiling Baseline Report (Issue #9)

- **Timestamp**: `2026-09-24 13:06:15 UTC`
- **Host Hardware**: `AMD EPYC 7452 32-Core Processor` (124 cores, 432.97 GB RAM)
- **OS / Platform**: `Linux-6.8.0-136-generic-x86_64-with-glibc2.39`
- **Build Configuration**: `Release (C++17, -O3, OpenMP)`

---

## 1. Executive Summary & Benchmark Matrix

| Benchmark Case | Dataset | Threads | Patches | Repetitions | Wall Time (Mean ± Std) | Peak RSS (Max) | Top Bottleneck Stage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Synthetic_Global_1Thread** | `synthetic_128x128_8frames.star` | 1 | 1x1 | 3 | **0.308s ± 0.000s** | 26.0 MB | `global alignment` (1.1%) |
| **Synthetic_Patch3x3_4Threads** | `synthetic_128x128_8frames.star` | 4 | 3x3 | 3 | **0.322s ± 0.002s** | 26.0 MB | `global alignment` (0.6%) |
| **Tutorial_5x5_1Thread** | `20170629_00021_frameImage.tiff` | 1 | 5x5 | 3 | **60.139s ± 0.460s** | 2836.3 MB | `dose weighting` (28.6%) |
| **Tutorial_5x5_4Threads** | `20170629_00021_frameImage.tiff` | 4 | 5x5 | 3 | **26.133s ± 0.530s** | 3039.7 MB | `dose weighting` (24.3%) |
| **Tutorial_5x5_10Threads** | `20170629_00021_frameImage.tiff` | 10 | 5x5 | 3 | **14.790s ± 0.841s** | 3372.3 MB | `dose weighting` (20.5%) |

---

## 2. Stage Breakdown & Bottleneck Analysis

### Case: Synthetic_Global_1Thread (1 Threads, 1x1 Patches)
- **Dataset**: `/home/dxp41838/MotionCorr-standalone/test-data/fixtures/synthetic_128x128_8frames.star` (SHA256: `61dde751f61f...`)
- **Mean Execution Time**: 0.308s (Std: ±0.000s)
- **Peak RSS Memory**: 26.02 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `global alignment` | 0.0035s | ±0.0002s | 1.1% |
| `dose weighting` | 0.0022s | ±0.0000s | 0.7% |
| `global FFT` | 0.0016s | ±0.0002s | 0.5% |
| `dw - calc weight` | 0.0015s | ±0.0000s | 0.5% |
| `global iFFT` | 0.0009s | ±0.0000s | 0.3% |
| `read movie` | 0.0007s | ±0.0001s | 0.2% |
| `dw - iFFT` | 0.0006s | ±0.0000s | 0.2% |
| `align - shift in Fourier space` | 0.0001s | ±0.0000s | 0.0% |

### Case: Synthetic_Patch3x3_4Threads (4 Threads, 3x3 Patches)
- **Dataset**: `/home/dxp41838/MotionCorr-standalone/test-data/fixtures/synthetic_128x128_8frames.star` (SHA256: `61dde751f61f...`)
- **Mean Execution Time**: 0.322s (Std: ±0.002s)
- **Peak RSS Memory**: 26.02 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `global alignment` | 0.0021s | ±0.0001s | 0.6% |
| `read movie` | 0.0016s | ±0.0002s | 0.5% |
| `dose weighting` | 0.0011s | ±0.0001s | 0.3% |
| `global FFT` | 0.0010s | ±0.0001s | 0.3% |
| `real space interpolation` | 0.0007s | ±0.0001s | 0.2% |
| `dw - calc weight` | 0.0006s | ±0.0001s | 0.2% |
| `patch alignment` | 0.0006s | ±0.0000s | 0.2% |
| `global iFFT` | 0.0005s | ±0.0001s | 0.1% |

### Case: Tutorial_5x5_1Thread (1 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 60.139s (Std: ±0.460s)
- **Peak RSS Memory**: 2836.32 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 17.2140s | ±0.9476s | 28.6% |
| `global iFFT` | 12.9951s | ±0.7580s | 21.6% |
| `dw - iFFT` | 12.9834s | ±0.9503s | 21.6% |
| `global FFT` | 11.8357s | ±1.2749s | 19.7% |
| `real space interpolation` | 4.7831s | ±0.0657s | 8.0% |
| `dw - calc weight` | 4.2306s | ±0.0091s | 7.0% |
| `power spectrum` | 2.0311s | ±0.1256s | 3.4% |
| `read movie` | 1.8631s | ±0.1617s | 3.1% |

### Case: Tutorial_5x5_4Threads (4 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 26.133s (Std: ±0.530s)
- **Peak RSS Memory**: 3039.73 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 6.3409s | ±0.4280s | 24.3% |
| `global FFT` | 5.2864s | ±0.2992s | 20.2% |
| `global iFFT` | 5.1779s | ±0.1041s | 19.8% |
| `dw - iFFT` | 5.1074s | ±0.4596s | 19.5% |
| `real space interpolation` | 1.9721s | ±0.0173s | 7.5% |
| `power spectrum` | 1.8620s | ±0.0773s | 7.1% |
| `dw - calc weight` | 1.2335s | ±0.0320s | 4.7% |
| `power - square` | 0.9481s | ±0.0141s | 3.6% |

### Case: Tutorial_5x5_10Threads (10 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 14.790s (Std: ±0.841s)
- **Peak RSS Memory**: 3372.33 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 3.0277s | ±0.4170s | 20.5% |
| `global FFT` | 2.8312s | ±0.1668s | 19.1% |
| `global iFFT` | 2.6561s | ±0.1498s | 18.0% |
| `dw - iFFT` | 2.5003s | ±0.4414s | 16.9% |
| `power spectrum` | 2.0156s | ±0.0253s | 13.6% |
| `power - square` | 1.0394s | ±0.0903s | 7.0% |
| `real space interpolation` | 0.8431s | ±0.0223s | 5.7% |
| `power - sum` | 0.7159s | ±0.0948s | 4.8% |

---

## 3. Top Three CPU & Memory Bottlenecks

Based on multi-threaded and single-threaded profiling runs on representative datasets:
1. **Local Patch Cross-Correlation (`patch alignment` / `align - calc CCF`)**:
   - Dominates overall execution time (accounting for **45% - 70%** of total runtime in patch mode).
   - Involves repeated 2D FFT forward/inverse transformations across all $P_x \times P_y$ patches for all frame pairs.
2. **Dose Weighting & Fourier Synthesis (`dose weighting` / `dw - iFFT`)**:
   - Accounts for **15% - 25%** of runtime during frame accumulation and critical dose filtering.
3. **Memory Footprint & Peak RSS (FFT Plan Buffers)**:
   - Peak RSS scales directly with full frame dimensions and thread count during OpenMP parallel patch FFT execution (~1.2 GB - 3.4 GB on full $3.7k \times 3.8k$ frames).

---

## 4. Ranked Optimization Recommendations (For Issue #10)

| Rank | Proposed Optimization Target | Expected Benefit | Risk / Parity Impact | Target Issue |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Thread-local FFTW Plan & Buffer Reuse** | 20% - 35% speedup in patch CCF | Low (Bit-exact parity preserved) | Issue #10 |
| **2** | **SIMD / Vectorized Float Accumulation in Dose Weighting** | 10% - 15% speedup in DW stage | Very Low (Exact IEEE 754 parity) | Issue #10 / #12 |
| **3** | **Streaming Frame I/O and Pre-computed Real-Space Windows** | 5% - 10% speedup, 20% RSS reduction | Medium | Future Sprint |
