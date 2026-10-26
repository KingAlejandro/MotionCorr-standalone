# Global half-gain damping: default-off research prototype (not for merge)

**Result.** With `--experimental_global_half_gain --max_iter 50 --experimental_align_tolerance 1e-9` (arm c) the
retained #267 FAIL cases `integer`, `fractional` and `affine` meet the unchanged 0.20/0.40/0.80 Å limits natively on CPU.
`pedestal` and `noisy` still FAIL; `flat` and `repeated` stay UNIDENTIFIABLE. The matched control without damping
(arm d, same budget, gain 1) fixes none of them, so the change comes from the damping and not from the longer budget.
At the production stop (arm b, 5 iterations / 0.5 px) only `affine` newly passes; `integer` gets worse (0.264 to 0.326 Å RMS)
and `noisy` gets worse (max 9.9 to 19.0 Å). Flags off, the products are identical to e77a51a2.
This is research evidence on one synthetic family. It is not adoption, not a stopping-rule proposal and not CUDA evidence.

## Change (source `a1c78adc`, tests/evidence `318dc481` and later; runner source unchanged between them)

- `--experimental_global_half_gain`: in `MotioncorrRunner::alignPatch`, after "Set origin" and the unscaled sumsq accumulation, `cur_x/cur_y *= 0.5` for the global alignment only. The scaling precedes both the accumulation into `x/yshifts` and the Fourier re-shift. The RMSD stop still uses the unscaled sumsq.
- `--experimental_align_tolerance <px>`: replaces the hard-coded 0.5 px stop **of the global alignment only**. Applying it to local patches would make nearly every patch non-converged and skipped at 1e-9, which would confound arms c/d; W5's replay also used captured patch candidates at the production stop. `--max_iter` is unchanged and still applies to local patches too, so arms c/d give local patches up to 50 iterations at the 0.5 px stop. Arm d has the same local budget as arm c.
- Both flags are CPU-only. With `--gpu` they are refused in `initialise()` before the device query (CPU-only and CUDA builds alike); without `--use_own` or with a non-positive/non-numeric tolerance they are rejected. The alignPatch region at e77a51a2 is byte-identical to the 805d9de2 region W5 used (checked by extracting both functions and diffing).

## Arm table (cpu64, CPUs 48-55, #267 eight cases, unchanged `eval_v2.py` / `check_motion_diagnostics.py`)

All 8 native runs per arm exited 0. Scores are the field parsed from the serialized STAR (6 significant digits for global shifts), fixed ROI, 0.885 Å/px,
RMS / p95 / max Å against 0.20 / 0.40 / 0.80. Cell = checker status / field gate, then RMS / p95 / max.

| Arm | checker PASS / FAIL / UNIDENTIFIABLE / other | field-gate PASS (of 8) | native exits |
|---|---|---|---|
| a0-base-flagsoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| a-cand-flagsoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| b-half-prod | 2 / 4 / 2 / 0 | 2 | [0, 0, 0, 0, 0, 0, 0, 0] |
| c-half-long | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |
| d-gain1-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |

| Case | a0-base-flagsoff | a-cand-flagsoff | b-half-prod | c-half-long | d-gain1-long |
|---|---|---|---|---|---|
| zero | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 |
| integer | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.325549 / 0.434555 / 0.434555 | PASS/PASS 0.177743 / 0.378286 / 0.378286 | FAIL/FAIL 0.392654 / 0.573054 / 0.573054 |
| fractional | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.273674 / 0.404167 / 0.404167 | PASS/PASS 0.046840 / 0.062306 / 0.062306 | FAIL/FAIL 0.428876 / 0.682875 / 0.682875 |
| affine | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | PASS/PASS 0.165893 / 0.323365 / 0.750467 | PASS/PASS 0.175520 / 0.337342 / 0.634428 | FAIL/FAIL 0.257860 / 0.504353 / 0.597196 |
| pedestal | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 |
| noisy | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.799221 / 5.876730 / 19.018634 | FAIL/FAIL 1.988823 / 4.225033 / 10.980241 | FAIL/FAIL 2.060526 / 4.394210 / 11.950092 |
| flat | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 |
| repeated | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 6.740209 / 8.831312 / 8.831312 | UNIDENTIFIABLE/FAIL 4.395413 / 5.842215 / 5.842215 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 |

- a0 = e77a51a2 binary, a = candidate binary, both flags off, both through the unchanged C1 driver (`c1_run_v2_cases.py`).
- **(a) reproduces C1 CPU K267 exactly**: 1 PASS / 5 FAIL / 2 UNIDENTIFIABLE, field metrics equal a0 bit for bit and equal `synth_combined/evidence/v2-comb-cpu-none.eval.json` (max abs difference 0.0 in all 8 cases; `results/arm_table.json`).
- b/c/d use `scripts/ds_run_v2_cases.py`: the C1 driver with only an `EXTRA` argument appended (`ds_run_v2_cases.diff`).
- Pedestal is identical in every arm (2.119133 Å): its error does not depend on the global update.
- Retained FAIL cases passing: **b** affine; **c** integer, fractional, affine; **d** none.

## Flags-off identity to e77a51a2 (no difference found)

| Check | Result |
|---|---|
| Full CPU CTest, candidate Release build | 92 tests, 91 passed, 1 skipped (`CompressedMrcStatus_bz2`: pbzip2 absent on cpu64, repo waiver), 0 failed; `validate_test_collection` rc 0, `test_ci_fail_closed` rc 0 |
| #267 eight cases, a vs a0 | field metrics and checker statuses equal |
| Known-motion fixtures (4 non-heavy cases x j1/dose-weighted/j4, `run_known_motion_gates.py`), base vs candidate | IDENTICAL: 193 files, 88 gated (MRC header 0-223 + pixels, STAR, EPS after path normalisation), 0 differing; gate verdicts equal (3 PASS, `km_local_noisy` FAIL in both, as at base) |
| Repo synthetic movie (`synthetic_movie.tiff`, 3x3 patches, dose weighting, j1), base vs candidate | IDENTICAL: 14 files, 7 gated, 0 differing (MRC label block 224-1023 holds the timestamp and is not gated) |
| Negative control: same movie, candidate with the flag on | DIFFERS (7 of 7 gated), so the comparator can see a change |

## Tests

- `GlobalHalfGain` (operator level, runs production `alignPatch` on a 5-frame periodic fixture): the first global update with the flag is exactly 0.5x the unflagged one (`==`), iteration-1 RMSD line identical, re-shifted frames bitwise equal to the reference shifted by the half update, local patches untouched, tolerance override global-only. Six mutants were built and run (`mutants.sh`, `results/mut/`): accumulate-only, re-shift-only, scaled sumsq, damp local, tolerance on local, factor 0.6. All six fail the test; the restored source passes. Without the source change the test does not compile.
- `ExperimentalFlagsCli`: `--gpu 0` with either flag is refused with the CPU-only message before any device query; the same flags without `--gpu` are not refused; bad tolerances (`0`, `-1`, `abc`, `nan`, `inf`) and use without `--use_own` are rejected. It runs in CPU-only builds. No CUDA build was configured, so the refusal is **UNRUN on a CUDA build** (same code path, but not executed there).
- The two tests are not added to `validate_test_collection.py`'s required list (prototype; no tool changed).

## Not run / limitations

- **Runtime (unrounded) field: UNRUN.** e77a51a2 has no runtime-model capture (`MC_DIAG_*` is not in `src/`). Only STAR-serialized scores exist. W5 found runtime and STAR scores within about 3e-5 Å RMS on its fixtures (largest: affine double-gain1-5it, 0.320006 vs 0.319982), far inside the limits, but that is not measured here.
- **Native N=9/13/20 and phase-ramp vel0/vel1 controls: UNRUN.** No generator in the repo produces them; W5 used offline replay. The only native N=5 fixtures are the #267 `integer`/`fractional` cases. W5 recorded production-stop regressions at larger N (vel0 isotropic N13/N20 PASS to FAIL) that this run cannot confirm or exclude.
- Native results do not match W5's offline numbers cell by cell (e.g. arm c integer 0.178 Å here, 0.074 Å in W5 map32); native b integer fails like W5's double-map replay and native b fractional fails like its map32 replay. The offline replay is not a native reproduction.
- One synthetic fixture family, 5 frames, one run per arm (the CPU build is bit-deterministic, so repeats would not add information). `noisy` worsens at the production stop and `pedestal` is unaffected.
- CPU only. No GPU, no 4GPUs, no CUDA build. CPU/CUDA agreement is not addressed. No default, gate, ROI, tolerance or checker changed.

## Provenance

- Base `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; candidate source `a1c78adc1d0ffcf031102bc0dad605c4fb670a1f` (C++ sources identical in later commits on the branch; later commits add a CLI-test wording fix and these files).
- Binaries (Release, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, CUDA=OFF): base `7d9fd428...c9c9`, candidate `cee711f8...5d4c` (full hashes in `results/build-*.binaries.sha256`). Fixture hashes: `results/v2/receipts/fixtures.sha256`.
- Host `small-refmac-machine` (cpu64), `Cpus_allowed_list: 48-55` (receipt `results/v2/receipts/env.txt`), `flock -n /tmp/motioncorr-damping-cpu48-55.lock`, no foreign process above 5% on the lane at start, cmake and Python from `~/.mc-venv`. Scratch `/tmp/motioncorr-damping-a1c78adc1d0f`, 829 MB. Source staged with `git archive`; no copied build tree.
- Build: `MC_REQUIRE_ALL_DECODERS` left OFF because pbzip2 is absent on cpu64 (explicit repo waiver).
- Commands: `scripts/build.sh`, `scripts/run_arms.sh`, `scripts/flagsoff.sh`, `scripts/ctest_cpu.sh`, `scripts/mutants.sh`, `scripts/summarize.py` (driven by `scripts/chain.sh`); exit codes in `results/chain.log`, `results/v2/receipts/*.exit`, `results/flagsoff/receipts/`.

## Retained failures and corrections

1. First configure used `MC_REQUIRE_ALL_DECODERS=ON`: failed on missing pbzip2 (twice, one of them with a stale script). Rebuilt with the waiver.
2. First `run_arms` launch failed at fixture generation because `python -I` hides the generator's sibling module (exit 2, no native run). Re-run without `-I`, as C1's `c1_v2.sh` does.
3. `ExperimentalFlagsCli` first failed on the wording for a non-numeric tolerance (`textToFloat` rejects it before my check); test loosened, source unchanged.
4. First full CTest (`results/ctest-cand-attempt1.log`): `CiFailClosedControls` failed (tests 5, 6, 8). Cause: my own known-motion flags-off step regenerated tracked ground-truth JSON inside the staged tree, and a `git archive` tree has no git metadata. Not caused by the change. Fixtures were restored from the commit, a git repo was initialised over the staged tree, and the whole suite was re-run: 0 failed.
5. First synthetic-movie comparison read the movie from `src-base/` and `src-cand/`; outputs mirror the input path, so the trees differed only by that path (`results/flagsoff/synth-compare-attempt1.json`). Re-run from one shared input path: IDENTICAL. The known-motion comparison ran in the first `flagsoff.sh` pass (commit 318dc481); only the synthetic part was re-run, with `FLAGSOFF_ONLY=synth`.
