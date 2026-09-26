# Issue 33: Metal Synthetic Regression Harness Execution and Evidence Contract

## 1. Context and Problem Statement

Following the development pattern of CUDA Issue #27 / PR #28, Issue #33 establishes a fast, trustworthy synthetic CPU-versus-Metal regression harness for MotionCorr on Apple silicon.

The harness evaluates:
1. **CPU versus Known Shifts**: Ground-truth recovery on deterministic synthetic fixtures.
2. **Metal versus Known Shifts**: Ground-truth recovery on deterministic synthetic fixtures.
3. **Metal versus CPU Parity**: Numerical equivalence under declared relaxed Gate 2 tolerances.

A numerical match alone cannot establish that a Metal GPU kernel actually executed; a CPU executable, mock fallback, or CPU wrapper could otherwise produce identical outputs and masquerade as an accelerated backend. Furthermore, stale outputs from previous runs must never be allowed to pass a new run.

---

## 2. Hardware and Execution Evidence Contract

For each requested Metal movie execution, the harness strictly requires:
1. **Explicit Device Selection and Startup Marker in `run.log`**:
   The process log must confirm that Metal acceleration was initialized on a named Metal device (e.g., `Using Metal acceleration on device [Apple M4 Pro]` or `Using Metal device: <name>`), matching the requested or auto-detected Metal device.
2. **Completed Metal Profile in the Movie Log (`<movie_base>.log`)**:
   The movie log must contain a `[Metal Global Alignment Profile]` block with an explicit, finite, non-negative total execution time:
   `Total Metal alignment time: <ms> ms`.
3. **Fresh Output Directories**:
   The harness mandates fresh run directories. If any case output directory already exists and contains prior files or directories, the harness immediately aborts before launching any processes with exit code 2.
4. **Diagnostic Artifact Retention on Failure**:
   If any process fails (non-zero exit), any file is missing, coverage is incomplete, pixels are corrupted, or numerical tolerances are exceeded, the harness preserves all output directories (`cpu/` and `metal/`), writes diagnostic failure reasons, and exits non-zero.

---

## 3. Numerical Acceptance Tolerances (Relaxed Gate 2)

The harness reuses `tools/compare_motioncorr.py` without creating duplicate metric definitions. In accordance with `docs/reference_gates.md`, an overall `PASS` requires:

| Metric | Threshold | Scope |
|---|---|---|
| Process Exits | `0` (CPU and Metal) | Both processes must exit successfully |
| Output Dimensions | `nx=128, ny=128, nz=1`, `mode=2` (float32) | Corrected MRC shape and datatype |
| Coverage | `COMPLETE` | Both MRC and STAR outputs present and evaluated |
| Trajectory Coordinate RMS Error | $\le 0.020\text{ px}$ | Per-frame shift discrepancy |
| Trajectory Max Frame Shift | $\le 0.050\text{ px}$ | Maximum single-frame shift discrepancy |
| Corrected Image Absolute RMSE | $\le 0.020$ | Pixel-wise root mean squared error |
| Corrected Image Relative RMSE | $\le 0.001$ ($0.1\%$) | Relative image error vs reference dynamic range |
| Corrected Image Max Pixel Error | $\le 5.0$ | Peak absolute difference across all pixels |
| Static STAR Metadata | $= 0$ differences | Unaltered micrograph metadata |
| Ground-Truth Shift Recovery | $\text{RMS} \le 0.15\text{ px}$, $\text{Max} \le 0.25\text{ px}$ | Accuracy against known synthetic shifts |

**Strict Rule**: Missing metrics are never substituted with 0.0. If any metric cannot be computed or parsed, the harness records an error and marks the case as `FAIL`.

---

## 4. Relationship to Issues #29, #30, #32, and #34

- **Issue #29**: Master tracking issue for the Metal backend.
- **Issue #30**: Opt-in macOS build wiring, CLI flags, and device selection.
- **Issue #32**: Global alignment Metal compute kernels.
- **Issue #33 (This Track)**: Harness, failure suite, and verification contracts.
- **Issue #34**: Full 24-movie dataset numerical validation and end-to-end benchmark.

A synthetic global-alignment `PASS` on $128 \times 128 \times 8$ fixtures validates global alignment kernel parity with local patches disabled (`--patch_x 1 --patch_y 1`). It does **not** substitute for 24-movie full-dataset acceptance under Issue #34.

Until Issue #32 provides a runnable Metal global alignment backend, positive Metal validation is marked **PENDING**, while the harness infrastructure, verification suite, and negative failure modes are verified on Apple silicon.
