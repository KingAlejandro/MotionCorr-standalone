# MotionCorr compare: main vs main_null

## Provenance

- kit: `None`
- arm `main`: `/tmp/wd10-f3-3634354/build-main/motioncorr` sha256 `993a19317385c1aa`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- arm `main_null`: `/tmp/wd10-f3-3634354/build-main/motioncorr` sha256 `993a19317385c1aa`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- host: cn1084.scarf.rl.ac.uk, AMD EPYC 7502P 32-Core Processor, 64 CPUs, lane 0-15, load1 9.1, clocksource tsc, THP [always] madvise never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 12 run, 12 clean, target 12 clean, at most 12
- input: `movies.star` in `/tmp/wd10-f3-3634354/data-f3`, 1 movies, STAR sha256 `9956244336b17ccc`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5 --bfactor 150 --eer_grouping 40 --eer_upsampling 1 --expected_frames 58 --seed 1 --skip_report_pdf --j 16`
- command: `/tmp/wd10-f3-3634354/src-fix/tools/profiling/mcprof.py compare main=/tmp/wd10-f3-3634354/build-main/motioncorr main_null=/tmp/wd10-f3-3634354/build-main/motioncorr --source main=/tmp/wd10-f3-3634354/src-main --source main_null=/tmp/wd10-f3-3634354/src-main --commit main=71ab841e69869b615555bb02f8f393db59c22d73 --commit main_null=71ab841e69869b615555bb02f8f393db59c22d73 --data /tmp/wd10-f3-3634354/data-f3 --star movies.star --work /work4/scd/scarf1415/W-D10/def-f3-3634354/e10474f3_aa12 --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 12 --no-lock -- --use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5 --bfactor 150 --eer_grouping 40 --eer_upsampling 1 --expected_frames 58 --seed 1 --skip_report_pdf --j 16`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 15.153 | 0.039 | 15.088-15.226 | 142.371 | 9497 | 241616 | 0 | - | - |
| main_null | 12 | 15.164 | 0.041 | 15.110-15.331 | 142.255 | 9483 | 239512 | 9 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 7.5-10.8, max foreign CPU on lane 0.09 cores, wall outlier rounds none
- `main_null`: load1 8.3-10.3, max foreign CPU on lane 0.09 cores, wall outlier rounds [10]

Rounds: 12 planned, 12 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `main_null` 0 (alone 0). Kept orders: AB 6, BA 6.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s.

### `main_null` vs `main`: **not resolved (below noise 0.043 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | +0.005 | -0.017..+0.042 | -0.062..+0.200 | -0.018..+0.061 (96.1%) | 0.043 | 6+/6- p=1 | +0.03% |

Reason: CI of median includes 0. Positive differences mean `main_null` is slower.
Positional: median B-A when `main_null` ran second -0.013 s (n=6), first +0.023 s (n=6); cost of running second -0.018 s.
Paired differences (s): -0.018, -0.003, +0.035, +0.033, -0.017, -0.057, +0.135, +0.061, -0.062, +0.200, -0.010, +0.012

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| main_null | PASS | 4 | 1 | 1 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
