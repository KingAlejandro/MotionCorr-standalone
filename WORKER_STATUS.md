# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: mixed — grok-4.3 implementation (fix + planning), Opus 5 high review/fix (helper extraction, committed regression, cpu64 validation, corrections)  
**Task class**: correctness (scoped fix + CPU validation evidence)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: Review pass complete. Two independent read-only reviews received and their valid findings applied (both-axes witness, ctest un-gated from Python, ADR reconciled, SOURCE_MANIFEST provenance entry, symmetric guard). Draft PR #100 retained.
**Changed files**: `src/motioncorr_runner.cpp`, `src/motioncorr_runner.h`, `tests/test_runner_numerics.cpp`, `CMakeLists.txt`, `SOURCE_MANIFEST.txt`, `docs/issue97_cpu_evidence/*`, ADR, whitelist, this file.
**Blockers**: none blocking. The option-on path deliberately diverges from pinned RELION `ad0b230`; documented for the maintainer rather than gated on a second approval. GPU remains deferred to the #26 slot.
**NEEDS_GPU**: Yes, deferred — CUDA option-on path unverified. Request: one GPU slot to run the same 4-arm option-off/on comparison with `_CUDA_ENABLED`. Waiting on the #26 coordinated slot; no GPU submitted.
**Next step**: maintainer decision on the documented option-on divergence from pinned RELION `ad0b230`. PR stays draft; GPU still deferred to #26.

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
- No GPU submission until #26 slot.
- All per COMMON.md: WORKER_STATUS updates, progress comments, small commits, draft PR.

## Active PIDs / jobs
- None yet.

## Latest test commands / results
- `make -j8 motioncorr_core` (Release, forced fresh TU rebuild) — PASS, pre-existing warnings only.
- `/tmp/issue97_verify` — 4 witnesses against real `interpolateShifts`; W1 reproduces the archived control exactly; frame0==0 exact; relative displacements bit-exact. EXIT=0.
- `/tmp/issue97_control` — zero-origin control old==new bitwise (3 cases, 2 non-trivial); nonzero-origin control differs. EXIT=0.
- Upstream `ad0b230` fetched and diffed: defect inherited verbatim.
- NOT run: end-to-end movie, CUDA, RELION downstream. See ADR.

---
*Published at session start per task-97.md directive. Model kept as grok-4.3.*

## cpu64 validation summary (2026-09-28)

Full evidence: `docs/issue97_cpu_evidence/` (raw logs, script, comparator).

- Lane CPUs 40-55, verified node1/socket1-local, no SMT siblings; `membind=1`;
  `Cpus_allowed_list: 40-55` confirmed on a pinned child. Held constant across all arms.
- Serialized under `flock /tmp/motioncorr-issue96-cpu-validation.lock`.
- Interference recorded: `ctffind` ~100% on CPU 58 (node1, outside the cpuset).
  Host not idle. **No timing claim is made from these runs.**
- Two separate source trees (base `4c952b3`, fixed `792f1e6`), Release, `-j16`.
  Binaries: base `b27f7351...`, fixed `9fb0c0be...`.
- Unit: `RunnerInterpolateRecenter` passes on fixed, absent on base.
  Full suite 14/14 fixed, 13/13 base. Mutation test fails as required when reverted.
- Integration, default-off: output MRC pixel payload and per-movie STAR
  **byte-identical** between base and fixed, on both the synthetic fixture and the
  full-size real movie (56,955,920-byte payload).
- Integration, option-on: intentionally differs — 99.98% of pixels on the real movie
  (max abs 22.56 on range 51.42), 611/777 STAR value lines. Joint
  `corrected_micrographs.star` accumulated motion is **equal** in both arms.
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
