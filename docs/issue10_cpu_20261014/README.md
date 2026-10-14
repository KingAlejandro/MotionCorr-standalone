# Issue #10: CPU CCF plan reuse, 14 October 2026

## Continuation validation

The checkpoint below is retained as historical evidence. Clean reference and
candidate CPU builds, both lifetime controls and known-motion checks have now
run on a second host. The full suites share two PID-identity failures in this
environment; they are not waived. See [the continuation report](resume/README.md)
for exact results, source pins, the standard-kit limitation and fresh unprofiled
measurements. No further production optimization has been added.

## Checkpoint status — paused at user request

**Experimental checkpoint, not merge-ready.** Production candidate compiled
and completed 48 runs / 24 exact paired comparisons. The added CMake targets
and plan-lifetime tests have NOT been configured, compiled or run. Clean
reference/candidate CTests, known-motion scientific gates, unprofiled kit
runs and the refined lock-wait probe are UNRUN. The user requested a handoff
before these started. No benchmark, build or test process is left running.

## Scope and decision

Base: `116eb04ad359cd5bf789b28809fc2047ea155b9b`, verified against GitHub main.
The [latest bounded request](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6176234026)
selects CPU CCF inverse-plan/copy elimination. It supersedes the earlier
scope-completion-only handoff. No reconstruction streaming, compact patches,
CUDA, Metal, JAX, public options, numerical gates or accumulation order changed.
`github-context.json` records the issue discussion and all 30 open PR titles
at inspection. #22/#109 are historical profiling/scaling proposals, not new
speed evidence; #90 preprocessing, #111 global inverse elision, #154 stage
profiles, #165 profiling kit, #170 per-movie costs and #174/#176 report work
are already integrated. No competing CCF-plan PR was found.

## Change

Eight added production lines in `MotioncorrRunner::alignPatch` retain one
array-bound `NewFFT::FloatPlan` per OpenMP worker for one alignment call.
The arrays use the existing `fftw_malloc` allocator and never move/reshape
during execution. The plan is constructed against the actual pointers;
`FFTW_UNALIGNED` is not used. Each worker executes only its own plan. Plans
are destroyed before their arrays, including on early return/unwind.
Every CCF element is overwritten in the next frame's correlation loop, and
no subsequent consumer reads the destroyed spectrum. Inverse normalization
remains `FwdOnly` (no inverse rescaling); precision, frequency layout, flags,
peak-search order and frame accumulation are unchanged.

The existing plan abstraction creates both a forward and inverse plan once
per worker. The unused forward plan remains a small setup cost. This avoids
adding a new public FFT abstraction or a second ownership implementation.
There is no cross-patch/movie cache and no FFTW internal threading change.

## Reproduction and hardware

See `environment.json` for topology, flags and linked libraries. The guest
reports AMD EPYC 9V74, five virtual cores/threads and one NUMA node, but has
a four-CPU cgroup quota and 16 GiB memory limit. This is not evidence of five
isolated physical cores. GCC 14.2.0, CMake 3.31.6, FFTW 3.3.10, Release
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`, CUDA OFF, TIMING OFF. No fast-math.
Dependencies were extracted from Debian packages into `/workspace/cpu10/deps`
without root, paid compute or credentials. CMake configure/build logs are retained.

`run_pairs.py` is a bounded issue-specific recipe, not a replacement profiling
framework. It uses existing `--profile` and the existing strict header/text
normalizers, alternating AB/BA/AB, retaining all outputs, and checking every
MRC/STAR in every pair. It runs 512x512x16 seeded synthetic and 3710x3838x24
RELION tutorial inputs, global/no-dose and 5x5/dose+noDW+even/odd, j1 and j4,
three repetitions each. All numerical options and input/binary hashes are in
`results.json`. Tutorial/gain hashes match `docs/reference_gates.md`.

Thread settings: `OMP_DYNAMIC=false`, `OMP_PROC_BIND=close`,
`OMP_PLACES=cores`, `OMP_NUM_THREADS=1/4`, `OPENBLAS_NUM_THREADS=1`;
CPU masks 0 and 0-3 respectively. FFTW transforms are single-threaded inside
outer OpenMP loops. Page caches were not flushed; no cold-storage claim.

```sh
python3 docs/issue10_cpu_20261014/run_pairs.py \
  --base /workspace/cpu10/bin/base --candidate /workspace/cpu10/bin/candidate \
  --data /workspace/cpu10/data --out /workspace/cpu10/pairs
```

These profile passes report internal process run wall, process CPU, kernel
peak RSS and main-thread stage intervals. Four-thread CCF sub-stages cover
only the master worker, not summed worker time or total stage wall. Plan
setup moves outside the CCF inverse sub-stage, so that sub-stage alone is
not a full optimization cost comparison. The prepared but UNRUN standard profiling
kit command will measure unprofiled spawn-to-reap wall/CPU/RSS with warmups and lane
checks. Do not pool those two timing instruments.

## Diagnostic method

`probe.patch` applies only to the original baseline in a separate tree. It
expands the convenience inverse into the same copy, array-bound plan,
execution and destruction, accumulating worker-local monotonic intervals.
It also times entrance to the existing FFTW named critical sections. The
reported lock-wait interval includes timer/lock-entry overhead; it is not a
hardware-counter measurement. Copy time includes allocation; plan/destructor
time includes wait, so do not add wait again. Summed worker intervals may
overlap and are not elapsed job time. These diagnostic builds are never
used for before/after speed claims.

Early exploratory profiling overlapped initial tests/builds and is excluded
from the retained controlled timing results. The initial CTest attempt also
had a CMake PATH error and used a changing build tree; clean reference/candidate suites are still UNRUN. The preliminary run reported
51/52 passes and one missing-cmake PATH error, but is not a valid frozen-source
regression certification.

## Validation and limits

`CcfPlanLifetime` links the real runner with test-only FFTW wrappers. It
requires repeated inverse execution, matching bound pointers, unchanged
ESTIMATE flags, one worker per plan, no concurrent execution/destruction,
and zero live inverse plans at exit, with j1/j4 and global/5x5 fixtures.
`CcfPlanNoReuseControl` compiles the production caller with the old convenience
call restored; completed products plus the specific no-reuse failure are
required. These linker wrappers are ELF-only; ordinary numerical tests
remain portable. No runtime production switches or relaxed assertions.

macOS execution, CUDA execution, all 24 tutorial movies, other experimental
collections, EER/other detector geometries, SMT/NUMA scaling and high-thread
counts are UNRUN. The inherited macOS SyntheticRegression failure mentioned
in the issue is not waived or claimed fixed by Linux testing. There is no
new downstream scientific-equivalence claim.

## Completed paired profile measurements

Wall seconds: median [minimum, maximum], three matched repetitions per arm.
These are profiled runs; full-job speedup remains unconfirmed.

| Case | Baseline s | Candidate s |
|---|---:|---:|
| synthetic-global-j1 | 0.348 [0.345, 0.353] | 0.354 [0.352, 0.369] |
| synthetic-global-j4 | 0.316 [0.310, 0.324] | 0.314 [0.312, 0.330] |
| synthetic-patch_all-j1 | 0.610 [0.606, 0.620] | 0.589 [0.587, 0.613] |
| synthetic-patch_all-j4 | 0.469 [0.451, 0.469] | 0.462 [0.438, 0.520] |
| tutorial-global-j1 | 17.929 [17.609, 18.325] | 17.683 [17.662, 17.803] |
| tutorial-global-j4 | 5.878 [5.804, 6.222] | 6.321 [5.707, 7.199] |
| tutorial-patch_all-j1 | 40.497 [39.546, 42.485] | 39.721 [39.411, 39.805] |
| tutorial-patch_all-j4 | 14.736 [14.327, 15.404] | 13.057 [12.167, 14.383] |

All 108 paired MRC/STAR file comparisons are exact, including full MRC
headers after timestamp normalization and STAR path normalization. This is
60 MRC pairs and 48 STAR pairs. Complete per-file hashes are in `results.json`.
The one-thread tutorial 5x5 combined CCF inverse median fell from 373.77 to
241.83 ms (about 35%). This excludes setup now moved outside that sub-stage.
Larger unrelated stage variation prevents attributing full-job timing changes
to this optimization. Four-thread sub-stage values represent the master
worker only. Full raw stage and process CPU measurements are retained.

Tutorial peak RSS is about 4.06–4.39 GiB across configurations; no paired
RSS increase exceeds 1%. Synthetic reported RSS is a constant 149748 KiB,
likely limited by the Python launcher's inherited high-water mark; do not
interpret it as precise algorithm memory use. No memory-saving claim.

The preparatory scripts in this directory use absolute `/workspace/cpu10`
paths and need review/adaptation before use in another environment:
`run_checks.sh` (clean baseline/candidate builds, CTests, known-motion),
`run_kit.sh` (unprofiled matched j4 tutorial), `run_probe.sh` and
`build_probe.py` (diagnostic build and j1/j4 runs). They are **UNRUN drafts**;
inspect logs/exit codes rather than assuming they pass. `probe.patch` is the
unrun refined instrumentation, not part of production. The initial rough
probe ran with overlapping setup jobs and is not retained as timing evidence.

Workspace scratch `/workspace/cpu10` retains dependencies, immutable base and
candidate binaries, downloaded/hash-verified inputs, all output trees/logs,
a clean baseline source archive and the prepared probe tree. None of the
large inputs, binaries or output images is committed. Resume from this
checkpoint, first verify current GitHub activity, then finish validation;
do not broaden into streaming/compact-patch work or publish without permission.
