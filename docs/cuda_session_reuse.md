# CUDA session reuse across movies

A healthy `CudaMovieSession` is parked at the end of a movie and reused by the
next movie when that movie has the same width, height, frame count and device.
The first movie also creates the CUDA primary context on a helper thread while
the main thread parses the movie header and reads the gain.

Results and limitations: see [Measurements](#measurements).

## Reuse rule

At `movie teardown`, after dose weighting and the last device read of the
movie, the runner calls `parkForReuse()`. Parking is refused, and the session
is released as before, when the session:

- is not initialised or is already parked;
- has recorded any CUDA failure (recoverable or fatal);
- still has an ingest stream, an ingest event or a live ingest scratch view;
- records a failure during `cudaDeviceSynchronize()` or while shedding its
  per-movie resources.

At the next `session setup`:

- same geometry, frame count and device: `resetForMovie(log)`. If it fails the
  session is released, `refuse_fallback_if_fatal` runs with boundary
  `session reuse`, and a fresh session is built unless the failure was fatal;
- anything else: the parked session is released before this movie allocates,
  with the same fatal refusal (boundary `release of the previous movie's
  session`), and a fresh session is built.

The failure state is never reset. A session that has failed is never parked,
and a parked session that has failed is never reset.

## Reset contract

What survives parking is exactly what `initialize()` would allocate again for
the same geometry: `d_Iframes`, `d_Fframes`, `d_fft_work`, `d_inverse_tile`,
and the R2C/C2R whole-frame plans. No stage reads these before writing them
(ingest and host upload overwrite `d_Iframes`; the forward FFT overwrites
`d_Fframes`; the other two are scratch).

| Per-movie state | Park | Reset | Test (`tests/cuda_session_reuse.cpp`) | Mutant |
|---|---|---|---|---|
| Fourier guard (spectrum left in `d_Fframes`) | — | `fourier_guard.reset()` | `state` | `skip_reset` |
| Unaligned sum `d_Isum` | freed | reallocated | `reuse` (ledger) | — |
| Gain alias or owned gain | dropped / freed | — | `state` | — |
| Gain lease (`CudaWorkerPlanPool`) | released | re-admitted as in `initialize()` | `state` | `keep_gain_lease` |
| Patch workspaces, patch plan, patch buffers | freed | — | `reuse` (ledger), `state` | `keep_patch_caches` |
| Uploaded group-table cache | cleared | — | `state` | `keep_group_table_cache` |
| Ingest streams, events, scratch views | park refused if live | — | `state` | `park_with_ingest_live` |
| Log binding | detached | bound to the new movie's log | `state` | `keep_log_binding` |
| Failure state | park refused | reset refused | `recoverable`, `fatal-park`, `fatal-reset` | `reuse_after_fatal` |

The `state` case checks each item directly through
`CudaMovieSessionTestAccess`: when the allocator hands back the same device
memory, a stale table or lease can be invisible in the outputs. The `reuse`
case compares a whole movie on a reused session with a fresh session bit for
bit and checks with a `cudaMalloc`/`cudaFree`/`cufftCreate` ledger that the
reset allocates only the unaligned sum and creates no plan.

## Memory

Retained between movies: the core above, about `nx*ny*nf*4 + ny*(nx/2+1)*nf*8
+ 2*ws` bytes, where `ws` is the larger of the R2C/C2R work sizes and the
inverse tile. For the tutorial geometry (3710 x 3838 x 24) that is
1366942080 + 1367678976 + 56986624 + 56986624 = 2848594304 bytes (2716.6 MiB).

This does not raise the process peak. Parking happens after every device
allocation of the movie, and between parking and the next `session setup` the
main thread does only host work (header parse, gain read). The next movie of
the same geometry allocates the same core first thing anyway; a movie of a
different geometry releases the parked session before allocating. The device
gain retained by `CudaWorkerPlanPool` is unchanged from the base.

At the end of `run()` (and before `exit()` on a job abort) the parked session is
released and checked. A failure is written to stderr and recorded in the
profile note `cuda_session_end_release`; it does not fail the job, because
every product was complete before the session was parked. The run prints
`CUDA movie sessions: N built, M reused`.

`CudaPreprocessingFailurePaths` runs two same-geometry movies through the
fault-injection executable, requires one reuse, identical payloads, and
`remaining-owned=0` at process exit. Its negative control,
`motioncorr_faultinject_leak_parked`, drops the parked session at the end of
run instead of releasing it, and must be reported as owning allocations.

## First-movie warm-up

`run()` starts one helper thread after the last pre-loop step that can
`REPORT_ERROR`. It calls only `cudaSetDevice(gpu_id)`, which creates the
primary context, and ignores the result. The main thread repeats every CUDA
call it depends on, so errors are reported where and how they were before. The
thread is joined in `session setup` (sub-stage `wait for context warm-up`), on
job abort, at the end of `run()`, and by the runner's destructor.

The pinned staging pool and session/plan creation stay on the main thread.
They need the context, so on the helper they would run after context creation,
and context creation alone already takes longer than the main-thread work it
overlaps (see Measurements).

## Measurements

Status: WIP, stopped for integration on 2026-10-09 at head `9c523de` (base `dfca087`).

MEASURED (4GPUs, GPU 1, CPUs 64-71):

- Native `ctest` in `build-cand`: 72/72 passed. This includes the six
  `CudaSessionReuse_*` cases, the seven `CudaSessionReuseMutant_*` controls
  (each fails at its intended assertion), and `CudaPreprocessingFailurePaths`
  with the parked-session leak control.
- Mixed-geometry identity, base vs candidate binaries, canonical options
  (`kit identity.compare_trees`, [mixed_identity.json](perf_round2/cuda-session-reuse/mixed_identity.json)):
  - frame-count batch (22, 22@20f, 23, 24, 25@20f, 26, 27; with gain): identical,
    7 MRC, `5 built, 2 reused`;
  - image-size batch (22, 2048x2048 crops of 23 and 24, 25; no gain): identical,
    4 MRC, `3 built, 1 reused`;
  - per-movie logs (excluded by the kit) equal apart from the output directory.

UNRUN: the kit `compare` on the 24-movie tutorial (wall verdict, stage and
device deltas, first-movie wall, `cudaMalloc`/`cudaFree` counts, peak and
retained VRAM), and 24-movie product identity. No wall or memory claim is made.
