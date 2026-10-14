# Issue #10 continuation validation, 14 October 2026

## Scope and source

Continue the newest branch `perf/issue10-cpu-ccf-plan` at
`5ac83a4ab4384f514a1ec2062f98c449576f01be`. The production change is the
existing `135d546` per-worker, array-bound CPU CCF plan reuse. Unchanged main
`116eb04ad359cd5bf789b28809fc2047ea155b9b` is the reference. This continuation
adds evidence and a bounded measurement recipe; it does not add another
optimization or change CUDA, Metal, JAX, FFT normalization, accumulation order,
public options or numerical gates. No merge or issue closure is requested.

## Completed correctness checks

- Clean Release CPU-only builds of reference and candidate, GCC 13.3.0,
  CMake 3.28.3, FFTW 3.3.10. Identical `-O3 -DNDEBUG -std=gnu++17 -fopenmp`
  flags and linked libraries; no fast-math. See configure logs and
  `environment-resume.json` for the explicit shared TIFF/PNG/JPEG paths.
- Full CTest: reference **50/52**, candidate **52/54**. Both fail exactly
  `ProfilingKit` and `MultiGpuScheduling`. The former reports `unknown`
  instead of `own` for a descendant; the latter cannot establish the launcher's
  PID/birth identity. The failures reproduce on unchanged main. Logs retain
  all failing nested assertions; neither test is disabled or weakened.
- New `CcfPlanLifetime` and `CcfPlanNoReuseControl` both pass. These link the
  actual runner, run global/5x5 with j1/j4 and check bound pointers, flags,
  worker ownership, reuse and destruction. The compiled old-call mutant
  completes products then fails the reuse witness as intended.
- Reference and candidate known-motion aggregates both **PASS**. The existing
  `km_local_noisy` characterization accuracy failure remains **FAIL** in both
  JSON reports. The three gate-role cases pass; execution/backend, thread/dose
  invariance and applied-image witnesses pass. All **40 MRC/STAR products**
  across these runs match exactly after the existing timestamp/root
  normalization (`known-product-identity.json`). This is implementation and
  applied-field evidence, not a new downstream reconstruction claim.

## Environment and standard-kit limitation

This second host reports Intel Xeon Platinum 8573C, nine visible CPU IDs,
an eight-CPU cgroup quota and an 8 GiB memory limit. This differs from the
earlier AMD/GCC14 checkpoint; those timing populations must not be pooled.
The container's child PID namespace disagrees with the mounted `/proc` PID
view (`NSpid` exposes both IDs). A child reports a valid lane from inside
itself, but looking up that child by its namespace PID can address a different
host process or no process. The isolated `PidOwnership` recheck fails too.

The unmodified standard kit was attempted on a synthetic 5x5 j4 pair.
It preserved strict product identity but discarded both runs because its
observed payload affinity was `[8]`, the kit's own runner lane, rather than
`0-3`. `report.md`, `compare.json`, `runs.jsonl`, `identity.json` and
`provenance.json` retain that outcome: **zero clean retained rounds**.
It supplies no accepted speed verdict. No ownership or affinity assertion was
relaxed to turn this into a clean result.

`../run_unprofiled.py` is a separate, issue-specific fallback. It checks
`taskset` affinity using `sched_getaffinity(0)` inside a child, takes the
shared benchmark lock, rejects active compilers, records monotonic
spawn-to-reap wall and `wait4` CPU/RSS, warms both arms once, alternates AB/BA,
and compares the full product tree after every pair. Logs/PDF bytes have the
existing comparator exclusions; all MRC headers/pixels, STAR and EPS are
checked. It cannot certify per-PID `/proc` ownership, foreign lane usage,
physical-core isolation or turbo behavior and is **not a clean mcprof
verdict**. Raw measurements will be reported with that limitation.

## Measurement status

Fresh measurements are in progress. No full-job speed improvement is claimed
at this checkpoint. The retained first-host matrix already covers global and
5x5, j1/j4, dose/no-dose, noDW and even/odd on tutorial and synthetic inputs.
The continuation finishes its missing plan/lock diagnostic and unprofiled
tutorial j4 comparison, plus small synthetic j1/j4 controls; it does not
repeat the whole historical matrix.

`run-measurements.sh` and `build-probe.py` record this host's exact commands.
The original `../probe.patch` is applied only to a separate reference source
tree. Diagnostic worker intervals, which overlap across workers and include
timer overhead, will be kept separate from uninstrumented process timings.
Large inputs and output trees are not committed. Release asset input hashes
are verified against `SHA256SUMS.txt` before use.

## Remaining limits

Native macOS/CUDA execution, the full 24-movie tutorial collection, other
experimental datasets, high thread counts and NUMA/SMT scaling remain UNRUN
for this change. Linux tests do not waive the issue's inherited macOS
SyntheticRegression concern. Full-suite green status and a standard-kit
certified CPU performance claim require a host with a consistent process view.
