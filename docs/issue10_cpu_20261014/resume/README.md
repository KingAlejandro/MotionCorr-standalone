# Issue #10 continuation validation, 14 October 2026

## Scope and source

Continue the newest branch `perf/issue10-cpu-ccf-plan` at
`5ac83a4ab4384f514a1ec2062f98c449576f01be`. The production change is the
existing `135d546` per-worker, array-bound CPU CCF plan reuse. Unchanged main
`116eb04ad359cd5bf789b28809fc2047ea155b9b` is the reference. This continuation
adds evidence and a bounded measurement recipe; it does not add another
optimization or change CUDA, Metal, JAX, FFT normalization, accumulation order,
public options or numerical gates. No merge or issue closure is requested.

At the user's request, the issue-10 commits were subsequently reattributed
to the authenticated `KingAlejandro` identity. The code commit is now
`1f4fe110720fecda07134a5f987f37efdb2310ae`, the original checkpoint is now
`5b7e482755669b74ad089f07e2f89282a5ef522d`, and the validated continuation
is `20e735650a012ae448965bf6579a3e5b1d823c4a`. Their trees are byte-for-byte
identical to the preceding commits. `source-identity.json` maps the historical
measurement pins, local documentation commit and published replacements;
binary hashes are unchanged. Both issue-10 branches use the corrected history.

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
- GitHub [Linux CI run 506](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38633456987)
  is **green on `20e7356`**: Ubuntu CPU **54/54 CTests**, known-motion aggregate,
  canonical fixture checks and smoke/failure controls pass. The CUDA job
  compiles successfully, including the linked controls, and checks the default
  architecture configuration. It performs **no GPU execution**. The preceding
  identical-tree run 505 is also green; its full Ubuntu log is retained in
  `ci-linux-512abeb.log`. Local process-identity failures are not concealed by
  the separate successful GitHub-hosted run.
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

## Completed unprofiled measurements: no full-job win established

The retained first-host matrix already covers global and 5x5, j1/j4,
dose/no-dose, noDW and even/odd on tutorial and synthetic inputs. This
continuation adds unprofiled timings, rather than repeating that profiled
matrix. All arms use identical host, compiler, input, mask and thread count.
One warmup per arm is excluded; execution order alternates AB/BA.

Tutorial, 3710x3838x24, 5x5, j4, dose + noDW + even/odd:

- Three complete measured pairs: baseline median **55.302 s**, range
  **54.051–64.164**; candidate median **57.322 s**, range **52.460–67.828**.
  Paired candidate-minus-reference differences are **+3.664, -1.591,
  +2.020 s**, median **+2.020 s**. Process CPU medians are **168.966 /
  173.658 s**. These observations do not demonstrate an improvement or a
  statistically resolved slowdown. Three pairs cannot provide the kit's
  distribution-free 95% median interval, which requires at least six.
- Peak RSS medians are **4,600,836 / 4,600,892 KiB**; the largest paired
  increase is **0.0058%**. This measures whole-process RSS, not just CCF arrays.
- Six pairs were planned. The strict full-tree comparison **failed on pair
  index 2**, so the recipe stopped after three. All canonical MRC/STAR/EPS
  products match, but the baseline tree also contains
  `workspace/scratch/28038873ca11/data/.tutorial.mrc.Q3ySGC`, a **22,806,528-byte**
  prefix of its final MRC. The baseline exited 0 and produced a complete final
  56,956,944-byte MRC. A subsequent unchanged-tree comparison still fails.
  `baseline-extra-file.json` records the artifact's hash and relationship;
  its cause is **UNRESOLVED**, and it is not attributed to the CCF change.
  The file has not been removed or excluded to make the inventory pass.
  This is **not a complete six-pair campaign or a full-tree identity pass**.

Synthetic, 512x512x16, three measured pairs per configuration. Values below
are per-arm median wall seconds and, separately, median paired differences:

- Global j1: **0.8620 / 0.8478 s**, paired **-0.0179 s**.
- Global j4: **0.7212 / 0.7214 s**, paired **-0.0304 s**.
- 5x5 + dose/noDW/even/odd j1: **1.6567 / 1.6464 s**, paired **+0.1029 s**.
- 5x5 + dose/noDW/even/odd j4: **1.2794 / 1.2995 s**, paired **+0.0578 s**.

All four synthetic full-tree comparisons pass on every measured pair and
warmup. No configuration has a resolved performance verdict at n=3.
The largest paired RSS increase across the synthetic cases is **1.47%**,
within the issue's 10% bound. Detailed ranges, CPU time and memory values
are in `unprofiled-summary.json`; every command, input/binary hash, run and
strict inventory verdict is retained in each `unprofiled-*/results.json`.

Across this new series, **96 canonical MRC/STAR file pairs are exact**:
**56 MRC and 40 STAR**, including warmups. `canonical-product-hashes.json`
retains every normalized file hash. This narrower product result does not
override the tutorial's extra-file/full-inventory failure. The separate
known-motion comparison contributes the 40 exact file pairs reported above.

## Completed diagnostic: planning/copy/lock mechanism

`run-measurements.sh` and `build-probe.py` record this host's exact commands.
The original `../probe.patch` is applied only to a separate reference source
tree. Both j1 and j4 diagnostic jobs complete **1,248 inverse CCF calls**.
Summed worker intervals, in seconds:

- j1: copy **0.0971**, plan including wait **0.3282**, execute **0.7957**,
  destruction including wait **0.1997**, lock wait **0.000230**.
- j4: copy **0.2903**, plan including wait **0.9986**, execute **1.4194**,
  destruction including wait **0.7447**, lock wait **1.0863**.

Lock wait is already contained in plan/destructor time, so it must not be
added again. These intervals include instrumentation overhead and can overlap
across workers. They are not elapsed job times or measured candidate savings.
The candidate removes repeated plan/copy work from the CCF loop, but retains
one forward/inverse plan pair per worker per alignment call. The lifetime
controls verify actual reuse; this is not a new standalone FFT benchmark.
Diagnostic process/stage profiles and all raw rows are retained separately
from the uninstrumented results. No whole-run time is computed by mixing them.

Large inputs and output trees are not committed. The tutorial movie and gain
hashes match the release `SHA256SUMS.txt`. The partial baseline artifact
remains in scratch; its size and SHA-256 are retained in the report.

## Acceptance recommendation

Numerical implementation checks and Linux CI are positive. Three matched
unprofiled repetitions exist for the new configurations, and measured RSS
stays within the 10% bound. **A meaningful whole-job CPU speedup is not
established.** Do not mark that performance acceptance item passed or reuse
the first-host stage improvement as a second-host full-job claim.

Keep this PR **draft** for an explicit benefit/complexity decision and a
clean-host performance comparison. Preserve the tutorial inventory failure
for investigation; no numerical gate, product inventory rule or ownership
assertion has been relaxed. No second optimization is added to rescue the
timing result, and neither the PR nor issue #10 is automatically merged/closed.

## Remaining limits

Native macOS/CUDA execution, the full 24-movie tutorial collection, other
experimental datasets, high thread counts and NUMA/SMT scaling remain UNRUN
for this change. Linux tests do not waive the issue's inherited macOS
SyntheticRegression concern. GitHub supplies the separate green Linux CI
result; a standard-kit certified CPU performance claim still requires a host
with a consistent process view and a passing complete product inventory.
