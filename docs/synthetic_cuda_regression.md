# Synthetic CPU-versus-CUDA Regression Harness

This document describes the fast, trustworthy synthetic regression harness for verifying MotionCorr CPU-versus-CUDA parity on deterministic synthetic fixtures with known ground truth shifts ([Issue #27](https://github.com/KingAlejandro/MotionCorr-standalone/issues/27)).

## Overview

The regression harness executes single-threaded CPU (`--use_own --j 1`) and CUDA global alignment (`--use_own --j 1 --gpu <id>`) with:
- Identical random seeds (`--seed 20260923`)
- Local patches disabled (`--patch_x 1 --patch_y 1`) to cleanly isolate global alignment
- Isolated temporary output directories for each implementation
- Automated parity and ground-truth recovery checks using `tools/compare_motioncorr.py`

The harness executes in seconds (< 1 minute), making it ideal for continuous integration and pre-commit checks on GPU systems.

---

## Quickstart

```bash
# Using the shell wrapper (auto-detects binaries and python environment):
./tools/run_cuda_synthetic_regression.sh --gpu 1

# Explicit Python invocation with subpixel coverage:
python3 tools/run_cuda_synthetic_regression.py \
    --cpu-bin build-cpu/motioncorr \
    --cuda-bin build-cuda/motioncorr \
    --gpu 1 \
    --include-subpixel \
    --json-out docs/synthetic_regression_report.json
```

---

## Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `--cpu-bin PATH` | Path to CPU `motioncorr` executable | Auto-detected in `build-cpu/` or `build/` |
| `--cuda-bin PATH` | Path to CUDA `motioncorr` executable | Auto-detected in `build-cuda/` or `build/` |
| `--gpu INT` | CUDA GPU device ID | `0` (use `1` on multi-GPU hosts when GPU 0 is occupied) |
| `--seed INT` | Random seed for MotionCorr execution | `20260923` |
| `--gate {relaxed,exact}` | Gate profile for CUDA vs CPU comparison | `relaxed` (Gate 2) |
| `--fixture-dir PATH` | Directory containing synthetic fixtures | `test-data/fixtures` |
| `--include-subpixel` | Run both integer-shift and seeded subpixel-shift fixtures | `False` |
| `--subpixel-only` | Run only the seeded subpixel-shift fixture | `False` |
| `--gt-threshold-rms FLOAT` | Threshold for ground-truth coordinate RMS shift error | `0.15 px` |
| `--gt-threshold-max FLOAT` | Threshold for ground-truth max frame shift error | `0.25 px` |
| `--output-dir PATH` | Base directory for run artifacts | Temporary directory (`mc_cuda_syn_*`) |
| `--keep-artifacts` | Retain temporary directories even on successful pass | `False` |
| `--json-out PATH` | Path to write machine-readable JSON summary | None |
| `--python PATH` | Python interpreter with NumPy installed | Auto-detected |

---

## Acceptance Gates and Thresholds

The harness evaluates three distinct comparisons:

### 1. CUDA versus CPU Parity (Gate 2 / Relaxed)
Validates that the CUDA global alignment kernel produces results numerically equivalent to the single-threaded CPU reference implementation:
- **Coordinate RMS Shift Error**: $\le 0.020\text{ px}$
- **Max Frame Shift Error**: $\le 0.050\text{ px}$
- **Image Absolute RMSE**: $\le 0.020$
- **Image Relative RMSE**: $\le 0.001$ ($0.1\%$)
- **Image Max Absolute Pixel Error**: $\le 5.0$
- **STAR Metadata Discrepancies**: $= 0$
- **Coverage**: Must be `COMPLETE` (both corrected MRC image and per-frame STAR trajectory evaluated). Missing metrics are never substituted with zero.

### 2. Ground-Truth Recovery (CPU vs Known Shifts & CUDA vs Known Shifts)
Evaluates how accurately each implementation recovers the applied synthetic shifts. Peak-finding precision on noisy $128 \times 128$ micrographs has finite accuracy (~0.07 px RMS), so ground-truth acceptance uses declared thresholds:
- **Coordinate RMS Shift Error**: $\le 0.150\text{ px}$
- **Max Frame Shift Error**: $\le 0.250\text{ px}$

---

## Failure Handling and Artifact Retention

If any comparison check fails, the comparator exits with an error, or either MotionCorr process terminates abnormally:
1. The harness immediately marks the run as `FAIL`.
2. The entire temporary run directory containing `cpu/` and `cuda/` outputs (including `run.log`, `.mrc`, `.star`, and comparison JSONs) is **retained**.
3. The exact path to the preserved artifacts is printed to stdout:
   ```text
   Artifacts preserved at: /tmp/mc_cuda_syn_abc123
   ```
4. The harness exits with a non-zero exit status (`1`), signaling failure to CI/CD pipelines.
