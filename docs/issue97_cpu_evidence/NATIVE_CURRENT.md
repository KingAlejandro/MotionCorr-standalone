# Current-main native selected-frame recenter validation

29 September 2026. Candidate `2d8fdfb2c6d25b9c7f1e707cd8ff66cc5487f3cb`,
base main `a75a3f87f7ef17e0a29b1c91a1edecda08ebed34`. The candidate adds a native
CTest invocation to the existing selected-frame regression; production arithmetic is
unchanged from reviewed `ba1ac7df`.

The test now accepts `--gpu` for the interpolation case and requires nine successful
CUDA patch-alignment completion witnesses in each option-off/on arm. It retains the
same geometry, selected original frames 2–8, unequal groups {2,2,3}, both-axis anchor
and linearity assertions, 3e-5 serialization tolerance, and calibrated nonzero shifts.
No tolerance was changed. CPU test invocation remains unchanged.

## Executed

- Fresh main and candidate Release builds, CUDA12.8 / sm80, on the four-GPU VM.
- **22/22 CTest passed**, including `RunnerInterpolateShiftsCuda` and
  `CudaWrapperUploadFailure` (two tests labelled cuda/hardware).
- Current main fails **18/18 native patch-axis anchor checks**. Both base arms have
  nine successful native patch witnesses, so rejection does not come from missing
  CUDA execution or nonconvergence.
- Candidate native option-off products equal main: one structurally valid 128×128
  float MRC including every normalized header/extended-header/pixel byte, the entire
  per-movie STAR, and joint STAR. Only the existing exact Relion timestamp token is
  normalized in the MRC header. The declared image/STAR inventory and joint paths
  are checked independently in both trees.
- Candidate option-on products differ from main as expected for the deliberately
  corrected origin. Both corrected candidate arms pass the numerical contract.
- A corroborating candidate rerun records actual payload PID/start identity,
  executable, CPU mask, NUMA maps and live physical GPU UUID for both arms.

Native device: `GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d`. Initial build/test mask
104–111, corroborating payload mask104–109, memory node1, runtime j1. Builds held
`/tmp/motioncorr-vm-build.lock` with j4; native work held its GPU1 correctness lock.
Other correctness jobs used distinct GPUs/CPU masks. **No timing or scaling claim.**

## Retained evidence and qualification

[`native-20260929/evidence.tar.gz`](native-20260929/evidence.tar.gz) preserves commands, source/input/binary/helper
hashes, build/CTest logs, original products, raw PID/UUID witnesses and the comparison.
The first `compare_trees` invocation failed because that tutorial-specific interface
expects a `Movies/` product directory while this fixture writes products at the root.
`driver.log` retains that failure. `regrade-v2.py` grades the already-produced files
with the same strict `validate_mrc`/STAR parsers and an explicit root-level inventory;
[`regrade-v2.json`](native-20260929/regrade-v2.json) is the passing product result. No MotionCorr result was modified.

This closes the previously unrun current-source native selected-frame check. It does
not establish scientific improvement, other geometries, or correction prevalence on
all24 tutorial movies. Historical CPU and earlier-source evidence remain unchanged.
