# Global peak/update alternatives: default-off research prototypes (not for merge)

Three separate default-off CPU-only prototypes on one branch (H3 adds the ported #262 DC hook, which composes with the other two): (1) global half-gain damping with a tolerance override, scored against the independent challenge that rated it NO-GO; (2) hypothesis H2, a coupled 2x2-Hessian subpixel peak, scored against its frozen predictions. Sections below: summary, half-gain, challenge scorecard, H2, H3, flags-off identity, limitations, provenance.

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
| H3 DCg + H2g (global DC bin zeroed, coupled peak, gain 1), production stop | integer, fractional, affine | noisy RMS 2.12 to 3.05, max 6.8 to 21.3 versus the matched non-DC arm; pedestal improves but still FAILs |
| H3 DCg + H2g, 50 iterations / 1e-9 | integer, fractional (both 0.000 Å) | affine FAILs (max 0.849); noisy max 9.3 to 9.9 versus the matched non-DC arm |
| H3 DCg alone (separable, gain 1) | none (long: integer 0.234, fractional 0.314) | integer at the production stop 0.264 to 0.519 |
| H3 DCg + half-gain | production: integer, fractional, affine; long: integer, fractional | long budget loses the affine pass of arm c (max 0.849) |

All are research evidence on one 5-frame synthetic family. Limitations are listed below; flags-off products are identical to e77a51a2 for both binaries.

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
| Early 0.5 px stops make `--max_iter 50` alone equal `--max_iter 5` | tested in the H3 round (`e-half-iter50-tol05`, iteration log): integer ran 50 iterations, fractional 8, noisy 8, and all three differ from arm b; only affine (stops at 5) matches | falsified for integer, fractional, noisy |
| The N=5 instability is a peak-definition defect, not an update-gain defect | H2 alone does not repair integer/fractional (H2 section); with the global DC bin also zeroed (H3), the coupled peak at gain 1 brings integer and fractional to the truth at both stops | supported only together with pedestal removal |
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

## H3: pedestal removal x peak/update law (frozen: [H3-dc-interaction-PREDICTION.md](H3-dc-interaction-PREDICTION.md))

Prediction file copied verbatim, SHA256 `ec6e60f8ac25ea341659475ddb62dfe32b6dc2719cc0b6930c5cb08939a10c23` verified before any code was written.

**DC hook port (source `1c1eacf9`).** `src/experiment_ccf_dc.h` is byte-identical to `3eee0a4b` (`cmp`). The CPU call site in `alignPatch` is the same two lines (include, and `if (experimentCcfDcZero(is_global, EXP_DC_CPU, 1)) DIRECT_A2D_ELEM(Fccs[tid], 0, 0) = fComplex(0.f, 0.f);` after the CCF product, before the inverse FFT). Delta of 3eee0a4b against 805d9de2 is: the header, that call site, the CMake option `MC_EXPERIMENT_CCF_DC` (default OFF; taken here as the option and its compile definition only), the CUDA call sites, the #269 `MC_DIAG_MODEL_OUT` runtime-capture block, and a CUDA-oriented stage oracle with mutants. The CUDA parts, the runtime-capture block and that oracle are not ported (so the runtime field stays UNRUN). The hook keeps its own selection mechanism: with the option built in, `MC_EXPERIMENT_CCF_DC_ARM=none|global|local|both` is required at run time. **Setting used: `global` for DC arms, `none` for the DC-off identity arm.**

**Manipulation control (mirrors #284).** The hook prints, per run, how many CCF frames were eligible and zeroed. Summed over the eight #267 cases per arm: `dcg-prod` global 85/85 zeroed, patch 0/275; `dcg-long` global 1510/1510, patch 0/300; `dcgh2g-prod` global 95/95, patch 0/260; `dcgh2g-long` 1510/1510, 0/345; `dcghalf-prod` 115/115, 0/280; `dcghalf-long` 1510/1510, 0/375; the DC-off arm `h3-dcoff` (ARM=none) 0/130 global, 0/270 patch. So the global arm zeroes every global CCF frame and no patch frame (the K267 counts are in each case's `.stdout`).

**Tests.** `CcfDcHook` (built only with the option): on a 5-frame fixture carrying a 100-grey-level DC pedestal in every spectrum, arm none leaves 0/5 global CCF DC bins zeroed; arm global zeroes 5/5 global and 0/5 patch; arm local the converse; a global call under arm local, and a patch call under arm global, are bitwise the arm-none result; a global call under arm global differs. The #262 CPU mutants (restore the bin, zero the wrong bin, swap the stage) are all killed (`mutants_h3.sh`, `results/mut-h3/`); the restored source passes.

**Flags-off / DC-off identity to e77a51a2** (default build `build-h3off` `032ed3fb...`, hook build `build-h3on` `e65068c1...`, both Release `-O3 -DNDEBUG`):

| Check | Result |
|---|---|
| Full CPU CTest, default build | 93 tests, 92 passed, 1 skipped (pbzip2), 0 failed; `validate_test_collection` and `test_ci_fail_closed` rc 0 |
| Full CPU CTest, hook build with `MC_EXPERIMENT_CCF_DC_ARM=none` | 94 tests (adds `CcfDcHook`), 93 passed, 1 skipped, 0 failed |
| K267, hook binary ARM=none, flags off (`h3-dcoff`) vs arm a | field metrics and statuses equal bit for bit (1/5/2) |
| Known-motion fixtures, base vs default build; base vs hook build ARM=none | IDENTICAL, 193 files, 88 gated, 0 differing (both) |
| Synthetic movie, base vs default build; base vs hook build ARM=none | IDENTICAL, 14 files, 7 gated, 0 differing (both) |
| Negative controls on the synthetic movie | half gain on: 7/7 differ; DC arm global on: 7/7 differ (the manipulation changes products) |

The iteration-accounting line (`[align] scope=global iterations=N ... converged=..`) added in this commit prints to stdout only when an experimental flag is set; numerics are unchanged.

### H3 arm table

Matched controls reused, not rerun: a, b, c, d, h2glob-prod, h2glob-long. Matched non-DC arm per DC arm: dcg-prod to a, dcg-long to d, dcgh2g-* to h2glob-*, dcghalf-prod to b, dcghalf-long to c. STAR scores, unchanged checker; runtime field UNRUN.

| Arm | checker PASS / FAIL / UNIDENTIFIABLE / other | field-gate PASS (of 8) | native exits |
|---|---|---|---|
| a-cand-flagsoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h3-dcoff | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| d-gain1-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcg-prod | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcg-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2glob-prod | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| h2glob-long | 1 / 5 / 2 / 0 | 1 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcgh2g-prod | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcgh2g-long | 3 / 3 / 2 / 0 | 3 | [0, 0, 0, 0, 0, 0, 0, 0] |
| b-half-prod | 2 / 4 / 2 / 0 | 2 | [0, 0, 0, 0, 0, 0, 0, 0] |
| c-half-long | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcghalf-prod | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |
| dcghalf-long | 3 / 3 / 2 / 0 | 3 | [0, 0, 0, 0, 0, 0, 0, 0] |
| e-half-iter50-tol05 | 4 / 2 / 2 / 0 | 4 | [0, 0, 0, 0, 0, 0, 0, 0] |

| Case | a-cand-flagsoff | h3-dcoff | d-gain1-long | dcg-prod | dcg-long | h2glob-prod | h2glob-long | dcgh2g-prod | dcgh2g-long | b-half-prod | c-half-long | dcghalf-prod | dcghalf-long | e-half-iter50-tol05 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| zero | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 | PASS/PASS 0.000000 / 0.000000 / 0.000000 |
| integer | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.263613 / 0.431607 / 0.431607 | FAIL/FAIL 0.392654 / 0.573054 / 0.573054 | FAIL/FAIL 0.519066 / 0.850897 / 0.850897 | FAIL/FAIL 0.234034 / 0.298257 / 0.298257 | FAIL/FAIL 0.446108 / 0.645090 / 0.645090 | FAIL/FAIL 0.378577 / 0.823228 / 0.823228 | PASS/PASS 0.074187 / 0.115719 / 0.115719 | PASS/PASS 0.000008 / 0.000014 / 0.000014 | FAIL/FAIL 0.325549 / 0.434555 / 0.434555 | PASS/PASS 0.177743 / 0.378286 / 0.378286 | PASS/PASS 0.120929 / 0.208056 / 0.208056 | PASS/PASS 0.000065 / 0.000109 / 0.000109 | PASS/PASS 0.177743 / 0.378286 / 0.378286 |
| fractional | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.524056 / 0.703415 / 0.703415 | FAIL/FAIL 0.428876 / 0.682875 / 0.682875 | FAIL/FAIL 0.326484 / 0.522132 / 0.522132 | FAIL/FAIL 0.313731 / 0.509885 / 0.509885 | FAIL/FAIL 0.496160 / 0.681394 / 0.681394 | FAIL/FAIL 0.358772 / 0.505934 / 0.505934 | PASS/PASS 0.029712 / 0.048260 / 0.048260 | PASS/PASS 0.000006 / 0.000012 / 0.000012 | FAIL/FAIL 0.273674 / 0.404167 / 0.404167 | PASS/PASS 0.046840 / 0.062306 / 0.062306 | PASS/PASS 0.177838 / 0.293384 / 0.293384 | PASS/PASS 0.000080 / 0.000132 / 0.000132 | PASS/PASS 0.133007 / 0.274928 / 0.274928 |
| affine | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL 0.402447 / 0.742491 / 0.911118 | FAIL/FAIL 0.257860 / 0.504353 / 0.597196 | FAIL/FAIL 0.303951 / 0.592239 / 0.890681 | FAIL/FAIL 0.393109 / 0.604233 / 0.857636 | FAIL/FAIL 0.267061 / 0.504069 / 0.830987 | FAIL/FAIL 0.221027 / 0.412843 / 0.582922 | PASS/PASS 0.158937 / 0.337093 / 0.694812 | FAIL/FAIL 0.175787 / 0.374775 / 0.849069 | PASS/PASS 0.165893 / 0.323365 / 0.750467 | PASS/PASS 0.175520 / 0.337342 / 0.634428 | PASS/PASS 0.199064 / 0.361175 / 0.769927 | FAIL/FAIL 0.175780 / 0.374690 / 0.848981 | PASS/PASS 0.165893 / 0.323365 / 0.750467 |
| pedestal | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 0.411737 / 0.746610 / 1.145954 | FAIL/FAIL 0.436191 / 0.817290 / 1.460827 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 0.262335 / 0.577125 / 1.016022 | FAIL/FAIL 0.262756 / 0.578415 / 1.033332 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 | FAIL/FAIL 0.318820 / 0.642494 / 1.079337 | FAIL/FAIL 0.262760 / 0.578404 / 1.033345 | FAIL/FAIL 2.119133 / 3.603757 / 3.893113 |
| noisy | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.342962 / 4.376569 / 9.903941 | FAIL/FAIL 2.060526 / 4.394210 / 11.950092 | FAIL/FAIL 1.744010 / 3.514956 / 7.383125 | FAIL/FAIL 1.660947 / 3.386998 / 8.920166 | FAIL/FAIL 2.115487 / 4.031991 / 6.757304 | FAIL/FAIL 1.778466 / 3.631657 / 9.302432 | FAIL/FAIL 3.049056 / 6.319967 / 21.295071 | FAIL/FAIL 1.802902 / 3.712072 / 9.883923 | FAIL/FAIL 2.799221 / 5.876730 / 19.018634 | FAIL/FAIL 1.988823 / 4.225033 / 10.980241 | FAIL/FAIL 2.583038 / 5.400150 / 10.567595 | FAIL/FAIL 1.767668 / 3.630567 / 9.548841 | FAIL/FAIL 1.926334 / 3.978985 / 10.649381 |
| flat | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 | UNIDENTIFIABLE/FAIL 2.104421 / 3.436505 / 3.436505 |
| repeated | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 9.012581 / 14.197954 / 14.197954 | UNIDENTIFIABLE/FAIL 9.029315 / 14.230078 / 14.230078 | UNIDENTIFIABLE/FAIL 16.533858 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 16.607416 / 28.003916 / 28.003916 | UNIDENTIFIABLE/FAIL 9.012581 / 14.197954 / 14.197954 | UNIDENTIFIABLE/FAIL 9.029315 / 14.230078 / 14.230078 | UNIDENTIFIABLE/FAIL 6.740209 / 8.831312 / 8.831312 | UNIDENTIFIABLE/FAIL 4.395413 / 5.842215 / 5.842215 | UNIDENTIFIABLE/FAIL 6.898739 / 8.985500 / 8.985500 | UNIDENTIFIABLE/FAIL 4.339040 / 5.718833 / 5.718833 | UNIDENTIFIABLE/FAIL 4.395413 / 5.842215 / 5.842215 |

### H3 prediction scorecard

| # | Prediction | Native result | Verdict |
|---|---|---|---|
| 1 | Flags off and DC off identical to e77a51a2 (rebuilt binary) | table above: CTest 0 failed on both builds, `h3-dcoff` equals a, products IDENTICAL | confirmed |
| 2 | DCg alone does not make integer or fractional meet the limits at the long budget | `dcg-long` integer 0.2340 / 0.2983 / 0.2983 (RMS > 0.20) FAIL; fractional 0.3137 / 0.5099 / 0.5099 FAIL | confirmed |
| 3a | DCg+H2g improves integer and fractional RMS versus DCg alone at both stops | integer 0.519 to 0.074 (prod), 0.234 to 0.000 (long); fractional 0.327 to 0.030 (prod), 0.314 to 0.000 (long) | confirmed |
| 3b | At least one meets 0.20/0.40/0.80 Å in STAR at the long budget | integer and fractional both PASS (RMS / p95 / max 0.000); also PASS at the production stop (integer 0.074 / 0.116, fractional 0.030 / 0.048) | confirmed |
| 4 | DCg+half at the long budget keeps the integer, fractional and affine passes of arm c | integer 0.0001 PASS, fractional 0.0001 PASS, **affine FAIL** (0.1758 / 0.3747 / 0.8491, max > 0.80; c had 0.1755 / 0.3373 / 0.6344) | **falsified** (affine pass lost) |
| 5 | Zero PASS; flat and repeated UNIDENTIFIABLE; noisy and pedestal reported in full; RMS or max increases versus the matched non-DC arm listed | zero PASS and flat/repeated UNIDENTIFIABLE in all six DC arms. Pedestal falls from 2.119 to 0.26 to 0.44 Å RMS in every DC arm (still FAIL). Regressions below | confirmed |

Regressions versus the matched non-DC arm (any of RMS, p95, max up; `results/h3_regressions_vs_matched.json`):

| DC arm vs matched | Case | Change (matched to DC arm) | Status |
|---|---|---|---|
| dcg-prod vs a | integer | RMS 0.264 to 0.519, max 0.432 to 0.851 | FAIL both |
| dcg-long vs d | affine | RMS 0.258 to 0.393, max 0.597 to 0.858 | FAIL both |
| dcgh2g-prod vs h2glob-prod | noisy | RMS 2.116 to 3.049, max 6.76 to 21.30 | FAIL both |
| dcgh2g-long vs h2glob-long | affine | max 0.583 to 0.849 (RMS 0.221 to 0.176 improves) | FAIL both |
| dcgh2g-long vs h2glob-long | noisy | RMS 1.779 to 1.803, max 9.30 to 9.88 | FAIL both |
| dcghalf-prod vs b | affine | RMS 0.166 to 0.199, max 0.751 to 0.770 | PASS both |
| dcghalf-prod vs b | repeated | RMS 6.74 to 6.90 | UNIDENTIFIABLE |
| dcghalf-long vs c | affine | max 0.634 to 0.849 | c PASS, DC arm FAIL |

Noisy against the flags-off arm a (RMS 2.343, max 9.904): `dcgh2g-prod` is worse on both (3.049, 21.295); `dcgh2g-long` has lower RMS (1.803) and about equal max (9.884).

**Falsification branch.** Prediction 3 holds, so the second branch applies: on this fixture family the principled candidate is pedestal removal plus the coupled peak at gain 1, and the challenge's peak-definition mechanism is supported natively once the pedestal is gone (H2 without DC did nothing for integer/fractional; with DCg it brings both to the truth). It is research evidence only. Before any adoption discussion it needs N=9/13/20 controls, noisy harm checks (the production-stop noisy regression above), and CUDA parity, none of which exist here.

**Guard fires, DCg+H2g** (peaks falling back to the separable result / peaks fitted, global alignment; no patch peaks use H2 in this arm):

| Case | production stop | long budget |
|---|---|---|
| zero | 0/5 | 0/5 |
| integer, fractional, affine, pedestal | 0/15 each | 0/250 each |
| noisy | 0/10 | 0/250 |
| flat | 5/5 (not negative definite) | 5/5 |
| repeated | 15/15 (not negative definite) | 250/250 |

Without the DC bin zeroed, H2 fired on every pedestal peak (5/5 global, 45/45 patch at the production stop; `results/h2_guard_counts.md`); with DCg it never fires there. Flat and repeated are degenerate inputs and still fire everywhere.

### Iteration log: does half-gain stop early at the production tolerance? (challenge claim, item 3)

One extra arm, `e-half-iter50-tol05`: `--experimental_global_half_gain --max_iter 50`, default 0.5 px tolerance, no driver change (the `[align]` stdout line gives iterations). Results: integer ran all 50 iterations (never below 0.5 px, last 0.586) and ends at 0.1777 Å, identical to arm c; fractional converged at iteration 8 (0.133 Å); affine stopped at iteration 5 (identical to arm b); noisy converged at iteration 8. The challenge's claim that `--max_iter 50` at the production tolerance stops at iteration 4 or earlier and is bit-identical to `--max_iter 5` is falsified natively for integer, fractional and noisy: those runs use more than five iterations and differ from arm b (integer 0.326 to 0.178, fractional 0.274 to 0.133, noisy RMS 2.799 to 1.926). It holds only for affine, which stops at the cap anyway. A longer budget at the default tolerance is enough for half-gain to pass integer, fractional and affine here; the tolerance override of arm c is not what matters. Arms b, c and d have no iteration log (older binary), so their own iteration counts are not observed.

## Not run / limitations (half-gain, H2 and H3)

- **Runtime (unrounded) field: UNRUN.** e77a51a2 has no runtime-model capture (`MC_DIAG_*` is not in `src/`). Only STAR-serialized scores exist. W5 found runtime and STAR scores within about 3e-5 Å RMS on its fixtures (largest: affine double-gain1-5it, 0.320006 vs 0.319982), far inside the limits, but that is not measured here.
- **Native N=9/13/20 and phase-ramp vel0/vel1 controls: UNRUN.** No generator in the repo produces them; W5 used offline replay. The only native N=5 fixtures are the #267 `integer`/`fractional` cases. W5 recorded production-stop regressions at larger N (vel0 isotropic N13/N20 PASS to FAIL) that this run cannot confirm or exclude.
- Native results do not match W5's offline numbers cell by cell (e.g. arm c integer 0.178 Å here, 0.074 Å in W5 map32); native b integer fails like W5's double-map replay and native b fractional fails like its map32 replay. The offline replay is not a native reproduction.
- One synthetic fixture family, 5 frames, one run per arm (the CPU build is bit-deterministic, so repeats would not add information). `noisy` worsens at the production stop and `pedestal` is unaffected.
- H3: the DC hook is ported for the CPU path only; the CUDA hook, the #269 runtime-capture block and CUDA parity are not ported or run. The H3 arms used the hook binary built from `1c1eacf9`, which also carries the iteration-accounting stdout line; arms a to d and the H2 arms ran on earlier binaries whose flags-off identity was verified separately. DCg+H2g's noisy regression at the production stop is not resolved.
- H2 arms were run once each; the half-gain arms' native N=9/13/20 controls remain UNRUN for H2 too. The fractional H2 production-stop improvement is small and from one fixture sample.
- CPU only. No GPU, no 4GPUs, no CUDA build. CPU/CUDA agreement is not addressed. No default, gate, ROI, tolerance or checker changed.

## Provenance

- Base `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; half-gain source `a1c78adc1d0ffcf031102bc0dad605c4fb670a1f`; H3 source `1c1eacf9ac2275b01105492bad84c58d164bd112` (staged `src-h3`; binaries `build-h3off` `032ed3fb...`, `build-h3on` `e65068c1...`, hashes in `results/build-h3o*.binaries.sha256`; receipts `results/v2/receipts-h3/`, `results/chain-h3*`, `results/flagsoff-h3/`, `results/ctest-h3o*`); H2 source `700d0c6d0366212de4935da76f6fbc9f10f4ebb5` (H2 binary `95c24099...d24f`, `results/build-h2.binaries.sha256`; tree staged as `src-h2`, same build flags and lane; H2 receipts in `results/v2/receipts-h2/`, `results/chain-h2*`, `results/flagsoff-h2/`, `results/ctest-h2.*`) (C++ sources identical in later commits on the branch; later commits add a CLI-test wording fix and these files).
- Binaries (Release, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, CUDA=OFF): base `7d9fd428...c9c9`, candidate `cee711f8...5d4c` (full hashes in `results/build-*.binaries.sha256`). Fixture hashes: `results/v2/receipts/fixtures.sha256`.
- Host `small-refmac-machine` (cpu64), `Cpus_allowed_list: 48-55` (receipt `results/v2/receipts/env.txt`), `flock -n /tmp/motioncorr-damping-cpu48-55.lock`, no foreign process above 5% on the lane at start, cmake and Python from `~/.mc-venv`. Scratch `/tmp/motioncorr-damping-a1c78adc1d0f`, 829 MB. Source staged with `git archive`; no copied build tree.
- Build: `MC_REQUIRE_ALL_DECODERS` left OFF because pbzip2 is absent on cpu64 (explicit repo waiver).
- Commands: `scripts/build_h3.sh`, `scripts/run_h3_arms.sh`, `scripts/mutants_h3.sh`, `scripts/flagsoff_h3.sh`, `scripts/chain_h3.sh`, `scripts/build.sh base|cand|h2`, `scripts/run_h2_arms.sh`, `scripts/mutants_h2.sh`, `scripts/flagsoff_h2.sh`, `scripts/chain_h2.sh`, `scripts/run_arms.sh`, `scripts/flagsoff.sh`, `scripts/ctest_cpu.sh`, `scripts/mutants.sh`, `scripts/summarize.py` (driven by `scripts/chain.sh`); exit codes in `results/chain.log`, `results/v2/receipts/*.exit`, `results/flagsoff/receipts/`.

## Retained failures and corrections

1. First configure used `MC_REQUIRE_ALL_DECODERS=ON`: failed on missing pbzip2 (twice, one of them with a stale script). Rebuilt with the waiver.
2. First `run_arms` launch failed at fixture generation because `python -I` hides the generator's sibling module (exit 2, no native run). Re-run without `-I`, as C1's `c1_v2.sh` does.
3. `ExperimentalFlagsCli` first failed on the wording for a non-numeric tolerance (`textToFloat` rejects it before my check); test loosened, source unchanged.
4. First full CTest (`results/ctest-cand-attempt1.log`): `CiFailClosedControls` failed (tests 5, 6, 8). Cause: my own known-motion flags-off step regenerated tracked ground-truth JSON inside the staged tree, and a `git archive` tree has no git metadata. Not caused by the change. Fixtures were restored from the commit, a git repo was initialised over the staged tree, and the whole suite was re-run: 0 failed.
5. First synthetic-movie comparison read the movie from `src-base/` and `src-cand/`; outputs mirror the input path, so the trees differed only by that path (`results/flagsoff/synth-compare-attempt1.json`). Re-run from one shared input path: IDENTICAL. The known-motion comparison ran in the first `flagsoff.sh` pass (commit 318dc481); only the synthetic part was re-run, with `FLAGSOFF_ONLY=synth`.
