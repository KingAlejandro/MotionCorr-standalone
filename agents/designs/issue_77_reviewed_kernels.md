# Issue 77: reviewed CUDA kernel and scratch optimizations

## Scope and baseline

The reference is main `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26`.
Preserve its GPU-resident movie pipeline: gain/hot-pixel work, global and local
patch preparation/alignment, and weighted/unweighted reconstruction remain on
CUDA where already supported. No CPU reconstruction substitution is permitted.
The architecture agent was consulted before these corrections.

## Numerical contract

Preserve dose weighting's divisions, `powf`, `expf`, `sqrtf`, frame accumulation
order, peak selection/reduction, transform shapes, and original arithmetic.
Retain only load/layout/staging, scratch reuse, and scheduling changes pending
same-backend real-data comparison. No relaxed math or CPU-equivalence claim.
The synthetic fixture must explicitly request CUDA; its marker alone does not
prove every stage ran on CUDA.

## Scratch ownership and failure handling

The alignment cache is process-local under the existing serial CUDA movie
execution contract; it is not a new concurrent interface. Key it by device,
CCF geometry and frame count. Recompute weights when source geometry/B changes.
Publish allocated storage only after allocations, cuFFT plan and workspace
query succeed. Destroy temporary plans before buffers on construction failure.
Release resets keys and restores the previously active device. Incomplete
alignment/error exits discard the cache; valid non-convergence may retain it.
Normal movie execution releases scratch before reconstruction, with a scoped
movie-exit cleanup covering early returns and exceptions.

Host-wrapper staging has scoped cleanup on every exit. Preserve main's
contract: only global alignment copies modified Fourier frames back to host.
Grouping metadata checks both host vector lengths before comparisons. Allocate
replacement buffer pairs before committing either pointer; clear metadata
before uploads so a partial upload cannot match an old valid key. Grow patch
scratch transactionally. Log tracked alignment storage, not a whole-movie peak.

## Stream ordering and synchronization

All touched transforms, kernels and copies use the default CUDA stream.
Successive transforms sharing workspace stay ordered without per-frame host
fences; retain stage-end synchronization. Inverse transform input is preserved
by same-stream asynchronous D2D copies before tile reuse.

Alignment retains host shift downloads and convergence evaluation every
iteration. Separate reusable reference/FFT/peak event pairs are read only after
that mandatory completion boundary. Phase-shift event timing is read at the
next boundary or the final event wait before return. Do not introduce new
streams or reuse an event before its measurement is consumed.

Weighted reconstruction queues copy, dose, inverse FFT and interpolation in
original frame order, then completes at the final image download/event wait.
Per-frame event arrays retain detailed measurements without stage fences.
Event ownership remains scoped. No unmeasured asynchronous speedup claim.

## Acceptance evidence

Compare candidate and exact baseline binaries on the same dedicated GPU,
fixtures/options/allocation. Require complete corrected-image pixels and
headers, per-movie models/STAR metadata, same-backend repeats, native resident
stage witnesses, and nonzero/missing-pair fail-closed comparisons. Tutorial
movies 00021 and 00046 are initial checks, followed by all 24 movies. Retain
CPU/RELION differences and synthetic noisy failures as separate diagnostics.
Use repeated paired full-run and stage timings, not standalone kernel estimates.
Root coordinates execution: CPU-only work uses cpu64; GPU work prefers exclusive
SCARF allocation. Shared 4GPUs requires taskset 96-103, at most eight total CPU
threads and one MotionCorr benchmark at a time; do not affect other users.

## Exclusions

No FFT engine replacement, fast math, changed peak algorithm, new multistream
pipeline, pinned-host acquisition, unrelated I/O changes, or broad refactor.
Acceptance and performance are pending runtime evidence; this ADR is not proof
of test execution or merge readiness.
