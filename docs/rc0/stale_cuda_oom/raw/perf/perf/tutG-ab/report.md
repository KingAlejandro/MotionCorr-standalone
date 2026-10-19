# MotionCorr compare: main vs fix

## Provenance

- kit: `78aae2d3e79298913c904f0616a27432119d3988`
- arm `main`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr` sha256 `c2263c22611dc72b`; source `71ab841e69869b615555bb02f8f393db59c22d73` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `fix`: `/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr` sha256 `29b894f0643f1b8f`; source `78aae2d3e79298913c904f0616a27432119d3988` (git in /mnt/clathrin/alex-motioncorr-rc0/W-D11/src-fix); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 88-95, load1 7.1, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 10 run, 8 clean, target 8 clean, at most 12
- input: `movies.star` in `/home/alex/motioncorr-validation-20261011-vm/tutorial-data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `tools/profiling/mcprof.py compare --cpus 88-95 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --pairs 8 --max-rounds 12 --warmup 1 main=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-main-nvcomp/motioncorr fix=/mnt/clathrin/alex-motioncorr-rc0/W-D11/build-fix-nvcomp/motioncorr --data /home/alex/motioncorr-validation-20261011-vm/tutorial-data --work /mnt/clathrin/alex-motioncorr-rc0/W-D11/perf/tutG-ab -- --use_own --dose_weighting --dose_per_frame 1.277 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 8 | 4.591 | 0.061 | 4.512-4.774 | 8.677 | 363 | 125788 | 22 | 3260 | 3269 |
| fix | 8 | 4.638 | 0.082 | 4.561-4.692 | 8.724 | 363 | 125798 | 22 | 3260 | 3269 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 3.0-5.9, max foreign CPU on lane 0.16 cores, wall outlier rounds [2]
- `fix`: load1 2.8-5.5, max foreign CPU on lane 0.15 cores, wall outlier rounds none

Rounds: 10 planned, 8 retained, 2 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 2 (alone 2), `fix` 0 (alone 0). Kept orders: AB 4, BA 4.

WARNING: arm main alone triggered 2 of 2 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

Discarded rounds:
- round 4 (BA): main: foreign CPU on lane 0.48 cores
- round 7 (AB): main: foreign CPU on lane 0.27 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s.

### `fix` vs `main`: **not resolved (below noise 0.132 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 8 | +0.026 | -0.025..+0.099 | -0.101..+0.163 | -0.101..+0.163 (99.2%) | 0.111 | 5+/3- p=0.727 | +0.57% |

Reason: CI of median includes 0. Positive differences mean `fix` is slower.
Positional: median B-A when `fix` ran second -0.005 s (n=4), first +0.076 s (n=4); cost of running second -0.041 s.
Paired differences (s): -0.014, -0.101, +0.003, +0.097, +0.104, +0.163, -0.059, +0.049

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fix | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.
