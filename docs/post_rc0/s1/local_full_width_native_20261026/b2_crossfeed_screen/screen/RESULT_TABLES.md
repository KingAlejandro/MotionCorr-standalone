# B2 cross-feed offline screen: result tables (generated from out/stage1_fit.json and out/stage2_result.json)

**Status: NOT_A_CANDIDATE** (never an acceptance). Primary criterion met: False; five original passes retained: True. Control reproduced: True.

## Stage 1 checks (sealed before truth)

| check | pass |
|---|---|
| C1_staged_only_runtime_and_star | True |
| C1_OFF_equals_retained_UP_only_bytes | True |
| C1_UP_only_UP_B2_observation_blocks_identical | True |
| C2_local_sets_present | True |
| C2_complete_patches | True |
| C2_spatial_rank6_and_ge4_times | True |
| C2_full_rank_all_arms | True |
| C2_equivalence_le_1e-9px | True |
| C2_h0_exactly_zero | True |
| C3_legacy_replay_le_ceiling | True |
| C4_B2_vs_native_UP_B2_le_ceiling | True |
| C5_local_disabled_unchanged | True |
| isolation_no_truth_generator_evaluator_modules | True |
| isolation_audit_hook_no_forbidden_or_foreign_open | True |

## Rank / conditioning per local observation set (arms: legacy "native", B1, B2, C)

| set | patches | arm | rank / columns | raw min sv | raw max sv | raw cond | scaled cond | spatial rank | distinct times |
|---|---|---|---|---|---|---|---|---|---|
| noisy/OFF | 8 | native | 18 / 18 | 0.06254 | 299.2 | 4785 | 265.5 | 6 | 5 |
| noisy/OFF | 8 | B1 | 26 / 26 | 0.04095 | 209.4 | 5114 | 336.8 | 6 | 5 |
| noisy/OFF | 8 | B2 | 26 / 26 | 0.04098 | 206.7 | 5044 | 320 | 6 | 5 |
| noisy/OFF | 8 | C | 26 / 26 | 0.02586 | 299.2 | 1.157e+04 | 528.9 | 6 | 5 |
| noisy/ON | 8 | native | 18 / 18 | 0.06254 | 299.2 | 4785 | 265.5 | 6 | 5 |
| noisy/ON | 8 | B1 | 26 / 26 | 0.04095 | 209.4 | 5114 | 336.8 | 6 | 5 |
| noisy/ON | 8 | B2 | 26 / 26 | 0.04098 | 206.7 | 5044 | 320 | 6 | 5 |
| noisy/ON | 8 | C | 26 / 26 | 0.02586 | 299.2 | 1.157e+04 | 528.9 | 6 | 5 |
| affine/OFF | 9 | native | 18 / 18 | 0.07783 | 316.7 | 4069 | 243.8 | 6 | 5 |
| affine/OFF | 9 | B1 | 27 / 27 | 0.05094 | 221.7 | 4352 | 309.8 | 6 | 5 |
| affine/OFF | 9 | B2 | 27 / 27 | 0.051 | 218.8 | 4290 | 294.3 | 6 | 5 |
| affine/OFF | 9 | C | 27 / 27 | 0.03216 | 316.7 | 9848 | 486.4 | 6 | 5 |
| affine/ON | 9 | native | 18 / 18 | 0.07783 | 316.7 | 4069 | 243.8 | 6 | 5 |
| affine/ON | 9 | B1 | 27 / 27 | 0.05094 | 221.7 | 4352 | 309.8 | 6 | 5 |
| affine/ON | 9 | B2 | 27 / 27 | 0.051 | 218.8 | 4290 | 294.3 | 6 | 5 |
| affine/ON | 9 | C | 27 / 27 | 0.03216 | 316.7 | 9848 | 486.4 | 6 | 5 |
| pedestal/OFF | 9 | native | 18 / 18 | 0.07783 | 316.7 | 4069 | 243.8 | 6 | 5 |
| pedestal/OFF | 9 | B1 | 27 / 27 | 0.05094 | 221.7 | 4352 | 309.8 | 6 | 5 |
| pedestal/OFF | 9 | B2 | 27 / 27 | 0.051 | 218.8 | 4290 | 294.3 | 6 | 5 |
| pedestal/OFF | 9 | C | 27 / 27 | 0.03216 | 316.7 | 9848 | 486.4 | 6 | 5 |
| pedestal/ON | 9 | native | 18 / 18 | 0.07783 | 316.7 | 4069 | 243.8 | 6 | 5 |
| pedestal/ON | 9 | B1 | 27 / 27 | 0.05094 | 221.7 | 4352 | 309.8 | 6 | 5 |
| pedestal/ON | 9 | B2 | 27 / 27 | 0.051 | 218.8 | 4290 | 294.3 | 6 | 5 |
| pedestal/ON | 9 | C | 27 / 27 | 0.03216 | 316.7 | 9848 | 486.4 | 6 | 5 |

## Replay, equivalence, h(0) (fixed ceiling 0.01313142874082845 px; equivalence bound 1e-9 px)

| set | legacy replay vs native runtime (field max px) | legacy coeff max abs diff | B1 vs B2 / C vs B2 (px) | h(0) exactly 0 (B1,B2,C) |
|---|---|---|---|---|
| noisy/OFF | 6.125e-06 | 3.238e-05 | 1.17e-13 / 2.79e-13 | True, True, True |
| noisy/ON | 5.705e-06 | 5.087e-05 | 8.66e-14 / 1.84e-13 | True, True, True |
| affine/OFF | 6.153e-06 | 4.060e-05 | 5.77e-15 / 9.88e-15 | True, True, True |
| affine/ON | 6.149e-06 | 4.507e-05 | 5.55e-15 / 7.66e-15 | True, True, True |
| pedestal/OFF | 3.303e-06 | 1.449e-05 | 1.04e-14 / 1.09e-14 | True, True, True |
| pedestal/ON | 7.886e-06 | 5.436e-05 | 5.11e-15 / 1.09e-14 | True, True, True |

## Old-harm control: B2 on the old-weight observations vs retained native UP_B2

| case | B2 projection vs native UP_B2 field (px) | offline B2 old weight R-rt (A) | retained native UP_B2 (A) | retained UP_only (A) | abs diff to UP_B2 (A) |
|---|---|---|---|---|---|
| noisy | 1.119e-05 | 1.9026 / 4.2003 / 9.2948 (FAIL) | 1.9026 / 4.2003 / 9.2948 (FAIL) | 1.6454 / 3.3373 / 7.2840 | 5.53e-06 |
| affine | 1.301e-05 | 0.1152 / 0.2570 / 0.5160 (PASS) | 0.1152 / 0.2570 / 0.5160 (PASS) | 0.1170 / 0.2603 / 0.5374 | 7.71e-06 |

## Full score table (A; RMS / p95 / max; limits .20 / .40 / .80)

Native columns are actual measured fields; offline columns are counterfactual. R-rt = runtime G + full-precision refit coefficients; R-hyb = STAR read-back G + the same coefficients (hybrid, not a serialised refit).

| case | field | native OFF | native ON | legacy OFF (offline) | legacy ON (offline) | B2 OFF | B2 + full-width |
|---|---|---|---|---|---|---|---|
| noisy | R-rt | 1.6454 / 3.3373 / 7.2840 FAIL | 1.0954 / 2.2402 / 4.4692 FAIL | 1.6454 / 3.3373 / 7.2840 FAIL | 1.0954 / 2.2402 / 4.4692 FAIL | 1.9026 / 4.2003 / 9.2948 FAIL | 0.8249 / 1.6520 / 3.2167 FAIL |
| noisy | R-hyb | 1.6454 / 3.3373 / 7.2838 FAIL | 1.0954 / 2.2403 / 4.4693 FAIL | 1.6454 / 3.3373 / 7.2840 FAIL | 1.0954 / 2.2402 / 4.4692 FAIL | 1.9026 / 4.2003 / 9.2948 FAIL | 0.8249 / 1.6520 / 3.2167 FAIL |
| affine | R-rt | 0.1170 / 0.2603 / 0.5374 PASS | 0.0660 / 0.1422 / 0.3295 PASS | 0.1170 / 0.2603 / 0.5374 PASS | 0.0660 / 0.1422 / 0.3295 PASS | 0.1152 / 0.2570 / 0.5160 PASS | 0.0654 / 0.1409 / 0.3307 PASS |
| affine | R-hyb | 0.1170 / 0.2603 / 0.5374 PASS | 0.0660 / 0.1422 / 0.3295 PASS | 0.1170 / 0.2603 / 0.5374 PASS | 0.0660 / 0.1422 / 0.3295 PASS | 0.1152 / 0.2570 / 0.5160 PASS | 0.0654 / 0.1409 / 0.3307 PASS |
| pedestal | R-rt | 0.1169 / 0.2603 / 0.5375 PASS | 0.0659 / 0.1420 / 0.3302 PASS | 0.1169 / 0.2603 / 0.5375 PASS | 0.0659 / 0.1420 / 0.3302 PASS | 0.1152 / 0.2575 / 0.5147 PASS | 0.0654 / 0.1408 / 0.3309 PASS |
| pedestal | R-hyb | 0.1169 / 0.2603 / 0.5375 PASS | 0.0659 / 0.1420 / 0.3302 PASS | 0.1169 / 0.2603 / 0.5375 PASS | 0.0659 / 0.1420 / 0.3302 PASS | 0.1152 / 0.2575 / 0.5147 PASS | 0.0654 / 0.1408 / 0.3309 PASS |
| zero | R-rt | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS |
| zero | R-hyb | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS |
| integer | R-rt | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS |
| integer | R-hyb | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS |
| fractional | R-rt | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS |
| fractional | R-hyb | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS |
| flat (UNIDENTIFIABLE) | R-rt | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL |
| flat (UNIDENTIFIABLE) | R-hyb | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL | 2.1044 / 3.4365 / 3.4365 FAIL |
| repeated (UNIDENTIFIABLE) | R-rt | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL |
| repeated (UNIDENTIFIABLE) | R-hyb | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL | 9.0126 / 14.1980 / 14.1980 FAIL |

## Directional diagnostic (noisy B2 + full-width vs the measured native legacy full-width field)

- R_rt_vs_native_runtime_ON: rms 1.0954 -> 0.8249 (improves), p95 2.2402 -> 1.6520 (improves), max 4.4692 -> 3.2167 (improves)
- R_hyb_vs_native_STAR_ON: rms 1.0954 -> 0.8249 (improves), p95 2.2403 -> 1.6520 (improves), max 4.4693 -> 3.2167 (improves)

Still FAIL against the unchanged limits (noisy B2 + full-width): R-rt 0.8249 / 1.6520 / 3.2167; R-hyb 0.8249 / 1.6520 / 3.2167.

## Every metric increase of B2 + full-width (all cases, both fields, vs native ON and vs native OFF; PASS->PASS included): 4

- affine R_rt max vs native runtime ON: 0.3295 -> 0.3307 A (PASS->PASS)
- affine R_hyb max vs native STAR ON: 0.3295 -> 0.3307 A (PASS->PASS)
- pedestal R_rt max vs native runtime ON: 0.3302 -> 0.3309 A (PASS->PASS)
- pedestal R_hyb max vs native STAR ON: 0.3302 -> 0.3309 A (PASS->PASS)

Margin-sensitive (within 0.01313142874082845 x .885 = 0.01162 A of a limit) B2 + full-width comparisons: none.
