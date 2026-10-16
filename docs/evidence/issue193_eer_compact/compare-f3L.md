# MotionCorr compare: base vs cand

## Provenance

- kit: `None`
- arm `base`: `/dev/shm/193/build-base/motioncorr` sha256 `9fd85f4592c6da53`; source `0ac2726a` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/193/build-cand/motioncorr` sha256 `3b84a17ca6caea47`; source `a86a334c` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 5.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 6 run, 6 clean, target 6 clean, at most 6
- CUDA device timing in --profile passes: `base` on, `cand` on
- input: `movies.star` in `/dev/shm/193/data/f3`, 2 movies, STAR sha256 `00d3e4e0db256b87`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames 58 --eer_grouping 40 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare base=build-base/motioncorr cand=build-cand/motioncorr --data /dev/shm/193/data/f3 --work /dev/shm/193/work-f3L --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 6 --profile-pass 3 --commit base=0ac2726a --commit cand=a86a334c -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames 58 --eer_grouping 40 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 6 | 12.549 | 0.205 | 12.439-12.791 | 55.411 | 5261 | 2840738 | 0 | 8756 | 8765 |
| cand | 6 | 10.337 | 0.150 | 10.004-10.522 | 42.952 | 3416 | 1828144 | 0 | 8762 | 8771 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `base`: load1 3.7-5.3, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `cand`: load1 3.7-5.2, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 6 planned, 6 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 3, BA 3.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s.

### `cand` vs `base`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 6 | -2.307 | -2.436..-2.159 | -2.454..-2.021 | -2.454..-2.021 (96.9%) | 0.215 | 0+/6- p=0.0312 | -18.38% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -2.220 s (n=3), first -2.394 s (n=3); cost of running second +0.087 s.
Paired differences (s): -2.451, -2.021, -2.220, -2.454, -2.138, -2.394

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `base` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `base`

Movie wall (steady median): 5586.5 -> 4555.1 ms (-1031.41 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 43.83 | 43.89 | +0.06 | 1.30 | +0.06 | +2 |
| read gain | 0.07 | 0.04 | -0.03 | 0.50 | -0.03 | +0 |
| session and device ingest | 0.90 | 0.96 | +0.07 | 0.50 | +0.07 | +7 |
| **host read movie** | 4163.39 | 3453.75 | -709.65 * | 552.48 | -916.36 | -154859 |
| allocate host sum | 0.02 | 0.02 | -0.00 | 0.50 | -0.00 | -1 |
| gain and sum | 332.87 | 227.39 | -105.48 | 294.80 | -105.39 | +22414 |
| hot pixels | 17.70 | 11.93 | -5.76 | 19.88 | -5.76 | -4309 |
| fix defects | 277.82 | 278.38 | +0.57 | 28.18 | +0.59 | -290 |
| release preprocessing | 0.26 | 0.27 | +0.01 | 0.50 | +0.01 | -2 |
| **global fft** | 21.27 | 230.50 | +209.23 * | 8.56 | +209.11 * | -24 |
| power spectrum | 0.07 | 0.04 | -0.03 | 0.50 | -0.03 | -2 |
| global alignment | 25.14 | 24.78 | -0.37 | 3.21 | -0.36 | -174 |
| allocate reconstruction | 0.02 | 0.01 | -0.00 | 0.50 | -0.00 | -2 |
| global ifft | 21.43 | 21.38 | -0.04 | 0.50 | -0.04 | -13 |
| patch alignment | 60.82 | 61.41 | +0.59 | 1.98 | +0.66 | -190 |
| fit polynomial | 3.48 | 3.41 | -0.07 | 0.50 | -0.07 | -70 |
| release alignment | 2.06 | 2.09 | +0.03 | 0.50 | +0.03 | -6 |
| **dose weighting** | 75.39 | 56.56 | -18.83 * | 1.76 | -18.78 * | -16390 * |
| **movie teardown** | 539.83 | 138.15 | -401.68 * | 18.14 | -401.66 * | -121 * |
| submit model and plot | 0.18 | 0.16 | -0.02 | 0.50 | -0.02 | -10 |
