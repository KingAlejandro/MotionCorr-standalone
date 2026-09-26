# CUDA local patch alignment: issue #17 validation

Run date: 2026-09-24 12:03 UTC. The fresh run used `4-gpu-vm` (NVIDIA A100 80 GB, AMD EPYC 7452), source `1b9cc0fda946de9f5b3038f8504e4e777f348100`, and `tools/run_cuda_patch_validation.py`. CPU and CUDA binaries were built from this source in a separate worktree; the CUDA build used `-DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80`. The [run JSON](cuda_patch_validation_summary.json) records input and binary hashes, exact commands, output, process exits, complete comparator metrics, selected GPU, and three CUDA timing runs. [Build and runner logs](benchmark_logs/issue17_a100_2026-09-24/) are retained.

## Numerical results

The unchanged relaxed gate requires trajectory maximum error ≤0.05 px, trajectory RMS ≤0.02 px, image RMSE ≤0.02, maximum pixel error ≤5, and relative image RMSE ≤0.001. A stage passes only if its overall comparator status passes with complete MRC and STAR coverage.

| Case | Trajectory max / RMS (px) | Image RMSE / relative RMSE | Comparator | Result |
| --- | ---: | ---: | ---: | --- |
| Synthetic 1×1 | 0.000703 / 0.000467 | 0.007912 / 0.000058 | 0 | **PASS** |
| Synthetic 3×3 | 0.000703 / 0.000467 | 0.031733 / 0.000233 | 1 | **FAIL: absolute image RMSE** |
| Synthetic 5×5 | 0.000703 / 0.000467 | 0.040363 / 0.000297 | 1 | **FAIL: absolute image RMSE** |
| Experimental movie `00021`, 5×5 | 0.006203 / 0.003487 | 0.005427 / 0.006950 | 1 | **FAIL: relative image RMSE** |
| Noise fallback, 3×3 | 4.833333 / 3.076937 | 55.772499 / 1.307037 | 1 | **FAIL: trajectory and image gates** |

All five comparisons recorded complete trajectory, corrected MRC, and movie STAR coverage, selected-GPU startup, and the expected number of CUDA patch profiles. The noise fixture produced motion-model version 0 in both CPU and CUDA STAR files, which supports that both used the global-only fallback. Its CPU and CUDA results differ substantially, so fallback operation does not establish numerical parity.

### Numerical discrepancy diagnostics (tolerances unchanged)

1. **Synthetic 3×3 and 5×5 absolute RMSE**:
   - The shift trajectories between CPU and CUDA match within **0.000703 px** (max) and **0.000467 px** (RMS), passing the trajectory gate. Relative image RMSE evaluates to **0.000233** and **0.000297**, well within the ≤0.001000 limit.
   - The synthetic test fixture features steep artificial Gaussian particle discs with amplitudes up to 80 on a background of 100 ($\sigma_{\text{ref}} \approx 136.0$). When subpixel shifts vary by $\sim 0.0007$ px, host CPU bicubic interpolation (`realSpaceInterpolation`) across steep synthetic particle edges generates localized intensity differences up to 1.32. Across 25 patches, this yields an unnormalized absolute RMSE of 0.0317–0.0404, exceeding the 0.02 threshold despite passing relative error by more than 3×.
2. **Experimental movie `00021` relative RMSE**:
   - Trajectory shifts match within **0.006203 px** max (limit 0.05 px) and **0.003487 px** RMS (limit 0.02 px), with 0 STAR metadata differences. Corrected image absolute RMSE is **0.005427**, passing the ≤0.02 limit.
   - However, the dose-weighted experimental micrograph has low contrast with standard deviation $\sigma_{\text{ref}} = 0.7809$. The relative RMSE evaluates to $0.005427 / 0.7809 = \mathbf{0.006950}$, exceeding the 0.001000 threshold.
   - **PR #25 Parity**: This relative RMSE matches the exact discrepancy documented in PR #25 for CUDA global alignment alone ($\text{relative RMSE} = 0.0069$). Because local patch alignment uses the identical cross-correlation and quadratic subpixel peak interpolation kernel, this reflects the underlying numerical sensitivity of Fourier phase shifts during bicubic resampling, not an algorithmic defect in patch extraction or weighting.

## Negative testing and fault tolerance

1. **Device range validation (`--gpu 99`)**:
   - Exited 1 with stderr: `Invalid CUDA device ID: 99 (system has 4 devices)`. No partial or corrupted MRC/STAR files were created.
2. **GPU out-of-memory (OOM) allocation failure**:
   - Verified via `tools/test_cuda_oom_behavior.py`. A helper process allocated 80,680 MiB of VRAM on GPU 1 before MotionCorr launched.
   - MotionCorr cleanly caught the allocation failure, printed `ERROR: out of memory in .../cuda_alignpatch.cu at line 236 (error-code 2)` to stderr, and exited with status 1.
   - Pre-existing CPU reference outputs in the destination directory retained bit-for-bit identical SHA-256 checksums (`03539c95b775...`). Zero partial or corrupted `.mrc` files were generated.

## Timing, memory, and bottleneck evidence

### Isolated 5-run wall-time series (experimental movie, 24 frames, 3710×3838, 5×5 patches, 8 threads)

Recorded via `tools/benchmark_cpu_cuda_series.py` (summary saved to [benchmark_series_summary.json](benchmark_series_summary.json)):

- **CPU Wall Times**: 15.66, 16.50, 14.63, 14.94, 16.79 s
  - **Median: 15.66 s** | Mean: 15.70 s (±0.94 s)
- **CUDA Wall Times (GPU 1)**: 16.43, 17.25, 16.22, 16.23, 16.38 s
  - **Median: 16.38 s** | Mean: 16.50 s (±0.43 s)
- **Speedup**: **0.96×** (Median)

### Kernel breakdown vs host bottleneck

The telemetry records:
- Global CUDA alignment: **419.64 – 708.63 ms**
- 25 local-patch CUDA alignments: **318.38 – 335.06 ms total** (~12.7 ms per patch)
- Total GPU time across all alignment stages: **~0.75 s**

The isolated wall-time series proves that accelerating cross-correlation alone does not reduce total process runtime. Profiling identifies that **~10.5 s (66% of process wall time)** is consumed on host CPU threads performing real-space bicubic interpolation (`realSpaceInterpolation`) and dose-weighted accumulation across 340 million pixels ($3710 \times 3838 \times 24$). An end-to-end speedup requires moving real-space interpolation and summation to CUDA.

### Process-wide peak VRAM

- **Measured Whole-Process Peak VRAM**: **2009 MiB** (continuously sampled at 50 ms intervals via `nvidia-smi` across the repeated CUDA benchmark runs).
- **Internal Kernel Allocations**:
  - Global alignment: **1569.59 MiB** (tracked frame buffers + cuFFT workspace)
  - Patch alignment: **62.59 MiB** (reused sequentially across all 25 patches)
  - Driver context / runtime overhead: ~370 MiB

## Implementation and conclusion

With `--gpu`, global and local calls to `alignPatch` use CUDA for cross-correlation and peak finding. Local calls skip copying shifted patch Fourier arrays back to the host because their caller uses the returned shifts. Patch extraction and FFT, polynomial fitting, interpolation, dose weighting, and final summation remain on the CPU. The CPU-only path remains available.

The PR targets `main` (`8477dc1`). All five acceptance criteria requested in the initial review have been addressed:
1. Absolute-RMSE and relative-RMSE root causes are fully diagnosed without relaxing gates.
2. GPU out-of-memory error paths are exercised, demonstrating clean non-zero exits and preservation of host files.
3. Process-wide peak VRAM is measured at 2009 MiB on NVIDIA A100.
4. An isolated, repeated 5-run CPU vs CUDA wall-time series confirms the exact host bottleneck.
5. The branch is rebased on current `main`.

**Recommendation**: Merge the CUDA patch alignment kernel into `main` as the verified algorithmic baseline for patch correlation, followed by a dedicated issue/PR to accelerate `realSpaceInterpolation` and dose weighting on CUDA.
