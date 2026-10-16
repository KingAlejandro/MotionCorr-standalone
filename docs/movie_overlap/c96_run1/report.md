# MotionCorr compare: base vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `base`: `/home/alex/mc-overlap/build-base/motioncorr` sha256 `6dfaf2d47d6c17a6`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-overlap/build-cand/motioncorr` sha256 `088ebd8abcf18ec1`; source `76972f3` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 72,73,74,75,76,77,78,79,88,89,90,91, load1 15.2, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 (index 2), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu2-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 7 run, 5 clean, target 5 clean, at most 8
- CUDA device timing in --profile passes: `base` on, `cand` on
- input: `movies.star` in `/home/alex/mc-overlap/data96`, 96 movies, STAR sha256 `e7edbab2297bb2c1`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID MOTIONCORR_MOVIE_PREFETCH=1 MOTIONCORR_MOVIE_PREFETCH_CPUS=88-91`
- command: `kit/tools/profiling/mcprof.py compare base=build-base/motioncorr cand=build-cand/motioncorr --data data96 --work c96 --cpus 72-79,88-91 --gpu-uuid GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 --runner-cpus 123 --env MOTIONCORR_MOVIE_PREFETCH=1 --env MOTIONCORR_MOVIE_PREFETCH_CPUS=88-91 --source base=base --source cand=cand --commit base=7d64043 --commit cand=76972f3 --pairs 5 --max-rounds 8 --lane-wait 120 --profile-pass 2 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 5 | 24.862 | 2.444 | 23.765-27.098 | 62.847 | 368 | 189837 | 9 | 3362 | 3371 |
| cand | 5 | 23.767 | 0.990 | 21.954-25.407 | 37.295 | 532 | 221034 | 15 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `base`: load1 16.5-26.8, max foreign CPU on lane 0.06 cores, wall outlier rounds none
- `cand`: load1 16.1-30.8, max foreign CPU on lane 0.15 cores, wall outlier rounds none

Rounds: 7 planned, 5 retained, 2 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 1 (alone 0), `cand` 2 (alone 1). Kept orders: AB 2, BA 3.

Discarded rounds:
- round 1 (AB): base: foreign CPU on lane 1.26 cores | cand: foreign CPU on lane 1.09 cores
- round 5 (AB): cand: foreign CPU on lane 0.68 cores

Lane wait before round: r1 120 s (timed out at 2.03 busy cores), r2 114 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 3 s.

### `cand` vs `base`: **not resolved (5 retained pairs, 6 needed)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 5 | -2.004 | -2.539..-1.811 | -3.251..+1.546 | n/a | 0.792 | 1+/4- p=0.375 | -8.06% |

Reason: fewer than 6 retained pairs (5): no verdict and no resolution. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -2.175 s (n=2), first -2.004 s (n=3); cost of running second -0.085 s.
Paired differences (s): +1.546, -1.811, -2.004, -3.251, -2.539

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 297 | 96 | 100 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `base` 2, `cand` 2. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `base`

Movie wall (steady median): 228.3 -> 203.4 ms (-24.94)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.70 | 1.51 | -0.18 | 2.03 | -0.17 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 54.89 | 42.99 | -11.90 | 38.41 | -7.70 | -45 |
| host read movie | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| gain and sum | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| hot pixels | 20.65 | 19.23 | -1.43 | 23.90 | -1.50 | +0 |
| fix defects | 2.18 | 2.05 | -0.13 | 6.48 | -0.02 | -0 |
| release preprocessing | 0.30 | 0.27 | -0.03 | 2.40 | +0.00 | +0 |
| global fft | 21.84 | 21.98 | +0.14 | 0.50 | +0.14 | +0 |
| power spectrum | 0.05 | 0.06 | +0.01 | 0.50 | +0.01 | +0 |
| global alignment | 9.53 | 9.54 | +0.01 | 12.58 | -0.01 | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| global ifft | 22.05 | 22.03 | -0.03 | 0.50 | -0.01 | +0 |
| patch alignment | 28.74 | 28.25 | -0.49 | 32.25 | -0.24 | +0 |
| fit polynomial | 1.83 | 1.71 | -0.12 | 1.61 | -0.11 | +0 |
| release alignment | 2.14 | 1.86 | -0.28 | 10.55 | -0.20 | +0 |
| dose weighting | 44.87 | 43.23 | -1.64 | 17.89 | -1.62 | +0 |
| movie teardown | 4.38 | 4.04 | -0.34 | 9.64 | -0.28 | +0 |
| submit model and plot | 0.08 | 0.08 | +0.00 | 0.50 | +0.00 | +0 |
