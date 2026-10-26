# W8 common-mean counterfactual screen (offline, new explicitly labelled arm "B2+CM")

Frozen before any new correction or score was computed. Only input admission/hash checks and schema reading of the retained W8 JSON were done first. This is a **new offline counterfactual arm**, not an amendment to W8/B2. Every B2 result and NO-GO stands unchanged. No repository edit, native/MotionCorr/GPU job, build, movie/pixels, held-out data, default/gate/ROI/generator/gauge change, publication or subagent. No Maarten or reserved case.

## Question
Does replacing only the B2 field's per-frame patch mean by the observed patch mean minus its index-0 value help the retained W8 errors? The total field changes by a uniform (spatially constant) per-frame shift `d[f]`. Independent review (Opus, `REPORT.md` item 2) shows this equals the total-field effect of augmenting the B2 fit with an arbitrary common temporal component, with the patch intercepts free. It can amplify common-mode noise (toy falsifier in `Global-refit-feasibility-r1`, retained as context; its iid noise costs are not native variance, and it says nothing about Q-canonical global/local recovery). No improvement is assumed. Tr-alpha differences are absorbed by the intercepts, but real observation noise stays correlated (`obs(1)=3*obs(0)`). Only the patch-mean temporal component is saturated, not each patch. Spatially varying errors are untouched.

## Pins (authorities)
- Mathematical: `/Users/alex.konstantinov/Documents/MotionCorr-evidence/20261026/Global-refit-feasibility-r1/{PLAN.md,check.py,RESULT.json,README.md,SHA256SUMS}`, `/tmp/mc-global-refit-opus-review-20261026-r1/{REPORT.md,review_result.json,MANIFEST.sha256}`, `.../mc-global-refit-opus-review-20261026-r1/PARENT_QUALIFICATIONS.md` (all read first; hashed in `pins/`).
- W8 documents, scripts and results: git objects at `0b3478b5` under `docs/post_rc0/s1/first_divergence_20261022/w8_intercept_refit_20261026/` (PLAN, README, scripts, `results/{refit,score,admission}.json`), extracted with `git archive`. The shared root checkout is stale and is not used.
- Census inputs: 100 H7a F movies (10 conditions x seeds 0..9: dose05, dose1, dose2, dose4, pedestal0, contrast025, contrast4, nonsquare, outmodel, pedestal32), original source `4fa272f6c3cb5cec35d98b270ed1c4067adf6160`, metadata only (`F/runtime.json`, `F/metrics.json`, `F/output/movie.star`; 300 files). Extracted from git objects at `4fa272f6`. Admission with the unchanged W8 `w8_admit.py` must give manifest sha256 `60a67d64729ee0c93317ffa0fa110c9d2b647b390a33fd07dfd7ec334ce29ad9`, equal to W8's `admission.json`. The local worktree copy at the same commit is cross-checked. No SSH fetch is needed, and no MRC is fetched.
- Evaluator/generator: `tools/check_realistic_motion.py` sha256 `b0ab099a256e458b1c8aea6c2ff5d9ceacab10dd81945b025e96e5c8a87b7ff9`, `test-data/generate_realistic_motion.py` sha256 `a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380`, from `git archive 4fa272f6`, unchanged. Fixed 129x129 lattice, frame-0 gauge, pixel units, Å limits RMS 0.20 / p95 0.40 / max 0.80.
- Runtime: local Mac, `uv run --offline --no-project --with numpy python -I -B`, same NumPy 2.5.4 / Python 3.15.1 as W8, BLAS/OMP threads capped at 2, scratch under 100 MB, memory under 512 MB.

## Stage 1 (truth inaccessible; `scripts/s1_common_mean.py`)
Reads only: `F/output/movie.star` (observations, geometry, via the reviewed W8 `read_star`), `F/runtime.json` (native G), and the existing stored B2 coefficients and patch centres in `refit.json@0b3478b5`. It imports no generator/evaluator/truth module (asserted at exit). B2 is not re-fitted. Time convention: STAR local-shift frame index `a[0]-1` = physical frame `f=0..39` (W8 `read_star`; the stored `G3 = max|obs(1)-3 obs(0)|` is recomputed as a convention check, expected <= 2e-5 px). For each fitted movie and axis:
- `m_obs[f] = mean_p obs[p,f]` over the complete 25 patches x 40 frames (completeness asserted);
- `m_B2[f] = mean_p local_B2(p,f)` at the same patch centres (`u=x/nx-.5`, `v=y/ny-.5`, `z=f`, 18 coefficients as stored); `local_B2(.,0)=0` exactly is asserted;
- `d[f] = m_obs[f] - m_obs[0] - m_B2[f]`, with `d[0]=0` asserted.
The counterfactual total field is B2 total + `d[f]` (uniform in space). Stage 1 writes only `d`, `m_obs`, `m_B2`, G and the stored coefficients' identity (no truth, no nuisance, no STAR serialization claim). The 10 `pedestal32` movies are `NO_LOCAL_RETAINED` and exactly unchanged (no observations invented, no d). The resulting G is not claimed physical truth, and its split differs from the Q-canonical one, though the total field is equivalent.

## Stage 2 (scoring only; `scripts/s2_score.py`)
Imports the unchanged evaluator/generator. Order:
1. Baseline gate: re-evaluate the stored B2 R_rt and the native runtime model for all 90 fitted movies and compare with `score.json@0b3478b5` within 1e-9 Å on RMS/p95/max, and require 68 of 80 in-model passes and 22 native. Any failure stops the run and is retained (no scorer repair, no gate adjustment).
2. Counterfactual: evaluate the model with `global = global_runtime + d` and the stored B2 coefficients (R-rt arm only; the R-hyb arm is not scored).
3. Identity check: `dMS = pixel_size^2 * mean_f(||d_f||^2 + 2 d_f . mean_ROI(error_B2[f]))` against direct `RMS_new^2 - RMS_old^2` in Å², tolerance 1e-10 Å², over all 90 movies. The ROI mean is over the fixed 129x129 lattice, `d_f` and the error are in px, and the mean over f includes f=0. This is an exact cross-term identity, not a causal attribution or a floor. If it fails, that is retained and reported.

## Fixed primary screen and stop rules (set now)
- Scored set: all 80 in-model movies. All 100 retained in the inventory. `outmodel` (10 rows) is a separate characterization (full-model RMS floor 0.885 Å cannot be subtracted, no scalar floor subtraction). `pedestal32` unchanged.
- Predeclared B2 failing in-model movies (12): dose05 seeds 00, 01, 02, 03, 04, 06, 08, 09; and seed 00 of dose1, pedestal0, contrast025, contrast4 (checked against `score.json`).
- **Rule 1.** These share noise draws. For each seed, the mean of dMS (Å²) over its predeclared failing rows. Seed 0 has 5 rows (dose05, dose1, pedestal0, contrast025, contrast4). Seeds 1, 2, 3, 4, 6, 8, 9 each have the dose05 row. The statistic is the median across the 8 seed groups {0,1,2,3,4,6,8,9}. **If median >= 0: NO-GO** before any native implementation.
- **Rule 2.** Any in-model movie that passes all three limits under B2 and fails any of them under B2+CM is **NO-GO**.
- List every RMS/p95/max numerical regression (strictly higher than B2), including those still passing.
- If neither rule fires, the label is only `NOT_REFUTED_OFFLINE`. Promotion stays blocked pending N5/harm, native applied-field and actual STAR tests. No automatic new experiment.
- Reporting: all 10 seed clusters over the 80 (mean dMS, pass counts), per-condition values (median RMS/p95/max before/after, passes, median dMS). The 80 correlated movies are not treated as independent, with no unplanned p-values. Frame-0 gauge, sign conventions, ROI and limits unchanged.

## Unrun / out of scope
Full refit STAR round trip, native applied field, Q-basis/global-local recovery, CUDA, real data, any production/native implementation, publication: UNRUN.

## Failure policy
Any failed attempt, stop or mismatch is kept in `logs/` and listed in the REPORT. Inputs are rehashed before and after (`admission/`).
