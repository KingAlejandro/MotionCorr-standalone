# CPU fused unweighted sums experiment, 2026-10-14

Stacked on #178 (`e8f3eb8ea6165edae73613751df5a2e92ff4f955`), refs #10. Separate from full-frame FFT plans, huge pages and dose-weighting experiments.

The streamed reconstruction caller now adds its stored float scratch pixel to the total and selected even/odd product in one OpenMP pixel loop. This removes a second scratch scan and makes the split addition parallel. The total-only path retains its original loop. Frame order, selected-frame parity, model time, interpolation arithmetic and its intermediate float store remain unchanged. See [design](design.md).

**Outcome: do not promote this experiment.** All four reconstruction-stage timing verdicts are unresolved, with an unfavorable j1 median. The tutorial's strict full output-tree gate also **FAILS** because the control output directory contains an unexpected truncated temporary file of unproven origin. Published MRC/STAR equality is recorded separately from that failure. The PR remains draft; no merge recommendation is made.

## Verification

Fresh GCC 13.3.0 CPU Release build, FFTW 3.3.10, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`, same current dependency paths as the main reference build. No fast-math. Production, wrapped focused test and unwrapped benchmark compile successfully. [Configure](configure.log), [build](build.log), [binary hashes and environment](environment.json).

- **10/10 relevant CTests pass**: CpuUnweightedStream, PatchRetryState, RunnerInterpolateRecenter, SyntheticRegression, RunnerLateBin, RunnerExportedUnits, StageProfile, RunnerModelParser, MicrographModelBounds and RunnerInterpolateShifts. [Log](focused-ctest.log), [detailed assertions](focused-ctest-detail.log).
- The focused test covers **288 cases**, comparing the actual production caller against both original full-stack interpolation plus ascending sums and a frozen #178 separate-scan caller. Shapes include a 65-wide vector tail, j1/j4, 1/2/7/32 frames, null/polynomial/general models and all four optional split-pointer combinations. Existing float-rounding, model-time, immutable-alias and GNU/ELF one-frame-allocation witnesses remain active.
- **Known-motion aggregate PASS**. All three gating cases pass. The inherited `km_local_noisy` characterization accuracy FAIL remains visible and is not reclassified. Applied-image, thread and dose invariance checks pass. [Aggregate](known-motion.json), [log](known-motion.log).
- **12 complete output-tree comparisons against #178 pass**, containing **40 canonical MRC/STAR file pairs**. Existing strict comparison normalizes only the writer clock and each output root; PDFs are inventoried, timing logs excluded. No numerical tolerance relaxed. [Comparisons](known-product-identity.json).

Local verification ran while another isolated worktree compiled, so elapsed test times are not performance evidence. No CUDA execution occurred.

Native GitHub CI run **514 is GREEN on production commit `b780577`**: 53/53 Linux CTests, known-motion aggregate, canonical fixture, smoke/failure checks and CUDA compilation. This does not establish native GPU execution. [CI status](ci-code-status.json), [Linux log](ci-code-linux.log).

## Performance

The designated **64-core VM / cpu64** was unreachable from this session. The user subsequently authorized container timing as a fallback. All results below are from container `442a2f5ea6ec`, with an 8-CPU cgroup quota and 8 GiB limit. No cpu64 timing was collected or pooled with these results.

`cpu_fused_sums_bench` compares the actual production streaming reconstruction caller with the frozen #178 caller in one unwrapped executable. It includes interpolation, scratch lifetime and accumulation. Four fixed configurations each use six alternating measured pairs after one excluded warmup pair, with all three float sums checked bitwise after every pair. **All 28 warmup/measured pair checks pass.** No outlier was removed and no configuration was retried. [Raw JSONL and statistics](container-kernel/results.json), [runner](run_kernel.py).

All shapes are 3710×3838. Control / fused wall medians and paired-median differences are:

- 24 frames, polynomial, j1: **8.805 / 12.089 s**; paired median **+3.437 s**, interval **[-0.809,+8.146] s**. Four pairs are slower and two faster. Unresolved, with an unfavorable median.
- 24 frames, polynomial, j4: **4.683 / 4.317 s**; paired median **-0.388 s**, interval **[-6.564,+0.051] s**. Unresolved.
- 24 frames, null model, j4: **0.870 / 0.828 s**; paired median **-0.104 s**, interval **[-0.319,+0.320] s**. Unresolved.
- Seven frames, polynomial, j4: **2.094 / 1.680 s**; paired median **-0.299 s**, interval **[-0.782,+0.180] s**. Unresolved.

Intervals are the existing distribution-free **96.875%** paired-median intervals. They all include zero. Favorable j4 medians do not establish a speedup, and these stage times must not be applied to the earlier cpu64 47.7-second profile. The [compiled local loop](local-accumulation-assembly.txt) does reuse one scratch-vector load for the two float additions, but that mechanism does not establish a speed gain.

## Complete products and diagnostic memory

**Four synthetic even/odd output-tree comparisons PASS**, covering global/5x5 and j1/j4 with `--first_frame_sum 2 --last_frame_sum 8`: an odd seven-frame selection. Both arms request dose weighting, noDW and even/odd products.

**The tutorial 5x5 j4 strict complete-tree comparison FAILS.** Only the control output directory contains the unexpected temporary file `workspace/scratch/28038873ca11/data/.tutorial_noDW.mrc.128xfS`. It is 46,661,632 bytes with a 3710×3838×1 float header, shorter than the complete 56,956,944-byte MRC. Its metadata and hash are retained in [baseline-extra-file.json](container-products/baseline-extra-file.json). No file was removed, no comparator exclusion added, and neither arm was rerun. Its creator and cause are unproven; filename style alone does not establish an application or synchronization origin. All 12 common compared files have no differences, including all four published MRC products.

Across these five configurations and the 12 known-motion comparisons, **70 canonical published MRC/STAR file pairs match exactly**, under the existing writer-clock/output-root normalization. This subset equality does **not** turn the tutorial's full-tree FAIL into a pass. [Canonical hashes](canonical-product-hashes.json), [complete run records and strict results](container-products/results.json).

The single tutorial diagnostic pair took **48.127 / 41.962 s** and peaked at **3,265,712 / 3,265,640 KiB** RSS, control/fused. Peak RSS is essentially unchanged at about **3.114 GiB**. These are single, unwarmed diagnostic observations, with no whole-movie speed or memory verdict. The control is the existing #178 binary; the fresh candidate has identical Release arithmetic flags and resolves the same current runtime libraries, but historical dependency include prefixes differ. Source/build history is recorded in the manifest.

The product-check harness initially used a shallow split-file glob even though absolute inputs create nested output paths. It stopped after the first successful baseline movie. The recursive presence check was corrected, that completed run was retained, and the remaining fixed population resumed without rerunning a movie. The incident and original traceback are preserved in the run records.

The container's mounted `/proc` view does not match child PID namespaces. Physical-host isolation and per-PID ownership cannot be certified, so this is a bounded fallback comparison, not a clean mcprof verdict. The runner records actual hostname, CPU description, affinity, cgroup limits when exposed, PID-view consistency, source revision, executable hash, commands and OpenMP environment. Kernel timings ran under the shared lock with no local builds/tests, and complete jobs followed sequentially. Container and future VM evidence must remain separate.

## Portable cpu64 commands

Run these only in the agreed exclusive measurement lane. For a cpu64 comparison, build both complete-job arms on cpu64 with the same compiler and dependency installation; do not transfer container binaries. The experiment is draft PR #182, branch `perf/cpu-fused-unweighted-sums`; the production commit is `b780577fd0d62af41793555e0f06b94b49f2e6e9`. Its #178 control is `e8f3eb8ea6165edae73613751df5a2e92ff4f955`.

From the experiment checkout:

```sh
cmake -S . -B ../build-fused-sums-cpu64 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF
cmake --build ../build-fused-sums-cpu64 --target motioncorr cpu_unweighted_stream cpu_fused_sums_bench -j4
git worktree add --detach ../MotionCorr-fused-control e8f3eb8ea6165edae73613751df5a2e92ff4f955
cmake -S ../MotionCorr-fused-control -B ../build-fused-control-cpu64 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCUDA=OFF
cmake --build ../build-fused-control-cpu64 --target motioncorr -j4
```

After all builds and unrelated jobs have finished, use masks verified for the existing cpu64 measurements. The example uses CPUs 0 and 0-3; replace them if those are not the agreed masks or are outside the process affinity:

```sh
python3 docs/cpu_fused_sums_20261014/run_kernel.py --binary ../build-fused-sums-cpu64/cpu_fused_sums_bench --out docs/cpu_fused_sums_20261014/cpu64-kernel --cpus-j1 0 --cpus-j4 0-3
```

`run_kernel.py` refuses to run outside its expected host, default `small-refmac-machine` (cpu64). It accepts the equivalent fully qualified hostname. For the explicitly authorized container fallback, supply its observed hostname with `--expected-host` and use a separate `container-kernel` output directory. It takes the shared `/tmp/motioncorr-bench.lock`, refuses to time while compilers are visible, records affinity from a child in each requested lane, and uses the repository's paired-statistics implementation. Retain all raw JSONL pairs, including slow runs; do not remove outliers. Its measured control and production caller share one executable and compiler. Complete-movie product checks must request `--dose_weighting --save_noDW --even_odd_split` in both global and 5x5 modes so they exercise the fused split writes. Record exact input hashes, selection, commands and binary hashes separately from stage timings. A single whole-movie diagnostic pair does not establish a speedup.
