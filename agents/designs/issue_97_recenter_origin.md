# ADR — Issue #97: save the first-frame origin before recentering interpolated shifts

**Status:** implemented, pending review. **Date:** 2026-09-28. **Base:** `main` @ `5ada983`.

## Defect

`--interpolate_shifts` (experimental, default off) recentered the per-frame interpolated
field in place and ascending:

```cpp
for (int iframe = 0; iframe < n_frames; iframe++) {
    interpolated_xshifts[iframe] -= interpolated_xshifts[0];
    interpolated_yshifts[iframe] -= interpolated_yshifts[0];
}
```

Iteration zero zeroes the origin that every later iteration still needs, so frame 0 ends at
exactly 0 while frames 1..n-1 keep their un-recentered absolute values. The stored field is
therefore the correct field plus the constant `interp(0)` for every frame after the first.

Two other sites already recenter correctly, by iterating downwards so frame 0 is done last:
the per-iteration recentre in `MotioncorrRunner::alignPatch`, whose loop carries that
instruction as a comment, and its device port in `cudaAlignPatchDevice`, which iterates
downwards and then assigns frame 0 rather than relying on the comment. The ascending loop in
the interpolate-shifts branch was the outlier. Both are untouched here.

## Decision

Extract the recentering into `MotioncorrRunner::recenterShiftsToFirstFrame`, which saves both
origins before the loop. `interpolateShifts` becomes public and static — it is a pure function
of its arguments — so the arithmetic can be driven directly from a test. No other arithmetic,
group-centre convention, frame numbering or fitting behaviour changes.

## Upstream parity

The defective block is inherited verbatim from pinned RELION `ad0b230`
(`SOURCE_MANIFEST.txt`). Correcting it is a deliberate divergence from the parity baseline, on
the option-on path only, and is recorded as a `Local change:` entry in the manifest. The
default option-off path stays bit-exact; that separation is what the evidence below measures.

## What the tests establish

`RunnerInterpolateRecenter` (`tests/test_runner_numerics.cpp`) drives the real helpers on four
exactly representable witnesses, compared with `==` and no tolerance, with the old in-place
loop reproduced locally as the negative control. Reverting either axis of the fix fails it with
a distinct message.

`RunnerInterpolateShifts` (`tests/test_runner_contract.py`) runs the binary end to end, twice,
and covers what the helper test structurally cannot: that the call site is still wired, that
`--first_frame_sum > 1` shifts the whole serialized field rather than just its first entry,
that the unequal final group the remainder distribution produces is handled, and that the
result is right on both axes. Its two discriminating checks are

* **cross-arm anchor agreement** — the interpolated field passes exactly through its anchors and
  both branches subtract the same origin, so at an integral group centre the option-on and
  option-off arms must agree with no tolerance at all; and
* **segment linearity** — frames that share one interpolation segment must lie on a line.

Both fail on the unfixed binary, on both axes, by the discarded origin. Neither can be
satisfied by frame 0 alone, which the old code also sets to zero.

## Not established

No CUDA or GPU execution. The recentering is backend-shared host code, so a CUDA build
compiles the identical arithmetic, but the CUDA patch-alignment path can feed different group
shifts into it and no GPU run has been made; a slot is not currently assigned to this issue.

No downstream scientific claim of any kind. Changed pixels are not better pixels; nothing here
says the corrected option-on output improves a reconstruction. No timing claim. One synthetic
fixture plus the single real movie in the retained cpu64 evidence — defect frequency across the
24-movie set is unmeasured.
