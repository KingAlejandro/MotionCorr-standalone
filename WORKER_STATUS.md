# WORKER_STATUS — issue #99, round 96

| Field | Value |
|---|---|
| Issue | #99 — fail-closed MRC image writes and completion |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | correctness |
| Phase | 1 — trace complete, ADR and whitelist published; implementation starting |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| Branch | `round96/99-claude-opus-5` |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-a01709b1` |
| PR | not yet opened |

## Scope (PR A only)

Reproduce deterministic short/failed write and delayed flush/close faults, then propagate
them so a failed image write becomes a named per-movie failure instead of a silently
truncated but "completed" micrograph. PR B (temporary paths, publication ordering,
completion identity/manifest) is designed in the ADR and explicitly deferred.

ADR, ownership trace and changed-file whitelist:
`agents/designs/issue_99_fail_closed_image_writes.md`.

## Changed files

Planned, per the ADR whitelist:

- production: `src/rwMRC.h`, `src/image.h`, `src/micrograph_model.cpp`
- tests: `tests/test_image_write_faults.cpp`, `tests/test_write_faults.py`, two
  `add_test` entries and one `add_executable` in `CMakeLists.txt`
- docs: `agents/designs/issue_99_fail_closed_image_writes.md`, `docs/issue99_write_faults/`,
  `WORKER_STATUS.md`

`src/motioncorr_runner.cpp` is deliberately **not** in the whitelist: #91 already landed the
per-movie failure contract this issue needs to raise into, and #97/#98/#69 hold the other
locks on that file.

Actually changed so far: `agents/designs/issue_99_fail_closed_image_writes.md`,
`WORKER_STATUS.md`.

## Latest test commands and results

None executed yet. Nothing below is claimed as passing.

## Active jobs / allocations

None.

## Blockers

None.

## NEEDS_GPU

**Not required for PR A.** Every fault in this issue is injected at the host stdio layer and
is backend-independent; the CUDA path reaches the same `Image::write`. The healthy-bytes
CUDA same-backend regression is the pre-existing #90/#91 evidence, which PR A must not
change and does not re-run. If integration later wants a CUDA-backend re-run of the two new
CTests, that is a slot request for #66 integration, not a measurement, and #26 owns this
round's GPU slot regardless.

## Next step

Implement D1/D2/D3 per the ADR, then build Release on cpu64 under
`flock /tmp/motioncorr-issue96-cpu-validation.lock` with `taskset -c 32-63`, parallelism
<= 16, and run the new plus existing CPU CTests.
