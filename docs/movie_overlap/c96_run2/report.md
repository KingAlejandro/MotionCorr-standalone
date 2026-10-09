# MotionCorr compare: base vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `base`: `/home/alex/mc-overlap/build-base/motioncorr` sha256 `6dfaf2d47d6c17a6`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-overlap/build-cand/motioncorr` sha256 `088ebd8abcf18ec1`; source `76972f3` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 72,73,74,75,76,77,78,79,88,89,90,91, load1 23.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 (index 2), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 126 s), /tmp/motioncorr-gpu2-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 12 run, 7 clean, target 8 clean, at most 12 (TARGET NOT REACHED)
- input: `movies.star` in `/home/alex/mc-overlap/data96`, 96 movies, STAR sha256 `e7edbab2297bb2c1`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 CUDA_DEVICE_ORDER=PCI_BUS_ID MOTIONCORR_MOVIE_PREFETCH=1 MOTIONCORR_MOVIE_PREFETCH_CPUS=88-91`
- command: `kit/tools/profiling/mcprof.py compare base=build-base/motioncorr cand=build-cand/motioncorr --data data96 --work c96b --cpus 72-79,88-91 --gpu-uuid GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598 --runner-cpus 123 --env MOTIONCORR_MOVIE_PREFETCH=1 --env MOTIONCORR_MOVIE_PREFETCH_CPUS=88-91 --source base=base --source cand=cand --commit base=7d64043 --commit cand=76972f3 --pairs 8 --max-rounds 12 --lane-wait 120 --profile-pass 0 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 7 | 25.437 | 2.101 | 23.424-28.050 | 69.002 | 368 | 203873 | 17 | 3362 | 3371 |
| cand | 7 | 23.791 | 1.350 | 22.998-27.963 | 39.714 | 532 | 221237 | 11 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `base`: load1 19.3-34.4, max foreign CPU on lane 0.13 cores, wall outlier rounds none
- `cand`: load1 21.2-34.0, max foreign CPU on lane 0.13 cores, wall outlier rounds [4]

Rounds: 12 planned, 7 retained, 5 discarded (a discard removes the whole round, every arm). Discards triggered by: `base` 4 (alone 2), `cand` 3 (alone 1). Kept orders: AB 3, BA 4.

Discarded rounds:
- round 1 (AB): cand: foreign CPU on lane 1.59 cores
- round 3 (AB): base: foreign CPU on lane 0.33 cores
- round 9 (AB): base: foreign CPU on lane 0.28 cores | cand: foreign CPU on lane 0.56 cores
- round 10 (BA): cand: foreign CPU on lane 0.60 cores | base: foreign CPU on lane 0.56 cores
- round 12 (BA): base: foreign CPU on lane 0.39 cores

Lane wait before round: r1 87 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 121 s (timed out at 2.28 busy cores), r11 2 s, r12 1 s.

### `cand` vs `base`: **not resolved (below noise 2.337 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 7 | -1.055 | -2.716..-0.333 | -3.301..+1.372 | -3.301..+1.372 (98.4%) | 1.907 | 2+/5- p=0.453 | -4.15% |

Reason: CI of median includes 0. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -2.312 s (n=3), first -0.976 s (n=4); cost of running second -0.668 s.
Paired differences (s): -0.896, +1.372, -2.312, -1.055, -3.301, -3.119, +0.231

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 297 | 96 | 100 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.
