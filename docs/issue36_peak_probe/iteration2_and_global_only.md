# Issue 36: second global iteration and global-only attribution

Date: 2026-09-24. This follows the [first-iteration matched trace](README.md). The host, movie TIFF/gain/STAR hashes, A100 GPU 0, CUDA-enabled binary SHA256 `c2419c8684de18301871441c95aabea3fafc226711503a85073f600c90942273`, and all processing options except those noted below are the same. The diagnostic source is on draft PR #38. Raw derived-movie arrays remain on the isolated `4-gpu-vm` checkout under `/home/alex/MotionCorr-issue36-diagnostics-build/validation/`; they are not committed.

## Iteration 2: feedback from first-iteration shifts

Fresh CPU and CUDA runs used `MOTIONCORR_PEAK_TRACE_ARRAYS=1`, `MOTIONCORR_PEAK_TRACE_ITER=2`, and post-grouping frame `0` or `4`, with the exact movie command in the first report. Both global alignments reached iteration 2 and converged there. All four new corrected-pixel payload hashes again matched the corresponding untraced CPU and CUDA baselines. The selected `Fref` at iteration 2 is a complete sum over all 24 Fourier frames, not a selected-frame sample.

| Iteration-2 checkpoint | Frame 0 CPU/CUDA | Frame 4 CPU/CUDA |
| --- | ---: | ---: |
| Selected input `Fframes` | bit-identical; frame 0 remains the recentering origin | RMSE `3.16108e-6` (float components) |
| Reference sum `Fref` | RMSE `3.85400e-6` | same complete reference |
| Weighted spectrum `Fccs` | RMSE `7.33235e-11` | RMSE `2.23131e-11` |
| Real CCF `Iccs` | RMSE `2.37536e-6` | RMSE `2.20468e-6` |
| CUDA spectrum replayed with FFTW, versus CPU `Iccs` | RMSE `6.19793e-7` | RMSE `3.30575e-7` |

The selected frame-0 input is still bit-identical, yet `Fref` has diverged because other frames received different shifts at iteration 1. For frame 4, the selected input has also diverged. Replaying the CUDA iteration-2 spectrum with FFTW reduces the real-CCF difference but no longer gives the CPU CCF or peak stencil exactly. Thus iteration 2 contains both **propagated input/reference differences** and an **inverse-FFT backend difference**. The frame-0 X peak location from the captured five-point stencil (evaluated in double) is `0.0235223` CCF pixels on CPU, `0.0247286` for the CUDA spectrum through FFTW, and `0.0258724` for native CUDA. These are controlled diagnostic decompositions, not independently additive error estimates for the final image.

## Same saved frame, controlled Fourier-shift replay

The CPU and CUDA iteration-1 frame-4 inputs were bit-identical. Their first-iteration origin-adjusted frame-4 shifts were `(3.3769185687, -2.9374296986)` and `(3.3863501549, -2.9383578300)` pixels respectively. `tools/replay_fourier_shift_cpu.cpp` applies the CPU runner's double-precision trigonometric-table and three-multiply complex formula to that **same** saved input, with either recorded shift. With the CPU shift, it reproduced the actual CPU iteration-2 frame-4 Fourier input bit for bit (SHA256 `344c78522ec7bc8b13c0ada981edb97cef7ad0366257074e5ad8bbb6f63b8006`).

| Comparison of complete frame-4 Fourier input after iteration-1 shift | Float-component RMSE |
| --- | ---: |
| CPU arithmetic with CPU shift vs CPU arithmetic with CUDA shift | `3.161158e-6` |
| CPU arithmetic with CUDA shift vs actual CUDA-shifted frame | `1.198402e-10` |
| Actual CPU-shifted vs actual CUDA-shifted frame | `3.161081e-6` |

For this frame and iteration, the **shift-value difference** accounts for almost all of the post-shift Fourier-frame difference. CPU versus CUDA Fourier-shift arithmetic at the CUDA value is about 26,000 times smaller in this component-RMSE comparison. This does not establish the same ratio for other frames or for final image pixels. The replay source compiled on the VM and produced the same SHA256 as the original one-off replay.

## Global-only correction still exceeds the image limit

A separate CPU/CUDA pair used `--patch_x 2 --patch_y 2`, which the movie log explicitly says skips local alignment. All other movie and global-alignment options were unchanged. This is a **diagnostic configuration**, not the 5×5 Gate 2 configuration.

| Movie `00021` CPU/CUDA corrected-image comparison | 5×5 full local | 2×2 global-only |
| --- | ---: | ---: |
| Absolute pixel RMSE | `0.003795078` | `0.006003968` |
| CPU reference standard deviation | `0.806114629` | `0.997510556` |
| Relative RMSE | `0.004707864` | `0.006018952` |
| Maximum absolute pixel difference | `1.140065` | `0.051978` |

The global-only relative RMSE exceeds the unchanged `0.001` numerical limit. Local fitting is therefore **not required** for an image difference above that limit on this movie. The full and global-only images have different reference standard deviations and different correction behavior; their RMSEs do not partition into independent global and local contributions. The global-only corrected-pixel SHA256s are CPU `ed33b6299dfc54782aa7f44c4d62c62b0727c6a0218ba8a96b18822942aaaeb1` and CUDA `64755b2d1bf0136fecd308cd7c893210255c2feac9f7abc1e190aab109291caa`.

The saved 5×5 STAR files also show a final global trajectory vector RMS difference of about `0.00349 px` over 24 frames (maximum `0.00640 px`). Evaluating their rounded 36-coefficient local models on a 5×5 spatial grid over 24 frames gives an approximately `0.00366 px` vector RMS difference (maximum `0.00822 px`). These are descriptive measurements from STAR's rounded values; they do not establish a causal decomposition of the image RMSE.

## Double cuFFT is not an immediate parity fix

`tools/replay_global_ccf_cufft_double.cu` converted the saved CUDA float `Fccs` spectrum to double, ran `CUFFT_Z2D`, and cast its unscaled real output back to float. This is an isolated FFT replay, not a replacement movie run.

| Real CCF versus CPU FFTW float result | Frame 0 RMSE | Frame 4 RMSE |
| --- | ---: | ---: |
| Native CUDA `CUFFT_C2R` float | `2.31772e-6` | `2.19278e-6` |
| Double CUDA `CUFFT_Z2D`, cast to float | `2.45346e-6` | `2.49750e-6` |

The double replay did not bring the full CCF closer to the CPU reference on either selected frame. Its frame-0 X peak moved nearer the CPU value, but its frame-4 X peak moved farther away; it is not a demonstrated parity correction. The committed helper reproduced the original one-off double-replay output byte for byte for frame 0 (SHA256 `22691adb595c6d6dbcf16a1a0b7a3c0553deaebffd09912ef5ce008f1ccc8630`).

## Boundary and next experiment

The evidence supports a causal chain for selected frames in one movie: float FFT backend differences change a flat peak at iteration 1; shift values diverge; the changed shifted frames alter the iteration-2 reference and CCF; the global-only corrected image already exceeds the numerical limit. It does **not** prove that this mechanism explains every frame, every movie, or the full 5×5 image difference. The next bounded experiment should replay a **common set of all 24 first-iteration peak shifts** through both Fourier-shift paths, then compare second-iteration reference/CCF and final global-only images. Keep Issue #36 open, PR #38 draft, and Gate 2's `0.001` threshold unchanged.
