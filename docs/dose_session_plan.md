# Reuse the resident session inverse plan for dose reconstruction

## Scope

Main `7336128` creates a contiguous rank2 single-precision batch-one C2R plan
for each resident CUDA movie. Dose reconstruction currently builds a second
plan with the same `{ny,nx}`, type and batch. Reuse the existing session plan
only for this synchronous reconstruction call. Nonresident reconstruction keeps
its original owned-plan path. No worker pool, cross-movie retention, reader,
gain/premask cache, dose arithmetic, normalization or interpolation changes.

Both plans use NULL embeds, hence cuFFT uses the same default contiguous layout
and ignores the apparent explicit-versus-zero stride distances. NVIDIA documents
this in [cuFFT advanced layouts](https://docs.nvidia.com/cuda/cufft/index.html#function-cufftmakeplanmany).
The session disables auto allocation and attaches a work area sized to the larger
R2C/C2R requirement. Its C2R executes on default stream0. Session forward/inverse
transforms synchronize per frame; reconstruction synchronizes its completion
events and downloads the result before returning. The serial movie caller cannot
execute another session FFT during this synchronous helper. This restriction is
part of the borrowed parameter contract, not a general concurrent plan cache.

## Ownership and failure

The session remains the sole plan/work-area owner. A borrowed handle never enters
the helper's ScopedCufftPlan, is not rebound, and is neither retained nor destroyed
by helper cleanup. The helper still owns its Fourier/real frame, accumulator,
dose vector, normalization plane and events. It uses the session failure state;
first-error provenance and fatal cleanup remain visible to the runner's fallback
refusal. Failed/fatal sessions keep the same checked release and retirement.
The borrowed call leaves original resident Fourier frames unchanged.

The reconstruction's existing `Peak VRAM` profile is component allocation
accounting, not whole-process/device peak. It excludes the borrowed workspace
because that workspace belongs to the existing session; the fallback still
accounts for its own workspace. No newly retained bytes exist between movies.

## Historical scale, not a new speed claim

PR136's retained plan pools together saved approximately 0.370s across 24 tutorial
movies while retaining approximately 215.2MiB of plan scratch/inverse tile, beyond
the separately retained gain. Its individual dose-plan step (~0.117s) was smaller
than run variability. PR140 used a different baseline and reported distinct
results; these figures are not additive/current-main predictions. Full donor
branches include ownership/cache mechanisms already superseded by PR143 and
must not be merged wholesale. This patch removes duplicate per-movie dose-plan
construction without importing their worker-lifetime residency architecture.

## Required evidence

- CPU inventory preserved; CUDA compile confirms the added parameter/call.
- Existing owned-plan exact arithmetic/fault controls remain unchanged.
- `CudaDoseSessionPlan` runs actual session reconstruction: odd/non-square and
  even geometry, null/polynomial model, exact frozen-oracle pixels, original
  Fourier preservation, zero helper plan creates/destroys, real owner transform
  after borrow/refusal and exactly-once session destruction.
- Returned-code recoverable then fatal cleanup checks retain first cause,
  reject redispatch after fatal state and leave helper-owned resources empty.
- Powered mutants must restore duplicate creation and accidentally adopt the
  borrowed handle; the controls must fail at their distinguishing assertions.
- Current-main versus candidate native application products require complete
  pixels/normalized full headers/STAR and numerical verdicts. Compilation does
  not establish these. Isolated paired timing follows correctness; no timing
  claim while other GPU jobs share resources.

## Current acceptance

Frozen source `fddbcf4756af015433c49eb620a1084e81701700` composes main
`733612887f96875bcd9c9f76d4cbba9973ac517b`, including the checksum repair.

- Mac: 39 collected CTests, 37PASS, inherited SyntheticRegressionFAIL and
  Linux-only NativeMovieStagingSKIP. This does not execute CUDA tests.
- VM, CUDA12.8/sm80/Release/nvCOMP OFF: genuine source Git checkout, all
  50 named Linux/native CTests PASS, no skipped/missing/failed tests. The
  required 39 CPU names and all 11 CUDA names are preserved.
- Six borrowed-session cases PASS. Original owned-plan reference remains
  50 exact null/polynomial cases plus five returned-code fault cases.
- Actual current-main session caller with the new default-zero helper API
  fails the extra-plan runtime assertion. An accidental borrowed-plan
  adoption also fails that assertion. Both compile and execute natively;
  these are not compilation/unknown-option negatives.
- Two seven-frame 96x96 synthetic movies, two exposure values and patch1/3:
  actual main versus candidate has 20 paired finite MRCs, complete normalized
  1024-byte/extended headers and 156672 pixels exact, plus six paired STARs
  exact. Every movie has a completed resident CUDA dose profile. Expected
  DW/noDW/EVN/ODD/PS inventory and geometry are checked independently.
- Actual PID/birth/executable/full CPU mask and physical GPU UUID witnesses,
  observed-descendant cleanup and empty-device release pass. All source,
  binary and external caller pins remain unchanged through acceptance.

The original odd-geometry test tried to prove ownership with the existing
multi-frame session inverse method. A separate unchanged-method probe before
any dose borrow showed that method already rejects the 35x29 multi-frame output
stride. The ownership test instead executes the actual owner handle into an
aligned single-frame output. The first failed campaign and the distinguishing
probe are retained; the dose helper's odd-geometry oracle remains required.

Venue: GPU0 `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, all descendants on
logical CPUs 96–103/membind1, build 4 under the shared build lock. Returned-code
faults do not establish genuine poisoned-context behavior. Tutorial/all24,
application speed, whole-device peak VRAM, PDF/log equivalence and scientific
acceptance are UNRUN for this patch. No numerical gate or tolerance changed.

External receipt archive and source/binary manifests are retained in the
coordinator evidence directory. Documentation-only publication must preserve
all source/test/CMake bytes of the frozen acceptance source.
