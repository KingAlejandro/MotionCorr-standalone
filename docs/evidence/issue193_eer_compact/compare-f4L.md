# MotionCorr compare: base vs cand

## Provenance

- kit: `None`
- arm `base`: `/dev/shm/193/build-base/motioncorr` sha256 `9fd85f4592c6da53`; source `0ac2726a` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/193/build-cand/motioncorr` sha256 `3b84a17ca6caea47`; source `a86a334c` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 4.1, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 6 run, 6 clean, target 6 clean, at most 6
- CUDA device timing in --profile passes: `base` on, `cand` on
- input: `movies.star` in `/dev/shm/193/data/f4`, 2 movies, STAR sha256 `81c92eb143cb9e7d`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames 144 --eer_grouping 40 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare base=build-base/motioncorr cand=build-cand/motioncorr --data /dev/shm/193/data/f4 --work /dev/shm/193/work-f4L --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 6 --profile-pass 3 --commit base=0ac2726a --commit cand=a86a334c -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames 144 --eer_grouping 40 --eer_upsampling 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 6 | 25.780 | 0.059 | 25.493-25.861 | 128.246 | 12296 | 6787175 | 0 | 20446 | 20455 |
| cand | 6 | 20.821 | 0.141 | 20.697-20.956 | 99.509 | 7687 | 4195685 | 0 | 20446 | 20455 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `base`: load1 4.5-6.3, max foreign CPU on lane 0.00 cores, wall outlier rounds [6]
- `cand`: load1 4.9-6.6, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 6 planned, 6 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 3, BA 3.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s.

### `cand` vs `base`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 6 | -4.952 | -5.004..-4.854 | -5.018..-4.797 | -5.018..-4.797 (96.9%) | 0.091 | 0+/6- p=0.0312 | -19.21% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -5.009 s (n=3), first -4.916 s (n=3); cost of running second -0.046 s.
Paired differences (s): -5.018, -4.916, -4.834, -4.988, -5.009, -4.797

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

Movie wall (steady median): 12626.0 -> 10203.1 ms (-2422.88 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 3.78 | 3.77 | -0.01 | 0.50 | -0.01 | -12 |
| read gain | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| session and device ingest | 1.38 | 1.54 | +0.16 | 0.50 | +0.16 | +14 |
| **host read movie** | 9892.90 | 8356.86 | -1536.04 * | 193.36 | -939.68 | +79550 |
| allocate host sum | 0.02 | 0.02 | +0.00 | 0.50 | +0.00 | -1 |
| gain and sum | 963.82 | 561.71 | -402.10 | 1165.02 | -401.93 | -34685 |
| hot pixels | 14.03 | 10.62 | -3.41 | 16.65 | -3.31 | -2682 |
| fix defects | 5.28 | 4.04 | -1.24 | 1.54 | -1.24 | -46 |
| release preprocessing | 0.30 | 0.28 | -0.01 | 0.50 | -0.01 | -2 |
| **global fft** | 53.37 | 558.45 | +505.08 * | 5.55 | +504.92 * | +33 |
| power spectrum | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| global alignment | 39.90 | 39.98 | +0.08 | 0.63 | +0.08 | -96 |
| allocate reconstruction | 0.02 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 52.88 | 52.88 | +0.00 | 0.50 | +0.00 | -6 |
| patch alignment | 137.00 | 137.57 | +0.57 | 1.45 | +0.52 | -312 |
| fit polynomial | 8.78 | 8.60 | -0.18 | 1.36 | -0.18 | -151 |
| release alignment | 2.85 | 2.94 | +0.09 | 1.28 | +0.00 | -68 |
| dose weighting | 127.27 | 138.69 | +11.42 | 63.60 | +11.38 | +10911 |
| **movie teardown** | 1322.12 | 324.85 | -997.27 * | 49.73 | -996.62 * | -210 |
| submit model and plot | 0.20 | 0.18 | -0.02 | 0.50 | -0.02 | -10 |
