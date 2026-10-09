# In-process movie overlap: next-movie strip prefetch (no-go)

**Decision: no-go.** Moving the next movie's TIFF strip read onto its own thread did not resolve a wall-time gain on the 96-movie kit compare, and the stop rule needed a resolved gain of at least 10%. The measured main-thread saving is about 16–18 ms of a 228 ms movie (7–8%), short of 10% even if a quieter host resolved it. The prototype is not productionised. Its code is kept for reference at `76972f3` on branch `perf/movie-overlap`.

## What was tried

This is design 1 of the round-3 brief: host prefetch only, with no second CUDA stream and no second set of movie buffers.

- **Opt-in:** `MOTIONCORR_MOVIE_PREFETCH=1`, default off. `MOTIONCORR_MOVIE_PREFETCH_CPUS` pins the thread; CPUs 88-91 were used.
- **Thread and buffer:** one `std::thread` owns its own pinned host buffer, sized from the current movie's staging bytes (160 MiB here). The thread makes no CUDA calls.
- **When it runs:** after a successful nvCOMP ingest of movie N, the thread scans and `pread`s every compressed strip of movie N+1 into that buffer, in the same `in_align` layout the chunked ingest uses. It starts only after `endIngestScratch` has drained the copy stream, so the buffer is never rewritten while an H2D copy is in flight.
- **Consumer:** the next ingest joins the thread. It uses the buffer only if file, frames, geometry, alignment and the read result all match exactly. Otherwise it logs the reason and runs the unchanged serial path, which still emits every refusal and diagnostic.
- **Unchanged:** the zlib wrapper and Adler-32 checks run on the prefetched bytes exactly as on serially read ones. Per-movie arithmetic is unchanged; only where and when the strips are read changes.

## Results (MEASURED, GPU2 on 4GPUs, A100 80 GB, 96-movie STAR = the 24 tutorial movies listed 4 times)

Kit `1d3c399`: base `7d64043`, candidate `76972f3`. The lane is CPUs 72-79 plus 88-91 for both arms, the runner is on CPU 123, and both arms get the same environment (base ignores the variable). The host load average was 15–34 throughout.

| run | clean pairs | median B−A | relative | CI of median | verdict |
|---|---|---|---|---|---|
| [run 1](movie_overlap/c96_run1/report.md) | 5 | −2.00 s | −8.06% | n/a | not resolved (6 pairs needed) |
| [run 2](movie_overlap/c96_run2/report.md) | 7 | −1.06 s | −4.15% | −3.30..+1.37 s | not resolved (CI includes 0) |

Pooling the 12 clean pairs gives a median of about −1.9 s (calculated, not a kit verdict). Three of the 12 pairs are positive, i.e. the candidate was slower.

Product identity in the kit's check passed in both runs: 297 files, 96 MRC, with MRC header bytes 0–223 and bytes from 1024 on, plus path-normalised STAR/EPS. A 4-movie smoke run also compared IDENTICAL with `cmp_trees.py`.

### Where the time went (run 1, `--profile` passes, steady-movie medians)

| device-ingest sub-stage (main thread) | base ms | candidate ms |
|---|---|---|
| ingest strip read | 24.68 | — (5.34 to fill tables from the prefetch) |
| ingest tag scan | 2.90 | — |
| ingest prefetch wait | — | 0.01 |
| ingest status d2h and sync | 12.60 | 24.48 |
| device ingest, total | 44.69 | 33.32 |

The prefetch thread finishes well ahead of the next movie: its join wait is 0.01 ms. In base, the GPU inflate of chunk k overlaps the host read of chunk k+1. With the read gone, the main thread now waits for that inflate instead: d2h-and-sync doubles. Ingest becomes GPU-bound at about 33 ms, so roughly 28 ms of host work removed yields only about 11 ms of main-thread time. No other stage moved beyond its noise threshold.

### Per-thread busy time (run 1, `--profile` thread records, whole 96-movie process)

| thread | base p01 / p02 s | candidate p01 / p02 s |
|---|---|---|
| main (CPU = wall, CUDA waits spin) | 21.67 / 23.29 | 20.15 / 21.51 |
| writer (192 product tasks) | 9.41 / 9.95 | 9.85 / 8.66 |
| prefetch (95 movies) | — | 5.45 / 4.51 (about 50 ms/movie) |
| process wall | 24.70 / 30.08 | 22.69 / 29.24 |

**The main thread is still the limit.** In the candidate it is busy for 74–89% of the process wall, against 30–43% for the writer and 15–24% for the prefetch thread. The main-thread saving is 1.5–1.8 s per 96 movies, about 16–18 ms/movie or 7%. That is consistent with the kit's −4% to −8% medians, and it is the ceiling for this design. The profiled steady-movie median fell 228.3 → 203.4 ms (−10.9%), but that figure comes from two profiled passes per arm, and no stage delta other than ingest's sub-stages was flagged; it is not a verdict.

### Memory

- **Peak RSS:** 368 → 532 MiB (+164 MiB), which is the prefetch's pinned buffer.
- **VRAM:** unchanged at 3362 MiB (NVML process peak).
- **Process CPU:** 62.8–69.0 s → 37.3–39.7 s, about −25 s per run. This is inferred, not measured per thread: the drop is the OpenMP workers of the serial strip-read region spinning after it. The candidate skips that region when the prefetch is used. The drop did not show up as wall time on a 12-CPU lane.

## Why it differs from earlier attempts, and why it still does not pay

- **#108** (bounded host prefetch, closed) lost about 0.32 s to contention with the OpenMP readers. Here the thread runs on its own CPUs and the other stages did not move, so contention is not the problem. The problem is that the removed host work was already partly overlapped with the GPU inflate.
- **#161** (two processes on one GPU, MPS) duplicated all host work per process. In-process overlap avoids that, but only for work that can leave the main thread. The strip read was the largest such block that is cheap to move.

## What would be needed for 10%

10% of a 228 ms movie is about 23 ms, so a further ~5–7 ms of main-thread time would have to go beyond this prototype, and a resolved verdict on this shared host needs a margin above that. The remaining main-thread blocks are:

- the GPU inflate wait in ingest (about 24 ms), which only design 2 can hide: the next movie's inflate on a second stream with a second set of movie buffers;
- hot pixels (about 19 ms, host);
- dose weighting (about 43 ms, mostly GPU).

Design 2 also needs the session-reuse ownership work from `perf/cuda-session-reuse`. It is a much larger change, and nothing here shows it would avoid the same GPU-bound limit: the GPU is already busy for about 150 ms of the movie.

## UNRUN

These were not run because the stop rule ended the experiment:

- the 24-movie compare (first-movie and tail effects);
- the Nsight trace pass;
- the identity matrix (eo+noDW, poison, late binning 1.25 with `--ingest auto`, CPU, mixed geometry);
- tests and compiled negative controls for the prefetch path;
- native ctest including the fault-injection tests.
