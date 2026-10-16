# MotionCorr compare: main vs cand

## Provenance

- kit: `None`
- arm `main`: `/dev/shm/194/build-main/motioncorr` sha256 `59a08840a721d175`; source `4b849165` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/194/build-cand/motioncorr` sha256 `dc33396f20a15f1f`; source `a414ec25` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 1.2, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 8 run, 8 clean, target 8 clean, at most 8
- input: `movies.star` in `/dev/shm/194/run10164`, 2 movies, STAR sha256 `abb4e867d5733f50`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --gpu 0 --j 8 --expected_frames 8 --ingest_witness /dev/shm/194/witness-10164.txt`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare main=build-main/motioncorr cand=build-cand/motioncorr --data run10164 --work work10164 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 8 --source main=/dev/shm/194/src-main --source cand=/dev/shm/194/src-cand --commit main=4b849165 --commit cand=a414ec25 -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --gpu 0 --j 8 --expected_frames 8 --ingest_witness /dev/shm/194/witness-10164.txt`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 3.132 | 0.086 | 3.028-3.198 | 7.567 | 2263 | 1244002 | 0 | 4559 | 4567 |
| cand | 8 | 2.471 | 0.018 | 2.441-2.527 | 4.650 | 1182 | 628256 | 0 | 4614 | 4623 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 1.2-2.9, max foreign CPU on lane 0.01 cores, wall outlier rounds none
- `cand`: load1 1.2-3.1, max foreign CPU on lane 0.01 cores, wall outlier rounds [2]

Rounds: 8 planned, 8 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 4, BA 4.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s.

### `cand` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | -0.637 | -0.691..-0.611 | -0.757..-0.558 | -0.757..-0.558 (99.2%) | 0.064 | 0+/8- p=0.00781 | -20.33% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -0.660 s (n=4), first -0.627 s (n=4); cost of running second -0.017 s.
Paired differences (s): -0.598, -0.638, -0.684, -0.615, -0.635, -0.714, -0.757, -0.558

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
