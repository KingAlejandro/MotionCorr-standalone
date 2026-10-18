# MotionCorr compare: main vs fix

## Provenance

- kit: `None`
- arm `main`: `/tmp/wd10-f3-3634354/build-main/motioncorr` sha256 `993a19317385c1aa`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- arm `fix`: `/tmp/wd10-f3-3634354/build-fix/motioncorr` sha256 `8acd81e722e191c3`; source `97fb9fda5902f4bd5c2aab7c40ae4064637b5125` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- host: cn1084.scarf.rl.ac.uk, AMD EPYC 7502P 32-Core Processor, 64 CPUs, lane 0-15, load1 9.5, clocksource tsc, THP [always] madvise never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 32 run, 32 clean, target 32 clean, at most 32
- input: `movies.star` in `/tmp/wd10-f3-3634354/data-f3`, 1 movies, STAR sha256 `9956244336b17ccc`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5 --bfactor 150 --eer_grouping 40 --eer_upsampling 1 --expected_frames 58 --seed 1 --skip_report_pdf --j 16`
- command: `/tmp/wd10-f3-3634354/src-fix/tools/profiling/mcprof.py compare main=/tmp/wd10-f3-3634354/build-main/motioncorr fix=/tmp/wd10-f3-3634354/build-fix/motioncorr --source main=/tmp/wd10-f3-3634354/src-main --source fix=/tmp/wd10-f3-3634354/src-fix --commit main=71ab841e69869b615555bb02f8f393db59c22d73 --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 --data /tmp/wd10-f3-3634354/data-f3 --star movies.star --work /work4/scd/scarf1415/W-D10/def-f3-3634354/e10474f3_ab32 --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 32 --no-lock -- --use_own --dose_weighting --dose_per_frame 1.0 --patch_x 5 --patch_y 5 --bfactor 150 --eer_grouping 40 --eer_upsampling 1 --expected_frames 58 --seed 1 --skip_report_pdf --j 16`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 32 | 15.151 | 0.044 | 15.086-15.283 | 142.502 | 9484 | 241619 | 9 | - | - |
| fix | 32 | 15.162 | 0.056 | 15.100-15.387 | 142.342 | 9475 | 240275 | 10 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 8.0-10.9, max foreign CPU on lane 0.09 cores, wall outlier rounds [14, 23]
- `fix`: load1 7.6-10.9, max foreign CPU on lane 0.09 cores, wall outlier rounds [3, 24]

Rounds: 32 planned, 32 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 16, BA 16.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s, r21 1 s, r22 1 s, r23 1 s, r24 1 s, r25 1 s, r26 1 s, r27 1 s, r28 1 s, r29 1 s, r30 1 s, r31 1 s, r32 1 s.

### `fix` vs `main`: **not resolved (below noise 0.039 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 32 | +0.002 | -0.019..+0.035 | -0.158..+0.257 | -0.018..+0.029 (98.0%) | 0.039 | 17+/15- p=0.86 | +0.01% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.013 s (n=16), first -0.010 s (n=16); cost of running second +0.012 s.
Paired differences (s): +0.106, -0.019, +0.139, +0.003, +0.027, -0.046, -0.008, +0.052, +0.077, +0.029, -0.047, -0.015, +0.013, -0.158, +0.012, +0.103, -0.023, -0.006, -0.011, +0.006, +0.019, +0.029, -0.157, +0.257, +0.001, -0.018, -0.019, -0.028, +0.053, -0.017, +0.106, -0.099

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 4 | 1 | 1 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
