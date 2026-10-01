# Multi-GPU work: agreed priority order

Set by the maintainer on 2026-10-01, after the setup attribution in
`SETUP_ATTRIBUTION.md` showed the context lifecycle is 291 ms/worker.

## 1. Workspace ablation — IN PROGRESS, highest priority

PR #93 caches GPU scratch, cuFFT plans and events across the ~26 alignPatch
calls within a movie, instead of allocating per call. It targets repeated
allocation and planning on **every movie**, so it benefits single- and
multi-GPU runs alike — unlike anything in the setup attribution, which only
pays once per process.

Status: PR93's source delta applies to post-#128 main with 9 conflict hunks
across 3 files, because #128 rewrote the same regions (ownership model, RAII
owners, scratch arena). Being resolved on `experiment/workspace-ablation`.

What finishing it requires:
- resolve the conflicts preserving both PR93's reuse and #128's failure
  ownership;
- byte-identical products against the retained oracle;
- a **paired** benchmark with arm order alternating within each pair. PR93's
  own null (3 wins / 3 losses, n=6, median -0.46 s) was taken at a venue with
  ~1.5 s variation on a 34 s run, where a 0.45 s effect is unresolvable. The
  new argument is the venue, not the mechanism: 4-gpu-vm now shows 0.13 s
  spread at 4 GPUs.
- prefer a runtime switch so one binary serves both arms, removing
  build-to-build difference as a confound.

## 2. Lifecycle discriminator — before any architecture change

Four separate processes against one process initialising four devices, with
driver init, per-device context retain and release timed separately. The
runtime API folds these together; the driver API separates them.

This decides whether process sharing could save anything: if the serialised
cost is in `cuInit`, one process wins; if it is per-device
`cuDevicePrimaryCtxRetain`, a shared process still retains N of them and saves
nothing. Running it costs minutes and forecloses a large rewrite.

## 3. Persistent workers across batches

Workers already process many movies each; the opportunity is keeping them
alive **between dataset submissions**, amortising init and teardown across
jobs rather than within one. Improves warm-service throughput; the first cold
run still pays startup. A fatal CUDA error must retire the affected worker
rather than returning it to the pool.

## 4. MPS — experiment, not an assumed fix

Measured on the probe: context creation 850 -> 569 ms at 4 processes, slope
207 -> 136 ms/worker; destruction 345 -> 207 ms. Whole probe -30%.

Why this is not yet a recommendation:
- A100 MPS clients keep separate GPU address spaces, so it does not remove all
  client-side initialisation, and the measured 0.67x is consistent with that.
- One process per **distinct** GPU gives MPS little context-switching to
  exploit; its design target is many clients sharing one device.
- It adds a daemon as an operational dependency, and on a shared host that is
  not free.

Kept on its own branch. Fault isolation was checked and did not regress: with
a truncated movie, MPS on and off both gave worker rcs [1,0,0,0] and 23/23
products recovered.

## Ruled out, with evidence

- **Persistence mode**: context creation moved 1%, scaling x3.39 -> x3.43.
  Reverted to the state it was found in. See `SETUP_ATTRIBUTION.md`.
- **`--skip_logfile` on sharded workers**: predicted 0.4-1.0 s at 4 GPUs,
  measured 0.02 s. Saves 0.52 s at 1 GPU.
- **A threaded multi-GPU rewrite**: would require isolating RNG state
  (`init_random_generator` is process-global and reseeded per movie) and
  runner state. The current evidence does not justify that complexity.
