# MotionCorr run: A

## Provenance

- kit: `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`
- arm `A`: `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr` sha256 `34e768128b83f7c9`; source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-101, load1 1.7, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 2 run, 2 clean, target 2 clean, at most 2
- input: `input.star` in `/mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01`, 1 movies, STAR sha256 `ba3a39e59ca796b5`
- payload options: `--use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/ingest-witness.txt --gpu 0`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools/profiling/mcprof.py run A=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr --work /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/kit-run2 --data /mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01 --star input.star --cpus 96-101 --runner-cpus 102-103 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --no-lock --commit A=e77a51a220cb0d91f4ac3c7fac211876d0c6833f --rounds 2 --warmup 0 --keep-outputs -- --use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/ingest-witness.txt --gpu 0`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 2 | 2.719 | 0.019 | 2.700-2.738 | 7.592 | 2911 | 1379079 | 0 | 6094 | 6103 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `A`: load1 1.7-1.7, max foreign CPU on lane 0.01 cores, wall outlier rounds none

Rounds: 2 planned, 2 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `A` 0 (alone 0).

Lane wait before round: r1 1 s, r2 1 s.
