# WORKER_STATUS — issue #69

| Field | Value |
|---|---|
| Issue | #69 "Make CUDA resource failures leak-free and resume-safe" |
| Model | `claude-opus-5`, high effort (no routing error observed) |
| Task class | correctness |
| Phase | implemented, CPU-validated, CUDA-compiled; draft PR open; waiting on a GPU slot |
| Base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Head | `75c21df` (plus this status update) |
| Branch | `round96/69-claude-opus-5` |
| Worktree | isolated T3 worktree; no other task's files touched |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/107 (draft) |

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
local-patch block and one include. #99/#53 own completion/resume publication semantics;
I rely on the existing per-movie failure contract at `:626-645` rather than changing it.

### PR93 (#77) is a hard conflict, and it is not just textual

Flagged by the independent spec review; I under-reported it in the first version of
this file. PR93 `fix/issue77-reviewed-kernels` head `4998599` touches three of my four
production files, and against main `4c952b3f` its diff is
`cuda_alignpatch.cu +523/-…`, `cuda_movie_session.cu +130/-…`,
`motioncorr_runner.cpp +195/-…`.

The overlap is substantive, not incidental:

- PR93 rewrites `cudaAlignPatchDevice` by hoisting **the same eight device buffers and
  the cuFFT plan** I convert to per-call scoped ownership into a process-static
  `PatchAlignCache` with its own `release()`, plus an `AlignCacheFailureCleanup` guard
  and a `FrameStagingCleanup` for the wrapper's `d_Fframes`. That is an **independent
  and mutually exclusive fix for F1 and F2.** Whichever lands first, the other's
  version of those two fixes becomes dead code and must be redone against the survivor.
- PR93 `#undef`s and redefines `HANDLE_ERROR` and `CUFFT_CHECK` in that file. My ADR's
  rationale is phrased around the fact that at `4c952b3f` the file does *not* do this;
  that sentence needs rewording if PR93 lands first.
- PR93's `preparePatchInVram` hunk overlaps my F3 hunk in the same function.

**Recommended order:** F3, F4, F5, F6 and both new tests are independent of PR93 and
can land either way. F1 and F2 should be reconciled with whichever of the two is
merged first, not stacked blindly. I have not rebased onto PR93 and am not requesting
a merge.

## Changed files

Production:
- `src/acc/cuda/cuda_alignpatch.cu` — F1, F2 scoped ownership of buffers/plan/events
- `src/acc/cuda/cuda_movie_session.cu` — F3, F4 truthful cache bookkeeping, clear before free
- `src/motioncorr_runner.cpp` — F5 retry shift reset, F6 poisoned-context classifier
- `src/motioncorr_runner.h` — one `friend` declaration for the test control (emits no code)

Tests and build:
- `tests/test_patch_retry_state.cpp` (new, CPU), `tests/cuda_fault_matrix.cpp` (new, GPU)
- `CMakeLists.txt` — registers both

Docs and evidence:
- `agents/designs/issue_69_cuda_failure_contracts.md`, `docs/issue69/**`, `WORKER_STATUS.md`

## Latest test commands and results

`cpu64`, cores 32-63, `flock /tmp/motioncorr-issue96-cpu-validation.lock`,
`-DCMAKE_BUILD_TYPE=Release` verified as `-O3 -DNDEBUG` in `flags.make`:

| Command | Result |
|---|---|
| `ctest --output-on-failure` on base `4c952b3f` | 13/13 passed |
| `ctest --output-on-failure` on candidate | 14/14 passed |
| `build-cand/patch_retry_state` | passed; truth anchor 0.063 px, ratio B/A = 2.0000, sum residual 0 |
| `compare_cpu_arms.py base cand synthetic_movie.tiff` | 10 files, 262,144 pixels, 0 differing; negative control reported exactly the 2 perturbed files |
| preprocessed-TU comparison, base vs candidate | only 1 friend declaration and 10 `__LINE__` values differ; negative control detects an injected line |

`4GPUs`, `taskset -c 96-103`, `-j8`, under `flock /tmp/motioncorr-bench.lock`,
**compile only, nothing executed on a device**:

| Command | Result |
|---|---|
| `cmake -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON && cmake --build -j8` | configure=0, build=0, CUDA 12.8; zero warnings in changed files; all 11 `__wrap_` symbols resolved in `cuda_fault_matrix` |

Evidence files: `docs/issue69/evidence/`.

## Resource context, as required by the resource update

- `cpu64` is 2 NUMA nodes: node0 = cores 0-31, node1 = cores 32-63, `numactl` available.
  My validation lane used **cores 32-63**, which is node-local (node1/socket1), so no
  cross-node memory traffic. No whole-host 64-core run was made, so the measurement lock
  was never needed.
- Recorded interference on `cpu64`, **not altered**: two unrestricted `ctffind`
  processes at ~100% CPU each, running 49 and 47 days. A concurrent `motioncorr` from
  another round96 worker was also observed. Topology, policy and the interference
  snapshot: `docs/issue69/evidence/cpu-resource-policy.txt`.
- `4GPUs` compile used `taskset -c 96-103`, a subset of the round's aggregate 96-111 /
  node1 budget, affinity read back from `/proc`. No GPU UUID is recorded for it because
  nothing was executed on a device. The GPU plan now requires cores, cpuset, NUMA policy
  and the actual GPU UUID for every run that does touch a device.
- `WORKER_RESOURCE_UPDATE.md` was dropped into this worktree by the orchestrator and was
  briefly committed by a `git add -A`; it has been untracked so the PR does not carry an
  unrelated coordination file. The file itself is left on disk untouched.

## Active PID / job / allocation

None. Both detached jobs completed and released their locks.

## Blockers

None blocking the code. Three evidence layers are blocked on a GPU slot.

## NEEDS_GPU

**Requested, not submitted.** #26 owns this round's initial GPU benchmark slot. Waiting
for Codex monitoring to assign one. Exact commands, resources and locks:
`docs/issue69/gpu_plan.md`.

- **What:** (1) `build/cuda_fault_matrix` — bounded fault matrix, already built and
  linked, ~5 min; (2) `build/cuda_wrapper_upload_failure` — existing control, re-run for
  no-regression; (3) forced-nonconvergence end-to-end witness for the retry fix, base vs
  candidate with a lowered `--max_iter` (a normal option, no fault switch, no source
  change), plus the default-`max_iter` control that must be identical; (4) healthy
  same-backend 24-movie CUDA control.
- **Resources:** one A100 on `4GPUs` or a SCARF allocation; `taskset -c 96-103`;
  `flock -w 2400 /tmp/motioncorr-bench.lock`; ~30 min total.
- **Correctness only.** No timing number is produced, so no quiescence gate is needed;
  the bench lock is still required because the work perturbs whoever is measuring.
- **Device safety:** the new code only reads the pending CUDA error. No
  `cudaDeviceReset`, no global cache drop, no other process or device touched.

## Next step

Fold in the two independent read-only reviews, then run the GPU layers once a slot is
assigned and publish the fault-matrix table. The PR stays draft until then.

## Model comparison record

- Model: `claude-opus-5`, high effort. No routing error; no model substitution.
- Interventions/revisions by the user: 0 after the initial assignment.
- Subagents: 2, both read-only, launched concurrently (code review; spec/scope/license).
- Tool or permission failures: 1 local quoting error writing a heredoc over ssh,
  self-corrected by writing the file locally and copying it.
- Revisions to my own work: 2 substantive — the CPU control's first truth assertion was
  wrong in premise (a single iteration estimates against the mean of the other frames,
  not the truth) and was replaced with a converged anchor; the same-backend comparator
  initially reported 9 spurious differences from unnormalised output-root paths and its
  negative control initially over-reported, both tightened.
- Bugs found in existing code: 6 (F1-F6), of which F1 and F5 are the substantive ones.
- Gates verified by actual execution: CPU build and 14/14 CTest, the retry-state
  contract, same-backend CPU output with a negative control, preprocessed-TU identity
  with a negative control, and a clean CUDA compile with interposition resolved.
- Gates not run: the entire GPU fault matrix, the end-to-end retry witness, and the
  24-movie CUDA control.
- Diff size vs `4c952b3f`: see `git diff --stat`; production changes are ~160 lines
  across four files, the rest is tests, evidence and documentation.
- Elapsed active time: roughly 75 minutes of wall clock from assignment to draft PR.
- Tokens/cost: not observable from here, so not reported.
