# Combined CUDA candidate: composition, requirements and evidence

Integration owner `a90c42be`. Composed head is a history-preserving merge of
three owners' reviewed sources onto main `6393547e`; no production line in this
branch was written here.

| Merged | Owner source | What it contributes |
|---|---|---|
| PR115 (#69) | `0f2ddd5d` | CUDA failure ownership: scoped resources, error classification, monotonic fatal state, runner disposal boundary |
| PR117 (#53) | `b70f352b` | Static whole-movie GPU workers, honest `--gpu` validation, launcher/merge/witness tooling |
| PR118 (#85 lane C) | `7b5a637b` | Compact uint16 TIFF ingest with device-side expansion and gain |

## Composition: what actually had to be decided

PR118 had already cross-ported PR115's production change, so the two share ten
of eleven touched files. Merging both onto main is therefore mostly a
confirmation, not a combination. Verified rather than assumed:

* The ten files PR115 and PR118 share resolve to **PR118's content byte for
  byte**, which for eight of them is identical to PR115's.
* `src/motioncorr_runner.cpp` is the only three-way file. PR117 changes
  argument parsing (~line 125 and 257-320); PR115/PR118 change movie
  processing (~line 1338 onward). The merged file is byte-identical to
  *PR118's runner with PR117's diff applied*, checked by reconstructing that
  file independently and comparing.

Four files needed a decision:

1. **`tools/validate_test_collection.py`** — required-test union recomputed to
   **23** (main's 20 + `PatchRetryState` + `OutputTreeComparator` +
   `MultiGpuScheduling`), `--min-count` 23. Each branch had independently
   raised the count to 21 or 22; git merged those identical `20 -> 21` edits
   without a conflict, which would have left the gate one to three tests short
   of what the composed tree registers.
2. **`tools/test_ci_fail_closed.py`** — the same 23 names restated
   independently, and all three new names added to the drop-one loop. This file
   deliberately duplicates the list; a stale copy re-breaks the count-gate
   preemption silently.
3. **`CMakeLists.txt`** — kept `MultiGpuScheduling` *and* `OutputTreeComparator`;
   took PR118's `motioncorr_faultinject` wrap set, which is PR115's plus
   `cudaGetLastError`; removed a `--wrap=cudaGetDeviceCount` that the auto-merge
   duplicated into one target.
4. **Both preprocessing failure arms kept.** PR115 registered
   `CudaPreprocessingFailurePaths --float-host`; PR118 registered the same
   script without it. The composed source contains both host paths and each
   registration can only observe its own, so dropping either would leave a
   production path uncovered. They are now
   `CudaPreprocessingFailurePathsFloatHost` and `CudaPreprocessingFailurePaths`.

`tests/cuda_fault_inject_shim.cpp` takes PR118's version, a strict superset:
it keeps `float-gain-fatal` (now excluding `applyGainDefectsAndSumU16`) and adds
the lane-C staging controls.

## Registered tests

| | Count |
|---|---|
| Device-free (required union) | 23 |
| CUDA labelled | 6 |
| **Default total** | **29** |
| With `MOTIONCORR_U16_TEST_MOVIE` set | 30 |

The six CUDA tests are `RunnerInterpolateShiftsCuda`,
`CudaWrapperUploadFailure`, `CudaU16StagingEquivalence`, `CudaFaultMatrix`,
`CudaPreprocessingFailurePaths`, `CudaErrorClass`; five carry the `hardware`
label as well. `CudaU16FailurePaths` stays opt-in behind the external fixture.

## Independent review and what changed because of it

A current-source review was run against `f104605`. It verified the
no-new-production claim independently — its own blob-identity matrix over all
33 changed files, its own `patch(1)` reconstruction of the runner, and a
reverse-apply containment check proving PR115's runner work survived PR118's
supersession — and confirmed the test-union arithmetic, the `--wrap` symbol
sets, the shim superset relation (by compiling both signatures and reading the
mangled names with `nm`), scope and licence. It found **no defect in the
composed production source**. Every finding was in this directory's harness:

| Finding | Action |
|---|---|
| P1 `run_matched_experiment.py` globbed `worker*` for the merge, so every arm was excluded and nothing was ever graded | fixed; it now also refuses on a worker-count mismatch |
| P1 A6 copied the a2 tree, whose `status.json` names a2's manifest and logs, so `merge_workers` refused and the arm could never pass | A6 is now its own run |
| A6's dropped set was the tail of worker 0's contiguous shard, i.e. a suffix resume | now removes an interior gap from every shard and asserts it is interior |
| The second preprocessing arm's rationale was false | arm removed; see composition note 4 |
| The sampler discarded the pid from `compute_apps`, so a co-tenant on a granted UUID was added to our figure | intersects with the descendant set; foreign contexts recorded separately |
| RSS over-counts shared pages once per process, which is not constant across a 1/2/4-worker contrast | `Pss` sampled alongside and documented as the figure to compare arms on |
| Both consumers read `status["witness"]`; the launcher writes `gpu_witness` and there is no `verdict` key | fixed in both |
| The block reference could silently fall back to a previous block's tree | no fallback; each arm records `graded_against` |
| `verify_composition.py` scanned only `src/` while its verdict said "every production byte" | scans `tests/`, `tools/` and `CMakeLists.txt` too, with the three hand-reconciled files declared up front |

Two findings were routed rather than fixed. `run_preprocessing_failure_controls.py:202`
records `host_storage` as one host path for a run that exercises both; the file
is byte-identical in PR115 and PR118 and belongs to the shared executor
([PR115 comment](https://github.com/KingAlejandro/MotionCorr-standalone/pull/115#issuecomment-5892887040)).
And 13 of the 23 required names inherited from main are absent from
`test_ci_fail_closed.py`'s drop-one loop, so their missing-name rejection is
never exercised; all three names this composition adds are covered, and
widening the inherited set is not this task's scope.

Not addressed, and recorded as a limitation: `test_aggregate_sampler.py` and
`verify_composition.py` are not registered as CTests, so nothing re-runs them
automatically. Registering them would change the required-test union that three
other owners are tracking, which is a coordination cost this task should not
impose unilaterally. They are run by hand and their results are recorded here.


## Requirements, evidence and support matrix

Status vocabulary: **PASS** executed and met · **PENDING** prepared, not yet
executed · **BLOCKED** waiting on another owner. A prepared check is not a pass.

### Composition and review

| Requirement | Status | Evidence |
|---|---|---|
| Start from current main `6393547e` | PASS | branch base; three `--no-ff` merges |
| Compose PR115, then PR117, then PR118 | PASS | `f7da619`, `7c17f2d`, `1793e7e` |
| Merge/`-x` provenance, no obsolete CUDA history | PASS | merge commits of the owner sources; no PR106/PR107 chain imported |
| Preserve owner commits, authorship and evidence | PASS | owner commits unrewritten; their `docs/` trees carried in |
| Do not duplicate PR118's PR115 cross-port | PASS | `verify_composition.py`: 10 of 11 `src/` files resolve to PR118's bytes |
| No production line written by the integrator | PASS | `verify_composition.py` PASS; fails on all three negative controls |
| Recompute the required-test union | PASS | 23 names, `--min-count` 23, restated list and drop-one loop updated |
| Complete test collection controls | PASS | `CiFailClosedControls` 8/8 on both hosts |
| Provenance oracle over `src/`, `tests/`, `tools/`, `CMakeLists.txt` | PASS | `verify_composition.py`; 3 declared reconciliations, 0 unsourced |
| Keep #93 / #108 / #121 out | PASS | absent from the branch |
| Current-source independent review | PASS | no defect in the composed production source; all harness findings fixed or routed |

### Executed checks

| Check | Host | Status | Result |
|---|---|---|---|
| CPU Release build | cpu64 | PASS | exit 0 |
| Required-test collection gate | cpu64 | PASS | 23/23 |
| CPU CTest | cpu64 | PASS | 23/23 |
| Negative controls: PR117 mutation harness on the composed tree | cpu64 | PASS | 83/83 detected, 0 skipped |
| CUDA compile, both arms | SCARF cn062 | PASS | distinct binaries `670cfa26…` / `5ac37830…` |
| CI, both jobs | GitHub | PASS | green on `a8d8dc6`, `9450a9d`, `0ed67fa`, `f104605` |
| **Native CUDA CTest** | 4-gpu-vm GPU3 | **PASS** | **30/30** at `0ed67fa`; re-run at the corrected 29 is in the queued SCARF job |
| Measurement-tool controls | cpu64 | PASS | 8/8, and each fails on its targeted mutation |

### Untimed all-24 native correctness

All rows **PENDING**, queued as one exclusive 4-GPU SCARF job. Driver:
`run_correctness_all24.sh`.

| Requirement | Arm |
|---|---|
| Serial vs 2-worker, per-movie exact | C2 via `compare24.py` |
| Serial vs 4-worker, per-movie exact | C4 |
| Complete finite pixels, full normalized MRC + extended headers, STAR inventory | S2/S4 via `compare_output_trees.py` |
| Aggregate STAR, optics and exposure identity | C3 |
| UUID, actual pid and achieved mask per worker | launcher witness + sampler `/proc` readback |
| Distinct shards, disjoint and complete | shard-manifest check |
| Controlled owned-child failure | A5, reports `KILL_DELIVERED` or `VACUOUS_NO_WORKER_FOUND` |
| Non-prefix resume | A6, canonical indices 5-11, reports removals made |

### Matched fixed-budget experiment

**BLOCKED**, prepared. Driver: `run_matched_experiment.py`. Waits on memory
owner `b3c72f3f`'s +0.230 GiB no-gain disposition and tests owner `ff83c21a`'s
accepted delta; neither has landed (both worktrees are still at their base).

Design: float vs compact ingest, 1/2/4 workers, fixed total 24 logical CPUs
(24 / 12+12 / 6+6+6+6) with per-worker `--j` and `--max_io_threads` equal to
that worker's CPU count, identical output modes, matched gain and no-gain
series, >=3 interleaved complete blocks with rotated arm order, every run
retained in `runs.jsonl` with `retained` and `excluded_because`. Recorded per
arm: launcher wall including setup and final drain, worker tail, simultaneous
aggregate RSS, UUID-filtered per-process GPU memory with interval, achieved
placement, and a full output grade against the block reference.

**No GO/NO-GO performance conclusion exists yet**, because no arm has run. The
retained PR118 gain-arm screen (31.57 → 25.04 s) is a different source under
different resources and does not transfer to this composition.

### Blocking dependency

PR115 and PR118 share an open reconstruction-cleanup review finding. The shared
executor's fix is uncommitted in their checkout (four files). This branch is
pinned to the sources before it and **must be recomposed and re-validated**;
re-run `verify_composition.py` with the updated owner revisions afterwards.

## Executed evidence

### CPU, cpu64 (`small-refmac-machine`), 29 Sep 2026

Fresh Release CPU-only build of composed source `1793e7e`, `taskset -c 32-47`,
`numactl --membind=1`, `-j16`, under `/tmp/motioncorr-issue96-cpu-validation.lock`.
ctffind PIDs 1156942 and 1635429 untouched.

| Check | Result |
|---|---|
| Configure + build | PASS, exit 0 |
| Required-test collection gate (`--min-count 23`) | **23/23 PASS** |
| Full CPU CTest | **23/23 PASS** |
| PR117 mutation harness on the composed tree | **83/83 mutations detected, 0 skipped** |

The first attempt reported 22/23. `CiFailClosedControls` control 2 shells out to
`cmake`, which was not on the driver's `PATH`; the source was not involved. The
authoritative run above has the venv toolchain on `PATH`.

The mutation run matters more than the test count: it re-proves on the *composed*
tree that each scheduling guard is still what makes its test pass, including the
two P1 fixes frozen in `b70f352b` (`merge accepts an empty required-product list`,
`launcher mistakes zombie-only groups for live survivors`).

### Native CUDA, 4-gpu-vm GPU3, composed source `0ed67fa`

**30/30 CTest PASS** on a real A100, 0 failed. Full record in
`evidence/native-ctest-vm-20260929/`.

That run is **pinned to `0ed67fa`**, which still registered the duplicate
`CudaPreprocessingFailurePathsFloatHost` arm; the current source registers 29.
Every test in the 29 passed there, and the only difference is the removed
duplicate, but the 30/30 figure describes the earlier source and is labelled as
such rather than restated for this one. The re-run at 29 is folded into the
SCARF correctness job, which reconfigures before testing. A first VM re-run
attempt refused: a colleague's RELION cross-validation job (`dxp41838`, pid
1905876) holds a context on all four VM devices, so the box is not available and
was left alone.

One disjoint device only — GPU0/1/2 belong to the shared reconstruction-cleanup
fix validation. The occupancy gate refused a first attempt because something
briefly held a context on GPU3; that refusal is retained beside the passing
retry.

This is the composed source's own native suite. It is **not** the all-24
serial-versus-2-and-4-worker matrix, which needs four devices and is queued as a
separate exclusive job, and it carries no timing claim. Neither owner's retained
native suite (PR115 26/26, PR118 28/28, PR117's regraded 24/24) certifies this
composition — each ran on its own source, before composition.

## Measurement tooling: what was verified before use

`#26`'s `tools/envelope_runner.py` was audited against this experiment's needs
and is **not usable as the driver**: it opens exactly one `Popen` and blocks on
it, so it cannot express a concurrent-worker arm, and its GPU sampler addresses
devices by nvidia-smi ordinal (`--id=<n>`) reading whole-device `memory.used`.
An ordinal does not identify silicon once `CUDA_VISIBLE_DEVICES` is set. Its RSS
semantics are correct and were reused as the model for `aggregate_sampler.py`.

`tools/envelope_report.py` is sound where it is mutation-proved, with constraints
worth recording for any later user: `median_cpu_s` is computed without a validity
gate on its inputs (a run with an unparsed `/usr/bin/time` silently contributes
zero — demonstrated: 55.0 reported for a true 110.0); `peak_rss_mib` is likewise
ungated on sample count; and its slot-ratio vacuity guard is
`len(a) == 1 and len(arms_by_slot) > 1`, which is disabled in exactly the
fully-degenerate case it exists to catch, printing "every slot was occupied by
more than one arm" over a single-arm slot. These are #26's to fix; they are
recorded here because this task was told to verify the tools before using them.

`tools/multi_gpu/run_multi_gpu.py` supplies UUID pinning, compute-apps witnesses,
per-worker start/end and the final-worker tail. It does **not** supply a
simultaneous aggregate RSS: `rss_hwm_kib` is per-process `VmHWM`, a lifetime peak
with ghostscript children excluded, and adding N of those is an upper bound on a
quantity nobody observed. `aggregate_sampler.py` fills exactly that gap.

## Drivers in this directory

| File | Purpose |
|---|---|
| `aggregate_sampler.py` | Simultaneous aggregate host RSS over the whole descendant tree on one clock, plus UUID-filtered per-process GPU memory from compute-apps, with the sampling interval published beside every figure |
| `test_aggregate_sampler.py` | Controls for the above. Control 1 is built so sum-of-peaks and sweep-total differ by 2x; control 2 is its negative control. Exits 2 when the platform cannot run them |
| `run_correctness_all24.sh` | Untimed serial vs 2- and 4-worker all-24 correctness, per-movie pixel exactness, structural grading, aggregate STAR identity, owned-child failure, non-prefix resume |
| `run_matched_experiment.py` | The matched fixed-total-24-CPU experiment: float vs compact ingest at 1/2/4 workers, gain and no-gain series, >=3 interleaved blocks |

## Dependencies and what is still open

* **Reconstruction-cleanup P1.** PR115 and PR118 share a review finding: a fatal
  temporary-resource release status can be lost before fallback/download. The
  existing shared executor owns the fix. This composition is pinned to the
  sources *before* it; it must be recomposed and re-validated on the reviewed
  final sources before acceptance. No production edit for it was made here.
* **Memory owner `b3c72f3f`** — the ~+0.230 GiB no-gain RSS increase. The timed
  matrix waits on that disposition.
* **Tests owner `ff83c21a`** — accepted support delta.
* **PR117** is frozen at `b70f352b` with its CPU/native CLI controls passing;
  final publication and CI are its owner's.

Out of scope and deliberately absent: #93, #108, #121's reader pool, any dynamic
scheduler, any cache redesign. PR65 Stage B remains INCONCLUSIVE and nothing here
addresses it.
