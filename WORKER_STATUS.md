# WORKER_STATUS.md — Issue #97 round96/97-grok-4-3 (grok-4.3)

**Issue**: #97 Fix --interpolate_shifts recentering origin  
**Model**: grok-4.3 (kept)  
**Task class**: correctness (tiny scoped fix)  
**Branch**: round96/97-grok-4-3 (isolated origin/main worktree)  
**Base commit**: 4c952b3f54479653512c4d208e09c9a8c02f3726 (main)  
**Phase**: Fix verified by execution against the real production symbol (see ADR "Verification status"). Upstream parity divergence identified — needs maintainer sign-off. PR #100 open as draft.
**Changed files**: `src/motioncorr_runner.cpp` (+5/-3), ADR, whitelist, this file. Test addition reverted — private method AND two of its three witnesses had wrong expected values (see ADR "Withdrawn test").
**Blockers**: Maintainer sign-off needed — the fix is a deliberate divergence from pinned RELION `ad0b230`, which AGENTS.md declares the parity baseline. GPU still waits on the #26 slot.
**NEEDS_GPU**: No — prepare only; wait for issue26 slot per COMMON.md  
**Next step**: Maintainer decision on the deliberate RELION-parity divergence (fix outright vs. gate behind a flag). Then independent review. GPU still blocked on #26 slot.

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
