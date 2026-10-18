# MotionCorr compare: main vs fix

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `main`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr` sha256 `29b894f0643f1b8f`; source `78aae2d3e79298913c904f0616a27432119d3988` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-fix); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 2.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 8 run, 8 clean, target 8 clean, at most 12
- input: `movies.star` in `/home/alex/motioncorr-validation-20261011-vm/tutorial-data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --patch_x 5 --patch_y 5`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 8 --max-rounds 12 --warmup 1 main=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr fix=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr --data /home/alex/motioncorr-validation-20261011-vm/tutorial-data --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf/tutL-ab -- --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --patch_x 5 --patch_y 5`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 5.378 | 0.092 | 5.341-5.531 | 9.613 | 368 | 126000 | 20 | 3362 | 3371 |
| fix | 8 | 5.393 | 0.066 | 5.338-5.456 | 9.634 | 368 | 126036 | 19 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 2.4-3.7, max foreign CPU on lane 0.00 cores, wall outlier rounds [4, 8]
- `fix`: load1 2.6-3.8, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 8 planned, 8 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 0 (alone 0). Kept orders: AB 4, BA 4.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s.

### `fix` vs `main`: **not resolved (below noise 0.109 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | -0.028 | -0.069..+0.038 | -0.117..+0.101 | -0.117..+0.101 (99.2%) | 0.078 | 3+/5- p=0.727 | -0.52% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.045 s (n=4), first -0.071 s (n=4); cost of running second +0.058 s.
Paired differences (s): -0.014, -0.042, +0.031, -0.067, +0.059, -0.074, +0.101, -0.117

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
