# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: grok-4.3 (kept)  
**Task class**: correctness (tiny scoped fix)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: Draft PR #100 ready for independent review (https://github.com/KingAlejandro/MotionCorr-standalone/pull/100); core fix complete and pushed; test addition reverted to obey strict private-API / tiny-PR boundary; milestone comment posted on #97.  
**Changed files**: src/motioncorr_runner.cpp (5 lines net), planning docs; test addition reverted (private method would require header change — out of tiny scope)  
**Blockers**: None (CPU-only; GPU waits for #26 coordinated slot)  
**NEEDS_GPU**: No — prepare only; wait for issue26 slot per COMMON.md  
**Next step**: Await independent review of PR #100. If approved, maintainer merges. GPU work remains blocked until #26 slot. All other tasks preserved.

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
- (to be populated after implementation)

---
*Published at session start per task-97.md directive. Model kept as grok-4.3.*
