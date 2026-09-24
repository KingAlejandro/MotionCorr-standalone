# Issue 36: exact weight and common-global-trajectory control

## Decision

The one-ULP global B-factor weight difference is fixed: CPU and CUDA now call the same host `RFLOAT`/`exp` row calculation, and CUDA uploads the resulting float plane. On both tutorial movies the traced CUDA weight is **byte-identical** to CPU. This correction does **not** change the CUDA corrected-image payload or rescue Gate 2.

The decisive control supplies all 24 CPU global shift deltas in each of the two global iterations to the CUDA Fourier-shift stage. CUDA still computes its own reference, weighted CCF spectra, cuFFT correlation images, and measured peaks. The control preserves the full 5×5 local alignment, dose weighting, model fit, interpolation, and image output. With this common trajectory, both movies pass the **unchanged** corrected-image relative-RMSE limit of `0.001`. These are counterfactual passes; native CUDA remains a Gate 2 failure.

| CUDA configuration | `00021` relative image RMSE | `00046` relative image RMSE | Gate 2 |
| --- | ---: | ---: | --- |
| Original GPU weight, native shifts | `0.004707864` | `0.010081785` | FAIL / FAIL |
| CPU-exact weight, native shifts | `0.004707864` | `0.010081785` | FAIL / FAIL |
| Original GPU weight, injected CPU global shifts | `0.000345353` | `0.000280298` | PASS / PASS, counterfactual |
| CPU-exact weight, injected CPU global shifts | `0.000345353` | `0.000280298` | PASS / PASS, counterfactual |

The native and CPU-exact-weight runs have identical corrected-image payloads for each movie. The two common-trajectory runs likewise have identical payloads. Holding the trajectory fixed therefore accounts for the image-gate failure in these two runs; the one-ULP weight variation does not. The relative image error falls by `13.6×` (`00021`) and `36.0×` (`00046`) with common shifts.

## Where residual differences remain

For each movie, the exact-weight trace has the same SHA-256 as the CPU weight plane (`0496047b4f461aeef64e9b3686b0b89fe6fbd099a768da89432a14c4817df6e5`). First-iteration weighted CCF spectra still differ: the largest per-frame float-component RMSE is `3.03e-14` (`00021`) and `3.54e-14` (`00046`), with maximum absolute difference `2.91e-11`. The first-iteration real CCF images still differ by up to `2.59e-6` and `2.53e-6` RMSE. The earlier all-frame FFTW replay localized most of that first-iteration CCF difference to the inverse-FFT backend.

The common-trajectory trace proves the injected `deltax/y` and outgoing `totalx/y` equal CPU exactly in both iterations. It also preserves separate audit arrays for the **measured** CUDA recentered deltas and the float phase inputs actually sent to the CUDA kernel. All 6,385 expected paired checkpoints and eight CUDA-only audit arrays are present for each movie; no raw-input byte differences or nonfinite values were reported.

The two common-trajectory weight controls are byte-identical at every checked frame of the first and second post-shift Fourier spectra, global inverse frames, model x/y fields, interpolated contributions, and cumulative sums, plus the final sum. Relative to CPU, 23 of 24 post-shift Fourier frames still differ under common shifts. The worst per-frame relative L2 difference after the first global shift is `1.41e-6` for `00021` and `8.95e-7` for `00046`, versus `0.01298` and `0.01013` with native CUDA shifts. The residual begins after the CUDA phase operation with the same injected trajectory and includes float conversion of its phase inputs; the trace does not isolate those two arithmetic effects from each other. The final relative image RMSE remains nonzero but below Gate 2.

There were no changes to Gate 2 thresholds. Both FFT libraries remain credible numerical implementations. The result does not certify the native CUDA shift decisions or prove that cuFFT alone causes those decisions. It establishes that the global shift-value differences carry the measured image-gate failure in `00021` and `00046`. A future native correction should target the CCF-to-subpixel-shift decision and then pass all 24 tutorial movies under the same gate.

## Provenance and files

The four-control runs used the isolated `4GPUs` checkout, A100 GPUs, one worker, fixed seed `1`, 24 frames, 5×5 patches, B-factor `150`, gain correction, and dose weighting at `1.277` electrons/Å²/frame. The common-trajectory executable SHA-256 is `5a4470e2111ab41307ee397cc855fd59acc8d82c97fdbb905aa3afc50f6af7cb`; the first exact-weight traced runs used `a19ccb43321cff6ad082592c8ca575b056f1de1958f0e18de50191b0a1e35ffa`. Fresh CPU full traces from the common-trajectory executable reproduced all six injected delta/total arrays and both corrected-pixel payloads **byte for byte** against the frozen CPU references. The frozen source arrays, input TIFFs, gain, and STAR selections were checked against fixed SHA-256 values before the legacy-weight counterfactual launches and independently verified for the exact-weight counterfactuals afterward.

The compact evidence here includes per-movie gate reports, preflight manifests, complete per-checkpoint comparison metrics, stage summaries, CPU source-reproduction reports, and control-analysis JSON. Raw ~30 GiB array traces per run remain on the analysis VM under `validation/issue36_phase5/`; they are not committed. `tools/run_issue36_phase5.py` performs the source checks and launches the counterfactual. `tools/verify_issue36_cpu_replay_source.py` checks the fresh CPU source, and `tools/analyze_issue36_phase5.py` summarizes all-frame controls. The override requires an explicit CPU trace and full trace directory; the normal CUDA path uses no injected trajectory.

The compact per-movie evidence is in [`00021/`](00021/) and [`00046/`](00046/). This is a controlled diagnostic on two movies, not a certified native CUDA parity result or a full provenance audit of every raw trace file. PR review should keep the remaining source-manifest concern open while the native shift-decision error is investigated.
