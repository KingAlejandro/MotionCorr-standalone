# CUDA local patch alignment: issue #17 validation

Run date: 2026-09-24. The captured run used `4-gpu-vm` (NVIDIA A100 80 GB, AMD EPYC 7452), the issue #17 branch based on `7a794dc`, and `tools/run_cuda_patch_validation.py`. The [captured JSON](cuda_patch_validation_summary.json) contains the comparator metrics and three CUDA timing runs. It was produced by the earlier harness version, whose `verdict` remained `UNKNOWN`; the per-stage comparator results below are the recorded evidence. The corrected harness now fails closed and requires a fresh run for a complete machine verdict.

## Numerical results

The unchanged relaxed gate requires trajectory maximum error ≤0.05 px, trajectory RMS ≤0.02 px, image RMSE ≤0.02, maximum pixel error ≤5, and relative image RMSE ≤0.001. A stage passes only if its overall comparator status passes with complete MRC and STAR coverage.

| Case | Trajectory max / RMS (px) | Image RMSE / relative RMSE | Comparator | Result |
| --- | ---: | ---: | ---: | --- |
| Synthetic 1×1 | 0.000703 / 0.000467 | 0.007912 / 0.000058 | 0 | **PASS** |
| Synthetic 3×3 | 0.000703 / 0.000467 | 0.031841 / 0.000234 | 1 | **FAIL: absolute image RMSE** |
| Synthetic 5×5 | 0.000703 / 0.000467 | 0.040174 / 0.000296 | 1 | **FAIL: absolute image RMSE** |
| Experimental movie `00021`, 5×5 | 0.006203 / 0.003487 | 0.005427 / 0.006950 | 1 | **FAIL: relative image RMSE** |
| Noise fallback, 3×3 | 4.833333 / 3.076937 | 55.772499 / 1.307037 | 1 | **FAIL: trajectory and image gates** |

All five comparisons recorded complete trajectory, corrected MRC, and movie STAR coverage. The noise fixture produced motion-model version 0 in both CPU and CUDA STAR files, which supports that both used the global-only fallback. Its CPU and CUDA results differ substantially, so fallback operation does not establish numerical parity. Invalid device `--gpu 99` exited 1 with a device-range error. GPU out-of-memory behaviour and preservation of CPU output after a GPU failure remain unverified.

The experimental result remains above the declared 0.001 relative image limit. That global CUDA discrepancy also affects this patch prototype; the data do not yet isolate how much of the final image difference comes from local patch alignment. No tolerance was changed.

## Timing and memory evidence

Three CUDA runs of the 24-frame, 3710×3838 experimental movie with 5×5 patches recorded process wall times of **14.16, 16.36, and 16.58 s** (median **16.36 s**). A single CPU reference run took **16.12 s**. This does not demonstrate an end-to-end speedup. The corresponding global CUDA alignment profiles were **330.24, 317.87, and 659.43 ms**; the 25 local-patch profiles totalled **316.58, 319.03, and 319.27 ms**. The wide global-transfer variation makes a single stage time unsuitable as a performance claim.

The profiler reports **1569.59 MiB** of tracked global buffers plus cuFFT workspace and **62.59 MiB** for each patch call. These are allocation sums from the implementation, not a measured peak for the whole GPU process. The run does not isolate host I/O, patch preparation, fitting, dose weighting, or interpolation times, so their individual bottlenecks and any projected speedup are unestablished.

## Implementation and next gates

With `--gpu`, global and local calls to `alignPatch` use CUDA for cross-correlation and peak finding. Local calls skip copying shifted patch Fourier arrays back to the host because their caller uses the returned shifts. Patch extraction and FFT, polynomial fitting, interpolation, dose weighting, and final summation remain on the CPU. The CPU-only path remains available.

Before promoting this draft: rerun the corrected harness in a fresh output directory; retain commands, source/binary/input hashes, logs, selected-GPU proof, complete comparator results, and a process-wide peak VRAM measurement. Diagnose the absolute-RMSE failures on 3×3 and 5×5 and the experimental relative-RMSE failure without raising gates. Exercise an out-of-memory or allocation-failure path and verify it leaves CPU outputs intact. Compare an isolated CPU and CUDA wall-time series before deciding whether the added CUDA complexity is worthwhile. The PR must also be based on current `main`; PR #25 has merged.

**Review verdict: CHANGES_REQUESTED.** The patch kernel wiring is a useful experimental step, but the current numerical and failure-handling evidence does not satisfy issue #17's acceptance gates.
