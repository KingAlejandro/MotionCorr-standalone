# #264 native qualification: frozen matrix and expected outcomes

Frozen before any native execution. The candidate is the commit that adds this file;
its compiled sources (`src/`, `tests/`, `CMakeLists.txt`, `tools/`) equal `52affe31`.
Base is `3691374061f782bc84531fd1c79d017ddcb5a7c2`. A failed stage is retained and the
chain stops; a later attempt is a new scratch directory and a new record, never a repair.

## Lane

4-gpu-vm, GPU1 `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d` only (`CUDA_VISIBLE_DEVICES=<UUID>`),
CPUs 14–15 (`taskset`), builds `--parallel 2` under a nonblocking `/tmp/motioncorr-build.lock`,
runtime one numeric thread and `--j 1`. GPU stages hold `/tmp/motioncorr-gpu1-correctness.lock`
(nonblocking) through pre/post health; the chain holds `/tmp/motioncorr-guard264-cpu14-15.lock`
and stops if `/tmp/motioncorr-i61-cpu-14-15.lock` is held. Bench lock is only probed (#198).
Contention, a foreign process on GPU1 or a health failure stops the chain; nothing waits or retries.
Scratch `/mnt/clathrin/alex-motioncorr-guard264-20261022-<sha12>` (cap 80 GiB). Release builds,
CUDA arch 80, nvcc 12.8, nvCOMP 5.3.0.16, `MC_REQUIRE_ALL_DECODERS=ON` with the private pbzip2
pinned at sha256 `35410d19…f21e` (no waiver). Scripts: `tools/`, driven by `tools/chain.sh`.
No timing claim; wall times are recorded only as receipts.

## Matrix and expected outcomes

| Row | What runs | Expected (gate) |
| --- | --- | --- |
| N1 cpu/cuda/nvcomp | candidate full build, `validate_test_collection.py` (`--cuda` for GPU configs), `test_ci_fail_closed.py` (cpu), full CTest `-j1`, no exclusions | every build rc 0; collection rc 0; CTest rc 0 with `LocalMotionDistortionGuard`, `LocalMotionGuardModel`, `LocalMotionGuardCall` registered; post-health PASS |
| N2 cpu, gpu | 24 distinct tutorial movies, base vs candidate binary, RC0 QF L command (`--patch_x 5 --patch_y 5`, dose weighting, gain), GPU adds `--ingest auto --gpu 0` | each arm rc 0, 24 STARs with a local model, **zero** guard messages; `compare_output_trees --products-only` against the RC0 L manifest rc 0 (products equal apart from declared normalisation) |
| N3 cpu, cuda | TEST-ONLY overlay builds of base and candidate; 7 known models injected as patch observations of `km_local_nonsquare` (768×512, 12 frames), plus one run without the overlay | per run: rc 0, one overlay line (n_obs > 18, 768/512/12), guard line present iff predicted reject, printed delta within 2e-5 relative of the prediction, STAR local model present iff accept, published coefficients within 1e-5 of injected; GPU1 UUID witnessed for CUDA. Base vs candidate per backend: identical global-shift block; image data equal iff decisions agree |
| N4 | candidate overlay build with the uncentred-domain mutant, CPU | every mutant row matches the uncentred prediction **and** at least one decision differs from the candidate |

N3 predictions (`predictions.json`, `predict.py`: independent rational emulation of each guard
with its early exit; finite values cross-checked against an exhaustive float64 pair scan):

| Case | Legacy (base) | Finite pairs (candidate) | Uncentred (mutant) |
| --- | --- | --- | --- |
| A_x `a(x−x²)` | 1.653225 accept | 3.300000 reject | 1.648925 accept |
| B_x `a(x+2x²)` | 3.282981 reject | 2.700000 accept | 3.276145 reject |
| A_y `a(y−y²)` | 1.654839 accept | 3.300000 reject | 1.648387 accept |
| B_y `a(y+2y²)` | 3.288128 reject | 2.700000 accept | 3.277861 reject |
| E_xy `c·xy`, nonsquare | 3.240000 reject | 2.970000 accept | 3.235781 reject |
| F mild translation/affine | 0.021484 accept | 0.021484 accept | 0.021484 accept |
| G large linear | 5.454545 reject | 5.454545 reject | 5.454545 reject |

All fields are linear in z, so the legacy B rows stop at the first frame above 3 (the native
early exit is observed through the printed value). The exact 3 px boundary is not testable through
the SVD fit (recovery error ~1e-10); it stays covered by the host tests. E is 1% inside the threshold.

N2 prediction: from the retained RC0 L s0 STAR models (hashes in `rc0-L-s0-stars.sha256`,
coefficients as published at 6 decimals), the largest delta over 24 movies is 0.0073 px (legacy)
and 0.0065 px (finite). Neither guard can fire; any guard line or product difference is a
contradiction that stops the campaign.

## What this cannot establish

Overlay builds are not production or ordinary-movie qualification, and injected observations say
nothing about whether real CCF observations are correct. N2 shows only "unchanged where both guards
accept". N4 is CPU only; CUDA mutant and nvCOMP N2/N3 arms are not run. No timing, accuracy or
science claim. CTest tests that start several threads share CPUs 14–15 (no CPU outside the lane).
