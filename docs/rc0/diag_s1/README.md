# W-DIAG-S1: CPU vs CUDA local-motion divergence on 10216, 12963 and 10474-F3 (issue #198)

Diagnosis only. No product source, threshold or default was changed. Tier B evidence (CPU agreement); nothing here is a Tier D (scientific outcome) claim. Revised after the R-S1 review of PR #212 (round 1: §6 and the corrections listed at the end).

## Result

**Patch acceptance and the unweighted polynomial fit amplify a small per-frame peak-selection difference into a large image difference.** In each divergent case, CPU and CUDA keep a different set of patches for the 18-term local-motion fit. Usually exactly one patch converges on one backend and not on the other. That flipped patch's trajectory is 12–24 px from its converged neighbours. In 12963 a separate patch, accepted on both backends, also deviates by up to 100 px. The fit has no outlier rejection, so these patches move the fitted displacement field by 7–9 px. Global shifts agree to ≤0.033 px.

- **Causal test.** Dropping the flipped patch from the backend that kept it brings relative RMSE down to the global-config (G) level: 10216 **0.434 → 0.0169** (G 0.0166) and 10474-F3 **0.600 → 0.0170** (G 0.0156). 12963 also needs two different-trajectory patches dropped from both sides (**0.499 → 0.056**, G 0.0227).
- **Initiating events.** The CCF logs show frames where two separate CCF maxima are within a few float ulps of each other, and the two backends' maps order them differently. Examples: 10216 (1,4) frame 46 is an exact tie on the CPU map and a 5-ulp lead on the CUDA map; 12963 (2,5) frame 32 is a 3-ulp CPU lead against a 35-ulp CUDA lead for the other peak.
- **#70 tie rule tested (§6).** Exact ties do occur. On CUDA's own maps the production lane reduction picks a different peak than CPU's rule would in 1–14 frame-iterations per movie. A CUDA variant with CPU tie semantics changes CUDA output on 10216 and 12963 but leaves CPU agreement essentially unchanged: 0.434 → 0.430, 0.600 → 0.600, 0.499 → 0.499, with the same kept sets and flips. **Verdict: not involved in this divergence.** #70 remains a real, smaller semantic difference.
- **Pre-existing.** `116eb04a` produces the same core MRC header, pixel payload and per-movie STAR as `1db86902` on both backends, for all three families.
- **What is inherited.** The 0.5 px convergence test, the discarding of non-converged patches, the CPU peak search, and the unweighted fit and its validation are unchanged from RELION 5.1 (`ad0b230`; extraction `4499be23`). The CUDA peak selector is standalone code and does not share CPU tie semantics (#70).

This does **not** establish that CUDA is free of defects. It establishes that the tested divergence is not explained by the #70 tie rule. The CUDA and CPU CCF maps differ by small amounts, and those differences reorder near-tied peaks. Whether they are pure rounding was not established.

### Coordinator hypothesis: **partially supported**

| clause | verdict | evidence |
|---|---|---|
| The divergent L cases are families with non-converging patches | **supported** | 10216: 4 patches non-converged on both backends plus 1 flip. 10474-F3: 4 plus 1. 12963: 2 plus 1. Controls: 0 non-converged (tutorial, 10361). |
| Small CPU/CUDA float differences change which patches converge | **supported** | One convergence flip per divergent case: 10216 (1,4), 12963 (4,1), 10474-F3 (1,2). Deterministic: repeat CUDA runs are identical. §6 shows the flips start at near-tied CCF peaks, not at CUDA tie handling. |
| …or whether patches are retried, or what the retry returns | **refuted at logged precision** | CPU never retries. CUDA retries every non-converged patch, and the retry's RMSD sequence equals the first attempt's in 61/61 retries across 18 CUDA runs (R-S1 found 107/107 over all 25 round-0 CUDA logs). This holds only to the 2-decimal logged RMSD: first-attempt and retry shift vectors are not logged separately, so exact retry neutrality is not shown. |
| The polynomial fit amplifies this into a large image difference | **supported** | The model field moves 7.4–9.4 px (max), while common patches agree to ≤0.49 px (10216, 10474-F3). The patch drop restores G-level agreement. 57–61% of the squared image error lies in the 5 highest-error tiles of 25 (uniform: 20%), all in or adjacent to the flipped patch's row or column. |
| Non-convergence predicts divergence (10641 "predicted divergent") | **refuted as a predictor** | 10641 (with its gain): 0/25 patches converge on either backend. Both runs fall back to the global trajectory (`motioncorr_runner.cpp:3809–3812`), so this local-fit amplification is absent. The remaining 0.042 relative RMSE is spatially uniform; that is not an image-gate pass. |
| Pre-existing | **supported** | `116eb04a` = `1db86902` in core header, payload and STAR on both backends (3/3 families). |

**Matching patch sets do not guarantee agreement.** 12963 keeps 22/22 patches after the flip-only drop and still reads 0.384. At `--max_iter` 10 and 20 both backends keep all 25 patches and it reads 0.329. Partial convergence is a warning sign, not a necessary or sufficient classifier.

## Provenance

| item | value |
|---|---|
| source | `1db869025507ac801845b4001b84e6bc0e77a645` (main). Longevity build `116eb04ad359cd5bf789b28809fc2047ea155b9b`. |
| host | 4GPUs (`4-gpu-vm`), A100 80GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, nvCOMP 5.3.0.16. Release `-O3 -DNDEBUG` (checked in `flags.make`). |
| lane | GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` (pinned with `CUDA_VISIBLE_DEVICES=<UUID>`). Every run: `taskset -c 104-111`, `/tmp/motioncorr-gpu1-correctness.lock` held, `/tmp/motioncorr-bench.lock` checked before and after acquiring the lane (0 s waited in all 92 runs). |
| GPU witness | The 6 round-0 campaign-1 CUDA runs recorded none: the sampler bug W-QUAL also hit. Fixed with a threaded `/proc`-descendant sampler. All 41 later CUDA runs (19 round 0, 22 round 1) record GPU1's UUID only (`run.json: gpu_witness_uuids`). |
| binaries reused from W-QUAL | CPU `dd86cd41…a6b26439`, CUDA+nvCOMP `77db3f92…12a99`. Equal to PR #209 `build-info.txt`. |
| binaries built here | Round 0, `1db86902` + dump/drop patch: CPU `11ce169a…4a74`, CUDA+nvCOMP `037bbd15…ec6eb`. `116eb04a`: CPU `7ad59e89…06a5`, CUDA+nvCOMP `6d27823a…dd18`. Round 1, `1db86902` + dump/drop + CCF/tie patch: CPU `7bad3c9c…0585`, CUDA+nvCOMP `48085dda…a06a`. Full hashes are in `raw/build-info.txt`. |
| inputs | `raw/inputs-sha256.txt`. Every movie and gain matches `docs/workload_corpus/corpus.md`, and every `movies.star` matches W-QUAL's. 10216 is read from W-QUAL's re-fetch, the rest from the corpus. 10641: `HM70-1_10-A-002_0002`, gain `CountCDSRef…`, angpix 0.4. |
| options | Exactly W-QUAL's L recipe: `--use_own --dose_weighting --bfactor 150 --seed 1 <family dose/frames/gain/EER> --j 8 --patch_x 5 --patch_y 5`, plus `--gpu 0 --ingest auto` for CUDA (`tools/diag_run.py: FAMILIES`). Exact argv and diagnostic env are in each `raw/runs/<label>/run.json`. |
| rc | 92/92 runs exited 0 (48 round 0, 44 round 1 with prefix `r1-`). |

**Scope of "identical".** Identical here means `tools/diag_identity.py`: the MRC core header (bytes 0–223), the pixel payload, and the per-movie STAR, compared byte for byte. MRC labels (224–1023, which carry a run timestamp) and the extended header are not part of the verdict; round-1 records report them separately (extended header equal in all 30 pairs, labels differ). Logs, PDF/EPS and the output inventory are not compared. This is narrower than the gate contract's `exact` profile.

**Diagnostic builds** are applied only in scratch clones and are not on this branch. `tools/diag_s1_patch_dump_drop.diff` adds env-gated code at the fit-entry point (`motioncorr_runner.cpp:3766`): `MC_DIAG_DUMP` logs every patch's final shifts, and `MC_DIAG_DROP="(iy,ix)…"` drops named *converged* patches. `tools/diag_s1_r1_ccf_ties.diff` (round 1) adds `MC_DIAG_CCF=<file>`, which writes per-frame CCF statistics to a separate file, and `MC_DIAG_CPU_TIES=1` (§6).

**Neutrality** (switches off or logging only, against production; `raw/analysis/`):

| build / switches | pairs identical | record |
|---|---|---|
| dump/drop build, env unset (10216 CPU and CUDA) | 2/2 | `identity-neutrality-A.jsonl` (round 0) |
| dump/drop build, `MC_DIAG_DUMP=1`, 5 families × 2 backends | **10/10** | `r1-identity-neutrality-dumpbuild.jsonl` (round-1 rerun with component verdicts and digests) |
| round-1 build: env unset, and `MC_DIAG_CCF`+`MC_DIAG_DUMP`, 4 families × 2 backends; tie variant with and without logging | **20/20** | `r1-identity-neutrality-ccfbuild.jsonl` |
| round-0 vs round-1 production STAR | 10/10 | `r1-star-r0-vs-r1-prod.txt` |

The round-0 dump neutrality record (`identity-neutrality-dump.CORRUPT-truncated-by-cut.jsonl`) is malformed. My shell pipeline passed the tool's output through `cut -c1-60,300-` before `tee`, which truncated every record. It is retained under that name and superseded by the round-1 rerun of the same binaries. R-S1 independently confirmed that all five drop arms leave every other patch's trajectory, the global STAR and the remaining local STAR observations unchanged.

## 1. Reproduction (`raw/analysis/<family>-L.json`)

| family | rel. RMSE | global RMS / max px | patches kept CPU / CUDA | flip | model-field diff max / rms px | same, each backend fitting only the common patches | share of sq. error in top 5 of 25 tiles |
|---|---:|---|---|---|---|---|---:|
| e10216 | **0.4344** | 0.0166 / 0.0327 | 21 / 20 | (1,4) CPU only | 7.40 / 1.63 | 0.22 / 0.033 | 0.61 |
| e12963 | **0.4990** | 0.0172 / 0.0316 | 22 / 23 | (4,1) CUDA only | 9.43 / 1.47 | 3.19 / 0.668 | 0.60 |
| e10474f3 | **0.5999** | 0.0104 / 0.0159 | 20 / 21 | (1,2) CUDA only | 7.44 / 1.58 | 0.05 / 0.015 | 0.57 |
| e10641 | 0.0416 | 0.0242 / 0.0483 | 0 / 0 | – | no local model | – | 0.20 |
| tutorial (control) | 0.0084 | 0.0049 / 0.0075 | 25 / 25 | – | 0.06 / 0.01 | 0.03 / 0.008 | 0.45 |
| e10361 (control) | 0.0091 | 0.0070 / 0.0149 | 25 / 25 | – | 0.01 / 0.01 | 0.02 / 0.009 | 0.37 |

The three divergent relative RMSE values equal W-QUAL's to four digits. The model field is the fitted local displacement, evaluated from the STAR `_rlnMotionModelCoeff` on a 33×33 grid over all frames. A Python refit of the STAR `data_local_shift` observations, using the same 18-term design as `motioncorr_runner.cpp:3815–3853`, reproduces each backend's STAR coefficients to ≤0.08 px in field terms. That refit produced the "common patches" column.

## 2. Localisation

**Per-patch convergence** (per-movie logs; `raw/analysis/<family>-L.json: patches`). The median CPU/CUDA difference in iteration-1 RMSD is 0.2–0.6% in the divergent families and 0.1% in the controls. The large differences are in patches whose trajectories differ, for example 12963 (2,5) at 55% and (3,5) at 12%, and 10216 (3,3) at 7.6%. The convergence test is strict `rmsd < 0.5` after each iteration, with early exit (`motioncorr_runner.cpp:4804–4810`).

| family | patch | CPU RMSD per iteration | CUDA RMSD per iteration | outcome |
|---|---|---|---|---|
| e10216 | (1,4) | 9.997, 1.513, 0.790, **0.483** | 10.29, 2.78, 2.83, 2.31, 2.40 (still cycling at ≈2.2 at 20 iterations) | CPU keeps, CUDA drops |
| e10474f3 | (1,2) | 2.15, 0.98, 1.69, 2.03, **0.516** | 2.17, 0.99, 1.91, 1.84, **0.47** | CUDA keeps, CPU drops: the two sides end either side of 0.5 px |
| e12963 | (4,1) | 4.03, 1.86, 1.01, 0.93, **0.83** | 4.08, 1.86, 0.70, **0.47** | CUDA keeps, CPU drops |
| e12963 | (2,5) | 8.28, **9.07**, 0.54, 0.26 | 3.71, 0.58, 0.36 | both keep, trajectories differ |
| e12963 | (5,2) | 5.67, 1.00, 0.38 | 5.67, **5.50**, 0.52, 0.25 | both keep, trajectories differ |

**Per-patch trajectories**, including non-converged patches, from the diagnostic dump (`raw/analysis/<family>-L-dump.json`). Neighbour deviation is the maximum distance from the median of the converged 4-neighbours; it indicates pathology and is not a truth measure.

| family | patch | frames with CPU–CUDA diff > 1 px | max diff px | neighbour deviation CPU / CUDA px |
|---|---|---|---:|---|
| e10216 | (1,4) flip | 31, 40, 44, 46, 47 | 13.6 | 23.6 / 23.5 |
| e10474f3 | (1,2) flip | none | 0.48 | 11.9 / 11.8 |
| e12963 | (4,1) flip | 31, 32 | 1.7 | 12.9 / 11.9 |
| e12963 | (2,5), common | 17, 32 | 98.4 | **100.3** / 7.1 |
| e12963 | (5,2), common | 12, 19 | 35.3 | 31.4 / 36.7 |

The other common patches agree to ≤0.49 px in 10216, ≤0.18 px in 10474-F3, and ≤1.3 px in 12963, apart from the two patches above. Each large difference sits in a few individual frames. §6 shows directly that these frames have two separate CCF maxima within a few float ulps of each other. In 10474-F3 the trajectories are effectively equal, and only the final increment falls either side of the 0.5 px tolerance.

**Fit inputs and coefficients.** The STAR `data_local_shift` patch sets equal the log-derived converged sets in every run without `MC_DIAG_DROP`. The largest coefficient changes are 10216 coeff 12 (X·y²·z) 2.248 → 1.317; 10474-F3 coeff 30 (Y·y²·z) 0.411 → 2.799; and 12963 coeff 15 (X·xy·z) 0.837 → −0.379. In the controls, coefficients agree to ≤0.011. In the backend that keeps the flipped patch, that patch has the largest fit residual: 10216 CPU (1,4) rms 11.4 px, max 23.3 px; 10474-F3 CUDA (1,2) rms 3.4 px, max 11.0 px. CPU 12963 (2,5) has a max residual of 99.6 px. Fit RMSD (X / Y) is 3.8 / 5.2 px (CPU) and 2.8 / 5.2 px (CUDA) for 10216, and 4.5 / 4.2 and 3.5 / 3.9 px for 12963, against 0.9–1.3 px in the controls. All are under the 10 px rejection threshold (`:2114`, `:3926–3938`). That check and the corner-gradient check (`:3866–3894`) can reject a whole model, but they never remove a bad patch or refit.

## 3. Causal test: drop the flipped patch (`raw/analysis/*-drop*.json`)

| arm vs arm | rel. RMSE | model-field diff max px | before |
|---|---:|---:|---:|
| 10216: CPU drop (1,4) vs CUDA | **0.0169** | 0.22 | 0.4344 |
| 10474-F3: CPU vs CUDA drop (1,2) | **0.0170** | 0.05 | 0.5999 |
| 12963: CPU vs CUDA drop (4,1) | 0.3844 | 3.15 | 0.4990 |
| 12963: CPU drop (2,5)(5,2) vs CUDA drop (4,1)(2,5)(5,2) | **0.0559** | 0.23 | 0.4990 |

With the patch sets equalised, the tile error map flattens: the top-5-tile share is 0.37 / 0.36 / 0.44, against 0.57–0.61 before and 0.37–0.45 in the controls. The remaining 0.017 matches the G-config difference (0.0166 / 0.0156). In 12963 the residual 0.056 sits above G (0.0227), common patches still differ by up to 1.2 px, and that residual is not explained.

## 4. Longevity (`raw/analysis/*-L-116.json`, `identity-116-vs-1db.jsonl`)

`116eb04a` CPU and CUDA+nvCOMP (`--ingest auto`; EER and int16 MRC take the float route there) produce the **same core header, payload and STAR as `1db86902`** for 10216, 10474-F3 and 12963 on both backends. The CPU-vs-CUDA numbers are therefore identical (0.4344 / 0.5999 / 0.4990). The divergence was present before the programme merges. Older builds such as `6b6adf44` were not run.

## 5. Interpretation

**Is either backend obviously pathological?** Neither backend is consistently the outlier.
- The outlier patch is CPU-kept in 10216 (1,4) and 12963 (2,5), and CUDA-kept in 10474-F3 (1,2) and 12963 (4,1).
- Both backends feed the fit flipped patches that sit 12–24 px from their neighbours. In 12963 there is also a common patch at up to 100 px.
- In 10216, the (1,4) trajectory is about 23.5 px from its neighbours on both backends; only CPU's version passes the 0.5 px test.
- Coefficient magnitudes (max |coeff| 0.96–2.80 across the six divergent fits) are not extreme relative to the controls (1.41–1.57).

This is Tier B evidence and does not show that either output is scientifically better.

**Does a larger `--max_iter` make them agree?** Only partly (diagnostic; `raw/analysis/*-L-mi{10,20}.json`):

| family | max_iter 5 | 10 | 20 |
|---|---:|---:|---:|
| e10474f3 | 0.600 (20 / 21 kept) | **0.079** (25 / 25) | 0.079 (25 / 25) |
| e12963 | 0.499 (22 / 23) | 0.329 (25 / 25) | 0.329 (25 / 25) |
| e10216 | 0.434 (21 / 20) | 0.500 (22 / 22, two flips in opposite directions) | 0.434 (23 / 22) |

10474-F3 falls to 0.079, still above its G level (0.0156). In 12963 all patches converge, but the different-trajectory patches remain. In 10216, CUDA's (1,4) is still cycling at ≈2.2 px per iteration at 20 iterations; §6 shows it alternating between two near-tied peaks in frame 46. Behaviour beyond 20 iterations was not tested.

## 6. Round 1: CCF peak margins and the #70 tie rule

**Question.** CPU keeps the first equal maximum in signed-y-then-x order (`motioncorr_runner.cpp:4732–4743`). Production CUDA scans that same ordinal order in 256 strided lanes with strict `>` and then reduces by value only (`cuda_alignpatch.cu:203–234`). For equal values it can therefore return a later ordinal than CPU (#70). Does this cause the S1 divergence?

**Method** (scratch build `tools/diag_s1_r1_ccf_ties.diff`; runs `raw/runs/r1-*`; analysis `raw/analysis/r1-*`; logs `raw/runs/r1-*-ccf-*/ccf.txt.gz`):
- `MC_DIAG_CCF` logs, for every patch, iteration and frame on both backends:
  - the CCF maximum;
  - the peak each tie rule picks on that map (CPU rule, and an exact host emulation of the CUDA lane reduction);
  - the number of exact float ties for the maximum;
  - the best competing 8-neighbour local maximum outside the 3×3 around the peak.
- On CUDA the CCF maps are copied back after the production kernel. The emulated selection is checked against the kernel's own subpixel output (≤1e-3 px), with 0 mismatches in all logged frame-iterations.
- `MC_DIAG_CPU_TIES=1` makes the CUDA reduction prefer the lower ordinal on equal values, which reproduces CPU's first-maximum rule. Nothing else changes. It applies to global, batched and per-patch alignment, because all three use this one kernel.

**Ties occur, and the CUDA lane rule does change selections on real maps** (first attempt plus retry; global alignment had no CPU/CUDA rule disagreement anywhere):

| family | CPU map: exact ties / frame-iters | CUDA map: exact ties | CUDA map: lane rule ≠ CPU rule |
|---|---|---|---|
| e10216 | 5 / 5546 | 17 / 7080 | **14** |
| e12963 | 17 / 3237 | 17 / 3627 | **7** |
| e10474f3 | 3 / 3770 | 5 / 4930 | **2** |
| tutorial | 0 / 1200 | 0 / 1200 | 0 |

Of the 64 tied patch frame-iterations in the production-rule logs (both backends, all four families), 60 are ties within the 3×3 around the peak, on a flat peak top. For an adjacent pair, the quadratic subpixel step gives the same position from either pixel in exact arithmetic, so the rule rarely matters there. The other 4 are ties between separate maxima, including both CPU-map ties in the next table.

**The decisive selections are not exact ties on the CUDA map.** The table shows the requested frames at the iteration where the backends first pick different integer peaks. The margin is the lead of the chosen peak over the other candidate, in float32 ulps at that CCF value (`r1-ccf-<family>.json: watch, first_selection_divergence_per_patch`).

| patch, frame, iteration | CPU map | CUDA map |
|---|---|---|
| 10216 (1,4), fr 46, it 1 | **exact tie** (0,−1) = (2,3); CPU rule picks (0,−1) | (2,3) leads (0,−1) by ≈5 ulps (no tie) |
| 10216 (1,4), fr 46, it 2–5 | stays at (0,0) | alternates (−2,−3), (2,3), (−1,−3), (2,3) against the (0,0) peak, leads 21–130 ulps |
| 12963 (2,5), fr 32, it 1 | (−8,8) leads (0,−1) by ≈3 ulps | (0,−1) leads (−8,8) by ≈35 ulps |
| 12963 (5,2), fr 12, it 2 | (0,0) | (6,7) leads by ≈4 ulps |
| 10474-F3 (1,2), fr 6, it 3 | **exact tie** (0,0) = (0,2); CPU rule picks (0,0) | (0,2) leads by ≈70 ulps |

In every case the CUDA map has a strict maximum, so CUDA's choice does not depend on its tie rule. The two maps differ by an almost uniform offset plus small local differences, enough to reorder two peaks that are a few ulps apart. In 10216 and 10474-F3 the tie is on the CPU map, where RELION's own first-maximum rule decides.

**CPU-tie variant vs CPU and vs unmodified CUDA** (`r1-<family>-L-cpu-vs-tiescuda.json`, `r1-<family>-L-prodcuda-vs-tiescuda.json`, `r1-identity-prodcuda-vs-tiescuda.jsonl`):

| family | rel. RMSE vs CPU: production → variant | kept CPU / CUDA (variant) | variant vs unmodified CUDA |
|---|---|---|---|
| e10216 | 0.4344 → 0.4300 | 21 / 20, flip (1,4) unchanged | products differ: rel. RMSE 0.0139, max trajectory change 1.25 px, kept set unchanged |
| e10474f3 | 0.5999 → 0.5999 | 20 / 21, flip (1,2) unchanged | identical |
| e12963 | 0.4990 → 0.4988 | 22 / 23, flip (4,1) unchanged; (2,5) 98.4 px and (5,2) 35.3 px unchanged | products differ: rel. RMSE 0.0034, max trajectory change 0.16 px |
| tutorial | 0.0084 → 0.0084 | 25 / 25 | identical |

**Verdict: not involved.** Ties occur, and the tie rule changes some CUDA selections and outputs (10216, 12963). Matching CPU tie order does not change the kept-patch sets, the flips, the different-trajectory patches, or CPU agreement (largest change 0.004 relative RMSE). The S1 divergence comes from arithmetic sensitivity of unequal, near-tied peaks. #70 remains an observable semantic difference and should be judged under #70/#66 on its own evidence. This experiment does not recommend merging the variant.

## Root-cause locations (`1db86902`)

Inherited from RELION 5.1 (`ad0b230`, identical in extraction `4499be23`):
- CPU per-frame peak: strict argmax, first maximum in signed-y-then-x order. `src/motioncorr_runner.cpp:4732–4745`.
- Convergence: strict `rmsd < 0.5` after each iteration with early exit, up to `max_iter`. `motioncorr_runner.cpp:4633, 4804–4810`.
- Non-converged patches discarded; converged patches accepted with no plausibility check. `motioncorr_runner.cpp:3766`, observations collected at `:3768–3789`.
- Unweighted 18-term least squares (`motioncorr_runner.cpp:3815–3853`; SVD with singular-value truncation at `src/matrix2d.h:1291–1325`, no observation rejection). Whole-model checks: corner gradient (`:3866–3894`, 3 px) and fit RMSD ≥ 10 px (`:2114`, `:3926–3938`).

Standalone CUDA code (not RELION):
- Peak selection with the lane-order tie rule (#70): `src/acc/cuda/cuda_alignpatch.cu:183–235`. Tested above and not the cause of this divergence.
- The same 0.5 px threshold: `cuda_alignpatch.cu:60, 685, 1003`.
- Retry of completed non-converged patches: `motioncorr_runner.cpp:3610–3763`. No effect observed at logged precision.

## Recommendation (options; maintainer decides)

Proposed D7 wording, R-S1's text updated with the round-1 result:

> In the tested movies (EMPIAR-10216, 10474 Falcon 3 and 12963, 5×5 patches), CPU and CUDA local-alignment products differ substantially (relative RMSE 0.43–0.60). This was already present before RC0 (`116eb04a`). The difference is amplified by patch acceptance and the inherited unweighted polynomial fit. It also occurs among trajectories accepted on both backends, and matching convergence status does not guarantee agreement. In the inspected cases the initiating events are frames where two cross-correlation peaks are within a few float ulps, and the two backends order them differently. Making CUDA use the CPU tie rule (#70) did not change this. No scientific equivalence or preference for either backend is established.

Options:
1. Ship RC0 with that bounded limitation and unchanged gates and defaults. Optionally point users at the log signals: patches with final RMSD ≥ 0.5 px, and a polynomial fit RMSD well above the 1–2 px seen in the controls.
2. Keep CPU/CUDA local-alignment agreement as a Tier B diagnostic and do not use matching patch sets as a qualification criterion.
3. After RC0, consider robust-fit or patch-plausibility work. That is a parity divergence from RELION and needs separate numerical-policy review plus known-motion (#59/#63) and downstream (#61) evidence. It does not settle #70, which is a separate semantic decision.

Possible next steps: explain 12963's residual 0.056 after equalising patch sets, and test beyond 20 iterations and on more movies per family.

## UNRUN and limits

- One movie per family. Other movies, 10474-F4, 10441 and 10028/10164 L were not examined beyond W-QUAL's table.
- Builds older than `116eb04a` were not run.
- Whether the CPU/CUDA CCF map differences are pure float rounding was not established. The CCF log records peak statistics, not whole maps.
- Retry neutrality holds at logged 2-decimal RMSD precision only.
- Identity scope: core header, payload and STAR. Labels and extended header are excluded from the verdict; logs and inventories are not compared. Round-0 images were deleted before review; round-1 identity records carry payload and STAR digests.
- The round-0 campaign-1 CUDA runs lack a direct GPU witness; all round-1 CUDA runs have one.
- No Tier C/D evaluation, no timing, no SCARF or second venue.

## Corrections in round 1 (R-S1)

- "Not caused by a CUDA defect" is withdrawn. The CUDA selector is standalone code with different tie semantics. #70 was then tested (§6) and found not involved, which is narrower than excluding CUDA defects.
- "Matching patch sets ⇒ agreement" is withdrawn (12963: 0.384 at 22/22 and 0.329 at 25/25).
- The malformed dump-neutrality record is renamed, its cause stated, and it is superseded by a rerun with full records.
- Narrowed wording:
  - deviations quoted as 12–24 px for flipped patches and up to 100 px for the 12963 common patch;
  - "identical" scoped to core header, payload and STAR;
  - the retry finding qualified to logged precision;
  - "fixes 10474-F3" changed to "reduces it to 0.079";
  - "inherited" limited to the CPU and shared fit code;
  - 10641 does not imply an image-gate pass;
  - the 20-iteration cycle does not prove that no iteration count resolves it.

## Reproduce

Scripts as run are in `tools/`:
- `diag_run.py`: runner with locks, taskset, witness and `--env`.
- `campaign{1,2,3,4}.sh`, `build.sh`, `build_r1.sh`.
- `diag_analyze.py`: log, STAR, coefficient, refit and tile analysis; imports `tools/compare_motioncorr.py`'s `parse_mrc`.
- `diag_dump.py`, `diag_identity.py`, `diag_ccf_analyze.py`.
- The scratch-only diffs `diag_s1_patch_dump_drop.diff` and `diag_s1_r1_ccf_ties.diff`.

Scratch root: `/mnt/clathrin/alex-motioncorr-rc0/W-DIAG-S1/`. Bulk MRC/PDF/EPS were deleted after analysis. Per run, `raw/runs/<label>/` holds `run.json` (argv, binary sha256, env, rc, wall, RSS, witness), `movie.log`, `movie.star`, `stdout.log`, `time-v.log`, the ingest witness, and `ccf.txt.gz` where logged.
