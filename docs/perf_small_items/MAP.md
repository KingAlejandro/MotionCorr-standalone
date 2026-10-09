# Per-movie cost map, main 7d64043

All numbers are MEASURED on 4GPUs GPU0 (`GPU-eddb42fe…`), payload CPUs 96-103, Release build of
7d64043, tutorial 96-movie STAR (TIFF + gain, `--ingest auto`), unless marked calculated or UNRUN.
The host is shared: load1 was 13.6 (trace) and ~16 (profile), so small host-side numbers carry a
few-percent noise.

Sources, in `map_evidence/`:
- `trace96_main_report.md`, `trace96_main_provenance.json`: kit Nsight trace, 96 movies.
  Window 28466.5 ms, device busy 48.6%, 2980 implicit-sync `cudaFree` calls blocking 807.8 ms.
- `prof96_main_stages.txt`: untraced `--profile`, 96 movies. First movie 669.5 ms, steady median
  215.8 ms, stage sum 22491 ms, run wall 24687 ms.
- `trace12_eager_report.md`, `trace12_lazy_report.md`: 12-movie traces with
  `CUDA_MODULE_LOADING=EAGER` and `=LAZY`.
- `hotpixel_subscopes.txt`: hot-pixel sub-scopes, 8 movies, with temporary scopes that were not
  committed.

The "wall" column is the untraced steady median. Traced numbers (wall, busy, idle) are inflated
by Nsight and are used only to attribute idle time and API calls. Idle kinds:
- **host**: host compute while the GPU has nothing queued.
- **blocked**: host blocked in a synchronous CUDA API call, such as `cudaMalloc`, a module load,
  or a blocking copy.
- **sync**: implicit device sync, such as `cudaFree` or a pageable D2H.

Per-movie API counts in the traced steady state:

| API | per movie |
|---|---|
| `cuModuleLoadData` (and matching unloads) | 46: fft plans 28, patch alignment 16, global alignment 2 |
| `cudaMalloc` / `cudaFree` | 24 / 24 |
| `cuMemAlloc` | 7 |
| `cudaEventCreate` | 24 |
| `cudaStreamCreate` | 3 |

## 1. Allocation churn and module loads

`CudaMovieSession` is built and destroyed for every movie. It owns movie buffers, cuFFT plans,
scratch, workspaces and events, so all of them are created and freed per movie, even though
geometry never changes in a homogeneous dataset.

| item | stage | wall ms | traced busy / idle | idle kind | code site | proposed exact fix | expected saving | risk |
|---|---|---|---|---|---|---|---|---|
| movie buffers `d_Iframes`, `d_Fframes`, `d_Isum` | session setup | 2.83 | –/– (5 mallocs, 307 ms over 96 movies) | blocked | cuda_movie_session.cu:484-486 | keep in a worker-pool geometry entry; reuse on a key hit | 2.8 | medium |
| global R2C/C2R plans (28 module loads) | session setup | 3.48 | – | blocked | cuda_movie_session.cu:509 | same entry holds the plans | 3.5 | medium |
| `d_fft_work`, `d_inverse_tile` | session setup | 1.76 | – | blocked | cuda_movie_session.cu:535-537 | same entry | 1.8 | medium |
| session release (4 frees, 4.05 ms implicit sync traced) | movie teardown | 3.64 | 7.15 traced | sync | cuda_movie_session.cu:570-620 | retained buffers are not freed | ~3 | medium |
| hot-pixel stats scratch (6 malloc + 6 free) | hot pixels | in 4.32 "gpu stats" | 0.32 / 20.95 | blocked, sync | cuda_movie_session.cu:886-949 | grow-only session scratch kept in the pool entry | ~0.5 (calculated) | low |
| defect-fix scratch (3 + 3) | fix defects | 1.74 | 9 syncs | blocked, sync | cuda_movie_session.cu:999-1003 | as above | ~0.5 (calculated) | low |
| batched patch workspace: 10 mallocs, `plan_patch_r2c`, batched C2R plan, 2 events (16 module loads) | patch alignment | part of 26.0 | 19.88 / 24.30 | blocked | cuda_movie_session.cu:2022-2109; cuda_alignpatch.cu:881-907 | retain the workspace across movies with a geometry and batch key | 3-5 (calculated from 16 loads × ~0.13 ms untraced plus mallocs) | medium: `cudaMemGetInfo` at cuda_movie_session.cu:2151/2219 chooses the chunk, see below |
| release of that workspace (14 frees, 15 syncs) | release alignment | 1.65 | 3.26 traced | sync | motioncorr_runner.cpp:3472; cuda_movie_session.cu:1959 | not freed while retained | 1.6 | medium |
| global-alignment workspace: 8 events and a C2R plan per call (2 module loads, 0.9 ms traced) | global alignment | part of 8.35 | 7.13 / 3.81 | blocked | runner:4136 → cuda_alignpatch.cu:1056, :495-502 | retained workspace | ~1 | low-medium |
| DW events (8) and ingest streams and events (3 streams) | DW, ingest | <0.5 total | – | blocked | cuda_realspace_dw.cu:253-267; cuda_movie_session.cu:1194, 1632-1635 | persistent per worker | <0.5 (calculated) | low; last |

**Module loads, EAGER vs LAZY.** Both settings load 46 modules per steady movie. The only
difference is the first movie: EAGER 942 ms, LAZY 783 ms (12-movie traces). Steady movies are
the same. The loads come from cuFFT plan creation, so caching plans is the only per-movie lever;
the loader setting is not.

**Design for the retained entry.** The aim is to avoid the ownership defects found in
#133, #136 and #140 (all closed). The entry extends the existing worker pool
(`mc_cuda::CudaWorkerPlanPool`, src/acc/cuda/cuda_plan_pool.h). That pool already provides the
exclusive lease, a device-restoring checked `drop`, and `retire`/`dropAll` called from the
session's `ReleaseFailureGuard`. It does not import perf/cuda-session-reuse 8e319d0.
- Key: (device, nx, ny, n_frames). If the key does not match, the entry is dropped (checked free
  on its own device) before anything new is allocated, so two geometries are never held at once.
- An entry is published to the pool only after `initialize()` has succeeded. Any failure leaves
  nothing published, and the existing guard retires or drops it.
- A cap: retained bytes count toward `retainedBytes()`. During a movie the retained set is exactly
  what the session would allocate anyway. Free VRAM at the patch-chunk `cudaMemGetInfo` therefore
  stays the same. This only holds if the patch workspace is allocated before that query; it must
  be checked per call site before that workspace is retained.
- Poisoning: buffer reuse can hide a missing write (see device-buffer reuse in A/B checks). So
  under `MOTIONCORR_FRAME_POOL_POISON=1`, retained buffers are filled with NaN on reuse, and the
  identity matrix includes that arm.

## 2. Hot pixels

18.70 ms wall per steady movie (75.2 on the first). Traced GPU busy is 0.32 ms, so the stage is
almost entirely host work with the GPU idle.

| item | wall ms | idle kind | code site | proposed exact fix | expected saving | risk |
|---|---|---|---|---|---|---|
| bad-list scan over the whole 14 Mpixel `bBad` | 10.86 (range 10.5-18.6) | host | motioncorr_runner.cpp:2444 | merge two ascending index lists: cached pre-mask indices plus this movie's new hits; keep the scan as a fallback when the merge cannot certify its inputs | 10.9 | low: the list is identical by construction, and a unit test compares it with the scan |
| `MultidimArray<bool> bBad(ny, nx)` zero fill | 2.02 [11.0 first] | host | motioncorr_runner.cpp:2303 | `resizeNoCp`: every element is overwritten by the pre-mask copy before any read | 2.0 | low |
| pre-mask deep copy | 1.75 [49.65 first, build] | host | motioncorr_runner.cpp:2401 | keep: detected pixels must not reach the cache | – | – |
| GPU stats: mean, sum of squared deviations, threshold collect (3 D2H syncs) | 4.32 | sync | motioncorr_runner.cpp:2326-2350 | keep: the two-pass statistics are what make the result exact | – | – |
| filter hits, reachability, Isum clear | ≈0.03 each | host | – | – | – | – |

RNG and determinism: the merge only changes how the list is built. Its order (ascending
row-major), and therefore every RNG draw, is unchanged. `HotPixelRngDeterminism` covers this.

## 3. Alignment round trips and setup idle

| item | stage | wall ms | traced busy / idle | syncs per movie | code site |
|---|---|---|---|---|---|
| per-iteration shift D2H and upload, 7 chunks of ≤4 patches | patch alignment | 26.0 | 19.88 / 24.30 | 51 | cuda_alignpatch.cu:997 (`cudaMemcpy h_cur`), :1008 (`d_shift`) |
| per-iteration D2H and H2D | global alignment | 8.35 | 7.13 / 3.81 | 15 | cuda_alignpatch.cu:654-670 |

**Setup idle.** The idle time before the first iteration of each alignment is host time spent
blocked in workspace construction: `cudaMalloc`, plan creation (16 + 2 module loads) and event
creation (§1). Retaining the workspaces removes it. This is the part of the round-trip idle that
is exact and cheap to remove.

**Option (a): device-side update and convergence test.** The host loop accumulates in double, in
descending frame order, and finishes with `std::sqrt`. A single-thread device kernel can match it
exactly if:
- the loop order is the same;
- FMA contraction is disabled (`__dadd_rn`/`__dmul_rn`, or `--fmad=false` for that kernel);
- `sqrt` is used, which is correctly rounded on the device, as `std::sqrt` is on the host.

The host still needs the convergence decision to stop launching. Either it reads a flag every
iteration, which is the same sync, or it launches all `max_iter` iterations with device-side
early exit and downloads the RMSD once at the end. The second costs empty launches after
convergence. Expected saving: part of the 24 ms traced idle, at most ~5-10 ms untraced
(calculated). Risk: high. The exactness argument depends on compiler flags per kernel, and a
missed contraction changes shifts in the last bit, which changes products. UNRUN.

**Option (b): pinned memory, async copies with events, speculative next iteration.**
- Pinned buffers and async copies only remove the pageable-staging cost, ~10-20 µs per copy, so
  under 1 ms per movie (calculated).
- A speculative next iteration needs the updated shifts on the device, which brings back
  option (a).

UNRUN.

## 4. Ingest host time

Session and device ingest is 65.6 ms wall (device ingest 57.36 ms):

| sub-stage | ms |
|---|---|
| strip read | 41.31 |
| status D2H and sync (waiting for decompression) | 9.71 |
| tag scan | 2.63 |
| setup | 0.88 |
| drain | 0.94 |
| verify | 0.29 |
| decompress submit | 0.37 |
| H2D submit | 0.30 |

The strip read is host wall time on the critical path. E's reader pool (perf/e-omp-wait-hotpixel
4e9d07d + d0bda26) replaces a libgomp parallel region per chunk with a persistent sleeping reader
team. Each region costs ~5-11 ms of spin contention under the 8-CPU cap. E's branch is not based
on main (merge base dfca087), so it needs a port. Expected saving: UNRUN until it is ported and
measured on main. Only wall time counts; CPU time does not.

## 5. Everything else

| item | wall ms | traced | idle kind | code site | proposed fix | expected saving | risk |
|---|---|---|---|---|---|---|---|
| setup | 1.50 | – | host | runner | none | – | – |
| fix defects | 1.74 | 2.49, 9 syncs | blocked, sync | runner:2499; cuda_movie_session.cu:999-1003 | scratch retention (§1) | ~0.5 | low |
| release preprocessing | 0.24 | 0.42 | sync | runner:2655 | none | – | – |
| global FFT / IFFT | 21.9 / 22.0 | 98% busy | – | runner:2682, 2918 | GPU-bound; FFT agent's scope | – | – |
| fit polynomial | 1.64 | 1.74 | host, GPU idle | runner:3326 | CPU-only least squares; none | – | – |
| release alignment | 1.65 | 3.26 | sync | runner:3468 | §1 | 1.6 | medium |
| dose weighting | 41.2 | 34.67 / 7.41 | blocked (8 events), host | runner:3620 | events only (§1) | <0.5 | low |
| movie teardown | 3.78 | 7.15 | sync | runner:3715 | §1 | ~3 | medium |
| between movies | 0.24 (22.49 ms total traced) | – | host | – | none | – | – |

**First movie.** First movie 669.5 ms, steady 215.8 ms:

| item | first movie ms | notes |
|---|---|---|
| read gain | 115.2 | host decode, once per run |
| session setup | 162.6 | plans 7.3 ms; the rest is CUDA context creation and initialisation |
| ingest setup | 100.0 | nvCOMP and pinned staging initialisation |
| decompress submit | 11.8 | |
| hot pixels | 75.2 | pre-mask build 49.65 ms, `bBad` construction 11.0 ms |
| dose weighting | 74.8 | first kernel and module loads |

`CUDA_MODULE_LOADING=LAZY` is 159 ms cheaper than EAGER on the first movie only.

**Per run.** Before the first movie: 4.8 ms. After the last movie: 2367.8 ms (context
destruction, 3 frees). Neither is per-movie.

## Order of fixes

Ranked by saving per unit of risk (savings are per steady movie):

| # | fix | saving | status |
|---|---|---|---|
| 1 | hot-pixel list merge + `resizeNoCp` | ~12.9 ms, exact, low risk | committed 613d8ce |
| 2 | retained global geometry (buffers, plans, FFT scratch) in the worker pool | ~11 ms (setup ~8 + release ~3) | committed, `geometry_retention.md` |
| 3 | retained patch and global-alignment workspaces | ~5-7 ms | |
| 4 | port of E's reader pool | UNRUN | |
| 5 | persistent events and streams | <0.5 ms | |
| 6 | alignment options (a) and (b) | | mapped, UNRUN |

Results for each fix are in the PR body and in `docs/perf_small_items/`.
