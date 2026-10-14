# CUDA context warm-up and registered pinned staging

Design note for the two start-up changes in `perf(cuda): create the CUDA context
and pinned stage while host setup runs`. Measurements are in
[`evidence/warmup/`](evidence/warmup/) and summarised in the PR.

## Why

With `--skip_report_pdf` (what launcher workers run) each process pays about
1.0 s of fixed cost; the first movie costs ~500 ms more than a steady one.
Two of those items sit on the main thread although nothing before them needs the
device:

- the CUDA primary context, created lazily inside the first movie's `session
  setup` (~174 ms);
- the 128 MiB pinned staging pool, `cudaHostAlloc` inside `ensurePinnedStage()`
  (~104 ms of `ingest setup`).

## 1. Context warm-up thread

`MotioncorrRunner::initialise()` starts a `mc_cuda::ContextWarmup` right after the
`--gpu` id is validated and `use_gpu` is set. The helper runs
`cudaSetDevice(gpu_id); cudaFree(0)`. The main thread joins it in
`executeOwnMotionCorrection()`, after `read gain` and before the first CUDA
call of the movie (`joinContextWarmup()`); the overlap window is the rest of
`initialise()`, STAR loading, the first movie's header parse and the gain read.

Started only when all of these hold: CUDA build, `--use_own`, a validated `--gpu`
id, not `--aggregate_only`. Never on the MotionCor2 path, never in a CPU-only
build. `MOTIONCORR_CUDA_WARMUP=0` disables it, so one binary can be timed both
ways.

### Ownership and failure contract

| Rule | How it is kept |
|---|---|
| The helper does only what the main thread would do anyway | Its operation is `cudaSetDevice` + `cudaFree(0)` for the device the main thread is about to use |
| Its result never changes control flow | `join()` returns an `Outcome` that is logged (`NOTE: CUDA context warm-up ... did not complete`) and added to `--profile`; no caller branches on it. The main thread then does its own `cudaGetDeviceCount`, `cudaSetDevice`, allocations, exactly as without a warm-up |
| A failed warm-up cannot turn a recoverable main path fatal, or the reverse | The CUDA last-error slot is per thread, so a failed helper call leaves nothing in the main thread's slot (which `refuse_fallback_if_fatal` reads). A sticky error is process-wide and the main thread meets it on its own first call, as it would have; a transient failure is simply retried by the main thread's own call |
| No exception crosses the thread boundary | The thread body catches everything and stores it in the `Outcome` |
| The helper is joined on every path | `join()` is idempotent; `~ContextWarmup()` joins, and the owner is a `unique_ptr` member of the runner, so REPORT_ERROR unwinding out of `initialise()` or `run()` joins before the runner is destroyed. The pipeline-abort `exit()` resets it explicitly because `exit()` runs no destructors of that object |
| Thread creation failure is harmless | `start()` is `noexcept`; if no thread can be created there is no warm-up |

Fault-injection harnesses: the warm-up issues `cudaSetDevice` and
`cudaFree(nullptr)` only. `CudaFaultMatrix` drives `CudaMovieSession` directly
and never constructs a runner, so it never sees the helper. The
`motioncorr_faultinject` shim counts `cudaMalloc` and `cudaGetDeviceCount`
ordinals, which the helper does not call, so no row's ordinal shifts. The shim's
ownership ledger is not thread-safe; the helper's `cudaFree(nullptr)` is
recognised by its thread and bypasses the ledger, and the main thread joins
before its first wrapped allocation.

Known cost: a run that has nothing to process (every movie already complete
under `--continue`) still creates a context it will not use, on the helper
thread, before `run()` ends.

## 2. Pinned staging pool: registered hugepage mapping (option b)

Chosen over handing the warm-up thread's allocation to the main thread (option
a), because (a) needs the pool size before the first movie is known. The size
comes from that movie's compressed request. A guessed size would pin memory for
runs that never use nvCOMP, and a pool above `MOTIONCORR_NVCOMP_PINNED_MAX_MB`
makes `ingestCompressedTiffStrips` decline the device ingest, which would change
behaviour. (b) keeps the size and the point of allocation exactly as today and
changes only how the bytes are pinned.

`mc_cuda::PinnedStage` (replacing the `thread_local PinnedStagePool`) owns one
buffer, either a 2 MiB-aligned anonymous `mmap` with `MADV_HUGEPAGE` pinned by
`cudaHostRegister`, or a `cudaHostAlloc` buffer. Each has exactly one free path
(`cudaHostUnregister` + `munmap`, or `cudaFreeHost`), `release()` is idempotent,
and `acquire()` refuses while a buffer is held, so grow is explicitly
release-then-acquire as before. If mapping or registration fails the mapping is
returned and `cudaHostAlloc` supplies the buffer; the log then carries one extra
line saying so. The `pinned staging pool grown to N bytes` line is unchanged.

Free behaviour: a failed unpin keeps ownership (as a failed `cudaFreeHost` did),
and the thread-exit destructor returns the mapping regardless, because the
context may be gone. `MOTIONCORR_PINNED_REGISTER=0` selects the `cudaHostAlloc`
path.

Registered memory is not `cudaHostAlloc` memory, but both are page-locked, the
buffer is only read by `cudaMemcpyAsync`, and no mapped/portable flag was used
before. A refused `cudaHostRegister` leaves its status in the thread's last-error
slot, which the fallback would not have raised, so `acquire()` clears it when
it is that status and leaves an older pending error alone.

`CudaPreprocessingFailurePaths` checks `remaining-owned=0` over `cudaMalloc` and
`cudaFree`; pinned host memory is outside that ledger, and its own ledger is
`CudaPinnedStage`.
