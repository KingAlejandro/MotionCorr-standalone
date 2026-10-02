# Single-GPU continuation after PR128

Baseline: `c499b1d3bf1cceec5c3b194f356844d6f493e7f2`, refetched 1 October 2026.
The supplied user handoff is the acceptance contract. PR128 is already merged.
The separate `experiment/post128-multigpu` branch owns scheduling and scaling;
this branch does not import its runner/CMake/harness changes.

## First ablation

Profile the current complete 24-movie nvCOMP run, then reuse the eight alignment
buffers, eight timing events, batched C2R plan and exact weights within a movie.
Retain the current kernels, floating-point ordering, convergence conditions and
synchronizations. Do not import PR93's process-static cache or arithmetic changes.
Global alignment and host fallback retain the existing ephemeral entry point.

The session owns the local workspace. Its full key covers device, patch/CCF
geometry, group count and weight/downsample/search dependencies. Publish validity
only after initialization succeeds. Register each resource immediately with the
existing scoped owners and session failure state. Invalidate before replacement;
release explicitly before reconstruction as well as on exceptions. Cleanup errors
must retain fatal state and prevent subsequent reconstruction/publication.

## Evidence

SCARF allocation 3516825 is dedicated to this single-GPU campaign. Fresh baseline
and a disposable NVTX-instrumented copy are built separately from the pinned tree.
Only uninstrumented complete runs establish performance. Profile ranges and GPU
API/kernel intervals are overlapping measurements, not additive wall components.
Unknown intervals remain unknown. Tool scripts are under `tools/single_gpu/`.

Required controls: repeated/changing geometry and group counts, B/downsample
changes, successive movies, first/partial malloc, event creation, plan creation
and planning, release failures and successful reuse. Compare exact shifts and
Fourier results from the actual production entry point. Complete output checks
cover inventory, full normalized/extended MRC headers, exact pixels, per-movie and
joint STAR, trajectories, requested options and unexpected fallback. Test CPU and
CUDA without nvCOMP too. Retain failed and skipped rows.

Screen baseline/candidate in three alternating pairs. If promising, confirm at
least five interleaved complete pairs at identical source-independent settings,
resources and filesystem/cache regime. Keep all observations and paired spread.
No merge is implied by this task; retain a no-win experiment without promotion.
