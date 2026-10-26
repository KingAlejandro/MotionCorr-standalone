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

## Local results, attempt 1 (historical, nonqualifying; evidence outside Git)

**Historical, NONQUALIFYING (attempt 1).** Host: macOS arm64 (AppleClang), Release, `-j2`, `OMP_NUM_THREADS=2`. This
block was produced with a stub `numpy` package on `PYTHONPATH` that bypassed the real-NumPy requirement in
`CMakeLists.txt`; the sentence "numpy is absent" was true only for the interpreter CMake chose, not for the host. Treat
every result in this block as superseded by the correction section below. Its mutant checks (call site passing
`false`, global leak, `pnx` replaced by the inherited value, capture-guard term removed) were run in attempt 1 only; the
saved `mut_*` logs contain configure/build output and no test verdicts, so the runtime kills are **UNVERIFIED**. Static
review of the tests supports that each defect would fail them; that is not a runtime result. UNRUN: the rest of the
CTest suite, CUDA, any movie, native byte neutrality, scientific accuracy.

## Correction: attempt 1 was limited; attempt 2 uses a real NumPy

Attempt 1 (above) configured with a stub `numpy` package on `PYTHONPATH`. That bypassed the real-NumPy requirement in
`CMakeLists.txt` and is **not qualifying evidence**; its logs are retained outside Git. "numpy is absent" was true only
for the interpreter CMake chose (`/opt/homebrew/bin/python3`), not for the host.

Attempt 2, source `634e4b48` (C++/test/CMake unchanged at that time; built from the live worktree with no as-built manifest, so source identity rests on the unchanged tree), fresh build directories, `PYTHONPATH` unset,
`-DPython3_EXECUTABLE=/Users/alex.konstantinov/.local/bin/python3` (CPython 3.13.7, NumPy 2.4.2,
`.../python3.13/site-packages/numpy/__init__.py`, sha256 `2e8da3e4385e79c4885b3f7324a8b957e6f01732b239e99e266a12c62a008b8d`), `-j2`, `OMP_NUM_THREADS=2`:

- Default build: `LocalFullWidthWeight`, `IsotropicWeight`, `GlobalHalfGain`, `CoupledPeak`, `PatchRetryState`,
  `ExperimentalFlagsCli` pass (6/6).
- `MC_EXPERIMENT_CCF_DC=ON`, `MC_EXPERIMENT_CCF_DC_ARM=none`, first run (4 selected tests): `CcfDcHook`,
  `ExperimentalFlagsCli`, `LocalCcfCaptureCli` passed and `LocalFullWidthWeight` was **Not Run** because its target was
  not yet built in that tree (3 PASS + 1 Not Run, not 4/4). After building that target, a separate run of
  `LocalFullWidthWeight` passed.

Tested: weight values, global/local selection, global estimates on the analytic fixture with the flag on or off, the log
witness, and CLI refusals. UNRUN: full-movie and global-trajectory byte neutrality, the rest of CTest, CUDA, any
movie, native pilot, scientific accuracy. The combination with `--experimental_local_b2` is UNRUN and untested; the pilot
keeps B2 off. The stub attempt supports no qualification claim.

## Attempt 3: clean archive of `5bcfa987`, DC registration check

`5bcfa987` adds one CMake property (`LocalFullWidthWeight` sets `MC_EXPERIMENT_CCF_DC_ARM=none` in DC builds) and docs; its
`src/` and `tests/` are byte-identical to `634e4b48`. A `git archive` of exactly that commit was extracted to a new
scratch directory; all 11641 extracted files matched their Git blob hashes before and after the build (no `MISMATCH`).
Real interpreter as in attempt 2 (NumPy 2.4.2), no stub, `PYTHONPATH` unset, `-DMC_EXPERIMENT_CCF_DC=ON`, targets
`motioncorr local_full_width_weight ccf_dc_hook` only, `-j2`, `OMP_NUM_THREADS=2`, caller `MC_EXPERIMENT_CCF_DC_ARM` unset.
`ctest -R '^(LocalFullWidthWeight|CcfDcHook|ExperimentalFlagsCli|LocalCcfCaptureCli)$'` exit 0, 4/4 passed. The new test
runs without the caller exporting the arm; control: the bare binary with the arm unset aborts (exit 134). Binary sha256
(motioncorr / local_full_width_weight / ccf_dc_hook): `64f00132...`, `801825d9...`, `b6d54782...`. The default-build 6/6
result remains attempt 2's, at the `634e4b48` tree. Full-movie and global-trajectory byte neutrality, the rest of CTest,
CUDA and any movie remain UNRUN. Source-level clearance is conditional and is not a merge or scientific claim.
