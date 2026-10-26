# W7: what limits known-motion recovery on the #269 census (flags-off, 100 movies)

**Result.** In every in-model condition, one term dominates the flags-off field error: each patch trajectory is anchored to its own single noisy frame-0 estimate, plus half of its frame-1 error through the extrapolated origin. That fixed per-patch offset is fitted as motion and then extrapolated to the ROI edges. It accounts for 93–97% of the field mean-square error, scales with dose like noise (log-log slope −0.58), and removing only this term moves every failing in-model movie under every limit it fails (counterfactual). Representability is not the limit for in-model motion (best achievable 0.000 Å; MotionCorr's pipeline with perfect inputs 0.0016 Å RMS). For `outmodel` the model family cannot pass at all: its best achievable error is 0.885 / 1.505 / 1.775 Å (RMS / p95 / max). `pedestal32` fails because the global alignment does not converge and every patch is dropped, as H7a found.

Plan: [ANALYSIS-PLAN.md](ANALYSIS-PLAN.md), committed before any decomposition (`3b092192`). Amendment 1 changed only gate G1's wording. Amendment 2 added one post-hoc diagnostic (the anchor test), declared before it was computed. All tables: [results/tables.md](results/tables.md). Per movie: [results/per_movie.csv](results/per_movie.csv) and `results/w7.json`.

## Inputs and checks

- H7a F arm (branch `experiment/global-damping-20261026` at `4fa272f6`, PR #286): runtime capture, STAR, log and metrics for all 100 movies. Unchanged evaluator `tools/check_realistic_motion.py` (`b0ab099a...`) and generator (`a10f694a...`, identical to the cpu64 census copy) from `4fa272f6`. Receipts from cpu64 `mc-km-truth-20261021/fixtures`. The truth is analytic, so no movie was regenerated. No MotionCorr run, no GPU.
- Gates, all passing on 100/100 movies:
  - G1: receipt `movie.mrcs` sha256 equals the H7a census hash, and the recipe equals `gen.recipe`.
  - G2: re-running the evaluator reproduces every `metrics.json` number to 1e-12.
  - G3: `obs(1) = 3·obs(0)` to 1.0e-5 px, which confirms the pin and the extrapolated origin.
  - G4: refitting the 18-term model to the STAR observations at z = g + 0.5 reproduces the runtime field to 3.4e-6 px.
  - G5: the split below adds up to the actual error to 3.4e-6 px.
- Compute: cpu64 CPUs 40–47 under `flock -n /tmp/motioncorr-w7-cpu40-47.lock`, `~/.mc-venv/bin/python -I` (NumPy 2.5.3), 5.3 min, exit 0 (`results/run2.log`).

## Observation convention (from the source; G3/G4 confirm it)

With `--group_frames 1`, `alignPatch` pins each patch's frame 0 to 0. The stored observation is `local[g] + 0.5·local[1]`, fitted at z = g + 0.5, and the field is evaluated at z = f. A patch's frame-0 estimate error `eps_0` therefore enters every observation of that patch as the constant `−1.5·eps_0 + 0.5·eps_1`, with variance about 2.5·σ². Time-varying noise, by contrast, is averaged over 40 frames by the cubic fit.

## Pass/fail (T1)

22 of 100 movies meet all three limits. RMS fails in 77, p95 in 74, max in 70. Passes per condition:

| dose05 | dose1 | dose2 | dose4 | pedestal0 | contrast025 | contrast4 | nonsquare | outmodel | pedestal32 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 7 | 10 | 1 | 1 | 1 | 1 | 0 | 0 |

`dose1`, `pedestal0`, `contrast025` and `contrast4` share each seed's Poisson draws, so they are one set of 10 noise realisations seen through four affine pixel maps. Their errors are nearly identical, so the pedestal and contrast settings do not matter at this scale.

## Ranked error budget (T6, T8)

The split `e = repr + glob_const + glob_var + obs_const + obs_var` is exact and linear:

- `repr`: MotionCorr's pipeline with perfect global and patch inputs.
- `glob_*`: the part of the global trajectory error that the polynomial does not absorb.
- `obs_*`: patch observation error carried through the fit, split per patch into its time-constant mean and the time-varying rest.

The table gives median mean-square shares; cross terms make up the remainder.

| condition | obs_const | glob_var | glob_const | obs_var | repr | cross | field RMS / p95 / max | with obs_const removed |
|---|---|---|---|---|---|---|---|---|
| dose05 | 0.956 | 0.070 | 0.021 | 0.021 | 0.000 | −0.105 | 0.380 / 0.702 / 1.596 | 0.141 / 0.239 / 0.405 |
| dose1 | 0.969 | 0.064 | 0.010 | 0.019 | 0.000 | −0.070 | 0.265 / 0.523 / 0.953 | 0.085 / 0.155 / 0.276 |
| dose2 | 0.943 | 0.074 | 0.029 | 0.021 | 0.000 | −0.082 | 0.176 / 0.337 / 0.675 | 0.053 / 0.098 / 0.168 |
| dose4 | 0.933 | 0.072 | 0.023 | 0.026 | 0.000 | −0.099 | 0.118 / 0.210 / 0.446 | 0.040 / 0.072 / 0.132 |
| nonsquare | 0.956 | 0.064 | 0.017 | 0.019 | 0.000 | −0.044 | 0.218 / 0.409 / 0.843 | 0.066 / 0.117 / 0.204 |
| outmodel | 0.074 | 0.006 | 0.001 | 0.002 | **0.920** | −0.004 | 0.923 / 1.574 / 2.270 | 0.889 / 1.512 / 1.942 |
| pedestal32 | — | 0.364 | 0.398 | — | 0.253 | 0.002 | 1.582 / 2.855 / 4.338 | (no local model) |

`pedestal0`, `contrast025` and `contrast4` match dose1 to within 0.013 Å RMS (tables.md).

1. **Per-patch anchor offset (`obs_const`)** dominates every in-model condition, for all three limits.
   - Counterfactual removal of this term alone brings every failing in-model movie under each limit it fails: dose1 family 9/9 RMS, 9/9 p95 and 8/8 max; dose05 10/10 on all three; nonsquare 9/9, 7/7 and 6/6.
   - The anchor test (amendment 2) gives a ratio of the per-patch mean error to the per-frame scatter of 0.97–1.06 (median by condition). So the offset is one frame's ordinary noise turned into a constant by the pin; frame 0 is not unusually bad.
   - The per-patch offset is 1.52× the per-frame scatter at dose1 (0.584 vs 0.382 px), close to the √2.5 = 1.58 that the convention predicts.
   - The offset grows from 0.05 Å at frame 1 to about 0.3 Å by frames 11–20 as the cubic absorbs it, and it is amplified outside the patch-centre hull: dose1 interior 0.196 Å, edge 0.358 Å, corner 0.472 Å.
2. **Global trajectory error the polynomial does not absorb**: 7–10% of the mean square. It largely cancels against (1) through a negative cross term, because the global and the patch anchors share frame 0's noise. Removing it alone rescues no failing movie on RMS, and 2 of 7 nonsquare movies on p95.
3. **Time-varying patch noise** (`obs_var`): about 2%.
4. **Representability and conventions** for in-model motion: at most 0.009 Å max. The half-frame z convention, centre vs patch-mean truth (0.010 px RMS) and the forward/inverse gap (0.008 px RMS) are all negligible.

The gain diagnostic (slope of `delta` on the ideal observation) is −0.16 / −0.12 at dose05 and within ±0.08 elsewhere. Patches that stopped after one iteration have smaller `delta` than two-iteration patches, so incomplete convergence is not a source.

**Not systematic.** The field RMS and every component scale with dose at log-log slopes from −0.47 to −0.58 (T7). The limit is how noise is propagated: one frame's noise per patch is promoted into the fitted motion.

**Rigid vs local (T2).** The per-frame spatial mean is 13–17% of the mean square in in-model conditions. The rest is local, and the maxima sit at corners in 82 of the 90 non-`outmodel` movies (edges in the other 8). 85–96% of above-p95 points lie outside the patch-centre hull, although that region holds only 35% of the lattice.

## Representability (T5; reported separately, never subtracted)

Values are RMS / p95 / max in Å, identical across the 10 seeds of each condition.

| truth | best fit on the lattice (R-lat) | MotionCorr pipeline with perfect inputs (R-pipe) |
|---|---|---|
| in-model (all 4096² conditions and nonsquare) | 0.0000 / 0.0000 / 0.0000 | 0.0016 / 0.0036 / 0.0094 |
| `outmodel` | **0.8849 / 1.5054 / 1.7753** | **0.8850 / 1.5049 / 1.7777** |

The `outmodel` sinusoid (2 px amplitude, one period across the frame) is outside the quadratic-in-space family. Even the best lattice fit exceeds every limit by 2–4×, so `outmodel` cannot pass with this model family and estimator improvements cannot change that. Its measured error (0.923 Å RMS) sits 0.04 Å above that floor.

## Recommended next experiment

**Offline refit of the H7a F observations with a free per-patch intercept.** Keep the same 18-term model, the STAR observations and the global trajectory, and add one nuisance constant per patch and axis. Then score the refit with the unchanged evaluator. This needs no pixels, no MotionCorr run and no GPU: it reads the retained STAR files, using the fit that G4 shows is exact. The intercept is identifiable only because the local model is zero at z = 0 and cubic.

- **Hypothesis.** The per-patch anchor offset is what limits the in-model conditions.
- **Prediction.** Median dose1-family field RMS falls from 0.265 Å to at most 0.15 Å, and in-model passes rise from 22. The −obs_const counterfactual (0.085 Å) is the lower bound; the extra intercepts cost some variance.
- **Refuted if** the median in-model RMS falls by less than 20%, or the fitted intercepts correlate with the measured per-patch offset (`delta` const, known from truth) at r < 0.5.

If the prediction holds, any production change moves the anchor convention, which is RELION-inherited code. That breaks parity and needs sign-off. This experiment does not touch production code.

## Limits

CPU F arm only. The C arm is not decomposed, since H7a shows C ≈ F outside `pedestal32`. PR #284 Tier B shows CUDA flags-off also meets all limits in 22/100 movies, but CUDA was not decomposed here. Truth is the generator's analytic model and gauge (frame 0). The ablations are attributions, not achievable results. Ten seeds per condition, and four of the conditions share noise draws. The anchor test was added after the first run (amendment 2).

## Files

- `scripts/analyze_w7.py`: gates, the decomposition and `w7.json`.
- `scripts/summarize_w7.py`: `tables.md` and `per_movie.csv`.
- `results/`: outputs. SHA-256 of all files is in `SHA256SUMS`.

## Review amendment (2026-10-26, additive; the text above is unchanged)

Early independent review accepted the W7 algebra and gates but corrected four interpretations. They supersede the wording above where they conflict.

- **Shares.** The mean-square shares, with their cross terms, are a descriptive split of one exact sum. They are not causal percentages, and "93–97% of the error" should be read as the standalone share of one additive component.
- **Anchor.** The per-patch time-constant component `mean(delta)` is not necessarily frame-0 noise. An anchor ratio near 1 shows only that the data are compatible with an i.i.d. single-anchor model. Counterexample (checked in W8 K9): a deterministic `eps` that is 0 on frames 0–19 and `a` on 20–39 has no frame-0 error, yet gives `delta(1) = 3 delta(0)` and ratio sqrt(20/19) = 1.026. The ratio cannot establish cause.
- **Representability.** R-lat is a least-squares RMS floor. Its p95 and max are those of the RMS-optimal fit, not minima of p95 or max. Counterexample (W8 K10): for `y = [0, 0, 3]` the least-squares constant gives RMS 1.414, p95 1.9 and max 2, while the constant 1.5 gives 1.5 for all three. The `outmodel` impossibility rests on the RMS floor 0.885 > 0.20 (and max ≥ RMS), not on individual p95 or max floors.
- **Counterfactual.** The −obs_const counterfactual (dose1 0.085 Å) is not a lower bound for any augmented refit, and W8 does not use it as one. As W8's controls show, a naive midpoint intercept refit is also biased even without noise: under `Tr`, a quadratic truth publishes as `b(f² - f)` and a cubic as `c(f³ - 1.5 f² + 0.75 f)`.

These causal claims stay provisional until the independent review completes. The W8 refit tests them directly.

## Manifests

- `SHA256SUMS` is frozen and binds the original W7 revision `1342b28f`: README `4106d963...`, before the review amendment. Its README line therefore does not match this file.
- `SHA256SUMS.v2` binds this amended revision. Every other file is unchanged and has the same hash in both manifests.
