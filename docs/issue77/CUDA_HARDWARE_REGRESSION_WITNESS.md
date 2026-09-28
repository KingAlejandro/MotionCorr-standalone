# Explicit Native CUDA Regression Witness and Fail-Closed Harness (PR #93 Review Fix)

## 1. Context and Review Finding

In [PR #93](https://github.com/KingAlejandro/MotionCorr-standalone/pull/93), review discussion [`discussion_r4119257375`](https://github.com/KingAlejandro/MotionCorr-standalone/pull/93#discussion_r4119257375) flagged at commit `4998599a5bfa990a13a74e32069abc3788f51ba4`:
> **Register the regression test with CUDA enabled**
> When this test runs through the normal CTest registration, `CMakeLists.txt:84-86` supplies only `--binary`, so the new `gpu=None` default means `run_motioncorr` never appends `--gpu` and the test still exercises the CPU path. Consequently, regressions in the CUDA cache and event-scheduling changes cannot fail this automated bit-exact gate; add a CUDA-build test variant that passes a device ID and confirms the native CUDA stages ran.

This bounded continuation addresses this finding on the clean PR #93 worktree without restarting broad optimization. Production kernels, cache management, and session state remain **strictly frozen** (reliability, error classification, and retry contracts are owned by #69).

---

## 2. Worktree and Provenance

- **Implementation Worktree Path**:
  `/Users/alex.konstantinov/Documents/Codex/2026-09-23/co/work/issue77-reviewed`
- **Branch**: `fix/issue77-reviewed-kernels`
- **Base Commit**: `4998599a5bfa990a13a74e32069abc3788f51ba4`
- **Review Fix Commit**: `c5d05daed8584b443bdc1eccb29601d63131cc93`
- **Agent / Assistant History**:
  - Initial PR #93 implementation and review: mixed Codex / manual engineering.
  - Review fix implementation and hardware validation: Gemini 3.8 Flash High via Antigravity harness (authorized route, no credential modifications).

---

## 3. Harness and CTest Registration Changes

### A. Stage-Backend-Device Witness Verification
In `tests/test_synthetic_regression.py`, `verify_cuda_stage_witnesses()` enforces three strict criteria when `--require-cuda` or `--gpu` is active:
1. **Device Startup Witness**: Asserts stdout contains:
   `Using CUDA acceleration on GPU device {gpu} for global alignment.`
2. **Fail-Closed CPU Fallback Detection**: Inspects stdout and movie log files (`*.log`) for any fallback markers:
   - `WARNING:.*falling back`
   - `falling back to CPU`
   - `falling back to streaming pipeline`
   - `materializing host frames for fallback`
   Any fallback immediately raises a `RuntimeError`—silent CPU fallback is never counted as a CUDA pass.
3. **Stage Profile Markers**: Confirms required native CUDA stages executed and recorded their profile blocks:
   - `[CUDA Global Alignment Profile]`
   - `[CUDA Global Alignment] completed`
   - `[CUDA Patch Alignment Profile]`
   - `[CUDA Patch Alignment] completed`
   - `[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]`

### B. Fail-Closed Negative Controls
`test_synthetic_regression.py --negative-control` exercises seven automated negative controls:
1. Missing CUDA startup witness in stdout -> rejected (`RuntimeError`).
2. CPU fallback warning in execution log -> rejected (`RuntimeError`).
3. Missing native CUDA stage profile marker -> rejected (`RuntimeError`).
4. Corrupted/altered image pixel values -> rejected (`compare_mrc` difference).
5. Corrupted/altered trajectory shifts -> rejected (`compare_shifts` difference).
6. Missing output files (MRC/STAR) -> rejected.
7. Non-zero process exit code -> caught and reported.

Running `--require-cuda` on a CPU-only binary was additionally verified to fail closed with exit code 1 (`ERROR: --gpu was specified with --use_own, but MotionCorr was built without CUDA support`).

### C. CMake Test Registration
In `CMakeLists.txt`:
- Under `BUILD_TESTING`:
  - Retains `SyntheticRegression` (runs CPU path without GPU dependency).
  - Registers `SyntheticRegressionNegativeControl` (`--negative-control`).
- Under `if(BUILD_TESTING AND CUDA)`:
  - Adds option `ENABLE_CUDA_HARDWARE_TESTS` (default `OFF`).
  - If `ENABLE_CUDA_HARDWARE_TESTS` is `ON`, or environment variables `MOTIONCORR_TEST_GPU` / `CUDA_VISIBLE_DEVICES` are set:
    - Registers `SyntheticRegressionCuda` with `LABELS "cuda;hardware"`, passing `--binary $<TARGET_FILE:motioncorr> --gpu ${_CUDA_TEST_DEVICE} --require-cuda`.
- Preserves compile-only CI (`cuda-compile` job in `.github/workflows/ci.yml`) without GPU requirement.

---

## 4. Hardware Validation Results on SCARF

A dedicated SLURM allocation was executed on SCARF (`gpu-devel` partition, quota-safe path `/work4/scd/scarf1415/motioncorr/pr93-witness/`). The shared 4GPU VM was untouched (#53 owns GPU 0/1, #69 owns GPU 2).

### Execution Environment Provenance
- **Job ID**: `3511128`
- **Node**: `gn0001.scarf.rl.ac.uk`
- **Date (UTC)**: `2026-09-28T07:14:01Z`
- **GPU Device**: NVIDIA A100-SXM4-40GB
  - **UUID**: `GPU-4cbb45c3-afb8-4430-1be8-155a7dceb02a`
  - **Memory**: 40960 MiB total, 40441 MiB free
  - **Active Processes**: None (exclusive allocation)
- **CPUs Allowed**: `5-8,17-20,37-40,49-52` (16 logical cores)
- **NUMA Topology**: 2 nodes (node distances 10, 32)
- **Toolchain**:
  - `nvcc`: CUDA 12.8, V12.8.61 (build `35404655_0`)
  - `gcc`: GCC 13.2.0
  - `cmake`: CMake 3.27.6
  - `python3`: Python 3.9.25 with NumPy

### Binary Identification
- Source SHA: `c5d05daed8584b443bdc1eccb29601d63131cc93`
- CPU Binary SHA256: `6d4bfbbf8d531da712be14c3940bd28955afe0eedf01d61ecedbeb9db0e50855`
- CUDA Binary SHA256: `7f2c465e8882057b86cbb00853ce24213f2bae16a6a7b66480ff4e8e4d2bce78`

### Test Suite Execution
1. **Negative Controls**:
   All 7 fail-closed negative controls PASSED (`python3 tests/test_synthetic_regression.py --negative-control`).
2. **CPU Binary Fail-Closed under `--require-cuda`**:
   Correctly failed closed with exit code 1 (`ERROR: --gpu was specified with --use_own, but MotionCorr was built without CUDA support`).
3. **Native CUDA Execution & Witness Verification**:
   Executed on A100 GPU 0.
   - Startup witness verified: `Using CUDA acceleration on GPU device 0 for global alignment.`
   - No CPU fallback detected.
   - All stage profile markers present in `synthetic_movie.log`:
     - `[CUDA Global Alignment Profile]`
     - `[CUDA Global Alignment] completed; converged=yes`
     - `[CUDA Patch Alignment Profile]`
     - `[CUDA Patch Alignment] completed; converged=yes`
     - `[CUDA Dose-Weighted Reconstruction Profile (Resident VRAM)]`
   - Multi-threaded CUDA trajectory parity: `--j 1` and `--j 4` produced **bit-for-bit identical STAR trajectories** (`0.000e+00` px difference).

### Numerical Comparison Against CPU Synthetic Baseline
Comparing native CUDA execution against the committed CPU reference (`test-data/synthetic/expected/`):
- Image Max Pixel Difference: `1.473312e+00`
- Image RMSE: `6.730821e-03`
- Shift Max Difference: `3.200000e-04 px`
- Shift RMSD: `1.692631e-04 px`

In accordance with strict policy ("preserve all missing native/science cases UNRUN, no relaxed gates"), the exact 0.0 tolerance was **not relaxed**. The difference between CUDA single-precision resident pipeline and CPU FFTW3 baseline is recorded as an exact numerical property rather than smoothed over.

---

## 5. Scope and Limits

1. **Whole-Application Performance**:
   Whole-application wall-clock gains remain unproven. Paired timings on the 24-movie tutorial dataset (Job 3510657) showed 33.99s baseline vs 31.31s candidate (7.9% in an n=1 run), with historical 6-pair median speedup of ~0.45s (~1.4%). While patch alignment stage time decreased ~47% (1.60s -> 0.85s), the actual kernel computation speedup was ~5% (147ms -> 140ms), with the remainder attributable to reduced staging overhead.
2. **Error Classification and Production State**:
   All production kernels and session logic remain frozen. Reliability contracts, retry policies, and error classifications belong to #69.
3. **PR and Issue Status**:
   This report provides the review fix and evidence for PR #93 and Issue #77. In accordance with instructions, no PR merge and no issue closure has been performed.
