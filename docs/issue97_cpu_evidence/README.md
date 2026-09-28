# Issue #97 — CPU validation evidence

Fix: `--interpolate_shifts` recentered per-frame shifts with an ascending in-place
loop, so iteration zero zeroed the origin that later iterations still needed.
Frames 1..n-1 kept un-recentered absolute values while frame 0 was forced to zero.

Raw artifacts in this directory:

| file | contents |
|---|---|
| `cpu64_validation_run.log` | complete raw run: provenance, builds, ctest, all 8 integration arms |
| `cpu64_product_comparison.log` | raw output of the product comparison |
| `run_validation.sh` | the exact script that produced the run |
| `compare_products.py` | the comparator |

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

**Interference (recorded, not eliminated):** `ctffind` ran at ~100% CPU on CPU 58
throughout. CPU 58 is on node1, the same NUMA node as this lane, so it shares L3 and
memory bandwidth. It is outside the 40-55 cpuset, so it does not contend for these
cores. An earlier probe also saw `ctffind` on CPU 32 and a colleague `motioncorr` on
CPU 12 (node0). None were touched. Host load average was 4.92/7.28/10.53 at probe and
7.81/7.15/8.85 at completion — **cpu64 was not idle**.

Because of that interference these runs are **not usable as timing evidence** and no
timing claim is made from them. Wall times appear in the raw log for provenance only.

Serialization: the run blocked on `flock /tmp/motioncorr-issue96-cpu-validation.lock`
and acquired it before doing any work (`[lock] acquired after 0s`). A probe shortly
before the launch found the lock held by another worker, so the wait path is real.

## Build provenance

Two **separate source trees**, each cloned and configured independently. A copied build
tree caches an absolute source path and would rebuild the original sources, which would
fake a green negative control.

| tree | commit | binary sha256 |
|---|---|---|
| base | `4c952b3f54479653512c4d208e09c9a8c02f3726` | `b27f7351d0b0481c01fe99df89f792bf3dc0782d572b05530bcd86dbd6911a0c` |
| fixed | `792f1e6725dccfa3544acbc152ea6896060d4f02` | `9fb0c0be1439fbc2365875578744bd1738bb9fad29ce214f3a3033f793338d11` |

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

- fixed tree: `RunnerInterpolateRecenter` **Passed**; all 4 witnesses pass.
- base tree: the case **does not exist** (`Total Tests: 0` when filtered), confirming it is new.
- full suite, fixed tree: **14/14 passed**.
- full suite, base tree: **13/13 passed** — the fixed tree adds exactly one test and regresses none.

Mutation test (run locally, not on cpu64): reverting `recenterShiftsToFirstFrame` to the
original in-place loop makes the case fail with
`corrected X differs at frame 1: got 0.000000 expected 1.000000`, exit 1.

All witnesses are exactly representable, so expected values are compared with `==` and
**no tolerance is used anywhere** in the test.

## Integration: which products change and which do not

Eight arms: {base, fixed} x {option-off, option-on} x {synthetic 128x128 8 frames @ 3x3
patches, real movie 20170629_00026 @ 5x5 patches}. `do_local` requires patch_x > 2 and
patch_y > 2, so 1x1 patches would skip local alignment entirely and the recenter block
would never execute. Both geometries were confirmed to actually reach it: 9 patches
(synthetic) and 25 patches (real movie) all converged, with `interpolate_shifts = 1`
echoed in the option-on logs.

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
| joint `corrected_micrographs.star` | **EQUAL** | **EQUAL** |

The changed values are the per-patch local motion model and the resulting interpolated
image. The joint accumulated-motion summary (`rlnAccumMotion*`) is **equal** in both
arms, so the reported global/accumulated motion is not what moves here.

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
- **No GPU/CUDA execution.** Deferred to the #26 coordinated slot. The CUDA option-on
  path is unverified.
- Two patch geometries only (3x3 and 5x5); no unequal-last-group or non-one
  first-selected-frame integration arm was run.
