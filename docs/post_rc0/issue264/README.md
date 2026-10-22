# Issue #264: centred local-model distortion guard

The updated 22 October Notion orchestrator plan W3 explicitly assigns #264 the
normal correctness-fix path. The issue's earlier FILE-ONLY instruction is retained
historically; this branch implements the newly assigned bounded fix, separately
from C1. No merge, policy/default promotion, other numerical repair, or scientific
qualification is requested by this record.

## Contract and intended difference

The reconstruction evaluates the spatial model at `ix/nx - 0.5, iy/ny - 0.5`.
The previous guard evaluated `(0,0), (1,0), (0,1), (1,1)` plus one forward step,
mostly outside that domain. It could accept an excessive neighbour displacement
or reject a valid model. The new helper checks actual adjacent pixel pairs.
For horizontal pairs the base rectangle is
`[-0.5,(nx-2)/nx-0.5] × [-0.5,(ny-1)/ny-0.5]`; for vertical pairs it is
`[-0.5,(nx-1)/nx-0.5] × [-0.5,(ny-2)/ny-0.5]`.
The spatial polynomial is quadratic, so each forward difference is affine;
the absolute maximum of each shift component occurs at a rectangle corner.
A direction of length one has no adjacent pair and contributes nothing.

The guard remains component-wise, in alignment pixels, with rejection only for
`largest_delta > 3`. It still checks every frame until the first failing frame
and uses the same global-only fallback. This is a coordinate-domain repair,
not a new Jacobian/vector-norm criterion, an estimator/convergence change, or
proof of accuracy. Models near the wrong-domain decision boundary can change
CPU and CUDA local-model retention and outputs. RELION parity therefore changes
intentionally for those cases. Source notices remain intact; no dependency added.

The helper is directly called by the existing CPU-host fit/guard shared with CUDA.
Its standalone test uses independent polynomial evaluation and an exhaustive
long-double reference over every valid integer pixel pair, rather than copying
the helper's corner construction. It covers both shift components, both axes,
nonsquare and singleton dimensions, a cross term, cubic time dependence, constant
and affine fields, the exact strict threshold, and exclusion of out-of-image pairs.

| Discriminating example (frame 1) | Legacy maximum | Actual pair maximum | Correct decision |
| --- | ---: | ---: | --- |
| `200x - 200x²`, nx=100 | 2.02 | 3.98 | reject |
| `100x + 200x²`, nx=100 | 5.02 | 2.94 | retain |
| `768xy`, nx=ny=128 | 6 | 3 | retain at unchanged threshold |
| `8x + 8x²`, nx=4 | 6.5 | 2.5 | retain; last pixel has no forward neighbour |

## Measured host controls

`host_results.json` records the original 36913740 runner bytes, exact extracted
legacy guard block, compiler/commands, tested helper/test hashes, generated header
and binary hashes, stdout/stderr, and results. macOS/Apple Clang, one compile at a
time; no MotionCorr movie or GPU process was launched. Numeric environment was
one thread and the busy shared host was checked before the bounded controls.

- Exact old guard block from 36913740, wrapped without arithmetic changes:
  ordinary exit 1, 45 of 51 checks fail.
- New production helper: exit 0, all 51 checks pass.
- Uncentred-domain mutant: ordinary exit 1, 37 checks fail.
- Out-of-image last-pair mutant: ordinary exit 1, 10 checks fail.
- Existing `tools/test_ci_fail_closed.py -v`: 8/8 PASS; raw log retained.

`LocalMotionDistortionGuard` is registered as a device-free CTest in CPU and CUDA
builds, and added to the required collection plus both mock suite inventories.
Full CMake/CPU/CUDA builds, full CTest collection/execution, independent latest-head
review, CI, and native movie/fitting/reconstruction/publication checks are **UNRUN**
at this record. Standalone compilation does not prove those broader claims.
No historical truth outcome is relabelled and no tolerance/gate is relaxed.

Reproduce into a new output directory (refuses an existing directory):

```sh
python3 docs/post_rc0/issue264/verify_host.py --out /tmp/mc264-new-controls --compiler clang++
python3 tools/test_ci_fail_closed.py -v
```

The legacy extraction is source-pinned; mutations use isolated temporary headers.
The scripts do not edit production source, old evidence, shared caches, or remote
machines. The recorded original attempt is immutable; later results belong in a
new directory with the then-current test/helper hashes.
