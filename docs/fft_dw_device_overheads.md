# Global FFT / inverse FFT / dose weighting: device-side overheads (task C)

Branch `perf/taskC-fft-dw-device`, stacked on `perf/host-device-overheads` (`5fb1b02`).
All numbers were measured on `4GPUs` (GPU3, CPUs 80-87, `--j 8`, nvCOMP, 24-movie
tutorial set, A100 80GB PCIe, CUDA 12.8 / cuFFT 11.3.3, shared host, load1 9-13).
Anything not listed under MEASURED was not run.

## Changes (default path, products byte-identical)

| commit | change |
|---|---|
| `6dbf1da` | **Dose weighting out of place.** `applyDoseWeightKernel` reads the resident Fourier frame and writes the weighted frame into the C2R input scratch (the session's existing `d_inverse_tile`). The per-frame 57 MB D2D copy (1.3 GB/movie) is gone. Same expression, one IEEE multiply per component; only the source pointer differs. In session mode the four other reconstruction buffers (accumulator, real frame, normalization plane, doses) share one `cudaMalloc` and one checked `cudaFree`, instead of four of each. |
| `8d8b569` | **No per-frame device syncs in the global forward and inverse FFT** (25 + 24 `cudaDeviceSynchronize`, now one each). Execution errors surface at one checked drain after the last launch; a failed launch drains first, so queued work finishes and an asynchronous error is attributed to this stage. |
| `10521a8` | Tests (below). |

Unchanged on purpose: the non-resident fallback `cudaDoseWeightAndInterpolate` and any call
to `cudaDoseWeightAndInterpolateDevice` without a `DoseWeightScratch` keep their original
five per-call allocations and cleanup, so the issue #69 failure-state semantics and the
`dw-release-fatal` production control are untouched.

## Idea-by-idea

1. **Out-of-place dose weighting: implemented**, see above.
2. **Inverse-FFT copy: kept (proved necessary).** `docs/fft_dw_device_overheads/c2r_probe.cu`
   runs a 2-D batch-1 C2R with a *separate* work area (the same plan and work-area setup as the
   session) and compares the input before and after. MEASURED: the input is overwritten
   in every word (7,123,200 of 7,123,200 for 3838x3710; also 4096x4096, 512x512, 3710x3838,
   7676x7420, 35x29, 32x24). That agrees with the cuFFT documentation (C2R may overwrite its
   input), so the copy stays. Fusing the copy into a kernel that already reads the frame is not
   possible in the inverse FFT: nothing reads it before the transform. In dose weighting the
   copy is fused (idea 1).
3. **Scratch reuse: partly.** `d_inverse_tile` is reused as the dose-weighting C2R input.
   The other four buffers are one allocation per movie instead of four. A fully
   session-resident block was written first, but then the helper no longer frees anything, so the
   production `dw-release-fatal` control (and the checked-cleanup path it witnesses) could not fire. It
   was dropped in favour of keeping a checked free inside the helper.
4. **Forward FFT syncs: implemented as a separate commit** and measured, rather than recorded
   as a no-go, because it was cheap and the tests make it safe. It brings no wall gain (below),
   as `experiment/post128-fft-sync` found. The freed host time is not used for anything.
5. **Relaxed-exactness alternatives (batched C2R, fused weight+C2R): UNRUN.** Not attempted;
   the default path is exact and these would need the CPU-gate comparison the brief asks for.

## Correctness evidence

MEASURED (head `10521a8`, GPU3):

- **Products, 24 movies, base vs candidate (also vs the dose-only arm): byte-identical.** MRC payloads (bytes 1024+) and header bytes 0-223 (24 files), STAR (25) and EPS (30),
  path-normalised: **0 differences**; no non-timing line differs in the 24 per-movie logs. (Round-1 trees of campaigns w1 (dose-only and dose+fft arms) and w2 (head); w3 trees were not kept.)
- **Native ctest 55/55**, including `CudaDoseNormalization`, `CudaDoseSessionPlan`,
  `CudaFaultMatrix`, `CudaPatchWorkspace`, `GlobalIfftElision`,
  `CudaPreprocessingFailurePaths` and `CudaNvcompReconstructionFailures`.
- Oracles in `tests/cuda_dose_normalization.cpp` (each fails without the behaviour):
  - out-of-place kernel byte-identical to the frozen original in-place kernel, source frame untouched, destination poisoned first so an unwritten element cannot pass (1365 frames);
  - 100 reconstructions vs the frozen original frame loop; `frame_copies == 0` (was `count`); and that the first weight launch follows the checked normalization completion;
  - session mode: `allocations == 1 && frees == 1` (was 5/5), C2R reads the caller's tile, stale tile bytes overwritten, resident frames intact, two consecutive calls reuse the tile;
  - **negative controls:** the same harness sees 5 allocations without a scratch, and a mis-ordered C2R input is *detected* by the byte comparison;
  - block-allocation fault: refused, original cause kept, nothing freed that it did not own, caller output untouched;
  - `--case fft`: forward and inverse bytes equal an oracle that keeps the per-frame wait, exactly **one** device wait per transform, Fourier frames preserved by the inverse, exec failure at frame 3 (both directions) refused, cuFFT status recorded, queue drained once, session not poisoned, no leak; perturbed-input negative control detected.
  - **Compiled negative control:** the same test source built against the pre-change session code fails with "forward FFT must wait for the device exactly once (per-frame waits are back)".
- Failure semantics: the borrowed late-fatal cleanup and allocation-5 fault cases still hold for the call without scratch; session mode has one block.

UNRUN: behaviour under a genuinely poisoned GPU context (only injected return codes, as before).
The 55/55 ctest is for head `10521a8`; the docs-only commit after it changes no code.

## Performance

### Nsight (3 movies, steady state per movie; traced wall is inflated, GPU times are not)

| stage | base wall / GPU | candidate wall / GPU | what changed |
|---|---|---|---|
| global fft | 25.4 / 21.5 ms | 22.1 / 21.6 ms | 25 syncs (18.5 ms host in them) -> 1 sync (14.6 ms) |
| global ifft | 24.0 / 21.8 ms | 22.3 / 21.9 ms | 24 syncs (15.1 ms) -> 1 sync (13.9 ms) |
| dose weighting | 72.9 / 39.9 ms | 63.1 / 31.5 ms | D2D copies 24 x 57 MB = 1.63 ms GPU -> 0; `cudaMalloc`/`cudaFree` 5+5 -> 1+1 (1.30+1.17 ms -> 0.54+0.39 ms host) |

The GPU time inside the FFT stages is unchanged (cuFFT dominates); what went away is host
waiting. In dose weighting the D2D copy was only 1.63 ms of GPU time (1.3 GB at about
800 GB/s), so that is the real kernel-side saving. The rest of the 8.4 ms GPU difference in the table
is the final-image D2H (CUPTI memcpy kind 2: 11.4 ms in the base trace, 4.8 ms in the candidate trace),
which this change does not touch; it is pageable-memory variance between two 3-movie traces and is
not a result. Each trace is a single 3-movie run; treat the wall numbers as indicative only.

### Per-stage `--profile` (MEASURED, mean over 23 steady movies, median of 6 interleaved runs per arm; ms/movie)

`base` = `5fb1b02`; `dose` = `6dbf1da`; `+fft` = `8d8b569`.

| stage | base | dose | +fft | base -> +fft |
|---|---|---|---|---|
| global fft | 22.49 | 22.48 | 21.81 | **-0.68** |
| global ifft | 23.83 | 23.74 | 22.07 | **-1.76** |
| dose weighting | 46.25 | 43.91 | 44.55 | **-1.70** (dose arm alone -2.34) |
| steady total | 254.24 | 250.55 | 249.52 | **-4.7** |

Run-to-run spread within an arm is mostly one slow run (base 305 ms total in run 4), not a
trend. The three stages together save about 4 ms per movie (about 1.9% of the steady total).
The `Total DW Reconstruction Time` log line (unprofiled, median of steady movies, 6 rounds):
base 34.85-36.38 ms, dose arm 32.0-33.5 ms.

### Unprofiled wall (MEASURED, 24 movies, interleaved pairs, order alternating)

| campaign | arm | pairs | paired saving median | mean | faster |
|---|---|---|---|---|---|
| w1 | dose-only (`6dbf1da`) | 6 | -0.02 s | -0.35 s | 2/6 |
| w1 | dose + fft (`8d8b569`) | 6 | -0.16 s | -0.50 s | 1/6 |
| u1 (log line only, no `--profile`) | dose + fft | 6 | +0.35 s | +0.37 s | 6/6 |
| w2 | head (`10521a8`) | 10 | +0.38 s | +0.42 s | 6/10 |
| w3 | head (`10521a8`) | 10 | +0.03 s | +0.14 s | 7/10 |
| pooled w1+w2+w3 (head code) | | 26 | +0.025 s | +0.10 s | 14/26 |

**Wall time is not resolved.** The base arm is bimodal under the shared host (about 7.6 s
or about 8.3 s) and each campaign's mean is driven by a few slow rounds that landed on one arm
or the other. On the 17 pairs where neither arm was disturbed the paired median is -0.012 s.
The stage-level saving (about 0.1 s per 24 movies) is below that noise. No wall-time gain is
claimed; this matches `experiment/post128-fft-sync` and `docs/host_device_overheads.md`.

### VRAM (MEASURED)

| | base | candidate |
|---|---|---|
| `Peak VRAM` log line (dose helper only) | 190.15 MiB | 135.81 MiB |
| whole-process `nvidia-smi` peak (100 ms sampling, 6 runs) | 3521 MiB (all 6) | 3391-3485 MiB |

The candidate uses less VRAM: the C2R input tile is the session's existing one, so session
mode allocates 136 MiB instead of 190 MiB per movie. No new persistent memory.

## Limitations

- No wall-time claim. Stage savings are about 4 ms/movie, below the noise of the shared host.
- The forward-FFT sync removal does not use the freed host time; it is shipped as a tested,
  exact change with a small per-stage gain, not as a wall win.
- GPU0 paired timing is left to the coordinator.
- The last D2D copy that remains is in the global inverse FFT (necessary, proved above).
