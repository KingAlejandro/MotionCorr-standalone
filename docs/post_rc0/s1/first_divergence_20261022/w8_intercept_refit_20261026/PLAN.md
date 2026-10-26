# W8 plan: offline refit of the H7a F patch observations with a per-patch nuisance intercept

Frozen and committed before any W8 fit, control or census number was computed. Offline reconstruction only: no pixels, no MotionCorr run, no CUDA, no other Maarten case. Nothing here is a native or scientific adoption claim. The W7 causal reading is provisional pending independent review (W7 review amendment).

## Question and predictions

W7 recommended refitting the retained H7a F observations with one nuisance constant per patch and axis. Predictions (Sol, frozen here) for the census-eligible arm, runtime-global refit:

- **P1** dose1-family (dose1, pedestal0, contrast025, contrast4: 40 movies but only 10 independent noise realisations) median field RMS ≤ 0.15 Å.
- **P2** in-model movies meeting all three limits rise above 22 of 80.
- **Refuted if** the median over the 80 in-model movies of the relative RMS improvement `(RMS_native - RMS_refit) / RMS_native` is below 20%, or the median per-movie Pearson r between fitted intercepts and truth-derived offsets is below 0.5.

Counts: 80 in-model (dose05, dose1, dose2, dose4, pedestal0, contrast025, contrast4, nonsquare), 10 `outmodel` (refit and scored, reported separately; its RMS floor is 0.885 Å, so it cannot pass), and 10 `pedestal32` (F kept no patches, so status `NO_LOCAL_RETAINED`: native global-only field kept, no observations invented, no refit). Same-noise conditions are not independent; no test treats them as such.

## Observation convention and arms

With `--group_frames 1` the STAR stores `obs(p,g) = Tr[h](g) = h(g) + 0.5 h(1)` with `h(0) = 0`, plus noise. The published physical field is `h(f) = sum_{s,k} c_sk S_s f^k` (k = 1..3; S = 1, u, u², v, v², uv), added to the fixed global trajectory `G[f]` and evaluated at z = f. Intercepts are nuisance parameters and are never published.

- **A (naive midpoint; the W7 recommendation read literally).** Fit `q(z) = sum a_k S z^k` at z = g + 0.5 plus a patch intercept, and publish `q(f)`. Expected to fail the quadratic and cubic controls even without noise. Under Tr, the published field is `b(f² - f)` for `h = b f²` and `c(f³ - 1.5 f² + 0.75 f)` for `h = c f³` (reviewer algebra; K4/K5 check it). A failure is retained as a failed arm and A is not run on the census.
- **B1 (physical design).** Columns `S_s (g^k + 0.5)` plus a patch intercept; publish `c`.
- **B2 (integer time).** Columns `S_s g^k` plus a patch intercept; publish `c`. B2 spans the same columns as B1 because `0.5 S_s(p)` is constant within a patch.
- **C (midpoint, transformed).** Fit `q` at z = g + 0.5 plus a patch intercept, then publish `h(f) = q(f + 0.5) - q(0.5)`. Per spatial monomial: `c3 = a3`, `c2 = a2 + 1.5 a3`, `c1 = a1 + a2 + 0.75 a3`. Same span as B.

B1, B2 and C must agree (K8). The census arm is B2, with B1 and C carried as equivalence checks. Noiseless exactness holds only if the actual residual `Tc - G` is cubic. A fixed erroneous or non-cubic `G` can bias every arm, and the census numbers include that.

**Truth isolation.** `scripts/w8_fit.py` imports only NumPy. Its inputs are observations, patch coordinates, frame indices and the arm; it never sees truth, the generator or the evaluator. Truth is used only to build controls and to score.

## Controls (each arm; all must pass before any census fit)

Using the actual 4096² and 5760x4092 patch geometries (from the F logs):

- **K1 rank and conditioning.**
  - Spatial matrix at the patch centres has rank 6.
  - At least 4 distinct times per patch.
  - Full rank 18 + n_patches per axis, with raw and column-scaled singular values (min, max, condition) reported.
- **K2 gauge.** The published field at f = 0 is exactly 0.
- **K3–K6 recovery.** Recovery of linear, quadratic and cubic fields, and of a random full 18-term field, from noiseless `Tr[h]`. Max lattice error ≤ 1e-8 px.
- **K7 offset invariance.** Adding random per-patch, per-axis offsets to the observations changes the published field by ≤ 1e-8 px.
- **K8 equivalence.** B1, B2 and C give the same published coefficients and field (≤ 1e-8 px) on K6 inputs and on a random noisy input.
- **K9 W7 counterexample.** Deterministic `eps` (frames 0–19 = 0, frames 20–39 = a) has no frame-0 error, yet gives `delta = Tr[eps] = eps`, `delta(1) = 3 delta(0)`, and anchor ratio sqrt(20/19) = 1.026. So the W7 anchor ratio cannot establish cause. Checked numerically.
- **K10 LS-floor counterexample.** For `y = [0, 0, 3]`, the least-squares constant (1) gives RMS sqrt(2), p95 1.9, max 2. The constant 1.5 gives RMS 1.5 and p95 = max = 1.5. So an RMS-optimal fit does not minimise p95 or max. Checked numerically.
- **K11 perfect census inputs.** With `G = g` and observations `Tr[Tc - g]`, the refit field is scored with the unchanged evaluator. Expected ≤ 1e-8 px for in-model; `outmodel` is reported only.

An arm that fails any of K1–K8 is recorded `FAILED_CONTROL` and not run on the census. A K9–K11 result is reported, not gated. On an unexpected failure of B or C: stop, keep the failure, diagnose, and report before any amended run.

## Census (held until the parent acknowledges the controls, per the reviewer's HOLD)

Inputs: H7a F `runtime.json`, `output/movie.star` and `output/movie.log` (branch `experiment/global-damping-20261026` @ `4fa272f6`). Unchanged evaluator and generator from `4fa272f6` (sha256 `b0ab099a...` and `a10f694a...`). Recipes come from `gen.recipe` (W7 G1 tied them to the receipts and movie hashes). Re-running the evaluator on the native runtime model must reproduce each F `metrics.json` (W7 G2) before scoring.

Arms scored separately, all offline reconstructions:

- **R-rt.** Runtime (full-precision) global + B2 refit of the STAR observations.
- **R-ser.** STAR read-back global + B2 refit of the same STAR observations.

The STAR observations are the only observation source, and they are serialised. Comparators are the native runtime field (`metrics.field`) and the native serialised field (`metrics.serialized_field`). All are scored by the unchanged evaluator (`evaluate()` on a model dict). Reported:

- **T1** pass/fail per movie for both arms.
- **T2** per-condition median RMS / p95 / max.
- **T3** P1, P2 and the refutation quantities.
- **T4** intercept correlation per movie: fitted B2 intercepts vs the truth-derived offset `d(p) = mean_g [obs(p,g) - (Tc(p,g) - G(g))]`.
- **T5** every regression: refit RMS above native, or a native limit pass that fails after the refit.
- **T6** outmodel and pedestal32 statuses.

Compute: cpu64 was unreachable at preflight (ssh timeout), so this runs on the local Mac with 2 BLAS threads (`uv run --no-project --with numpy python -I`, NumPy 2.5.4). Scratch ≤ 1 GB.

## Amendment 1 (pre-census, from independent review; predictions and refutation rules unchanged)

- **Arm naming.** The frozen "R-ser" is renamed **R-hyb**: STAR read-back global plus full-precision B2 coefficients. It is a hybrid offline reconstruction, not a serialised field. A full global-plus-coefficient STAR round trip of the refit is **UNRUN**, because no pinned writer is invoked offline. Both arms are offline reconstructions, not native applied fields.
- **Gate correction.** v1 `w8_controls.py` let B2 stay eligible on a K8 disagreement. Its results are kept unchanged (`results/controls.json`). The versioned `w8_controls_v2.py` (`results/controls_v2.json`) treats B1/B2/C as one equivalence group: a K8 or any member failure makes all three ineligible. It adds:
  - **K12:** a forced disagreement from a wrong C transform must break K8, empty the eligible set, and make stage 1 refuse (exit 4).
  - **K13:** a rank-deficient geometry must be rejected.

  The census consumer (`w8_refit.py` via `w8_gate.py`) refuses unless v2 allows it, and requires every census fit to be full rank (rank equal to the number of columns).
- **Truth isolation.** The census runs as two processes. Stage 1 (`w8_refit.py`) reads only `runtime.json` and the STAR file, and asserts at exit that no generator or evaluator module was imported. Stage 2 (`w8_score.py`) adds truth for scoring only.
- **Correlation target.** The frozen T4 target `d = mean_g[obs - (Tc - G)]` contains the `+0.5 R(1)` convention term, which is the correct target for the B2 intercept. It stays the gating quantity for the r < 0.5 rule. A secondary r, with `0.5 R(1)` removed from both the intercept and the target, is reported only.
- **Pipeline smoke test.** `test_w8_pipeline.py` runs both stages on two synthetic movies built from analytic truth, with no census data: perfect in-model inputs and a no-local movie.
