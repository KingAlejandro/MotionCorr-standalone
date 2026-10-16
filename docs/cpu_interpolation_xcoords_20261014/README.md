# Exact interpolation x-coordinate experiment

## Current state — 16 October 2026

Merged main `1db869025507ac801845b4001b84e6bc0e77a645` (#178 included);
merged/tested code is `d22c4569160a6d88eb73b754c2cbaa5edd9f452b`.
The earlier d7171b81 merge and controls remain retained as history.
Both production methods now use one private cache builder, tested directly against
inline division for 57,922 coordinates across 13 widths (including detector and
odd widths). The reciprocal-multiply mutant fails on macOS and GCC/Linux.
Linux Release passes 60/60 CTests on full rerun (an initial ProfilingKit timeout
is retained); macOS has only the two independently reproduced main failures. Tutorial and synthetic 5x5-patch product trees match current main
exactly (8 MRC payloads, 4 canonical STARs); a payload-bit mutant is rejected.
Streamed one-frame offsets are tested against the frozen full-stack reference.
The cache remains per interpolation call, so #178's unweighted path rebuilds it
once per frame, outside all row/pixel loops; no cross-call cache is introduced.
Both measurement drivers require a full source SHA **per measured binary** and
record it separately from driver HEAD, with caller-attestation explicitly labelled.

[Current commands, statuses, hashes, limitations and logs](review_20261016/streamed-main/README.md).
[Earlier review-fix evidence](review_20261016/README.md).
No new timing was collected; application benefit remains unresolved. Keep draft.
Everything below is historical evidence against the original baseline, not a
current-main performance claim. Its old receipt `source` identifies driver HEAD,
not verified build provenance for either binary.

## Original experiment

This independent issue #10 experiment starts from main
`116eb04ad359cd5bf789b28809fc2047ea155b9b`. It does not include #177's CCF plans,
#178's streamed unweighted sums, #179's dose weights, or #180's FFT/memory changes.
The user requested it after the roadmap in #179 identified a repeated division.
The issue #10 ownership update is
https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6180038421.

## Change and numerical contract

The two existing CPU polynomial reconstruction methods each build one
`std::vector<RFLOAT>` of width `nx` at entry. Every entry uses the **original**
`(RFLOAT)ix / nx - 0.5` expression. Pixel loops load the stored value. The cache
is shared read-only by the OpenMP team, survives all rows and frames in that call,
and is released when reconstruction returns. It costs 29,680 bytes at width 3710
(default double RFLOAT), with one allocation per reconstruction invocation.

At 3710 x 3838 x 24, one pass formerly evaluated 341,733,120 x-coordinate
expressions. This version evaluates 3,710. This is an operation-count explanation,
not a runtime claim. Coefficients, polynomial evaluation order, y coordinates,
boundary clamping, frame order, source pixels, `float` destination stores,
OpenMP row scheduling and progress logging are unchanged. The generic model,
null-model sum and CUDA paths are unchanged. No reciprocal multiplication,
incremental coordinates, fused interpolation/sum or fast-math is introduced.

The production methods number input frames from zero, including higher-order time
terms at nonzero `iframe`. They have no frame-offset parameter. This change does
not introduce or change an offset. Integration with #178's separate streamed
single-frame helper needs a separate follow-up to reuse one cache across frames.

## Controls

`CpuInterpolationXcoords` invokes both actual private production methods through
the existing test friend, against frozen main implementations in
`tests/cpu_interpolation_reference.h`. The frozen header preserves the full
upstream GPL notice; only function names and an explicit thread-count parameter
were changed. This is an independent arithmetic baseline, not a reimplementation
of the new cache.

The matrix has 480 configurations, each exercising both sum and withoutsum:
8 shapes (including 1 x 1, 2 x 3, odd/nonsquare and width 65), 1/3/7 frames,
5 models (zero, fractional, large/clamped, nonlinear and near-integer movement),
1/4 threads, and normal/exceptional source pixels. Exceptional inputs include
signed zero, subnormals, infinities and NaNs. Destinations start nonzero to check
existing `+=` semantics. Every output float is compared by bits; all input floats
and progress logs must remain identical. Tests exercise boundary clamping and
nonzero frame indices, without changing gate tolerances.

## Reproduction

Use the usual documented CPU Release configuration with tests enabled, then:

```sh
cmake --build build -j4 --target motioncorr cpu_interpolation_xcoords runner_numerics
ctest --test-dir build -R '^CpuInterpolationXcoords$' --output-on-failure
```

The optional kernel benchmark runs frozen main and actual production code in one
process, with one warmup per arm and alternating order by pair. It includes cache
allocation and coordinate construction in candidate timing. Inputs and output
reset are outside timing, as are full bitwise comparisons after every pair.
It times either the summed reconstruction or the materialized-frame path:

```sh
OMP_WAIT_POLICY=PASSIVE python3 docs/cpu_interpolation_xcoords_20261014/run_kernel.py \
  --expected-host small-refmac-machine --cpus-j1 "$J1_CPUS" --cpus-j4 "$J4_CPUS" \
  --binary /absolute/build/cpu_interpolation_xcoords --source-sha "$BINARY_BUILD_SHA" \
  --out /absolute/evidence/cpu64-kernel
```

Select both CPU lists from the host's actual topology and allowed affinity before
running. `--cpus-j1` requires exactly one CPU; `--cpus-j4` requires four distinct
CPUs. Ranges and comma-separated CPU indices are supported. The driver rejects a
hostname mismatch, malformed/duplicate CPU lists, or CPUs outside its allowed
affinity **before creating output or starting a workload**. The expected hostname
defaults to `small-refmac-machine`; a different venue requires an explicit
`--expected-host` naming that observed host. Each workload's taskset affinity is
queried and checked before measurement. No fixed CPU 0–3 assumption remains.

The portable `run_products.py` adapter accepts the same venue arguments plus
`--base`, `--candidate`, `--base-source-sha`, `--candidate-source-sha`, `--data`,
and a new `--out` directory. The required full 40-character SHAs attest each
binary's actual build source, not the driver's checkout. The kernel driver also
requires `--source-sha`. Both receipts label these as caller attestations, not
automatic verification of the build or a clean tree; retain archive/build commands
and binary hashes. Historical receipts are preserved unchanged. It directly runs the
agreed matrix using the existing strict product comparator. It does not call
#179's older harness, whose fixed CPU mask would be unsafe to reuse unchecked on
a different host. The matrix is three alternating synthetic local j4 pairs plus
one warmup pair, and one identity pair each for synthetic global j1/global j4/local
j1 and tutorial local j4 (DW, save-noDW, even/odd). Single-pair wall and RSS values
are diagnostics. Three synthetic pairs are also insufficient for a movie-speed
verdict.

Use a global benchmark lock and no overlapping build/test/movie timing. Record
CPU mask, host/compiler/flags/input/source/binary hashes and raw pairs. The marker
`affinity-confirmed` is a reminder, not an implementation of CPU ownership checks.
This benchmark cannot establish a complete-movie speedup or peak-RSS improvement.
Whole movies must compare complete MRC/STAR inventories on fixed matching hosts.

## Results

CPU Release build passed with GCC 13.3.0, CMake 3.28.3 and no fast-math.
The six focused checks passed: the 480-configuration exact matrix,
SyntheticRegression, RunnerInterpolateRecenter, RunnerInterpolateShifts,
RunnerModelParser and MicrographModelBounds. The initial four-test run omitted
building the existing `runner_numerics` helper and failed RunnerModelParser with
FileNotFoundError. After building that helper, all six passed. Both logs are kept;
there was no source or gate change to resolve that setup failure.

`reference-provenance.txt` verifies the complete frozen functions against main
byte for byte after the documented function-name/thread-argument substitutions.
`interpolation-divisions.txt` records GCC's outlined OpenMP loops. Each original
loop has one y division and two static sites for x division (compiler-unrolled
copies). The candidate retains the y division and removes both x division sites.
This confirms generated-code mechanism, not runtime benefit.

Draft PR #181 publishes the same tested tree as
`cffe054a8d178c2788995fa7c9a3763e514f949e`. CI run 513
(`38649220847`) passed native Linux's 53/53 CTests, the known-motion aggregate,
canonical fixture checks, smoke checks and failure controls. CUDA compilation
also passed; native GPU execution was not run. The complete local CTest suite
and other CPU architectures remain UNRUN here. The container-only kernel and
whole-product results below supplement that unchanged production code.

## Measurement venue

All timing in this report is from container `442a2f5ea6ec`, using an exposed Intel
Xeon Platinum 8573C, nine visible CPU IDs (0–8), an 8-CPU quota, and an 8 GiB
memory limit. Both arms used CPU mask `0` at j1 and `0-3` at j4. OpenMP waiting was
PASSIVE, dynamic teams were disabled, and binding used `close` / `cores`.

CPU64 timing is **UNRUN**. Container and VM results are separate; no cpu64
performance claim is made. Hostname and CPU-mask checks in the portable drivers
prevent silently substituting another venue. Physical-host exclusivity and
per-PID `/proc` ownership are not certified in this container.

## Container measurements

The production code remains `cffe054`; the product receipt pins its portable
measurement driver by SHA-256 and records the local evidence commit. Both arms use GCC 13.3.0, Release `-O3 -DNDEBUG`, identical
FFTW/system libraries and input hashes, with no fast-math. The matching host has
an 8-CPU quota and 8 GiB memory limit; affinity, OpenMP waiting/binding and binary
hashes are recorded in the receipts. Physical-host exclusivity and per-PID
`/proc` ownership are not certified. This is bounded container evidence, not a
clean cpu64 profiling verdict.

All 24 measured kernel-pair comparisons, and their excluded warmup comparisons,
had identical output bits. Medians are reference/candidate; the intervals below
are descriptive 96.875% sign-median intervals from six paired differences within
one process, not whole-job confidence intervals:

- 3710 x 3838 x 24, summed, j1: **5.924 / 4.501 s**; paired median -1.212 s,
  interval [-1.813, +0.824] s. Five of six pairs improved; the large-geometry
  speed verdict remains unresolved.
- Same geometry, summed, j4: **4.194 / 3.339 s**; paired median -0.548 s,
  interval [-1.453, +6.372] s. The large positive difference is retained.
  Speed verdict remains unresolved.
- 512 x 512 x 16, materialized frames, j1: **0.09359 / 0.06978 s**;
  all six pairs improved, interval [-0.03839, -0.00665] s. This supports an
  improvement for this small, within-process kernel case only.
- Same small geometry, materialized frames, j4: **0.05681 / 0.04601 s**;
  interval [-0.02013, +0.06080] s. Speed verdict remains unresolved.

`kernel/` keeps every raw measured pair and stderr record. No outlier was removed
and no record was pooled with the dose-weighting experiment or any VM result.

The complete product matrix passed **8 strict tree comparisons**, with
**42 canonical MRC/STAR file pairs** (26 MRC pairs). The existing comparator
normalizes only its documented writer timestamp/root fields; PDF files are
inventoried, and timing-bearing logs are excluded. Full raw run logs, commands,
input/binary hashes, wall/user/sys measurements, RSS and canonical hashes
are under `products-container/`.

Three measured synthetic local j4 pairs have reference/candidate wall medians
1.0505 / 0.9364 s and paired differences [-0.3905, -0.1036, +0.0601] s. Three
pairs with mixed signs cannot establish a job-speed improvement. The global
j1/global j4/local j1 checks have one pair each and establish identity only:
reference/candidate diagnostic wall values were 0.6318 / 0.5458 s, 0.5096 /
0.5391 s, and 1.0868 / 0.9581 s respectively. Every individual run, including the
excluded synthetic warmup pair, is retained in the raw receipt.

The tutorial 5 x 5 j4 DW/save-noDW/even-odd identity pair was **46.214 / 41.591 s**.
This is a single diagnostic observation, **not a measured movie-speed verdict**.
Peak RSS was 4,601,288 / 4,600,804 KiB, both about 4.388 GiB. The extra cache has
not established a whole-movie peak-RSS reduction.

The numerical contract and removal of repeated x division are established.
The large-geometry kernel and whole-movie speed gains remain unresolved. Keep
this as a draft experiment pending a repeatable, matching-host performance win.
Combined runs with #178, #179 or #180, and all cpu64 timing, remain UNRUN.
