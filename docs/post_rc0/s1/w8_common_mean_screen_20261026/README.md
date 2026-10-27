# Common-mean correction: offline NO-GO

The frozen B2+CM screen is rejected by its predeclared Rule 2: five previously passing in-model movies fail after replacing the B2 patch mean by the observed mean minus its frame-0 value. Passes fall from 68/80 to 67/80, with five losses and four rescues. B2's previous scientific NO-GO remains unchanged. No native implementation is warranted on this evidence.

| Newly failing movie | B2 | B2+CM | Limit |
|---|---:|---:|---:|
| contrast025-s03, RMS Å | 0.190288 | 0.217043 | 0.20 |
| contrast4-s03, RMS Å | 0.186492 | 0.207861 | 0.20 |
| dose1-s03, RMS Å | 0.186632 | 0.208104 | 0.20 |
| pedestal0-s03, RMS Å | 0.186443 | 0.207862 | 0.20 |
| contrast025-s04, maximum Å | 0.763602 | 0.805758 | 0.80 |

The four seed-3 rows share one noise draw. These are correlated cases; no independent-sample inference or p-value is claimed. Rule 1's median mean-square change over eight predeclared failing seed groups is −0.00127849 Å² and does not reject the arm. The separate ANY-new-failure rule does.

The plan was frozen at 18:13:33 UTC on 26 October 2026, SHA256 `427d215cb64313a6e9013293407591db38da4fac20963b82af19702064b6303b`. Exactly 100 exposed W8 movies were admitted, ten seeds per condition, using 300 metadata files. The input manifest `60a67d64729ee0c93317ffa0fa110c9d2b647b390a33fd07dfd7ec334ce29ad9` is unchanged before/after. Stage 1 used observations and existing B2 coefficients without truth access or refitting. Scoring used the unchanged `4fa272f6` evaluator, fixed 129×129 ROI, frame-0 gauge and .20/.40/.80 Å limits. The ten no-local movies remain unchanged; the ten outmodel movies remain a separate characterization, with no floor subtraction.

Sonnet 5.5 HIGH performed the screen. The parent independently verified all 490 original manifest entries, recomputed the frozen decision and counts, and rebuilt the correction and direct field metrics for all nine changed-status movies. See [parent review](parent-review/REPORT.md) and [numeric results](parent-review/RESULT.json). The author's all-row baseline and cross-term-identity checks remain author-reported beyond that bounded independent scope.

Mean-square error decreases in 58/80 in-model cases, but this does not override new gate failures. The original report records 92 strict metric increases in 47/90 fitted movies. Its explanatory sentence about tails is conditional algebraic context, not an established physical cause; the parent qualification retains that distinction. Spatially varying errors are untouched by this uniform correction.

No MotionCorr producer, build, image read, STAR writer, native applied-field test, N5/harm campaign or CUDA execution was performed for this arm. No estimator adoption, new tolerance, native qualification or speedup claim follows. This hypothesis is closed; a different intervention requires its own discriminating plan.

## Evidence

[PLAN.md](PLAN.md), [original report](REPORT.md), scripts, admission, scoring records, regression CSV and original logs are retained verbatim. [EVIDENCE_INDEX.json](EVIDENCE_INDEX.json) binds the complete verified local archive, including the extracted source/input authority and stage-1 correction array. Those duplicate input/source trees stay outside Git. `ORIGINAL_SHA256SUMS` applies to that full original archive, whereas `SHA256SUMS` binds this compact package. Parent audit assertion failures and corrections are retained separately and did not modify any original result. The screen is based on W8 `0b3478b5` and source/input authority `4fa272f6c3cb5cec35d98b270ed1c4067adf6160`.
