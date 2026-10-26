# H7a: does DCb+H2a hold at production scale? (100 #269 seeded motion-truth movies, native CPU)

Frozen spec: [H7-scale-PREDICTION.md](H7-scale-PREDICTION.md), copied verbatim, SHA256 `d0b2f2c242edc6cd21fd2577c9ff20fc8bbc19469c9c70c9534d76e5572c87f8` verified and committed (1d09674e) before any H7 run. H7b (Maarten case 000000) was not part of this round: predictions 6 and 7 are **UNRUN**.

**Result.** Flags-off (F) reproduces the C1 K269 CPU census exactly (100/100 STAR files and summed-image payloads byte-identical; no identity defect). DCb+H2a (C) is not better than F on these movies: C has lower truth-field RMS in 52 of 100 movies and higher in 48
(two-sided exact sign test p = 0.76; on the STAR-serialised field 55/45, p = 0.37), so **prediction 1 fails**. Predictions 2, 3 and 4 hold (23 against 22 movies meeting all limits; no F-pass/C-fail movie; guard fires 0 of 8,000 global and 0 of 191,960 patch peaks).
The falsification branch for prediction 1 applies as written. The whole difference is in one condition: in the 10 `pedestal32` movies F does not converge globally and drops all 25 patches, C converges and keeps them; in the other 90 movies C and F differ at the noise level (median relative RMS change 0.0002, largest 0.021 Å).

## Part 1: review findings (code and tests only; source `1d09674e`)

| Finding | Change | Result |
|---|---|---|
| F1 CoupledPeak gap | `CoupledPeak` now asserts closeness to the fixture's true shifts through `alignPatch` (20 forced global iterations via the existing `--experimental_align_tolerance`, rms(recovered + truth) < 0.1 px) and adds a tilted fixture (power along kx = ky, rho = +0.894 computed from the spectrum and the CCF weight) where the separable fit is unstable and the coupled fit recovers the truth | isotropic: off, global, all all 0.0000 px; tilted: separable 0.6810 px, coupled 0.0000 px. The reviewer's 5 mutants (`mut.py`, applied verbatim) all FAIL now (gather-transpose, y-flip, x-flip, apply-sign, apply-y-only-sign), as do the 8 earlier operator mutants: 13 of 13 killed on cpu64 (`part1/chain-p1x-mutants.out`); the 5 were also checked locally. The thresholds (0.1 px, separable at least 0.3 px and 3 times the coupled error) were fixed from the instability argument before the fixture was first run; the observed values are above |
| F3 DC hook on CUDA | a build with the #262 hook refuses `--gpu` with a clear error unless `MC_EXPERIMENT_CCF_DC_ARM` is exactly `none` (unset also refused), in `initialise()` before the CUDA checks; new CTest `CcfDcHookGpuRefusal` (registered for hook builds only) | arms global, local, both, unset, bogus and empty refused; `none` with `--gpu` and any arm without `--gpu` not refused. Two mutants (refusal removed; unset allowed) both killed. Default builds are unchanged (the check is compiled out) |
| F6 staging | `scripts/stage_tree.sh` (git-archive staging, records commit, git tree sha, archive-stream sha256 and a staged-file manifest sha256) and `scripts/record_binaries.sh` (recomputes the manifest after the build and records each binary's sha256, build type and flags). Record for this round: `stage_records/p1.json`, `part1/stage-p1-binaries.json` | manifest at staging equals the manifest after the build (`d549c6c6...`); binaries `build-p1off` `c550a754...` (default) and `build-p1on` `fca7d270...` (hook) |

Flags-off identity to e77a51a2 re-verified on these binaries: full CPU CTest default build 94 tests (93 passed, 1 skipped for pbzip2, 0 failed) and hook build with `MC_EXPERIMENT_CCF_DC_ARM=none` 96 tests (95 passed, 1 skipped, 0 failed); `validate_test_collection` and `test_ci_fail_closed` rc 0 on both; known-motion trees (193 files, 88 compared) and the synthetic movie (14 / 7) IDENTICAL to e77a51a2 for both builds; capture on identical to capture off; the DC arm global and half gain on still change products (comparator sees a change).

## Part 2: H7a

**Inputs.** The 100 movies of the C1 K269 CPU census (10 conditions x 10 seeds). They were generated on cpu64; only 18 originals remain there. The 4GPUs copies are 261 GB and the 4GPUs to cpu64 path through the laptop ran at 1.7 MB/s, so they were not copied.
Instead the 18 originals were used in place and the other 82 were regenerated with the same generator, numpy 2.5.4 + scipy 1.18.1 deps and expectation files under `/home/ubuntu/mc-km-truth-20261021`. **Every movie, retained or regenerated, is accepted only if its sha256 equals the movie.mrcs hash in its RECEIPT.json**
(identical to the hashes in the 4GPUs copies the C1 census read): 100 of 100 matched. Regenerated copies were deleted after use (scratch stayed under 8 GB; 34 MB retained).
**Binary.** `build-p1on` (hook build, `fca7d270...`), both arms, same binary; F has `MC_EXPERIMENT_CCF_DC_ARM=none`, C has `both` plus `--experimental_coupled_peak all`; runtime capture on; production stop (default `--max_iter`, no tolerance flag).
**Command.** The C1 census command line exactly (`--patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --skip_logfile --ingest float`) with `--j 8` instead of 2 (the CPU build is bit-deterministic across `--j`; the F comparison below confirms it).
**Evaluator.** `tools/check_realistic_motion.py`, unchanged (129 x 129 lattice, limits 0.20 / 0.40 / 0.80 Å; runtime field from the capture, STAR-serialised field separately).
**Lane.** cpu64 CPUs 32-55 in three 8-CPU slices under `flock -n` on both `/tmp/motioncorr-damping-cpu48-55.lock` and `/tmp/motioncorr-damping-cpu32-47.lock`; median run 10.6 s (F) and 10.8 s (C).

### Manipulation control

Summed over the 100 movies, arm C (DC arm `both`) zeroed 8,000 of 8,000 global and 191,960 of 191,960 patch CCF frames; arm F (`none`) zeroed 0 of 9,200 global and 0 of 222,560 patch frames (F has more eligible frames because its pedestal32 movies iterate longer and run patch alignments that C does not need to repeat). The coupled-peak counts show H2 fitted on 8,000 global and 191,960 patch peaks in C and on none in F.

### Identity of F with the C1 K269 CPU census (stop condition: not triggered)

F STAR bytes equal the C1 CPU census STAR for 100 of 100 movies, and the summed-image payload (bytes from 1024) equals for 100 of 100 (C1 binary `5692c6dc...`, `--j 2`; here `--j 8`). All 200 native runs exited 0.

### Movie size, CCF crop factor, binning (reported for every input)

| Movies | Size (x, y, frames) | Bytes | Binning | Global CCF (crop factor) | CCF pixel in movie px | Patch (5 x 5) and its CCF |
|---|---|---|---|---|---|---|
| 90 (all conditions except nonsquare) | 4096 x 4096 x 40 | 2,684,355,584 | `--bin_factor 1`, no early binning | 1024 x 1024 (0.25) | 4.0 | 818 x 818, CCF 216 x 216 (0.264, 3.79 px) |
| 10 (nonsquare) | 5760 x 4092 x 40 | 3,771,188,224 | same | 1536 x 1024 (0.267, 0.250) | 3.75, 3.996 | 1152 x 818, CCF 288 x 216 |

(Crop from the native formula: scale = sqrt(-ln 1e-8 / (2 B)) = 0.2478 at B = 150, `findGoodSize`, clipped to the frame; patch sizes from each movie's log.) These movies are in the cropped regime the review (F2) said the 128 x 96 fixtures never reach.

### Scorecard

| # | Prediction | Result | Verdict |
|---|---|---|---|
| 1 | C has lower truth-field RMS than F in more movies than not, two-sided exact sign test p < 0.05 | runtime RMS: C lower 52, higher 48, ties 0, p = 0.764; STAR RMS: 55 / 45, p = 0.368 | **falsified** |
| 2 | More movies meet all three limits under C than under F | F 22, C 23 (runtime and STAR agree); the one extra is pedestal32-s02 | confirmed (by one movie) |
| 3 | Every F-pass / C-fail movie listed; more than 2 falsifies "no harmful regression" | none (0 movies, runtime and STAR) | confirmed |
| 4 | Guard fire rates for global and patch peaks stay below 5% | global 0 / 8,000 (0.00%), patch 0 / 191,960 (0.00%); no movie above 0% | confirmed |
| 5 | Convergence or failure changes reported per movie | exit 0 for all 200 runs. Ten movies change, all `pedestal32` s00 to s09: F global alignment does not converge (5 iterations) and all 25 patches are dropped; C converges in 2 iterations and drops 0 of 25. Dropped patches over all movies: F 250 of 2,500, C 0. Sampling status unchanged | reported |

**Falsification branch.** Prediction 1 fails, so the first branch applies as written: the candidate does not generalise from uncropped fixtures on this evidence, no CUDA port, and the next step is diagnosing the cropped-peak regime. Prediction 3 is within its limit and prediction 4 is far below 5%, so the other two triggers are not met.

### What the numbers say, and what they do not

- **Outside pedestal32 (90 movies):** C and F are practically the same estimate. Median relative RMS change +0.0002, largest absolute change 0.021 Å, largest relative change 6.6%; C is lower in 42 and higher in 48 (post-hoc sign test p = 0.60; STAR 45 / 45, p = 1.0). The coupled peak is active (the C STAR differs from the F STAR in all 100 movies) and its guard never fires, so the 3x3 quadratic is valid at the 4 px crop; it just changes little here.
- **pedestal32 (10 movies):** F RMS 1.33 to 2.51 Å (global not converged, no local model), C 0.19 to 0.38 Å; C passes all limits in one of the ten. With the DC bin zeroed, the pedestal stops mattering: median C RMS is 0.26623 Å for pedestal32 and 0.26623 Å for pedestal0.
- **All other conditions:** pass counts are identical for F and C (dose1 1/1, dose05 0/0, dose2 7/7, dose4 10/10, outmodel 0/0, nonsquare 1/1, pedestal0 1/1, contrast025 1/1, contrast4 1/1), so most of these movies fail at least one of the three limits under both arms; the cause is not in the arms compared here.
- H7a has one combined arm (DC both plus H2 all). It cannot attribute the pedestal32 gain to the DC factor and the null elsewhere to the peak factor; that attribution needs separate arms and was not run.

Per-movie table: [results/h7a_per_movie.md](results/h7a_per_movie.md); every number: `results/h7a.json`; raw rows `results/census.json`; per-arm STAR, log, runtime capture, metrics, stdout and run record under `results/runs/<movie>/{F,C}/`.

## Limits

CPU only; one binary; one run per arm (the CPU build is bit-deterministic across `--j`, confirmed by F matching a `--j 2` reference in 100 of 100 movies). The evaluator's truth is the synthetic motion model; 78 of 100 movies fail at least one of the three limits in F, so the limits are hard to meet at this scale independent of the arms. H7b is UNRUN. CUDA parity is UNRUN and, per the falsification branch, not the next step.
