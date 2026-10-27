# Independent read-only audit: B2 cross-feed offline screen r1 (Opus, 2026-10-27)

**Verdict: SUPPORTED, bounded.** The frozen fits, control and scoring support **NOT_A_CANDIDATE**, and I found no hidden harm. The status rests on noisy B2 + full-width failing all three limits on both fields, by 0.62 / 1.25 / 2.42 A. It does not depend on a margin, on the 0.0131 px ceiling, or on the isolation receipts. The findings below are process and wording issues. None changes a number, gate or status.

Scope: the saved packet metadata and truth NPY only. No image pixels, native run, SSH, build, new fit arm, multistart or tolerance change. The originals were not edited.

## Inputs (all pins matched; `results/a1_integrity.json`)
- Packet `/tmp/mc-lfw-b2-crossfeed-20261026-r1/`: PLAN `df804f52…`, PINS `18841057…`, stage1_seal `41fed948…`, stage2_result `c5520cf3…`, MANIFEST `36b5253d…`. All 101 manifest entries match. The only unlisted file is MANIFEST.json itself.
- Durable copy: COPY_INDEX.tsv `4de4c522…`. All 102 entries match both the durable copy and the /tmp packet. There are no unindexed files.
- Bundle MANIFEST `49698c7c…` lists 258 files. The 32 run files used here match. truth/MANIFEST `9697c203…` is bound by repo `final_seal/BUNDLE_ADDENDUM.json` (`97bb477b…`). All 8 truth NPYs match it. The 12 retained-control files match PINS.
- W8 sources: `w8_fit` `e4000d87…`, `w8_refit` `d3088ae1…` and `w8_gate` `601c2806…` are byte-equal to `git show 0b3478b5:…/w8_intercept_refit_20261026/scripts/`. The only configuration change is `R.NF = 5`. `score_fields_v3` `bd685429…` and `score_fields_v2` `e0ef769c…` match at HEAD `4c11c9c9`.
- Seal: all 16 sealed files and all 40 staged files re-hash equal. The staged root contains only `runtime.json` and `<case>.star`, and every staged file still equals its source.

## Chronology (mtimes plus the seal; observed, not proof)
PINS 23:59:22Z, PLAN/FREEZE 23:59:55Z, staging 00:03:19Z, stage-1 attempt 1 00:03:29Z, attempt 2 00:03:51Z, seal 00:04:11Z, stage2_score.py written 00:04:35Z, stage 2 output 00:04:43–44Z. `stage2_result.json` embeds the PLAN and seal hashes.

The attempt-1 to attempt-2 change is only `stage1_fit.py:7` (`Path(...).resolve()`). With isolation and environment excluded, the numerical content of `stage1_fit.json` is identical between attempts. That attempt is preserved under `out/attempt1/`.

## Independent re-evaluation (`scripts/a2_reeval.py`, `a3_compare.py`)
The re-evaluation imports nothing from W8 or the scorer. It uses its own generic STAR loop parser, its own basis, QR for the legacy fit, and per-patch demeaning (Frisch–Waugh) for B2. A C-form fit with explicit intercepts is evaluated as q(f+.5)−q(.5) directly. Field and metrics are its own code, computed against the truth NPY on ROI rows 12:84 and cols 12:116 at 0.885 A/px.
- All 32 native metrics and all 24 offline metrics reproduce stage 2 to ≤1.4e-13 A, with no gate disagreements. Own B2 and legacy coefficients match the sealed ones to ≤5.8e-13.
- Rank: legacy is 18/18 and B2 is 26/26 (noisy) and 27/27 (affine, pedestal). Spatial rank is 6 and raw cond(B2) is 5044 / 4290. The C form differs from B2 by ≤5.4e-14 px. h(0) is 0 exactly, which holds by construction because z⁰ is excluded from the basis.
- **Noisy B2 + full-width** is R-rt 0.82485 / 1.65200 / 3.21674 A and R-hyb 0.82485 / 1.65200 / 3.21674 A. It is **FAIL on every limit on both fields**. It improves on the native legacy full-width field in every metric (runtime 1.0954 / 2.2402 / 4.4692), but it still fails.
- **The five prior passes are retained on both fields.** Affine is 0.0654 / 0.1409 / 0.3307 and pedestal is 0.0654 / 0.1408 / 0.3309. Zero, integer and fractional have no patches and `local_enabled=false`, so their native fields are unchanged.
- **flat and repeated** have no local observations, unchanged raw distances (RMS 2.1044 and 9.0126 A), and are labelled UNIDENTIFIABLE in RESULT_TABLES. They are excluded from the primary criterion.
- **Increases:** I independently found exactly the 4 reported increases. All are max-metric PASS→PASS versus native ON: affine 0.32948 → 0.33075 (R-rt) and 0.32950 → 0.33075 (R-hyb), pedestal 0.33018 → 0.33087 and 0.33016 → 0.33087. There are none versus native OFF and no ties in the local cases.
- **Margin:** no B2 + full-width, offline or native value lies within 0.011621 A of a limit. The closest B2 + full-width value is 0.1258 A away (integer RMS).

## Old harm control and replay: coefficients versus field vectors (`results/a2_reeval.json`, `a4_discrimination.json`)
| comparison | coeff max \|Δ\| | field component max (px) | **field vector max (px)** |
|---|---|---|---|
| control noisy: offline B2(OFF obs) vs native UP_B2 runtime | 3.04e-5 | 1.119e-5 | **1.119e-5** |
| control affine | 6.42e-5 | 1.301e-5 | **1.303e-5** |
| legacy replay, worst set (pedestal ON) | 5.44e-5 | 7.886e-6 | **7.889e-6** |
| legacy replay noisy OFF | 3.24e-5 | 6.125e-6 | **7.158e-6** |

The coefficient differences are not the bounded quantity. The packet compares field differences, so RESULT.md's "≤ 1.3e-5 px" and "≤ 7.9e-6 px" are correct. Vector maxima are about 1000× below 0.01313142874082845 px.

The ceiling can discriminate a wrong arm here. Legacy versus B2 field vector distance on the same observations is ≥0.0338 px in every set, and 5.03 px for noisy OFF.

The old UP+B2 harm reproduces. Offline B2 on the old-weight noisy observations gives 1.90257 / 4.20029 / 9.29478 A, against the retained 1.90257 / 4.20029 / 9.29478 A (|Δ| ≤ 5.5e-6 A) and UP_only 1.64537 / 3.33729 / 7.28403 A. It is FAIL on all limits and reported, not hidden. The affine control is 0.1152 / 0.2570 / 0.5160 A, PASS, with |Δ| ≤ 7.7e-6 A. UP_only and UP_B2 share identical observations and an identical runtime global.

**R-rt and R-hyb are separate fields.** R-hyb uses the STAR read-back global plus the full-precision coefficients. It is not a genuine refit serialization. The STAR global differs from the runtime global by ≤5.0e-6 px, so R-hyb and R-rt differ by <1e-6 A here and R-hyb says almost nothing about coefficient serialization. Native full-precision versus STAR coefficient fields differ by 1.2e-4–4.7e-4 px (vector) for legacy, and by 2.9e-4 px for the UP_B2 native case. That is far below every gate distance, but a genuine B2 refit serialization remains UNRUN.

## Findings
1. **Low (isolation guard weaker than its name and the plan).** `stage1_fit.py:104-106` sets `isolation_audit_hook_no_forbidden_or_foreign_open` from forbidden-substring hits only, and the `other` class is never asserted. PLAN.md:15 says the run "asserts none is outside" the allowed trees. The guard therefore cannot fail on a foreign path that contains no listed substring.

   Attempt 1 demonstrates this. It had 44 `other` opens, and `out/attempt1/stage1_fit.json` still has `overall_pass: true`. ATTEMPTS.md describes this as a classification issue, which is accurate, but does not say the guard stayed green.

   In the sealed attempt 2 the receipts show 40 staged, 6 pinned-source, 104 interpreter/NumPy, 0 other and 0 forbidden opens. No truth, generator or evaluator module was loaded. The hook at `stage1_fit.py:6` also drops bytes-path opens, and C-level opens are invisible to it. Probe: Path and str opens reach the hook as str, while bytes paths do not.

   Isolation is therefore observed and auditable from the receipts only. It is not proven, and the verdict does not depend on it.
2. **Low (ceiling semantics).** The packet compares a component-wise max against a ceiling that was derived as a *vector* bound (`docs/post_rc0/s1/native_b2_20261026/rounding_prediction.json`, `vector_bound_px`). That derivation used 40-frame dose-movie STAR precision and conditioning, and the ceiling was not re-derived for these 5-frame fixtures. This has no effect here: vector maxima are ≤1.303e-5 px, and the plan freezes the ceiling as a compatibility bound only.
3. **Low (seal scope).** `stage2_score.py` was written after the seal (00:04:35Z vs 00:04:11Z) and is not in `stage1_seal.json`. Only the criteria were frozen in advance. Its logic matches PLAN.md:24-31, and my independent re-scoring removes the dependence on it. That stage 2 ran only once is supported by mtimes and the one-line stdout only.
4. **Info.** PLAN.md:30 says "any tie … is listed". The only ties are the local-disabled cases, which are identical by construction. They are described as unchanged but not enumerated, so nothing is hidden. The RESULT_TABLES replay table puts the coefficient |Δ| next to the field px column. Both are labelled, but they are different quantities.

## Not established
These are UNRUN, as the packet states: a genuine refit STAR write/read-back, a native compound run, and any applied-image or real-data accuracy. Noisy is one realization, so I make no p-value, independence, causal-noise or generalization claim. I did no floor subtraction. This audit did not re-review the native pilot (closed by `efa5c844…`) or the W8 source.

## Execution
Interpreter: uv CPython 3.13.7 with NumPy 2.4.2, run as `python -I -B` with `OMP/OPENBLAS/VECLIB=1`. a2 peak RSS was 54 MB and wall time 0.6 s. Scratch is about 80 KB.

One run failed and is preserved: the first a2 run used `/opt/homebrew/bin/python3 -I` (3.15.1, no NumPy) and exited with ModuleNotFoundError, rc 1. It was rerun unchanged with the packet's interpreter. The NumPy-dependent outputs come only from the rerun. Hashes are in `HASHES.sha256`.
