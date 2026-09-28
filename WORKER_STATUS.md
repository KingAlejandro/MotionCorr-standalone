# WORKER_STATUS — issue #99, round 96

| Field | Value |
|---|---|
| Issue | #99 — fail-closed MRC image writes and completion |
| Model | `claude-opus-5` (high effort), Claude Code / T3 Code |
| Task class | correctness |
| Phase | 4 — PR A implemented, validated on cpu64, draft PR open; independent read-only review in flight |
| Base | `4c952b3f54479653512c4d208e09c9a8c02f3726` (current main) |
| Head | `eda0350` |
| Branch | `round96/99-claude-opus-5` (pushed) |
| Worktree | `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3code-a01709b1` |
| PR | https://github.com/KingAlejandro/MotionCorr-standalone/pull/105 (draft) |
| Progress comments | [issue #99 plan](https://github.com/KingAlejandro/MotionCorr-standalone/issues/99#issuecomment-5860981003) |

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
| `ctest --output-on-failure -j 4`, candidate `239320f` | **15/15 passed**, including the two new tests |
| `ctest -R 'ImageWriteFaults\|WriteFaults'`, negative control `39220ea` (pre-fix main + tests only) | **both fail**, exit 8 — one by assertion, one by `SIGABRT` from the destructor throw |
| Pre-fix end-to-end fault run | exit **0**, `b.mrc` truncated to 599040 B, `b.star` written, joint STAR and `logfile.pdf` published — the false completion, reproduced |
| Post-fix, same fault | exit **1** (status, not signal), names product/stage/movie, no `b.star`, healthy movie byte-identical, joint STAR withheld; repaired retry exit 0 |
| Healthy parity, pre- vs post-fix | `mov/p.mrc`, `mov/p.star`, `corrected_micrographs.star` byte-identical by whole-file SHA-256 |

Two files differ in the parity comparison and both are recorded rather than omitted: one
line of measured wall time in the per-movie `.log`, and the pre-existing ghostscript PDF
nondeterminism in `logfile.pdf`, which is preserved.

Binary hashes: candidate `motioncorr` `0d957e85…`, pre-fix `motioncorr` `b9d16a2d…`;
input `synthetic_movie.tiff` `95b5f0d3…`.

## Unrun / not claimed

- **Short header write as a distinct observation: unrun.** Measured, not assumed — with
  `st_blksize` 4096 a 1024-byte header never reaches `write(2)` inside its own `fwrite`, so
  even `RLIMIT_FSIZE=0` surfaces at the next flush point. Probe committed.
- **No crash-durability claim.** No `fsync` added.
- **No GPU run, no timing of any kind.**
- PR A leaves a truncated file on disk; safe today only via `completeMrc` resume
  validation, which the retry phase demonstrates.

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

Fold in the independent read-only code/spec/license review findings, then hand the draft
PR to integration. Do not merge.
