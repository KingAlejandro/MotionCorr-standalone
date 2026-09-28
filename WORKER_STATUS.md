# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: mixed — grok-4.3 implementation (fix + planning), Opus 5 high review/fix (helper extraction, committed regression, cpu64 validation, corrections)  
**Task class**: correctness (scoped fix + CPU validation evidence)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: Review pass complete. Two independent read-only reviews received and their valid findings applied (both-axes witness, ctest un-gated from Python, ADR reconciled, SOURCE_MANIFEST provenance entry, symmetric guard). Draft PR #100 retained.
**Changed files**: `src/motioncorr_runner.cpp`, `src/motioncorr_runner.h`, `tests/test_runner_numerics.cpp`, `CMakeLists.txt`, `SOURCE_MANIFEST.txt`, `docs/issue97_cpu_evidence/*`, ADR, whitelist, this file.
**Blockers**: none blocking. The option-on path deliberately diverges from pinned RELION `ad0b230`; documented for the maintainer rather than gated on a second approval. GPU remains deferred to the coordinated shared-GPU slot, now owned by #53.
**NEEDS_GPU**: Yes, deferred — the CUDA option-on path is unverified. Request: one slot to run the same 4-arm option-off/on comparison with `_CUDA_ENABLED`. Not submitted; #53 owns the shared-GPU slot.
**Next step**: maintainer decision on the documented option-on divergence from pinned RELION `ad0b230`. PR stays draft; GPU still deferred to the shared-GPU slot owned by #53.

## Scoped plan (per issue-97.json + task-97.md + COMMON.md)
- Own ONLY the saved-first-frame-origin recentering fix.
- Read archived control/hash from issue-97.json, reproduce with deterministic nonzero first-frame offset on production path (not expression-only control).
- Verify exact simple relative displacement truth + justified float tolerance.
- Keep option-off CPU (and eventual CUDA) controls EXACT; option-on change explicit as bugfix.
- No peak-tie/noise/perf changes; check pinned RELION provenance.
- Tiny separate PR; independent review; bounded tests only.
- Preserve other tasks/worktrees; no merges; no scope creep.
- Record NUMA/CPU topology, actual Cpus_allowed_list etc. per COMMON addendum.
- Evidence: hashes, commands, outputs, intentional diff only on option-on.

## Evidence commitments
- Source hash of reproducer + actual MotionCorr build.
- CPU-only integration first.
- No GPU submission until the coordinated shared-GPU slot, now owned by #53 (previously #26).
- All per COMMON.md: WORKER_STATUS updates, progress comments, small commits, draft PR.

## Latest test commands / results

Superseded by "cpu64 validation summary" below, which is authoritative. The earlier
`/tmp/issue97_verify` and `/tmp/issue97_control` harnesses were deliberately not committed
and are replaced by the committed `RunnerInterpolateRecenter` regression; their results are
no longer cited anywhere. The one surviving item from that phase:

- Upstream `ad0b230` fetched and diffed: the defect is inherited verbatim. Recorded in
  `SOURCE_MANIFEST.txt` and in the ADR.

## Active PIDs / jobs
- None. The cpu64 validation job completed; its lock was released.

## cpu64 validation summary (2026-09-28)

Full evidence: `docs/issue97_cpu_evidence/` (raw logs, script, comparator).

- Lane CPUs 40-55, verified node1/socket1-local, no SMT siblings; `membind=1`;
  `Cpus_allowed_list: 40-55` confirmed on a pinned child. Held constant across all arms.
- Serialized under `flock /tmp/motioncorr-issue96-cpu-validation.lock`.
- Interference recorded: two `ctffind` at 99.9% on CPUs 32 and 33 (node1, outside the cpuset).
  Host not idle. **No timing claim is made from these runs.**
- Two separate source trees (base `4c952b3`, fixed `85dd1f9`), Release, `-j16`.
  Binaries: base `b27f7351...`, fixed `cd9a7316...`. HEAD `e8f1c562` differs from `85dd1f9`
  in docs only, so the evidence describes the final production source.
- Unit: `RunnerInterpolateRecenter` passes on fixed, absent on base.
  Full suite 14/14 fixed, 13/13 base. Mutation test fails as required when reverted.
- Integration, default-off: output MRC pixel payload and per-movie STAR
  **byte-identical** between base and fixed, on both the synthetic fixture and the
  full-size real movie (56,955,920-byte payload).
- Integration, option-on: intentionally differs — 99.98% of pixels on the real movie
  (max abs 22.56 on range 51.42), 611/779 STAR lines. Joint `corrected_micrographs.star`
  accumulated motion is equal in both arms — **now measured** (`followup_measurements.log`)
  after review found the original comparator structurally could not see those values.
- Not established: any scientific/downstream claim, timings, CUDA, >1 real movie.

## Independent review (2026-09-28)

Two bounded read-only reviewers, run concurrently, no recursion.

Code/correctness reviewer: **CHANGES_REQUESTED**. Found no fault in `src/` — confirmed the
extracted method is semantically identical (the `size_t` bound provably equals `n_frames` at the
only call site), and independently recomputed all four witnesses from the source formula. It also
found corroboration I had missed: `motioncorr_runner.cpp:3122-3128` and
`acc/cuda/cuda_alignpatch.cu:393-398` already implement this same recentering as *descending*
loops with the comment `// do frame 0 last!`, so the intended semantics are unambiguous and the
ascending loop was the outlier.

Spec/license reviewer: **SPEC_CONFORMANCE_FAILED**, **LICENSE_COMPLIANCE_PASSED** (advisory).
Two of its findings were already resolved in `092b796` before it reported (whitelist amendment,
executed option-off control).

Applied from both:
- Added nonzero-origin-on-both-axes witnesses. This was the substantive one: every bug-exposing
  witness previously had `yshifts` all-zero, so the `origin_y` half of the fix was untested and a
  Y-only regression would have kept the suite green. Now mutation-proven per axis.
- Added negative X slope and unequal-last-group witnesses, and an empty-input case.
- Moved `RunnerInterpolateRecenter` out of the `if(Python3_Interpreter_FOUND)` block and switched
  to `$<TARGET_FILE:>`; it was a pure C++ test that would have silently vanished on a
  Python-less host.
- Reconciled the ADR, which still claimed at HEAD that no test was committed, and removed hashes
  pointing at a tree that no longer exists.
- Added the `Local change:` entry to `SOURCE_MANIFEST.txt` for the deliberate upstream divergence.
- Made `interpolateShifts` static and added a symmetric length guard to the now-public helper.

Not applied, with reasons:
- *Drop `WORKER_STATUS.md` / `issue97-whitelist.md` from the merge (no precedent at repo root).*
  Kept: COMMON.md mandates WORKER_STATUS for this round. Flagged for the maintainer to drop at
  merge if unwanted — they are process artifacts, not product.
- *`--first_frame_sum > 1` arm.* Not run; declared unrun in the ADR instead.
