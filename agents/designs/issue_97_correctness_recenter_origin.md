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
- No perf, noise, or peak-tie impact. **RELION parity IS affected** on the option-on path — see "Upstream provenance and parity" below.
- NO committed regression test (see Verification status below). Verified out-of-tree against the real symbol instead.

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

---

## Upstream provenance and parity (checked 2026-09-28)

`SOURCE_MANIFEST.txt` pins upstream `https://github.com/3dem/relion` branch `ver5.1`
commit `ad0b230ca22095700f6392479326836efb1c911d`, and records only two local deltas
(per-movie metadata init in this file; `rnd_gaus` re-seed in `funcs.cpp`) — neither
touches this block.

Fetched the pinned upstream file and diffed the block directly:

```
curl -sS https://raw.githubusercontent.com/3dem/relion/ad0b230ca22095700f6392479326836efb1c911d/src/motioncorr_runner.cpp
sha256(upstream file) = cf21cf29ca9c4d16d0012b5d54c6adf249b3092a745bba347d19d7d7141e549e
upstream lines 1600-1604 == our pre-fix lines 2160-2164, byte for byte
```

**The defect is inherited verbatim from upstream RELION 5.1, not introduced by this project.**

**Consequence requiring maintainer sign-off:** AGENTS.md states the project maintains
"bit-exact numerical parity against RELION 5.1 (`commit ad0b230`)". This fix is therefore a
*deliberate, scoped divergence from upstream parity* on the `--interpolate_shifts` path.
It is not a silent change and must be approved as such. Mitigating scope:

- `--interpolate_shifts` is experimental and default-off.
- Every reference fixture and benchmark log in the repo records `interpolate_shifts = 0`
  (`test-data/fixtures/reference_output/synthetic_128x128_8frames.log`,
  `docs/benchmark_logs/pr28_a100_2026-09-24/*.log`), so no existing parity artifact can move.
- Grep shows only three consumers of the flag: CLI parse (L140), logfile echo (L1371),
  and this block (L2159). No other code path reads it.

An alternative, if upstream parity must be preserved unconditionally, is to gate the
corrected behaviour behind a separate flag. That is a maintainer decision, not taken here.

## Verification status (executed 2026-09-28, CPU, darwin/arm64)

Build: out-of-tree `/tmp/issue97-build`, `CMAKE_BUILD_TYPE=Release` (`-O3 -DNDEBUG`),
AppleClang, `RFLOAT` = 8 bytes. Release chosen deliberately: an unqualified CMake configure
in this project builds `-O0`.

`src/motioncorr_runner.cpp` sha256 `6620b8c6019c505d7c02a6418a6b9e6dcef1f66679f6f5c9b880021c3ddeb3cb`
`libmotioncorr_core.a` sha256 `f407737ee792aed2c70d264a85e48d6cd18cdf39c30663bdb0d7b261d5fcb242`

Verified by linking two throwaway harnesses (in `/tmp`, deliberately not committed) against
the built `libmotioncorr_core.a`, calling the **real** `MotioncorrRunner::interpolateShifts`
symbol. Access was opened with `#define private public`; member-function mangling does not
encode access and `interpolateShifts` reads no member state, so the callee is genuine
production code, not a retyped copy of the expression.

| Check | Result |
|---|---|
| Compiles (forced fresh rebuild of the TU) | PASS — 4 pre-existing `sprintf` deprecation warnings only |
| W1 reproduces the archived control exactly | PASS — interpolated `-1 0 1 2 3 4`, old `0 0 1 2 3 4`, new `0 1 2 3 4 5` |
| Fixed frame-0 offset is exactly 0 | PASS (all 4 witnesses, `== 0`, not a tolerance) |
| Relative displacements preserved | Bit-exact in all 4 witnesses (`!=` on doubles, no tolerance) |
| Zero-origin control: old == new bitwise | PASS — 3 cases incl. 2 non-trivial (`memcmp` identical) |
| Nonzero-origin control: old != new | PASS (intended bug-change) |

Harness sources retained: `/tmp/issue97_verify.cpp`
sha256 `e7d48b39484fa0a492f3342da8e9e7faf7d34a0ea1d25825f837ef73bce3fc40`;
`/tmp/issue97_control.cpp` sha256 `619f499b338985500d63688047acb68316a5fbbe87aa78273d32750568e229cc`.

### Tolerance honesty
Relative displacement was bit-exact for every witness tested, including cases with
non-representable values (1/3). This is **not** claimed as a general guarantee:
`(a−c)−(b−c)` need not equal `a−b` in floating point for extreme magnitude ratios.
For realistic pixel-scale shifts the double-precision headroom makes the invariant hold,
and no tolerance was loosened anywhere to obtain these results.

### NOT verified — explicitly unrun
- No end-to-end MotionCorr movie run, option-on or option-off.
- No CUDA / GPU execution (deferred to the #26 coordinated slot).
- No RELION downstream / FSC / B-factor comparison.
- Frequency and magnitude of this defect on real experimental movies remain unmeasured.
- No committed regression test in `tests/` (see below).

### Withdrawn test — correction of an earlier claim
Commit `f9c1754` added a regression to `tests/test_runner_numerics.cpp` and `db62593`
reverted it. The stated reason (`interpolateShifts` is private, exposing it would touch the
header and exceed the tiny-PR scope) was true but incomplete. Executing the real path now
shows **two of its three witnesses asserted wrong expected values** and would have failed:

- W2 asserted `fixed[5] == 3.0`; the real path yields `5.0`. It was also labelled a
  "zero-origin" control while its actual frame-0 offset is `3.5` — it did not test the
  condition its name asserted.
- W3 asserted `fixed[6] == 5.0`; the real path yields `8.0` (the comment even said
  "rough check").

Only W1 was correct. Reverting was the right outcome for the wrong reason; a future test
must be validated against executed output before being committed.
