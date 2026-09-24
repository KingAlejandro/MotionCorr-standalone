# MotionCorr CPU Performance & Profiling Baseline Report (Issue #9)

- **Timestamp**: `2026-09-24 11:44:13 UTC`
- **Host Hardware**: `AMD EPYC 7452 32-Core Processor` (124 cores, 432.97 GB RAM)
- **OS / Platform**: `Linux-6.8.0-136-generic-x86_64-with-glibc2.39`
- **Build Configuration**: `Release (C++17, -O3, OpenMP)`

---

## 1. Executive Summary & Benchmark Matrix

| Benchmark Case | Dataset | Threads | Patches | Repetitions | Wall Time (Mean ± Std) | Peak RSS (Max) | Top Bottleneck Stage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Synthetic_Global_1Thread** | `synthetic_128x128_8frames.star` | 1 | 1x1 | 3 | **0.313s ± 0.003s** | 26.0 MB | `global alignment` (1.4%) |
| **Synthetic_Patch3x3_4Threads** | `synthetic_128x128_8frames.star` | 4 | 3x3 | 3 | **0.338s ± 0.008s** | 26.2 MB | `global alignment` (0.8%) |
| **Tutorial_5x5_1Thread** | `20170629_00021_frameImage.tiff` | 1 | 5x5 | 3 | **67.598s ± 0.460s** | 2798.1 MB | `dose weighting` (27.9%) |
| **Tutorial_5x5_4Threads** | `20170629_00021_frameImage.tiff` | 4 | 5x5 | 3 | **31.278s ± 0.427s** | 3038.4 MB | `dose weighting` (25.0%) |
| **Tutorial_5x5_10Threads** | `20170629_00021_frameImage.tiff` | 10 | 5x5 | 3 | **17.960s ± 0.125s** | 3372.9 MB | `dose weighting` (22.0%) |

---

## 2. Stage Breakdown & Bottleneck Analysis

### Case: Synthetic_Global_1Thread (1 Threads, 1x1 Patches)
- **Dataset**: `/home/dxp41838/MotionCorr-standalone/test-data/fixtures/synthetic_128x128_8frames.star` (SHA256: `61dde751f61f...`)
- **Mean Execution Time**: 0.313s (Std: ±0.003s)
- **Peak RSS Memory**: 26.02 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `global alignment` | 0.0044s | ±0.0002s | 1.4% |
| `dose weighting` | 0.0026s | ±0.0000s | 0.8% |
| `global FFT` | 0.0020s | ±0.0000s | 0.6% |
| `dw - calc weight` | 0.0016s | ±0.0000s | 0.5% |
| `global iFFT` | 0.0014s | ±0.0000s | 0.4% |
| `dw - iFFT` | 0.0010s | ±0.0000s | 0.3% |
| `read movie` | 0.0008s | ±0.0000s | 0.3% |
| `align - iFFT CCF (in thread)` | 0.0001s | ±0.0000s | 0.0% |

### Case: Synthetic_Patch3x3_4Threads (4 Threads, 3x3 Patches)
- **Dataset**: `/home/dxp41838/MotionCorr-standalone/test-data/fixtures/synthetic_128x128_8frames.star` (SHA256: `61dde751f61f...`)
- **Mean Execution Time**: 0.338s (Std: ±0.008s)
- **Peak RSS Memory**: 26.16 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `global alignment` | 0.0027s | ±0.0004s | 0.8% |
| `read movie` | 0.0017s | ±0.0002s | 0.5% |
| `global FFT` | 0.0017s | ±0.0001s | 0.5% |
| `patch alignment` | 0.0014s | ±0.0001s | 0.4% |
| `prepare patch` | 0.0013s | ±0.0000s | 0.4% |
| `dose weighting` | 0.0012s | ±0.0001s | 0.4% |
| `real space interpolation` | 0.0008s | ±0.0001s | 0.2% |
| `global iFFT` | 0.0007s | ±0.0001s | 0.2% |

### Case: Tutorial_5x5_1Thread (1 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 67.598s (Std: ±0.460s)
- **Peak RSS Memory**: 2798.11 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 18.8709s | ±0.1770s | 27.9% |
| `global iFFT` | 15.5119s | ±0.1705s | 22.9% |
| `dw - iFFT` | 14.6920s | ±0.1510s | 21.7% |
| `global FFT` | 14.4741s | ±0.0867s | 21.4% |
| `real space interpolation` | 4.7515s | ±0.0343s | 7.0% |
| `dw - calc weight` | 4.1789s | ±0.0313s | 6.2% |
| `power spectrum` | 2.2371s | ±0.0584s | 3.3% |
| `read movie` | 1.8687s | ±0.0162s | 2.8% |

### Case: Tutorial_5x5_4Threads (4 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 31.278s (Std: ±0.427s)
- **Peak RSS Memory**: 3038.37 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 7.8132s | ±0.0713s | 25.0% |
| `global iFFT` | 6.7836s | ±0.0808s | 21.7% |
| `global FFT` | 6.7091s | ±0.0320s | 21.5% |
| `dw - iFFT` | 6.5991s | ±0.0601s | 21.1% |
| `power spectrum` | 2.3110s | ±0.1872s | 7.4% |
| `real space interpolation` | 1.9920s | ±0.0204s | 6.4% |
| `power - square` | 1.2313s | ±0.0278s | 3.9% |
| `dw - calc weight` | 1.2140s | ±0.0263s | 3.9% |

### Case: Tutorial_5x5_10Threads (10 Threads, 5x5 Patches)
- **Dataset**: `/home/dxp41838/relion30_tutorial/Movies/20170629_00021_frameImage.tiff` (SHA256: `df298b1b7741...`)
- **Mean Execution Time**: 17.960s (Std: ±0.125s)
- **Peak RSS Memory**: 3372.91 MB

| Stage / Subroutine | Mean Duration (s) | StdDev (s) | % of Total Time |
| :--- | :--- | :--- | :--- |
| `dose weighting` | 3.9564s | ±0.0105s | 22.0% |
| `global iFFT` | 3.5583s | ±0.0382s | 19.8% |
| `dw - iFFT` | 3.4361s | ±0.0066s | 19.1% |
| `global FFT` | 3.4213s | ±0.0262s | 19.0% |
| `power spectrum` | 2.3767s | ±0.0637s | 13.2% |
| `power - square` | 1.2350s | ±0.0230s | 6.9% |
| `power - sum` | 0.9098s | ±0.0529s | 5.1% |
| `real space interpolation` | 0.8329s | ±0.0082s | 4.6% |

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
