# Issue #98 — Reject malformed text-defect rectangles

**Status:** In progress — parser source read; preparing failing timeout reproducer + fix implementation
**Phase:** 3-4. Write failing test on old code, implement bounded fix
**Model:** grok-4.3
**Task class:** correctness
**Branch:** `round96/98-grok-4-3`
**Base:** `origin/main` (4c952b3f54479653512c4d208e09c9a8c02f3726)

## Phase
1. Read live issue comments, AGENTS.md, architecture docs
2. Publish scoped plan, ADR/whitelist, WORKER_STATUS.md, GitHub progress comment
3. Implement fix in text-defect parser (only)
4. Write/verify failing test on old code → pass on fix
5. CPU-only validation, sanitizers
6. Commit/push, draft PR

## Scope (strictly bounded)
- Own ONLY the text-defect rectangle parser in MotionCor2
- Distinguish clean whitespace EOF from malformed/partial record
- Initialize wide integers, prevent overflow
- Clip image bounds BEFORE iteration
- Define comments/empty/zero-size policy from existing supported contract
- Healthy mask identity, first/last malformed batch, resume
- No RNG/noise-model/statistical change
- Small separate PR, sanitizers where supported, CPU lock

## Out of scope (never touch)
- Any GPU code, CUDA kernels, device paths
- Other parsers, I/O layers, alignment, dose-weighting
- Numerical tolerances, RMSE gates, reproducibility changes
- Any work on issue26 GPU slots or shared4GPU resources
- Merges, issue closures, new credentials

## Next step
Read live issue #98 comments, then AGENTS.md and architecture docs before coding.
