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

The behavioural change is confined to the `if (interpolate_shifts)` block; the surrounding
changes are the extraction, its declaration, the regression and its evidence, all enumerated in
the whitelist section below.

## Rationale
- Correctness: first frame must retain its interpolated offset after recentering to first-frame origin (by definition of "recenter").
- Evidence-based: deterministic nonzero offset witness on real call path (not synthetic expression).
- No tolerance relaxation; use exact integer witnesses + justified float compare for general case.
- Independent of #68 (units), #69 (CUDA state), #70 (ties), etc.

## Consequences
- Option-on outputs change for movies where first interpolated offset !=0 (expected bugfix delta, recorded as such).
- Option-off and non-interpolate paths: bit-exact no change.
- No perf, noise, or peak-tie impact. **RELION parity IS affected** on the option-on path — see "Upstream provenance and parity" below.
- Committed regression test `RunnerInterpolateRecenter`, plus executed CPU integration evidence (see below).

## Whitelist of allowed modifications (strict)
1. `src/motioncorr_runner.cpp` — the recenter call site plus the extracted
   `recenterShiftsToFirstFrame` definition.
2. `src/motioncorr_runner.h` — declare that helper and widen `interpolateShifts` to public
   static. Widened from the original whitelist on coordinator direction so the regression can
   drive real production code; see `issue97-whitelist.md` Amendment 2026-09-28.
3. `tests/test_runner_numerics.cpp` + `CMakeLists.txt` — the regression and its ctest entry.
4. `docs/issue97_cpu_evidence/` — raw cpu64 logs, script, comparator.
5. `SOURCE_MANIFEST.txt` — a `Local change:` entry for the deliberate upstream divergence.
6. `WORKER_STATUS.md`, `issue97-whitelist.md`, progress comments, this ADR.
7. Still excluded: CUDA/GPU code (deferred to the shared-GPU slot owned by #53), gate or tolerance changes, peak-tie/noise/
   performance work, anything touching another issue.

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
commit `ad0b230ca22095700f6392479326836efb1c911d`. At the time of this check it recorded two
local deltas (per-movie metadata init in this file; `rnd_gaus` re-seed in `funcs.cpp`), neither
touching this block. A third entry for this fix has since been added by this branch.

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

## Verification status (executed 2026-09-28; unit locally on darwin/arm64, integration on cpu64 linux/x86_64)

Two independent verification layers now exist, both committed:

**1. Unit regression** `RunnerInterpolateRecenter` (`tests/test_runner_numerics.cpp`), registered
in `CMakeLists.txt` outside the Python-interpreter guard so it cannot silently vanish. It drives
the real `MotioncorrRunner::interpolateShifts` and `recenterShiftsToFirstFrame`; the only
arithmetic reproduced locally is the OLD in-place loop, as the negative control.

Mutation-proven **per axis** — the earlier version of this test could not have caught a Y-only
regression, because all of its bug-exposing witnesses had `yshifts` all-zero:

| mutation | result |
|---|---|
| X branch reverted to `-= xshifts[0]` | FAILS, exit 1: `corrected X at frame 1: got 0.000000 expected 1.000000` |
| Y branch reverted to `-= yshifts[0]` | FAILS, exit 1: `corrected Y at frame 1: got 0.000000 expected -1.500000` |
| fix intact | passes, exit 0 |

**2. CPU integration on cpu64** — 8 arms, full provenance, raw logs retained in
`docs/issue97_cpu_evidence/`. Headline: the default-off path is **byte-identical** between base
`4c952b3` and fixed on a full-size real movie (56,955,920-byte MRC payload, 779-line STAR), while
option-on differs as intended. See that directory's README for placement, NUMA policy, interference
and the full product-by-product table.

Current file hashes at the time of writing:

```
f1550193df79b540afc769c10b423d7ccdf94330b5f8b443d0086fa3cd39d2c2  src/motioncorr_runner.cpp
cd9425306b0180b80dd085433b5f0dc9458e03e7944fd31e7d927ed0bce16894  src/motioncorr_runner.h
043a2b1483063025e6107e8cd7395fa13e843a5aad46df56ce4848d3cc2f301d  tests/test_runner_numerics.cpp
```

Binary hashes for the two cpu64 builds are recorded in `docs/issue97_cpu_evidence/README.md`.
The earlier `/tmp` harnesses referenced by a previous revision of this ADR were deliberately not
committed and are superseded by the two layers above; their hashes have been removed rather than
left pointing at a tree that no longer exists.

| Check | Where | Result |
|---|---|---|
| Compiles, forced fresh rebuild of the TU | local + cpu64 | PASS (pre-existing `sprintf` warnings only) |
| W1 reproduces the archived control exactly | unit | PASS — interpolated `-1 0 1 2 3 4`, old `0 0 1 2 3 4`, new `0 1 2 3 4 5` |
| Frame-0 offset exactly 0 after fix, both axes | unit | PASS, `== 0`, no tolerance |
| Expected values for all 4 witnesses | unit | PASS, each recomputed by hand from the source formula and confirmed by two independent reviewers |
| Nonzero interpolated origin on BOTH axes | unit | PASS — cases 2 and 3; X and Y mutants each caught separately |
| Relative displacements preserved | unit | Exact, `==` on doubles, no tolerance |
| Zero-origin control: old == new, per axis | unit | PASS (biconditional, asserted per axis) |
| Empty-input guard | unit | PASS |
| `RunnerInterpolateRecenter` present/absent | cpu64 | passes on fixed tree; does not exist on base tree |
| Full suite | cpu64 | 14/14 fixed, 13/13 base — exactly one test added, none regressed |
| Default-off output unchanged, synthetic | cpu64 | MRC payload and STAR **byte-identical** base vs fixed |
| Default-off output unchanged, real movie | cpu64 | MRC payload (56,955,920 B) and 779-line STAR **byte-identical** |
| Default-off unchanged, real movie, CUDA | 4GPUs | MRC payload (56,955,920 B) and 779-line STAR **byte-identical** on the native CUDA backend |
| Option-on changed, real movie, CUDA | 4GPUs | 611/779 STAR lines differ; joint accumulated motion equal |
| Option-on output changed, real movie | cpu64 | 14,236,598/14,238,980 px differ; 611/779 STAR lines |
| Joint STAR accumulated motion equal | cpu64 | measured in `followup_measurements.log`; the original comparator could not see these values (see the evidence README correction) |
| Recenter block actually reached | cpu64 | 9 patch blocks (3x3) and 25 (5x5), `interpolate_shifts` 0/1 per arm, zero "Too few patches" — captured from the nested per-movie logs in `followup_measurements.log` |

### Tolerance honesty
Relative displacement is bit-exact for every committed witness. Note what that does and does
not rest on: all committed witnesses are exactly representable, and where the interpolation
divides by 3 (the unequal-last-group case, centres {1,3,6}) every numerator happens to be an
exact multiple of 3, so each quotient is a small integer. Exactness there is a property of the
chosen values, not of the formula — editing a group size or a shift in that case could break it
without tripping this rationale. Bit-exactness is **not** claimed as a general guarantee:
`(a−c)−(b−c)` need not equal `a−b` in floating point for extreme magnitude ratios.
For realistic pixel-scale shifts the double-precision headroom makes the invariant hold,
and no tolerance was loosened anywhere to obtain these results.

### NOT verified — explicitly unrun

- ~~No CUDA / GPU execution.~~ **Now run** on 4GPUs (A100, CUDA 12.8, sm_80): default-off
  byte-identical and option-on changed on the native CUDA backend, with
  `[CUDA Patch Alignment Profile]` confirming the local/patch path the fix touches ran on
  device. See `docs/issue97_gpu_evidence/`. Still NOT run there: the ctest suite (the host
  lacks numpy, which current main hard-requires for `BUILD_TESTING=ON`). No timing claim —
  another user's job shared the device. Note `src/acc/cuda/cuda_alignpatch.cu` contains an
  independent, already-correct descending-loop recentering; it was not touched.
- **No downstream scientific claim.** No RELION refinement, FSC, B-factor or resolution
  comparison. Nothing here says the corrected option-on output is scientifically better,
  only that it matches the code's stated intent.
- **One real movie only** (`20170629_00026`) and one synthetic fixture. Defect frequency and
  magnitude across the 24-movie set are unmeasured; a single movie is not representative for
  any load-bearing quantitative claim.
- **No timing claim** from the cpu64 runs — `ctffind` ran concurrently on the same NUMA node.
- **Non-one first selected frame** (`--first_frame_sum > 1`) is not covered by any arm.
- Only two patch geometries were run (3x3 synthetic, 5x5 real movie). No unequal-patch or
  other local-mode geometry.
- **No general-case floating-point witness.** Every committed witness is exactly representable
  and compared with `==`. The relative-displacement invariant is therefore demonstrated only on
  exact inputs; see "Tolerance honesty" above for why it is not claimed in general.
- The test covers the helper directly. Nothing asserts that the call site at
  `motioncorr_runner.cpp` still calls it, so reverting the call alone would keep the unit test
  green — that wiring is covered only by the integration arms.

### History — the withdrawn first attempt

Commit `f9c1754` added a regression that `db62593` reverted. The stated reason (`interpolateShifts`
was private) was true but incomplete: executing the real path showed two of its three witnesses
asserted wrong values (W2 expected 3.0, real 5.0; W3 expected 5.0, real 8.0) and its "zero-origin
control" had a frame-0 offset of 3.5, so it did not test the condition its name claimed.

The regression committed in `792f1e6` and extended in the review pass supersedes it. Every
expected value was recomputed from the interpolation formula and confirmed by two independent
read-only reviewers, and each witness is exactly representable so `==` is used with no tolerance.
