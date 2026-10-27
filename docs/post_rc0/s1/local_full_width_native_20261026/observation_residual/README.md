# Observation-residual diagnostic (descriptive; NOT_A_CANDIDATE unchanged)

One saved-metadata diagnostic: no fit, intervention, CCF, pixels, SSH or native run; no gate, threshold or acceptance claim. Definitions, formulas, STOP rules and tables were frozen first (`PLAN.md`, `PINS.json`, `FREEZE.txt`); the Tr mapping `Tr[H] = H + 0.5*H[:,1]` matches the pinned `tiny_challenge.py` / `TINY_DIAGNOSTIC_PLAN.md` item 4 and the existing G3 check, so no STOP. `y` is the stored STAR observation, `H = truth(centre) - G`, `e_Tr = y - Tr[H]`, `s = y - y[:,0]`, `eta = s - H`. Algebra `eta = e_Tr - e_Tr[:,0]` closes to <= 8.9e-16 px. Full tables: `out/RESULT_TABLES.md`, `out/RANKED_LISTS.md`; values: `out/observation_residual.json`.

## Where the error sits (RMS of vector norm, px, patches' frames g=1..4)
| case/arm | eta | e_Tr | largest patch (eta RMS, share of sum eta^2) | g1-3 / g4 eta |
|---|---|---|---|---|
| noisy OFF | 3.208 | 3.610 | (62,79): 7.495, 68% (one row: g4 |eta| 14.81 px) | 1.890 / 5.519 |
| noisy ON | 1.423 | 1.969 | (104,15): 2.394, 35% | 1.437 / 1.378 |
| affine OFF | 0.182 | 0.212 | (104,15): 0.359, 43% | 0.147 / 0.260 |
| affine ON | 0.105 | 0.123 | (104,15): 0.217, 47% | 0.083 / 0.153 |
| pedestal OFF / ON | 0.182 / 0.105 | 0.212 / 0.123 | (104,15): 0.359 / 0.218 | 0.147 / 0.260 and 0.083 / 0.154 |

- **Noisy, old weight:** the observation error is one patch-frame, (62,79) at g=4, eta = (10.56, -10.39) px; other patches are 1.1 to 3.1 px RMS. With full-width ON that row is 1.61 px.
- **Noisy, full-width:** point-observation errors remain: eta RMS 1.42 px against H RMS 1.15 px. They are flat over frames (1.47, 1.40, 1.44, 1.38 px at g=1..4) while H grows from 0.24 to 1.91 px, and g=4 is no longer special. The largest patch is (104,15), where eta is about -1.8 to -2.7 px in x and -0.9 to -1.4 px in y at every g=1..4. (20,47) is the only noisy patch whose RMS is higher ON than OFF (1.31 to 1.45 px).
- **Affine and pedestal, full-width:** eta grows about linearly with g (0.038, 0.078, 0.116, 0.153 px) at about 0.27 of the H RMS per frame (OFF about 0.46 to 0.48); (104,15) is largest, then (20,47) and (20,79). (20,15) is the only patch with a higher RMS ON than OFF (0.035 to 0.044 px).
- **e_Tr[:,0]** (observed reference offset, not evidence of frame-0 noise): RMS 0.81 / 0.74 px noisy OFF / ON, 0.033 / 0.019 px affine.
- **Fitted published field minus H at the patch centres** (sealed coefficients; different estimand from the dense ROI metrics, which are linked in T0 and not rescored): noisy ON native/legacy 1.538, B2 1.142 px; noisy OFF legacy 2.330, B2 2.663 px; affine ON 0.0989 (legacy) and 0.0985 (B2) px.
- **Excluded patch:** noisy (104,47) has no observation in either arm and is not imputed; its log iteration criterion goes from final RMSD 1.5895 px (OFF) to 8.36418 px (ON), with no point-truth claim.

## Limits
This describes where the stored point observations differ from the unchanged truth and global. It cannot separate objective, iteration, noise or window causes, and the ON/OFF changes are not causal shares. A point truth need not maximize a finite-window CCF. One noisy realization. STAR observations carry 5-decimal rounding (up to 1e-5 px per axis in `s` and `eta`); the 40-frame compatibility ceiling is not used as an accuracy test. The concentration shares and eta/H ratios come from `supplementary.py` (post-freeze arithmetic). Nothing here reopens the B2 candidate.

Environment: CPython 3.13.7, NumPy 2.4.2, one numeric thread, 0.06 s, peak RSS in `out/observation_residual.json`; scratch 1.4 MB. Attempts: `ATTEMPTS.md` (one failed hand-array test attempt, a test defect, preserved).
