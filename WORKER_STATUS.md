# WORKER_STATUS — issue #69

| Field | Value |
|---|---|
| Issue | #69 "Make CUDA resource failures leak-free and resume-safe" |
| Model | `claude-opus-5`, high effort (no routing error observed) |
| Task class | correctness |
| Phase | implemented, reviewed by two independent read-only agents, review findings folded in, revalidated; draft PR open; waiting on a GPU slot |
| Base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Head | `192c580` (plus this status update) |
| Branch | `round96/69-claude-opus-5` |
| Worktree | isolated T3 worktree; no other task's files touched |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/107 (draft) |

## Whitelist — files this task may change

- `src/acc/cuda/cuda_alignpatch.cu` (F1, F2)
- `src/acc/cuda/cuda_movie_session.cu` (F3, F4)
- `src/motioncorr_runner.cpp` (F5, F6, F7 — **shared file**, see coordination)
- `src/motioncorr_runner.h` (test access only; one `friend` line, emits no code)
- `src/acc/cuda/cuda_error_class.h` (**new production header**, added mid-round so the
  F6 predicate could be unit tested; `#ifdef _CUDA_ENABLED`-guarded, no new logic. It
  was not on the original whitelist and should have been added when it was created —
  the whitelist exists to catch exactly a new file appearing under `src/`)
- `tests/test_patch_retry_state.cpp` (new), `tests/cuda_error_class.cpp` (new),
  `tests/cuda_fault_matrix.cpp` (new, GPU)
- `CMakeLists.txt` (test registration and test-target link options only)
- `agents/designs/issue_69_cuda_failure_contracts.md`, `docs/issue69/**`, `WORKER_STATUS.md`

Not touched: allocators, `custom_allocator.cuh`, `acc_ptr.h`, FFT engine, numerical
gates, defaults, compiler flags, dependencies, any other issue's files.

## Coordination

`src/motioncorr_runner.cpp` is shared with #97/#98/#99. My edits are confined to the
local-patch block and one include. #99/#53 own completion/resume publication semantics;
I rely on the existing per-movie failure contract at `:626-645` rather than changing it.

### PR93 (#77) is a hard conflict, and it is not just textual

Flagged by the independent spec review; I under-reported it twice, and the corrected
version got two facts wrong, which the second-round code review caught. This is the
verified version. PR93 `fix/issue77-reviewed-kernels` head `4998599`, measured with
`git diff --numstat 4c952b3f 4998599`:

| File | PR93 | Also changed by me |
|---|---|---|
| `src/acc/cuda/cuda_alignpatch.cu` | +359 / -164 | yes (F1, F2) |
| `src/acc/cuda/cuda_movie_session.cu` | +92 / -38 | yes (F3, F4) |
| `src/motioncorr_runner.cpp` | +59 / -136 | yes (F5, F6, F7) |
| `src/motioncorr_runner.h` | +0 / -22 | yes (one `friend` line) |

So it is **four of my four** production files, not three — an earlier version of this
section said three, and also quoted insertions and deletions summed into a single `+N`
figure, which made `motioncorr_runner.cpp` read as `+195` against an actual `+59`.

The overlap is substantive, not incidental:

- PR93 rewrites `cudaAlignPatchDevice` by hoisting **the same eight device buffers and
  the cuFFT plan** I convert to per-call scoped ownership into a process-static
  `PatchAlignCache` with its own `release()`, plus an `AlignCacheFailureCleanup` guard
  and a `FrameStagingCleanup` for the wrapper's `d_Fframes`. That is an **independent
  and mutually exclusive fix for F1 and F2.**
- PR93 `#undef`s and redefines `HANDLE_ERROR` and `CUFFT_CHECK` in that file. My ADR's
  rationale is phrased around the fact that at `4c952b3f` the file does *not* do this;
  that sentence needs rewording if PR93 lands first.
- PR93's `cuda_movie_session.cu` hunk `@@ -653,31 +667,70 @@` rewrites the same patch
  cache block F3 rewrites, including its own free-and-replace restructuring and a new
  `cached_group_start` memcmp path. **F3 is therefore not independent either.**
- In `motioncorr_runner.h` PR93 only deletes the gain-cache block and `EERRenderer`
  forward declaration, a different region from my `friend` line, so that file should
  auto-merge.

**Recommended order, corrected.** **F1, F2 and F3** must be reconciled with whichever
of the two lands first — not stacked. **F4, F5, F6, F7 and both new tests are
independent**: `git diff 4c952b3f 4998599 -- src/motioncorr_runner.cpp` contains no hit
for `local_xshifts`, `d_patch_fcomplex_buffer`, `device_prep_ok`, `preparePatchInVram`
or `alignPatchDevice`, and PR93's `cuda_movie_session.cu` hunks skip
`releasePreprocessingBuffers` entirely. An earlier version of this section claimed F3
was independent three lines after stating that PR93 overlaps it; that contradiction is
resolved in favour of the overlap, which is the one I verified.

I have not rebased onto PR93 and am not requesting a merge.

## Changed files

Production:
- `src/acc/cuda/cuda_alignpatch.cu` — F1, F2 scoped ownership of buffers/plan/events
- `src/acc/cuda/cuda_movie_session.cu` — F3, F4 truthful cache bookkeeping, clear before free
- `src/motioncorr_runner.cpp` — F5 retry shift reset, F6 poisoned-context refusal,
  F7 scoped owner for the patch Fourier scratch
- `src/motioncorr_runner.h` — one `friend` declaration for the test control (emits no code)
- `src/acc/cuda/cuda_error_class.h` — new, the F6 predicate, extracted so it is testable

Tests and build:
- `tests/test_patch_retry_state.cpp` (new, CPU), `tests/cuda_error_class.cpp` (new,
  device-free), `tests/cuda_fault_matrix.cpp` (new, GPU)
- `CMakeLists.txt` — registers all three

Docs and evidence:
- `agents/designs/issue_69_cuda_failure_contracts.md`, `docs/issue69/**`, `WORKER_STATUS.md`

## Latest test commands and results

`cpu64`, cores 32-63, `flock /tmp/motioncorr-issue96-cpu-validation.lock`,
`-DCMAKE_BUILD_TYPE=Release` verified as `-O3 -DNDEBUG` in `flags.make`:

| Command | Result |
|---|---|
| `ctest --output-on-failure` on base `4c952b3f` | 13/13 passed |
| `ctest --output-on-failure` on candidate | 14/14 passed (re-run after review fixes: 14/14) |
| `build-cand/patch_retry_state` | passed; truth anchor 0.063 px, ratio B/A = 2.0000, sum residual 0 |
| `compare_cpu_arms.py base cand synthetic_movie.tiff` | 10 files, 262,144 pixels, 0 differing; negative control reported exactly the 2 perturbed files |
| preprocessed-TU comparison, base vs candidate | only 1 friend declaration and 10 `__LINE__` values differ; negative control detects an injected line |

`4GPUs`, `taskset -c 96-103`, `-j8`, under `flock /tmp/motioncorr-bench.lock`,
**compile only, nothing executed on a device**:

| Command | Result |
|---|---|
| `cmake -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80 -DBUILD_TESTING=ON && cmake --build -j8` | configure=0, build=0, CUDA 12.8; zero warnings in changed files; all three test binaries linked; 14 `__wrap_` symbols |
| `build/cuda_error_class` (device-free; creates no CUDA context) | 21 cases, 13 poisoning / 8 recoverable, 0 failures |
| `docs/issue69/harness/reloc_check.sh` (read-only disassembly) | every production call site in `cudaAlignPatchDevice`, `cudaAlignPatch` and `preparePatchInVram` routes through `__wrap_*`; **0** production sites reach a bare interposed symbol |

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

## Independent review — done

Two read-only agents (code; spec/scope/licence) were run concurrently. Verdicts were
`CHANGES_REQUESTED` and `SPEC_CONFORMANCE_FAILED` / `LICENCE_PASSED`. Eleven findings
were acted on and are recorded in `docs/issue69/RESULTS.md` §7 and in commits
`18a9983`, `d50147b` and `192c580`. Three were defects in this branch's own work: an
indeterminate-member read in the new control, a leak the new `REPORT_ERROR` introduced
into the loop this issue de-leaks, and a fault matrix that claimed a test that did not
exist and would have mis-scored its first real run. Three were documentation
overclaims, now corrected rather than softened.

## Next step

Run the GPU layers once a slot is assigned and publish the fault-matrix table. The PR
stays draft until then.

## Model comparison record

- Model: `claude-opus-5`, high effort. No routing error; no model substitution.
- Interventions/revisions by the user: 0 after the initial assignment.
- Subagents: 2, both read-only, launched concurrently (code review; spec/scope/licence).
  Both returned actionable defects; neither was a rubber stamp.
- Tool or permission failures: 1 local quoting error writing a heredoc over ssh,
  self-corrected by writing the file locally and copying it.
- Revisions to my own work: 5 substantive. Two found by me: — the CPU control's first truth assertion was
  wrong in premise (a single iteration estimates against the mean of the other frames,
  not the truth) and was replaced with a converged anchor; the same-backend comparator
  initially reported 9 spurious differences from unnormalised output-root paths and its
  negative control initially over-reported, both tightened.
- Bugs found in existing code: 7 (F1-F6 plus the pre-existing `d_patch_fcomplex_buffer`
  leak on `alignPatchDevice`'s throw, surfaced while fixing a review finding). F1 and
  F5 are the substantive ones.
- Gates verified by actual execution: CPU build and 14/14 CTest, the retry-state
  contract, same-backend CPU output with a negative control, preprocessed-TU identity
  with a negative control, and a clean CUDA compile with interposition resolved.
- Gates not run: the entire GPU fault matrix, the end-to-end retry witness, and the
  24-movie CUDA control.
- Diff size vs `4c952b3f`: see `git diff --stat`; production changes are ~200 lines
  across five files, the rest is tests, evidence and documentation.
- Elapsed active time: roughly 75 minutes to the draft PR, about 2 hours including the
  independent reviews and acting on them.
- Final review verdict: not re-run after the fixes. The two recorded verdicts are
  pre-fix and should be read that way.
- Tokens/cost: not observable from here, so not reported.
