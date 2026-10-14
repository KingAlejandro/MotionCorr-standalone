# Exact-output CPU dose-weight experiment, 14 October 2026

Refs #10. Independent of the other agent's full-frame reusable FFT plans,
final inverse preservation copy, frame-buffer reuse and huge-page experiments.
The implementation changes only CPU dose weighting and its tests. Main reference:
`116eb04ad359cd5bf789b28809fc2047ea155b9b`. Final production/test commit:
`92882f27171b38c267c25cbb18b01284adf54f91`. Later evidence edits do not change code.

**Outcome:** promising kernel improvement with exact spectra and products;
**no demonstrated whole-job speed improvement** on this host. Keep draft for
review and a representative clean-host comparison, particularly cpu64/SCARF.

## What changed

The dose formula depends on ky squared, so positive/negative frequency rows
have identical scalar weights and normalization. Share those scalars, retaining
independent complex pixels. A 64-frequency tile permits contiguous application
within each frame, instead of jumping among movie allocations per frequency.
The frame-reduction order, scalar formulas, original complex operators, separate
multiply/divide passes and intermediate float stores are preserved. DC/Nyquist,
odd-height and tail handling are explicit. Scalar scratch per worker is
`(64*N + 64)*sizeof(RFLOAT)`: 12.5 KiB at N=24 and 32.5 KiB at N=64.
No frame-sized cache, FFT or interpolation change. See [design.md](design.md).

## Normal-data kernel measurements

`cpu_dose_bench` links the real production method and a frozen main reference
(`tests/cpu_dose_reference.h`). It has **no exp-call wrappers**. Each configuration
runs in one process, warms each arm once, alternates AB/BA for six measured pairs,
resets identical asymmetric input outside timing, and compares every output
complex value bit for bit. Fixtures are finite, non-subnormal spectra with signed
zeros; these are generated kernel inputs, not captured tutorial FFT arrays.

Wall medians, main/candidate:

- 512 x 512 x 64, j1: **0.300329 / 0.121932 s**. All six pairs faster.
- 512 x 512 x 64, j4: **0.105834 / 0.043703 s**. All six pairs faster.
- 3710 x 3838 x 24, j1: **4.114606 / 1.890950 s**, about 2.18x for this
  kernel. All six pairs faster; paired median **-2.243332 s**, descriptive
  96.875% interval **[-4.540798, -1.636822] s**.
- 3710 x 3838 x 24, j4: **2.873145 / 1.533395 s**. Five of six pairs faster;
  paired interval **[-1.559364, +0.258753] s** crosses zero, so unresolved.

The existing paired routines resolve the first three configurations within
these samples. These are **within-process descriptive statistics**, not independent
whole-job trials or a certified host-isolation verdict. Do not transfer these
seconds or ratios directly to the user's cpu64 47.7-second profile. All 28 kernel
pair comparisons, including warmups, have exact complex spectra. Raw runs,
CPU times, commands, affinity, source/binary hashes and summaries: `kernel-normal/`.

## Whole-movie measurements

Fresh matching Release builds, tutorial 3710 x 3838 x 24, 5x5, j4, dose weighting
+ save_noDW + even/odd, same input/gain, seed, CPU mask and environment. One
profiled warmup per arm is excluded, then three unprofiled alternating pairs:

- Main/candidate wall medians **55.629 / 55.462 s**.
- Paired candidate-minus-main deltas **-0.167, +2.019, -11.971 s**;
  median **-0.167 s**. No outlier removed. Three pairs cannot establish the
  kit's distribution-free median interval, which requires at least six.
  **No whole-job speed verdict or finite resolution is claimed.**
- Measured maximum process RSS **4,601,124 / 4,600,748 KiB** (about 4.388 GiB
  each). Largest measured paired increase: **0.0023%**. Including cold warmups,
  maxima are **4,601,124 / 4,621,664 KiB**, about 4.388 / 4.408 GiB, a roughly
  0.45% increase. This measures whole-process peaks, not just scalar scratch.
- All **four full product-tree comparisons pass**, including warmup, with
  the existing writer-clock/root normalization and log-timing/PDF-byte exclusions.
  No new exclusion or numerical tolerance was introduced.

The separate warmup profiles show weighting **2.376 / 0.974 s**. Their process
times are **92.238 / 45.625 s**, with substantial differences in unchanged
stages. These are diagnostic cold/warm observations, not a job speedup or a
replicated stage comparison. Raw results/profiles/logs: `whole-tutorial/`;
whole-run statistics and RSS: `summary.json`.

## Correctness and CI

- **1,680 focused bitwise cases pass**: tile boundaries/tails, DC/Nyquist,
  odd/even/tiny shapes, asymmetric rows, signed zeros, subnormal/nonfinite
  spectrum pixels, zero/nonuniform/scaled doses, one/four threads and 1/7/24/64
  frames. GNU/ELF wrappers witness `ny*nfx*N` exp calls in main and
  `(floor(ny/2)+1)*nfx*N` in production. These wrappers are absent from the
  benchmark binary. The independent frozen control rejects unchanged main's
  call count and prevents treating pixel symmetry as weight symmetry.
- Known-motion aggregate **PASS**, all default cases and j1/j4/dose variants.
  The existing `km_local_noisy` characterization accuracy remains **FAIL**;
  execution/backend, invariance and applied-image witnesses pass. Twelve complete
  output-tree comparisons to main pass. Alongside the four whole-movie pairs,
  **64 MRC/STAR file pairs** match exactly after existing normalization.
  `canonical-product-hashes.json` retains their normalized SHA256 values.
- [Native GitHub Linux CI run 510](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38645261718)
  is **green on final code `92882f2`**: **53/53 CTests**, known-motion aggregate,
  canonical fixture/digest preflight, smoke outputs and failure controls.
  CUDA and linked controls compile successfully. **No native GPU execution**.
  Full Ubuntu log and status are retained here. No native Mac/cpu64/SCARF
  execution or performance claim is made for this branch.

Local first-prototype CTest initially ran **43/53**. Two restored build helper
executables had mode 0644; eight tests failed to launch them or consequently
failed on helper invocation. Restoring execute bits on those two local ELF
outputs and rerunning the eight affected tests gave **8/8 PASS**. The remaining
`ProfilingKit` and `MultiGpuScheduling` failures also reproduce on fresh unchanged
main (**50/52**), due to the mounted `/proc` PID view disagreeing with child
namespaces. Initial failures and repair-run logs are retained, not waived. The
final tiled source separately passes its expanded control, known-motion checks,
whole-movie identity and all 53 tests on GitHub's native host.

## Earlier experiment and provenance

`row-only-stress/` preserves the initial row-pair-only prototype and all four
completed six-pair kernel populations. That harness deliberately contains a
subnormal real component at every 37th element. Timing was unresolved in every
configuration; some warmups were slower even though measured medians were lower.
The archived patch/harness, raw stderr and full JSON remain available. These
populations are **not pooled with normal-data results** and do not isolate the
causal benefit of tiling because the final normal fixture differs. There is no
final-tile subnormal-stress performance claim; subnormal bitwise controls pass.
An initial queued row-only whole-job run was paused before payload launch during
prototype iteration and supplies no measured samples.

`environment.json` maps the local and API-published commits with identical full
trees. All commits are attributed to the authenticated KingAlejandro identity.
The final binary SHA256 is
`2076a2d3629fd77f223626129f6435bcd93ce5ec480292886a6fd26df628f8c9`;
main is `373f61b5f45dcb14a79129517ff72c90f253dec4fbd5cbd4acb4e90a53bead25`.
Final unwrapped kernel binary:
`d1936756ab91d852f05fe71dec21c61ceb7b84debc2f4e06673dcb6ea4c49346`.

Both product builds use GCC 13.3, CMake 3.28.3, FFTW 3.3.10 and matching
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`, without fast-math. The host reports Intel
Xeon Platinum 8573C, eight CPUs of cgroup quota, nine visible IDs and an 8 GiB
memory limit; THP is `madvise`. Masks are 0/j1 and 0-3/j4. Kernel runs explicitly
use passive OpenMP waiting; whole jobs share identical inherited waiting policy.
Every timed acquisition takes `/tmp/motioncorr-bench.lock`, checks self affinity
inside a child and rejects compilers. Local builds, suites and other benchmarks
are finished before timing. Standard per-PID ownership and physical-host isolation
cannot be certified in this PID namespace, so this is **not clean mcprof evidence**.
Do not pool this host with cpu64, SCARF, or earlier sessions.

Next priorities and the limits of the bitwise contract:
[opportunities.md](opportunities.md). No merge or issue closure is requested.
