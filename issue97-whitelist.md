# Change whitelist for issue #97 (strict scope)

Allowed:
- src/motioncorr_runner.cpp:2160-2172 region ONLY (save first-frame origin before in-place subtract for interpolate_shifts path)
- Bounded regression test (new or added) exercising real interpolate + recenter path with nonzero first offset
- WORKER_STATUS.md, this whitelist, ADR, commit messages
- GitHub progress comments on #97

Forbidden (enforced by review):
- Any other source lines or files
- CUDA / GPU code or tests in this PR
- Gate tolerance changes, RELION runs, perf numbers
- Anything outside recenter origin bug

Base: 4c952b3
Branch: round96/97-grok-4-3
Model: grok-4.3

---

## Amendment 2026-09-28 (Opus 5 review/fix phase, coordinator-directed)

The original whitelist forbade header changes, which blocked a regression test that
calls real production code rather than a retyped copy of its arithmetic. The
coordinator directed that such a regression be committed. Scope widened, deliberately
and minimally, to:

5. `src/motioncorr_runner.h` — extract the recenter into a named method
   `recenterShiftsToFirstFrame` (public static) and move `interpolateShifts` from
   private to public so the motion-model arithmetic is unit testable. Both are pure
   functions of their arguments and read no member state. No behaviour change.
6. `tests/test_runner_numerics.cpp` + `CMakeLists.txt` — the `interpolate_recenter`
   case and its ctest registration.
7. `docs/issue97_cpu_evidence/` — raw cpu64 validation logs, script and comparator.

Still forbidden: CUDA/GPU code, gate or tolerance changes, peak-tie/noise/performance
work, anything touching another issue, merges, closures, default promotion.
