# Issue 36: first global peak probe on movie 00021

Follow-up: [iteration-2 feedback, global-only image comparison, and shift/FFT replays](iteration2_and_global_only.md).

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

These four initial traces narrow the leading X-shift difference to **at or before the real-space CCF samples**, not the integer peak choice or double-versus-float quadratic division alone. The matched-array follow-up below identifies the first non-identical stage and separates the inverse-FFT contribution for these two frames. This is one movie and two selected frames, not a new 24-movie Gate 2 result. The `0.001` threshold was not changed.

## Phase 2: matched array checkpoints and FFT replay

The follow-up source adds an **optional** `MOTIONCORR_PEAK_TRACE_ARRAYS=1` to the same one-movie peak probe. It saves five native-endian binary chunks for the selected iteration and post-grouping frame: `input` (complex float `[3838,1856]`), `weight` (float `[972,487]`), `fref` and `fccs` (complex float `[972,487]`), and `iccs` (float `[972,972]`). The on-disk order is row-major; complex values are interleaved real/imaginary `float32`. The five chunks total 70,233,040 bytes per backend, below the explicit 256 MiB limit. Their paths are `motioncorr-global-array-{cpu,cuda}-{stage}.bin` in the trace directory. Raw chunks remain on the VM in `validation/phase2_frame{0,4}_trace/`; they are derived movie data and are not committed. The diagnostic source and FFTW replay helper are included in this draft PR.

The same CUDA-enabled binary (SHA256 `c2419c8684de18301871441c95aabea3fafc226711503a85073f600c90942273`) ran CPU and GPU-0 variants of the exact Phase-1 command above, changing only `MOTIONCORR_PEAK_TRACE_FRAME` between `0` and `4` and adding `MOTIONCORR_PEAK_TRACE_ARRAYS=1`. Source was copied into the isolated VM worktree for this diagnostic build; the main VM checkout was untouched. All four runs completed. Input TIFF, gain, and STAR hashes were unchanged from Phase 1. The corrected-pixel payload SHA256s remained exactly `bf738254...` (CPU) and `0e04d076...` (CUDA) in **both** frame selections, matching the previous untraced runs. Thus this opt-in capture did not change the observed movie output.

| Stage, selected iteration 1 | Frame 0 CPU/CUDA | Frame 4 CPU/CUDA |
| --- | ---: | ---: |
| Input Fourier frame | bit-identical | bit-identical |
| B-factor weight | 389,040 / 473,364 float coefficients differ; RMSE `1.0694e-8`, max `1.1921e-7` | same |
| Reference sum `Fref` | bit-identical | bit-identical |
| Weighted spectrum `Fccs` | 778,586 / 946,728 float components differ; RMSE `1.0026e-14`, max `3.6380e-12` | 778,215 differ; RMSE `7.8273e-15`, max `1.8190e-12` |
| Real CCF `Iccs` | 602,002 / 944,784 pixels differ; RMSE `2.3177e-6`, max `1.1444e-5` | 597,906 differ; RMSE `2.1928e-6`, max `1.1444e-5` |

The **first non-identical stage** is weight generation. The CPU uses its host expression and `exp`, while CUDA uses float arithmetic and `expf`; this is a plausible source of the one-step weight differences, although the trace by itself does not isolate each arithmetic operation. The selected input and `Fref` are exactly equal.

To separate spectrum differences from inverse-FFT differences, `tools/replay_global_ccf_fftw.cpp` ran both saved `Fccs` arrays through the same `fftwf_plan_dft_c2r_2d(972,972,...,FFTW_ESTIMATE)` path, with no inverse scaling, on the same VM. Replaying the CPU spectrum reproduced the CPU `Iccs` **bit for bit** for frames 0 and 4. Replaying the CUDA spectrum through FFTW differed from the CPU `Iccs` at only 27 pixels (frame 0, RMSE `1.0196e-8`) and 15 pixels (frame 4, RMSE `7.5999e-9`). The five values around each selected peak were bit-identical to the CPU values in both replays. In contrast, the native CUDA cuFFT results differed at 602,002 and 597,906 pixels respectively, with ~`2.2–2.3e-6` RMSE. The FFTW replay of the CUDA spectrum gave frame 0's CPU X curvature denominator `-0.0012321472` and unscaled shift `-1.7105263158`, while native CUDA gave `-0.0012359619` and `-1.7129629630` when its captured stencil is evaluated in double precision. Frame 4 likewise recovered the CPU peak stencil from the CUDA spectrum.

**Interpretation:** For these two selected frames in movie `00021`, tiny pre-FFT spectrum differences exist, but FFTW-versus-cuFFT inverse output is the dominant contributor to the measured real-CCF difference and the observed peak-stencil/shift discrepancy. This is a controlled same-input FFT replay, not proof that the two FFT libraries alone explain the full corrected-image Gate 2 failure across 24 movies. Local-patch alignment, later iterations, and output generation may amplify or add differences. Issue #36 remains open; the Gate 2 relative image-RMSE limit remains `0.001`.

To reproduce the replay on the VM, build the helper and use fresh output paths (it refuses existing output files):

```sh
g++ -O2 tools/replay_global_ccf_fftw.cpp -lfftw3f -o /tmp/replay_global_ccf_fftw
/tmp/replay_global_ccf_fftw <trace-dir>/motioncorr-global-array-cuda-fccs.bin \
  <trace-dir>/replay-fftw-cuda.bin 972 972
```

The replay helper source was checked against the original diagnostic replay: both produced byte-identical outputs for the frame-0 CPU and CUDA spectra. The CPU-spectrum replay SHA256 is `1bbc27913c10efd3b8f46ab7ced45e9ec8752c4d9cfa98b132bba8739c761455`; the CUDA-spectrum FFTW replay SHA256 is `c20c618827d68322bddd6c6513b6f0ea8e931f9a326bfaadb014cabbe931de91`. The raw input array SHA256 for frame 0 is `b604183a30802041b8c670a8af4a63ec0ed254cbac7bf4902c4a2e1d9d851167` in both backends. The reference SHA256 is `38d37610238987c985df4b4fc4eb2a603d7019177665b5c4bebc2` in both.
