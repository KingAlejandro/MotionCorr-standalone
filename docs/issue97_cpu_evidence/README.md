# Issue #97 — CPU validation evidence

Fix: `--interpolate_shifts` recentered per-frame shifts with an ascending in-place
loop, so iteration zero zeroed the origin that later iterations still needed.
Frames 1..n-1 kept un-recentered absolute values while frame 0 was forced to zero.

Raw artifacts in this directory:

| file | contents |
|---|---|
| `cpu64_validation_run.log` | complete raw run: provenance, builds, ctest, all 8 integration arms |
| `cpu64_product_comparison.log` | raw output of the product comparison (`compare_products.py`) |
| `run_validation.sh` | the exact script that produced the run |
| `compare_products.py` | the comparator actually relied on |
| `followup_measurements.log` | follow-up capture of the joint-STAR values and patch-convergence evidence |
| `followup.sh` | the script that produced it (read-only over the retained outputs) |
| `followup_measurements.log` | follow-up capture of the joint-STAR values and patch-convergence evidence |
| `followup.sh` | the script that produced it (read-only over retained outputs) |

**Read the raw log's own `GATE:` line with care.** `run_validation.sh` ends by invoking an
earlier comparator that only inspected the top level of each arm directory. motioncorr mirrors
the input path under the output directory, so the per-movie `.mrc` and `.star` are nested and
that first version never saw them — it compared only the joint summary STAR and therefore
reported the option-on arms as unchanged. Its `GATE: ATTENTION` line in
`cpu64_validation_run.log` is an artifact of that flaw and is superseded by
`compare_products.py` / `cpu64_product_comparison.log`, which walks recursively and matches by
basename (necessary because the synthetic input lives under `src-base/` vs `src-fixed/`, so the
nested paths differ between arms by construction).

## Host, placement and NUMA

Host `cpu64` / `small-refmac-machine`, AMD EPYC 7763, 2 sockets, 64 cores,
**1 thread per core (no SMT)**, 2 NUMA nodes: node0 = CPUs 0-31, node1 = CPUs 32-63.
Node distances 10 (local) / 20 (remote).

Lane: **CPUs 40-55**, chosen inside the 32-63 admission lane and verified node-local.
Admission lanes are not a claim of locality, so the mapping was checked rather than assumed:

```
CPU,NODE,SOCKET,CORE  ->  40..55 all map to NODE 1, SOCKET 1, CORE == CPU (no SMT siblings)
```

Actual inherited placement of a pinned child, not just the requested mask:

```
Cpus_allowed_list:  40-55
Mems_allowed_list:  0-1
numactl --show:     policy: bind / cpubind: 1 / nodebind: 1 / membind: 1 / preferred: 1
```

CPU and memory policy were held constant across every arm
(`taskset -c 40-55 numactl --membind=1`), applied top-level so descendants inherit.
Build parallelism 16, runtime threads 16.

**Interference (recorded, not eliminated):** the retained interference probe
(`cpu64_validation_run.log`) shows two `ctffind` processes at 99.9% CPU on **CPUs 32 and 33**.
Both are on node1, the same NUMA node as this lane, so they share L3 and memory bandwidth;
both are outside the 40-55 cpuset, so they do not contend for these cores. None were touched.
Host load average was **16.36 / 11.00 / 9.42** at start and **11.38 / 10.77 / 9.48** at
completion — **cpu64 was not idle**. A follow-up probe later saw one `ctffind` on CPU 50,
which IS inside the lane; that probe ran only the read-only re-comparison described below, no
build and no motioncorr execution, so it affects nothing measured here.

Because of that interference these runs are **not usable as timing evidence** and no timing
claim is made from them. Note the raw log records `Elapsed (wall clock)` for the two **builds
only**; the per-arm `/usr/bin/time -v` output was written but the script's `tail -3 | grep`
never matched the Elapsed line, so no per-arm wall time was captured. Nothing here depends on
one.

Serialization: the run blocked on `flock /tmp/motioncorr-issue96-cpu-validation.lock`
and acquired it before doing any work — `[lock] acquired after 30s`, i.e. it genuinely waited
behind another worker rather than finding the lock free.

## Build provenance

Two **separate source trees**, each cloned and configured independently. A copied build
tree caches an absolute source path and would rebuild the original sources, which would
fake a green negative control.

| tree | commit | binary sha256 |
|---|---|---|
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` | `b27f7351d0b0481c01fe99df89f792bf3dc0782d572b05530bcd86dbd6911a0c` |
| fixed | `85dd1f9a4c7b96e224034b009236a1a2600e5e46` | `cd9a7316eecf108132afabe6041f26433e741611d816901257e8f6252fa56de1` |

`CMAKE_BUILD_TYPE=Release` was set explicitly for both: an unqualified configure in this
project builds `-O0`. Compiler `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`,
CMake from `/home/ubuntu/.mc-venv`. Both trees verified clean (0 modified files).
The complete production delta between the two trees is inlined in the raw log.

Inputs:

```
44f32752ebb62fc22428e95a1449e54e3a6952036285b805b96085f296ec5ed0  synthetic_128x128_8frames.mrcs
f989391b9d0e3e3b927a8de59d60179ade0b7ae5075ce7c3a9a5002ae2254ae3  20170629_00026_frameImage.tiff
8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1  gain.mrc
```

## Unit regression

`RunnerInterpolateRecenter` calls the real `MotioncorrRunner::interpolateShifts` and
`MotioncorrRunner::recenterShiftsToFirstFrame`. The only arithmetic reproduced in the
test is the OLD in-place loop, which is the negative control, not the code under test.

- fixed tree: `RunnerInterpolateRecenter` **Passed**; all 4 witnesses plus the empty-input
  guard pass, including the two carrying a nonzero interpolated origin on both axes.
- base tree: the case **does not exist** (`Total Tests: 0` when filtered), confirming it is new.
- full suite, fixed tree: **14/14 passed**.
- full suite, base tree: **13/13 passed** — the fixed tree adds exactly one test and regresses none.

Mutation test, per axis (run locally, not on cpu64). The earlier version of this test could
not have caught a Y-only regression, because all of its bug-exposing witnesses had `yshifts`
all-zero:

| mutation | result |
|---|---|
| X branch reverted to `-= xshifts[0]` | FAIL, exit 1: `corrected X at frame 1: got 0.000000 expected 1.000000` |
| Y branch reverted to `-= yshifts[0]` | FAIL, exit 1: `corrected Y at frame 1: got 0.000000 expected -1.500000` |
| fix intact | pass, exit 0 |

All witnesses are exactly representable, so expected values are compared with `==` and
**no tolerance is used anywhere** in the test.

## Integration: which products change and which do not

Eight arms: {base, fixed} x {option-off, option-on} x {synthetic 128x128 8 frames @ 3x3
patches, real movie 20170629_00026 @ 5x5 patches}. `do_local` requires patch_x > 2 and
patch_y > 2, so 1x1 patches would skip local alignment entirely and the recenter block
would never execute. That the block is reached is therefore load-bearing, and an earlier
revision asserted it without having captured it: the run script grepped `"$out"/*.log`, which
matches only the top-level `stdout.log`/`time.log`, while motioncorr writes its per-movie
logfile into the mirrored nested path. Captured from the nested logs in
`followup_measurements.log`:

```
syn-*-off   Patches: X = 3 Y = 3   interpolate_shifts = 0   patch_blocks=9    too_few_patches=0
syn-*-on    Patches: X = 3 Y = 3   interpolate_shifts = 1   patch_blocks=9    too_few_patches=0
mov-*-off   Patches: X = 5 Y = 5   interpolate_shifts = 0   patch_blocks=25   too_few_patches=0
mov-*-on    Patches: X = 5 Y = 5   interpolate_shifts = 1   patch_blocks=25   too_few_patches=0
```

Whole-file hashes are not used: the MRC header carries a creation timestamp, so
byte-identical results still hash differently. Comparison is on the MRC pixel payload
(after the 1024-byte header plus NSYMBT) and on STAR values.

### Default-off exactness control — UNCHANGED

| product | synthetic | real movie |
|---|---|---|
| output `.mrc` pixel payload | **IDENTICAL** (65,536 bytes) | **IDENTICAL** (56,955,920 bytes) |
| per-movie `.star` motion model | **byte-identical** (164 lines) | **byte-identical** (779 lines) |
| joint `corrected_micrographs.star` | identical | identical |

The default path is provably untouched, on a real movie, at full size.

### Option-on — INTENTIONALLY CHANGED

| product | synthetic | real movie |
|---|---|---|
| output `.mrc` pixel payload | DIFFERS: 16,243/16,384 px (99.14%), max abs 11.93 on data range 428.70 (rel 2.78e-02) | DIFFERS: 14,236,598/14,238,980 px (99.98%), max abs 22.56 on data range 51.42 (rel 4.39e-01) |
| per-movie `.star` motion model | DIFFERS in 99/163 value lines | DIFFERS in 611/777 value lines |
| joint `corrected_micrographs.star` | **EQUAL** (measured, see below) | **EQUAL** (measured, see below) |

The changed values are the per-patch local motion model and the resulting interpolated image.

**Correction, and how the joint-STAR claim is now supported.** An earlier revision asserted the
accumulated-motion summary was equal while citing a comparator that *could not see those
numbers*: its filter dropped any line containing a path, and in `corrected_micrographs.star` the
`rlnAccumMotion*` values sit on the same data row as the micrograph path. That row was discarded
from both sides, so only headers and labels were ever compared. It was a vacuous comparison and
should not have been published as a measured result.

`compare_products.py` now normalises path *tokens* rather than dropping rows, so the data row is
compared, and the values were additionally extracted directly. Both are in
`followup_measurements.log`:

```
syn-{base,fixed}-{off,on}   opticsGroup 1   Total  4.323048   Early 1.386941   Late  2.936107
mov-{base,fixed}-{off,on}   opticsGroup 1   Total 13.167835   Early 1.829223   Late 11.338612
```

Identical across all four arms for each input. The corrected comparator reports
`STAR identical after normalising path tokens (25 lines compared, values included)` for every
pair, while still reporting the per-movie products as DIFFER on the option-on arms — so the
filter fix did not blunt the comparison. The claim holds, but it is now measured rather than
assumed. This is consistent with the code: accumulated motion is computed from
`mic.getShiftAt(frame, 0., 0., ...)`, the global trajectory, not the local patch model.

## Limits — what this does NOT establish

- **No scientific claim.** These are code-output differences. Nothing here says the
  corrected option-on result is scientifically better, or that downstream results are
  equivalent. No FSC, B-factor, RELION downstream or resolution comparison was run.
  The fix is justified by the code's stated intent ("Recenter to the first frame"),
  not by a measured scientific improvement.
- **One real movie only** (`20170629_00026`), one synthetic fixture. Frequency and
  magnitude of the defect across the 24-movie set are unmeasured; a single movie is not
  representative for any load-bearing quantitative claim.
- **No timing claim** — concurrent `ctffind` on the same NUMA node.
- **No GPU/CUDA execution.** Deferred to the coordinated shared-GPU slot, now owned by #53. The CUDA option-on
  path is unverified.
- Two patch geometries only (3x3 and 5x5); no unequal-last-group or non-one
  first-selected-frame integration arm was run.
