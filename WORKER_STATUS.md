# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: grok-4.3 (kept)  
**Task class**: correctness (tiny scoped fix)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: Planning complete; ADR/whitelist published; GitHub comment posted (https://github.com/KingAlejandro/MotionCorr-standalone/issues/97#issuecomment-5860947483); now implementing minimal fix + reproduction on real path  
**Changed files**: (none yet)  
**Blockers**: None (CPU-only; GPU waits for #26 coordinated slot)  
**NEEDS_GPU**: No — prepare only; wait for issue26 slot per COMMON.md  
**Next step**: Write short correctness ADR + whitelist; publish GitHub progress comment on #97; verify call-site; implement minimal fix + bounded regression test.

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
