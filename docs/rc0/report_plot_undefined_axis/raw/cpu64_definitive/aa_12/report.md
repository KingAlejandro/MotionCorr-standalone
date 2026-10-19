# MotionCorr compare: main vs main_null

## Provenance

- kit: `None`
- arm `main`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `main_null`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: small-refmac-machine, AMD EPYC 7763 64-Core Processor, 64 CPUs, lane 48-55, load1 9.6, clocksource kvm-clock, THP always [madvise] never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 12 run, 12 clean, target 12 clean, at most 12
- input: `movies2.star` in `/dev/shm/mc-w-d13-definitive/data`, 2 movies, STAR sha256 `aa019332ca8825b2`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`
- command: `/home/ubuntu/mc-w-d13/src-fix/tools/profiling/mcprof.py compare main=/home/ubuntu/mc-w-d13/build-main/motioncorr main_null=/home/ubuntu/mc-w-d13/build-main/motioncorr --source main=/home/ubuntu/mc-w-d13/src-main --source main_null=/home/ubuntu/mc-w-d13/src-main --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 --commit main_null=1afa03b57afbae42138ee30c3545b57b5a74c321 --data /dev/shm/mc-w-d13-definitive/data --star movies2.star --work /dev/shm/mc-w-d13-definitive/aa_12 --cpus 48-55 --runner-cpus 56-59 --no-lock --lane-wait 300 --warmup 1 --pairs 12 --max-rounds 12 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 17.476 | 0.078 | 17.377-17.612 | 132.092 | 3219 | 3369578 | 43 | - | - |
| main_null | 12 | 17.425 | 0.061 | 17.349-17.511 | 131.801 | 3217 | 3338598 | 46 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 9.2-9.9, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `main_null`: load1 9.0-10.0, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 12 planned, 12 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `main_null` 0 (alone 0). Kept orders: AB 6, BA 6.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s.

### `main_null` vs `main`: **not resolved (below noise 0.112 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.043 | -0.114..+0.029 | -0.259..+0.107 | -0.181..+0.038 (96.1%) | 0.112 | 4+/8- p=0.388 | -0.25% |

Reason: CI of median includes 0. Positive differences mean `main_null` is slower.
Positional: median B-A when `main_null` ran second -0.081 s (n=6), first +0.000 s (n=6); cost of running second -0.040 s.
Paired differences (s): -0.020, -0.181, +0.038, +0.097, -0.259, -0.026, -0.092, -0.060, -0.187, +0.107, -0.070, +0.026

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| main_null | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
