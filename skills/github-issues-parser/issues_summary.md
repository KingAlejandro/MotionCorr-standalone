# GitHub Issues Summary: MotionCorr-standalone

Total entries: **18**

## Overview

- **Open Issues:** 15
- **Closed Issues:** 0
- **Pull Requests (Merged/Closed):** 3

## Detailed Issue Breakdown

### [PR] #1: Add GitHub issue agents in hackathon Google Cloud (PR - CLOSED)
- **Type / State:** `PR` | `closed`
- **Labels:** `agent:review`
- **Estimated Difficulty:** **Medium** (2.5/5)
  - *Rationale:* Standard development and validation task.

### [PR] #2: Add RELION SPA tutorial test dataset (PR - CLOSED)
- **Type / State:** `PR` | `closed`
- **Estimated Difficulty:** **Medium** (2.5/5)
  - *Rationale:* Standard development and validation task.

### [PR] #3: Document SPA tutorial movie parity (PR - CLOSED)
- **Type / State:** `PR` | `closed`
- **Estimated Difficulty:** **Low** (1.5/5)
  - *Rationale:* Documentation, license notices, clean checkout validation, and release checklist definition.

### [OPEN] #4: Define the reference outputs and numerical acceptance gates (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`
- **Priority:** `P0`
- **Dependencies:** `None; can start immediately.`
- **Owner Fit:** scientific validation
- **Estimated Difficulty:** **Medium** (2.5/5)
  - *Rationale:* Establishing baseline ground truth fixtures, normalization scripts, and numerical parity metrics.
- **Objective:** Record the exact RELION 5.1 commit, compiler, inputs, command lines, gain file, output normalization, and comparison tools for the existing synthetic and tutorial movie runs. Turn the one-thread macOS comparison into a reproducible reference bundle without committing the multi-gigabyte movies.
- **Key Acceptance Criteria:**
  - A small synthetic fixture and its generation recipe are versioned; the experimental dataset is referenced by the existing release and checksums.
  - A comparison command reports motion trajectory error, corrected-image RMSE/max error, STAR-field differences, runtime, peak memory, and exit status.
  - The existing exact one-thread CPU parity cases pass; header timestamps and paths are explicitly normalized.
  - Proposed numerical tolerances for new backends are written down and approved before claiming their parity; exact CPU reference values remain visible.

### [OPEN] #5: Build and smoke-check standalone MotionCorr on Linux CI (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:integration`
- **Priority:** `P0`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** build/CI engineer
- **Estimated Difficulty:** **Low-Medium** (2/5)
  - *Rationale:* Setting up GitHub Actions Linux runner with CMake, FFTW3, OpenMP, LibTIFF, and running a smoke fixture.
- **Objective:** Add a Linux build workflow for the existing CMake target with FFTW, OpenMP, TIFF/PNG/JPEG, and zlib. Keep the experimental full-size tutorial data outside the routine CI job.
- **Key Acceptance Criteria:**
  - Clean Linux build completes in CI from main with dependency versions captured in the job log.
  - CLI help and a compact deterministic MRC or TIFF fixture run through the binary and produce a readable corrected MRC plus motion STAR.
  - The workflow fails on a nonzero process exit or missing/invalid outputs, and README includes Linux build instructions.

### [OPEN] #6: Compare all 24 RELION SPA tutorial movies against RELION 5.1 (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`
- **Priority:** `P0`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** scientific validation / data runner
- **Estimated Difficulty:** **Medium** (2.5/5)
  - *Rationale:* Automated dataset test harness running 24 RELION SPA tutorial movies and comparing STAR files and MRC RMSE against RELION 5.1.
- **Objective:** Extend the documented one-movie, one-thread comparison to all 24 compressed TIFF movies using the shared release and the same gain, 5 x 5 patches, dose weighting, and optics settings. Use the exact upstream commit in README as the comparator.
- **Key Acceptance Criteria:**
  - Run manifest records hashes, commands, versions, host, thread count, and per-movie success or failure.
  - For every movie, report trajectory differences, corrected-image RMSE and maximum error, and normalized STAR comparison; retain links to logs/artifacts.
  - Any nonmatching movie gets a reproducible case and a follow-up issue; do not silently raise tolerances.
  - Summary clearly distinguishes one-thread reproducibility from the known four-thread variation.

### [OPEN] #7: Diagnose four-thread output variation and define a deterministic mode (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`, `track:cpu`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** CPU numerical engineer
- **Estimated Difficulty:** **Medium-High** (3.5/5)
  - *Rationale:* Debugging non-deterministic OpenMP reductions, parallel FFTW plan concurrency, defect correction state, and floating-point associativity.
- **Objective:** The README reports a small trajectory/image difference on repeated four-thread tutorial-movie runs. Identify whether the variation comes from reduction order, shared random state in defect correction, FFT planning, or another stage; keep this issue focused on diagnosis and a minimal remedy.
- **Key Acceptance Criteria:**
  - A repeat-run script runs the same movie at 1 and 4 threads at least five times and reports trajectory and image dispersion.
  - The first stage that diverges is identified with evidence; any fix preserves the one-thread reference result.
  - If a deterministic mode is implemented, repeated four-thread runs give identical normalized outputs on the fixture; otherwise document a bounded residual and a follow-up fix issue.

### [OPEN] #8: Validate EER and compressed-MRC input paths with gain and frame grouping (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`, `track:integration`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** I/O specialist
- **Estimated Difficulty:** **Medium-High** (3.5/5)
  - *Rationale:* Falcon 4 EER event decoding/rendering, frame grouping, upsampling, and gain application across variable format edge cases.
- **Objective:** The CPU runner has separate EER rendering and compressed-MRC read paths in src/motioncorr_runner.cpp; these have not been covered by the documented MRC/TIFF parity runs. Exercise both without bundling restricted input files in Git.
- **Key Acceptance Criteria:**
  - A legal/shareable fixture or reproducible acquisition recipe exists for each format, with checksums and command lines.
  - At least one EER grouping/upsampling case and one compressed-MRC case produce valid motion STAR and corrected image.
  - Gain dimensions, first/last frame selection, and malformed/truncated input have explicit expected outcomes.
  - Compare with the same RELION 5.1 build where supported, and record numerical differences and any format limitations.

### [OPEN] #9: Profile CPU time and peak memory on representative movie sizes (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:cpu`
- **Priority:** `P0`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** performance engineer
- **Estimated Difficulty:** **Low-Medium** (2/5)
  - *Rationale:* Executing benchmark suite on representative movies, collecting stage timer metrics, RSS, and writing profile report.
- **Objective:** Use the existing stage timers in src/motioncorr_runner.cpp to establish a baseline before optimization. Cover global-only and 5 x 5 local alignment, 1 and 4 threads, and one full-size tutorial movie.
- **Key Acceptance Criteria:**
  - A repeatable benchmark recipe records hardware, build flags, input hashes, thread count, wall time, stage times, peak RSS, and output checksums.
  - Results identify the top three time and memory costs, including movie I/O, FFT/CCF, patch alignment, and dose weighting where applicable.
  - At least three repetitions per case are summarized with variability; no optimization claim is based on a single run.
  - A short ranked list recommends isolated optimization issues with expected benefit and risk.

### [OPEN] #10: Optimize one measured CPU bottleneck without changing scientific outputs (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:cpu`
- **Priority:** `P1`
- **Dependencies:** `#9 (profile), #4 (reference)`
- **Owner Fit:** CPU performance engineer
- **Estimated Difficulty:** **Medium** (3/5)
  - *Rationale:* Profiling-guided single bottleneck optimization in CPU runner (e.g. FFT buffer reuse, threading, SIMD) preserving bit-exact single-thread output.
- **Objective:** Take the highest-impact safe bottleneck from the profile, such as repeated FFT work, frame buffers, or patch CCF allocation. Make one localized change rather than rewriting the full runner.
- **Key Acceptance Criteria:**
  - Before/after benchmark uses identical host, compiler, input, and thread count, with at least three repetitions.
  - One-thread reference corrected pixels and motion STAR remain identical after allowed path/header normalization.
  - Peak RSS does not regress by more than 10 percent unless the speed/memory tradeoff is documented and accepted.
  - Measured improvement is reported with variability; if no meaningful improvement, close with evidence rather than a speed claim.

### [OPEN] #11: Characterize local patch fit failures and improve diagnostics (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`, `track:cpu`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** motion-model engineer
- **Estimated Difficulty:** **Medium** (3/5)
  - *Rationale:* Improving diagnostics, logging valid patch count and RMSD, robust fallback mechanism when 18-parameter polynomial fit diverges.
- **Objective:** The local path fits an 18-parameter third-order time/polynomial spatial model, skips nonconverged patches, and may fall back to global motion. Make these outcomes visible and test edge cases without changing the default model first.
- **Key Acceptance Criteria:**
  - Synthetic spatially varying trajectories include known recoverable motion and at least two underdetermined or bad-patch cases.
  - Per-movie log/STAR clearly exposes valid patch count, fit RMSD, and whether global fallback occurred.
  - Known-motion error and corrected-image quality are compared with the current baseline; no regression in the existing exact-parity cases.
  - Any proposed model change has a separate experiment/result and does not silently alter default behavior.

### [OPEN] #12: Add focused dose-weighting and output-contract checks (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:validation`, `track:integration`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** scientific I/O engineer
- **Estimated Difficulty:** **Medium** (3/5)
  - *Rationale:* Testing and validating critical dose-weighting curves (100/200/300 kV), odd/even sum outputs, and MRC/STAR output contracts.
- **Objective:** Exercise the doseWeighting path and output combinations in src/motioncorr_runner.cpp: weighted sum, optional nonweighted sum, odd/even sums, power spectrum, binning, and MRC/STAR metadata.
- **Key Acceptance Criteria:**
  - Small generated fixtures cover 100/200/300 kV handling, pre-exposure, first/last frame selection, and both dose-weighted and unweighted output.
  - For each documented combination, assert expected files, dimensions, pixel size, MRC mode, motion STAR fields, and finite pixel values.
  - One-thread CPU outputs retain RELION 5.1 parity on comparable settings; unsupported combinations fail with an actionable message.

### [OPEN] #13: Prototype Bayesian trajectory smoothing as an opt-in experiment (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:research`
- **Priority:** `P2`
- **Dependencies:** `#4 (reference), #11 (patch)`
- **Owner Fit:** algorithm researcher
- **Estimated Difficulty:** **High** (4/5)
  - *Rationale:* Mathematical formulation of state-space/Gaussian process trajectory smoothing, hyperparameter selection, and edge condition handling without degrading default output.
- **Objective:** Investigate temporal Bayesian smoothing of measured global or patch trajectories. This is distinct from RELION Bayesian polishing and must not be described as that feature. Start with an explicit noise/prior model and an offline trajectory experiment before wiring it into correction.
- **Key Acceptance Criteria:**
  - Design note states observation model, prior, inference method, boundary behavior, and compute/memory cost.
  - On simulated trajectories with known ground truth, report shift RMSE, bias, and oversmoothing against unsmoothed baseline across at least three noise/motion regimes.
  - On at least one experimental movie, compare corrected-image/STAR metrics and show plots of original and smoothed paths.
  - Any implementation is opt-in with default output unchanged; scientific go/no-go decision is recorded before promotion.

### [OPEN] #14: JAX proof of concept for global shift estimation (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:jax`, `track:research`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** JAX/array-computing engineer
- **Estimated Difficulty:** **Medium-High** (3.5/5)
  - *Rationale:* Vectorized global shift estimation, 2D FFT, Hermitian symmetry layout handling, and JAX JIT compilation parity.
- **Objective:** Implement a separate prototype of the global FFT, weighted cross-correlation, peak interpolation, and iterative Fourier shifting from alignPatch. Keep it outside the default C++ executable and document CPU/GPU device assumptions.
- **Key Acceptance Criteria:**
  - A reproducible entry point accepts a small reference fixture and writes per-frame shifts in a documented format.
  - Axes, FFT normalization, Hermitian layout, sign convention, and first-frame origin are explicitly checked against the C++ reference.
  - Shift error and output differences are reported on synthetic and one experimental movie using the acceptance metrics from the reference issue; any tolerance is declared before judging results.
  - Compilation time, steady-state runtime, transfers, and peak device memory are reported separately; decide whether to proceed to local-patch work.

### [OPEN] #15: JAX prototype for patch trajectories, polynomial fit, and dose weighting (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:jax`
- **Priority:** `P2`
- **Dependencies:** `#14 (jax_global), #4 (reference)`
- **Owner Fit:** JAX/array-computing engineer
- **Estimated Difficulty:** **High** (4/5)
  - *Rationale:* Array-oriented patch cross-correlations, polynomial surface fitting in JAX, JIT compilation tuning, and MRC/STAR I/O.
- **Objective:** Extend the JAX prototype through grouped patch CCF, local trajectory fitting/interpolation, dose weighting, and corrected-image output. Keep interoperability with the same movie input and STAR semantics, but allow a prototype-specific command line.
- **Key Acceptance Criteria:**
  - 3 x 3 and 5 x 5 patch cases, with and without dose weighting, run from a documented recipe.
  - Report per-frame and per-patch shift error, corrected-image RMSE/max error, fit/fallback decisions, runtime, compile time, and peak memory against the C++ reference.
  - No unapproved tolerance change; failed numerical gates are recorded rather than masked by visual similarity.
  - End with a clear maintainability/performance go-no-go recommendation.

### [OPEN] #16: CUDA proof of concept for global alignment kernels (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:cuda`, `track:research`
- **Priority:** `P1`
- **Dependencies:** `#4 (reference)`
- **Owner Fit:** CUDA engineer
- **Estimated Difficulty:** **High** (4/5)
  - *Rationale:* GPU global alignment kernels (batched cuFFT, cross-correlation, subpixel peak finding) requiring precise floating-point parity with C++ reference.
- **Objective:** Build a standalone GPU prototype for batched FFT/CCF, peak finding, and Fourier shift equivalent to the current global alignPatch path. Do not confuse the existing RELION external --use_motioncor2 wrapper with this implementation.
- **Key Acceptance Criteria:**
  - Build and run recipe names CUDA toolkit, GPU model, driver, and library versions; CPU-only builds still work.
  - Synthetic known-shift and one experimental movie report trajectory error and corrected-image metrics against the C++ reference, with GPU tolerance declared before the comparison.
  - Host-device transfer, kernel time, end-to-end time, and peak VRAM are separated, with at least three steady-state runs.
  - A documented go/no-go decision identifies the next kernel boundary and numerical risks.

### [OPEN] #17: CUDA patch alignment and dose-weighted correction prototype (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `track:cuda`
- **Priority:** `P2`
- **Dependencies:** `#16 (cuda_global), #4 (reference)`
- **Owner Fit:** CUDA engineer
- **Estimated Difficulty:** **Very High** (5/5)
  - *Rationale:* Requires custom CUDA kernels for grouped patches, 2D/3D spline/polynomial interpolation, FFT/CCF memory staging, and GPU dose weighting with numerical parity constraints.
- **Objective:** Extend the CUDA prototype to grouped local patches, polynomial motion fit/interpolation, dose weighting, and corrected sum. Keep CUDA optional and preserve the CPU path.
- **Key Acceptance Criteria:**
  - 3 x 3 and 5 x 5 patch cases run end to end on a named GPU, including a full-size experimental movie.
  - Patch convergence/fallback, trajectories, MRC pixels, STAR metadata, runtime, and peak VRAM are compared with CPU reference gates.
  - GPU out-of-memory or unsupported-device behavior is explicit and does not corrupt CPU output.
  - A maintained-build plan and performance-versus-complexity decision are recorded before making this a supported backend.

### [OPEN] #18: Document install, provenance, and a first standalone release checklist (Issue - OPEN)
- **Type / State:** `Issue` | `open`
- **Labels:** `documentation`, `track:integration`
- **Priority:** `P2`
- **Dependencies:** `#5 (linux), #6 (tutorial)`
- **Owner Fit:** release/documentation maintainer
- **Estimated Difficulty:** **Low** (1.5/5)
  - *Rationale:* Documentation, license notices, clean checkout validation, and release checklist definition.
- **Objective:** Prepare a usable installation and support story for the GPL-2.0-or-later standalone extraction, without implying it is an official RELION or MotionCor2 release. Cover macOS/Linux dependencies, supported inputs, outputs, and benchmark limitations.
- **Key Acceptance Criteria:**
  - Install instructions work from a clean checkout on the supported platforms, including a version/help check.
  - Source manifest and upstream commit remain traceable; third-party notices and dataset license/link are documented.
  - A release checklist names required CI, numerical-parity, real-movie, and artifact checks, plus known limitations.
  - Example command and expected output file inventory are validated against a released binary or reproducible build.
