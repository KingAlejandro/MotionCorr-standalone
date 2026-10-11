# MotionCorr compare: main vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-small/build-cand/motioncorr` sha256 `711196168ce32414`; source `28a290d` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 13.0, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 684 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 1.5}
- rounds: 10 run, 6 clean, target 6 clean, at most 16
- input: `movies.star` in `/home/alex/mc-small/data96`, 96 movies, STAR sha256 `b906a827b28fc122`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py compare main=/home/alex/mc-small/build-main/motioncorr cand=/home/alex/mc-small/build-cand/motioncorr --data /home/alex/mc-small/data96 --star movies.star --work /home/alex/mc-small/runs/kit96w --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --source main=/home/alex/mc-small/src-main --source cand=/home/alex/mc-small/src-cand --commit main=7d64043 --commit cand=28a290d --settle-timeout 600 --pairs 6 --max-rounds 16 --lane-wait 300 --warmup 1 --lock-timeout 14400 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 6 | 26.582 | 2.108 | 25.025-27.620 | 73.883 | 368 | 177114 | 10 | 3362 | 3371 |
| cand | 6 | 20.334 | 0.350 | 19.685-21.279 | 35.147 | 368 | 181420 | 13 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 15.5-17.4, max foreign CPU on lane 0.02 cores, wall outlier rounds none
- `cand`: load1 15.0-16.9, max foreign CPU on lane 0.23 cores, wall outlier rounds none

Rounds: 10 planned, 6 retained, 4 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 2 (alone 2), `cand` 2 (alone 2). Kept orders: AB 4, BA 2.

WARNING: kept pairs are unbalanced by order (AB 4, BA 2): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 2 (BA): main: foreign CPU on lane 0.53 cores
- round 3 (AB): main: foreign CPU on lane 0.29 cores
- round 6 (BA): cand: foreign CPU on lane 1.05 cores
- round 8 (BA): cand: foreign CPU on lane 0.30 cores

Lane wait before round: r1 1 s, r2 4 s, r3 301 s (timed out at 1.04 busy cores), r4 1 s, r5 2 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s.

### `cand` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 6 | -5.921 | -6.954..-4.740 | -7.935..-4.626 | -7.935..-4.626 (96.9%) | 1.706 | 0+/6- p=0.0312 | -22.28% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -5.921 s (n=4), first -6.303 s (n=2); cost of running second +0.191 s.
Paired differences (s): -6.973, -7.935, -4.626, -6.897, -4.945, -4.671

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 297 | 96 | 100 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.
