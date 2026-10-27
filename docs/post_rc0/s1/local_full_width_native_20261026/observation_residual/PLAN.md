# Observation-residual diagnostic: PLAN (frozen before any new payload value is computed)

One saved-metadata diagnostic authorized by the parent after the B2 cross-feed screen (NOT_A_CANDIDATE, unchanged). It does not reopen the B2 candidate, adds no arm, gate, threshold or acceptance claim, and has no automatic follow-on.

**Question (descriptive only):** under current full-width, where do the point-observation errors of the accepted patches concentrate, and do the new full-width point-observation errors remain? It cannot decide objective versus iteration versus noise/window cause.

**Excluded by construction:** any fit, intervention, optimization, CCF capture, pixel or movie processing, SSH, native run, new arm, fitter tuning. Stored coefficients are only evaluated, never re-estimated. The pinned operator is the unchanged W8 `w8_fit.field` evaluator and the pinned `w8_refit.read_star` STAR reader (frame count set to 5, as in the sealed stage 1).

## Cases and inputs
Cases noisy, affine, pedestal, each OFF (old weight) and ON (full-width): the 6 existing accepted patch sets (noisy 8 patches in both arms; affine and pedestal 9). Inputs are pinned by sha256 in `PINS.json`: the read-only audit bundle (`runs/<case>/<arm>/{<case>.star, runtime.json, <case>.log}`, `truth/<case>_field.npy`), the sealed screen outputs (`stage1_fit.json` for the stored native runtime / legacy / B2 coefficients, `stage2_result.json` for sealed ROI metrics), and the pinned W8 sources. The bundle STAR and runtime files are checked equal to the files the sealed stage 1 consumed (`stage1_staged_manifest.json`).

## Fixed definitions (per accepted patch p, frame index g = 0..4 = stored STAR frame 1..5)
- `y[p,g]`: stored observation (STAR local shift, 5-decimal rounding).
- `G[g]`: the runtime global of that run (`runtime.json` `global`), fixed; asserted equal to the sealed stage-1 value.
- `T[p,g]`: unchanged truth field at the patch centre, `truth[g, y_c, x_c]` (same indexing as the pinned `tiny_challenge.py`; centres are asserted integral and in range).
- `H[p,g] = T[p,g] - G[g]`.
- Expected stored-observation image: `Tr[H][p,g] = H[p,g] + 0.5*H[p,1]`, defined only when `H[p,0] = 0` exactly.
- `e_Tr = y - Tr[H]` (operator Tr gauge), reported as raw x, y components and vector norm.
- `s = y - y[:,0]` (physical recentred observation trajectory).
- `eta = s - H` (physical-gauge observation error).
- Algebra: `eta = e_Tr - e_Tr[:,0]` exactly when `H[:,0]=0`; the raw actual closure `max|eta - (e_Tr - e_Tr[:,0])|` is reported per case/arm. Only roundoff is expected; no scientific gate is attached, and a value above 1e-12 px would be reported as unexpected, not tuned away.
- `e_Tr[:,0]` is the observed reference offset/nuisance. It is not evidence about frame-0 noise.
- Fitted point-field error (sealed coefficients only): `F_pub[p,g] = w8_fit.field(coeff, u_p, v_p, g)` with `u = x/nx - 0.5`, `v = y/ny - 0.5`; error `= F_pub - H` (equal to total field minus G minus H). Coefficient sets: native runtime (measured), legacy refit (stage 1), B2 refit (stage 1). This is a point-centre estimand, not dense ROI accuracy. The sealed ROI metrics (Å) are linked and never rescored or replaced.

## Confirmed Tr mapping (before computing)
The mapping `Tr[R] = R(g) + 0.5*R(1)` with `R = T - G` is the one used in the retained-only challenge (`tiny_challenge.py` lines 33-34; `TINY_DIAGNOSTIC_PLAN.md` item 4; both pinned in `PINS.json`) and is the pin-to-pin relation behind the existing G3 check `y1 = 3*y0` (|y1 - 3 y0| <= 2e-5 px in pinned `w8_refit.py`; reported per set as `G3_max_px`, not a new gate). The unpinned plan text `native_b2_20261026/independent_gemini4argon/FROZEN_PLAN.md` states the same operator. Definition agrees with the parent's; no mismatch.

## STOP conditions (stop without changing any gauge or definition)
Unsupported shape; nonfinite value; a patch lacking any of frames 1..5; `G[0]` or truth at g=0 at an accepted centre not exactly zero; non-integral or out-of-range centre; any input hash different from `PINS.json`; any frozen script differing from `FREEZE.txt`; thread variables not all 1; a Tr definition mismatch.

## Quantities reported
Per accepted patch and frame (all patches, all frames, no filtering): `y, H, Tr[H], e_Tr, s, eta`, each as x, y and vector norm. Summaries (RMS of the vector norm, max norm, signed component means, component RMS, n):
- per frame across patches, for `H`, `e_Tr`, `eta`, and each fitted point-field error;
- per patch over g=1..4 (also g=1..3 and g=4 separately; `e_Tr` also over g=0..4);
- overall, with the g=4 endpoint kept separate from g=1..3.
Arm changes ON minus OFF on common patches (vector change, change of norm, per frame, per patch, overall). Full ranked lists, not threshold-filtered: patch/frame rows by norm for `eta`, `e_Tr`, each fitted error, plus patch RMS and arm-change rankings. `eta` at g=0 is identically zero by construction and is not ranked.

The excluded patch (noisy (104,47) in both arms) is listed as excluded with no observation and is not imputed; no truth value is tabulated for it. Its log iteration criterion (final RMSD 1.5895 px OFF, 8.36418 px ON) is retained as a separate criterion with no point-truth claim; log iteration sequences for every patch are tabulated as context.

## Precision and provenance
STAR observations carry 5-decimal rounding (half-unit 5e-6 px per axis), so `s` and `eta` are precision-limited (a difference of two rounded values carries up to 1e-5 px per axis). The 40-frame compatibility ceiling (0.01313142874082845 px) is not borrowed as an accuracy test here.

## Interpretation rules (frozen)
No new gate, margin or threshold; no pass/fail; no causal shares between tables (ON/OFF changes are changes, not attributions); a point truth need not maximize a finite-window CCF, so a nonzero `eta` is not by itself an estimator defect; one noisy realization, no independence or generalization claim; NOT_A_CANDIDATE, the old noisy B2 harm and all sealed statuses stay fixed; the vague quantity `observation - (truth - G)` is not used as a physical error before the Tr correction (it is `e_Tr + 0.5*H[:,1]` in disguise and is not reported).

## Checks before the run (criteria frozen, no relaxation)
`test_resid_lib.py` checks the new implementation against tiny hand arrays (Tr image, constant-nuisance case, frame-0 and frame-3 perturbation cases, summary formula, STOP conditions, a wrong half-factor negative control) and the pinned `w8_fit.field` coefficient layout. It uses no project data.

## Resources
CPython 3.13.7 / NumPy 2.4.2 (`~/.local/bin/python3`), one numeric thread (OMP/OPENBLAS/MKL/VECLIB = 1), scratch under 100 MB in `/tmp/mc-lfw-observation-residual-20261027-r1`, RAM under 1 GB (largest array a 1 MB truth field); the run records interpreter identity, wall time and peak RSS. Failed attempts are preserved (`ATTEMPTS.md`).

## Freeze order
`resid_lib.py`, `test_resid_lib.py` (hand arrays passed, one failed first attempt preserved in `out/`), `observe.py`, `make_tables.py`, `build_pins.py`, then `PINS.json`, then `FREEZE.txt` (sha256 of PLAN, PINS and all scripts) before `observe.py` first loads any truth or observation.
