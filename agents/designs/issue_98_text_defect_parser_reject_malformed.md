# ADR: Issue #98 — Reject malformed MotionCor2 text defect rectangles (grok-4.3)

**Date:** 2026-09-28
**Status:** Draft — scoped for implementation
**Issue:** #98
**Model/Task:** grok-4.3 / correctness

## Decision
Replace the unchecked `while (!f_defect.eof()) { int x,y,w,h; f_defect >> x >> y >> w >> h; ... }` pattern in the MotionCor2 text defect parser with an extraction-checked, bounded, overflow-safe implementation that:
- Initializes wide-integer temporaries before extraction.
- Uses extraction status as loop control or explicit post-extraction validation.
- Distinguishes clean EOF (after complete record + optional whitespace) from malformed token or trailing partial record.
- Clips rectangle bounds to image dimensions BEFORE any pixel iteration.
- Rejects zero-size, negative, or overflowed rectangles per policy derived from existing supported contract (empty files, comments).
- Adds timeout-guarded failing test against old parser behavior for huge off-image rectangles, then verifies fix.
- Preserves healthy-mask identity and valid defect-fixture semantics exactly.

## Rationale
The classic anti-pattern leaves `failbit` set without `eofbit`, causing non-advancing loop with uninitialized or stale rectangle values fed to downstream mask loops. This matches the audit finding and the verified `defect_stream.cpp` reproducer (exact bytes retained). Huge off-image rectangles must terminate boundedly (no billions of iterations). Policy for comments/empty/zero-size must be explicit and derived from contract, not invented.

## Scope (whitelist)
**In:**
- Only the text-defect rectangle parser code path (MotionCor2 format).
- Associated unit/CLI tests for parser robustness.
- Sanitizer builds (ASan/UBSan where supported) under CPU lock.
- ADR, WORKER_STATUS.md, progress comments, small commits, draft PR.

**Out (never):**
- GPU/CUDA paths, any device code, issue26 GPU slot work.
- Other parsers, I/O, alignment, dose weighting, statistical layers.
- RNG changes, noise model, #20 work.
- Merges, issue close, new auth, broad downloads.
- Any change to numerical gates, RMSE, bit-reproducibility contract.
- Touching colleague worktrees or #26 resources.

## Implementation constraints (per task-98 + COMMON)
- CPU-only (cpu64 under lock).
- At most 2 concurrent read-only subagents.
- Preserve other tasks; no merges.
- Record exact hashes, commands, outputs, NUMA placement.
- Small separate PR.
- Healthy mask identity + malformed batch/resume tests.
- No statistical change.

## Verification gates
1. Old parser + huge malformed rectangle → timeout test FAILS (guard demonstrates hang risk).
2. Fixed parser → same test passes in bounded time; no UB, no overflow iteration.
3. Valid defect fixture → identical output mask (bit identity).
4. Default tutorial (no defects) → identical output.
5. Malformed-first, malformed-last, resume cases → clean rejection or graceful skip per policy.
6. Empty file, comment-only, zero-size rect → policy-defined behavior, no crash.

## Evidence to record
- Source/binary hashes before/after.
- Exact failing command + timeout output on old code.
- Passing command + full output on fix.
- Mask identity diffs (none).
- CPU mask, lscpu topology, numactl policy for every run.
- gh comment URLs, PR URL.

## Risks & fallbacks
- Policy for comments/empty may need spec clarification from maintainer (read issue comments first — done).
- If existing contract silently accepts partial records, document and preserve or escalate.
- Sanitizers may not be available on all build hosts; note and use where supported.

**Owner:** grok-4.3 scoped agent (Claude Code execution)
**Next:** Implement parser + tests per this ADR; obtain independent read-only review; commit/push draft PR.
