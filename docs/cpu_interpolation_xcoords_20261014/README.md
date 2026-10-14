# Exact interpolation x-coordinate experiment

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
OMP_DYNAMIC=FALSE OMP_PROC_BIND=close OMP_PLACES=cores OMP_WAIT_POLICY=PASSIVE \
  taskset -c 0 build/cpu_interpolation_xcoords --bench 3710 3838 24 1 6 sum affinity-confirmed
OMP_DYNAMIC=FALSE OMP_PROC_BIND=close OMP_PLACES=cores OMP_WAIT_POLICY=PASSIVE \
  taskset -c 0-3 build/cpu_interpolation_xcoords --bench 3710 3838 24 4 6 sum affinity-confirmed
```

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

The full CTest suite, complete movie identity/timing, other CPU architectures and
CUDA compilation/execution are UNRUN for this independent branch. No performance
result is claimed yet.
