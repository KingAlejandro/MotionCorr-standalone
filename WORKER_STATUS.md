# WORKER_STATUS — issue #69

| Field | Value |
|---|---|
| Issue | #69 "Make CUDA resource failures leak-free and resume-safe" |
| Model | `claude-opus-5`, high effort (no routing error observed) |
| Task class | correctness |
| Phase | five review passes against the same two agents; two returned DELTA_BLOCKED and both blocks were real; latest source confirmed at `f2219fb6`; non-blocking items handed off unfixed; draft PR open; waiting on a GPU slot |
| Base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Head | source frozen at `e191aab`; docs head `f2219fb6`. `git diff e191aab HEAD -- src tests CMakeLists.txt` is empty |
| Branch | `round96/69-claude-opus-5` |
| Worktree | isolated T3 worktree; no other task's files touched |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/107 (draft) |

## Whitelist — files this task may change

- `src/acc/cuda/cuda_alignpatch.cu` (F1, F2)
- `src/acc/cuda/cuda_movie_session.cu` (F3, F4)
- `src/motioncorr_runner.cpp` (F5, F6, F7 — **shared file**, see coordination)
- `src/motioncorr_runner.h` (test access only; one `friend` line, emits no code)
- `src/acc/cuda/cuda_failure_state.h` (**new production header**, the monotonic
  poisoning latch and diagnostic provenance for the Codex P1 fix)
- `src/acc/cuda/cuda_scoped_resources.h` (**new production header**, fixed-capacity
  scoped owners for the Codex P2 fix)
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
- `src/acc/cuda/cuda_failure_state.h` — new, monotonic poisoning latch (Codex P1)
- `src/acc/cuda/cuda_scoped_resources.h` — new, fixed-capacity owners (Codex P2)

The whitelist failed to catch these two new `src/` files when they were created, for
the second round running, and the spec review caught it again. The list above is now
seven production files, not five.

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

## Review rounds — two, both with findings

**Round 2** re-ran the same two agents against pinned head `92437fa9`. Verdicts at that
head: CHANGES_REQUESTED and SPEC_CONFORMANCE_FAILED / LICENCE_PASSED. All nine round-1
code findings verified fixed and no new production defect found; the blocks were five
evidence and documentation items, three of them mine:

- the untracking of `WORKER_RESOURCE_UPDATE.md` had **silently regressed** — re-added
  by a `git add -A` in the commit titled "address review findings", while this file
  asserted the removal had held. Untracked again and added to `.git/info/exclude`;
  verified `git add -A` no longer re-adds it;
- `#include <sstream>` escaped the CUDA guard, falsifying RESULTS §4's premise in the
  same commit that relabelled §3 as a control for catching escaped guards;
- the classifier raised the production build's minimum CUDA version with no floor in
  `find_package`;
- `reloc_check.sh` could print a confident "0" on its own failure;
- the PR93 disclosure was wrong on file count, diff magnitudes and F3's independence.

### Verdict history, adverse verdicts included

| Pass | Head | Code reviewer | Spec reviewer |
|---|---|---|---|
| 1 full | `75c21df` / `d04657d` | CHANGES_REQUESTED | SPEC_CONFORMANCE_FAILED / LICENCE_PASSED |
| 2 full | `92437fa9` | CHANGES_REQUESTED | SPEC_CONFORMANCE_FAILED / LICENCE_PASSED |
| 3 delta | `934779b7` | DELTA_CONFIRMED | DELTA_CONFIRMED / LICENCE_PASSED |
| 4 delta | `0a90a4b7` | **DELTA_BLOCKED** | **DELTA_BLOCKED** / LICENCE_PASSED |
| 5 confirm-only | `f2219fb6` | DELTA_CONFIRMED | **DELTA_BLOCKED** (two doc lines) |
| 6 confirm-only | `d104aa44` | (source unchanged since `e191aab`, covered by pass 5) | DELTA_CONFIRMED / LICENCE_PASSED |

An earlier version of this table listed only the confirmations. Pass 4 was blocked by
both reviewers and both blocks were real: the code reviewer found that my lost-error
fix had introduced a masking regression strictly worse than the head it replaced, and
the spec reviewer found a binary hash in RESULTS that the evidence contradicted. A
verdict history that records confirmations and omits the adverse verdicts is not a
history.

**Round 3 (delta).** The same two reviewers were resumed for a bounded confirmation of
`92437fa9 -> 934779b7`, covering the CUDA-version guard, the `<sstream>` guard and
regenerated TU evidence, the fail-closed relocation harness, the coordination-file
exclusion and the corrected PR93 disclosure. Both returned **DELTA_CONFIRMED** naming
`934779b7` explicitly, plus **LICENCE_PASSED**. No blocking defect. Verdicts published
on #69 and PR #107.

Ten non-blocking items were recorded and **deliberately not fixed**, so the verdicts
bind to the exact reviewed head. They are listed in the published comment. The two I
would fix first: `docs/issue69/RESULTS.md` never mentions the early-binning control at
all (an omission -- three other documents state it), and RESULTS §4's "this control is
why it was caught" is generous, because the escaped `#include` was found by a reviewer
reading the source, not by the control, which was not re-run.

**Source is frozen at `934779b7`**, which is the head both verdicts cover.

## Round 1 — done

Two read-only agents (code; spec/scope/licence) were run concurrently. Verdicts were
`CHANGES_REQUESTED` and `SPEC_CONFORMANCE_FAILED` / `LICENCE_PASSED`. Eleven findings
were acted on and are recorded in `docs/issue69/RESULTS.md` §7 and in commits
`18a9983`, `d50147b` and `192c580`. Three were defects in this branch's own work: an
indeterminate-member read in the new control, a leak the new `REPORT_ERROR` introduced
into the loop this issue de-leaks, and a fault matrix that claimed a test that did not
exist and would have mis-scored its first real run. Three were documentation
overclaims, now corrected rather than softened.

## Hand-off

`docs/issue69/HANDOFF.md` lists all 20 known-unfixed items and the 6 unrun layers, so
none of them depends on this transcript surviving. The spec reviewer's sweep at
`d104aa44` found one further instance of the stale-quotation class (§5's classifier
block, stale-but-true and under-claiming); it is item 14 and was deliberately not
actioned, per that reviewer's own guidance to refresh it when the section is next
touched.

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
- Revisions to my own work: 10 substantive. Two found by me before any review: — the CPU control's first truth assertion was
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
- Final review verdict: CHANGES_REQUESTED and SPEC_CONFORMANCE_FAILED / LICENCE_PASSED
  at head `92437fa9`. Those are pre-fix for round 2 as well; the current head has not
  been re-reviewed and carries no verdict.
- GPU slot: #26 announced release and the bench lock is observably free with all four
  A100s idle, but **no slot has been assigned to this task**, so no GPU execution has
  occurred. Availability is not authorization.
- Review passes: 5 (full, full, delta, delta, confirm-only), all against the same two
  agents; no new agents were ever spawned. Two passes returned DELTA_BLOCKED and both
  blocks were real. See the verdict history table above.
- Defects the reviews found in **my own work across the whole task: 13**, of which two
  were regressions of fixes I had already reported as complete (the re-added
  coordination file, and the masking regression inside the lost-error fix), and three
  were stale figures in documents asserting measurements the tree contradicted.
- **Unrun and unclaimed:** bounded fault matrix, forced-nonconvergence witness,
  early-binning streaming control, all-24 same-backend CUDA control, and **any build on
  a CUDA toolkit older than 12.8** -- the `CUDART_VERSION` guards are reasoned, not
  exercised.
- Tokens/cost: not observable from here, so not reported.
