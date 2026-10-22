# #259: CUDA local warp border branch

Base `3691374061f7` (origin/main). Negative-control tree `8fb56bbe` (base plus the new test only). Fixed tree `b9440a09` (adds the fix and two compiled mutants). 4GPUs, A100 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` under `/tmp/motioncorr-gpu3-correctness.lock`, CPUs 112–119 (builds on 104–111), Release `-O3 -DNDEBUG`, sm_80, CUDA 12.8. Trees were cloned from a bundle, so they carry `.git` metadata; all configure and build exit codes are 0. The host was loaded by other agents (occupancy files in `native/`); nothing here is a timing result.

## Fix

`cuda_realspace_dw.cu`: `x0`/`y0` (the floor, and through it the bounds/fallback decision) are computed from `(double)ix - (double)x_fitted`, as on the CPU. The interpolation weights keep their float `x_target`/`y_target`, so interior pixels are unchanged except where a floor now falls on the other side of an integer (value-continuous). The border policy is untouched. The float polynomial coefficients and float `x_fitted` are not changed (see limits).

## Incidence (host/device replay, not an instrumented kernel)

`replay_branch.cu` copies the float expressions of the kernel (same nvcc, default FMA contraction) and compares three arms per pixel and frame over the real fitted coefficients of the movie's STAR local model, z = frame index: `old` (float target, `floorf`), `fixed` (float `x_fitted`, double floor), `cpu` (double coefficients and evaluation, no contraction). It scans every pixel of every frame. "flip" = one arm interpolates and the other takes the nearest-pixel fallback; "fallback" = both fall back, to different pixels; "cell" = both interpolate and the floor differs by one (value-continuous). Output in `native/replay-*.txt`.

| movie (frames) | pixel-frames | near a bound (<1e-3 px) | old vs CPU: flip / fallback / cell | fixed vs CPU: flip / fallback / cell |
|---|---:|---:|---|---|
| tutorial-00, 3710×3838 (24) | 3.42e8 | 16125 | 18 / 89 / 52329 | 0 / 0 / 57 |
| e10216-00, 4096² (59) | 9.90e8 | 17697 | 39 / 248 / 161039 | 0 / 1 / 392 |
| e12963-05, 4096² EER (39) | 6.54e8 | 16832 | 18 / 150 / 103696 | 0 / 3 / 482 |

Discrete differences (flip + fallback) on the old kernel: 107, 287 and 168 pixel-frames, about 3e-7 of all pixel-frames. They are not only on the last row/column: most are interior output pixels whose source coordinate lands within a float step of a bound, i.e. pixels within the local shift of an edge. The fix removes all flips; the few residual fallback and cell differences come from the float coefficients and float `x_fitted`, which this change does not address. (e10216-05 has no local model, so e10216-00 was used.)

## Test

`tests/cuda_realspace_border_branch.cpp` launches the production kernel through `cudaRealSpaceInterpolation` with a `ThirdOrderPolynomialModel` (frame 0 zero, frame 1 the test image) and compares every output pixel with a double CPU-logic oracle built from the same float coefficients. Cases: last column (I=y, x shift 1e-5, y shift 0.5; the issue's example), last row (x/y exchanged), interior output with edge source in x and in y (shift −3+1e-5), corner (4096²), and two controls (constant image; ordinary 0.3/0.5 shifts). Controls must match even under `--expect-mismatch`.

- Negative control (`8fb56bbe`, old kernel): `native/ctest-before-border.log`, exit 8. 63 pixels differ in each of the four boundary cases (worst 0.5; at the last column pixel y=1 the kernel gives 0, CPU 0.5), 4095 in the corner case, 0 in both controls.
- Fixed tree `b9440a09`: passes, all 7 cases match.
- Mutants `x_float` and `y_float` (`CudaRealspaceBorderBranchMutant_*`, compiled copies of the kernel with one axis' floor restored to `floorf(x_target)`): each fails only its own axis (`native/border-branch-mutants.txt`). `x_float`: last column 63, interior-output-edge-source x 63, corner 4095 pixels differ; last row and y-edge cases 0. `y_float`: last row 63, edge-source y 63, corner 3839 differ; x cases 0. Both controls match in both mutants. The unmutated binary passes all 7 in the same run, and `--expect-mismatch` returns 0 for each mutant. The corner case also shows the same rounding picking the wrong fallback row at x=0 (257 vs 256).

## CTest on `b9440a09` (Release, 4GPUs)

| configuration | result | log |
|---|---|---|
| CPU (`-DCUDA=OFF`) | 74/74 passed, exit 0 | `native/ctest-after-cpu.log` |
| CUDA | 111/111 passed, exit 0 | `native/ctest-after-cuda.log` |
| CUDA + nvCOMP 5.3 | 114/114 passed, exit 0 | `native/ctest-after-nvcomp.log` |

## Product effect (CUDA before vs after, same argv, one movie per process)

`--use_own --dose_weighting --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --save_noDW --gpu 0 --ingest auto`, built without nvCOMP. Per-movie STARs (shifts, models) are identical before and after. An A/A rerun of the old binary changes 0 pixels in all four products, so the comparison is deterministic. `native/product-compare.txt`.

| product | changed pixels | pixels with \|diff\| > 1e-3·rms (max edge distance) | max \|diff\|/rms | whole-image relRMSE |
|---|---:|---|---:|---:|
| tutorial-00 DW | 234 (1.6e-5) | 76 (6 px) | 0.85 | 5.3e-5 |
| tutorial-00 noDW | 394 | 79 (6 px) | 0.79 | 1.0e-4 |
| e10216-00 DW | 360 (2.2e-5) | 238 (17 px) | 0.68 | 3.6e-5 |
| e10216-00 noDW | 467 | 265 (17 px) | 0.54 | 6.3e-5 |

All changes of consequence are within 6 and 17 px of an image edge, about the local shift. Elsewhere the changes are rounding-level (an interior-only subset of the tutorial DW product: 149 pixels, \|diff\|/rms ≤ 1.1e-6). One border pixel moves by up to 0.85 of the image rms (a single pixel-frame nearest-pixel jump).

## Limits

- Not run: Tier A/known-motion/QF rows and other §9.4 rows beyond full CTest on the three configurations plus the native product runs above. This is a CUDA-source fix, so the per-row re-entry set is for the maintainer to select.
- The effect on the S1 relative-RMSE metric is not separated here: the changed pixels are ~2e-5 of the image, and whole-image relRMSE before/after is ≤1e-4, but that is not a CPU-vs-CUDA S1 measurement.
- The replay differs from the kernel only by compile context; it was not an instrumented production kernel. Float coefficient and `x_fitted` rounding remain.
- Output intentionally differs from the old CUDA product only at pixel-frames where it took the wrong fallback (CPU-parity direction); it needs maintainer sign-off per §9.2.
