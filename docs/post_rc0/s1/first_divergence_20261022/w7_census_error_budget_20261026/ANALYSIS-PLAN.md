# W7 analysis plan: error budget of flags-off recovery on the #269 census

Written and committed before any decomposition below was computed. Descriptive attribution only: no hypothesis tests, no p-values, no thresholds tuned to the data.

**Question.** On the 100 #269 seeded motion-truth movies (4096x4096x40, nonsquare 5760x4092x40, CCF cropped ~4x), flags-off MotionCorr fails at least one of the 0.20 / 0.40 / 0.80 Å field limits in 78 movies. What limits recovery?

**Known when this plan was written.** The H7a README, its per-movie table (F and C field RMS/p95/max per movie), one F `metrics.json`/`movie.star`/`movie.log` (contrast025-s00), the PR #284 Tier B summary (CPU and CUDA `none` both meet all limits in 22/100), and the source of `alignPatch`, `interpolateShifts` and the polynomial fit. No decomposition, refit or representability number had been computed.

## Inputs (read only)

- F arm of H7a, branch `experiment/global-damping-20261026` head `4fa272f6` (PR #286): `results/runs/<movie>/F/{runtime.json, output/movie.star, output/movie.log, metrics.json}` for all 100 movies.
- Evaluator `tools/check_realistic_motion.py` (sha256 `b0ab099a...`) and its imports, and generator `test-data/generate_realistic_motion.py` (sha256 `a10f694a...`, equal to the cpu64 census copy `v2/test-data/`), both from `4fa272f6`, used unchanged. The truth is the generator's analytic `displacement()`; no pixels are needed and no movie is regenerated.
- `RECEIPT.json` for each movie from cpu64 `/home/ubuntu/mc-km-truth-20261021/fixtures/<movie>/`.

No MotionCorr runs, no GPU. Compute on cpu64 CPUs 40-47 under `flock -n /tmp/motioncorr-w7-cpu40-47.lock` with `~/.mc-venv/bin/python -I`.

## Notation and conventions (the evaluator's, unchanged)

- Truth `T(f,x) = -displacement(r,f,x,y)` on the evaluator's 129x129 lattice over the ROI `[32, n-33]`, frames `f = 0..39`. Field `M(f,x) = global[f] + P(z=f,u,v)` with the 18-term polynomial, `u = x/nx - 0.5`, `v = y/ny - 0.5`. Error `e = M - T`. Metrics are the evaluator's `vector_metrics` on vector magnitudes over all frames and lattice points (frame 0 included), in Å (0.885 Å/px).
- `g(f)` is the evaluator's declared global drift (the generator's `g`, the full-frame spatial mean of the truth for both motion models).
- Patch observations are the STAR `data_local_shift` rows. From the source, with `--group_frames 1` (`interpolate_shifts = 0`): `alignPatch` pins `local[0] = 0`; the stored observation is `obs(p,g) = local[g] - interp(0) = local[g] + 0.5 local[1]` (linear extrapolation of the group centres `g + 0.5` to frame 0), and it is fitted at `z = g + 0.5`. Patch centre `x_c = (x_start + x_end - 1) / 2` as in the log. Patches are extracted from globally aligned frames, so the quantity a patch measures is `R(p,g) = T(p,g) - global[g]`.
- Ideal observation for the actual run: `obs*(p,g) = Tr[R(p,.)](g)` with `Tr[h](g) = h(g) - h(0) + 0.5 (h(1) - h(0))` (`h(0) = 0` here). Observation error `delta = obs - obs*`.
- `Fit[o]` is the 18-term least-squares fit of observations `o` at the observed patch centres and `z = g + 0.5`, evaluated on the lattice at `z = f`.

## Validation gates (all must pass before any table is produced; on failure stop and report)

- **G1 receipts**: each receipt's sha256 equals the RECEIPT hash recorded in the F `metrics.json` identity, and its recipe equals `gen.recipe(condition, seed)` (no generation is needed for the truth).
- **G2 evaluator reproduction**: calling the evaluator's `evaluate()` on the F runtime model reproduces every number in the F `metrics.json` (field, global_trajectory, local_component, border, serialized_field), exactly or to 1e-12 relative.
- **G3 observation convention**: for every patch, `obs(p,1) = 3 obs(p,0)` to STAR rounding (≤ 2e-5 px), which checks `local[0] = 0` and the extrapolated origin.
- **G4 fit reproduction**: `Fit[obs]` from the STAR rows reproduces the runtime coefficients; the max lattice difference between the refitted and the runtime field is reported and must be ≤ 0.005 px.
- **G5 additivity**: the decomposition in T6 reconstructs `e` on the lattice to ≤ 0.005 px max.

## Tables

All per-movie values go to a CSV/JSON; the README shows per-condition medians and ranges over the 10 seeds. Note on independence: `dose1`, `pedestal0`, `contrast025` and `contrast4` share the Poisson draws for each seed (they differ by an affine pixel transform), so they are not independent replicates; this is reported, not corrected for.

- **T1 pass/fail**: 10 conditions x 10 seeds, F runtime field, unchanged evaluator; for each movie which limits fail (RMS, p95, max); per-condition counts per limit.
- **T2 rigid vs local**: `e = ebar(f) + etilde`, with `ebar(f)` the lattice spatial mean per frame. Exact mean-square shares, and the evaluator metrics of each part.
- **T3 temporal**: per-frame RMS of `e`, `ebar`, `etilde` in frame bins `0` (zero by convention), `1`, `2-10`, `11-20`, `21-30`, `31-39`; frame holding the max. Global trajectory error `eps_g(f) = global[f] - g(f)` split into its mean over `f = 1..39` (time-constant part, which contains the frame-0 anchor error), its cubic-in-z projection of the remainder (absorbable by the polynomial), and the rest (jitter).
- **T4 spatial**: lattice regions by the patch-centre hull: interior (both coordinates within the extreme patch centres), edge (one outside), corner (both outside). Point fraction per region, RMS of `e` and `etilde` per region, share of lattice-frame points above the movie's p95 per region, region and frame of the max.
- **T5 representability (reported separately, never subtracted from any error)**:
  - `R-lat`: best fit of `T` in the model family on the lattice itself (free `global[f]` with `global[0] = 0`, 18 coefficients, `z = f`), least squares; evaluator metrics of its residual. A lower bound on the field RMS the model family can reach.
  - `R-pipe`: MotionCorr's pipeline with perfect inputs: `global = g`, observations `Tr[T(p,.) - g]` at the patch centres and `z = g + 0.5`, the same fit, evaluated by the unchanged evaluator.
  - Both per movie (they depend only on the condition's motion and geometry). Sensitivity, reported only: ideal observations as the patch-area mean of the truth instead of the centre value; and the size of the forward-vs-inverse convention gap `|d(x) - d(q(x))|` on the lattice (the evaluator is not changed).
- **T6 observation vs fit**: exact linear split `e = e_repr + e_glob + e_obs`, where `e_repr` is the R-pipe residual, `e_glob = eps_g - Fit[Tr[eps_g]]` (spatially uniform) and `e_obs = Fit[delta]`. Further: `delta` per patch into its mean over frames (time-constant, anchor-like) and the rest; `eps_g` into time-constant over `f >= 1` and the rest. For each component: standalone evaluator metrics; mean-square share with the cross terms listed so the shares add to the total; and the ablation (evaluator metrics of `e` with that component removed), reported as a counterfactual for attribution, not as an achievable result. Observation diagnostics: RMS of `delta`; its least-squares slope on `R` per movie and axis (a gain/convergence diagnostic); `delta` RMS by patch iteration count (1 vs 2 or more) from the log. `pedestal32` F has no local model: there `e = (g - T) + eps_g`, reported separately.
- **T7 dose scaling**: per-component median RMS at dose 0.5 / 1 / 2 / 4 and the log-log slope over the four doses (a purely noise-limited component scales with slope -0.5; a systematic one with ~0).
- **T8 ranking**: per condition, components ranked by mean-square share for the RMS limit and by ablation change for p95 and max; the share of the failing-limit error attributed to each where the split is exact. Then the single smallest discriminating next experiment, stated with its hypothesis and the observation that would refute it.

## Out of scope

The C arm, CUDA, the evaluator, limits, ROI, generator and gauge are not changed. No new estimator is implemented or run here; the next experiment is named, not executed.
