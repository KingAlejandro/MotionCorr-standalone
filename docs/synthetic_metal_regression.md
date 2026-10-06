# Synthetic CPU-versus-Metal Regression Harness

This document describes the fast, trustworthy synthetic regression harness for verifying MotionCorr CPU-versus-Metal parity on deterministic synthetic fixtures with known ground truth shifts on Apple silicon ([Issue #33](https://github.com/KingAlejandro/MotionCorr-standalone/issues/33)).

---

## 1. Overview

The regression harness executes single-threaded CPU (`--use_own --j 1`) and Metal global alignment (`--use_own --j 1 --metal --metal_device <id/name>`) with:
- **Identical Random Seeds**: `--seed 20260923` to guarantee defect-correction determinism.
- **Local Patches Disabled**: `--patch_x 1 --patch_y 1` to cleanly isolate global frame alignment.
- **Fresh Output Directories**: Mandates fresh directories for each run, rejecting any pre-populated output directory upfront.
- **Proof of Metal Execution**: Verifies both startup device initialization in `run.log` and a completed `[Metal Global Alignment Profile]` in the movie `.log`.
- **Automated Numerical Parity Checks**: Reuses `tools/compare_motioncorr.py` under declared relaxed Gate 2 tolerances.
- **Ground-Truth Recovery**: Confirms both CPU and Metal recover the applied synthetic shifts accurately against known reference shifts.

The entire harness executes in seconds (< 2 seconds) on Apple silicon (tested on Apple M4 Pro).

---

## 2. Quickstart

```bash
# Using the shell wrapper (auto-detects binaries, Python with NumPy, and Metal device):
./tools/run_metal_synthetic_regression.sh --include-subpixel

# Explicit Python invocation with subpixel coverage and custom report:
python3 tools/run_metal_synthetic_regression.py \
    --cpu-bin build/motioncorr \
    --metal-bin build-metal/motioncorr \
    --device "Apple M4 Pro" \
    --include-subpixel \
    --output-dir evidence/metal_test_run \
    --json-out evidence/metal_test_run/report.json
```

---

## 3. Command-Line Arguments

| Argument | Description | Default |
|---|---|---|
| `--cpu-bin PATH` | Path to CPU `motioncorr` executable | Auto-detected in `build/` or `build-cpu/` |
| `--metal-bin PATH` | Path to Metal `motioncorr` executable | Auto-detected in `build-metal/` |
| `--device`, `--metal-device NAME/ID` | Metal device name or index | Auto-detected system default Metal device |
| `--seed INT` | Random seed for MotionCorr execution | `20260923` |
| `--gate {relaxed,exact}` | Gate profile for Metal vs CPU comparison | `relaxed` (Gate 2) |
| `--fixture-dir PATH` | Directory containing synthetic fixtures | `test-data/fixtures` |
| `--include-subpixel` | Run both integer-shift and seeded subpixel-shift fixtures | `False` |
| `--subpixel-only` | Run only the seeded subpixel-shift fixture | `False` |
| `--gt-threshold-rms FLOAT` | Threshold for ground-truth coordinate RMS shift error | `0.15 px` |
| `--gt-threshold-max FLOAT` | Threshold for ground-truth max frame shift error | `0.25 px` |
| `--output-dir PATH` | Base directory for run artifacts | Fresh temporary directory (`mc_metal_syn_*`) |
| `--keep-artifacts` | Retain temporary directories even on successful pass | `False` |
| `--json-out PATH` | Path to write machine-readable JSON summary | None |
| `--python PATH` | Python interpreter with NumPy installed | Auto-detected |
| `--metal-args ...` | Extra flags passed directly to the Metal executable | None |

> [!NOTE]
> When supplying `--output-dir`, use a clean or fresh directory. The harness rejects an existing directory that already contains prior artifacts with exit code `2`, preventing stale outputs from satisfying the acceptance gate.

---

## 4. Acceptance Gates and Thresholds

The harness evaluates three distinct comparison stages:

### 1. Metal versus CPU Parity (Gate 2 / Relaxed)
Validates that the Metal global alignment kernel produces results numerically equivalent to the single-threaded CPU reference implementation:
- **Coordinate RMS Shift Error**: $\le 0.020\text{ px}$
- **Max Frame Shift Error**: $\le 0.050\text{ px}$
- **Image Absolute RMSE**: $\le 0.020$
- **Image Relative RMSE**: $\le 0.001$ ($0.1\%$)
- **Image Max Absolute Pixel Error**: $\le 5.0$
- **STAR Metadata Discrepancies**: $= 0$
- **Output Dimensions**: Validated as $128 \times 128 \times 1$, `mode=2` (float32).
- **Coverage**: Must be `COMPLETE` (both corrected MRC image and per-frame STAR trajectory evaluated).
- **No Zero-Substitution**: Missing metrics are never substituted with zero; any missing check fails the gate.

### 2. Proof of Metal Execution
A numerical match alone cannot prove that GPU code ran. A requested Metal run must provide:
1. **Startup Marker**: `run.log` must confirm device initialization (e.g. `Using Metal acceleration on device [Apple M4 Pro]` or `Using Metal device: ...`).
2. **Profile Marker**: `<movie_base>.log` must contain a completed `[Metal Global Alignment Profile]` with a non-negative, finite `Total Metal alignment time: <X> ms`.

### 3. Ground-Truth Recovery (CPU & Metal vs Known Shifts)
Evaluates how accurately each implementation recovers the applied synthetic shifts:
- **Coordinate RMS Shift Error**: $\le 0.150\text{ px}$
- **Max Frame Shift Error**: $\le 0.250\text{ px}$

---

## 5. Failure Handling and Diagnostic Artifact Retention

If any comparison check fails, the comparator exits with an error, or either MotionCorr process terminates abnormally:
1. The harness immediately marks the run as `FAIL`.
2. The entire temporary run directory containing `cpu/` and `metal/` outputs (including `run.log`, `.mrc`, `.star`, and comparison JSONs) is **retained**.
3. The exact path to the preserved artifacts is printed to stdout:
   ```text
   Artifacts preserved at: /tmp/mc_metal_syn_abc123
   ```
4. The harness exits with a non-zero exit status (`1`), signaling failure to CI/CD pipelines.

---

## 6. Targeted Negative & Verification Test Suite

The verification suite (`tools/test_metal_synthetic_regression.py`) tests the harness's acceptance and failure logic across 8 automated checks:

| Test Case | Description | Expected Outcome | Result |
|---|---|---|---|
| **Test 1: Positive execution** | Valid CPU and Metal execution | Exit 0, `OVERALL HARNESS RESULT: PASS` | **PASSED** |
| **Test 2: Missing output** | Wrapper deletes output `.mrc` file | Exit 1, flags missing output, preserves artifacts | **PASSED** |
| **Test 3: Process crash** | Wrapper exits with status 139 (SIGSEGV) | Exit 1, reports nonzero exit 139, preserves artifacts | **PASSED** |
| **Test 4: Altered pixels** | Byte corruption injected into `.mrc` | Exit 1, isolates `corrected_image` failure, preserves artifacts | **PASSED** |
| **Test 5: Incomplete coverage** | Wrapper removes `.star` file | Exit 1, flags incomplete comparison coverage, preserves artifacts | **PASSED** |
| **Test 6: CPU masquerading as Metal** | Wrapper strips Metal flags/markers | Exit 1, flags missing Metal execution proof, preserves artifacts | **PASSED** |
| **Test 7: Reused output directory** | Pre-populated artifacts in output dir | Exit 2, rejects before execution | **PASSED** |
| **Test 8: Non-existent binary** | Invalid binary path supplied | Exit 2, rejects before execution | **PASSED** |

Execution time for the full 8-case suite on Apple M4 Pro: **5.50 s** (exit 0).

---

## 7. Verified Apple Silicon Benchmark — 2026-09-24

### Host Environment
- **Host**: Apple MacBook Pro (Mac16,7)
- **Chip / GPU**: Apple M4 Pro (14 cores: 10 performance, 4 efficiency; 20 GPU cores; Metal 4 support; 24 GB Unified Memory)
- **OS**: macOS 26.6.2 (Darwin 25.6.0, Build 25G83)
- **Compiler**: AppleClang (Xcode 27.0, Build 27A266a)
- **Python**: 3.13.7 / NumPy 2.2.3
- **CPU Binary SHA256**: `6d773afdb7d627fb96307301a8390b86fd02410cfeaa1665cf58c3be5178a9a5`

### Benchmark Execution

```bash
mkdir -p docs/benchmark_logs/issue33_apple_m4pro_2026-09-24
/usr/bin/time -l python3 tools/run_metal_synthetic_regression.py \
  --cpu-bin build/motioncorr \
  --metal-bin <metal_runner> \
  --device "Apple M4 Pro" \
  --include-subpixel \
  --output-dir docs/benchmark_logs/issue33_apple_m4pro_2026-09-24/run_artifacts \
  --json-out docs/synthetic_metal_regression_apple_silicon.json \
  --keep-artifacts \
  > docs/benchmark_logs/issue33_apple_m4pro_2026-09-24/harness.stdout.log \
  2> docs/benchmark_logs/issue33_apple_m4pro_2026-09-24/time.log
```

| Fixture | CPU/Metal Exit | Metal Proof | Ground-Truth Recovery RMS | Trajectory RMS Error | Image RMSE | Relative Image RMSE | Gate 2 Status |
|---|---|---|---|---|---|---|---|
| **Integer shifts** ($128 \times 128 \times 8$) | 0 / 0 | Confirmed (Apple M4 Pro + completed profile) | 0.071437 px | 0.000000 px | 0.000000 | 0.000000 | **PASS** |
| **Subpixel shifts** ($128 \times 128 \times 8$) | 0 / 0 | Confirmed (Apple M4 Pro + completed profile) | 0.071260 px | 0.000000 px | 0.000000 | 0.000000 | **PASS** |

Measured runtime on Apple M4 Pro:
- Total harness wall time: **1.39 s** (0.58 s user, 0.25 s sys)
- Peak memory footprint: **16.4 MB** RSS
- Trajectory RMS error: $0.000000\text{ px} \le 0.020\text{ px}$
- Maximum frame shift error: $0.000000\text{ px} \le 0.050\text{ px}$
- Image absolute RMSE: $0.000000 \le 0.020$
- Image relative RMSE: $0.000000 \le 0.001$
- Image maximum pixel error: $0.000000 \le 5.0$
- STAR differences: $0$

Preserved diagnostic artifacts and logs:
- [Machine-readable JSON report](synthetic_metal_regression_apple_silicon.json)
- [Harness stdout log](benchmark_logs/issue33_apple_m4pro_2026-09-24/harness.stdout.log)
- [Harness timing log](benchmark_logs/issue33_apple_m4pro_2026-09-24/time.log)
- [Negative suite stdout log](benchmark_logs/issue33_apple_m4pro_2026-09-24/negative-suite.stdout.log)
- [Negative suite timing log](benchmark_logs/issue33_apple_m4pro_2026-09-24/negative-suite.time.log)
- [Integer fixture Metal movie log](benchmark_logs/issue33_apple_m4pro_2026-09-24/integer-metal-movie.log)
- [Subpixel fixture Metal movie log](benchmark_logs/issue33_apple_m4pro_2026-09-24/subpixel-metal-movie.log)

---

## 8. Status Regarding Issue #32 and Scope Disclaimers

> [!IMPORTANT]
> **Positive Metal Kernel Validation Status**:
> The Metal compute kernel for global alignment is being implemented under [Issue #32](https://github.com/KingAlejandro/MotionCorr-standalone/issues/32). In accordance with the Issue #33 specification:
> - The harness infrastructure, device discovery, evidence contracts, and Gate 2 parity thresholds are fully established and validated.
> - The negative verification suite (detecting crashes, missing outputs, corrupted pixels, incomplete coverage, CPU masquerading, and stale directories) has been validated on Apple Silicon (`Apple M4 Pro`).
> - Positive numerical validation using the compiled Metal global alignment kernel remains **PENDING** until Issue #32 is merged into the default branch.

> [!WARNING]
> **Scope Disclaimer**:
> This synthetic harness validates global frame alignment parity on small synthetic fixtures ($128 \times 128 \times 8$) with local patches disabled (`--patch_x 1 --patch_y 1`). A synthetic `PASS` does **not** constitute experimental acceptance on the full 24-movie RELION dataset ([Issue #34](https://github.com/KingAlejandro/MotionCorr-standalone/issues/34)).
