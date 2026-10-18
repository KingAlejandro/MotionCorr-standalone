# MotionCorr compare: mainA vs mainB

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `mainA`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `mainB`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 4.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 20 run, 20 clean, target 20 clean, at most 26
- input: `movies.star` in `/mnt/clathrin/alex-motioncorr-rc0/W-D11/perf-e10216`, 3 movies, STAR sha256 `a82e24f692e4133e`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 20 --max-rounds 26 --warmup 1 mainA=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr mainB=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr --data /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf-e10216 --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf2/e10216L-null -- --use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --gpu 0 --j 8 --patch_x 5 --patch_y 5 --ingest compact`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| mainA | 20 | 6.786 | 0.099 | 6.663-6.948 | 21.003 | 2349 | 2921268 | 21 | 8904 | 8913 |
| mainB | 20 | 6.830 | 0.083 | 6.672-6.960 | 21.207 | 2344 | 2916976 | 22 | 8904 | 8913 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `mainA`: load1 3.5-4.9, max foreign CPU on lane 0.00 cores, wall outlier rounds none
- `mainB`: load1 3.4-4.6, max foreign CPU on lane 0.00 cores, wall outlier rounds none

Rounds: 20 planned, 20 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `mainA` 0 (alone 0), `mainB` 0 (alone 0). Kept orders: AB 10, BA 10.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 1 s, r17 1 s, r18 1 s, r19 1 s, r20 1 s.

### `mainB` vs `mainA`: **not resolved (below noise 0.069 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 20 | +0.042 | -0.009..+0.071 | -0.187..+0.196 | -0.006..+0.065 (95.9%) | 0.069 | 13+/7- p=0.263 | +0.62% |

Reason: CI of median includes 0. Positive differences mean `mainB` is slower.
Positional: median B-A when `mainB` ran second +0.003 s (n=10), first +0.061 s (n=10); cost of running second -0.029 s.
Paired differences (s): -0.187, +0.065, -0.001, +0.157, -0.114, -0.006, +0.032, +0.039, +0.007, +0.155, +0.059, +0.196, -0.040, -0.017, +0.052, +0.146, -0.023, +0.045, +0.086, +0.056

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| mainB | PASS | 15 | 3 | 7 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
