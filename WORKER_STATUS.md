# WORKER_STATUS — issue #53, round 96

| Field | Value |
|---|---|
| Issue | #53 — current-main multi-GPU scheduler |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | implementation |
| Phase | 1 — plan and ADR published; implementation starting |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Branch | `round96/53-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-20acbcac` |
| PR | not yet opened |

## Scope (PR A only)

Per the #53 and PR55 audit handoffs and the #66 execution plan: refresh the static
launcher onto current main, reject misleading native device-list syntax, prove
metadata/collision/abort/resume behaviour with cheap CPU fixtures. No dynamic
coordinator, no intra-movie GPU rewrite, no coordinator C++ flags (PR B), no
throughput claim.

ADR and changed-file whitelist: `agents/designs/issue_53_multi_gpu_scheduling.md`.

## Changed files

Planned, per the ADR whitelist:

- production: `src/motioncorr_runner.cpp` (device-list rejection + help text only)
- tooling: `tools/multi_gpu/{star_io,partition_star,merge_workers,gpu_witness,run_multi_gpu,compare24}.py`
- tests: `tests/test_multi_gpu_scheduling.py`, `tests/fake_worker.py`, one `CMakeLists.txt` `add_test`
- docs: `agents/designs/issue_53_multi_gpu_scheduling.md`, `docs/multi_gpu/`, `WORKER_STATUS.md`

Actually changed so far: `agents/designs/issue_53_multi_gpu_scheduling.md`, `WORKER_STATUS.md`.

## Latest test commands and results

None run yet.

## Active jobs / allocations

None.

## Blockers

None for PR A.

## NEEDS_GPU

Requested, **not yet scheduled**. Everything below is prepared-but-unrun and is reported
as unrun.

- Purpose: native all-24 serial-versus-sharded **exact equality** plus per-device
  physical-UUID and completed-stage witnesses. Correctness only — **no timing arm, no
  competing benchmark matrix.** #26 owns this round's benchmark slot.
- Resource: 4 physical GPUs, one process per GPU, within the shared-`4GPUs` contract —
  aggregate CPUs 96-103, eight logical CPUs total, `flock /tmp/motioncorr-bench.lock`.
  A dedicated SCARF allocation is preferred if offered.
- Dataset: the 24 tutorial movies, `movies.star` `fb998f70…`, `gain.mrc` `8919cdc7…`.
- Estimated occupancy: one serial arm plus one 4-way sharded arm plus 24 comparator
  invocations. Exact commands will be pinned in `docs/multi_gpu/` before submission.
- Waiting on: Codex monitoring to assign a slot.

## Next step

Implement the ADR's PR A: STAR I/O, partitioner, launcher, merge, fake-worker fixtures,
device-list rejection. Then independent read-only review, then draft PR.
