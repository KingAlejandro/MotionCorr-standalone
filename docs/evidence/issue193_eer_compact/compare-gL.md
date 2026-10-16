# MotionCorr compare: base vs cand

## Provenance

- kit: `None`
- arm `base`: `/dev/shm/193/build-base/motioncorr` sha256 `9fd85f4592c6da53`; source `0ac2726a` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/193/build-cand/motioncorr` sha256 `3b84a17ca6caea47`; source `a86a334c` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 3.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 6 run, 6 clean, target 6 clean, at most 6
- CUDA device timing in --profile passes: `base` on, `cand` on
- input: `movies.star` in `/dev/shm/193/data/g`, 1 movies, STAR sha256 `593b962db54c80f8`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.282051 --bfactor 150 --seed 1 --expected_frames 39 --eer_grouping 49 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --gainref gain.gain`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare base=build-base/motioncorr cand=build-cand/motioncorr --data /dev/shm/193/data/g --work /dev/shm/193/work-gL --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 6 --profile-pass 3 --commit base=0ac2726a --commit cand=a86a334c -- --use_own --dose_weighting --dose_per_frame 1.282051 --bfactor 150 --seed 1 --expected_frames 39 --eer_grouping 49 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --gainref gain.gain`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 6 | 5.250 | 0.033 | 5.212-5.295 | 20.865 | 3720 | 1040136 | 0 | 6120 | 6133 |
| cand | 6 | 4.605 | 0.048 | 4.567-4.661 | 17.448 | 2358 | 729604 | 0 | 6140 | 6149 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `base`: load1 3.2-4.5, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `cand`: load1 3.3-4.2, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 6 planned, 6 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 3, BA 3.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s.

### `cand` vs `base`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 6 | -0.640 | -0.669..-0.616 | -0.694..-0.599 | -0.694..-0.599 (96.9%) | 0.045 | 0+/6- p=0.0312 | -12.20% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -0.624 s (n=3), first -0.674 s (n=3); cost of running second +0.025 s.
Paired differences (s): -0.599, -0.613, -0.624, -0.694, -0.657, -0.674

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 9 | 1 | 5 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `base` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `base`

Movie wall (steady median): 4681.3 -> 4018.6 ms (-662.64 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.84 | 1.91 | +0.06 | 0.83 | +0.07 | -1 |
| read gain | 388.04 | 391.30 | +3.26 | 51.08 | +3.30 | +1 |
| session and device ingest | 161.31 | 161.23 | -0.09 | 47.02 | +0.03 | +39 |
| **host read movie** | 3131.35 | 2727.10 | -404.25 * | 166.56 | -435.12 | -25996 |
| allocate host sum | 0.01 | 0.02 | +0.00 | 0.50 | +0.00 | +0 |
| **gain and sum** | 228.36 | 129.57 | -98.79 * | 8.49 | -98.67 * | +18 |
| hot pixels | 74.11 | 70.99 | -3.12 | 5.62 | -3.03 | -7 |
| fix defects | 25.04 | 14.23 | -10.81 | 25.43 | -10.81 | -266 |
| release preprocessing | 0.29 | 0.27 | -0.02 | 0.50 | -0.02 | +0 |
| **global fft** | 14.31 | 151.55 | +137.24 * | 3.60 | +137.03 * | +38 |
| power spectrum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| global alignment | 11.87 | 12.23 | +0.36 | 0.50 | +0.36 | +5 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 14.26 | 14.20 | -0.06 | 0.60 | -0.06 | +1 |
| **patch alignment** | 181.27 | 178.25 | -3.02 | 19.36 | -3.33 | -61 * |
| fit polynomial | 2.20 | 2.18 | -0.02 | 0.50 | -0.02 | -0 |
| release alignment | 2.01 | 2.03 | +0.02 | 0.50 | +0.02 | +0 |
| dose weighting | 60.06 | 57.80 | -2.26 | 25.42 | -2.26 | +1 |
| **movie teardown** | 384.74 | 103.58 | -281.16 * | 48.31 | -280.80 * | +2 |
| submit model and plot | 0.15 | 0.14 | -0.00 | 0.50 | -0.00 | -0 |
