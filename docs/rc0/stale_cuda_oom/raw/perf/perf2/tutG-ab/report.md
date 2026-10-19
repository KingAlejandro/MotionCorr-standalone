# MotionCorr compare: main vs fix

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `main`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr` sha256 `29b894f0643f1b8f`; source `78aae2d3e79298913c904f0616a27432119d3988` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-fix); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 3.0, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 20 run, 20 clean, target 20 clean, at most 26
- input: `movies.star` in `/home/alex/motioncorr-validation-20261011-vm/tutorial-data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 20 --max-rounds 26 --warmup 1 main=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr fix=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr --data /home/alex/motioncorr-validation-20261011-vm/tutorial-data --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf2/tutG-ab -- --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 20 | 4.563 | 0.058 | 4.508-4.735 | 8.676 | 363 | 125726 | 17 | 3260 | 3269 |
| fix | 20 | 4.576 | 0.155 | 4.483-4.760 | 8.675 | 363 | 125790 | 18 | 3260 | 3269 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 2.5-3.2, max foreign CPU on lane 0.20 cores, wall outlier rounds [3, 17]
- `fix`: load1 2.4-3.2, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 20 planned, 20 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 10, BA 10.

Lane wait before round: r1 1 s, r2 1 s, r3 3 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s.

### `fix` vs `main`: **not resolved (below noise 0.114 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 20 | +0.021 | -0.036..+0.102 | -0.184..+0.206 | -0.029..+0.101 (95.9%) | 0.114 | 11+/9- p=0.824 | +0.46% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second -0.038 s (n=10), first +0.087 s (n=10); cost of running second -0.062 s.
Paired differences (s): +0.042, +0.033, -0.173, +0.101, +0.168, -0.005, -0.184, +0.073, -0.021, +0.149, -0.055, +0.206, +0.009, +0.108, -0.131, -0.029, -0.005, +0.041, -0.056, +0.118

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
