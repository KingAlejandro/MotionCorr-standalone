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
| CUDA / hardware labelled | 7 |
| **Default total** | **30** |
| With `MOTIONCORR_U16_TEST_MOVIE` set | 31 |

The seven hardware tests are `RunnerInterpolateShiftsCuda`,
`CudaWrapperUploadFailure`, `CudaU16StagingEquivalence`, `CudaFaultMatrix`,
`CudaPreprocessingFailurePaths`, `CudaPreprocessingFailurePathsFloatHost`,
`CudaErrorClass`. `CudaU16FailurePaths` stays opt-in behind the external fixture.

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

### Native CUDA

Pending. See the two drivers below. No native result is claimed for this
composition yet, and neither owner's retained native suite (PR115 26/26,
PR118 28/28, PR117's regraded 24/24) certifies it — they were executed on their
own sources, before composition.

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
