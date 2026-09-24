# Synthetic CPU-versus-CUDA Regression Harness

This document describes the fast, trustworthy synthetic regression harness for verifying MotionCorr CPU-versus-CUDA parity on deterministic synthetic fixtures with known ground truth shifts ([Issue #27](https://github.com/KingAlejandro/MotionCorr-standalone/issues/27)).

## Overview

The regression harness executes single-threaded CPU (`--use_own --j 1`) and CUDA global alignment (`--use_own --j 1 --gpu <id>`) with:
- Identical random seeds (`--seed 20260923`)
- Local patches disabled (`--patch_x 1 --patch_y 1`) to cleanly isolate global alignment
- Isolated temporary output directories for each implementation
- Automated parity and ground-truth recovery checks using `tools/compare_motioncorr.py`

The harness executes in seconds (< 1 minute) on the tested A100 and can be run after CUDA changes on a GPU host.

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

When supplying `--output-dir`, use a fresh directory. The harness rejects an existing case directory with artifacts so an earlier MRC, STAR, or CUDA profile cannot satisfy a new run.

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
- **CUDA execution**: The process log must name the requested GPU, and the movie log must contain a completed CUDA global-alignment profile with numeric total time. Both markers are recorded in the JSON report.

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

## Verified hackathon A100 run — 2026-09-24

This run used the PR #28 source after integrating PR #25 head `7a794dc9d526739b4c8c78308c9b39385369d1fd` and its CPU determinism fix. Validated commit: `5e218d181a51e54fc0c20dbaa7442aef8a21e94f`; source tree: `9c247ac0154506afe685c1e2c136e5af7098edbc`. CPU and CUDA binaries were built from this worktree with:

```bash
cmake -S . -B build-cpu -DCUDA=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build-cpu --parallel 16
cmake -S . -B build-cuda -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DCMAKE_BUILD_TYPE=Release
cmake --build build-cuda --parallel 16
```

The exact measured command, run from `/home/alex/MotionCorr-pr28-verified`, was:

```bash
mkdir -p evidence/pr28-a100-final
/usr/bin/time -v python3 tools/run_cuda_synthetic_regression.py \
  --cpu-bin build-cpu/motioncorr --cuda-bin build-cuda/motioncorr \
  --gpu 2 --include-subpixel --python /home/alex/mc-env/bin/python3 \
  --output-dir evidence/pr28-a100-final \
  --json-out evidence/pr28-a100-final/report.json \
  > evidence/pr28-a100-final/harness.stdout.log \
  2> evidence/pr28-a100-final/time.log
```

Host `4-gpu-vm`: Linux 6.8.0, NVIDIA A100 80 GB PCIe device 2, driver 570.86.10, CUDA compiler 12.8.61 (`/usr/local/cuda-12.8/bin/nvcc`), GCC 13.3.0, CMake 3.28.3, Python 3.12.3, NumPy 2.5.3. CPU binary SHA256: `704b690d9de362f1edef17e7f44db203b63187bd4dff0a09cec9b1791d089fcf`; CUDA binary SHA256: `e33435262270f9f6b25800dcdf8062be0337fbe2435487609172b608b3a0c6b6`.

| Fixture | CPU/CUDA exit | CUDA proof | CPU/CUDA ground-truth RMS (px) | CUDA vs CPU trajectory RMS (px) | Image RMSE | Relative image RMSE | Gate 2 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Integer shifts, 128 × 128 × 8 | 0 / 0 | Device 2 + completed profile | 0.070699 / 0.070905 | 0.002280 | 0.019158 | 0.000298 | PASS |
| Subpixel shifts, 128 × 128 × 8 | 0 / 0 | Device 2 + completed profile | 0.069950 / 0.070552 | 0.002115 | 0.018612 | 0.000290 | PASS |

Both fixtures had complete MRC and STAR coverage, zero static STAR differences, the expected 128 × 128 × 1 float32 corrected output, and no missing metrics. Maximum frame-shift errors were 0.004220 and 0.003689 px; maximum absolute pixel errors were 0.121765 and 0.115601. All were within the declared Gate 2 limits. The harness reported **2/2 PASS** in 3.8715 s; `/usr/bin/time -v` measured 4.01 s wall time and exit 0. The [machine-readable report](synthetic_cuda_regression_a100_2026-09-24.json), [harness output](benchmark_logs/pr28_a100_2026-09-24/harness.stdout.log), [time log](benchmark_logs/pr28_a100_2026-09-24/time.log), and [CUDA movie logs](benchmark_logs/pr28_a100_2026-09-24/) preserve the measured result and device markers.

The eight-case verification suite, invoked as `python3 tools/test_cuda_synthetic_regression.py --cpu-bin build-cpu/motioncorr --cuda-bin build-cuda/motioncorr --gpu 2`, passed in 15.64 s with exit 0. Its [output](benchmark_logs/pr28_a100_2026-09-24/negative-suite.stdout.log) includes a real-CUDA positive run, real-CUDA image and coverage failures, and rejection of a CPU wrapper and reused output directory.

This is a **small synthetic global-alignment** result with local patches disabled. It does not close PR #25's experimental 24-movie numerical gate: that separate rerun remains **0/24 PASS** because relative corrected-image RMSE exceeded 0.001 on every movie. See the [CUDA validation report](cuda_global_alignment_validation.md).
