# Global peak/update alternatives: default-off research prototypes (not for merge)

Two separate default-off CPU-only options on one branch: (1) global half-gain damping with a tolerance override, scored against the independent challenge that rated it NO-GO; (2) hypothesis H2, a coupled 2x2-Hessian subpixel peak, scored against its frozen predictions. Sections below: summary, half-gain, challenge scorecard, H2, flags-off identity, limitations, provenance.

**Half-gain result.** With `--experimental_global_half_gain --max_iter 50 --experimental_align_tolerance 1e-9` (arm c) the
retained #267 FAIL cases `integer`, `fractional` and `affine` meet the unchanged 0.20/0.40/0.80 Å limits natively on CPU.
`pedestal` and `noisy` still FAIL; `flat` and `repeated` stay UNIDENTIFIABLE. The matched control without damping
(arm d, same budget, gain 1) fixes none of them, so the change comes from the damping and not from the longer budget.
At the production stop (arm b, 5 iterations / 0.5 px) only `affine` newly passes; `integer` gets worse (0.264 to 0.326 Å RMS)
and `noisy` gets worse (max 9.9 to 19.0 Å). Flags off, the products are identical to e77a51a2.
This is research evidence on one synthetic family. It is not adoption, not a stopping-rule proposal and not CUDA evidence.

## Summary

| Candidate | Retained FAIL cases newly meeting 0.20/0.40/0.80 Å (STAR, native CPU) | Main harm / caveat |
|---|---|---|
| Half-gain, production stop (b) | affine | integer 0.264 to 0.326 Å RMS; noisy RMS 2.34 to 2.80, max 9.9 to 19.0 |
| Half-gain + 50 iterations / 1e-9 (c) | integer, fractional, affine | diagnostic budget, not the production stop; noisy max 9.9 to 11.0; the matched gain-1 control (d) fixes none |
| H2 coupled peak, production stop (all / global) | none | integer 0.264 to 0.446 Å RMS (worse); fractional 0.524 to 0.496; affine 0.402 to 0.315 / 0.267 |
| H2 coupled peak + 50 iterations / 1e-9 (all / global) | none | integer 0.379 (max 0.823); fractional 0.359; affine 0.189 / 0.221 (still FAIL); noisy improves |

Both are research evidence on one 5-frame synthetic family. Limitations are listed below; flags-off products are identical to e77a51a2 for both binaries.

## Half-gain change (source `a1c78adc`, tests/evidence `318dc481` and later; runner source unchanged between them)

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

Combined table with the H2 arms (same lane, driver, evaluator; controls a and d from the half-gain pass were not rerun; `h2-flagsoff` is the new binary with flags off):

| Arm | checker PASS / FAIL / UNIDENTIFIABLE / other | field-gate PASS (of 8) | native exits |
|---|---|---|---|
| a-cand-flagsoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2-flagsoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| b-half-prod | 2 / 4 / 2 / 0 | 2 | [0, 0, 0, 0, 0, 0, 0, 0] |
| c-half-long | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |
| d-gain1-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2all-prod | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2glob-prod | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2all-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2glob-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |

| Case | a-cand-flagsoff | h2-flagsoff | b-half-prod | c-half-long | d-gain1-long | h2all-prod | h2glob-prod | h2all-long | h2glob-long |
|---|---|---|---|---|---|---|---|---|---|
| zero | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 |
| integer | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.325549 / 0.434555 / 0.434555 | PASS/PASS 0.177743 / 0.378286 / 0.378286 | FAIL/FAIL 0.392654 / 0.573054 / 0.573054 | FAIL/FAIL 0.446108 / 0.645090 / 0.645090 | FAIL/FAIL 0.446108 / 0.645090 / 0.645090 | FAIL/FAIL 0.378577 / 0.823228 / 0.823228 | FAIL/FAIL 0.378577 / 0.823228 / 0.823228 |
| fractional | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.273674 / 0.404167 / 0.404167 | PASS/PASS 0.046840 / 0.062306 / 0.062306 | FAIL/FAIL 0.428876 / 0.682875 / 0.682875 | FAIL/FAIL 0.496160 / 0.681394 / 0.681394 | FAIL/FAIL 0.496160 / 0.681394 / 0.681394 | FAIL/FAIL 0.358772 / 0.505934 / 0.505934 | FAIL/FAIL 0.358772 / 0.505934 / 0.505934 |
| affine | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | PASS/PASS 0.165893 / 0.323365 / 0.750467 | PASS/PASS 0.175520 / 0.337342 / 0.634428 | FAIL/FAIL 0.257860 / 0.504353 / 0.597196 | FAIL/FAIL 0.315415 / 0.594961 / 0.903561 | FAIL/FAIL 0.267061 / 0.504069 / 0.830987 | FAIL/FAIL 0.189143 / 0.409459 / 0.817548 | FAIL/FAIL 0.221027 / 0.412843 / 0.582922 |
| pedestal | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 |
| noisy | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.799221 / 5.876730 / 19.018634 | FAIL/FAIL 1.988823 / 4.225033 / 10.980241 | FAIL/FAIL 2.060526 / 4.394210 / 11.950092 | FAIL/FAIL 2.184854 / 4.115589 / 7.167637 | FAIL/FAIL 2.115487 / 4.031991 / 6.757304 | FAIL/FAIL 1.771371 / 3.668836 / 9.375074 | FAIL/FAIL 1.778466 / 3.631657 / 9.302432 |
| flat | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 |
| repeated | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 6.740209 / 8.831312 / 8.831312 | UNIDENTIFIABLE/FAIL 4.395413 / 5.842215 / 5.842215 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 |

## Flags-off identity to e77a51a2 (no difference found; half-gain binary `cee711f8`)

| Check | Result |
|---|---|
| Full CPU CTest, candidate Release build | 92 tests, 91 passed, 1 skipped (`CompressedMrcStatus_bz2`: pbzip2 absent on cpu64, repo waiver), 0 failed; `validate_test_collection` rc 0, `test_ci_fail_closed` rc 0 |
| #267 eight cases, a vs a0 | field metrics and checker statuses equal |
| Known-motion fixtures (4 non-heavy cases x j1/dose-weighted/j4, `run_known_motion_gates.py`), base vs candidate | IDENTICAL: 193 files, 88 gated (MRC header 0-223 + pixels, STAR, EPS after path normalisation), 0 differing; gate verdicts equal (3 PASS, `km_local_noisy` FAIL in both, as at base) |
| Repo synthetic movie (`synthetic_movie.tiff`, 3x3 patches, dose weighting, j1), base vs candidate | IDENTICAL: 14 files, 7 gated, 0 differing (MRC label block 224-1023 holds the timestamp and is not gated) |
| Negative control: same movie, candidate with the flag on | DIFFERS (7 of 7 gated), so the comparator can see a change |

## Half-gain tests

- `GlobalHalfGain` (operator level, runs production `alignPatch` on a 5-frame periodic fixture): the first global update with the flag is exactly 0.5x the unflagged one (`==`), iteration-1 RMSD line identical, re-shifted frames bitwise equal to the reference shifted by the half update, local patches untouched, tolerance override global-only. Six mutants were built and run (`mutants.sh`, `results/mut/`): accumulate-only, re-shift-only, scaled sumsq, damp local, tolerance on local, factor 0.6. All six fail the test; the restored source passes. Without the source change the test does not compile.
- `ExperimentalFlagsCli`: `--gpu 0` with either flag is refused with the CPU-only message before any device query; the same flags without `--gpu` are not refused; bad tolerances (`0`, `-1`, `abc`, `nan`, `inf`) and use without `--use_own` are rejected. It runs in CPU-only builds. No CUDA build was configured, so the refusal is **UNRUN on a CUDA build** (same code path, but not executed there).
- The two tests are not added to `validate_test_collection.py`'s required list (prototype; no tool changed).

## Independent challenge to half-gain (`challenge/REVIEW.md`, SHA256 `9a77c550...005941f5`) scored against the native arms

The review rates fixed 0.5 damping NO-GO. Half-gain is reported here as a candidate the challenge rejected; nothing was tuned.

| Challenge claim | Native result | Verdict |
|---|---|---|
| Harm on `noisy` at the production stop | b: RMS 2.343 to 2.799 Å (+19.5%), max 9.904 to 19.019 Å (+92%) | confirmed |
| `noisy` also suffers at the long budget | c vs a: RMS 1.989 (better), max 10.980 (worse); c vs matched control d: RMS 2.061 and max 11.950 (c better on both) | not confirmed against the matched control |
| Production-stop failures remain (integer double-map, fractional map32) | b: integer FAIL 0.3255 (and worse than a, 0.2636); fractional FAIL 0.2737 | confirmed |
| `affine` fails at the production stop (map32 0.2004) | b: affine PASS 0.1659 / 0.3234 / 0.7505 | contradicted (natively it passes) |
| Early 0.5 px stops make `--max_iter 50` alone equal `--max_iter 5` | no arm runs half-gain with `--max_iter 50` and the default tolerance, and the unchanged driver suppresses iteration logs | not tested |
| The N=5 instability is a peak-definition defect, not an update-gain defect | H2 below does not repair integer/fractional, though it lowers RMS against the matched control d on integer, fractional, affine and noisy | not supported as a sufficient cause on these fixtures |
| NO-GO for a half-gain prototype | at the production stop half-gain is not a repair (integer and noisy worse); only at the diagnostic budget does it newly pass cases, and arm d shows that is the damping | NO-GO stands for production use; the research prototype exists under the bounded contract |
## H2: coupled 2x2-Hessian peak (`--experimental_coupled_peak {off,global,all}`, source `700d0c6d`)

Spec and predictions: [H2-coupled-peak-PREDICTION.md](H2-coupled-peak-PREDICTION.md), copied verbatim; SHA256 `00e77b0e1205583a04a451a0a7fca1069beac4d30b57108d5a419ab8d178c583` verified against the orchestrator's copy and `H2-FREEZE.sha256`.

**Implementation.** The inherited separable fit is the "Quadratic interpolation by Jasenko" block in `MotioncorrRunner::alignPatch` (CPU path). It is left in place and runs first. With the option on, `MotioncorrRunner::coupledPeakOffset` computes the full quadratic on the same 3x3 CCF samples (H_xx, H_yy second differences, H_xy corner stencil / 4, g central differences, offset -H^-1 g) and replaces the result only when H is negative definite (H_xx < 0, det H > 0) and |delta| <= 1 px per component; otherwise the separable result stands. Guard-fire counts go to stdout (and the logfile) per `alignPatch` call as `[coupled_peak] scope=... peaks=N guard_fired=M (not_negative_definite=.., offset_gt_1px=..)`. `global` applies it to the global alignment only, `all` to global and patch peaks. CUDA refuses it (`initialise()`, before the device query). The half-gain code is unchanged.

**Tests.** `CoupledPeak` fits exact tilted quadratic peaks with known offsets: the coupled estimate recovers them to about 1e-16 while the verbatim separable fit misses by 0.13 to 0.34 px at rho = +/-0.756 (and is exact at rho = 0, as a control). It also checks the guard (positive definite, saddle, indefinite, flat, offset > 1 px rejected, 0.98 px accepted) and, through the production `alignPatch`, that `off` equals the default, `global` changes global peaks only, and `all` also changes patch peaks, with counts. Eight mutants (drop H_xy, flip its sign, wrong stencil scale, no negative-definite guard, no offset guard, swapped axes, `global` leaking to patches, estimate never applied) all fail the test and the restored source passes (`mutants_h2.sh`, `results/mut-h2/`). `ExperimentalFlagsCli` now also covers the new option (refused with `--gpu` before the device query, bad values and use without `--use_own` rejected). The refusal is UNRUN on a CUDA build.

### Prediction scorecard (STAR-serialized scores, unchanged checker, ROI and limits; runtime field UNRUN)

| # | Prediction | Native result | Verdict |
|---|---|---|---|
| 1 | Flags off: products and metrics identical to e77a51a2 / C1 K267 (1 PASS / 5 FAIL / 2 UNIDENTIFIABLE) | `h2-flagsoff` equals arm a bit for bit on all 8 cases (1/5/2); full CPU CTest 93 tests, 92 passed, 1 skipped (pbzip2), 0 failed; known-motion trees IDENTICAL (193 files, 88 gated); synthetic movie IDENTICAL (7 gated); flag-on negative control differs | confirmed |
| 2a | Integer and fractional: field RMS decreases at the production stop | integer 0.2636 to 0.4461 Å (up); fractional 0.5241 to 0.4962 Å (down) | **falsified** (integer worsens; fractional improves only slightly) |
| 2b | At least one of integer/fractional meets 0.20/0.40/0.80 Å in runtime and STAR at 50 iterations / 1e-9 | integer 0.3786 / 0.8232 / 0.8232 FAIL; fractional 0.3588 / 0.5059 / 0.5059 FAIL (STAR); runtime UNRUN | **falsified** on STAR |
| 3 | Affine still FAILS; any improvement reported, not a cure | affine FAIL in all four arms; RMS 0.4024 to 0.3154 / 0.2671 (prod all / global) and 0.1891 / 0.2210 (long all / global); `h2glob-long` max 0.583 but RMS 0.221 and p95 0.413 exceed the limits | confirmed |
| 4 | Zero stays PASS; flat and repeated stay UNIDENTIFIABLE | zero PASS 0.000000 in every arm; flat and repeated UNIDENTIFIABLE in every arm | confirmed |
| 5 | Harm check, full report, no threshold chosen afterwards | regressions vs flags-off: integer RMS and max up in all four arms (0.264 to 0.446 / 0.379; max 0.432 to 0.645 / 0.823); repeated RMS 16.534 to 16.607 in the two long arms (same value as control d, UNIDENTIFIABLE). Improvements: noisy RMS and max down in all four arms (2.343 to 2.185 / 2.115 prod, 1.771 / 1.778 long; max 9.904 to 7.168 / 6.757 prod, 9.375 / 9.302 long); fractional and affine down. Pedestal bitwise unchanged | reported |
| 6 | CPU/CUDA agreement not assessed | not assessed | n/a |

The frozen falsification rule (neither integer nor fractional improves at the production stop, or noisy worsens in both RMS and max) is **not** triggered: fractional improves slightly and noisy improves. Predictions 2a and 2b are nevertheless falsified, and no retained FAIL case newly passes in any H2 arm, so H2 is not a repair on this family. Against the matched long-budget control d (gain 1, same budget) the H2 long arms lower RMS on integer (0.393 to 0.379), fractional (0.429 to 0.359), affine (0.258 to 0.189 / 0.221) and noisy (2.061 to 1.771 / 1.778), with a worse integer max (0.573 to 0.823). The 0.083 px float32 pedestal deadzone the prediction names as a possible limit is consistent with the pedestal, flat and repeated rows (guard fires on every peak) but was not isolated here.

`all` and `global` agree exactly on integer, fractional, zero, flat, repeated and pedestal (global-only cases or no patch peaks accepted), and differ on affine and noisy, where patch peaks matter.

### Guard fires (peaks falling back to the separable result / peaks fitted, summed over iterations)

| Case | h2all-prod / h2glob-prod | h2all-long | h2glob-long |
|---|---|---|---|
| zero | global 0/5 (0 not-neg-def, 0 >1px) (h2glob-prod: global 0/5 (0 not-neg-def, 0 >1px)) | global 0/5 (0 not-neg-def, 0 >1px) | global 0/5 (0 not-neg-def, 0 >1px) |
| integer | global 0/25 (0 not-neg-def, 0 >1px) (h2glob-prod: global 0/25 (0 not-neg-def, 0 >1px)) | global 7/250 (0 not-neg-def, 7 >1px) | global 7/250 (0 not-neg-def, 7 >1px) |
| fractional | global 0/25 (0 not-neg-def, 0 >1px) (h2glob-prod: global 0/25 (0 not-neg-def, 0 >1px)) | global 4/250 (1 not-neg-def, 3 >1px) | global 4/250 (1 not-neg-def, 3 >1px) |
| affine | global 0/15 (0 not-neg-def, 0 >1px) + patch 0/70 (0 not-neg-def, 0 >1px) (h2glob-prod: global 0/15 (0 not-neg-def, 0 >1px)) | global 6/250 (0 not-neg-def, 6 >1px) + patch 1/60 (0 not-neg-def, 1 >1px) | global 6/250 (0 not-neg-def, 6 >1px) |
| pedestal | global 5/5 (5 not-neg-def, 0 >1px) + patch 45/45 (45 not-neg-def, 0 >1px) (h2glob-prod: global 5/5 (5 not-neg-def, 0 >1px)) | global 5/5 (5 not-neg-def, 0 >1px) + patch 45/45 (45 not-neg-def, 0 >1px) | global 5/5 (5 not-neg-def, 0 >1px) |
| noisy | global 2/25 (1 not-neg-def, 1 >1px) + patch 4/140 (2 not-neg-def, 2 >1px) (h2glob-prod: global 2/25 (1 not-neg-def, 1 >1px)) | global 11/250 (4 not-neg-def, 7 >1px) + patch 2/140 (1 not-neg-def, 1 >1px) | global 11/250 (4 not-neg-def, 7 >1px) |
| flat | global 5/5 (5 not-neg-def, 0 >1px) (h2glob-prod: global 5/5 (5 not-neg-def, 0 >1px)) | global 5/5 (5 not-neg-def, 0 >1px) | global 5/5 (5 not-neg-def, 0 >1px) |
| repeated | global 20/20 (20 not-neg-def, 0 >1px) (h2glob-prod: global 20/20 (20 not-neg-def, 0 >1px)) | global 30/30 (30 not-neg-def, 0 >1px) | global 30/30 (30 not-neg-def, 0 >1px) |

Pedestal, flat and repeated fire on every peak (H not negative definite: float32 pedestal or degenerate CCF peaks), so H2 is the inherited estimator there by construction. Integer and fractional never fire at the production stop (0 of 25 each) and fire 7/250 and 4/250 at the long budget.

## Not run / limitations (half-gain and H2)

- **Runtime (unrounded) field: UNRUN.** e77a51a2 has no runtime-model capture (`MC_DIAG_*` is not in `src/`). Only STAR-serialized scores exist. W5 found runtime and STAR scores within about 3e-5 Å RMS on its fixtures (largest: affine double-gain1-5it, 0.320006 vs 0.319982), far inside the limits, but that is not measured here.
- **Native N=9/13/20 and phase-ramp vel0/vel1 controls: UNRUN.** No generator in the repo produces them; W5 used offline replay. The only native N=5 fixtures are the #267 `integer`/`fractional` cases. W5 recorded production-stop regressions at larger N (vel0 isotropic N13/N20 PASS to FAIL) that this run cannot confirm or exclude.
- Native results do not match W5's offline numbers cell by cell (e.g. arm c integer 0.178 Å here, 0.074 Å in W5 map32); native b integer fails like W5's double-map replay and native b fractional fails like its map32 replay. The offline replay is not a native reproduction.
- One synthetic fixture family, 5 frames, one run per arm (the CPU build is bit-deterministic, so repeats would not add information). `noisy` worsens at the production stop and `pedestal` is unaffected.
- H2 arms were run once each; the half-gain arms' native N=9/13/20 controls remain UNRUN for H2 too. The fractional H2 production-stop improvement is small and from one fixture sample.
- CPU only. No GPU, no 4GPUs, no CUDA build. CPU/CUDA agreement is not addressed. No default, gate, ROI, tolerance or checker changed.

## Provenance

- Base `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; half-gain source `a1c78adc1d0ffcf031102bc0dad605c4fb670a1f`; H2 source `700d0c6d0366212de4935da76f6fbc9f10f4ebb5` (H2 binary `95c24099...d24f`, `results/build-h2.binaries.sha256`; tree staged as `src-h2`, same build flags and lane; H2 receipts in `results/v2/receipts-h2/`, `results/chain-h2*`, `results/flagsoff-h2/`, `results/ctest-h2.*`) (C++ sources identical in later commits on the branch; later commits add a CLI-test wording fix and these files).
- Binaries (Release, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, CUDA=OFF): base `7d9fd428...c9c9`, candidate `cee711f8...5d4c` (full hashes in `results/build-*.binaries.sha256`). Fixture hashes: `results/v2/receipts/fixtures.sha256`.
- Host `small-refmac-machine` (cpu64), `Cpus_allowed_list: 48-55` (receipt `results/v2/receipts/env.txt`), `flock -n /tmp/motioncorr-damping-cpu48-55.lock`, no foreign process above 5% on the lane at start, cmake and Python from `~/.mc-venv`. Scratch `/tmp/motioncorr-damping-a1c78adc1d0f`, 829 MB. Source staged with `git archive`; no copied build tree.
- Build: `MC_REQUIRE_ALL_DECODERS` left OFF because pbzip2 is absent on cpu64 (explicit repo waiver).
- Commands: `scripts/build.sh base|cand|h2`, `scripts/run_h2_arms.sh`, `scripts/mutants_h2.sh`, `scripts/flagsoff_h2.sh`, `scripts/chain_h2.sh`, `scripts/run_arms.sh`, `scripts/flagsoff.sh`, `scripts/ctest_cpu.sh`, `scripts/mutants.sh`, `scripts/summarize.py` (driven by `scripts/chain.sh`); exit codes in `results/chain.log`, `results/v2/receipts/*.exit`, `results/flagsoff/receipts/`.

## Retained failures and corrections

1. First configure used `MC_REQUIRE_ALL_DECODERS=ON`: failed on missing pbzip2 (twice, one of them with a stale script). Rebuilt with the waiver.
2. First `run_arms` launch failed at fixture generation because `python -I` hides the generator's sibling module (exit 2, no native run). Re-run without `-I`, as C1's `c1_v2.sh` does.
3. `ExperimentalFlagsCli` first failed on the wording for a non-numeric tolerance (`textToFloat` rejects it before my check); test loosened, source unchanged.
4. First full CTest (`results/ctest-cand-attempt1.log`): `CiFailClosedControls` failed (tests 5, 6, 8). Cause: my own known-motion flags-off step regenerated tracked ground-truth JSON inside the staged tree, and a `git archive` tree has no git metadata. Not caused by the change. Fixtures were restored from the commit, a git repo was initialised over the staged tree, and the whole suite was re-run: 0 failed.
5. First synthetic-movie comparison read the movie from `src-base/` and `src-cand/`; outputs mirror the input path, so the trees differed only by that path (`results/flagsoff/synth-compare-attempt1.json`). Re-run from one shared input path: IDENTICAL. The known-motion comparison ran in the first `flagsoff.sh` pass (commit 318dc481); only the synthetic part was re-run, with `FLAGSOFF_ONLY=synth`.
