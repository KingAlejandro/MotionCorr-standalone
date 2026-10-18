# MotionCorr compare: main vs fix

## Provenance

- kit: `None`
- arm `main`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/home/ubuntu/mc-w-d13/build-fix/motioncorr` sha256 `68dc7ac11049bb15`; source `b82d25f4dda6bca746e4206fed1272851cc6a5ce` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: small-refmac-machine, AMD EPYC 7763 64-Core Processor, 64 CPUs, lane 48-55, load1 8.8, clocksource kvm-clock, THP always [madvise] never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 4 run, 4 clean, target 4 clean, at most 6
- input: `movies2.star` in `/dev/shm/mc-w-d13-pilot/data`, 2 movies, STAR sha256 `aa019332ca8825b2`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`
- command: `/home/ubuntu/mc-w-d13/src-fix/tools/profiling/mcprof.py compare main=/home/ubuntu/mc-w-d13/build-main/motioncorr fix=/home/ubuntu/mc-w-d13/build-fix/motioncorr --source main=/home/ubuntu/mc-w-d13/src-main --source fix=/home/ubuntu/mc-w-d13/src-fix --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 --commit fix=b82d25f4dda6bca746e4206fed1272851cc6a5ce --data /dev/shm/mc-w-d13-pilot/data --star movies2.star --work /dev/shm/mc-w-d13-pilot/pilot_2mov --cpus 48-55 --runner-cpus 56-59 --no-lock --warmup 1 --pairs 4 --max-rounds 6 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 4 | 17.571 | 0.066 | 17.515-17.612 | 132.524 | 3205 | 3386515 | 48 | - | - |
| fix | 4 | 17.598 | 0.040 | 17.571-17.629 | 132.611 | 3206 | 3362538 | 40 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 8.8-9.8, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `fix`: load1 9.1-9.9, max foreign CPU on lane 0.01 cores, wall outlier rounds none

Rounds: 4 planned, 4 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 2, BA 2.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s.

### `fix` vs `main`: **not resolved (4 retained pairs, 6 needed)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 4 | +0.029 | -0.003..+0.063 | -0.018..+0.086 | n/a | 0.054 | 3+/1- p=0.625 | +0.16% |

Reason: fewer than 6 retained pairs (4): no verdict and no resolution. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.034 s (n=2), first +0.029 s (n=2); cost of running second +0.002 s.
Paired differences (s): +0.086, +0.055, -0.018, +0.002

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
