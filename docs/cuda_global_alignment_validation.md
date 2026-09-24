# CUDA global alignment validation

**Issue:** [#16](https://github.com/KingAlejandro/MotionCorr-standalone/issues/16)
**Rerun:** 2026-09-24, `4-gpu-vm`, NVIDIA A100 80 GB PCIe
**Gate 2 result:** **FAIL — 0/24 experimental movies pass**

The CUDA implementation completes the 24-movie RELION SPA tutorial dataset, but its corrected images do not meet the declared [relaxed numerical gate](reference_gates.md#gate-2-numerical-equivalence-gate---gate-relaxed). The previous 24/24 PASS claim omitted the relative image RMSE check. The older [`cuda_24_movies_comparison.json`](cuda_24_movies_comparison.json) is historical trajectory telemetry and must not be used as Gate 2 evidence. The corrected, per-movie results and provenance are in [`cuda_24_movies_gate2_rerun.json`](cuda_24_movies_gate2_rerun.json).

## Source and run

| Component | Revision |
| --- | --- |
| CUDA PR head before this update | `4c987a674d7c31296317e0b4d1c5ad967bb49e04` |
| Main with the CPU determinism fix | `13ce0d2365ce6db5696d1e701f3043a803ac3d8e` |
| Validation merge on the GPU VM | `4a00f0ba2c0f5ad45b3b9cd9c9321dc2300e875d` |
| Validated source tree | `b5ce2339f366f9d88d8918cceffc086c58dc43e0` |

The PR branch merge of main resolves the CMake overlap while producing the same source tree as the GPU VM validation merge. Both CPU and CUDA builds completed on the VM (CUDA toolkit 12.8, driver 570.86.10). The dataset comprised 24 TIFF movies, each with 24 frames of 3710 × 3838 pixels, and the tutorial gain reference. Both paths used `--use_own --seed 1 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc`. CPU references used `--j 1` in six four-movie batches; CUDA used `--gpu 0 --j 4` in one 24-movie batch. All seven processes exited 0.

CPU controls after the determinism fix: the first movie's `--j 1` and `--j 4` outputs were exact, a repeated `--j 4` run was exact, and split versus sequential CPU processing was exact for the first eight movies. The small synthetic CUDA fixture passed the relaxed gate. These controls do not override the experimental image failure.

## Experimental Gate 2 comparison

Each movie was compared with its fixed CPU `--j 1` reference using **both corrected MRC and per-movie STAR files**, plus the CUDA run's `/usr/bin/time -v` log. All 24 comparisons had complete coverage. The comparator exited 1 for each movie because relative image RMSE exceeded 0.001.

| Check | Limit | Result | Movies passing |
| --- | ---: | ---: | ---: |
| Trajectory coordinate RMS | ≤ 0.020 px | 0.002880–0.007699 px | 24/24 |
| Maximum frame shift error | ≤ 0.050 px | 0.005243–0.012371 px | 24/24 |
| Corrected image absolute RMSE | ≤ 0.020 | 0.002658–0.009082 | 24/24 |
| **Corrected image relative RMSE** | **≤ 0.001** | **0.002899–0.010082** | **0/24** |
| Maximum absolute pixel error | ≤ 5.0 | 1.140–3.323 | 24/24 |
| Static STAR differences | 0 | 0 | 24/24 |
| CUDA process exit | 0 | 0 | 24/24 |
| **Overall Gate 2** | **All checks pass** | **FAIL** | **0/24** |

The first movie's relative image RMSE was 0.004708. The older CPU reference from before the determinism fix differs from the new fixed reference, so the original 24-movie comparisons are stale. Static STAR checks cover schema and static fields; local motion coefficients are not an independent gate. Corrected-image error measures the full output path, not only the global CUDA kernel.

## Reproduction and interpretation

For each movie, run `tools/compare_motioncorr.py` with explicit `--ref` and `--test` MRC paths, `--ref-star` and `--test-star` STAR paths, `--test-log` pointing to the full CUDA `/usr/bin/time -v` log, `--gate relaxed`, and `--json-out`. The dataset wrapper `tools/compare_cuda_dataset.py` now propagates the comparator's full gate result and exits nonzero if any expected movie fails or is missing. It requires a single directory of CPU `--j 1` references; the archived rerun used six reference directories, so its 24 per-movie comparator reports were aggregated into the committed JSON instead.

The earlier per-kernel timings remain exploratory. The rerun's 24-movie CUDA wall time was about 10 min 30 s while CPU jobs ran concurrently, so it is not an isolated end-to-end speedup measurement. CPU local patch alignment still runs after GPU global alignment. Do not treat the successful batch exit or small synthetic pass as numerical acceptance.

**Decision:** Gate 2 remains closed. Investigate the corrected-image discrepancy and repeat the full reference comparison before claiming parity or an accepted speedup. No numerical threshold has been relaxed.
