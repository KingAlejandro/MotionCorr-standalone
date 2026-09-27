# Issue 74 — Optional CUDA profiling overhead: synchronization audit

Base commit `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26` (equal to `origin/main` at fetch
time on 2026-09-27; `origin/integrate/cuda-stabilization` is 9 commits behind it and was
not used as a base). Experimental core #82 and evidence #81 are merged.

This is the "audit which events/synchronizations are profiling-only versus
correctness/error checks" step. It is a reading of the merged source, not a measurement.

## 1. The backend markers already exist and are reused unchanged

Issue #74 item 1 (a cheap completed-backend marker independent of profiling) is already
implemented and merged. Nothing here re-implements it.

| marker | emitted by | consumed by |
|---|---|---|
| `Using CUDA acceleration on GPU device <N> for global alignment.` (stdout) | `src/motioncorr_runner.cpp:264` | `tools/run_known_motion_gates.py:65` |
| `[CUDA Global Alignment] completed; converged=<yes\|no>` (per-movie log) | `src/acc/cuda/cuda_alignpatch.cu`, after the profile block | `tools/run_known_motion_gates.py:66` |

`backend_evidence()` in `tools/run_known_motion_gates.py` requires **both** when `--gpu`
is given, and when `--gpu` is absent it *rejects* a run in which either marker appears —
that is the CPU-masquerade control, and it works in both directions.

Both markers sit outside the `[CUDA ... Profile]` block, so the profile block is not load
bearing for the execution witness. That is what makes this issue safe to attempt at all.

## 2. Classification of every event and synchronization in the two owned files

### `src/acc/cuda/cuda_alignpatch.cu`, `cudaAlignPatchDevice`

Called once per movie for global alignment and once per patch for patch alignment
(`5x5 = 25` patches in the tutorial configuration), up to `max_iter` iterations each.

| site | kind | verdict |
|---|---|---|
| `ev_start_total` / `ev_stop_total` + one `cudaEventSynchronize` | one per call | **correctness-relevant.** This is the stage's single checked completion boundary: it is `HANDLE_ERROR`-wrapped and it runs before the completion marker is printed. Kept unconditional. |
| `ev_start_kernel` / `ev_stop_kernel` + `cudaEventSynchronize` after reference+CCF | 1 per iteration | profiling-only |
| same pair, after peak finding | 1 per iteration | profiling-only |
| same pair, after the Fourier shift kernel | 1 per iteration when `n_frames > 1` | profiling-only |
| `ev_start_cufft` / `ev_stop_cufft` + `cudaEventSynchronize` | 1 per iteration | profiling-only |
| `ev_start_d2h` / `ev_stop_d2h` + `cudaEventSynchronize` | 1 per iteration | profiling-only |
| `LAUNCH_HANDLE_ERROR(cudaGetLastError())` after each launch | 4 per iteration | **correctness.** Unchanged. |
| blocking `cudaMemcpy` D2H of candidate shifts | 2 per iteration | **correctness.** This is the real ordering the iteration depends on: the host cannot read shifts early, and a sticky kernel fault from anything enqueued earlier in the iteration surfaces here, error-checked. Unchanged. |
| blocking `cudaMemcpy` H2D of `d_shiftx`/`d_shifty` | 2 per iteration | **correctness.** Unchanged. Also the reason the old H2D label was wrong — see §4. |

So per call the profiling-only synchronizations are `5 x iterations` (4 when
`n_frames == 1`), against exactly one synchronization that is actually required.

### `src/acc/cuda/cuda_realspace_dw.cu`, `cudaDoseWeightAndInterpolateDevice`

| site | kind | verdict |
|---|---|---|
| `ev_start_total` / `ev_stop_total` + one `cudaEventSynchronize` | one per call | **correctness-relevant**, same argument as above. Kept unconditional. |
| `ev_*_dw`, `ev_*_cufft`, `ev_*_interp` + their `cudaEventSynchronize` | 3 per frame | profiling-only |
| `LAUNCH_HANDLE_ERROR` after each launch | 2 per frame | **correctness.** Unchanged. |
| blocking `cudaMemcpy` D2H of `d_Isum` | 1 per call | **correctness.** Unchanged. |

3 profiling-only synchronizations per frame, so 72 for a 24-frame movie.

### `src/acc/cuda/cuda_realspace_dw.cu`, `cudaRealSpaceInterpolationDevice`

Only the total pair. Nothing profiling-only to make optional; left alone apart from a
label correction.

### Not touched

`src/acc/cuda/cuda_movie_session.cu` holds the session per-frame workspace
synchronization and the `cudaDeviceSynchronize()` completion/error boundaries
(lines 325, 433, 587, 595, 617, 626, 645). Those are out of scope for this issue and are
unmodified. `src/motioncorr_runner.cpp` TIMING tags, the TIFF/MRC readers, the gain/sum
loops and the scheduler are untouched (#85 / #53 overlap).

## 3. Why removing the profiling-only synchronizations cannot change results

1. **Ordering.** Everything runs on the default stream, which this change does not alter.
   Stream order already guarantees that frame `i+1`'s copy into `d_Fframe` follows frame
   `i`'s `cufftExecC2R` read of it, that frame `i+1`'s inverse FFT write to `d_Iframe`
   follows frame `i`'s interpolation read, and that iteration `n+1`'s kernels follow
   iteration `n`'s. No new streams, batches or allocations are introduced.
2. **Reduction order.** `d_Isum` accumulation stays a sequential in-stream chain of the
   same kernels in the same order, so the floating-point reduction order is identical.
   No arithmetic is touched.
3. **Host reads.** Every device-to-host download is a blocking `cudaMemcpy` to pageable
   memory, so the host still cannot observe an unfinished result.
4. **Error detection.** Launch-configuration faults are still caught by the unchanged
   `LAUNCH_HANDLE_ERROR(cudaGetLastError())` immediately after each launch. A kernel
   execution fault is sticky and is returned by the next CUDA call, which is an
   error-checked blocking copy within the same iteration/frame, and in the worst case by
   the always-on total-event synchronization before the stage prints its completion
   marker. Detection granularity coarsens from per-substage to per-stage; detection
   itself does not go away, and no failed run can print a completion marker.

The honest limit of this argument: it is a source-level argument. It is not evidence.
The measurement plan in `plan.md` is what has to show that both modes produce identical
pixels, headers, STAR and trajectories.

## 4. Label corrections (issue #74 item 3)

Three labels overstated what was measured. All three are corrected in place, keeping the
existing key spelling byte-identical so that the tools which already parse them keep
parsing them.

| line | was | problem |
|---|---|---|
| alignment profile | `Host-to-Device transfer time: 0.00 ms (Resident VRAM)` | false. Two H2D shift uploads happen per iteration when `n_frames > 1`. Now reports that the figure is not measured and states how many uploads and how many bytes actually occurred. |
| alignment profile | `Peak GPU memory allocated:` | this is the sum of the buffers this one call allocates, not a process peak. Qualified as such. |
| alignment profile | `Buffer VRAM:` | includes `sz_fframes`, which the caller owns and this function does not allocate. Qualified as such. |
| both reconstruction profiles | `Peak VRAM:` | same function-scratch-vs-process-peak overstatement. Qualified as such. |

## 5. Pre-existing finding, reported not fixed

Two legacy validators already fail to match the current log format and were therefore
already dead as parsers, before this change:

* `tools/run_cuda_patch_validation.py:57-67` — its concatenated regex requires
  `Host-to-Device transfer time: <num> ms` to be followed only by whitespace, but the
  merged source has emitted `0.00 ms (Resident VRAM)` since before this branch.
* `tools/run_cuda_reconstruction_validation.py:56-64` — expects
  `[CUDA Reconstruction Profile]`, `Analytical Dose Weighting:`, `cuFFT Inverse C2R:`,
  `Real-space Interpolation & Accumulation:` and `Total Reconstruction Time:`; the merged
  source emits `[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]`,
  `Dose Weighting Kernel:`, `cuFFT C2R Execution:`, `Interpolation & Accum:` and
  `Total DW Reconstruction Time:`.

Neither is used by CI (`.github/workflows/ci.yml` compiles CUDA but runs no CUDA
hardware validation) and neither is in this issue's ownership, so both are left as they
are and reported here instead.

The parsers that *are* live keep working:
`tools/run_known_motion_gates.py` (markers only, unchanged),
`tools/run_cuda_synthetic_regression.py:226` (anchored `Total GPU alignment time:` line,
which is still numeric in both modes and had no trailing text added), and
`tools/compare_cuda_dataset.py` (per-field unanchored regexes, tolerant of the added
qualifiers; its detailed fields correctly become absent when the detailed events are off,
because in that mode they genuinely were not measured).

`tools/compare_motioncorr.py`, which decides exact-output equality, reads MRC headers and
data, STAR files and trajectories. It does not read the per-movie log, so none of these
log-text changes can affect an exactness verdict.
