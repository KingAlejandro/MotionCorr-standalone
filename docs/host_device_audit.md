# Host/device placement and transfer audit (single-GPU CUDA path)

*Host* means the CPU and system RAM; *device* means the GPU and its memory.

This note records which part of each movie runs on the GPU and which on the CPU,
every crossing between them, and why each crossing exists. It is an analysis,
not a change. Measured figures are labelled; savings are estimates until a
change is measured with `--profile` under matched conditions.

## Source and method

- Source: main `af64101` (#153 merged), plus the measurement-only `--profile`
  (#154) and host buffer reuse (#155) where stated.
- Data: the 24-movie RELION tutorial (3838×3710, 24 frames, uint16 Deflate TIFF),
  `--use_own --dose_weighting --patch_x 5 --patch_y 5 --gainref --j 8 --ingest nvcomp`.
- Host: 4GPUs VM, A100-80GB PCIe GPU0, CPUs 96–103, CUDA 12.8, nvCOMP 5.3,
  Release sm80. The VM is shared (load1 21–33 from another user) and uses the
  `acpi_pm` clocksource, so every `clock_gettime` is slow.
- Device side: an Nsight Systems `--trace=cuda,nvtx` capture of the stock binary.
  `--profile` emits NVTX ranges, so copies, kernels and runtime calls are
  attributed to stages without source patching.
- Host side: unprofiled `--profile` runs. Nsight inflates host time in
  call-heavy stages by about 2×: patch alignment is 118 ms per movie traced and
  ~50 ms untraced. Use `--profile` to judge changes, not traced per-call times.

## Summary

The resident CUDA path already keeps the whole movie in device memory from
ingest to the final image. Decompression, gain, sum, forward and inverse FFTs,
correlation and peak search, phase shifts, interpolation and dose weighting are
all GPU kernels. The CPU keeps control logic, a few contract-bound computations,
and a large number of small blocking waits.

Steady state with #155 (unprofiled, about 312 ms per movie): GPU kernels plus
copies account for about 154 ms. The rest is CPU-only time while the GPU waits.

## Per-stage audit

Per movie. Wall and GPU columns come from the traced run, except patch
alignment, whose untraced wall is shown.

| stage | wall / GPU ms | crossings | why |
|---|---|---|---|
| read compressed TIFF + device ingest | 115 / 41 | 131 MiB compressed H2D; 4 pointer/size tables (92k strips) H2D; status, length and Adler-32 D2H (1.4 MiB); 3 stream syncs | **required:** the GPU cannot read files. **required:** fail-closed integrity verdict before the movie is used (#134, #151). **removable:** tables built on CPU and uploaded; read, copy and decode run serially with no overlap |
| allocate host sum | 15 / 0 | none (57 MB CPU array) | **removable:** allocated every movie; unread on the resident path unless the hot-pixel exactness guard falls back to CPU statistics |
| hot pixels | 24 / 0.3 | reduction partials and sparse hit list D2H; 6 `cudaFree` | **required:** CPU decides whether the GPU statistics are within the exactness guard, else recomputes on CPU. **CPU by design:** premask copy, full 14 MB mask scan, reachability walk. **removable:** scratch allocated and freed per movie |
| fix defects | 2 / 0 | neighbour samples D2H, replacements H2D | **required:** replacements come from `rand()`/`rnd_gaus()` in a fixed CPU order (RELION-compatible RNG stream); moving it changes products |
| global forward FFT | 26 / 21 | 25 device syncs | **removable:** one FFT per frame with a device-wide sync after each, because R2C and C2R share one single-frame work area |
| global alignment | 18 / 7 | per-iteration shifts D2H and phase shifts H2D; ~15 event syncs | **required by current design:** CPU applies the update, tests convergence and logs RMSD. **removable:** 4 event syncs per iteration only time kernels for the log |
| allocate reconstruction | 6 / 0 | none (57 MB CPU buffer zeroed) | **removable:** zeroed on CPU, then fully overwritten by the GPU result |
| global inverse FFT | 25 / 21 | 1.3 GB D2D; 24 device syncs | **removable:** C2R overwrites its input, so each frame is copied to scratch to keep the Fourier frames for dose weighting; synced per frame |
| patch alignment | ~50 / 25 | ~100 D2H and ~160 H2D small copies; ~277 event syncs; ~250 blocking `cudaMemcpy` | **required by current design:** the same CPU-driven convergence loop per patch. **removable:** 25 independent patches run sequentially; ~11 timing syncs per patch; group tables uploaded per patch |
| fit polynomial | 2 / 0 | none | **CPU by design:** 18-parameter double-precision least squares over ~600 observations; must match CPU `solve()` exactly |
| dose weighting + reconstruction | 61 / 39 | 1.3 GB D2D; 54 MiB final image D2H; 74 event syncs; 5 `cudaFree` | **required:** the final image is written to MRC by the CPU writer. **removable:** in-place weighting needs a per-frame scratch copy; 3 timing syncs per frame; buffers allocated per movie; image copied to unpinned memory |

Kernel counts per movie from the trace: ingest 3, hot pixels 6, forward FFT 169,
global alignment 18, inverse FFT 168, patch alignment 458, dose weighting 217.

## Why work remains on the CPU

1. **Files.** Compressed bytes must cross from disk to the device. That crossing
   is unavoidable, but it can overlap with decoding.
2. **Exactness contracts.** Defect replacement consumes the CPU RNG stream in a
   fixed order. The polynomial fit must match CPU double-precision `solve()`.
3. **Fail-closed checks.** The nvCOMP integrity verdict and the hot-pixel
   statistics guard are decided on the CPU, with CPU fallback when a guard fails.
4. **CPU-driven alignment loops.** Shifts return to the CPU every iteration for
   the update, the convergence test and RMSD logging. This is the largest source
   of round-trips. It is a design choice: the loop could run on the device if
   the float/double update order and the log lines are reproduced exactly.

## Round-trips that are habits, not dependencies

- **Timing-only event syncs**, about 400 per movie (alignment, patches, dose
  weighting). Removing them alone was measured as a no-go on
  `experiment/post128-alignment-sync`: three pairs, median 0.2 s slower. The
  data dependency still serialises each step. They are worth removing only
  together with batching.
- **Sequential patches.** 25 independent patches give about 250 blocking
  round-trips. Batched, it is one round-trip per iteration for all patches.
- **Serial ingest.** Read, then copy, then decode, with CPU-built pointer tables.
- **Two 1.3 GB device-to-device copies** per movie, caused by in-place C2R and
  in-place weighting.
- **Per-frame device syncs** in both global FFTs, caused by the shared
  single-frame work area.
- **Unneeded host buffers:** the host sum and the zeroed reconstruction buffer.
- **About 30 `cudaMalloc`/`cudaFree` pairs** per movie; `cudaFree` also
  synchronises the device.

## Target shape

Per movie, three crossings remain:

1. compressed bytes in, overlapped with the previous chunk's decode;
2. one small verdict back: integrity, hot-pixel exactness, and the shifts the
   log and polynomial fit need;
3. the final image out to the writer, overlapped with the next movie.

Defect replacement (2 ms per movie) stays on the CPU to keep the RNG contract.
The removable items above cover most of the ~158 ms per movie of CPU-only time.
A rough, unmeasured estimate is about 200 ms per movie, from ~312 ms.

## Suggested order

1. Skip the unneeded host buffers, and record timing events only under
   `--profile` (low risk).
2. Split ingest into sub-stages in `--profile`, then pipeline chunks and build
   the strip tables on the device.
3. Batch patch alignment: all patches per iteration, one shift download,
   converged patches masked. Prove batched cuFFT gives byte-identical results,
   or fall back to smaller groups.
4. Dose weighting out of place, with scratch reused across movies and the final
   image copied to pinned memory.
5. Fixed per-run costs that matter for multi-GPU: first-movie context, module
   loading and pinned allocation (~0.87 s), and the end-of-run PDF (~0.8 s).

A no-code alternative to measure in parallel: two workers per GPU, so one
worker's CPU time overlaps the other's GPU time.

Every step is gated on byte-identical products, the existing fault-injection
suites, and an interleaved `--profile` A/B.
