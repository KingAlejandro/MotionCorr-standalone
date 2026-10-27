# W8 common-mean counterfactual screen: NO-GO (frozen Rule 2)

**Verdict: NO-GO.** Offline counterfactual B2+CM (B2 field with its per-frame patch mean replaced by observed patch mean minus index 0) fires Rule 2 of the frozen screen: 5 in-model movies that pass all limits under B2 fail under B2+CM. Rule 1 does not fire. B2 results and the B2 NO-GO are unchanged. No native implementation is warranted.

Frozen PLAN `PLAN.md` (sha256 `427d215c…`, 2026-10-26T18:13:33Z) was written before any new correction or score. Inputs: exactly 100 movies, 300 metadata files, manifest `60a67d64…`, rehashed before and after (identical; `admission/rehash_comparison.json`). Source: W8 `0b3478b5`, H7a F inputs and unchanged evaluator/generator `4fa272f6` (hashes match). No SSH fetch was needed. Stage 1 loaded no truth/generator/evaluator module (asserted). Baseline gate passed (B2 and native reproduce `score.json` to 2e-15 Å; 68/80 B2 and 22/80 native passes; the 12 failing movies are exactly the predeclared list). The dMS identity holds to 3.8e-16 Å² on all 90 fitted movies (limit 1e-10).

## Rules
- **Rule 1 (median over 8 seed groups of mean dMS on the predeclared 12 failing rows): −0.00128 Å², does not fire.** Seed groups, mean dMS Å²: s0 −0.00736 (5 rows), s1 +0.00174, s2 −0.00424, s3 +0.00590, s4 −0.00998, s6 −0.00060, s8 −0.00196, s9 +0.00253. Three of eight groups are positive; the median is the mean of the middle two (s8 and s6).
- **Rule 2 fires: 5 movies.** contrast025-s03, contrast4-s03, dose1-s03 and pedestal0-s03 (one shared-noise realisation) go RMS 0.186–0.190 → 0.208–0.217 Å (limit 0.20). contrast025-s04 goes max 0.764 → 0.806 Å (limit 0.80; RMS improves 0.144 → 0.138). In-model passes: native 22, B2 68, B2+CM 67 (−5 lost, +4 gained: contrast4-s00, dose1-s00, pedestal0-s00 and dose05-s08 now pass).
- Of the 12 B2 failures, 4 pass under B2+CM. The other 8 still fail, among them contrast025-s00 at RMS 0.2019 (just over) and dose05-s00, s01, s02, s03, s04, s06 and s09.

## Seed clusters across the 80 in-model movies (8 movies per seed; 4 conditions share each seed's noise, so these are not 80 independent units)
| seed | mean dMS Å² | passes B2 → CM | movies with RMS regression |
|---|---|---|---|
| 0 | −0.00483 | 3 → 6 | 1 |
| 1 | +0.00002 | 7 → 7 | 3 |
| 2 | −0.00165 | 7 → 7 | 1 |
| 3 | +0.00502 | 7 → 3 | 6 |
| 4 | −0.00212 | 7 → 6 | 0 |
| 5 | −0.00113 | 8 → 8 | 3 |
| 6 | −0.00011 | 7 → 7 | 1 |
| 7 | +0.00035 | 8 → 8 | 2 |
| 8 | −0.00052 | 7 → 8 | 4 |
| 9 | −0.00048 | 7 → 7 | 1 |

## Per condition (median RMS / p95 / max Å, B2 → B2+CM; passes of 10)
| condition | RMS | p95 | max | passes | median dMS Å² |
|---|---|---|---|---|---|
| dose05 | 0.216 → 0.211 | 0.385 → 0.385 | 0.831 → 0.810 | 2 → 3 | −0.00126 |
| dose1 | 0.131 → 0.127 | 0.236 → 0.237 | 0.478 → 0.487 | 9 → 9 | −0.00020 |
| dose2 | 0.097 → 0.095 | 0.167 → 0.165 | 0.333 → 0.338 | 10 → 10 | −0.00031 |
| dose4 | 0.065 → 0.058 | 0.108 → 0.103 | 0.211 → 0.209 | 10 → 10 | −0.00072 |
| pedestal0 | 0.132 → 0.127 | 0.236 → 0.237 | 0.477 → 0.486 | 9 → 9 | −0.00029 |
| contrast025 | 0.136 → 0.131 | 0.251 → 0.241 | 0.517 → 0.495 | 9 → 7 | −0.00140 |
| contrast4 | 0.132 → 0.127 | 0.236 → 0.237 | 0.477 → 0.486 | 9 → 9 | −0.00030 |
| nonsquare | 0.108 → 0.105 | 0.197 → 0.193 | 0.407 → 0.407 | 10 → 10 | −0.00089 |
| outmodel (separate, 10 rows) | 0.897 → 0.897 | 1.525 → 1.525 | 2.072 → 2.067 | 0 → 0 | −0.00090 |
| pedestal32 (10 rows) | unchanged (`NO_LOCAL_RETAINED`, no d) | | | native 0 | n/a |

Mean-square error falls in 58 of 80 in-model movies and 9 of 10 outmodel movies. The correction is small (RMS of d: median 0.026 px, max 0.079 px).

## Regressions
Every strict RMS/p95/max increase (including those still passing): 92 entries in 47 of 90 fitted movies (in-model: 36 max, 29 p95, 22 RMS; outmodel: 3 max, 1 RMS, 1 p95). Full list: `results/regressions.csv`; per-movie values: `results/stage2_per_movie.csv`. The p95 and max regressions arise because a uniform shift cannot fix spatially varying error and shifts the tails.

## Limits
Offline reconstruction from serialised (`%12.6f`) observations, scored with the unchanged evaluator. Not a native applied field. Refit STAR round trip, native checks, N5/harm, Q-basis recovery, CUDA and real data: UNRUN. The toy common-mode noise falsifier is context only. This screen does not give an independent-sample test, and no p-values are reported. Outmodel's 0.885 Å floor is not subtracted. B2 was not re-fitted.

## Smallest next action
None on this arm: record the NO-GO. The median per-condition change in mean-square error is only about 0.0002–0.0014 Å², so a different hypothesis would need its own frozen plan.

## Files
`PLAN.md`, `pins/`, `admission/` (before/after, rehash comparison), `scripts/{s1_common_mean,s2_score,s3_tables}.py`, `results/{stage1_d.json,stage2_score.json,stage2_per_movie.csv,regressions.csv}`, `logs/` (commands, failed attempts, environment), `SHA256SUMS`. Resources: local Mac, NumPy 2.5.4 / Python 3.15.1, 2 BLAS threads, stage 2 wall 26 s, max RSS 159 MB, scratch 16 MB.
