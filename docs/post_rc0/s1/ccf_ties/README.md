# S1.3: CCF near-tie logging, CPU vs CUDA local alignment

Post-RC0 campaign item S1.3 (`docs/release/POST_FREEZE_TEST_PLAN.md` §0, issue [#238](https://github.com/KingAlejandro/MotionCorr-standalone/issues/238)); S1.3b (amplitude/backend decomposition of the patch-input difference) is folded into Result (b). Frozen source F = `6d68e2d6`. Diagnosis only: no product source, gate or default was changed, and no timing claim is made. This is Tier B evidence (CPU agreement), not a scientific-outcome claim.

## Result

**(a) Near-tie mechanism: confirmed for every S1-relevant patch (9/9). Established for these five cases.**

Each S1-relevant patch first separates where the two backends pick different integer CCF peaks in one frame. In each case the two candidates are:
- **≤16 ulps apart on both maps** in 7/9 patches;
- **an exact or ≤3-ulp tie on one map with a 36–68-ulp lead on the other** in 2/9 (12963 (2,5) and 10474-F3 (1,2)).

All of these leads, at most 68 ulps (≈8e-6 of the peak value), are smaller than the local CPU–CUDA map difference in the same frame (67 and 133 ulps there). A patch is S1-relevant if it reaches the fit on at least one backend and either its acceptance differs or its trajectory differs by more than 1 px.

Divergences that are not integer-peak near-ties also occur, but none starts an S1-relevant patch:
- 17 first-separation events where both backends keep the same integer peak but the quadratic subpixel step differs by >0.5 px, on flat peaks (13 in 12963, 3 in 10474-F3, 1 in 10216 5×5);
- one patch (10216 3×3 (2,3)) where the iteration-2 RMSD lands either side of the 0.5 px test (CPU 0.5105, CUDA 0.4997), so CPU runs one more iteration (0.38 px final difference).

**10216 3×3 (relative RMSE 0.196, 9/9 patches accepted on both backends)** is the same mechanism without an acceptance flip:
- **(2,1):** the decisive event is an adjacent-pixel near-tie at frame 1, the reference frame, at iteration 2. The peak pixels (0,1) and (0,2) are 3 ulps apart on the CPU map and 4 ulps on the CUDA map. The candidate shift jumps 1.79 px, and because every frame's increment is taken relative to frame 1, the jump moves the whole trajectory (1.13 px final).
- **(1,1):** has the same kind of frame-1 near-tie at iteration 1 (1 and 3 ulps, 1.60 px jump) but re-converges to 0.31 px.
- **Fit attribution:** refitting CUDA's STAR observations with (2,1) taken from CPU reduces the model-field difference from 1.81/0.515 px (max/rms) to 0.79/0.146 px. Taking (1,1), (2,1) and (2,3) from CPU reduces it to 0.12/0.032 px (`raw/analysis/e10216-p3-fitattr.json`).

**(b) Map differences vs floating-point rounding: the CCF computation and peak search are rounding-consistent, but the patch inputs carry a systematic CUDA-specific term from the global inverse FFT (S1.3b, below). Established for 10216 5×5 and 12963 5×5. The remaining patch-input difference is the global-trajectory difference, which starts from rounding.**

| stage | CPU vs CUDA | reading |
|---|---|---|
| CCF computation, each backend's float32 map vs a float64 recomputation from its own dumped inputs (all five cases) | CPU ≤9.3 ulps at the peak (≤4.0e-7 rel.); CUDA ≤9.4 ulps (≤4.4e-7 rel.) | FFT/reduction rounding, same size on both backends |
| global alignment, iteration 1 inputs (CCF window, all five cases) | ≤2.7e-7 relative | preprocessing rounding |
| global alignment maps (all five cases) | ≤7 ulps local at iteration 1 (≤9 later), offset ≤3 ulps; no integer-peak difference in any global frame; candidate shifts ≤0.045 px at iteration 1; final global trajectories ≤0.038 px apart | rounding acting on the quadratic subpixel step |
| full-frame spectra after equal global shifts (S1.3b, 10216 and 12963, frames 2/11/21) | ≤1.93e-6 relative over the whole spectrum, including CUDA's float shift kernel at large phases | rounding |
| **real frames after the global inverse FFT, same spectra** (S1.3b) | differ by 7.0e-4–1.0e-2 relative, entirely as a per-row constant h(y). CPU matches a float64 `irfft2` of its spectrum to 1.5e-7. CUDA (cuFFT C2R) adds h(y) = −Im(IFFT_y of the spectrum's kx = nx/2 column), to a residual of 2e-6 (rms 0.14) and 6e-8 (rms 0.014) at frame 11; frames 2 and 21 are covered by the patch prediction below | **systematic.** A sub-pixel shift makes the Nyquist column non-Hermitian (anti-Hermitian part 0.7–2.0 rel.). FFTW discards that part; cuFFT turns it into a row offset across the frame |
| patch inputs, iteration 1 (S1.3b decomposition) | measured CPU vs CUDA: 2.9e-3 (10216), 6.5e-3 (12963) relative. CPU with CUDA's global trajectory reproduces the amplitude residual (3.60e-4 vs 3.68e-4; 5.85e-4 vs 6.02e-4; frame-by-frame r = 0.9995 / 0.9998). At equal trajectories CUDA still differs by 1.6e-3 / 6.4e-3, all in the kx = 0 column; h(y) predicts it to ≤5.8e-7 in all 150 patch-frames checked (25 patches × frames 2/11/21 × 2 movies) | two parts: shift/crop geometry of the global-trajectory difference (translation plus the amplitude residual), and the cuFFT row term, which dominates in 12963 |
| patch maps (all five cases) | up to 2.1e-3 relative, mostly a uniform offset (≤25,200 ulps, which cannot change argmax or the quadratic step) plus a local part ≤259 ulps at iteration 1. Float64 maps built from the two backends' inputs differ by the same amount to three significant figures | entirely input-driven, not CCF arithmetic |
| phase-shift application on patch windows (own increments on own input) | CPU ≤1.1e-8; CUDA ≤5.7e-7, growing with phase (up to 72 rad) | float phase and `__sincosf`; negligible |

So the near-tied peaks are reordered by input differences with two sources:
- **Rounding-initiated:** global trajectories differ by ≤0.038 px, starting from ≤7-ulp map differences.
- **Systematic:** cuFFT's C2R row term, present whenever a frame's x-shift is fractional.

**Equal global trajectories do not remove the flips (S1.3b test 3).** CUDA was run with CPU's global trajectory injected and compared against CPU:
- **12963:** all 5 S1-relevant patches still diverge, at the same frames with margins within 3 ulps of before; relative RMSE 0.4999 (was 0.4990).
- **10216:** the decisive (1,4) frame-46 event recurs exactly (picks (0,−1) / (2,3), margins 0 / 5 ulps), but CUDA's (1,4) now converges (last RMSD 0.425 instead of 2.40), so relative RMSE falls to 0.0210 (was 0.4344).

Because the remaining input difference at equal trajectories is the row term to within 5.8e-7, these flips are attributed to the row term. That attribution is inferred: removing the term has not been tested.

The peaks are badly conditioned in float32. They sit on a large pedestal: in 10216, peak values are ~36,130 while the next separate maximum is only ~3,300 ulps lower. The top pixels of a peak are often within a few ulps, and in 10216 3×3 (2,1) the y-curvature at the CPU pick is 7 ulps. In 3/9 S1-relevant events (10216 5×5 (1,4), 10474-F3 (1,2), 10641 (5,2)), float64 maps of a backend's own inputs order the two candidates opposite to its float32 map (by ≤0.08 ulp): there the float32 CCF rounding itself decides a tie at the 0–1-ulp level. In the other 6/9, both backends' float64 maps keep their own float32 order, so the input difference decides.

### S1.3b method (10216 5×5, 12963 5×5)

Diagnostic commits `61c3a85e` and `c8fa55f5` on `diag/s1-ccf-ties` ([`diag_s1_3b_override_fulldump.diff`](diag_s1_3b_override_fulldump.diff)):
- `MC_DIAG_GLOBAL_SHIFTS_OUT` writes the global trajectory exactly.
- `MC_DIAG_GLOBAL_SHIFTS` injects a trajectory right after global alignment, as an extra Fourier shift by (injected − own). CUDA uses its production shift kernel, CPU its own shift function, and frames with zero difference are skipped.
- `MC_DIAG_FULL_DUMP` dumps full-frame spectra after the shifts and real frames after the inverse FFT.

Runs and checks:
- **Neutrality:** with its own trajectory injected, each backend is byte-identical to production (4/4). The instrumented own runs are byte-identical too (4/4), and the full-dump runs equal their counterparts (4/4). The per-frame records equal the S1.3 records byte for byte.
- **16 runs, all exit 0, on 4GPUs lane GPU2** under its lock; CUDA runs UUID-witnessed.
- **Tools:** `campaign_b.sh`/`post_b.sh`/`pairs.py` (pairs P0–P4), `campaign_c.sh`/`fullframe.py`/`hpredict.py`.
- **Outputs:** under [`raw/s13b/`](raw/s13b/), including `first_separation_table_b.md` and `counts_b.json` for test 3.

## Cases

Both backends of each movie ran on one venue: 4GPUs, lane GPU2. Relative RMSE is from the production arms (`compare_motioncorr.py --gate backend`, recorded only, not graded); every value reproduces #243 / #212 to the digits shown.

| case | movie | relative RMSE | patches kept CPU / CUDA | S1-relevant patches |
|---|---|---:|---|---|
| e10216-p3 | EMPIAR-10216 `FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions`, 3×3 | 0.196182 | 9 / 9 | (2,1) |
| e10216-p5 | same movie, 5×5 | 0.434362 | 21 / 20 | (1,4) |
| e12963-p5 | EMPIAR-12963 `FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER`, 5×5 | 0.499014 | 22 / 23 | (2,5), (3,2), (4,1), (5,2), (5,4) |
| e10474f3-p5 | EMPIAR-10474 Falcon 3 `2019-06-21_20-39-45_801_eer_data_4096x4096`, 5×5 | 0.599858 | 20 / 21 | (1,2) |
| e10641b-p5 | EMPIAR-10641 `HM70-1_10-A-004_0008_Oct28_23_06_04` (#243 movie e10641-01), 5×5 | 0.807827 | 8 / 9 | (5,2) |

These are all S1-positive cases #243 reported (5×5: 10216, Falcon 3 `…20-39-45`, 10641 movie 2, 12963; 3×3: 10216). The first 10641 movie keeps no patches on either backend and was not run.

### Decisive event per S1-relevant patch

This is the largest-jump event in the patch's first separating iteration. Positions are integer CCF-pixel (x, y). A margin is how far the backend's own pick leads the other backend's pick on that backend's map. "Local D" is the largest CPU–CUDA map difference in that frame after removing the frame's mean offset.

| case | patch | acceptance CPU/CUDA | iteration, frame | CPU pick / CUDA pick | margin CPU map / CUDA map (ulps) | local D (ulps) | candidate jump (px) | final trajectory diff (px) |
|---|---|---|---|---|---|---:|---:|---:|
| e10216-p3 | (2,1) | yes/yes | it 2, frame 1 | (0,1) / (0,2), adjacent | 3 / 4 | 14 | 1.79 | 1.13 |
| e10216-p5 | (1,4) | yes/no | it 1, frame 46 | (0,−1) / (2,3) | 0 / 5 | 17 | 14.06 | 13.59 |
| e12963-p5 | (2,5) | yes/yes | it 1, frame 32 | (−8,8) / (0,−1) | 3 / 36 | 68 | 45.61 | 98.40 |
| e12963-p5 | (3,2) | yes/yes | it 1, frame 37 | (0,1) / (0,2), adjacent | 6 / 1 | 37 | 1.50 | 1.10 |
| e12963-p5 | (4,1) | no/yes | it 1, frame 31 | (1,1) / (0,2), adjacent | 1 / 2 | 38 | 3.78 | 1.67 |
| e12963-p5 | (5,2) | yes/yes | it 1, frame 8 | (0,0) / (0,−1), adjacent | 1 / 12 | 47 | 0.91 | 35.33 |
| e12963-p5 | (5,4) | yes/yes | it 1, frame 13 | (0,0) / (−1,1), adjacent | 0 / 10 | 36 | 1.43 | 1.27 |
| e10474f3-p5 | (1,2) | no/yes | it 3, frame 6 | (0,0) / (0,2) | 0 / 68 | 133 | 5.91 | 0.48 |
| e10641b-p5 | (5,2) | no/yes | it 1, frame 41 | (0,0) / (−1,1), adjacent | 0 / 1 | 7 | 4.33 | 0.50 |

Every patch with a first-separation event, including those that are not S1-relevant, is listed in [`raw/analysis/first_separation_table.md`](raw/analysis/first_separation_table.md). Counts are in [`raw/analysis/counts.json`](raw/analysis/counts.json). Over the five cases there are 58 first-separation events in 39 patches:
- 36 integer-peak events with both margins ≤16 ulps;
- 5 with a larger one-sided margin, 24–68 ulps;
- 17 same-peak subpixel events.

In 37/41 integer-peak events the two picks are adjacent pixels, so both sit on one flat-topped peak. Single-patch counterfactuals for 5×5 flips are #212's (dropping the flipped patch restores G-level agreement) and were not repeated.

### #70 observation

In 8 first-separation events the CUDA map holds exactly equal values at both picks, so CUDA's lane tie rule (#70) decided. In all 8, CPU's first-maximum rule would have chosen CPU's pick. None is in an S1-relevant patch. Two are in patches that reach the fit on neither backend (10474-F3 (1,4), 10641 (5,3)); the other six are in patches kept on both backends with final differences ≤0.54 px. This is consistent with #212's result that the tie rule changes some outputs slightly without explaining S1. It is recorded for #70 and changes nothing here.

## Method

The diagnostic patch is on branch `diag/s1-ccf-ties`, commit `9283ff7a`, on top of F. It is committed here as [`diag_s1_3_ccf_records.diff`](diag_s1_3_ccf_records.diff) and must not be merged. It is env-gated and read-only.
- **`MC_DIAG_CCF=<file>`** writes one record for every frame of every iteration of every patch and of global alignment, on both backends (CPU `alignPatch`; CUDA batched, per-patch and full-spectrum retry paths). Each record has:
  - the selected integer peak and its value;
  - the window maximum, plus the CPU-rule and CUDA-lane-rule positions and the exact-tie count;
  - the best separate local maximum (8-neighbour maximum outside the 3×3 around the pick) and its position;
  - the five subpixel inputs (peak and its ±x, ±y neighbours);
  - the backend's own candidate shift before re-referencing to frame 1.

  On CUDA, the maps and candidate shifts are copied back after the production kernel, and a host recomputation of the kernel's selection and subpixel step is checked against them: 0 mismatches in 32,195 CUDA frame-iterations.
- **`MC_DIAG_MAPS=<dir>`, `MC_DIAG_MAP_PATCHES=…`** dump raw float32 CCF maps, the CCF-window input spectra entering each iteration, and the weights. All patches and global were dumped on both backends (30 GB, scratch only).

Analysis (`tools/analyze.py`, `summarize.py`, `counts.py`, `phasefit.py`, `fitattr.py`):
- **Trajectories** are rebuilt from the records with each backend's own arithmetic. alignPatch pins frame 1's increment to +0.0, so frames align directly.
- **An event** is a frame whose two candidate shifts differ by >0.5 px. The first separating iteration is the first iteration containing an event; patches without an event but with different iteration counts are listed separately.
- **Margins** are taken from the dumped maps at the two picks, in float32 ulps at the larger value. "Near-tie" means ≤16 ulps on both maps; the 24–68-ulp cases are reported separately rather than absorbed into that label.
- **The rounding decomposition** recomputes every dumped patch and global iteration in float64 (reference sum, CCF spectrum, unnormalised inverse FFT) from each backend's own inputs and weights.
- **The ramp, phase-fit and shift tests** are as described in the (b) table. The CUDA rows use `cuda-batched`, the path every patch took on the first attempt. All 27 CUDA retries (non-converged patches) reproduce their first attempt exactly, in every frame's pick and candidate shift, and none converged. This closes #212's retry-neutrality limit (logged precision only) for these cases.

## Neutrality

Instrumentation does not change products. In 20/20 pairs (5 cases × 2 backends × {diagnostic build with env unset, diagnostic build with all records and all map dumps on}) against the production F build of the same backend, the MRC core header (bytes 0–223), pixel payload and per-movie STAR are byte-identical (`tools/identity.py`, `raw/analysis/*-identity-*.jsonl`). The extended header is equal in all 20. MRC labels carry a timestamp and differ; logs and plots are not compared.

## Provenance

| item | value |
|---|---|
| source | production F `6d68e2d6`; diagnostic `9283ff7a` (= F + the diff). Copied with `git archive` (CMakeLists, src, tests, tools, scripts, notices); tarball hashes in `raw/build-info.txt` |
| builds | 4 × `-DCMAKE_BUILD_TYPE=Release`, all exit 0, `-O3 -DNDEBUG`; CUDA `-O3`, sm_80; nvCOMP 5.3.0.16. sha256: prod CPU `db15536e…ec1b`, diag CPU `767fd76f…12c1`, prod CUDA+nvCOMP `1824a7fb…cbf5e`, diag CUDA+nvCOMP `2e9b0178…ecb0` (full hashes and flags in `raw/build-info.txt`) |
| host | 4GPUs, A100 80GB PCIe, driver 570.86.10, g++ 13.3.0, CUDA 12.8.61, CMake 3.28.3 |
| lane | GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` by UUID, `taskset -c 112-119`, `/tmp/motioncorr-gpu2-correctness.lock` held per run for both backends, bench lock checked. GPU1 was held by another campaign; GPU2's lock and CPUs were idle. Every CUDA run witnessed GPU2's UUID only |
| inputs | `raw/inputs-sha256.txt`; the three #212 movies match `docs/rc0/diag_s1/raw/inputs-sha256.txt`, and the 10641 movie, gain and STAR match #243's `e10641-01` run record |
| options | #212's L recipe: `--use_own --dose_weighting --bfactor 150 --seed 1 <family options> --j 8 --patch_x N --patch_y N`, plus `--gpu 0 --ingest auto` on CUDA (`tools/run.py`); exact argv and env per run in `raw/runs/<label>/run.json` |
| runs | 30/30 exit 0 (5 cases × 2 backends × {prod, diag off, diag on}) |

`raw/runs/<label>/` holds `run.json`, the per-movie STAR and log, the ingest witness and, for "on" runs, `ccf.txt.gz` (the per-frame records). `raw/analysis/` holds per-case `traj`, `maps`, `phasefit`, `fitattr`, identity and backend-comparator outputs, plus `summary.json`, `counts.json` and `first_separation_table.md`. Bulk MRCs and map dumps remain in `/mnt/clathrin/alex-motioncorr-s1ccf/` on 4GPUs.

## Reproduce

On 4GPUs, with `tools/` copied to `$S=/mnt/clathrin/alex-motioncorr-s1ccf/tools` and the two source trees unpacked as `src-prod`/`src-diag`:

```sh
bash tools/build.sh                                  # 4 builds; prints rc and sha256
LANE_GPU=2 bash tools/campaign.sh                    # 30 runs, resumable
for c in e10216-p3 e10216-p5 e12963-p5 e10474f3-p5 e10641b-p5; do
  bash tools/post.sh $c                              # identity, backend comparator, traj, maps, fitattr
  ~/.mc-venv/bin/python3 tools/phasefit.py $c analysis/$c-phasefit.json
done
~/.mc-venv/bin/python3 tools/summarize.py analysis e10216-p3 e10216-p5 e12963-p5 e10474f3-p5 e10641b-p5 > analysis/summary.json
~/.mc-venv/bin/python3 tools/counts.py analysis/summary.json > analysis/counts.json 2> analysis/first_separation_table.md
```

## Open

- **Does removing the cuFFT row term remove the flips?** It accounts for the equal-trajectory input difference to ≤5.8e-7. A diagnostic CUDA run that matches FFTW (dropping the Nyquist column's anti-Hermitian part before C2R) would establish it as the cause of the 12963 flips. Not run.
- **Does the row term reach products?** CUDA real-space frames carry it after the global inverse FFT. Whether the published micrographs do, and how much of the G-config CPU–CUDA difference (~0.017) it explains, was not measured. Any fix is a product change and a maintainer decision.
- **The row term in the other three cases:** 10216 3×3, Falcon 3 and 10641 were not run with S1.3b. The term exists whenever a frame's x-shift is fractional, but its size there was not measured.
- **Breadth:** one movie per family, the five S1-positive cases known on 2026-10-19. The 36 extra staged movies of #243 were not examined. No SCARF or second-venue run.
- **Consequences:** S1 still matters only as far as S1.4 (downstream CTF/FSC/B-factor) shows. Nothing here says which backend's output is better.

S1.3b closes three of S1.3's open items:
- the amplitude part is the shift/crop geometry;
- CUDA's full-frame shift accuracy is ≤1.93e-6 (full spectra after equal shifts);
- preprocessing plus shifts agree full-band to ≤1.93e-6.
