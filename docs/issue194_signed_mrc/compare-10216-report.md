# MotionCorr compare: main vs cand

## Provenance

- kit: `None`
- arm `main`: `/dev/shm/194/build-main/motioncorr` sha256 `59a08840a721d175`; source `4b849165` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/194/build-cand/motioncorr` sha256 `dc33396f20a15f1f`; source `a414ec25` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 2.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 8 run, 8 clean, target 8 clean, at most 8
- input: `movies.star` in `/dev/shm/194/run10216`, 2 movies, STAR sha256 `d5b7e12c2e7b5a6a`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --gpu 0 --j 8 --expected_frames 59 --ingest_witness /dev/shm/194/witness-10216.txt`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare main=build-main/motioncorr cand=build-cand/motioncorr --data run10216 --work work10216 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 8 --source main=/dev/shm/194/src-main --source cand=/dev/shm/194/src-cand --commit main=4b849165 --commit cand=a414ec25 -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --gpu 0 --j 8 --expected_frames 59 --ingest_witness /dev/shm/194/witness-10216.txt`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 6.378 | 0.073 | 6.232-6.475 | 16.368 | 4180 | 3035316 | 0 | 8904 | 8913 |
| cand | 8 | 5.106 | 0.036 | 5.061-5.142 | 12.308 | 2325 | 1962486 | 0 | 8904 | 8913 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 2.9-4.1, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `cand`: load1 2.6-3.7, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 8 planned, 8 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 4, BA 4.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s.

### `cand` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | -1.281 | -1.328..-1.211 | -1.372..-1.110 | -1.372..-1.110 (99.2%) | 0.086 | 0+/8- p=0.00781 | -20.08% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -1.285 s (n=4), first -1.281 s (n=4); cost of running second -0.002 s.
Paired differences (s): -1.164, -1.110, -1.372, -1.282, -1.226, -1.323, -1.343, -1.280

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
