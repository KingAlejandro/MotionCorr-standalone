# MotionCorr compare: mainA vs mainB

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `mainA`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `mainB`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 2.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 20 run, 20 clean, target 20 clean, at most 26
- input: `movies.star` in `/home/alex/motioncorr-validation-20261011-vm/tutorial-data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 20 --max-rounds 26 --warmup 1 mainA=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr mainB=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr --data /home/alex/motioncorr-validation-20261011-vm/tutorial-data --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf2/tutG-null -- --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| mainA | 20 | 4.568 | 0.052 | 4.502-4.738 | 8.696 | 363 | 125730 | 21 | 3260 | 3269 |
| mainB | 20 | 4.578 | 0.077 | 4.505-4.803 | 8.653 | 363 | 125724 | 21 | 3260 | 3269 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `mainA`: load1 2.4-3.4, max foreign CPU on lane 0.00 cores, wall outlier rounds [1, 6, 10]
- `mainB`: load1 2.4-3.4, max foreign CPU on lane 0.15 cores, wall outlier rounds [11]

Rounds: 20 planned, 20 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `mainA` 0 (alone 0), `mainB` 0 (alone 0). Kept orders: AB 10, BA 10.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 2 s, r13 1 s, r14 4 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 3 s, r20 1 s.

### `mainB` vs `mainA`: **not resolved (below noise 0.076 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 20 | +0.019 | -0.037..+0.067 | -0.203..+0.238 | -0.028..+0.064 (95.9%) | 0.076 | 12+/8- p=0.503 | +0.41% |

Reason: CI of median includes 0. Positive differences mean `mainB` is slower.
Positional: median B-A when `mainB` ran second -0.010 s (n=10), first +0.039 s (n=10); cost of running second -0.024 s.
Paired differences (s): -0.203, +0.037, +0.008, -0.066, -0.028, -0.134, +0.076, +0.102, -0.116, -0.128, +0.238, +0.035, +0.000, +0.111, -0.020, +0.064, +0.030, +0.079, -0.020, +0.041

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| mainB | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
