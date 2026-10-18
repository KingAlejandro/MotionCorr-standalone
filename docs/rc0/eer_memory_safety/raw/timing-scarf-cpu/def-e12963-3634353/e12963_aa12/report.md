# MotionCorr compare: main vs main_null

## Provenance

- kit: `None`
- arm `main`: `/tmp/wd10-12963-3634353/build-main/motioncorr` sha256 `6a017db68bc6da72`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- arm `main_null`: `/tmp/wd10-12963-3634353/build-main/motioncorr` sha256 `6a017db68bc6da72`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- host: cn070.scarf.rl.ac.uk, AMD EPYC 7502 32-Core Processor, 64 CPUs, lane 0-15, load1 10.7, clocksource tsc, THP [always] madvise never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 12 run, 12 clean, target 12 clean, at most 12
- input: `movies.star` in `/tmp/wd10-12963-3634353/data-12963`, 1 movies, STAR sha256 `ae611d612a3f8979`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.282051282051282 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --expected_frames 39 --seed 1 --skip_report_pdf --j 16`
- command: `/tmp/wd10-12963-3634353/src-fix/tools/profiling/mcprof.py compare main=/tmp/wd10-12963-3634353/build-main/motioncorr main_null=/tmp/wd10-12963-3634353/build-main/motioncorr --source main=/tmp/wd10-12963-3634353/src-main --source main_null=/tmp/wd10-12963-3634353/src-main --commit main=71ab841e69869b615555bb02f8f393db59c22d73 --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 --data /tmp/wd10-12963-3634353/data-12963 --star movies.star --work /work4/scd/scarf1415/W-D10/def-e12963-3634353/e12963_aa12 --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 12 --no-lock -- --use_own --dose_weighting --dose_per_frame 1.282051282051282 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --expected_frames 39 --seed 1 --skip_report_pdf --j 16`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 9.502 | 0.032 | 9.466-9.531 | 85.739 | 6576 | 172308 | 7 | - | - |
| main_null | 12 | 9.494 | 0.016 | 9.446-9.515 | 85.716 | 6561 | 171262 | 0 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 7.4-10.2, max foreign CPU on lane 0.09 cores, wall outlier rounds none
- `main_null`: load1 7.3-9.3, max foreign CPU on lane 0.09 cores, wall outlier rounds [3]

Rounds: 12 planned, 12 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `main_null` 0 (alone 0). Kept orders: AB 6, BA 6.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s.

### `main_null` vs `main`: **not resolved (below noise 0.038 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.010 | -0.033..+0.007 | -0.054..+0.028 | -0.043..+0.022 (96.1%) | 0.038 | 4+/8- p=0.388 | -0.11% |

Reason: CI of median includes 0. Positive differences mean `main_null` is slower.
Positional: median B-A when `main_null` ran second -0.005 s (n=6), first -0.019 s (n=6); cost of running second +0.007 s.
Paired differences (s): +0.002, -0.054, -0.043, -0.025, -0.006, -0.014, +0.022, +0.028, -0.004, +0.026, -0.029, -0.047

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| main_null | PASS | 4 | 1 | 1 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
