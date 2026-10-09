# Batched local patch alignment

Follows `docs/host_device_audit.md` (#156) and `docs/host_device_overheads.md`
(#159). Base: `perf/host-device-overheads` `5fb1b02`.

## What changed

The resident CUDA path used to align the 5×5 local patches one after another.
Each patch ran its own convergence loop with a blocking shift download per
iteration. Now `CudaMovieSession::alignPatchesBatched` aligns the patches in
chunks of K:

1. `preparePatchInVram` (unchanged) writes each patch's grouped Fourier stack
   into its own slot of `BatchedPatchAlignmentWorkspace`. No host waits.
2. `cudaAlignPatchBatchDevice` runs one iteration for every active patch in the
   chunk: the per-patch kernels and C2R plan on that patch's slot, then **one**
   D2H of all patches' shifts. The host applies the unchanged per-patch update
   (`updatePatchShifts`, now shared with the per-patch path) and convergence
   test, then **one** H2D of all phase shifts and one shift kernel per active
   patch.
3. A patch that converged, or reached `max_iter`, is retired at the iteration
   where the per-patch loop would have stopped. It is not launched or shifted
   again.

The runner consumes the results inside its existing patch loop, in patch order.
For each completed patch it writes the patch's log lines (`writePatchBatchLog`)
right after the `Patch (iy, ix)` header, then continues as before. A
non-converged patch therefore still takes the existing host retry with zeroed
shifts, and every later decision in the loop is unchanged.

Blocking shift round-trips per movie on the tutorial data: from 50.3
patch-iterations, each with two D2H and two H2D copies, to 14.3 chunk-iterations
with K=4, each with one D2H and one H2D.

## Exactness

Target and result: byte-identical shifts, verdicts, iteration counts, log lines
and products.

- Every patch runs the same kernels with the same launch geometry and the same
  batch-`n_groups` C2R plan configuration as the per-patch path, in the same
  per-patch order. Only pointers and host waits differ.
- cuFFT batch size was measured first (cuFFT 11.3, A100, 13 geometries). A
  single plan over K·n transforms is **not** bit-identical to batch n: at
  256×256, n=4, K=25, 6 553 091 of 6 553 600 output floats differ (it is
  identical for the other 12 geometries, including the tutorial's 192×192
  CCF). The batch-n plan executed at slot offsets was identical in all 13. The
  batched path therefore uses one batch-n plan, executed once per patch.
  Slots are padded to 512 bytes so each transform sees the same pointer
  alignment as a fresh allocation.
- The CCF geometry and the host update are now single functions used by both
  paths, so they cannot drift.

## Memory and chunk size

The workspace holds K patch stacks plus CCF scratch: 59 MiB per patch at the
tutorial geometry (766×742, 24 groups), 1477 MiB for 25 patches, plus a 3 MiB
cuFFT work area.

K is chosen per movie by `choosePatchBatchChunk`: as many patches as fit in
`cudaMemGetInfo` free memory after a headroom of max(1 GiB, 10% of total),
capped by `MOTIONCORR_PATCH_BATCH` (default **4**). A declined reservation is
retried at K/2 down to 1. The log states the chunk size, free memory, workspace
size and the rise in device memory use. The workspace is released at the
existing checked "release alignment" point, before reconstruction.

The default is 4 because larger chunks did not pay on the tutorial data. The
stage gain was flat above K≈3, while freeing a larger workspace cost more in
"release alignment" (+1.4 ms at K=25) and the following dose weighting ran
slower (+3.1 ms at K=25, none measurable at K=4). The cause of the
dose-weighting slowdown was not established.

`MOTIONCORR_PATCH_BATCH=0` disables the batched path; `=1` runs it one patch
per chunk.

## Fallback and failure ownership

The batched path only computes. Every patch it does not complete takes the
existing per-patch device path, including its #69 retry logic.

| event | behaviour |
|---|---|
| cap 0, unequal patch sizes, no chunk fits | all patches per-patch; reason logged |
| recoverable allocation or plan failure in `reserve` | nothing retained, nothing recorded, pending slot cleared; retry at K/2, then per-patch |
| poisoning code in `reserve` | recorded and thrown; the movie fails, no retry |
| recoverable `preparePatchInVram` failure | workspace released (checked); earlier chunks kept; this chunk and later ones per-patch |
| fatal `preparePatchInVram` failure | decided from the preserved failure state plus pending slot, as in the runner; thrown, no retry |
| any alignment error | thrown, workspace released; the movie fails, as in the per-patch path |
| workspace release failure | reported by the existing pre-reconstruction gate; no products |

## Log

`Patch (iy, ix)`, ` Iteration k: RMSD = …` and
`[CUDA Patch Alignment] completed; converged=…` are byte-identical and in the
same order. The iteration lines are written at emission time, so they inherit
the same stream formatting state as before. The profile block per patch keeps
its line layout. It gains one line saying that the GPU time and VRAM figures
cover all patches aligned together. The per-patch path's `--profile` per-kernel
timings are not produced for batched patches.

## Tests

- `CudaPatchBatch` (hardware): batched vs per-patch on 5 geometries (up to the
  tutorial's 766×742×24), odd patch counts, K=1…n, `max_iter` 1–5, converging
  and non-converging patches, through both the direct entry point and the
  session (preparation into slots included). It compares shifts, verdicts,
  iteration counts, contract log lines and the shifted Fourier payload. It also
  requires coverage: converged, unconverged, and chunks that mix retired and
  active patches. It includes chunk arithmetic, 12 reservation fault controls
  and 5 session fault controls (declined, halved, recoverable prep, exec error,
  fatal prep).
- `CudaPatchBatchMutant_shift_retired` and `CudaPatchBatchMutant_never_retire`:
  CMake writes a copy of `cuda_alignpatch.cu` with one line of the batched loop
  changed and links it in place of the original. The test must report
  mismatches. A target line that is missing or not unique stops the configure
  step.
- `motioncorr_retry_caller` also wraps the batched entry point, so the production
  non-convergence retry is exercised from a batched patch.

## Measured (4GPUs, A100 GPU1, CPUs 64–71, `--j 8`, nvCOMP, 24-movie tutorial)

Base `5fb1b02`; candidate is this branch. Shared host, load1 9–15.

- **Products:** 79 files (24 MRC, 25 STAR, 30 EPS) and 2501 log contract lines
  identical to base for K=4 (default), 25, 7, 1 and the disabled path.
- **Native CTest:** all tests pass, including the three new ones.
- **Per stage, `--profile`, ms/movie, steady state.** As shipped, `--profile`
  turns on the per-patch path's per-kernel event syncs, which the batched path
  does not have. The shipped binaries therefore credit batching with removing
  that telemetry: patch alignment 44.3 → 31.3 ms (K=25, 4/4 pairs). For a fair
  comparison, measurement-only builds of both arms with that timing forced off,
  4 rotating rounds:

  | arm | patch alignment | release alignment | dose weighting |
  |---|---|---|---|
  | base (per-patch) | 37.44 | 0.75 | 48.19 |
  | K=1 | 34.35 (−3.09) | 0.86 | 47.67 |
  | K=4 (default) | 32.57 (−4.87) | 1.18 (+0.44) | 48.17 |
  | K=25 | 31.44 (−5.99) | 2.18 (+1.43) | 51.27 (+3.07) |

  The remaining stage time is mostly GPU work. The audit's traced figure was
  ~25 ms/movie of kernels and copies, so larger chunks have little left to
  remove.
- **Unprofiled paired wall**, base vs K=4, 10 interleaved pairs: no measurable
  change. Excluding the first (cold) pair, the median paired delta is
  +0.006 s per 24-movie run (mean −0.007 s, SD 0.12 s), candidate faster in 4/9.
  The ~4.4 ms/movie net stage saving (~0.1 s per run) is not visible in wall at
  this sample size.
