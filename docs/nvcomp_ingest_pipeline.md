# Pipelined nvCOMP Deflate ingest

`CudaMovieSession::ingestCompressedTiffStrips` (`src/acc/cuda/cuda_movie_session.cu`)
decodes a Deflate TIFF movie on the GPU in chunks of frames. Before this change it
read, uploaded, decoded and verified the whole movie as one batch.

## Design

- **Chunks and slots.** The movie is split into chunks of `chunk_frames` frames.
  With more than one chunk, two slots alternate. While the GPU copies and decodes
  chunk k from slot `k % 2`, the host reads chunk k+1 into the other slot. A copy
  stream and a compute stream let the H2D copy of chunk k+1 overlap the decode of
  chunk k. Events `h2d_done[j]`, `comp_free[j]` and `status_ready[j]` order them.
  A single chunk uses one slot.
- **Chunk size.** The default is `ceil(n_frames / 4)`, which is 6 for the 24-frame
  tutorial movies. `MOTIONCORR_NVCOMP_CHUNK_FRAMES=<n>` overrides it, and an
  invalid value logs a warning. The requested size is halved (for example
  6 → 3 → 1) until both slots fit the arena borrowed from the pre-FFT Fourier
  buffer and the pinned cap.
- **Pinned staging.** The payload and strip tables live in a worker-lifetime
  pinned pool, laid out by `pinnedChunkLayout` in `cuda_deflate_layout.h`. The pool
  reserves 12.5% headroom in 32 MiB granules and is never shrunk.
  - `MOTIONCORR_NVCOMP_PINNED_MAX_MB` caps it (default 256 MiB). The cap bounds the
    chunk size the way the arena does.
  - A worker that already holds more pinned memory than the cap declines the
    nvCOMP path instead of reporting a budget it is not inside.
- **Span reads.** When a frame's strips are contiguous in the file, one `pread`
  reads the whole span. `spreadPackedStrips` then moves the strips in place into
  their aligned slots. This gives the same bytes as one `TIFFReadRawStrip` per
  strip. Non-contiguous frames still use `TIFFReadRawStrip`.

### Fail-closed contract (#134, #151)

No decoded byte reaches `d_Iframes`/`d_Isum` before its chunk passes all checks:

1. The host waits for `status_ready` of chunk k.
2. It checks nvCOMP status and decoded length for every strip of the chunk, and
   only then the Adler-32 values. A checksum mismatch therefore cannot mask a
   decoder failure later in the same chunk.
3. Only after both checks does it launch `fusedU16FlipGainAndSumKernel` for chunk k.

If chunk k fails, the function returns false. Earlier chunks have already been
summed, but nothing is published:

- **Verification failure.** No CUDA error is recorded, so `ingestMovie` reports
  NotApplicable.
  - Under `--ingest nvcomp`, the movie fails.
  - Under `--ingest auto`, the host reader runs, and `applyGainDefectsAndSum`
    overwrites `d_Iframes` and `d_Isum` in full.
  - This matches the old batch code, which also converted earlier batches before
    a later batch failed.
- **CUDA error.** The ingest reports RecoverableFailure, as before.

### Slot reuse

| resource of slot j | rewritten only after |
|---|---|
| host payload and tables | `cudaEventSynchronize(h2d_done[j])` of the chunk that last used it |
| device payload and tables | `comp_free[j]`, waited on by the copy stream |
| device decode output | chunk k's gain kernel; the compute stream orders chunk k+2's decode after it |
| pinned readback | chunk k's verification; chunk k+2's D2H is enqueued after it |

## Tests

- `DeflateLayout` (`tests/test_deflate_layout.cpp`) checks:
  - the span-then-spread read gives the same bytes as direct per-strip placement;
  - the pinned layout regions are disjoint and inside the reserved total;
  - chunk-size parsing and defaults.
- `CudaNvcompAcceptanceFailures` (`tests/run_nvcomp_acceptance_controls.py`) runs
  the real binary on a 6-frame fixture. A test shim edits the descriptor readback
  of one chosen chunk, and counts gain-kernel launches. The gain-launch count is
  the negative control for verify-before-consume: a refusal at chunk c must show
  exactly c launches.
  - Products are identical at chunk sizes 2, 1 and 6. The fixture arena does not
    fit a 6-frame request, so it halves to 1.
  - Status and size refusals at chunk 0 happen before any Adler check, with 0
    gain launches.
  - Status refusal at chunk 1 and Adler refusal at chunk 2 (with 1 and 2 gain
    launches):
    - under the pin: no products;
    - under `--ingest auto`: host-reader products identical to healthy.

## Measurements

All results here are MEASURED, at the following setup:

| item | value |
|---|---|
| host and hardware | 4GPUs, GPU2 (A100 80GB PCIe, `GPU-063e5232-…`), CPUs 72-79 (EPYC 7452) |
| dataset | the 24 tutorial movies in `/home/alex/mc-perf-20261001/data` |
| options | `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp` |
| base | `5fb1b02` |
| base with sub-stage profiling | `3fab591` |
| candidate | `c4dad3b` |
| build | Release, `-DCUDA=ON -DUSE_NVCOMP=ON`, nvCOMP 5.3.0.16 |

### Correctness

- Native CTest at `c4dad3b` on GPU2: **55/55 passed**. This includes
  `DeflateLayout`, `NvcompGuards`, `CudaAdler32`, `CudaNvcompAcceptanceFailures`,
  `CudaNvcompReconstructionFailures` and `CudaPreprocessingFailurePaths`. All 9
  acceptance-control rows pass.
- 24-movie product identity, base vs candidate. The comparison covers:
  - the full file set;
  - MRC header bytes 0-223 and every byte from offset 1024;
  - STAR, EPS and LST files, with the output root normalised.

  Logs and PDFs are not compared (they contain timings and dates).

  | candidate arm | witnessed chunking | result |
  |---|---|---|
  | default | `chunk=6/24 x 4, slots=2` in 24/24 movie logs | identical |
  | `MOTIONCORR_NVCOMP_CHUNK_FRAMES=1` | `1/24 x 24, slots=2` | identical |
  | `MOTIONCORR_NVCOMP_CHUNK_FRAMES=24` | `24/24 x 1, slots=1` | identical |
  | `--ingest compact` (sanity) | host reader | identical |

### Ingest sub-stages under `--profile`

Four interleaved runs per arm. Each value is the median per movie over the 23
steady movies of each run, then the median across runs, in ms.

| sub-stage | base `3fab591` | candidate | delta |
|---|---:|---:|---:|
| stage: session and device ingest | 78.94 | 75.94 | −3.00 |
| device ingest | 70.12 | 67.84 | −2.28 |
| — strip read | 26.35 | 51.97 | +25.62 |
| — status D2H and sync | 25.64 | 9.34 | −16.30 |
| — H2D submit | 11.46 | 0.39 | −11.07 |
| — gain/sum/cast | 2.00 | 0.10 | −1.90 |
| — tag scan | 1.96 | 2.54 | +0.58 |
| — setup | 1.17 | 0.87 | −0.30 |
| — decompress submit, verify, slot wait, drain | 0.24 | 1.68 | +1.44 |
| session setup | 8.37 | 8.15 | −0.22 |

Chunk-size sweep on the candidate, one profiled run each (ms per movie):

| chunk frames (chunks) | device ingest | strip read | status sync |
|---|---:|---:|---:|
| 24 (1, one slot) | 59.80 | 18.08 | 36.04 |
| 12 (2) | 50.67 | 26.70 | 17.53 |
| 8 (3) | 59.68 | 41.29 | 12.00 |
| 6 (4, default) | 67.98 | 52.32 | 9.51 |
| 3 (8) | 95.31 | 84.02 | 4.13 |
| 1 (24) | 156.02 | 144.00 | 1.72 |
| 6, `OMP_WAIT_POLICY=passive` | 43.02 | 23.04 | 13.22 |
| 24, `OMP_WAIT_POLICY=passive` | 56.44 | 14.14 | 35.85 |

The span read is faster than the old per-strip read: 18 ms against 26 ms for one
chunk. Each additional chunk, however, adds about 5–11 ms of strip-read time,
even at 8 frames per chunk, where all 8 IO threads have work.

- An 8-thread `TIFFOpen`/`TIFFClose` costs about 1.5 ms (measured separately), so
  per-chunk file opens explain only part of this.
- With `OMP_WAIT_POLICY=passive`, the default 4-chunk read drops to 23 ms and
  device ingest to 43 ms. The per-chunk cost is therefore mostly OpenMP
  spin-waiting threads competing for the 8 CPUs between the per-chunk parallel
  regions.
- These are single runs. Changing the process-wide wait policy also affects every
  other stage, so it needs its own paired wall A/B. It is not part of this change.

### Unprofiled wall

Eight interleaved pairs (ABBA order), after one discarded warm-up run per arm.
Each pair ran under `flock /tmp/motioncorr-bench.lock` plus the GPU2 lock. All
four GPUs showed 0% utilisation at the start of each pair. Box load1 rose from
9.6 to 15 during the series (foreign load outside CPUs 72-79).

| pair | base s | candidate s | cand − base |
|---|---:|---:|---:|
| 1 | 8.207 | 8.593 | +0.386 |
| 2 | 8.999 | 7.821 | −1.179 |
| 3 | 8.393 | 7.828 | −0.565 |
| 4 | 7.414 | 8.981 | +1.567 |
| 5 | 7.759 | 7.181 | −0.578 |
| 6 | 7.353 | 7.390 | +0.037 |
| 7 | 7.430 | 7.210 | −0.220 |
| 8 | 7.463 | 7.164 | −0.300 |

- Median paired difference: −0.26 s. 5 of 8 pairs are negative.
- Arm medians: 7.61 s (base) and 7.61 s (candidate).
- The measured device-ingest saving, about 2.3 ms × 24 movies ≈ 0.05 s per run, is
  far below the per-run noise. **No wall-time change is established.**

### Memory

Peak RSS comes from `/usr/bin/time -v`; pinned bytes come from the movie logs.

| | base | candidate (default chunking) |
|---|---:|---:|
| pinned staging pool | 160 MiB (126 MB payload request) | 96 MiB (65 MB request) |
| peak RSS, 9 runs each | 600–602 MB, median 601 MB | 396–508 MB, median 452 MB |

The candidate's RSS varies between runs in steps of about 55 MB; this was not
investigated. Pinned staging at chunk 24 is 160 MiB, the same as base; at chunk
1 it is 32 MiB.

## Limitations

- The 6-frame acceptance fixture cannot fit a multi-frame slot, so it never
  exercises the single-slot path. That path is covered only by the 24-movie
  identity run at `MOTIONCORR_NVCOMP_CHUNK_FRAMES=24`.
- Halving skips sizes that would fit. For example, 6 → 3 → 1 never tries 2. This
  is conservative, not incorrect.
- UNRUN:
  - a genuinely corrupt Deflate stream, or a poisoned CUDA context, mid-movie;
  - more than one worker sharing the pinned cap (`--j` with several GPU workers);
  - any dataset other than the 24 tutorial movies.
- The default chunk size does not minimise device ingest on this dataset: 12
  frames measured lower in a single run. The OpenMP wait-policy finding above
  matters more than the chunk size.
