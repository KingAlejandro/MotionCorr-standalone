# MotionCorr compare: main vs main_null

## Provenance

- kit: `None`
- arm `main`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `main_null`: `/home/ubuntu/mc-w-d13/build-main/motioncorr` sha256 `307a030b03785201`; source `1afa03b57afbae42138ee30c3545b57b5a74c321` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: small-refmac-machine, AMD EPYC 7763 64-Core Processor, 64 CPUs, lane 48-55, load1 9.5, clocksource kvm-clock, THP always [madvise] never
- locks: /tmp/motioncorr-cpu64-bench.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 6 run, 6 clean, target 6 clean, at most 10
- input: `movies.star` in `/home/ubuntu/mc-rc0-paired-20261017/work/tutorial`, 2 movies, STAR sha256 `65b1c972db5b06f4`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`
- command: `/home/ubuntu/mc-w-d13/src-fix/tools/profiling/mcprof.py compare main=/home/ubuntu/mc-w-d13/build-main/motioncorr main_null=/home/ubuntu/mc-w-d13/build-main/motioncorr --source main=/home/ubuntu/mc-w-d13/src-main --source main_null=/home/ubuntu/mc-w-d13/src-main --commit main=1afa03b57afbae42138ee30c3545b57b5a74c321 --commit main_null=1afa03b57afbae42138ee30c3545b57b5a74c321 --data /home/ubuntu/mc-rc0-paired-20261017/work/tutorial --star movies.star --work /home/ubuntu/mc-w-d13/aa_null --cpus 48-55 --runner-cpus 56-59 --bench-lock /tmp/motioncorr-cpu64-bench.lock --warmup 1 --pairs 6 --max-rounds 10 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.mrc --seed 1 --expected_frames 24 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 6 | 17.703 | 0.042 | 17.650-17.832 | 133.653 | 3207 | 3331495 | 39 | - | - |
| main_null | 6 | 17.691 | 0.059 | 17.650-18.125 | 133.790 | 3210 | 3355178 | 39 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 9.2-9.9, max foreign CPU on lane 0.00 cores, wall outlier rounds [5]
- `main_null`: load1 9.0-9.8, max foreign CPU on lane 0.00 cores, wall outlier rounds [5]

Rounds: 6 planned, 6 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `main_null` 0 (alone 0). Kept orders: AB 3, BA 3.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s.

### `main_null` vs `main`: **not resolved (below noise 0.171 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 6 | +0.018 | -0.030..+0.046 | -0.049..+0.293 | -0.049..+0.293 (96.9%) | 0.067 | 4+/2- p=0.688 | +0.10% |

Reason: CI of median includes 0. Positive differences mean `main_null` is slower.
Positional: median B-A when `main_null` ran second +0.034 s (n=3), first +0.001 s (n=3); cost of running second +0.017 s.
Paired differences (s): -0.049, +0.001, +0.034, +0.050, +0.293, -0.040

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| main_null | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
