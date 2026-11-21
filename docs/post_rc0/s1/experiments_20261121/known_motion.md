# Accuracy against known motion

These tests use an exact motion field to score the dense region of interest. The original limits stay at 0.20 Å RMS, 0.40 Å p95 and 0.80 Å maximum. B2 and full-width CCF weighting were evaluated as CPU experiments. [Scores, rank and oracle results](data/known_motion.json)

| Input and estimator | RMS (Å) | p95 (Å) | Maximum (Å) | Result |
| --- | ---: | ---: | ---: | --- |
| SCARF contrast025-s09, released CPU STAR | 0.27985 | 0.54792 | 0.92970 | FAIL |
| SCARF contrast025-s09, B2 STAR | 0.12790 | 0.22781 | 0.46384 | PASS |
| SCARF contrast025-s09, B2 plus full-width STAR | 0.12143 | 0.22092 | 0.46847 | PASS |
| Retained five-frame noisy fixture, measured runtime observations | 0.68386 | 1.24575 | 2.82869 | FAIL |
| Noisy fixture, closest refined candidate on each final CCF | 0.68386 | 1.24575 | 2.82869 | FAIL |
| Noisy fixture, exact shifts at the same nine sites | 0.16442 | 0.21227 | 0.21227 | PASS |

The two seed-09 B2 variants used 25 patches. Adding full-width weighting improved RMS and p95 and slightly worsened maximum error. Fitting true residual shifts at the same sites with the measured global trajectory gave 0.09806 Å RMS. The SCARF B2 build used `0b0ab0d0` with a scratch observation dump. Its binary SHA-256 was `ad08e64e477a080b18efaa65f67f19ff52d4571e126f9ef42028d95242c98cff`.

## Noisy fixture

The replay held the measured global trajectory, the nine patch locations, the frame-0 anchor and the C++ B2 fitter fixed. The actual measured peak was already the closest refined candidate to truth on all 36 final non-anchor maps. On 32 of these maps, no refined candidate lay within half a grid cell diagonally. Replacing any single measured patch track with truth also failed the field limits. Using true shifts at all nine sites passed. The measured failure is therefore attributable to the observations in this controlled comparison, and picking another candidate from these particular final maps provides no recovery. The earlier correlation inputs and iteration states remain open.

The final-map capture ran on macOS arm64. Five focused CTests passed (LocalCcfCapture, LocalB2Fit, LocalFullWidthWeight, ExperimentalFlagsCli and LocalCcfCaptureCli). Capture-on and capture-off runtime JSON, per-movie STAR and image pixels agreed exactly. The initial full MRC byte check failed on creation-time digits. A check of the same outputs established equality outside that header label. No producer was repeated for the label check.

## High-pedestal fixture

On the frozen Linux counterpart of pedestal32-s01, B2 accepted zero patches and published the global-only result. With B2 plus full-width weighting, one site at (1227, 3684) contributed 40 observations and the solver exited 1. The spatial basis had rank 1 of 6, and the intercept-removed design had rank 3 of 18. Substituting the exact shifts at the same site produced the same refusal. This separates lack of spatial support from measurement error on that case.

These are selected synthetic development cases. General accuracy improvements, image-information retention and independent real-data accuracy remain open.
