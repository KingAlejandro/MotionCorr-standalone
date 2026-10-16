# W-DIAG-S1: CPU vs CUDA local-motion divergence on 10216, 12963 and 10474-F3 (issue #198)

Diagnosis only. No product source, threshold or default was changed. Tier B evidence (CPU agreement); nothing here is a Tier D (scientific outcome) claim.

## Result

**The divergence is caused by the inherited patch-selection and polynomial-fit logic, not by a CUDA defect.** In each divergent case, CPU and CUDA keep a different set of patches for the 18-term local-motion fit. Usually exactly one patch converges on one backend and not on the other. That patch's trajectory is 12–100 px away from its converged neighbours. The unweighted fit has no outlier rejection, so including or excluding that one patch moves the fitted displacement field by 7–9 px. Global shifts agree to ≤0.033 px.

- **Causal test.** Dropping the flipped patch from the backend that kept it brings relative RMSE down to the global-config (G) level: 10216 **0.434 → 0.0169** (G 0.0166) and 10474-F3 **0.600 → 0.0170** (G 0.0156). 12963 needs two more patches dropped from both sides (**0.499 → 0.056**, G 0.0227). Those two converge on both backends but to trajectories that differ by up to 98 px in 1–2 frames.
- **Pre-existing.** `116eb04a`, the first-parent predecessor of the programme merges (#195/#196/#197/#178/#185/#187), gives products **byte-identical** to `1db86902` on both backends for all three families.
- **Inherited logic.** The 0.5 px convergence test, the discarding of non-converged patches, the unweighted fit and its validation are unchanged from the RELION 5.1 extraction (`4499be23`, upstream `ad0b230`). The CUDA path implements the same logic. Small float differences between FFTW/CPU and cuFFT/GPU decide which side of those discrete decisions a marginal patch lands on.

### Coordinator hypothesis: **partially supported**

| clause | verdict | evidence |
|---|---|---|
| The divergent L cases are families with non-converging patches | **supported** | 10216: 4 patches non-converged on both backends plus 1 flip. 10474-F3: 4 plus 1. 12963: 2 plus 1. Controls: 0 non-converged (tutorial, 10361). |
| Small CPU/CUDA float differences change which patches converge | **supported** | One convergence flip per divergent case: 10216 (1,4), 12963 (4,1), 10474-F3 (1,2). Deterministic: a repeat CUDA run and the diagnostic build are byte-identical. |
| …or whether patches are retried, or what the retry returns | **refuted** | CPU never retries. CUDA retries every non-converged patch, and the retry's RMSD sequence equals the first attempt's in **61/61** retries across 18 CUDA runs (to the logged 2-decimal precision). Final shifts are logged after the retry and match the CPU's non-converged results to <0.6 px in 10216. The retry costs time but does not change the result. |
| The polynomial fit amplifies this into a large image difference | **supported** | The model field moves 7.4–9.4 px (max), while common patches agree to ≤0.49 px (10216, 10474-F3). The patch drop restores G-level agreement. 57–61% of the squared image error lies in the 5 highest-error tiles of 25 (uniform: 20%). All five are in, or adjacent to, the flipped patch's row or column. |
| Non-convergence predicts divergence (10641 "predicted divergent") | **refuted as a predictor** | 10641 (with its gain): **0/25 patches converge on either backend.** Both runs log "too few valid local trajectories" and fall back to the global trajectory, so relative RMSE is 0.042 and spatially uniform. Divergence needs *partial* convergence with a patch at the decision boundary. |
| Pre-existing | **supported** | `116eb04a` is byte-identical to `1db86902` on both backends (3/3 families). |

12963 also has a second route that the hypothesis does not name. Two patches converge on both backends but follow different trajectories because a different CCF maximum is chosen in 1–2 frames: (2,5) differs by 98 px in frames 17 and 32, and (5,2) by 35 px in frames 12 and 19. This is the same mechanism (the per-frame argmax is unstable in low-SNR patches) acting without a convergence flip. `--max_iter` cannot fix it.

## Provenance

| item | value |
|---|---|
| source | `1db869025507ac801845b4001b84e6bc0e77a645` (main). Longevity build `116eb04ad359cd5bf789b28809fc2047ea155b9b`. |
| host | 4GPUs (`4-gpu-vm`), A100 80GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, nvCOMP 5.3.0.16. Release `-O3 -DNDEBUG` (checked in `flags.make`). |
| lane | GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` (pinned with `CUDA_VISIBLE_DEVICES=<UUID>`). Every run: `taskset -c 104-111`, `/tmp/motioncorr-gpu1-correctness.lock` held, `/tmp/motioncorr-bench.lock` checked before and after acquiring the lane (0 s waited in all 48 runs). |
| GPU witness | The 6 campaign-1 CUDA runs recorded none: the sampler bug W-QUAL also hit. Fixed with a threaded `/proc`-descendant sampler. All 19 later CUDA runs record GPU1's UUID only (`run.json: gpu_witness_uuids`). Five of the six campaign-1 CUDA products are byte-identical to witnessed reruns (`identity-neutrality-*.jsonl`). `e10361-L-cuda` (control) is UUID-pinned but unwitnessed. |
| binaries reused from W-QUAL | CPU `dd86cd41…a6b26439`, CUDA+nvCOMP `77db3f92…12a99`. Equal to PR #209 `build-info.txt`. |
| binaries built here | `1db86902`+diagnostic patch: CPU `11ce169a…4a74`, CUDA+nvCOMP `037bbd15…ec6eb`. `116eb04a`: CPU `7ad59e89…06a5`, CUDA+nvCOMP `6d27823a…dd18`. Full hashes are in `raw/build-info.txt`. |
| inputs | `raw/inputs-sha256.txt`. Every movie and gain matches `docs/workload_corpus/corpus.md`, and every `movies.star` matches W-QUAL's. 10216 is read from W-QUAL's re-fetch, the rest from the corpus. 10641: `HM70-1_10-A-002_0002`, gain `CountCDSRef…`, angpix 0.4. |
| options | Exactly W-QUAL's L recipe: `--use_own --dose_weighting --bfactor 150 --seed 1 <family dose/frames/gain/EER> --j 8 --patch_x 5 --patch_y 5`, plus `--gpu 0 --ingest auto` for CUDA (`tools/diag_run.py: FAMILIES`). Exact argv is in each `raw/runs/<label>/run.json`. |
| rc | 48/48 runs exited 0. |

The diagnostic patch (`tools/diag_s1_patch_dump_drop.diff`) was applied only in a scratch clone and is not on this branch. It adds env-gated code at the fit-entry point (`motioncorr_runner.cpp:3766`): `MC_DIAG_DUMP` logs every patch's final shifts, and `MC_DIAG_DROP="(iy,ix)…"` drops named *converged* patches. With the env unset, and with `MC_DIAG_DUMP=1`, its products are byte-identical to the production binaries on both backends (MRC core header + payload + STAR; 12/12 pairs, `raw/analysis/identity-neutrality-*.jsonl`).

## 1. Reproduction (`raw/analysis/<family>-L.json`)

| family | rel. RMSE | global RMS / max px | patches kept CPU / CUDA | flip | model-field diff max / rms px | same, each backend fitting only the common patches | share of sq. error in top 5 of 25 tiles |
|---|---:|---|---|---|---|---|---:|
| e10216 | **0.4344** | 0.0166 / 0.0327 | 21 / 20 | (1,4) CPU only | 7.40 / 1.63 | 0.22 / 0.033 | 0.61 |
| e12963 | **0.4990** | 0.0172 / 0.0316 | 22 / 23 | (4,1) CUDA only | 9.43 / 1.47 | 3.19 / 0.668 | 0.60 |
| e10474f3 | **0.5999** | 0.0104 / 0.0159 | 20 / 21 | (1,2) CUDA only | 7.44 / 1.58 | 0.05 / 0.015 | 0.57 |
| e10641 | 0.0416 | 0.0242 / 0.0483 | 0 / 0 | – | no local model | – | 0.20 |
| tutorial (control) | 0.0084 | 0.0049 / 0.0075 | 25 / 25 | – | 0.06 / 0.01 | 0.03 / 0.008 | 0.45 |
| e10361 (control) | 0.0091 | 0.0070 / 0.0149 | 25 / 25 | – | 0.01 / 0.01 | 0.02 / 0.009 | 0.37 |

The three divergent relative RMSE values equal W-QUAL's to four digits. The model field is the fitted local displacement evaluated on a 33×33 grid over all frames, using the STAR `_rlnMotionModelCoeff`. A Python refit of the STAR `data_local_shift` observations, using the same 18-term design as `motioncorr_runner.cpp:3815–3853`, reproduces each backend's STAR coefficients to ≤0.08 px in field terms. That refit is how the "common patches" column was computed.

## 2. Localisation

**Per-patch convergence** (per-movie logs; `raw/analysis/<family>-L.json: patches`). The median CPU/CUDA difference in iteration-1 RMSD is 0.2–0.6% in the divergent families (0.1% in the controls). The large differences are in the patches whose trajectories differ, for example 12963 (2,5) at 55% and (3,5) at 12%, and 10216 (3,3) at 7.6%.

| family | patch | CPU RMSD per iteration | CUDA RMSD per iteration | outcome |
|---|---|---|---|---|
| e10216 | (1,4) | 9.997, 1.513, 0.790, **0.483** | 10.29, 2.78, 2.83, 2.31, 2.40 (limit cycle at ≈2.2 to 20 iterations) | CPU keeps, CUDA drops |
| e10474f3 | (1,2) | 2.15, 0.98, 1.69, 2.03, **0.516** | 2.17, 0.99, 1.91, 1.84, **0.47** | CUDA keeps, CPU drops: the two sides end either side of 0.5 px |
| e12963 | (4,1) | 4.03, 1.86, 1.01, 0.93, **0.83** | 4.08, 1.86, 0.70, **0.47** | CUDA keeps, CPU drops |
| e12963 | (2,5) | 8.28, **9.07**, 0.54, 0.26 | 3.71, 0.58, 0.36 | both keep, trajectories differ |
| e12963 | (5,2) | 5.67, 1.00, 0.38 | 5.67, **5.50**, 0.52, 0.25 | both keep, trajectories differ |

**Per-patch trajectories**, including non-converged patches, from the diagnostic dump (`raw/analysis/<family>-L-dump.json`). Neighbour deviation is the maximum distance from the median of the converged 4-neighbours. It is an indicator of pathology, not a truth measure.

| family | patch | frames with CPU–CUDA diff > 1 px | max diff px | neighbour deviation CPU / CUDA px |
|---|---|---|---:|---|
| e10216 | (1,4) flip | 31, 40, 44, 46, 47 | 13.6 | 23.6 / 23.5 |
| e10474f3 | (1,2) flip | none | 0.48 | 11.9 / 11.8 |
| e12963 | (4,1) flip | 31, 32 | 1.7 | 12.9 / 11.9 |
| e12963 | (2,5) | 17, 32 | 98.4 | **100.3** / 7.1 |
| e12963 | (5,2) | 12, 19 | 35.3 | 31.4 / 36.7 |

The other common patches agree to ≤0.49 px in 10216, ≤0.18 px in 10474-F3, and ≤1.3 px in 12963, apart from the two patches above. Each difference sits in a few individual frames. This is consistent with a different CCF maximum chosen in those frames: near-tied peaks in a low-SNR 818×818 patch. Per-frame CCF values are not logged, so this attribution is an inference from the trajectories. In 10474-F3 the trajectories are effectively equal, and only the final increment falls either side of the fixed 0.5 px tolerance.

**Fit inputs and coefficients.** The STAR `data_local_shift` patch sets equal the log-derived converged sets in every run without `MC_DIAG_DROP` (`log_star_consistent`). The largest coefficient changes are 10216 coeff 12 (X·y²·z) 2.248 → 1.317; 10474-F3 coeff 30 (Y·y²·z) 0.411 → 2.799; and 12963 coeff 15 (X·xy·z) 0.837 → −0.379. In the controls, coefficients agree to ≤0.011. In the backend that keeps the flipped patch, that patch has the largest fit residual: 10216 CPU (1,4) rms 11.4 px, max 23.3 px; 10474-F3 CUDA (1,2) rms 3.4 px, max 11.0 px. CPU 12963 (2,5) has max residual 99.6 px. Fit RMSD (X / Y) is 3.8 / 5.2 px (CPU) and 2.8 / 5.2 px (CUDA) for 10216, and 4.5 / 4.2 and 3.5 / 3.9 px for 12963, against 0.9–1.3 px in the controls. Both are under the program's own 10 px rejection threshold, so neither fit is rejected.

## 3. Causal test: drop the flipped patch (`raw/analysis/*-drop*.json`)

| arm vs arm | rel. RMSE | model-field diff max px | before |
|---|---:|---:|---:|
| 10216: CPU drop (1,4) vs CUDA | **0.0169** | 0.22 | 0.4344 |
| 10474-F3: CPU vs CUDA drop (1,2) | **0.0170** | 0.05 | 0.5999 |
| 12963: CPU vs CUDA drop (4,1) | 0.3844 | 3.15 | 0.4990 |
| 12963: CPU drop (2,5)(5,2) vs CUDA drop (4,1)(2,5)(5,2) | **0.0559** | 0.23 | 0.4990 |

With the patch sets equalised, the tile error map flattens: the top-5-tile share is 0.37 / 0.36 / 0.44, against 0.57–0.61 before and 0.37–0.45 in the controls. The remaining 0.017 matches the G-config difference (0.0166 / 0.0156), so these patches explain the extra L divergence. In 12963 the residual 0.056 sits above G (0.0227), and common patches still differ by up to 1.2 px. That is not explained further here.

## 4. Longevity (`raw/analysis/*-L-116.json`, `identity-116-vs-1db.jsonl`)

`116eb04a` CPU and CUDA+nvCOMP (`--ingest auto`; EER and int16 MRC take the float route there) produce **byte-identical products to `1db86902`** for 10216, 10474-F3 and 12963 on both backends. The CPU-vs-CUDA numbers are therefore identical: 0.4344 / 0.5999 / 0.4990. The divergence predates the programme. Older builds such as `6b6adf44` were not run; the change of route at #195/#196 had already been shown product-neutral by W-QUAL route invariance.

## 5. Interpretation

**Is either backend obviously pathological?** Neither backend is consistently the outlier. Both backends feed the fit patches that sit 12–100 px from their converged neighbours. The outlier patch is CPU-kept in 10216 (1,4) and 12963 (2,5), and CUDA-kept in 10474-F3 (1,2) and 12963 (4,1). In 10216 the (1,4) trajectory is about 23.5 px from its neighbours on *both* backends; only CPU's version passes the 0.5 px test. Coefficient magnitudes (max |coeff| 0.96–2.80 across the six divergent fits) are not extreme relative to the controls (1.41–1.57). The pathology is in which patch observations reach the fit, not in the coefficients themselves. This is Tier B evidence and does not show that either output is scientifically better.

**Does a larger `--max_iter` make them agree?** Only in some cases (diagnostic; `raw/analysis/*-L-mi{10,20}.json`):

| family | max_iter 5 | 10 | 20 |
|---|---:|---:|---:|
| e10474f3 | 0.600 (20 / 21 kept) | **0.079** (25 / 25) | 0.079 (25 / 25) |
| e12963 | 0.499 (22 / 23) | 0.329 (25 / 25) | 0.329 (25 / 25) |
| e10216 | 0.434 (21 / 20) | 0.500 (22 / 22, two flips in opposite directions) | 0.434 (23 / 22) |

10474-F3 is a slow-convergence threshold effect, and its top-row patches all converge by iteration 10. In 12963, all patches converge but the different-trajectory patches remain. In 10216, CUDA's (1,4) is a limit cycle (≈2.2 px per iteration to 20 iterations), so no iteration count resolves it.

## Root-cause location (`1db86902`)

All of these are inherited from RELION 5.1 (`ad0b230`). The first import `4499be23` has the same tolerance, drop, fit, threshold and argmax lines.

- Per-frame CCF peak is a strict argmax over the search window. CPU: `src/motioncorr_runner.cpp:4732–4745`. CUDA: `src/acc/cuda/cuda_alignpatch.cu:183–235` (`findPeakAndInterpolateKernel`). Near-tied peaks are resolved by sub-ulp float differences between FFTW and cuFFT.
- Binary convergence on the final increment at a fixed 0.5 px after `max_iter`: `motioncorr_runner.cpp:4633, 4806–4810`; `cuda_alignpatch.cu:60, 685, 1003`.
- Non-converged patches are discarded and converged ones accepted with no plausibility check: `motioncorr_runner.cpp:3766`.
- Unweighted 18-term least-squares fit with no outlier rejection: `motioncorr_runner.cpp:3815–3853`. Validation is only corner smoothness (`:3866–3894`, 3 px) and fit RMSD ≥ 10 px (`:2114`, `:3928`). 10216's 5.2 px fit RMSD passes.
- Observation, not a defect: the CUDA path re-runs every completed non-converged patch (`motioncorr_runner.cpp:3610–3763`) and gets the same answer (61/61). The CPU path has no retry.

## Recommendation (options; maintainer decides)

For the RC0 support statement:

1. **State the limitation without changing code (no source change).** CPU and CUDA local-motion products agree at the global-config level when every patch's convergence status is the same on both backends: tutorial and 10361 here, and 10164 and 10028, where W-QUAL found zero STAR differences. On movies where patch alignment only partly converges (seen in 10216, 10474-F3 and 12963), the two backends can keep different patches. The fitted local model and image then differ substantially (relative RMSE 0.4–0.6). This behaviour is inherited from RELION and present before RC0. The per-movie log shows it: patches with a final RMSD ≥ 0.5 px, and "Polynomial fit RMSD" well above about 1–2 px. Optionally, suggest checking such movies or using global alignment for them.
2. **Keep it as a Tier B diagnostic and do not block RC0.** Report CPU-vs-CUDA L agreement only for movies whose patch sets match, and list the partial-convergence families separately.
3. **Post-RC0 algorithm change (parity divergence, needs sign-off and Tier C/D evidence).** For example: reject patch trajectories inconsistent with their neighbours before the fit, weight the fit, or replace the hard 0.5 px gate with a robust criterion. Any of these changes CPU output relative to RELION and breaks the `ad0b230` parity invariant. Fit quality would need known-motion (#59/#63) and downstream (#61) evidence, not CPU agreement.

Suggested next steps if wanted: a per-frame CCF peak-margin log for the flipped patches would make the "near-tied peak" attribution direct rather than inferred. A 12963 study could explain the residual 0.056.

## UNRUN and limits

- One movie per family. Other movies, 10474-F4, 10441 and 10028/10164 L were not examined beyond W-QUAL's table. 10641 was run with one movie only.
- Builds older than `116eb04a` (for example `6b6adf44`) were not run.
- Per-frame CCF peak values and the second-best peak are not logged, so the near-tie attribution is inferred.
- Retry identity is shown to the logged 2-decimal RMSD precision. Final post-retry shifts are logged at 9 digits only for the final state.
- Campaign-1 CUDA runs lack a direct GPU witness. Five are covered by byte-identity to witnessed reruns; `e10361-L-cuda` is UUID-pinned only.
- No Tier C/D evaluation, no timing, no SCARF or second venue.

## Reproduce

Scripts as run are in `tools/`: `diag_run.py` (runner with locks, taskset and witness), `campaign{1,2,3}.sh`, `build.sh`, `diag_analyze.py` (log/STAR/coefficient/refit/tile analysis; imports `tools/compare_motioncorr.py`'s `parse_mrc`), `diag_dump.py`, `diag_identity.py`, and the scratch-only `diag_s1_patch_dump_drop.diff`. Scratch root: `/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/`. Bulk MRC/PDF/EPS were deleted after analysis; MRC payload SHA-256 values for identity checks are in the `identity-*.jsonl` files. Per run, `raw/runs/<label>/` holds `run.json` (argv, binary sha256, env, rc, wall, RSS, witness), the per-movie `movie.log` and `movie.star`, `stdout.log`, `time-v.log` and the ingest witness.
