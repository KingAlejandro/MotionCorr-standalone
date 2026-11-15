# H7: does DCb+H2a hold at production scale? (frozen before any H7 run)

Frozen by the orchestrator (Opus 5.5) on 2026-10-26, after #286 head e5346a1e (H6) and the independent code review
(`20261026/PR286-code-review/REVIEW.md`), before any H7 run.

## Why

DCb+H2a (DC arm 'both' plus `--experimental_coupled_peak all`) passes K267 zero, integer, fractional, affine and
pedestal natively on CPU, and noisy improves over the baseline. Because its global path equals DCg+H2g, it also
passes 15/16 native N-controls; the harmful iso case fails in every arm, baseline included.

All of that evidence is on 128x96 fixtures, where the CCF is never cropped. Review finding 2: production frames crop
the CCF (motioncorr_runner.cpp:4853), so peaks are about 4x narrower in CCF pixels. A 3x3 quadratic may then fit
poorly, and the 1 px guard means about 4 movie px. H7 tests whether the improvement survives that regime.

## Arms

Both arms use the same #286 binary and differ only in flags: flags-off (F) and DCb+H2a (C). Production stop only:
default max_iter and tolerance, no experimental tolerance. For every input, the worker must report the movie size,
the CCF crop factor and the binning actually used.

## H7a: the #269 seeded motion-truth census (100 movies, CPU, arm none)

The inputs are the same 100 movies as the C1 K269 CPU census. Score them with the existing reviewed #269 truth
evaluator, unchanged, using its existing limits, ROI and scoring.

1. Paired over the 100 movies, C has lower truth-field RMS than F in more movies than not: two-sided exact sign
   test p < 0.05.
2. The number of movies meeting all three limits (0.20/0.40/0.80 A) is higher for C than for F.
3. Every movie that passes under F and fails under C is listed individually as harm. More than 2 such movies
   falsifies "no harmful regression" at this scale.
4. Guard fire rates for global and patch peaks are reported. The prediction is that they stay below 5%;
   a higher rate means the 3x3 quadratic is not valid at this crop.
5. Convergence or failure changes (exit codes, dropped patches) are reported per movie.

## H7b: Maarten case 000000 (4096x4096x48, development-exposed only)

Run F and C on CPU with the same binary, scored with the existing validated scorer
(`20261025/Maarten-000000-truth-contract/`). Do not open the other 19 cases.

6. The particle-location error RMS under C is no worse than under F. Both stay above the model-family floor of
   1.72 A, which is reported and never subtracted.
7. The global trajectory scale ratio against the particle trajectory (F was about 0.93) is reported for both arms.
   No prediction is made for it.

## Falsification

- **Prediction 1 fails, or prediction 3 exceeds 2 movies:** the candidate does not generalise from uncropped
  fixtures. No CUDA port; the next step is diagnosing the cropped-peak regime.
- **Prediction 4 exceeds 5%:** the 3x3 quadratic is invalid at production crop, whatever the outcome of
  predictions 1-3.
