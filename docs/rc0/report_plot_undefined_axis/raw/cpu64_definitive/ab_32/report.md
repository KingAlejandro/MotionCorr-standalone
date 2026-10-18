# MotionCorr compare: main vs fix

## Provenance

- kit: `None`
- arm `main`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/home/ubuntu/mc-w-d13/build-fix/motioncorr` sha256 `68dc7ac11049bb15`; source `b82d25f4dda6bca746e4206fed1272851cc6a5ce` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: small-refmac-machine, AMD EPYC 7763 64-Core Processor, 64 CPUs, lane 48-55, load1 2.1, clocksource kvm-clock, THP always [madvise] never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 32 run, 32 clean, target 32 clean, at most 32
- input: `movies2.star` in `/dev/shm/mc-w-d13-definitive/data`, 2 movies, STAR sha256 `aa019332ca8825b2`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`
- command: `/home/ubuntu/mc-w-d13/src-fix/tools/profiling/mcprof.py compare main=/home/ubuntu/mc-w-d13/build-main/motioncorr fix=/home/ubuntu/mc-w-d13/build-fix/motioncorr --source main=/home/ubuntu/mc-w-d13/src-main --source fix=/home/ubuntu/mc-w-d13/src-fix --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 --commit fix=b82d25f4dda6bca746e4206fed1272851cc6a5ce --data /dev/shm/mc-w-d13-definitive/data --star movies2.star --work /dev/shm/mc-w-d13-definitive/ab_32 --cpus 48-55 --runner-cpus 56-59 --no-lock --lane-wait 300 --warmup 1 --pairs 32 --max-rounds 32 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 32 | 17.398 | 0.113 | 17.228-17.561 | 131.466 | 3206 | 3358942 | 46 | - | - |
| fix | 32 | 17.400 | 0.086 | 17.237-17.616 | 131.510 | 3213 | 3353833 | 50 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 5.1-10.2, max foreign CPU on lane 0.01 cores, wall outlier rounds none
- `fix`: load1 6.2-10.2, max foreign CPU on lane 0.01 cores, wall outlier rounds [2, 12]

Rounds: 32 planned, 32 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 16, BA 16.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s, r21 1 s, r22 1 s, r23 1 s, r24 1 s, r25 1 s, r26 1 s, r27 1 s, r28 3 s, r29 1 s, r30 1 s, r31 1 s, r32 1 s.

### `fix` vs `main`: **not resolved (below noise 0.116 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 32 | -0.000 | -0.090..+0.058 | -0.141..+0.276 | -0.084..+0.052 (98.0%) | 0.116 | 16+/16- p=1 | -0.00% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second -0.078 s (n=16), first +0.054 s (n=16); cost of running second -0.066 s.
Paired differences (s): +0.019, +0.056, -0.008, +0.008, -0.071, +0.154, -0.049, +0.022, -0.096, +0.135, -0.114, +0.276, -0.141, +0.102, -0.089, +0.149, -0.126, -0.132, +0.065, +0.072, -0.084, -0.028, -0.015, +0.012, -0.138, -0.094, -0.120, +0.052, -0.015, +0.009, +0.043, +0.200

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
