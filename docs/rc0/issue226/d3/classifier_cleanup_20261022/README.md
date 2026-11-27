# #226 D3 classifier and cleanup controls, 2026-10-22

This round starts at PR251 head `4c82012b2995c5255fa1fecf29ade9b3108e4d8c`
on the new isolated branch `pr251-d3-classifier-cleanup-controls`. The live
issue226 discussion, PR251 body/review and empty inline-review collection were
read before implementation. `review-context.json` retains the nonblocking review:
no defect was previously reproduced; the one-byte control skips planning.

## Finding and narrow guard

At the base revision, `src/motioncorr_runner.cpp:2492-2495` records the cuFFT
result, destroys the plan, then inspects the runtime status. A simulated
`CUFFT_ALLOC_FAILED` accompanied by `cudaErrorIllegalAddress`, followed by cleanup
that replaces the pending status with success or an allocation failure, is
reported as ordinary OOM. Both original-source controls exit normally with code
1 and retain identical next-movie products; their test predicates fail because
the diagnostic is OOM instead of fatal. See `before/grades.json` and logs in
`receipts.tgz`. This is a reproduced status-preservation gap under injection,
not a reproduced hardware fault or an observed cuFFT-library failure sequence.

The sole production change records `cudaPeekAtLastError()` in the existing
`CudaFailureState` before `owner.releaseAll()` (now line 2495). Its existing
monotonic fatal latch then outranks cleanup and ordinary OOM. No algorithm,
interface, dependency, default, allocation policy, tolerance or publication rule
changes. This routine guard does not need a design ADR.

## Controls and results

The dedicated `motioncorr_streaming_plan_fault` target combines the existing
resident-refusal/allocation ownership shim with new cuFFT wrappers. They select
the direct admission caller, return simulated statuses, and really destroy each
successfully created handle exactly once. Actual CUDA errors always take
precedence over simulated peek statuses. Production has no fault switch.

- **Before: FAIL as required**, two fatal-before-cleanup rows. Three native
  processes including the healthy reference. Both regressions report OOM rather
  than fatal; no crash is accepted as a diagnostic.
- **After: PASS, 16/16 rows**, plus a standalone reference. Coverage includes
  healthy planned streaming, create/auto-allocation/make-plan allocation versus
  nonallocation errors, cleanup allocation/nonallocation/fatal errors, earlier
  fatal versus later cleanup success/OOM, earlier nonallocation error versus
  cleanup OOM, and earlier OOM versus cleanup fatal.
- **Early refusal: PASS**, the existing one-byte test and its reference. The
  shared helper adds retained receipts and exact product inventories without
  changing its numerical comparator or threshold.
- **Final wrapper follow-up: PASS, 6/6 affected fatal rows**, plus a reference.
  The initial injection supplied one-observation simulated peek returns. Final
  harness review changed this to preserve the virtual status until cleanup,
  matching the non-consuming semantics of `cudaPeekAtLastError`. All six fatal
  cases were rerun. The production guard is identical in both after builds;
  ordinary rows are unchanged and were not rerun after this test-only change.

Total: **29 small native MotionCorr processes**, sequential, no timeout/signal.
All failed-movie rows require exactly b's MRC/STAR and no failed a or joint STAR;
b is compared strictly against its standalone reference. Healthy planned
streaming requires a and b plus joint STAR, with both movies matching the
reference. Comparisons retain the existing writer-timestamp mask, full MRC
header/extended-header/payload checks and normalized movie-name STAR comparison.
All tested admission-plan handles balance, all actual destroys succeed, and
allocation tracking reports zero remaining ownership and zero stale releases.
JSON receipts retain product hashes, inventories and grading problems.

Release CUDA-only configure/build passed. The first build failed because macOS
archive metadata produced `._*.cpp` entries in the scratch source glob; its log,
exit receipt and removed metadata-file list are retained. Only those metadata
files in this round's scratch were removed before the clean rebuild.
CTest `-N` confirms both test registrations; the hardware controls were invoked
directly for retained evidence. Python syntax, shell syntax and `git diff --check`
pass. No full-suite result is inferred from these bounded runs.

## Resources, commands and receipts

Native venue: `ssh -J ccp4-gateway 4GPUs`, hostname `4-gpu-vm`, physical GPU3
`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, A100 80 GB PCIe, driver 570.86.10.
CUDA nvcc 12.8.61, GCC 13.3.0, CMake 3.28.3, Python
`/home/alex/.mc-venv/bin/python3`, NumPy 2.5.3. CUDA-only; nvCOMP is not needed
for this streaming-planner boundary. Local Python syntax checks use
`/Users/alex.konstantinov/.local/bin/python3`.

All detached drivers use `taskset -c 10-13`, build `--parallel 2`, runtime `--j 1`
and OMP/OpenBLAS/MKL/NumExpr threads 1. Common build lock:
`/tmp/motioncorr-build.lock`, nonblocking. Canonical runtime lock:
`/tmp/motioncorr-gpu3-correctness.lock`, nonblocking, held through all samples and
post-health checks. The benchmark lock is probed/released before rechecking
occupancy. `sample_guard.py` requires initial/pre idle, checks UUID, processes,
utilization, memory, recovery action, all ECC counts, retired/remapped-page state
and unchanged health. Post settling was fixed before launch at at most five
samples one second apart; every sample is saved and checked for errors.

Scratch only: `/mnt/clathrin/mc-d3-classifier-20261022`. Source came from a
`git archive` of the base plus the named test overlay; `source-before.json`,
`source-after.json` and `source-final.json` bind exact relevant source hashes.
The production source hash is identical between after and final. Original source
archive hash, build flags, toolchain, binary hashes, input hashes, argv, PID,
exit, affinity and numeric-thread settings are retained. Inputs are deterministic
48 x 40 x 6 synthetic float MRC movies, not QM/scientific data.

Exact configure/build/test invocations are in `run_remote.sh`. The executed
modes, in order, were `build-before` (metadata failure), `build-before-clean`,
`before`, `build-after`, `after`, `build-final`, `final`, each launched as:

```sh
nohup taskset -c 10-13 src/docs/rc0/issue226/d3/classifier_cleanup_20261022/run_remote.sh MODE \
  > MODE.log 2>&1 < /dev/null &
```

Each driver writes its own PID/exit receipt. Existing completion and exit receipts
were reconciled before subsequent launches; failures and products were preserved.
`receipts.tgz` contains compact raw logs, JSON receipts, grades, every health XML,
configuration/collection evidence and final release probes, with no binaries or
movie products. `receipts.sha256` binds it. Complete products/build/source remain
in the isolated scratch. The final driver and all native processes exited;
GPU3 was idle/healthy and canonical GPU/build/benchmark locks were released.
No resets, foreign kills, service/cache changes, pushes, merges or remote comments.
The protected root remained at `c8844894` with its original untracked
`pr117-fix-measure-20260929/`; the parent branch remained at `1f0a58bf`.

## Limits and prior identities

### Review follow-up: require the planning control

Review of `35d2f950` found that the new hardware control was registered but
omitted from both `CUDA_REQUIRED_TESTS` in `tools/validate_test_collection.py`
and the independent `CUDA_SUITE` in `tools/test_ci_fail_closed.py`. Both now
require `CudaStreamingPlanClassificationCleanup`. The existing drop-one control
therefore also rejects its omission while keeping the inventory count unchanged.

`collection-review-before.json` retains actual validator CLI calls over constructed
CPU/CUDA inventories derived from the independent collection fixture. The old
validator accepts the complete CPU and CUDA inventories and also incorrectly
accepts the CUDA inventory with the new control replaced by an additive filler.
`collection-review-after.json` records the same inputs: complete CPU/CUDA collections
exit 0; omitting the new control exits 1 and names the missing test. These are
host collection-policy checks, not actual CTest or native executions.

The focused existing unittest also **PASS**:

```sh
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /Users/alex.konstantinov/.local/bin/python3 -B -m unittest \
  tools.test_ci_fail_closed.TestCiFailClosedControls.test_3_zero_or_missing_collected_tests_fails -v
```

`collection-review-unittest.log` retains its result, including existing CPU,
drop-one CUDA, empty-command and automatic CUDA-cache selection controls.
Production, CMake, native test sources and the original receipt archive are
unchanged by this follow-up. No native run or build was repeated.

All fatal and library failures here are **simulated classifier returns** around
real healthy native GPU work. Genuine poisoned contexts, actual failing cuFFT
teardown, real low-memory devices, nvCOMP configuration, full suites, QF,
performance and scientific qualification remain **UNRUN in this round**.
The full 74/109/112 suites and QM evidence in the parent D3 directory retain their
original implementation `4cd85167` and venue identities; they do not qualify this
new guard. D2/PR252 and the science pilot are separate and were not incorporated.
No merge recommendation is made.
