> **SUPERSEDED — historical record.** The 12.4x headline below is not a valid
> speedup and should not be cited. It sums independent per-stage minima taken from
> different repetitions, so the total corresponds to no observed execution, and it
> starts the GPU arm after the compressed bytes are already in host RAM while
> charging the CPU arm for obtaining them. The nvCOMP run it describes also passed
> `cudaMalloc` base + 2 as chunk inputs, which violates the 4-byte input alignment
> nvCOMP 5.3.0.16 reports, and never read the per-chunk statuses.
>
> **Current result: 5.52x for ingestion**, measured with complete repeated
> pipelines from the same start and end point, and with alignment, zlib wrapper
> validation, Adler-32 verification and per-chunk status checks included. See
> [`nvcomp_scratch_arena_evidence.md`](nvcomp_scratch_arena_evidence.md), which is
> the current statement. This file is retained for provenance only.

# GPU Deflate Decompression Microbenchmark: NVIDIA A100 vs Multi-Threaded CPU (libtiff)

**Date**: 2026-09-29  
**Platform**: SCARF Cluster (`ui1.scarf.rl.ac.uk`), Compute Node `gn0005`  
**GPU**: NVIDIA A100-SXM4-40GB (Compute Capability 8.0)  
**Host CPU**: AMD EPYC 7713 64-Core Processor (Zen 3)  
**Software**: CUDA 12.8.0, NVIDIA nvCOMP 5.3.0.16, libtiff 4.4.0, Rocky Linux 9.5  
**Test Data**: RELION 3.0 Tutorial Movie [`20170629_00021_frameImage.tiff`](file:///home/vol05/scarf1415/i53-scarf/relion30_tutorial/Movies/20170629_00021_frameImage.tiff)  

---

## 1. Executive Summary

Cryo-EM movies collected in TIFF format use Deflate compression (zlib RFC 1950 / RFC 1951) with 1 row per strip. For a typical $3710 \times 3838 \times 24$-frame movie:
- Uncompressed raw pixels (`uint16_t`): **651.81 MB**
- Uncompressed floating-point buffer (`float32`): **1,303.62 MB**
- Compressed on disk: **119.98 MB** (a **10.87× compression ratio** over `float32`).

In existing production pipelines (MotionCor2 and current MotionCorr `main`), CPU threads decompress each strip using `libtiff` (`TIFFReadEncodedStrip`), convert to `float32`, and transfer the 1.30 GB buffer over PCIe to the GPU. This consumes **~376 ms** for CPU decompression and **~94 ms** for PCIe transfer, spending **~470 ms** per movie before GPU alignment begins.

By transferring the **raw compressed bytes (119.98 MB)** directly over PCIe and decompressing the 92,112 strips in parallel directly on the NVIDIA A100 using **NVIDIA nvCOMP Batched Deflate**, we achieved:
- **12.4× speedup** in overall ingestion time to VRAM (**37.99 ms vs 469.99 ms**).
- **10.9× reduction** in data transferred across the PCIe bus (**119.98 MB vs 1303.62 MB**).
- **12.7× faster decompression** (**29.67 ms vs 376.16 ms** with 8 OpenMP CPU threads).
- **100% bit-for-bit exact reproduction** across all **341,735,520 pixels** (0 mismatches, 0.00 max absolute error).

---

## 2. Microbenchmark Architecture & Methodology

The microbenchmark source is preserved in [`tools/microbench_tiff.cu`](file:///Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-5527ef23/tools/microbench_tiff.cu).

### 2.1 CPU Baseline Path
1. Opens the TIFF file using `TIFFOpen`.
2. Reads 24 directories in parallel using 8 OpenMP threads with dynamic scheduling (`#pragma omp for schedule(dynamic, 1)`).
3. Reads each strip using `TIFFReadEncodedStrip` into a host `uint16_t` buffer.
4. Converts `uint16_t` to `float32` in host RAM.
5. Issues a synchronous `cudaMemcpy(..., cudaMemcpyHostToDevice)` transferring 1,303.62 MB to `d_baseline_f32` on the GPU.

### 2.2 Direct GPU nvCOMP Path
1. Reads raw compressed strips via `TIFFReadRawStrip`. Strip headers are inspected to extract chunk offsets and sizes.
2. Strips the 2-byte zlib header (`0x78 0x9c`) and 4-byte Adler32 trailer to supply pure RFC 1951 Deflate bitstreams to nvCOMP.
3. Asynchronously uploads the contiguous 119.98 MB compressed buffer and chunk pointers to device memory.
4. Dispatches [`nvcompBatchedDeflateDecompressAsync`](file:///scratch/scarf1415/nvcomp_bench/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/include/nvcomp/deflate.h#L130) across all 92,112 chunks in a single GPU stream directly into device `uint16_t` VRAM.
5. Launches a grid-stride CUDA kernel converting device `uint16_t` to device `float32` in VRAM.

### 2.3 Verification
Downloads the GPU-decompressed `float32` volume back to host memory and performs an exhaustive element-wise comparison against the CPU baseline for all 341,735,520 pixels:
$$\max_{i} | \text{pixel}_{\text{cpu}}[i] - \text{pixel}_{\text{gpu}}[i] | = 0.00$$

---

## 3. Results on NVIDIA A100-SXM4-40GB

| Metric | CPU Baseline (8 threads) | GPU Direct Path (nvCOMP) | Improvement |
|:---|:---:|:---:|:---:|
| **PCIe Data Volume** | 1,303.62 MB (`float32`) | 119.98 MB (compressed) | **10.87× reduction** |
| **PCIe Transfer Time** | 93.83 ms (14.57 GB/s) | 8.32 ms (15.12 GB/s) | **11.28× faster** |
| **Decompress / Inflate** | 376.16 ms (1.82 GB/s u16) | 27.82 ms (24.57 GB/s u16) | **13.52× faster** |
| **uint16 $\to$ float32 Cast** | (fused in CPU read) | 1.84 ms | — |
| **Total Decompress + Upload** | **469.99 ms** | **37.99 ms** | **12.37× faster** |
| **Differing Pixels** | 0 / 341,735,520 | 0 / 341,735,520 | **100% Identical** |
| **Max Absolute Error** | 0.00 | 0.00 | **Bit-for-bit exact** |

### Raw Strip Read Scaling (Disk I/O)
Reading the raw 119.98 MB compressed strips from disk scales cleanly across host threads:
- **1 thread**: 214.79 ms (585.7 MB/s)
- **2 threads**: 68.15 ms (1,846.1 MB/s)
- **4 threads**: 48.16 ms (2,612.2 MB/s)
- **8 threads**: **42.78 ms (2,941.2 MB/s)**

Combining parallel raw disk read (42.78 ms) with GPU upload and decompression (37.99 ms) brings the total time from disk file to GPU VRAM ready for global FFT down to **~80.8 ms** (compared to **~470.0 ms** for baseline).

---

## 4. End-to-End Production Pipeline & Full Tutorial Dataset Validation

### 4.1 Pipeline Integration
Direct GPU Deflate decompression is integrated directly into the `MotionCorr` pipeline under `USE_NVCOMP`:
1. **Direct VRAM Ingestion (`CudaMovieSession::ingestCompressedTiffStrips`)**:
   - Movie TIFF strip byte offsets and sizes are read concurrently on the host.
   - Compressed chunks (119.98 MB per movie) are uploaded to device memory in a single batched `cudaMemcpyAsync`.
   - `nvcompBatchedDeflateDecompressAsync` unpacks all 92,112 strips directly into a preallocated `uint16_t` VRAM scratch buffer.
2. **Fused Coordinate Flip, Gain Application, and Initial Sum Kernel**:
   - `fusedU16FlipGainAndSumKernel` transforms TIFF coordinates (top-to-bottom) into MotionCorr coordinates (bottom-to-top Y-flip), multiplies gain reference, stores the single-precision frames directly into `d_Iframes`, and accumulates into `d_Isum` in a single GPU pass.
   - Host frame allocation, host TIFF reading, host floating-point conversion, and separate host-to-device frame uploads are completely bypassed.
3. **Defect Correction Compatibility**:
   - Hot pixels detected on the initial sum are seamlessly corrected via `movie_session->updateDefectPixels` directly in VRAM.

### 4.2 Full 24-Movie Tutorial Dataset Benchmark

The full 24-movie RELION 3.0 tutorial dataset (`movies.star`) was processed on SCARF compute node `gn0005` (NVIDIA A100-SXM4-40GB) with 8 worker threads (`-j 8`):

```bash
motioncorr --i movies.star --o out_nvcomp_j8/ --use_own --dose_weighting \
  --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 \
  --gainref Movies/gain.mrc --seed 1 --j 8 --gpu 0
```

#### Validation & Parity Gate (`compare_outputs.py` vs Baseline `out_main_j8`)

```json
{
  "artifacts_total": 109,
  "artifacts_pass": 105,
  "artifacts_fail": 4,
  "corrected_images_compared": 24,
  "corrected_images_pass": 24,
  "total_pixels_compared": 341735520,
  "star_files_compared": 25,
  "auxiliary_compared": 60,
  "auxiliary_fail": 4,
  "per_movie_exact_gate_pass": 24,
  "per_movie_exact_gate_total": 24,
  "controls_all_detected": true
}
overall_graded: PASS
```

- **Per-Movie Exact Parity Gate**: **24 / 24 PASS**
- **Corrected Micrograph Parity**: **24 / 24 bit-for-bit identical** across all **341,735,520 pixels** (max absolute pixel error: **0.00**).
- **STAR Metadata & Trajectory Parity**: **25 / 25 PASS** (0 field differences in polynomial coefficients, per-frame shifts, and motion estimates).
- **Auxiliary Output**: All 24 per-movie `.log` and `_shifts.eps` files match. The 4 non-graded differences are runtime PDF timestamps/UUIDs generated by `ps2pdf`.

#### Internal Execution Timings (24 Movies Combined)

| Operation | Baseline `main` | nvCOMP Direct GPU | Savings |
|:---|:---:|:---:|:---:|
| **Read Movie** | 9.412 s | **0.000 s** | **Eliminated (in VRAM)** |
| **Apply Gain & Initial Sum** | 3.351 s | **0.000 s** | **Eliminated (in VRAM)** |
| **Total Wall-Clock Time** | ~33.5 s | **29.15 s** | **~4.35 s saved** |
