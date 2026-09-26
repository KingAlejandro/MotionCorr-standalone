# Issue 36: every-frame CPU/CUDA checkpoint trace

## Scope and status

This opt-in diagnostic compares the fixed CPU path with the A100 CUDA global-alignment path on RELION SPA tutorial movies `20170629_00021` and `20170629_00046`. Each movie has 24 source frames. The command uses one worker, a fixed random seed, 5×5 local patches, and dose weighting. Raw array chunks stay on the isolated `4GPUs` analysis VM; this directory contains the complete numerical comparison for each paired checkpoint, compact summaries, controlled FFTW replays, and unchanged Gate 2 reports.

**Gate 2 still fails.** The trajectory and STAR checks pass, while corrected-image relative RMSE is `0.004707864` for `00021` and `0.010081785` for `00046`, versus the declared `0.001` limit. The trace does not change the gate or make a parity claim.

Both CPU/CUDA pairs passed the exact 6,385-key coverage check with zero unmatched keys, zero raw-input byte differences, and zero nonfinite scalar pairs. Each movie has 6,072 numerically different checkpoints; the other 313 match exactly. The compressed metrics preserve both hashes and the numerical comparison for every key.

## What each pair records

The trace contains every frame at these boundaries, in execution order:

1. Raw read, gain application, defect correction, source/group mapping, and initial FFT.
2. Global weight; both global iterations' frame inputs, reference spectrum, weighted CCF spectra, inverse-FFT correlation images, 16-column integer/subpixel peak records, origin-adjusted and accumulated shifts, and post-shift Fourier frames.
3. Global inverse FFT; each of 25 local patches' bounds, spatial frame inputs, local alignment checkpoints for both iterations, and final patch shifts.
4. Polynomial model observations and coefficients; per-frame dose, weighted Fourier frame, and inverse FFT frame.
5. Per-frame fitted x/y displacement fields, native-precision interpolated contribution, cumulative output after each frame, and final sum.

Each binary chunk has a matching shape/dtype sidecar. The comparator pairs by checkpoint key, verifies backend and movie identity, checks every chunk size/shape and finite values, computes SHA-256 for both arrays, and records numerical differences. Different CPU float64 and CUDA float32 shift arrays are compared numerically while retaining both byte hashes. The `--require-tutorial-24x5` check requires the exact 6,385-key stage/frame/patch schema on each backend, so an omitted checkpoint on both sides cannot pass unnoticed. Missing keys are reported as a failed pairing after all shared keys are compared. The full trace is deliberately limited to the dose-weighted, third-order polynomial output path; unsupported paths and `--save_noDW` stop without a completion marker.

The machine-readable files are:

| File per movie | Contents |
| --- | --- |
| `<movie>_metrics.jsonl.gz` | One comparison and two SHA-256 hashes for every paired checkpoint; includes each patch, frame, and iteration. |
| `<movie>_summary.json` | Stage/family extrema and every frame's peak-shift error; lists integer-peak and interpolation-branch changes. |
| `<movie>_fftw_replay.json` | CUDA CCF spectra replayed through float FFTW for each captured global iteration and frame. |
| `<movie>_gate2.json` | Full corrected-image, trajectory, and STAR gate result. |

The raw chunks remain under `validation/release_<movie>_<backend>/trace` in the isolated VM checkout. Complete corrected outputs remain beside each trace; copies of the four run logs and four movie logs are in `logs/`. The two compressed metrics files here contain hashes and scalar statistics, not movie pixels or Fourier arrays.

## Observed causal sequence

| Boundary | `00021` | `00046` | Interpretation |
| --- | ---: | ---: | --- |
| Raw/gain/defect/initial FFT | 24/24 frames byte-identical | 24/24 byte-identical | Same input and CPU preprocessing. |
| First global input and reference | 24/24 inputs and reference identical | Same | No earlier frame/reference divergence. |
| Global weight | max difference `1.19e-7` | same | Float evaluation differs by one ULP at some coefficients. |
| First weighted CCF spectrum | max absolute difference `2.91e-11` | same | Small float arithmetic difference before inverse FFT. |
| First inverse-FFT CCF image | per-frame RMSE `2.11–2.59e-6` | `2.13–2.53e-6` | Float FFTW/cuFFT produce different real correlation values. |
| CUDA spectrum replayed through FFTW | per-frame RMSE versus CPU `5.55e-9–6.18e-8` | `9.41e-9–8.74e-8` | The inverse-FFT implementation accounts for most first-iteration CCF difference on all 24 frames. |
| First global subpixel peak | max vector error `0.00937 px` | `0.00773 px` | Small CCF differences are amplified by a shallow quadratic peak. Integer peak and interpolation branch are unchanged. |
| Second global input/reference | 23/24 input frames differ; reference differs | same | First-iteration shift decisions feed back into the next pass. |
| Global inverse frame/local patch input | 23/24 frames differ | same | Local alignment begins with propagated global differences. |
| 25 local patches, 2 iterations | No integer peak or branch changes; max subpixel error `0.01478 px` | No integer peak or branch changes; max `0.01783 px` | Local motion model receives and further responds to differing frames. |
| Fitted output displacement fields | 23/24 frames differ; max absolute x/y difference `0.00526/0.00416 px` | 23/24; `0.01124/0.01241 px` | Different patch observations produce different polynomial coefficients and pixel displacements. |
| Native-precision interpolated frame contribution | 23/24 frames differ; max absolute difference `1.13255` | 23/24; `1.72687` | Common CPU interpolation receives different weighted frames and model fields. |
| Cumulative output after each frame | 23/24 frames differ; max absolute difference `1.14007` | 23/24; `1.71742` | Final image discrepancy accumulates from the changed per-frame contributions. |
| Final corrected image | relative RMSE `0.004707864` | `0.010081785` | Both exceed Gate 2's `0.001` limit. |

The CCF replay is a controlled comparison **at the FFT boundary**. Iteration 1 has identical input frames and reference, so it is strong evidence that FFT backend variation dominates that boundary. In iteration 2, replaying CUDA spectra through FFTW leaves CPU-versus-replay CCF RMSE of `3.01–6.20e-7` for `00021` and `3.84–7.41e-7` for `00046`. Those residuals are much larger than iteration 1 because the inputs and reference already differ. Local alignment also starts from different frames. The trace does not prove the entire final image difference is caused only by FFTW versus cuFFT. Both FFT libraries are credible implementations; accepting their local numerical variation still leaves the declared corrected-image acceptance criterion unmet.

No integer peak moves or interpolation fallback-branch changes were observed across the 52 peak records per movie (2 global plus 50 local). This rules out a coarse peak-selection discrepancy in these two runs. It does not rule out a separate subtle CUDA error or prove equivalence on other movies. The next decisive counterfactual is a complete run with a common global shift trajectory at the CPU/CUDA boundary, followed by the unchanged image gate; the per-frame model/interpolation checkpoints here will locate any remaining output-stage contribution.

Only global alignment uses CUDA in this configuration. Local patch alignment, dose weighting, inverse transforms after global alignment, model fitting, and final interpolation run through the same CPU code in both runs. Their differences therefore occur with already differing frame spectra, trajectories, or fitted coefficients; they are not evidence of an independent CUDA local/interpolation kernel failure. The previous [controlled frame-4 Fourier-shift replay](../issue36_peak_probe/iteration2_and_global_only.md) found shift **values** much more consequential than CPU-versus-CUDA shift arithmetic for that one frame. A common-trajectory full run is still needed to establish the contribution across every frame.

## Reproduction and provenance

- Base source revision before these diagnostic changes: `3a8dbbc` on `codex/issue36-diagnostics`; the diagnostic source, tools, and report are in PR #38.
- Analysis host: `4GPUs`, GPU ordinal `0`, NVIDIA A100 80GB PCIe, UUID `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`; driver `570.86.10`, CUDA compiler `12.8.61`. The CUDA movie logs contain CUDA global-alignment and cuFFT profile markers. CPU and CUDA runs use the same executable.
- Final diagnostic executable SHA-256: `a77777bc84bb033ce279dffc3e036c62100c5f0f43881cccc244753b1a59a6f7`.
- Input SHA-256: movie `00021` `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`; movie `00046` `61094383ce6750976275b13227033dcdb154c8214ef3db402aa6440a505ad377`; gain `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`.
- The `00046` one-row STAR selection SHA-256 is `29be387682e00c48da13d69e517709a8ff0b4583cca31fa037ee9366ffe32a31` and points to the same source TIFF. Movie `00021` uses the first row of the tutorial `movies.star`.
- Runs use `--use_own --j 1 --do_at_most 1 --seed 1 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc`, plus `--gpu 0` for CUDA. The full trace is enabled only by `MOTIONCORR_FULL_TRACE_DIR=<fresh directory>` and `MOTIONCORR_FULL_TRACE_MAX_GIB=128`.
- A separate **untraced** `00021` CPU/CUDA pair with this final executable reproduced the same corrected-pixel payload SHA-256 values as the traced runs: CPU `bf738254a4d9c218ddc723a3ec595c999c3ad27a01a56b97c2d903046a0f77b0`; CUDA `0e04d076edfdb02115c3201cbe0516235604099ff606e9342cd69f25065391d5`.
- Trace chunks are exact native-endian arrays. The full mode is explicitly larger than the 256 MiB selected-frame probe; each run has an enforced 128 GiB cap. The comparator and summarizer never modify the numerical gate.
