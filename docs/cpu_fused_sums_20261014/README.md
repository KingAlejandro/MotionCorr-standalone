# CPU fused unweighted sums experiment, 2026-10-14

Stacked on #178 (`e8f3eb8ea6165edae73613751df5a2e92ff4f955`), refs #10. Separate from full-frame FFT plans, huge pages and dose-weighting experiments.

The streamed reconstruction caller now adds its stored float scratch pixel to the total and selected even/odd product in one OpenMP pixel loop. This removes a second scratch scan and makes the split addition parallel. The total-only path retains its original loop. Frame order, selected-frame parity, model time, interpolation arithmetic and its intermediate float store remain unchanged. See [design](design.md).

## Verification

Fresh GCC 13.3.0 CPU Release build, FFTW 3.3.10, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, same current dependency paths as the main reference build. No fast-math. Production, wrapped focused test and unwrapped benchmark compile successfully. [Configure](configure.log), [build](build.log), [binary hashes and environment](environment.json).

- **10/10 relevant CTests pass**: CpuUnweightedStream, PatchRetryState, RunnerInterpolateRecenter, SyntheticRegression, RunnerLateBin, RunnerExportedUnits, StageProfile, RunnerModelParser, MicrographModelBounds and RunnerInterpolateShifts. [Log](focused-ctest.log), [detailed assertions](focused-ctest-detail.log).
- The focused test covers **288 cases**, comparing the actual production caller against both original full-stack interpolation plus ascending sums and a frozen #178 separate-scan caller. Shapes include a 65-wide vector tail, j1/j4, 1/2/7/32 frames, null/polynomial/general models and all four optional split-pointer combinations. Existing float-rounding, model-time, immutable-alias and GNU/ELF one-frame-allocation witnesses remain active.
- **Known-motion aggregate PASS**. All three gating cases pass. The inherited `km_local_noisy` characterization accuracy FAIL remains visible and is not reclassified. Applied-image, thread and dose invariance checks pass. [Aggregate](known-motion.json), [log](known-motion.log).
- **12 complete output-tree comparisons against #178 pass**, containing **40 canonical MRC/STAR file pairs**. Existing strict comparison normalizes only the writer clock and each output root; PDFs are inventoried, timing logs excluded. No numerical tolerance relaxed. [Comparisons](known-product-identity.json).

Verification ran while another isolated worktree compiled, so elapsed test times are not performance evidence. Native CI has not yet been checked on this experiment. No CUDA execution occurred.

## Performance

Benchmarks have not run yet. `cpu_fused_sums_bench` provides an unwrapped, actual-production reconstruction-stage comparison against the frozen #178 caller. It alternates paired order, excludes one warmup pair, initializes outputs outside timing, and checks all three sum images bitwise after every pair. Intended measurements are tutorial geometry, polynomial model j1/j4 plus null model j4, six measured pairs each. Representative unprofiled complete jobs and peak RSS are separate checks. No whole-movie speedup claim is made.

The current host has an 8-CPU cgroup quota and 8 GiB memory limit. Its mounted `/proc` view does not match child PID namespaces, so per-PID ownership and physical-host isolation cannot be certified. Any fallback timings must retain this limitation and remain distinct from clean cpu64/SCARF measurements.
