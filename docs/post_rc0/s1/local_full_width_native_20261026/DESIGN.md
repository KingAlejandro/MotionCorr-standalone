# Default-off local full-width CCF weight (CPU research prototype)

Base `42af5406` (production source unchanged since `927a6890`). Status: implementation under review; **no native run, no
movie, no scientific claim**.

## Premise (not acceptance)

The sealed saved-state screen
([report](../local_full_width_frequency_20261026/README.md)) changed only the local x-frequency denominator `22 -> 42`
(`nfx = pnx/2+1 -> pnx`) in a two-patch joint-objective diagnostic. Selected-point RMS fell `6.72 -> 1.27 px`
(bad patch) and `1.28 -> 1.00 px` (central). This is NOT_REFUTED_ON_TWO_EXPOSED_PATCHES. Native iteration, full field,
actual STAR and harm controls are UNRUN. Original C9 margin FAIL stands; no gate or tolerance is relaxed here.

## Change

`--experimental_local_full_width_weight`, default off, CPU `--use_own` only.

- Only when the flag is on **and** `!is_global`, `alignPatch` evaluates `ccfWeightAt` with `x_norm = pnx` instead of
  `nfx`. `ccfWeightAt`, its operation order, the y normalisation, B, DC, peak estimator, reference construction,
  iteration/stopping, fitting/rejection, gauge, ROI and publication are untouched.
- The selection stays in `ccfWeightXNorm`, which gains a defaulted fifth argument. Existing callers/tests are unaffected.
- Global alignment is bit-identical with the flag either way, including when `--experimental_isotropic_weight`
  (the harmful global arm) is selected. That arm is preserved, not replaced.
- Refused before any movie access: with `--gpu` (same guard block as the other CPU-only flags), without `--use_own`,
  and under the fixed-scope `MC_DIAG_LOCAL_CCF_DIR` capture, whose unsupported-combination guard now lists the flag
  (capture with the flag off is unchanged). No CUDA weight is implemented.
- **Intentional flagged log difference.** With the flag on, each patch `alignPatch` call writes one line to the per-movie
  log, before the weight loop and outside OpenMP:
  `" EXPERIMENTAL local full-width weight: x_norm = <weight_x_norm>, pnx = <pnx>, nfx = <nfx>"`. It uses the values
  actually selected for the weight. Flag off writes no line; a global alignment never writes it, so a global-only run
  (1x1 patches, no local stage) has zero such lines and a 3x3 run has one per patch alignment call. Products, files and
  defaults are otherwise unchanged. The line is a reach witness, not evidence of accuracy.

## Test plan (criteria fixed before results)

1. `LocalFullWidthWeight` (C++, analytic, no movie):
   a. Flag OFF: `ccfWeightXNorm` returns `nfx` for local and global; weights at 42x32 sample bins equal an
      independently coded inherited formula bitwise (float32), including `x_norm = 22`.
   b. Flag ON local: x_norm equals `pnx` on non-square geometries (42x32, 128x96, 64x48); weights equal the literal
      physical `exp(-2 B ((ky/pny)^2 + (kx/pnx)^2))` in float32, and a frequency pair with the same physical kx/pnx
      but different pnx maps to equal weights.
   c. Flag ON global, with and without the global isotropic flag: x_norm is identical to the flag-off value.
   d. Integration through `alignPatch`: local ON differs from local OFF; local ON equals the global
      isotropic arm bitwise on the same stack (same `x_norm = pnx`, nothing else differs in `alignPatch`), which
      fails if `nfx`, `pnx/2`, or `pnx/2+1` is used; the log witness equals the actual `x_norm/pnx/nfx` for local ON and is
   absent for local OFF and for every global arm; global results are bitwise equal with the flag on or off, with and
      without the isotropic flag; default is off.
2. `LocalCcfCaptureCli` (DC build): the flag is an unsupported scope under `MC_DIAG_LOCAL_CCF_DIR`; a control with the
   exact scope reaches the missing input. `ExperimentalFlagsCli` additions: `--gpu 0` refused first; non-`--use_own` rejected; a valid CPU configuration
   reaches the ordinary missing-input failure; the flag together with `--experimental_isotropic_weight` is not refused.
3. Existing `IsotropicWeight`, `GlobalHalfGain`, `CoupledPeak`, `ExperimentalFlagsCli` and local-capture CLI tests keep
   their original criteria.

Compilation and these tests do not establish byte neutrality of a movie run or scientific accuracy. Native pilot
(`.20/.40/.80 A` field gates, runtime vs actual STAR, N5/9/13/20, harmful global-isotropic 20-frame control) needs
source review, trusted venue access and parent-frozen inputs; none is authorised by this change.

## Local results at the source pin (informational; see the evidence index outside Git)

Host: macOS arm64 (AppleClang), Release, `-j2`, `OMP_NUM_THREADS=2`. numpy is absent, so configure used a stub `numpy`
package on `PYTHONPATH` outside the repository; only tests that do not need numpy were run. `LocalFullWidthWeight`,
`IsotropicWeight`, `GlobalHalfGain`, `CoupledPeak`, `PatchRetryState`, `ExperimentalFlagsCli` passed (default build);
`LocalCcfCaptureCli`, `CcfDcHook`, `ExperimentalFlagsCli` passed (`MC_EXPERIMENT_CCF_DC=ON`, arm `none`). Mutants caught:
call site passing `false` (integration test), global leak in the selection, `pnx` replaced by the inherited value
(weight test), capture-guard term removed (`LocalCcfCaptureCli`). UNRUN: the rest of the CTest suite, CUDA, any movie,
native byte neutrality, scientific accuracy.
