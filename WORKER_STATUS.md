# WORKER_STATUS — issue #69

| Field | Value |
|---|---|
| Issue | #69 "Make CUDA resource failures leak-free and resume-safe" |
| Model | `claude-opus-5`, high effort (no routing error observed) |
| Task class | correctness |
| Phase | plan + ADR published; implementation next |
| Base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Head | (see git log on branch) |
| Branch | `round96/69-claude-opus-5` |
| Worktree | isolated T3 worktree; no other task's files touched |
| PR | not yet opened |

## Whitelist — files this task may change

- `src/acc/cuda/cuda_alignpatch.cu` (F1, F2)
- `src/acc/cuda/cuda_movie_session.cu` (F3, F4)
- `src/motioncorr_runner.cpp` (F5, F6 — **shared file**, see coordination)
- `src/motioncorr_runner.h` (F5 test access only)
- `tests/test_patch_retry_state.cpp` (new)
- `tests/cuda_fault_matrix.cpp` (new, GPU)
- `CMakeLists.txt` (test registration only)
- `agents/designs/issue_69_cuda_failure_contracts.md`, `docs/issue69/**`, `WORKER_STATUS.md`

Not touched: allocators, `custom_allocator.cuh`, `acc_ptr.h`, FFT engine, numerical
gates, defaults, compiler flags, dependencies, any other issue's files.

## Coordination

`src/motioncorr_runner.cpp` is shared with #97/#98/#99. My edits are confined to the
local-patch block around `:2072-2155`. #99/#53 own completion/resume publication
semantics; I rely on the existing per-movie failure contract at `:626-645` rather than
changing it.

## Changed files

(none committed yet beyond docs)

## Latest test commands and results

(none run yet)

## Active PID / job / allocation

none

## Blockers

none

## NEEDS_GPU

Requested, waiting for a Codex-assigned slot. #26 owns this round's initial GPU
benchmark slot; I will not submit before assignment.

- **Purpose:** bounded fault matrix, forced-nonconvergence witness, healthy same-backend
  24-movie control. Correctness only — no timing claim, so no quiescence gate needed,
  but the bench lock is required because the work perturbs others.
- **Resources:** one A100 on `4GPUs` (or a SCARF Slurm allocation), `taskset -c 96-103`,
  build `-j8`, `flock /tmp/motioncorr-bench.lock`, ~20 min.
- **Commands:** see `docs/issue69/gpu_plan.md` once written.

## Next step

Implement F1-F6 as separate commits, add the CPU control, build and run the CPU suite on
`cpu64` under `flock /tmp/motioncorr-issue96-cpu-validation.lock`.
