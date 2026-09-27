# Architectural Decision Record — Issue #97: Fix interpolated_shifts recenter origin

**Status**: Draft for review (tiny correctness fix)  
**Date**: 2026-09-28  
**Issue**: #97  
**Branch**: round96/97-grok-4-3  
**Model**: grok-4.3  
**Scope**: ONLY the first-frame origin save before in-place recenter mutation in interpolate_shifts path. No other changes.

## Context
The `--interpolate_shifts` option (default off) uses `interpolateShifts` then applies recentering:
```cpp
for (int iframe = 0; iframe < n_frames; iframe++) {
    interpolated_xshifts[iframe] -= interpolated_xshifts[0];
    ...
}
```
When `iframe==0`, this mutates `[0]` to 0 *before* later frames subtract, so first-frame offset is lost (always becomes exactly 0 after recenter, even when interpolation produces nonzero). Archived reproducer (sha256 39dae5d1336981762a840f5bf8b9d0910d7f647570bb90d817fb4c6b42fdcc82) demonstrates the expression defect producing `[0,0,1,2,3,4]` vs correct `[0,1,2,3,4,5]`.

This is a latent bug in option-on path only; option-off path and all default tutorial outputs unaffected.

## Decision
Save original first-frame offset *before* any mutation, then subtract the saved value. Preserve all other arithmetic, group centres, frame numbering, interpolation formula, and polynomial fit.

Change is minimal, localized to the `if (interpolate_shifts)` block in motioncorr_runner.cpp:2160-2172.

## Rationale
- Correctness: first frame must retain its interpolated offset after recentering to first-frame origin (by definition of "recenter").
- Evidence-based: deterministic nonzero offset witness on real call path (not synthetic expression).
- No tolerance relaxation; use exact integer witnesses + justified float compare for general case.
- Independent of #68 (units), #69 (CUDA state), #70 (ties), etc.

## Consequences
- Option-on outputs change for movies where first interpolated offset !=0 (expected bugfix delta, recorded as such).
- Option-off and non-interpolate paths: bit-exact no change.
- No perf, noise, peak, or RELION-provenance impact.
- Bounded regression test added using known simple displacements.

## Whitelist of allowed modifications (strict)
1. `src/motioncorr_runner.cpp` — only the two-line save + use of `origin_x`, `origin_y` inside the `if (interpolate_shifts)` block (lines ~2159-2172).
2. New regression test file under `tests/` or existing test harness (bounded, CPU-only initially).
3. `WORKER_STATUS.md` updates, progress comments, this ADR.
4. No other files, no CUDA changes yet (GPU waits #26 slot), no gate changes, no docs beyond status.

## Verification gates (per issue-97.json)
- Real-path regression fails on original, passes on fix.
- Frame-zero offset ==0 after recenter (mathematically).
- Relative displacements preserved (exact simple truth + float tol justified).
- Option-off controls exact (same-backend).
- Pinned RELION check: no inheritance of bug assumed.
- Full evidence: hashes, commands, outputs, intentional diff only.

## Out of scope (enforced)
- No GPU timings/benchmarks.
- No RELION FSC/B-factor runs.
- No performance, no other issues.
- No merges, no scope expansion.

**Approval**: Maintainer approval via existing session auth for narrow assignment. Independent review required before merge.
