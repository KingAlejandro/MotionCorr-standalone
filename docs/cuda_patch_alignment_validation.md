# CUDA local patch alignment: issue #17 validation

Run date: 2026-09-24 12:03 UTC. The fresh run used `4-gpu-vm` (NVIDIA A100 80 GB, AMD EPYC 7452), source `1b9cc0fda946de9f5b3038f8504e4e777f348100`, and `tools/run_cuda_patch_validation.py`. CPU and CUDA binaries were built from this source in a separate worktree; the CUDA build used `-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80`. The [run JSON](cuda_patch_validation_summary.json) records input and binary hashes, exact commands, output, process exits, complete comparator metrics, selected GPU, and three CUDA timing runs. The corrected harness returned **FAIL** with exit status 1. [Build and runner logs](benchmark_logs/issue17_a100_2026-09-24/) are retained.

## Numerical results

The unchanged relaxed gate requires trajectory maximum error ≤0.05 px, trajectory RMS ≤0.02 px, image RMSE ≤0.02, maximum pixel error ≤5, and relative image RMSE ≤0.001. A stage passes only if its overall comparator status passes with complete MRC and STAR coverage.

| Case | Trajectory max / RMS (px) | Image RMSE / relative RMSE | Comparator | Result |
| --- | ---: | ---: | ---: | --- |
| Synthetic 1×1 | 0.000703 / 0.000467 | 0.007912 / 0.000058 | 0 | **PASS** |
| Synthetic 3×3 | 0.000703 / 0.000467 | 0.031733 / 0.000233 | 1 | **FAIL: absolute image RMSE** |
| Synthetic 5×5 | 0.000703 / 0.000467 | 0.040363 / 0.000297 | 1 | **FAIL: absolute image RMSE** |
| Experimental movie `00021`, 5×5 | 0.006203 / 0.003487 | 0.005427 / 0.006950 | 1 | **FAIL: relative image RMSE** |
| Noise fallback, 3×3 | 4.833333 / 3.076937 | 55.772499 / 1.307037 | 1 | **FAIL: trajectory and image gates** |

All five comparisons recorded complete trajectory, corrected MRC, and movie STAR coverage, selected-GPU startup, and the expected number of CUDA patch profiles. The noise fixture produced motion-model version 0 in both CPU and CUDA STAR files, which supports that both used the global-only fallback. Its CPU and CUDA results differ substantially, so fallback operation does not establish numerical parity. Invalid device `--gpu 99` exited 1 with a device-range error and no partial corrected MRC. GPU out-of-memory behaviour and preservation of CPU output after a GPU failure remain unverified.

The experimental result remains above the declared 0.001 relative image limit. That global CUDA discrepancy also affects this patch prototype; the data do not yet isolate how much of the final image difference comes from local patch alignment. No tolerance was changed.

## Timing and memory evidence

Three CUDA runs of the 24-frame, 3710×3838 experimental movie with 5×5 patches recorded process wall times of **16.35, 16.24, and 16.63 s** (median **16.35 s**). A single CPU reference run took **16.09 s**. This does not demonstrate an end-to-end speedup. The corresponding global CUDA alignment profiles were **458.25, 419.64, and 708.63 ms**; the 25 local-patch profiles totalled **318.38, 335.06, and 325.72 ms**. The wide global-transfer variation makes a single stage time unsuitable as a performance claim.

The profiler reports **1569.59 MiB** of tracked global buffers plus cuFFT workspace and **62.59 MiB** for each patch call. These are allocation sums from the implementation, not a measured peak for the whole GPU process. The run does not isolate host I/O, patch preparation, fitting, dose weighting, or interpolation times, so their individual bottlenecks and any projected speedup are unestablished.

## Implementation and next gates

With `--gpu`, global and local calls to `alignPatch` use CUDA for cross-correlation and peak finding. Local calls skip copying shifted patch Fourier arrays back to the host because their caller uses the returned shifts. Patch extraction and FFT, polynomial fitting, interpolation, dose weighting, and final summation remain on the CPU. The CPU-only path remains available.

Before promoting this draft: diagnose the absolute-RMSE failures on 3×3 and 5×5 and the experimental relative-RMSE failure without raising gates. Exercise an out-of-memory or allocation-failure path and verify it leaves CPU outputs intact. Record a process-wide peak VRAM measurement. Compare an isolated, repeated CPU and CUDA wall-time series before deciding whether the added CUDA complexity is worthwhile. The PR now targets current `main`.

**Review verdict: CHANGES_REQUESTED.** The patch kernel wiring is a useful experimental step, but the current numerical and failure-handling evidence does not satisfy issue #17's acceptance gates.
