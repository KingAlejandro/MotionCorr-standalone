# MotionCorr compare: main vs fix

## Provenance

- kit: `None`
- arm `main`: `/tmp/wd10-12963-3634353/build-main/motioncorr` sha256 `6a017db68bc6da72`; source `71ab841e69869b615555bb02f8f393db59c22d73` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- arm `fix`: `/tmp/wd10-12963-3634353/build-fix/motioncorr` sha256 `a3f2a19e6d134e65`; source `97fb9fda5902f4bd5c2aab7c40ae4064637b5125` (given on command line); --profile present
  - linked: libfftw3.so.3=/lib64/libfftw3.so.3, libfftw3f.so.3=/lib64/libfftw3f.so.3, libtiff.so.5=/lib64/libtiff.so.5
- host: cn070.scarf.rl.ac.uk, AMD EPYC 7502 32-Core Processor, 64 CPUs, lane 0-15, load1 4.7, clocksource tsc, THP [always] madvise never
- settle: {"settled": true, "waited_s": 0.0}
- rounds: 32 run, 32 clean, target 32 clean, at most 32
- input: `movies.star` in `/tmp/wd10-12963-3634353/data-12963`, 1 movies, STAR sha256 `ae611d612a3f8979`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.282051282051282 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --expected_frames 39 --seed 1 --skip_report_pdf --j 16`
- command: `/tmp/wd10-12963-3634353/src-fix/tools/profiling/mcprof.py compare main=/tmp/wd10-12963-3634353/build-main/motioncorr fix=/tmp/wd10-12963-3634353/build-fix/motioncorr --source main=/tmp/wd10-12963-3634353/src-main --source fix=/tmp/wd10-12963-3634353/src-fix --commit main=71ab841e69869b615555bb02f8f393db59c22d73 --commit fix=97fb9fda5902f4bd5c2aab7c40ae4064637b5125 --data /tmp/wd10-12963-3634353/data-12963 --star movies.star --work /work4/scd/scarf1415/W-D10/def-e12963-3634353/e12963_ab32 --cpus 0-15 --runner-cpus 16-19 --warmup 1 --pairs 32 --no-lock -- --use_own --dose_weighting --dose_per_frame 1.282051282051282 --patch_x 5 --patch_y 5 --bfactor 150 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --expected_frames 39 --seed 1 --skip_report_pdf --j 16`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 32 | 9.509 | 0.044 | 9.440-9.649 | 85.840 | 6561 | 171592 | 12 | - | - |
| fix | 32 | 9.487 | 0.017 | 9.456-9.538 | 85.625 | 6554 | 171603 | 13 | - | - |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 5.8-13.4, max foreign CPU on lane 0.10 cores, wall outlier rounds [10, 30]
- `fix`: load1 5.7-13.2, max foreign CPU on lane 0.14 cores, wall outlier rounds [8]

Rounds: 32 planned, 32 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 16, BA 16.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s, r21 1 s, r22 1 s, r23 1 s, r24 1 s, r25 1 s, r26 1 s, r27 1 s, r28 1 s, r29 1 s, r30 1 s, r31 1 s, r32 1 s.

### `fix` vs `main`: **not resolved (below noise 0.033 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 32 | -0.025 | -0.044..+0.000 | -0.134..+0.073 | -0.040..-0.007 (98.0%) | 0.033 | 9+/23- p=0.0201 | -0.26% |

Reason: |median| does not exceed noise. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second -0.029 s (n=16), first -0.017 s (n=16); cost of running second -0.006 s.
Paired differences (s): -0.035, +0.002, -0.025, -0.047, +0.015, -0.074, -0.043, -0.025, -0.062, -0.134, -0.029, +0.056, -0.020, -0.040, -0.007, +0.073, +0.001, +0.000, -0.109, +0.023, -0.048, -0.017, -0.034, +0.023, -0.029, -0.019, -0.025, +0.005, -0.026, -0.128, -0.064, -0.016

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 4 | 1 | 1 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
