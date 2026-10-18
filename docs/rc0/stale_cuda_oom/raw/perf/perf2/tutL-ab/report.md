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
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 21 run, 20 clean, target 20 clean, at most 26
- input: `movies.star` in `/home/alex/motioncorr-validation-20261011-vm/tutorial-data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --patch_x 5 --patch_y 5`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 20 --max-rounds 26 --warmup 1 main=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr fix=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr --data /home/alex/motioncorr-validation-20261011-vm/tutorial-data --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf2/tutL-ab -- --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --patch_x 5 --patch_y 5`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 20 | 5.411 | 0.099 | 5.335-5.555 | 9.679 | 368 | 125990 | 25 | 3362 | 3371 |
| fix | 20 | 5.425 | 0.068 | 5.336-5.536 | 9.690 | 368 | 125980 | 20 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 2.4-3.2, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `fix`: load1 2.3-3.0, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 21 planned, 20 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `fix` 1 (alone 1). Kept orders: AB 11, BA 9.

WARNING: kept pairs are unbalanced by order (AB 11, BA 9): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 16 (BA): fix: foreign CPU on lane 0.36 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 3 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s, r21 1 s.

### `fix` vs `main`: **not resolved (below noise 0.068 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 20 | +0.004 | -0.046..+0.030 | -0.151..+0.137 | -0.045..+0.024 (95.9%) | 0.068 | 11+/9- p=0.824 | +0.07% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second +0.010 s (n=11), first -0.027 s (n=9); cost of running second +0.018 s.
Paired differences (s): +0.006, +0.047, +0.122, -0.075, -0.045, +0.101, +0.094, -0.039, -0.048, -0.027, +0.137, -0.101, -0.011, +0.003, +0.024, +0.020, -0.151, -0.121, +0.005, +0.010

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
