# Issue #142: architecture experiments

Baseline: `57e98666a6225a8fdb6dafbdbc356478c21cea3a`. These are opt-in tools,
not a new production backend. No numerical gate or shipped default changes.

## Question 1: make FFT scheduling a resource policy?

The shipped movie session uses batch-one cuFFT plans and synchronizes every
frame. That was a reasonable response to a measured 3.5 GiB whole-process
limit for one 24-frame geometry. Does it remain the right policy for small,
long, rectangular and larger movies on a card with more memory?

Compare the actual production `CudaMovieSession` entry points with a small
experimental implementation using the same layout, normalization and preserved
Fourier input: batch one with per-frame synchronization (harness control),
batch one with stage synchronization, and stage-synchronized batches two/four.
Tail batches have their own plan; no padding or uninitialized transforms.
Plans share one workspace on the default stream. Plan setup is measured
separately from repeated transforms; arms are rotated and reversed by round.
Both Fourier and inverse outputs are compared to the actual production result
after every measured iteration, outside the timed region. Batch-one controls
must be bit-exact; batching differences are reported, never silently accepted.

Report explicitly owned movie/scratch bytes and cuFFT workspace. These omit
driver/context/library-private allocations and other pipeline stages: they
are not whole-process peaks. The reference movie retained for comparison is
benchmark-only overhead. Synthetic FFT input is not scientific validation.

Do not promote a candidate on this evidence alone. A useful candidate needs
full-application timing, exact output checks (or separate scientific acceptance
for intentional arithmetic changes), failure-path coverage and a memory budget.
The expected architecture decision is whether to keep a fixed policy or make
it explicit, not to select a universally fastest batch from a single machine.

## Existing work to reuse

- PRs #136/#140: worker gain and plan ownership/reuse; avoid another pool.
- PR #117: process isolation and movie sharding; avoid threaded runners while
  mutable metadata, PRNG and backend caches remain shared.
- PR #139: CUDA Graphs measured no-go for its tested large-movie workload;
  telemetry removal is a separate decision. No graph arm here.
- Issues #67/#74/#134: completion identity, optional profiling, decoder safety.

Initial workflow assumption: pipeline/HPC integration, with interactive CLI
and acquisition-time processing considered separately. This is a hypothesis
to validate with users, not a claim that interviews have taken place.
