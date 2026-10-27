# Audit disposition (additive; status stays NOT_A_CANDIDATE)

Disposition of the independent Opus audit (`audit/REPORT.md`, sha256 98425f53…; verdict "SUPPORTED, bounded"). The frozen `screen/PLAN.md`, `screen/PINS.json`, scripts and results are unchanged by this file. It only states what the screen does and does not establish. The audit's findings were low severity; none changes a number or the status.

## What the audit confirmed

- An independent solver and STAR basis reproduce all 56 metrics (32 native, 24 offline) to <= 1.4e-13 Å.
- Noisy B2 + full-width (R-rt / R-hyb): 0.82485 / 1.65200 / 3.21674 Å against limits 0.20 / 0.40 / 0.80 Å. It misses by 0.62 / 1.25 / 2.42 Å, so no margin or ceiling choice can change the status.
- The five retained passes stay passes; the old noisy harm (B2 on old-weight observations, 1.9026 / 4.2003 / 9.2948 Å) reproduces.

## Bounds on the audit's low findings

**(a) Isolation is observed, not proved.** The sealed receipts record 0 `other` and 0 forbidden opens (40 staged, 6 pinned-source, 104 interpreter/NumPy). The implementation did not enforce an empty `other` class: `isolation_audit_hook_no_forbidden_or_foreign_open` is set from forbidden-substring hits only. The audit hook also misses bytes-path opens, and C-level opens are invisible to it. Attempt 1 recorded 44 `other` opens (a `/tmp` symlink classification defect) and its guard still reported `overall_pass: true`. This package makes no claim of proved truth isolation. The verdict does not rest on it: the audit's own computation reproduces every metric from the staged inputs.

**(b) `stage2_score.py` is not in the seal.** It was written after the seal (00:04:35Z against the seal at 00:04:11Z) and is absent from `out/stage1_seal.json`. Only the criteria (`PLAN.md`, `PINS.json`) were fixed beforehand. The independent re-score closes the dependence on this script. "Scored once" rests on file times and stdout, not on a sealed receipt.

**(c) The 0.01313142874082845 px ceiling is a compatibility ceiling only.** It was derived as a 40-frame vector bound (`native_b2_20261026/rounding_prediction.json`, `vector_bound_px`). The screen applied it as a component-wise maximum on 5-frame fixtures without re-deriving it. It is not a scientific or noisy-acceptance margin, and no status depends on it. Observed values, from the audit, kept in separate units:

| comparison (audit `a2_reeval.json`) | coefficient max abs diff | field component max (px) | field vector max (px) |
|---|---|---|---|
| control, noisy: offline B2 on OFF obs vs native UP_B2 | 3.04e-5 | 1.119e-5 | 1.119e-5 |
| control, affine | 6.42e-5 | 1.301e-5 | 1.303e-5 |
| legacy replay, worst set (pedestal ON) | 5.44e-5 | 7.886e-6 | 7.889e-6 |
| legacy replay, noisy OFF | 3.24e-5 | 6.125e-6 | 7.158e-6 |

The coefficient column (3.0e-5 to 6.4e-5) is in coefficient units, not field pixels, and is not the bounded quantity; do not compare it with the ceiling. The vector maxima are about 1000 times below the ceiling. The ceiling does separate the wrong arm: legacy against B2 differs by >= 0.0338 px (5.03 px for noisy OFF). No retroactive derived gate is added, and the original control receipts are unchanged.

**(d) R-hyb is not a genuine refit serialization.** It combines the STAR read-back global with full-precision coefficients. The STAR global differs from the runtime global by <= 5.0e-6 px, so R-hyb and R-rt differ by < 1e-6 Å in these cases. A genuine B2 refit written and read back through STAR was not run. For reference, native full-precision against STAR coefficient fields differ by 1.2e-4 to 4.7e-4 px (legacy) and 2.9e-4 px (native UP_B2).

**(e) Increases and ties.** All four max-metric PASS→PASS increases against native ON are retained as reported: affine 0.32948 → 0.33075 Å (R-rt) and 0.32950 → 0.33075 Å (R-hyb); pedestal 0.33018 → 0.33087 Å (R-rt) and 0.33016 → 0.33087 Å (R-hyb). None is an increase against native OFF. No value is within 0.011621 Å (ceiling × 0.885 Å/px) of a limit; the closest is 0.1258 Å (integer RMS). The only ties are the five local-disabled cases (zero, integer, fractional, flat, repeated), which have no local observations and are unchanged by construction. The screen did not enumerate them one by one; `RESULT_TABLES.md` carries them as unchanged.

**(f) Status is fixed.** NOT_A_CANDIDATE stands. The old noisy B2 harm stands. Flat and repeated remain UNIDENTIFIABLE. No native run follows from this screen.

## Table units

`RESULT_TABLES.md` puts coefficient |Δ| beside a field-pixel column; both are labelled in the table, but read them as different quantities (see (c)).

## Audit execution

One audit run failed and is preserved (`audit/results/FAILED_ATTEMPTS.txt`): the system Python 3.15.1 had no NumPy (rc 1); the rerun used the packet's interpreter. Audit cost: peak RSS 54 MB, 0.6 s.
