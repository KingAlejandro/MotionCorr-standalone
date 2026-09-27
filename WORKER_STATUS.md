# WORKER_STATUS — issue #94

| field | value |
|---|---|
| Issue | #94 bounded next-movie CUDA prefetch |
| Model | `claude-opus-5` (Opus 5, 1M context), high effort |
| Task class | implementation |
| Phase | 1/5 — plan + ADR published, implementation starting |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (origin/main) |
| Head | (none yet) |
| Branch | `round96/94-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-967d9ef6` |
| PR | (not yet opened) |

## Changed files so far

- `agents/designs/issue_94_bounded_prefetch.md` (new, ADR + changed-file whitelist)
- `WORKER_STATUS.md` (new)

## Latest test commands / results

None yet. No build has been run on this branch.

## Active PID / job / allocation

None.

## Blockers

None blocking design/implementation/CPU tests.

## NEEDS_GPU

Requested, **not yet scheduled**. #26 owns this round's first GPU slot; nothing will be
submitted to `4GPUs` or SCARF until Codex assigns one.

- Purpose: paired serial-vs-prefetch end-to-end screening on the 24 tutorial movies, plus
  exact same-backend output comparison, on the resident CUDA path.
- Resources: 1 GPU first; CPUs `96-103` only (8 logical CPUs total, shared by all MotionCorr
  work); `flock /tmp/motioncorr-bench.lock` for the whole series; no competing benchmark.
- Estimated occupancy: one Release build (<= 8 jobs) inside the lock, then >= 3 interleaved
  paired blocks with alternating arm order over 24 movies.
- Command: `scripts/prefetch_gpu_screen.sh` (to be committed this round; will be published in
  the issue comment with its exact invocation before any request to run it).
- Follow-on only if 1-GPU screening is not negative: 2/3/4-worker schedules under the same
  fixed aggregate CPU budget.

## CPU compute

`cpu64` (`small-refmac-machine`) probed at 2026-09-28T23:48Z: reachable, load1 2.48,
`~/.mc-venv/bin/cmake` present, `flock -n /tmp/motioncorr-issue96-cpu.lock` free. All CPU
builds/tests for this task will run there under `taskset -c 40-47` and that round lock, build
and runtime parallelism <= 8.

## Next step

Implement `src/movie_prefetch.{h,cpp}` (byte budget, bounded queue, producer) and the runner
integration, then the cheap lifecycle and equivalence tests, then a staged Release build and
`ctest` run on `cpu64`.
