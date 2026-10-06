# Global-frequency dependency experiment

Related: issue #142. Base: `6c87441d3e44e977994bd26175601092cc344a21`.

This is an opt-in dependency experiment, not a production optimization or a
measured speedup. The normal executable has no CLI or environment switch for it.
The experiment's build option is disabled by default. No numerical gate changes.

## Question

Can global alignment update only the Fourier samples consumed by correlation,
then reproduce the complete aligned movie by replaying the same phase sequence
on the remaining samples?

The current CUDA reference and correlation kernels read a fixed subset of each
full-resolution Fourier frame. The phase kernel nevertheless updates every
sample after every iteration. The experiment preserves full-size allocations,
the correlation estimator, peak search, convergence calculation, and FFT plans.
It changes when the complementary frequencies receive their phase updates.

At 3710 by 3838 pixels, B-factor 150, no early binning and automatic correlation
sizing, the current sizing rule gives a 972 by 972 correlation grid. Its stored
samples are approximately 6.65% of the full half-complex frame. This is a source
calculation, not measured traffic or a prediction of application speedup. This
prototype still retains the full Fourier allocation.

## Contract

1. Preserve original image dimensions independently of the selected support.
   Never call the existing estimator with the cropped dimensions as if they
   described the original image.
2. Select exactly the indices read by `computeReferenceKernel` and
   `computeCCFKernel`, including their positive midpoint row convention.
3. Preserve reference summation order, weights, FFT layout, peak tie behavior,
   frame-zero convention, relative shifts, and convergence threshold.
4. Record the actual normalized float phase inputs after each iteration.
   Reconstructing them from the accumulated trajectory can round differently.
5. Include the final executed iteration, whose phase update precedes the
   convergence check, including a call that exhausts its iteration limit.
6. Replay each recorded phase on the complementary frequencies in its original
   order, using the original phase arithmetic. Do not collapse phases into one
   accumulated shift or fuse the replay loop in this experiment.
7. Complete and check replay and resource cleanup before reporting successful
   execution. Numerical nonconvergence remains distinct from runtime failure.

The expected invariant is byte-identical complete Fourier payload, trajectory,
per-iteration control state, and convergence result within the same build and
device. CPU-versus-CUDA agreement is a different question.

## Why this is deliberately small

Separate replay launches perform essentially the same total high-frequency
work as the original implementation. They establish a dependency boundary. A
later performance experiment could keep a frequency value in registers while
replaying the sequence, but compiler contraction and instruction ordering would
need fresh exactness checks. Physical compaction is another separate change.

No product-plan extraction, reader change, defect RNG change, pool integration,
multi-GPU scheduler change, or default execution policy is included. Those
boundaries can build on a successful dependency proof without being prerequisites
for it.

## Acceptance and limitations

The native harness must compare the actual reference and experimental entry
points, every retained iteration field, and every final complex value. It must
include actual cropped support, full support, non-square geometry, multiple
weight/downsample settings, early convergence, iteration-limit exhaustion, frame
zero, and input/call isolation. A nontrivial complement must receive nonzero
shifts so an omitted replay cannot pass vacuously.

Comparison sensitivity controls that alter an in-memory result are distinct
from compiled implementation mutants that omit or corrupt replay. Native
acceptance requires the latter to fail for the intended numerical mismatch.
Neither compilation nor CPU tests establishes this CUDA invariant.

Input fixtures and output checks exercise this internal alignment boundary.
They do not establish whole-movie product equivalence, detector-sized throughput,
peak memory, or downstream scientific quality. Those become relevant before any
production integration or performance claim.

## Build and run

Use an allocated, otherwise idle CUDA device and retain its identity, driver,
toolkit, exact source revision, binary digest and complete output. Existing
cluster allocation/lock rules still apply.

```sh
cmake -S . -B build-frequency -DCMAKE_BUILD_TYPE=Release \
  -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON \
  -DMOTIONCORR_CUDA_FREQUENCY_EXPERIMENT=ON
cmake --build build-frequency --target cuda_frequency_replay --parallel 4
ctest --test-dir build-frequency -R '^CudaFrequencyReplay$' --output-on-failure
```

For retained native traces, binary/source identity and optional prebuilt mutant
controls, use a new output directory:

```sh
python3 tools/run_cuda_frequency_replay.py \
  --binary build-frequency/cuda_frequency_replay --output frequency-evidence
```

The runner accepts `--skip-replay-binary` and `--corrupt-replay-binary`. They must
be separately compiled actual-source variants. For the former, remove only the
block between `BEGIN GLOBAL FREQUENCY COMPLEMENT REPLAY` and its `END` marker.
For the latter, change the final `false` argument of that block's region-kernel
launch to `true`, which reapplies phases to support instead of the complement.
Build each in an isolated checkout with the same toolchain. Retain each source
patch and binary digest. An unrelated CUDA error, timeout or missing device is
not an accepted mutant rejection. This document does not claim either mutant
has been compiled or executed.

A successful native suite with either compiled mutant missing is recorded as
`INCOMPLETE` with exit code 2. Full `PASS` requires both mutants to be rejected
for the intended mismatch; runtime failures return 1. The manifest records
binary digests, device/runtime identity, the current source revision/diff and
relevant file hashes. Its run-time source snapshot is not proof that a supplied
binary was built from those files; retain the build commands with the evidence.

The index-support control can run without CUDA:

```sh
c++ -std=c++17 -O2 -I. tests/test_cuda_frequency_support.cpp -o /tmp/frequency-support
/tmp/frequency-support
```

The target is absent in ordinary builds. Enabling the option with `CUDA=OFF`
is a configuration error. A native test without a usable GPU fails rather than
reporting a passing numerical result.

CI compiles both the ordinary CUDA build and the opt-in target. Its hosted
runner has no GPU; its only executed new test enumerates the support indices on
the host. It establishes compile/link and index coverage, not native equality.

## Recorded verification

See `verification.json` for the local checks and their limits. The existing 33
CPU tests passed. Independent host enumeration checked 726 geometries and
7,550,928 coordinates and rejected four support-boundary mutations. Experiment-
OFF preprocessed source/header tokens match the pinned base after source-line
numbers are normalized and includes are removed. Native CUDA equality, actual
compiled replay mutants, and performance remain unrun locally.

## Follow-on decisions

- If exactness fails, retain the first differing stage and sample, investigate
  indexing/code generation, and do not loosen the comparison.
- If it passes, separately evaluate fused per-pixel replay and physical support
  compaction against the same oracle before making a throughput claim.
- Full support has no complementary work to defer. It is an important control,
  not a case expected to benefit.
- A future reconstruction API will also need explicit correction realization
  and geometry/units. This experiment does not establish that saved global
  trajectories alone suffice for exact corrected-frame replay.
