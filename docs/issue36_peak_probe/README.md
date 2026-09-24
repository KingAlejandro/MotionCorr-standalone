# Issue 36: first global peak probe on movie 00021

Date: 2026-09-24. Host: `4-gpu-vm` (Ubuntu 24.04, GCC 13.3, CUDA toolkit 12.8.61, driver 570.86.10, NVIDIA A100 80 GB PCIe GPU 0). Diagnostic source: `dd29b59` (`codex/issue36-diagnostics`); CPU and CUDA runs used the **same** CUDA-enabled binary, SHA256 `68307b3ea2c1dac0d4d85f4d16041d400135837e2b53ac2a596863c659d96908`.

Input TIFF SHA256: `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`. Gain SHA256: `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`. `movies.star` SHA256: `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041`; `--do_at_most 1` selected its first movie, `Movies/20170629_00021_frameImage.tiff`.

## Exact run form

Working directory: `/home/alex/MotionCorr-standalone/relion30_tutorial`. Each of the four runs used a fresh output directory and a fresh trace directory per selected frame. The trace directory was shared only between its CPU and CUDA pair.

```sh
MOTIONCORR_PEAK_TRACE_DIR=<fresh-trace-directory> \
MOTIONCORR_PEAK_TRACE_FRAME=<0-or-4> \
MOTIONCORR_PEAK_TRACE_ITER=1 \
/usr/bin/time -v /home/alex/MotionCorr-issue36-diagnostics-build/build-issue36-cuda/motioncorr \
  --i movies.star --o <fresh-output-directory> --use_own \
  [--gpu 0 for the CUDA run] --j 1 --do_at_most 1 --seed 1 \
  --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
  --bfactor 150 --gainref Movies/gain.mrc
```

The option in square brackets above describes the CPU/CUDA variant; omit the brackets themselves. All four processes exited 0. CUDA stdout confirmed device 0 and the movie log contained a completed CUDA global-alignment profile. Saved full logs and corrected MRCs remain in `/home/alex/MotionCorr-issue36-diagnostics-build/validation/`.

## What the traces show

The paired traces are [frame 0 CPU](frame0_cpu.json), [frame 0 CUDA](frame0_cuda.json), [frame 4 CPU](frame4_cpu.json), and [frame 4 CUDA](frame4_cuda.json). Frame indices are zero-based **post-grouping** `alignPatch` ordinals. Both backends chose the same integer CCF peak in each pair.

| Iteration 1 checkpoint | CPU | CUDA | CUDA minus CPU |
| --- | ---: | ---: | ---: |
| Frame 0 integer peak | `(-2, 2)` | `(-2, 2)` | same |
| Frame 0 peak center | 20.8308639526 | 20.8308658600 | +0.0000019073 |
| Frame 0 X curvature denominator | -0.0012321472 | -0.0012359619 | -0.0000038147 |
| Frame 0 unscaled X shift | -1.7105263158 | -1.7129629850 | -0.0024366692 |
| Frame 0 scaled X shift before origin adjustment | -6.5288607321 | -6.5381612778 | -0.0093005457 px |
| Frame 4 scaled X shift before origin adjustment | -3.1519421634 | -3.1518111229 | +0.0001310405 px |
| Frame 4 X shift after frame-0 recentering | 3.3769185687 | 3.3863501549 | +0.0094315862 px |

The frame-0 CUDA five-point stencil, recomputed **in double precision**, gives unscaled X shift `-1.7129629630`. The actual CUDA result is `-1.7129629850`, only `2.2e-8` away. Most of the frame-0 X difference therefore already exists in the CCF samples supplied to interpolation; changing only the arithmetic precision of the five-point interpolation would not remove it. The flat X curvature (~0.00123 around a peak of 20.83) amplifies changes of one or two float steps in the stencil. The Y calculation also shows some float-intermediate rounding, so this conclusion is strongest for X on these two probed frames.

The newly generated corrected-pixel payloads match the earlier fixed-CPU and CUDA rerun payloads respectively (CPU SHA256 `bf738254a4d9c218ddc723a3ec595c999c3ad27a01a56b97c2d903046a0f77b0`; CUDA SHA256 `0e04d076edfdb02115c3201cbe0516235604099ff606e9342cd69f25065391d5`). MRC whole-file hashes differ because headers contain run metadata. The CPU/CUDA corrected-image RMSE is `0.00379507781`, relative RMSE `0.00470786371` against the fixed CPU reference standard deviation `0.8061146293`, and maximum absolute pixel difference `1.1400647163`. This exactly reproduces movie 00021's recorded Gate 2 image failure, whose relative limit is `0.001`.

## Interpretation and next boundary

These four traces narrow the leading X-shift difference to **at or before the real-space CCF samples**, not the integer peak choice or double-versus-float quadratic division alone. They do not identify whether the first difference comes from reference summation, B-factor weights, weighted CCF formation, or FFTW-versus-cuFFT inverse results. Trace matched `Fref`, weighted `Fccs`, and `Iccs` for the selected frame/iteration next. The peak probe does not yet record those arrays, input hash internally, source-frame mapping, or local-model checkpoints. This is one movie and two selected frames, not a new 24-movie Gate 2 result. The `0.001` threshold was not changed.
