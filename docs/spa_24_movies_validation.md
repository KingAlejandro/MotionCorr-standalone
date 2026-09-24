# RELION SPA tutorial: fixed-code 24-movie CPU validation

Run date: 2026-09-24T09:59:30.216212+00:00
Host: `4-gpu-vm`
Standalone source: `13ce0d2365ce6db5696d1e701f3043a803ac3d8e`
RELION 5.1 source: `ad0b230ca22095700f6392479326836efb1c911d`

## Results

- Standalone `j=1` versus RELION `j=1`, **exact gate: 1/24 pass**; **relaxed Gate 2: 1/24 pass**.
- Standalone `j=4` versus standalone `j=1`, **exact gate: 24/24 pass**; **relaxed Gate 2: 24/24 pass**.
- Standalone `j=4` versus saved RELION `j=4`, relaxed Gate 2: 0/24 pass (contextual comparison).
- Standalone `j=1` versus the fixed-seed CPU reference used for PR #25: **24/24 exact pass**.
- Six sequential four-movie batches: `j=1` 1782.04 s; `j=4` 723.30 s; ratio **2.46x**. These totals include six process startups per setting and do not measure one uninterrupted 24-movie job. The `j=1` batches ran first, so cache order may affect this ratio; the alternating-order repeats below provide a separate timing check.
- Joint STAR differences, standalone `j=1` versus RELION `j=1`: 68.
- Joint STAR differences, standalone `j=4` versus standalone `j=1`: 0.

The pre-fix four-thread image differences and the earlier 3.46x timing claim are superseded by this rerun. The fix in PR #24 serializes defect replacement and resets the random seed per movie. Numerical gates remain unchanged.
The historical PR #23 run recorded 24/24 exact single-thread matches before PR #24. That result describes the older binary; the fixed-code result above is the current result.

## Reproduction and provenance

Each setting ran six four-movie jobs **sequentially** on 4-gpu-vm with `--seed 1`, gain correction, dose weighting, 5 × 5 patches, and B factor 150. The prior RELION 5.1 outputs were reused after verifying the input SHA256 values and complete upstream artifacts. See [the manifest](spa_24_movies_manifest.json) for actual input hashes, binary hashes, exact commands, per-movie metrics, and exit status. New process logs are in [benchmark_logs](benchmark_logs/).

The four-thread comparison with the saved RELION four-thread output is contextual: that upstream output predates the determinism fix and is not the CPU reproducibility gate.

## Isolated repeat timing

Representative movie: `20170629_00021_frameImage`. Runs alternated thread order, with no overlapping MotionCorr jobs.

| Threads | Wall seconds by repeat | Median wall seconds |
| ---: | --- | ---: |
| 1 | 66.99, 75.54, 68.99 | 68.99 |
| 4 | 30.35, 30.53, 30.82 | 30.53 |

Median single-movie speed ratio: **2.26x**. This is a representative-movie measurement; the six-batch total above is the dataset measurement.
Exact repeat-output comparisons: **5/5 pass**.

**Exact upstream parity remains unresolved.** `20170629_00022_frameImage` is a reproducible case for [Issue #20](https://github.com/KingAlejandro/MotionCorr-standalone/issues/20), which tracks defect-correction RNG changes. The per-movie seed reset is a candidate cause; the metrics below establish the difference without assigning a cause.

## Per-movie comparison

### Standalone `j=1` versus RELION 5.1 `j=1`

| Movie | Exact gate | Relaxed Gate 2 | vs PR #25 CPU | Shift RMS (px) | Max shift (px) | Image RMSE | Relative RMSE | Max pixel error | Exact STAR differences |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `20170629_00021_frameImage` | PASS | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00022_frameImage` | FAIL | FAIL | PASS | 0.003484 | 0.007240 | 0.00438067 | 0.00527576 | 3.1215 | 1248 |
| `20170629_00023_frameImage` | FAIL | FAIL | PASS | 0.006998 | 0.011170 | 0.00614749 | 0.00718521 | 3.24067 | 1242 |
| `20170629_00024_frameImage` | FAIL | FAIL | PASS | 0.003432 | 0.005710 | 0.00594273 | 0.00693159 | 2.56192 | 1249 |
| `20170629_00025_frameImage` | FAIL | FAIL | PASS | 0.003345 | 0.005610 | 0.00678123 | 0.00802777 | 2.59313 | 1237 |
| `20170629_00026_frameImage` | FAIL | FAIL | PASS | 0.003595 | 0.008017 | 0.00508224 | 0.00587133 | 2.73756 | 1245 |
| `20170629_00027_frameImage` | FAIL | FAIL | PASS | 0.004538 | 0.008284 | 0.00779691 | 0.00894413 | 4.20328 | 1262 |
| `20170629_00028_frameImage` | FAIL | FAIL | PASS | 0.002871 | 0.004398 | 0.00618458 | 0.00698755 | 4.11468 | 1245 |
| `20170629_00029_frameImage` | FAIL | FAIL | PASS | 0.003502 | 0.005138 | 0.00462369 | 0.00533728 | 5.98141 | 1249 |
| `20170629_00030_frameImage` | FAIL | FAIL | PASS | 0.003847 | 0.006565 | 0.00621156 | 0.00724404 | 3.07668 | 1243 |
| `20170629_00031_frameImage` | FAIL | FAIL | PASS | 0.002377 | 0.003998 | 0.00430021 | 0.0049618 | 3.32241 | 1230 |
| `20170629_00035_frameImage` | FAIL | FAIL | PASS | 0.007100 | 0.017398 | 0.0091379 | 0.0102094 | 7.05736 | 1254 |
| `20170629_00036_frameImage` | FAIL | FAIL | PASS | 0.003337 | 0.007376 | 0.00568264 | 0.00639513 | 2.4462 | 1243 |
| `20170629_00037_frameImage` | FAIL | FAIL | PASS | 0.005866 | 0.009420 | 0.0076993 | 0.00823544 | 1.97752 | 1242 |
| `20170629_00039_frameImage` | FAIL | FAIL | PASS | 0.008358 | 0.013263 | 0.0108976 | 0.0122447 | 3.28393 | 1256 |
| `20170629_00040_frameImage` | FAIL | FAIL | PASS | 0.004901 | 0.009852 | 0.00698071 | 0.00780587 | 3.45056 | 1245 |
| `20170629_00042_frameImage` | FAIL | FAIL | PASS | 0.002140 | 0.006206 | 0.00371561 | 0.00419033 | 2.70459 | 1233 |
| `20170629_00043_frameImage` | FAIL | FAIL | PASS | 0.002981 | 0.007327 | 0.00423474 | 0.00482467 | 2.671 | 1245 |
| `20170629_00044_frameImage` | FAIL | FAIL | PASS | 0.003044 | 0.004391 | 0.00509958 | 0.00556068 | 2.93593 | 1240 |
| `20170629_00045_frameImage` | FAIL | FAIL | PASS | 0.004247 | 0.005949 | 0.00729399 | 0.00813643 | 3.95001 | 1257 |
| `20170629_00046_frameImage` | FAIL | FAIL | PASS | 0.002794 | 0.005582 | 0.00618065 | 0.00686212 | 4.44843 | 1247 |
| `20170629_00047_frameImage` | FAIL | FAIL | PASS | 0.003236 | 0.005800 | 0.00579391 | 0.00644721 | 2.38617 | 1242 |
| `20170629_00048_frameImage` | FAIL | FAIL | PASS | 0.004071 | 0.005530 | 0.00626271 | 0.00695023 | 2.6896 | 1249 |
| `20170629_00049_frameImage` | FAIL | FAIL | PASS | 0.002977 | 0.007082 | 0.00429401 | 0.00474659 | 2.82306 | 1239 |

### Standalone `j=4` versus standalone `j=1`

| Movie | Exact gate | Relaxed Gate 2 | Shift RMS (px) | Max shift (px) | Image RMSE | Relative RMSE | Max pixel error | STAR differences |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `20170629_00021_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00022_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00023_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00024_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00025_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00026_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00027_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00028_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00029_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00030_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00031_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00035_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00036_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00037_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00039_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00040_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00042_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00043_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00044_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00045_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00046_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00047_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00048_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |
| `20170629_00049_frameImage` | PASS | PASS | 0.000000 | 0.000000 | 0 | 0 | 0 | 0 |

## Gate interpretation

Every table status comes from the comparator's overall status with complete trajectory, image, and STAR coverage. A trajectory pass alone is not a full Gate 2 pass. The exact STAR-difference column includes derived motion fields; the relaxed comparator intentionally excludes those fields. Per-movie failure reasons and exact comparator commands are recorded in the manifest.

The fixed-seed standalone `j=1` output is the CPU reference for CUDA comparisons. RELION 5.1 is the separate upstream reference for extraction parity. Matching the current CPU reference does not establish matching RELION.
