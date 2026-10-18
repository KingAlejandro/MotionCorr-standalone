# MotionCorr compare: main vs fix

## Provenance

- kit: `None`
- arm `main`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/home/ubuntu/mc-w-d13/build-fix/motioncorr` sha256 `68dc7ac11049bb15`; source `b82d25f4dda6bca746e4206fed1272851cc6a5ce` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: small-refmac-machine, AMD EPYC 7763 64-Core Processor, 64 CPUs, lane 48-55, load1 6.0, clocksource kvm-clock, THP always [madvise] never
- locks: /tmp/motioncorr-cpu64-bench.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 8 run, 8 clean, target 8 clean, at most 12
- input: `movies.star` in `/home/ubuntu/mc-rc0-paired-20261017/work/tutorial`, 2 movies, STAR sha256 `65b1c972db5b06f4`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`
- command: `/home/ubuntu/mc-w-d13/src-fix/tools/profiling/mcprof.py compare main=/home/ubuntu/mc-w-d13/build-main/motioncorr fix=/home/ubuntu/mc-w-d13/build-fix/motioncorr --source main=/home/ubuntu/mc-w-d13/src-main --source fix=/home/ubuntu/mc-w-d13/src-fix --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 --commit fix=b82d25f4dda6bca746e4206fed1272851cc6a5ce --data /home/ubuntu/mc-rc0-paired-20261017/work/tutorial --star movies.star --work /home/ubuntu/mc-w-d13/ab_compare --cpus 48-55 --runner-cpus 56-59 --bench-lock /tmp/motioncorr-cpu64-bench.lock --warmup 1 --pairs 8 --max-rounds 12 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 17.630 | 0.130 | 17.511-17.661 | 132.950 | 3201 | 3369510 | 34 | - | - |
| fix | 8 | 17.681 | 0.282 | 17.494-18.367 | 133.530 | 3209 | 3355571 | 43 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 7.3-9.7, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `fix`: load1 8.0-9.8, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 8 planned, 8 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 4, BA 4.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s.

### `fix` vs `main`: **not resolved (below noise 0.424 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | +0.051 | -0.007..+0.196 | -0.131..+0.717 | -0.131..+0.717 (99.2%) | 0.141 | 4+/4- p=1 | +0.29% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.051 s (n=4), first +0.088 s (n=4); cost of running second -0.018 s.
Paired differences (s): -0.003, -0.008, -0.131, +0.183, +0.106, -0.007, +0.237, +0.717

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
