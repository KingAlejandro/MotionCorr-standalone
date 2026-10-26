# W8: offline intercept refit of the H7a F observations (100 #269 movies)

**Result.** The B2 refit takes the H7a F STAR patch observations and fits the same 18-term field with one nuisance intercept per patch and axis, at the physical time z = f. Both predictions hold and neither refutation rule fires. Dose1-family median RMS falls from 0.265 to 0.134 Å, in-model movies meeting all three limits rise from 22 to 68 of 80, and the median in-model RMS improvement is 47%. One movie regresses at the max: dose4-s00 goes from 0.289 to 0.514 Å but still passes. These are **offline reconstructions** scored by the unchanged evaluator. They are not native applied fields, and nothing here is a native, serialisation or scientific adoption claim.

Plan and predictions were frozen before any computation ([PLAN.md](PLAN.md), `95a853e0`). Amendment 1, made before the census in response to review, renamed R-ser to R-hyb and corrected the gate (`6aea2825`). The predictions were not changed.

## Predictions vs results (R-rt vs the native runtime field)

| frozen rule | result | verdict |
|---|---|---|
| P1 dose1-family median RMS ≤ 0.15 Å (40 movies, 10 independent noise realisations) | 0.1344 Å | holds |
| P2 in-model passes > 22 of 80 | 68 (native 22) | holds |
| refuted if median in-model relative RMS improvement < 20% | 47.5% (range −0.9% to +63%) | not refuted |
| refuted if median intercept r < 0.5 (frozen target, contains `+0.5 R(1)`) | 0.981 (in-model range 0.89–0.995) | not refuted |

The secondary r, with `0.5 R(1)` removed from both sides, is also 0.981, since that term is small (median RMS 0.046 px against a target RMS of 0.53 px). r is a diagnostic that fits the parameterisation. It does not show that frame-0 noise is the cause (W7 review amendment; K9 counterexample).

## Per condition (median RMS / p95 / max Å; passes of 10)

| condition | native runtime | R-rt | passes native → R-rt |
|---|---|---|---|
| dose05 | 0.380 / 0.702 / 1.596 | 0.216 / 0.385 / 0.831 | 0 → 2 |
| dose1 | 0.265 / 0.523 / 0.953 | 0.131 / 0.236 / 0.478 | 1 → 9 |
| dose2 | 0.176 / 0.337 / 0.675 | 0.097 / 0.167 / 0.333 | 7 → 10 |
| dose4 | 0.118 / 0.210 / 0.446 | 0.065 / 0.108 / 0.211 | 10 → 10 |
| pedestal0 | 0.265 / 0.523 / 0.952 | 0.132 / 0.236 / 0.477 | 1 → 9 |
| contrast025 | 0.278 / 0.546 / 1.003 | 0.136 / 0.251 / 0.517 | 1 → 9 |
| contrast4 | 0.265 / 0.523 / 0.952 | 0.132 / 0.236 / 0.477 | 1 → 9 |
| nonsquare | 0.218 / 0.409 / 0.843 | 0.108 / 0.197 / 0.407 | 1 → 10 |
| outmodel (reported separately) | 0.923 / 1.574 / 2.270 | 0.897 / 1.525 / 2.072 | 0 → 0 |
| pedestal32 | 1.582 / 2.855 / 4.338 | `NO_LOCAL_RETAINED` (no refit) | 0 → n/a |

R-hyb (STAR read-back global + full-precision B2 coefficients, a hybrid and not a serialised field), scored against the native serialised field, agrees with R-rt to within 4.3e-6 Å on every movie. It also has 68 of 80 passes. A full STAR round trip of the refit global and coefficients is **UNRUN**.

- **Still failing (12 in-model movies):** dose05 s00, s01, s02, s03, s04, s06, s08 and s09, and seed 00 of the dose1 family (dose1, pedestal0, contrast025 and contrast4 share that seed's noise draws, so this is one realisation, not four). In-model limit failures fall from 57 / 54 / 50 to 10 / 6 / 7 (RMS / p95 / max).
- **Regression (both arms):** dose4-s00, RMS 0.084 → 0.085 Å and max 0.289 → 0.514 Å. It still passes every limit; no native pass becomes a failure.
- **outmodel:** RMS improves by 0.4–3.8%, but it cannot pass. The model family's RMS floor is 0.885 Å, which exceeds the 0.20 Å limit. Its r is 0.41 and is excluded from the in-model refutation rule by the frozen counts.
- **pedestal32:** F kept no patches, so the native global-only field is kept and no observations were invented.

## Controls (all retained)

- **Arm A, the naive midpoint refit (W7's recommendation read literally): FAILED_CONTROL.** In noiseless controls it gives 0.10 px error on quadratic truth and 0.21 px on cubic, matching the reviewer's algebra, and it was not run on the census.
- **v1 gate defect.** `results/controls.json` is kept as produced. Its gate would have let B2 stay eligible on a K8 disagreement.
- **v2 gate.** `results/controls_v2.json` gates B1/B2/C as one group, and every check passes:
  - K1–K11: full rank 43/43, spatial rank 6, exact recovery to 2e-12 px, offset invariance, and equivalence within 5e-12 px.
  - K12: a forced wrong-transform disagreement of 4.0e-4 px empties the eligible set, and stage 1 refuses with exit 4.
  - K13: rank 34 of 43 is rejected.
- **Census-time checks:**
  - G3: `obs(1) = 3 obs(0)` to 1.0e-5 px.
  - G4: the native refit reproduces the runtime field to 3.4e-6 px.
  - B1/C vs B2 agree to 1.0e-11 px on the census inputs, and every fit is full rank.
  - No truth module was imported in stage 1.
  - The evaluator reproduced all 100 native `metrics.json`.
- **Smoke test:** both stages run on synthetic perfect inputs; R-rt is within 3.9e-7 Å of the truth (`results/smoke.log`).

## Receipts

- **Inputs:** H7a F `runtime.json`, `metrics.json` and `output/movie.star`, from branch `experiment/global-damping-20261026` @ `4fa272f6` (worktree clean).
  - My admission (`results/admission.json`): exactly 100 expected names, 10 per condition, 300 files, input manifest sha256 `60a67d64...`.
  - Parent admission receipt (`results/parent_admission_receipt.json`, sha256 `8cbdd887...`, for reviewed head `6aea2825`): its 300 file hashes equal mine, and a re-hash after the run matched too.
  - Ordering: my run started at 13:48 GMT after the reviewer clearance and before the parent receipt (13:48:56 UTC) arrived. It was not repeated. The inputs are identical by hash.
- **Source:** evaluator `tools/check_realistic_motion.py` sha256 `b0ab099a...` and generator `a10f694a...`, both via `git archive 4fa272f6` into `/tmp/w8src`.
- **Review:**
  - Independent read-only review cleared head `6aea2825c84b2fb9c5c45efc8cfe12e3b2675e0c`.
  - Its tiny checks: full rank 43/43, row-collinear 34/43 rejected, 3-times 37/43 rejected, all W8 (15) and W7 v2 (8) manifest hashes, and v1/v2 numeric K1–K11 identical.
  - It did not repeat the full controls or the census.
  - The census code is byte-identical to that head except one added admission line in `run_census.sh`, which calls the new `scripts/w8_admit.py`. The operator, fit, gate, refit and score scripts are unchanged.
- **Command:** `scripts/run_census.sh /tmp/w8src <H7a results/runs>`. Exit 0, 42.0 s wall (`results/census.log`).
- **Resources:** local Mac with 2 BLAS threads (load ~10 from other work), `uv run --no-project --with numpy python -I`, NumPy 2.5.4, Python 3.15.1. cpu64 was unreachable (ssh timeout). Scratch: `/tmp/w8src`, under 2 MB, deleted after the run.
- **Hashes:** `SHA256SUMS` covers PLAN, README, scripts and results.

## Limits

- **Reconstructions only.** All fields are offline reconstructions from serialised (`%12.6f`) observations. Native applied fields, a refit STAR round trip, CUDA and real data are UNRUN.
- **Shared noise.** Four in-model conditions share noise draws, so the 80 in-model movies are not 80 independent cases.
- **Causation.** Fixing a refit's convention does not prove what causes the native error. W7's causal reading stays provisional.
- **Parity.** The B2 convention changes how MotionCorr's RELION-inherited fit treats the frame-0 reference, so a native change would break parity and needs sign-off. No default, tolerance or policy was changed.

## Smallest next step

Run a default-off native CPU prototype of the B2 fit on the same 100 movies. That turns R-rt into an applied field and gives the refit STAR round trip. Acceptance: the native applied field equals the offline R-rt to STAR precision, and the pass counts match. Because the prototype changes inherited fitting code, this needs parent and maintainer authorisation.
