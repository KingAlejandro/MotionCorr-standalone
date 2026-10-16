# MotionCorr compare: main vs cand

## Provenance

- kit: `None`
- arm `main`: `/dev/shm/194/build-main/motioncorr` sha256 `59a08840a721d175`; source `4b849165` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/194/build-cand/motioncorr` sha256 `dc33396f20a15f1f`; source `a414ec25` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 2.9, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 2 run, 2 clean, target 2 clean, at most 2
- input: `movies.star` in `/dev/shm/194/run12963`, 1 movies, STAR sha256 `2b244e8bf6b81801`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.282051282051282 --bfactor 150 --seed 1 --expected_frames 39 --patch_x 5 --patch_y 5 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --gpu 0 --j 8 --ingest_witness /dev/shm/194/witness-12963.txt`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `src-cand/tools/profiling/mcprof.py compare main=build-main/motioncorr cand=build-cand/motioncorr --data run12963 --work work12963 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 2 --source main=/dev/shm/194/src-main --source cand=/dev/shm/194/src-cand --commit main=4b849165 --commit cand=a414ec25 -- --use_own --dose_weighting --dose_per_frame 1.282051282051282 --bfactor 150 --seed 1 --expected_frames 39 --patch_x 5 --patch_y 5 --gainref gain.gain --eer_grouping 49 --eer_upsampling 1 --gpu 0 --j 8 --ingest_witness /dev/shm/194/witness-12963.txt`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 2 | 4.630 | 0.034 | 4.596-4.664 | 17.313 | 2357 | 737508 | 0 | 6116 | 6125 |
| cand | 2 | 4.592 | 0.031 | 4.561-4.623 | 17.232 | 2359 | 730118 | 0 | 6116 | 6125 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 2.6-3.3, max foreign CPU on lane 0.01 cores, wall outlier rounds none
- `cand`: load1 3.1-3.5, max foreign CPU on lane 0.01 cores, wall outlier rounds none

Rounds: 2 planned, 2 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 1, BA 1.

Lane wait before round: r1 1 s, r2 1 s.

### `cand` vs `main`: **not resolved (2 retained pairs, 6 needed)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 2 | -0.038 | -0.040..-0.037 | -0.041..-0.035 | n/a | 0.004 | 0+/2- p=0.5 | -0.82% |

Reason: fewer than 6 retained pairs (2): no verdict and no resolution. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -0.035 s (n=1), first -0.041 s (n=1); cost of running second +0.003 s.
Paired differences (s): -0.035, -0.041

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 9 | 1 | 5 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
