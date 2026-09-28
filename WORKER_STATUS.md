# WORKER_STATUS — issue #53, round 96

| Field | Value |
|---|---|
| Issue | #53 — current-main multi-GPU scheduler |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | implementation |
| Phase | 3 — draft PR open; independent read-only review in progress |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `e0699da` |
| Branch | `round96/53-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-20acbcac` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/106 (draft) |

## Scope (PR A only)

Static whole-movie process workers, deterministic metadata merge, native
device-list honesty, cheap CPU fixtures. **Not** in this PR: dynamic coordinator
or work queue, coordinator gain/merge C++ flags, intra-movie GPU split, any
numerical change, any throughput claim.

ADR and changed-file whitelist: `agents/designs/issue_53_multi_gpu_scheduling.md`.
PR55's branch, history and evidence are untouched.

## Changed files

Diff against base is exactly the ADR whitelist, 19 files:

- production: `src/motioncorr_runner.cpp` (+36/-11, device-list validation and help text only)
- tooling: `tools/multi_gpu/{star_io,partition_star,merge_workers,gpu_witness,run_multi_gpu,compare24}.py`
- tests: `tests/{fake_worker,test_multi_gpu_scheduling}.py`, one `add_test` in `CMakeLists.txt`
- docs/evidence: `agents/designs/issue_53_multi_gpu_scheduling.md`, `docs/multi_gpu/`, `WORKER_STATUS.md`

No pre-existing test, tolerance, gate or numerical constant is touched.
`WORKER_RESOURCE_UPDATE.md` is Alex's file and is deliberately left untracked.

Commits, separated by kind as the round requires:
`6b17a2e` docs/ADR · `1b8ada5` fix · `8008b60` tools · `3eece28` test · `e0699da` evidence.

## Latest test commands and results

Host `small-refmac-machine` (cpu64), `taskset -c 32-63` (NUMA node 1), under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`. Release,
`-O3 -DNDEBUG -std=gnu++17 -fopenmp`, g++ 13.3.0, cmake 4.4.3, Python 3.12.3.
Patched binary `f4748106a1a296efd961b655fce675c9336cda42ca63f7b4bf4488d12ef9e8f2`;
unpatched-main control `de35fddc37d8237576adea7d34bec618ce1bf4867286b87ec568815c71645f8a`.
Raw logs: `docs/multi_gpu/pr_a_evidence/`.

| Command | Result |
|---|---|
| `tests/test_multi_gpu_scheduling.py --binary <built>` | **16/16 passed** |
| `docs/multi_gpu/negative_controls.py` | **12/12 mutations detected**, no survivors |
| `ctest --output-on-failure -j 4` | **14/14 passed** (13 pre-existing + `MultiGpuScheduling`) |
| `--gpu 0:1:2:3 / 0,1 / 0:1 / 0abc / -1 / 0`, patched vs base | recorded in `device_list_witness.txt` |

Interference recorded: two unrestricted `ctffind` process trees (PIDs
1156938/1156942, 1635423/1635428/1635429) and host load 6.95–7.60 throughout.
Nothing in PR A is timed, so this affects no claim; it is recorded so none of
this evidence is later reused as a timing baseline.

## Active jobs / allocations

None. cpu64 scratch at `~/mc-issue53-round96` and `~/mc-issue53-round96-base`;
no job is holding a lock.

## Blockers

None for PR A. Two independent read-only reviews (code/correctness, and
spec-conformance/license) are running; the PR is not called reviewable until
both are recorded.

## NEEDS_GPU

Requested, **not scheduled**, **UNRUN**, and reported as unrun. Full plan and
exact commands: `docs/multi_gpu/NEEDS_GPU.md`.

- Purpose: native all-24 **serial-versus-sharded exact equality** with physical
  GPU UUID and completed-stage witnesses. **Correctness only — no timing arm,
  no competing benchmark matrix.** #26 owns this round's slot.
- Resources, per the 28 Sep resource update: shared `4GPUs`, **initially at most
  2 GPUs**; aggregate **16 logical CPUs 96-111 on NUMA node 1**; one
  `flock /tmp/motioncorr-bench.lock`. A dedicated SCARF allocation preferred if
  offered. One serial arm, one sharded arm, 24 comparator invocations, two
  argument-parser probes. No repeats — nothing is being timed.
- Inputs: `movies.star` `fb998f70…`, `gain.mrc` `8919cdc7…`, verified against
  `Movies/SHA256SUMS.txt`. Chosen cores, inherited cpuset, NUMA/memory policy and
  actual GPU UUIDs recorded per run, as the resource update requires.
- Includes the one claim PR A's CPU evidence cannot support: that an **unpatched
  CUDA build** resolves `--gpu 0:1:2:3` to device 0 and announces it. That is
  currently a code-reading claim only.
- Both arms' complete output trees retained — a parity run cannot certify an arm
  whose outputs were deleted.

## Next step

Record both independent reviews on the PR, address any finding, then post the
milestone comment on #53. GPU arms stay unrun until a slot is assigned.
