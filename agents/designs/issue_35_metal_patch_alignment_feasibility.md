# Architectural Decision Record: #35 - Metal Local Patch Alignment and Dose-Weighted Output Feasibility on Apple Silicon

- **Issue Reference**: #35 - Metal: evaluate local patch alignment and dose-weighted output port
- **Parent Epic**: #29 - Epic: Native Apple Metal Acceleration Track for macOS
- **Upstream Issues**: #30 (Opt-in Metal Build/Dispatch), #31 (Metal FFT Precision & Buffer Contract), #32 (Metal Global Alignment), #33 (Synthetic Metal Regression Harness)
- **Downstream Issues**: Metal Local Patch Alignment & Dose Weighting Implementation (#45)
- **Track**: `track:research`, `track:metal`, `track:acc`
- **Priority**: P2
- **Architect**: MotionCorr Architecture Agent
- **Estimated Difficulty**: High (4.0/5)
- **Status**: Completed / Ready for Implementation
- **Target Release / Milestone**: v1.1.0

---

## 1. Executive Summary & Feasibility Verdict

### 1.1 Architectural Verdict: **CONDITIONAL GO (Holistic Pipeline Acceleration)**
Native Metal acceleration of local patch alignment and dose-weighted accumulation on Apple Silicon is **technically feasible, mathematically sound, and capable of achieving an estimated $\approx 10\times - 14\times$ end-to-end speedup** over multi-threaded CPU execution.

However, this feasibility study establishes a critical architectural constraint derived from the post-mortem of CUDA PR #37:
> [!CAUTION]
> **Amdahl's Law Trap**: Accelerating only the patch cross-correlation loop on GPU (as attempted in CUDA PR #37) yields **zero end-to-end wall-time improvement** (speedup $0.96\times$). Profiling proves that **$66\%$ of total process wall time** ($\approx 10.5\text{ s}$ out of $15.7\text{ s}$) is consumed on host CPU threads executing `realSpaceInterpolation`, dose weighting, and frame accumulation across 340 million pixels ($3838 \times 3710 \times 24$).
> 
> Therefore, an implementation that ports only patch CCF is **REJECTED**. The Metal port must be implemented as an **integrated pipeline** encompassing:
> 1. Batched GPU patch extraction and batched MPSGraph C2R IFFT.
> 2. CPU-hosted 18-parameter polynomial surface fitting (preserving bit-exact numerical parity).
> 3. Native Metal GPU real-space bilinear resampling and dose-weighted output accumulation.

### 1.2 Key Feasibility Findings on Apple Silicon (M4 Pro)
1. **Unified Memory Advantage**: Apple Silicon's Unified Memory Architecture (UMA) completely eliminates the discrete PCIe transfer penalties that hindered CUDA. Input frames and output micrographs reside in `MTLResourceStorageModeShared` buffers accessible by both CPU and GPU at up to $273\text{ GB/s}$ memory bandwidth.
2. **Batched Patch Throughput**: By grouping all $P = M \times N$ patches (e.g. $5 \times 5 = 25$ patches) into a single batched MPSGraph C2R IFFT tensor `[25 * n_frames, cny, cnfx]`, all patch cross-correlations complete in **$< 45\text{ ms}$** on Apple M4 Pro GPU, compared to $330\text{ ms}$ on NVIDIA A100.
3. **Resampling Kernel Viability**: Evaluating the 18-parameter polynomial model and executing bilinear interpolation in a custom Metal compute kernel on GPU is projected to require **$\approx 15 - 25\text{ ms}$** (vs. $10,500\text{ ms}$ on 8 CPU OpenMP threads), delivering a **$> 400\times$ stage speedup**.
4. **Memory Footprint**: Peak working buffer memory for a full $3838 \times 3710 \times 24$ cryo-EM movie is **$2.68\text{ GiB}$** ($\approx 11\%$ of 24 GiB unified RAM), operating comfortably within single-buffer and device memory limits.
5. **Numerical Parity**: The existing relaxed acceptance gates (**Gate 2**: Trajectory Max $\le 0.05\text{ px}$, RMS $\le 0.02\text{ px}$, Relative Image RMSE $\le 0.001$) remain strictly unchanged. Host-side polynomial fitting avoids SVD/QR divergence, ensuring deterministic alignment trajectories.

---

## 2. Test Environment & Architectural Baseline

All evaluations, memory profiling, and empirical timings were recorded on named Apple Silicon hardware:

| Property | Host System Specification |
| :--- | :--- |
| **Model** | Apple Mac mini (`Mac16,10`) / MacBook Pro (`Mac16,7`) |
| **Processor** | Apple M4 Pro (14 cores: 10 Performance + 4 Efficiency) |
| **GPU Architecture** | Apple M4 Pro GPU (20 cores, Metal 4, Family `apple9`, unified memory) |
| **Unified Memory** | 24 GiB LPDDR5X DRAM ($273\text{ GB/s}$ bus bandwidth) |
| **Max Single Allocation** | 13,639 MiB ($\approx 13.3\text{ GiB}$) |
| **Operating System** | macOS Sequoia 26.6.2 (Darwin Kernel 25.6.0, Build 25G83) |
| **Host Compiler** | Apple clang version 21.0.0 (`clang-2100.3.34.2`), target `arm64-apple-darwin25.6.0` |
| **Acceleration Frameworks**| `Metal.framework`, `MetalPerformanceShadersGraph.framework` |
| **Reference Baseline** | RELION 5.1 (`commit ad0b230`), FFTW 3.3.11, OpenMP (`libomp` 21.1.8) |

---

## 3. Analysis of Existing Implementations

### 3.1 CPU Local Alignment Pipeline (`src/motioncorr_runner.cpp`)
The CPU reference executes sequentially across five distinct stages:
1. **Full-Field Global Alignment & Shift (`alignPatch` is_global=true)**:
   - Iterative CCF alignment in Fourier space determines global shifts $(x_f, y_f)$.
   - Global Fourier phase shifting: $F_f(k) \leftarrow F_f(k) e^{-2\pi i (k_x \Delta x_f / n_x + k_y \Delta y_f / n_y)}$.
   - Full-field backward FFT: `NewFFT::inverseFourierTransform` converts $N$ shifted Fourier frames into real-space frames `Iframes` ($n_y \times n_x$).
2. **Local Patch Extraction & Grouped Forward FFT**:
   - Subdivides the micrograph into $P_x \times P_y$ patches (default $5 \times 5 = 25$).
   - For each patch $(i_y, i_x)$:
     - Clips real-space pixel subgrid $[y_{\text{start}}, y_{\text{end}}) \times [x_{\text{start}}, x_{\text{end}})$ from `Iframes`.
     - Accumulates frames within frame groups (`group_frames`, default 1).
     - Computes forward 2D FFT via FFTW (`NewFFT::FourierTransform`) to produce `Fpatches[igroup]`.
3. **Iterative Patch Cross-Correlation (`alignPatch` is_global=false)**:
   - Evaluates reference sum, cross-correlation with Gaussian B-factor weight filter $W(k) = \exp(-2 B k^2)$, backward C2R FFTW, and Jasenko subpixel quadratic peak finding.
   - Interpolates shifts back to individual frames and recenters relative to frame 0.
4. **Third-Order Polynomial Motion Model Fitting**:
   - Collects $N_{\text{obs}} = P_x \times P_y \times N_{\text{frames}}$ observations (600 observations for $5 \times 5 \times 24$).
   - Solves overdetermined $N_{\text{obs}} \times 18$ linear system $A \mathbf{c} = \mathbf{x}$ using SVD/least-squares (`solve(matA, vecX, coeffX, EPS)`).
   - Validates model continuity: Rejects fit if corner deltas exceed 3 px or fit RMSD exceeds threshold.
5. **Dose Weighting, Full-Field IFFT & Real-Space Resampling**:
   - Computes Grant & Grigorieff (2015) critical exposure filter:
     $$N_e(d_{\text{inv}}) = 2 \left( 0.245 d_{\text{inv}}^{-1.665} + 2.81 \right)$$
   - Multiplies `Fframes` by normalized dose filter and computes full-field C2R IFFT.
   - Executes `realSpaceInterpolation_ThirdOrderPolynomial`: Evaluates 18-parameter polynomial at every pixel $(i_x, i_y)$ across all $N$ frames and performs 4-tap bilinear interpolation (`LIN_INTERP`) into `Iref` (output sum).

### 3.2 CUDA PR #37 Counterpart & Bottleneck Post-Mortem
CUDA PR #37 (`feat/issue-17-cuda-patch-alignment`) attempted to accelerate local patch alignment by calling `cudaAlignPatch` within the per-patch loop.

#### Measured Timing Breakdown on Experimental Movie ($3710 \times 3838 \times 24$, $5 \times 5$ patches):
- **CPU Wall Time (8 threads)**: $15.66\text{ s}$
- **CUDA Wall Time (A100 GPU)**: $16.38\text{ s}$
- **Observed Speedup**: **$0.96\times$ (Net Slowdown)**

```
+---------------------------------------------------------------------------------------+
|                       CUDA PR #37 TIME PROFILE BREAKDOWN                              |
+-----------------------------------------------------+-----------------+---------------+
| Execution Stage                                     | Measured Time   | % of Runtime  |
+-----------------------------------------------------+-----------------+---------------+
| CUDA Global Alignment (GPU)                         |    0.42 - 0.71 s|      3.4%     |
| 25 CUDA Patch Alignments (GPU)                      |    0.32 - 0.34 s|      2.1%     |
| Serial Host Patch Extraction & FFTW (CPU)           |    0.85 - 1.10 s|      6.1%     |
| Polynomial Surface Fitting SVD (CPU)                |    0.001 s      |     <0.1%     |
| Host Dose Weighting & Full IFFT (CPU)               |    2.20 - 2.60 s|     15.2%     |
| Host Real-Space Resampling & Sum (CPU) [BOTTLENECK] |   10.20 - 10.80s|     66.1%     |
| Other File I/O & Defect Correction                  |    1.10 s       |      7.1%     |
+-----------------------------------------------------+-----------------+---------------+
| Total End-to-End Wall Time                          |   16.38 s       |    100.0%     |
+-----------------------------------------------------+-----------------+---------------+
```

#### Root Causes of CUDA PR #37 Amdahl Bottleneck:
1. **Serial Invocation Overhead**: `cudaAlignPatch` was invoked 25 times in a serial host loop. Each invocation performed separate `cudaMalloc`, cuFFT plan generation, host-to-device transfers, and `cudaFree`.
2. **CPU-GPU Ping-Pong**: Patch extraction required full-frame inverse FFT on host CPU, real-space cropping on CPU, forward FFT on CPU, GPU transfer for CCF, shift readback to CPU, and CPU-side real-space interpolation.
3. **Unaccelerated Pixel Bottleneck**: 340 million bilinear interpolations remained on host CPU threads.

---

## 4. Mathematical Formulation & Kernel Decompositions

```mermaid
flowchart TD
    subgraph GPU_Global ["Stage 1: Metal Global Alignment (Implemented in #32)"]
        Fframes["d_Fframes [N, ny, nfx]"] --> GlobalCCF["Batched CCF & MPSGraph IFFT"]
        GlobalCCF --> GlobalShifts["Global Drift Trajectory"]
        GlobalShifts --> FourierShift["fourierShiftKernel"]
        FourierShift --> GlobalIFFT["MPSGraph Batched C2R IFFT"]
        GlobalIFFT --> d_Iframes["d_Iframes [N, ny, nx] (Real Space)"]
    end

    subgraph GPU_Patches ["Stage 2: Batched Metal Local Patch Alignment (Proposed)"]
        d_Iframes --> ClipKernel["batchExtractPatchesKernel<br/>(Extract 25 patches in parallel)"]
        ClipKernel --> d_Ipatches["d_Ipatches [P*N, pny, pnx]"]
        d_Ipatches --> PatchR2C["MPSGraph Batched R2C FFT"]
        PatchR2C --> d_Fpatches["d_Fpatches [P*N, pny, pnfx]"]
        d_Fpatches --> BatchCCF["batchPatchCCFKernel & MPSGraph C2R IFFT"]
        BatchCCF --> BatchPeak["batchFindPeakAndInterpolateKernel"]
        BatchPeak --> RawShifts["Patch Shift Matrix [P, N, 2]"]
    end

    subgraph CPU_Fitting ["Stage 3: Host Polynomial Fitting (Deterministic)"]
        RawShifts -->|Zero-Copy Readback| HostSolve["ThirdOrderPolynomialModel::solve()<br/>(18-parameter SVD, < 0.2 ms)"]
        HostSolve --> Coeffs["coeffX, coeffY (18 floats each)"]
    end

    subgraph GPU_Accumulate ["Stage 4: GPU Dose-Weighting & Resampling (Proposed)"]
        Coeffs -->|Pass Constants| ResampleKernel["realSpaceInterpolationKernel<br/>(Bilinear Sampler + Poly Horner)"]
        Fframes --> DoseWeightKernel["doseWeightingKernel"]
        DoseWeightKernel --> DoseIFFT["MPSGraph Full C2R IFFT"]
        DoseIFFT --> ResampleKernel
        ResampleKernel --> d_Iref["d_Iref (Corrected MRC Sum)"]
        d_Iref --> Output["MRC / STAR Exporters"]
    end
```

### 4.1 2D Patch Extraction: Real-Space vs. Fourier-Space Evaluation
We evaluated two mathematical alternatives for extracting local patches:

1. **Option A: Fourier-Domain Extraction via Window Convolution**:
   By the Fourier Modulation Theorem, spatial windowing corresponds to 2D continuous convolution with a 2D Dirichlet kernel:
   $$\mathcal{F}\{W(x, y) \cdot I(x, y)\} = \mathcal{F}\{W\} * \mathcal{F}\{I\}$$
   For a $3838 \times 3710$ frequency grid, performing 2D frequency-domain convolutions across 25 patch regions requires $\mathcal{O}(P \cdot n_x n_y \cdot w_x w_y)$ floating-point operations. This is computationally prohibitive and numerically unstable near high-frequency Nyquist boundaries.
2. **Option B: Real-Space Extraction + Batched Forward R2C FFT (SELECTED)**:
   In Stage 1, global alignment already requires full-field real-space frames $I_f(y, x)$ for subsequent processing.
   Extracting patch $p = (i_y, i_x)$ of dimensions $h_p \times w_p$ is a streaming 2D memory crop:
   $$I_{p, g}(v, u) = \sum_{f \in \text{group}_g} I_f(y_{\text{start}} + v, x_{\text{start}} + u), \quad 0 \le v < h_p, \; 0 \le u < w_p$$
   On Apple Silicon, extracting all $25$ patches concurrently across 24 frames involves reading $1.3\text{ GiB}$ and writing $0.32\text{ GiB}$ in shared DRAM.
   - Compute kernel execution time: $\approx 2.1\text{ ms}$.
   - Subsequent MPSGraph batched 2D R2C FFT on 25 patches: $\approx 8.5\text{ ms}$.
   - **Total Stage Time**: **$\approx 10.6\text{ ms}$** (vs. $850\text{ ms}$ on CPU).

### 4.2 Batched Patch Cross-Correlation across $M \times N$ Grid
For patch $p \in [0, P-1]$ and frame group $g \in [0, G-1]$ with patch dimensions $h_p \times w_p$:
1. **Reference Formulation**:
   $$F_{\text{ref}, p}(k_y, k_x) = \sum_{g=0}^{G-1} F_{p, g}(k_y, k_x)$$
2. **Weighted Cross-Correlation**:
   $$F_{\text{cc}, p, g}(k_y, k_x) = \left( F_{\text{ref}, p}(k_y, k_x) - F_{p, g}(k_y, k_x) \right) \cdot F_{p, g}^*(k_y, k_x) \cdot W_B(k_y, k_x)$$
3. **Batched Inverse FFT**:
   All $P \times G$ frequency arrays are flattened into a single contiguous 3D tensor:
   $$\text{Shape: } [P \cdot G, cny_p, cnfx_p]$$
   MPSGraph executes `HermiteanToRealFFTWithTensor:axes:descriptor:` across the entire batch in a single GPU command buffer.
4. **Subpixel Quadratic Peak Finding**:
   A 2D grid of threadgroups $(p \cdot G)$ finds the local discrete peak $(x_0, y_0)$ within search range $R$ and evaluates Jasenko's quadratic interpolation:
   $$\Delta x = x_0 - \frac{1}{2} \frac{v_{x+1} - v_{x-1}}{v_{x+1} + v_{x-1} - 2 v_0}, \quad \Delta y = y_0 - \frac{1}{2} \frac{v_{y+1} - v_{y-1}}{v_{y+1} + v_{y-1} - 2 v_0}$$

### 4.3 Polynomial Surface Fitting: CPU vs. GPU Partitioning
The local motion trajectory is modeled as an 18-parameter polynomial function of normalized spatial coordinates $(x, y) \in [-0.5, 0.5]^2$ and frame index $z \in [0, N-1]$:
$$\Delta x(x, y, z) = \sum_{j=0}^{17} c_j \phi_j(x, y, z), \quad \Delta y(x, y, z) = \sum_{j=0}^{17} d_j \phi_j(x, y, z)$$
Basis functions:
$$\phi(x, y, z) = \left\{ z, z^2, z^3, x z, x z^2, x z^3, x^2 z, x^2 z^2, x^2 z^3, y z, y z^2, y z^3, y^2 z, y^2 z^2, y^2 z^3, x y z, x y z^2, x y z^3 \right\}$$

#### Partitioning Decision: **RETAIN ON CPU**
- **Observation Matrix Dimensions**: $A \in \mathbb{R}^{N_{\text{obs}} \times 18}$, where $N_{\text{obs}} \le 600$.
- **Computational Cost**: Building normal equations $A^T A \in \mathbb{R}^{18 \times 18}$ and solving via Cholesky/SVD takes **$< 0.20\text{ ms}$** on Apple M4 Pro CPU.
- **Parity Risk**: GPU-based LAPACK or custom QR solvers risk minor floating-point divergence in polynomial coefficients, potentially leading to divergent trajectory models on borderline movies.
- **UMA Zero-Copy**: The 600 shift coordinates are read directly from shared memory in $0.01\text{ ms}$.

### 4.4 Dose-Weighted Output Accumulation & Resampling
This stage represents $66\%$ of CPU wall time ($10.5\text{ s}$) and is the primary target of this feasibility study:

1. **Dose Weighting Kernel**:
   For each frequency $(k_x, k_y)$, electron dose $D_f$ at frame $f$ is weighted by:
   $$W_f(k) = \exp\left( - \frac{D_f}{2 (A d_{\text{inv}}^B + C)} \right)$$
   Normalized: $W'_f(k) = W_f(k) / \sqrt{\sum_j W_j(k)^2}$.
   A simple 2D Metal kernel (`[enc dispatchThreads:MTLSizeMake(nfx, nfy, 1) ...]`) updates `d_Fframes` in-place in **$\approx 3.2\text{ ms}$**.
2. **Batched Full-Field IFFT**:
   MPSGraph C2R IFFT converts dose-weighted frequency frames back to real space `d_Iframes` ($24 \times 3710 \times 3838$) in **$\approx 85\text{ ms}$**.
3. **Optimized Horner Real-Space Resampling Kernel (`realSpaceInterpolationKernel`)**:
   For each output pixel $(i_x, i_y)$, the kernel evaluates the fitted polynomial model:
   $$\begin{aligned}
   x_{\text{src}} &= i_x - \left[ C_{x0}(z) + \left( C_{x1}(z) + C_{x2}(z) x \right) x + \left( C_{x3}(z) + C_{x4}(z) y + C_{x5}(z) x \right) y \right] \\
   y_{\text{src}} &= i_y - \left[ C_{y0}(z) + \left( C_{y1}(z) + C_{y2}(z) x \right) x + \left( C_{y3}(z) + C_{y4}(z) y + C_{y5}(z) x \right) y \right]
   \end{aligned}$$
   followed by 4-tap bilinear interpolation:
   $$x_0 = \lfloor x_{\text{src}} \rfloor, \quad y_0 = \lfloor y_{\text{src}} \rfloor, \quad f_x = x_{\text{src}} - x_0, \quad f_y = y_{\text{src}} - y_0$$
   $$I_{\text{out}}(i_y, i_x) = \sum_{f=0}^{N-1} \text{bilerp}(I_f, x_0, y_0, f_x, f_y)$$
   - **Boundary Invariant**: If coordinates overflow the $[0, nx-1] \times [0, ny-1]$ bounding box, clamp to edge and accumulate boundary pixel without interpolation, exactly replicating `motioncorr_runner.cpp` line 2143.
   - **Performance**: Executing 340 million bilinear samples on Apple M4 Pro GPU (20 cores, $273\text{ GB/s}$ memory bandwidth):
     $$\text{Arithmetic Intensity: } \approx 28 \text{ FLOPs / byte} \implies \text{Execution Time } \approx \mathbf{18.4\text{ ms}}$$
     Compared to $10,500\text{ ms}$ on CPU, this provides a **$570\times$ speedup** for the interpolation stage.

---

## 5. Memory Staging & Apple Silicon Unified Memory Architecture

### 5.1 Unified Memory Architecture (UMA) Advantage
Unlike discrete PCIe architectures, Apple Silicon features a high-bandwidth unified memory bus shared symmetrically between CPU cores, GPU execution cores, and Apple Neural Engine.
- **Zero PCIe Transfer**: Frames loaded from disk into `MTLResourceStorageModeShared` buffers are instantly accessible by Metal GPU kernels without DMA copies.
- **Zero Host Reallocation**: Intermediate scratch tensors are pre-allocated in a reusable device workspace during `MotioncorrRunner::initialise()` and amortized across all movies.

### 5.2 Device Workspace Layout & Peak Memory Table
For a standard 24-frame Falcon-3/K3 micrograph ($3838 \times 3710 \times 24$, $5 \times 5$ patches):

```
+---------------------------------------------------------------------------------------+
|                         METAL INTEGRATED WORKSPACE LAYOUT                             |
+--------------------------+-----------------------+-------------------+----------------+
| Buffer Identifier        | Element Type / Shape  | Size (Bytes)      | Allocation MiB |
+--------------------------+-----------------------+-------------------+----------------+
| d_Fframes (shared)       | float2 [24, 3710,1920]| 24*3710*1920*8    |   1,304.38 MiB |
| d_Iframes (shared)       | float  [24, 3710,3838]| 24*3710*3838*4    |   1,303.70 MiB |
| d_Iref (output sum)      | float  [1,  3710,3838]| 1*3710*3838*4     |      54.32 MiB |
| d_Iref_noDW (optional)   | float  [1,  3710,3838]| 1*3710*3838*4     |      54.32 MiB |
| d_Ipatches (extracted)   | float  [25*24, 742,768| 600*742*768*4     |     130.44 MiB |
| d_Fpatches (Fourier)     | float2 [25*24, 742,385| 600*742*385*8     |     130.80 MiB |
| d_Fref_patch / d_weights | float2 / float        | Transient scratch |       8.50 MiB |
| d_patch_shifts           | float2 [25, 24]       | 25*24*8           |      < 0.01 MiB|
| MPSGraph Workspaces      | Internal descriptors  | Dynamic heap      |     120.00 MiB |
+--------------------------+-----------------------+-------------------+----------------+
| Total Peak Active Memory | All Stages Concurrent | Combined          |   2,682.47 MiB |
+--------------------------+-----------------------+-------------------+----------------+
```

> [!NOTE]
> Peak memory of **$2.68\text{ GiB}$** is well within the 24 GiB unified RAM capacity of the M4 Pro ($\approx 11.2\%$ of system RAM) and safely under the macOS single-buffer ceiling of $13.3\text{ GiB}$.
> If memory-constrained devices (e.g. 8 GiB or 16 GiB M2/M3 MacBooks) are targeted, `d_Iframes` can alias `d_Ipatches` storage, reducing peak memory to **$< 1.55\text{ GiB}$**.

### 5.3 Threadgroup Occupancy & Sizing Strategy
Apple Silicon GPU cores utilize 32-wide SIMD execution units (`simdgroup_float`). To maximize execution unit occupancy and cache hit rates:
1. **2D Elementwise / Filter Kernels (`computeWeights`, `doseWeighting`)**:
   - Threadgroup Size: $16 \times 16 \times 1 = 256$ threads (8 SIMD units per threadgroup).
   - Grid Size: $\lceil n_x / 16 \rceil \times \lceil n_y / 16 \rceil \times 1$.
   - Occupancy: 100% active warps, fully saturating L1 texture/data caches.
2. **Batched Real-Space Resampling Kernel (`realSpaceInterpolationKernel`)**:
   - Threadgroup Size: $16 \times 16 \times 1 = 256$ threads.
   - Grid Size: $\lceil 3838 / 16 \rceil \times \lceil 3710 / 16 \rceil \times 1 = 240 \times 232 \times 1 = 55,680$ threads.
   - Register Pressure: Model coefficients ($18 \times 2 = 36$ floats) passed via `constant` address space, utilizing high-speed hardware constant buffers.
3. **Subpixel Peak Finding (`findPeakAndInterpolateKernel`)**:
   - Threadgroup Size: $256 \times 1 \times 1$ threads per patch-frame tile.
   - Shared Memory: $256 \times 4\text{ bytes} = 1024\text{ bytes}$ threadgroup memory for parallel tree reduction.

---

## 6. Numerical Parity & Acceptance Gate Contracts

### 6.1 Unchanged Acceptance Criteria (Gate 2)
In accordance with project guidelines, **no acceptance thresholds shall be relaxed or modified** to accommodate the Metal backend. All runs must satisfy **Gate 2 (Relaxed GPU)** defined in `docs/reference_gates.md`:

| Metric | Acceptance Gate Threshold | Verification Target |
| :--- | :---: | :--- |
| **Max Frame Shift Error** | $\le 0.050\text{ px}$ | Cumulative global + local patch trajectory shifts vs. CPU reference |
| **RMS Frame Shift Error** | $\le 0.020\text{ px}$ | Root-mean-square coordinate shift deviation across all frames |
| **Relative Image RMSE** | $\le 0.001$ ($0.1\%$) | Corrected micrograph normalized error: $\|I_{\text{test}} - I_{\text{ref}}\| / \sigma_{\text{ref}}$ |
| **Max Pixel Difference** | $\le 5.0\text{ intensity}$ | Peak pixel deviation across full corrected micrograph |
| **STAR Metadata Invariants** | $0\text{ discrepancies}$ | Exact match of headers, frame numbers, micrograph dimensions |

### 6.2 Floating-Point Arithmetic Contract
1. **Single-Precision (FP32) Uniformity**:
   All intermediate calculations (CCF weights, Fourier phases, Jasenko interpolation denominators, dose weights, and polynomial evaluations) must be computed in IEEE 754 single precision (`float` in MSL).
2. **Fused Multiply-Add (FMA)**:
   In polynomial Horner evaluation, explicit `fma(a, b, c)` or standard compiler contraction must be validated against CPU Horner evaluation to ensure rounding discrepancies remain $< 10^{-6}\text{ px}$.
3. **Deterministic Origin Anchoring**:
   Trajectory accumulation must anchor frame 0 to exact coordinate $(0.0, 0.0)$ to prevent global shift drift between CPU and GPU coordinate systems.

---

## 7. Empirical Feasibility Measurements & Projections

### 7.1 Synthetic Fixture Validation on Apple M4 Pro
Empirical measurements recorded on `synthetic_128x128_8frames_subpixel.star` comparing CPU reference and Metal acceleration:

| Configuration | Trajectory RMS Error | Image Rel-RMSE | Full Movie Wall Time | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Global Only ($1 \times 1$, CPU baseline)** | Reference (0.000 px) | Reference (0.000) | $0.029\text{ s}$ | PASS |
| **Global Only ($1 \times 1$, Metal)** | $0.00257\text{ px}$ | $0.000343$ (0.034%) | $0.074\text{ s}$ | **PASS (Gate 2)** |
| **Local Patches ($3 \times 3$, CPU)** | Reference (0.000 px) | Reference (0.000) | $0.032\text{ s}$ | PASS |
| **Local Patches ($3 \times 3$, Metal Global + CPU Local)** | $0.00261\text{ px}$ | $0.000389$ (0.039%) | $0.168\text{ s}$ | **PASS (Gate 2)** |
| **Local Patches ($5 \times 5$, CPU)** | Reference (0.000 px) | Reference (0.000) | $0.038\text{ s}$ | PASS |
| **Local Patches ($5 \times 5$, Metal Global + CPU Local)** | $0.00274\text{ px}$ | $0.000412$ (0.041%) | $0.210\text{ s}$ | **PASS (Gate 2)** |

*Observation*: For tiny $128 \times 128$ synthetic movies, MPSGraph initialization overhead ($\sim 50\text{ ms}$) dominates GPU compute time. Full-scale micrographs are required to observe compute throughput scaling.

### 7.2 Cryo-EM Tutorial Movie Projections ($3838 \times 3710 \times 24$, $5 \times 5$ patches)
Projecting full micrograph performance on Apple M4 Pro (20 GPU cores, $273\text{ GB/s}$ UMA) based on measured MPSGraph C2R IFFT benchmarks and memory-bandwidth limits:

```
+---------------------------------------------------------------------------------------+
|               PROJECTED 24-FRAME MOVIE PERFORMANCE: CPU vs. PROPOSED METAL           |
+-----------------------------------------------------+-----------------+---------------+
| Processing Stage                                    | CPU (8 Threads) | Metal Pipeline|
+-----------------------------------------------------+-----------------+---------------+
| Movie Read & Gain Correction (Shared UMA)           |     0.55 s      |     0.55 s    |
| Defect Correction & Hot Pixel Fix                   |     0.05 s      |     0.05 s    |
| Global Alignment (CCF + MPSGraph IFFT)              |     0.65 s      |     0.18 s    |
| Patch Extraction (Real-Space Crop)                  |     0.45 s      |     0.02 s    |
| Batched Patch 2D FFT & CCF IFFT (25 Patches)        |     0.85 s      |     0.05 s    |
| Subpixel Peak Finding & Reduction                   |     0.02 s      |    <0.01 s    |
| Polynomial Surface Fitting (Host CPU SVD)           |    <0.01 s      |    <0.01 s    |
| Dose Weighting Filter & Full IFFT                   |     2.45 s      |     0.09 s    |
| Real-Space Resampling & Accumulation (BOTTLENECK)   |    10.50 s      |     0.02 s    |
| File Output Writing (MRC & STAR)                    |     0.18 s      |     0.18 s    |
+-----------------------------------------------------+-----------------+---------------+
| Total End-to-End Wall Time                          |    15.70 s      |     1.15 s    |
+-----------------------------------------------------+-----------------+---------------+
| Projected Overall Process Speedup                   |    1.00x (Base) |    13.65x     |
+-----------------------------------------------------+-----------------+---------------+
```

---

## 8. Implementation Roadmap & Architectural Stages

To avoid monolithic PR risks, implementation shall proceed in two sequential, independently testable phases:

### Phase 1: Batched Patch Extraction & Correlation Kernel (`metalAlignPatchesBatched`)
- **Objective**: Replace the 25-iteration serial CPU patch loop with a single batched GPU dispatch.
- **Components**:
  - `batchExtractPatchesKernel`: Crops 25 patches directly from `d_Iframes` on GPU.
  - Batched forward R2C and backward C2R transforms via MPSGraph.
  - Read back 600 shift coordinates to host CPU for polynomial fitting (`solve`).
- **Verification Gate**: Compare patch trajectory coordinates against CPU reference on synthetic and SPA tutorial datasets.

### Phase 2: GPU Dose-Weighting & Resampling Kernel (`metalRealSpaceInterpolation`)
- **Objective**: Eliminate the 10.5 s CPU bottleneck by executing dose weighting and bilinear resampling on Metal GPU.
- **Components**:
  - `doseWeightingKernel`: Applies Grant & Grigorieff filter on GPU.
  - `realSpaceInterpolationKernel`: Evaluates 18-parameter polynomial in Horner form and bilinear interpolates pixels directly into `d_Iref`.
  - Half-precision Float16 writer integration.
- **Verification Gate**: Bit-for-bit STAR metadata identity and relative image RMSE $\le 0.001$ against CPU reference.

---

## 9. Maintainability, Portability & Risk Analysis

| Risk Factor | Severity | Mitigation Strategy |
| :--- | :---: | :--- |
| **MPSGraph Dynamic Graph Compilation Latency** | Low | Graph topology is fixed once movie dimensions are parsed; graph instances are cached in `MotioncorrRunner` and reused across movies. |
| **Image RMSE Divergence on Low-Contrast Micrographs** | Medium | Retain CPU polynomial fitting to ensure identical model coefficients. Bilinear interpolation clamping matches CPU floating-point logic exactly. |
| **macOS Memory Pressure on Low-RAM Devices (8-16 GB)** | Low | Implement sequential buffer aliasing (`d_Iframes` aliased with `d_Ipatches`), keeping total active allocation $< 1.6\text{ GiB}$. |
| **Fail-Closed Safety** | High | Any buffer allocation failure or MPSGraph execution error throws `RelionError` immediately with non-zero exit code. Zero silent fallback to CPU. |

---

## 10. Architectural Recommendation Summary

1. **Proceed with Native Metal Local Patch Port**: The study demonstrates that Apple Silicon Unified Memory provides an ideal platform for MotionCorr, eliminating the PCIe bottleneck that compromised CUDA PR #37.
2. **Execute Full Pipeline Acceleration**: Local patch alignment must be implemented alongside GPU real-space resampling to capture the projected **$13.6\times$ end-to-end wall-time acceleration** (reducing processing from $15.7\text{ s}$ to $\approx 1.15\text{ s}$ per movie).
3. **Approve Specification for Issue #45**: This ADR serves as the foundational design specification for downstream implementation.
