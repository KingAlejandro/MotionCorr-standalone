# WORKER_STATUS — issue #99, round 96

| Field | Value |
|---|---|
| Issue | #99 — fail-closed MRC image writes and completion |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | correctness |
| Model routing | `claude-opus-5[1m]` as assigned; no routing error, no substitution |
| Phase | 5 — PR A implemented, independently reviewed, review findings applied, re-validated on cpu64; draft PR open and reviewable |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `095f137` |
| Branch | `round96/99-claude-opus-5` (pushed) |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-a01709b1` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/105 (draft) |
| Progress comments | [plan](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99#issuecomment-5860981003), [executed results](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99#issuecomment-5861082448) |

## Scope delivered (PR A)

Reproduced, then propagated. Two defects, not one: `writeMRC` discarded every
`fwrite`/`fseek` result (and `_write` discarded `writeMRC`'s, so the existing `err < 0`
guard was dead on the MRC branches); and the only flush in the chain, `fclose` inside
`~fImageHandler`, reported by throwing from an implicitly `noexcept` destructor, i.e.
`std::terminate`. PR B (temporary paths, publication ordering, completion identity) is
designed and deliberately not started.

ADR and ownership trace: `agents/designs/issue_99_fail_closed_image_writes.md`.
Evidence: `docs/issue99_write_faults/REPORT.md`.

## Changed files (matches the ADR §6 whitelist)

- production: `src/rwMRC.h`, `src/image.h`, `src/micrograph_model.cpp`
- tests: `tests/test_image_write_faults.cpp`, `tests/test_write_faults.py`,
  `CMakeLists.txt` (one `add_executable`, two `add_test`)
- docs: `agents/designs/issue_99_fail_closed_image_writes.md`,
  `docs/issue99_write_faults/`, `WORKER_STATUS.md`

`src/motioncorr_runner.cpp` deliberately untouched — #91's per-movie failure contract
already provides what this needed to raise into, and #97/#98/#69 hold the other locks.

Diff vs base: 5 production/test files plus docs; `git diff --stat 4c952b3f..eda0350 -- src/`
is 3 files.

## Latest test commands and results

Host `small-refmac-machine` (cpu64), `taskset -c 32-63`, under
`flock /tmp/motioncorr-issue96-cpu-validation.lock`, Release `-O3 -DNDEBUG`, CUDA=OFF,
`--parallel 16`. Scripts as executed are committed at
`docs/issue99_write_faults/cpu_validation.sh` and `cpu_evidence.sh`.

| Run | Result |
|---|---|
| `ctest --output-on-failure -j 4`, candidate `f83a466` | **15/15 passed**, including the two new tests |
| `ctest -R 'ImageWriteFaults\|WriteFaults'`, negative control `dddc676` (pre-fix main + tests only) | **both fail**, exit 8 — one by assertion, one by `SIGABRT` from the destructor throw |
| Pre-fix end-to-end fault run | exit **0**, `b.mrc` truncated to 599040 B, `b.star` written, joint STAR and `logfile.pdf` published — the false completion, reproduced |
| Post-fix, same fault | exit **1** (status, not signal), names product/stage/movie, no `b.star`, healthy movie byte-identical, joint STAR withheld; repaired retry exit 0 |
| Healthy parity, pre- vs post-fix | `mov/p.mrc`, `mov/p.star`, `corrected_micrographs.star` byte-identical by whole-file SHA-256 |

Two files differ in the parity comparison and both are recorded rather than omitted: one
line of measured wall time in the per-movie `.log`, and the pre-existing ghostscript PDF
nondeterminism in `logfile.pdf`, which is preserved.

Binary hashes: candidate `motioncorr` `59936bbe…`, pre-fix `motioncorr` `b9d16a2d…`;
input `synthetic_movie.tiff` `95b5f0d3…`.

## Unrun / not claimed

- **Short header write as a distinct observation: unrun.** Measured, not assumed — with
  `st_blksize` 4096 a 1024-byte header never reaches `write(2)` inside its own `fwrite`, so
  even `RLIMIT_FSIZE=0` surfaces at the next flush point. Probe committed.
- **No crash-durability claim.** No `fsync` added.
- **No GPU run, no timing of any kind.**
- PR A leaves a truncated file on disk; safe today only via `completeMrc` resume
  validation, which the retry phase demonstrates.

## Independent review (COMMON.md requirement), both read-only

Two bounded read-only reviewers, run concurrently, neither able to modify anything.

**Code/correctness review.** Clean on leaks, double-frees, double-close, success-path and
read-path behaviour, `errno` handling, and — checked by brace nesting over all thirteen
`write(` sites in `src/` — on throws inside OpenMP structured blocks. Applied its
findings in `b0e10f5`: `strerror`'s static buffer replaced with
`std::generic_category().message()` (the only new shared state); the sticky `ferror`
check dropped from `mrcWriteBlock`; the handler-reuse close taught to name its file; the
reuse guard extended to `ftiff` (a pre-existing fd leak the rewritten `releaseHandles`
would otherwise have fixed); the per-slice label made lazy. Declined one: `writeIMAGIC`'s
unchecked return, because that function is a stub that unconditionally throws.

**Spec-conformance and license review.** `SPEC_CONFORMANCE_PASSED`, `LICENSE_PASSED`
(GPL-2.0, no vendored code, no new dependency, POSIX libc only). All eight changed files
inside the ADR §6 whitelist, nothing outside it, no CUDA/gate/default/perf change. Found
that the destructor test case was vacuous — fixed in `f83a466`, and fixing it exposed a
second fault the review had not seen: the paired form used a post-fix API, so the
negative control silently degraded to `Not Run` rather than failing. Both are now
corrected and the control demonstrably compiles and runs on the pre-fix tree.
It also corrected the ADR's claim that `micrograph_model.cpp` is collision-free with
respect to #98 (#98's defect-text detection lives in the same file, ~50 lines away).

## Observation for #66/#69, not fixed here

`src/motioncorr_runner.cpp:3207` — `REPORT_ERROR("Shouldn't happen.")` sits inside the
`#pragma omp parallel for` opened at `:3183`. An exception leaving an OpenMP structured
block is undefined behaviour and calls `std::terminate`, the same class of defect #91
fixed for the frame-read region. Pre-existing and untouched by this branch; that file is
out of this issue's whitelist and is held by sibling tasks.

## Active jobs / allocations

None. All cpu64 jobs completed; the validation lock is released.

## Blockers

None.

## NEEDS_GPU

**Not required.** Every fault is injected at the host stdio layer and is
backend-independent; the CUDA path reaches the same `Image::write`. No CUDA arithmetic,
gate or output default is touched, so the #90/#91 same-backend evidence still stands
unchanged and was not re-run. #26 owns this round's GPU slot.

## Next step

Hand the draft PR to integration for a maintainer decision. Do not merge. PR B stays
designed-and-unstarted in ADR §7.
