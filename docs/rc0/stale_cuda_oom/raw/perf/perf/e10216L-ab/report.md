# MotionCorr compare: main vs fix

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `main`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr` sha256 `29b894f0643f1b8f`; source `78aae2d3e79298913c904f0616a27432119d3988` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-fix); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 11.6, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 9 run, 8 clean, target 8 clean, at most 12
- input: `movies.star` in `/mnt/clathrin/alex-motioncorr-rc0/W-D11/perf-e10216`, 3 movies, STAR sha256 `a82e24f692e4133e`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 8 --max-rounds 12 --warmup 1 main=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr fix=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr --data /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf-e10216 --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf/e10216L-ab -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 6.569 | 0.070 | 6.338-6.722 | 19.847 | 2344 | 2880737 | 18 | 8904 | 8913 |
| fix | 8 | 6.665 | 0.137 | 6.387-6.859 | 20.304 | 2357 | 2902270 | 21 | 8904 | 8913 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 5.6-9.7, max foreign CPU on lane 0.02 cores, wall outlier rounds [5]
- `fix`: load1 5.8-9.3, max foreign CPU on lane 0.12 cores, wall outlier rounds none

Rounds: 9 planned, 8 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 1 (alone 0), `fix` 1 (alone 0). Kept orders: AB 5, BA 3.

WARNING: kept pairs are unbalanced by order (AB 5, BA 3): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 6 (BA): fix: unclassified GPU pids [607727] | main: unclassified GPU pids [607774]

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 3 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s.

### `fix` vs `main`: **not resolved (below noise 0.240 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | +0.094 | -0.053..+0.209 | -0.186..+0.293 | -0.186..+0.293 (99.2%) | 0.204 | 5+/3- p=0.727 | +1.42% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.032 s (n=5), first +0.204 s (n=3); cost of running second -0.086 s.
Paired differences (s): -0.062, -0.050, +0.032, +0.293, +0.225, +0.155, +0.204, -0.186

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 15 | 3 | 7 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
