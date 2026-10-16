# MotionCorr compare: main vs cand

## Provenance

- kit: `None`
- arm `main`: `/dev/shm/192/build-main/motioncorr` sha256 `0655b1e86b6f5a47`; source `None` (unknown: /dev/shm/192/main-src is not a git checkout and has no SOURCE_COMMIT); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/dev/shm/192/build-cand/motioncorr` sha256 `8345cbb9c49fa81d`; source `None` (unknown: /dev/shm/192/cand-src is not a git checkout and has no SOURCE_COMMIT); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 5.5, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 490 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.1}
- rounds: 10 run, 10 clean, target 10 clean, at most 10
- CUDA device timing in --profile passes: `main` on, `cand` on
- input: `movies.star` in `/dev/shm/192/data/e10641`, 2 movies, STAR sha256 `3513be533d779b68`
- payload options: `--use_own --dose_weighting --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --dose_per_frame 1.0 --expected_frames 70 --gainref gain.mrc --gpu 0 --j 8`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID OMP_NUM_THREADS=8`
- command: `cand-src/tools/profiling/mcprof.py compare main=build-main/motioncorr cand=build-cand/motioncorr --data /dev/shm/192/data/e10641 --star movies.star --work /dev/shm/192/out/time10641 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --pairs 10 --warmup 1 --profile-pass 3 --env OMP_NUM_THREADS=8 -- --use_own --dose_weighting --bfactor 150 --seed 1 --patch_x 5 --patch_y 5 --dose_per_frame 1.0 --expected_frames 70 --gainref gain.mrc --gpu 0 --j 8`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 10 | 29.212 | 0.093 | 29.134-29.486 | 39.190 | 7163 | 7050038 | 19 | 15034 | 15043 |
| cand | 10 | 7.424 | 0.086 | 7.326-7.471 | 17.200 | 2121 | 1086394 | 25 | 14582 | 14591 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 1.7-4.0, max foreign CPU on lane 0.02 cores, wall outlier rounds none
- `cand`: load1 1.6-3.3, max foreign CPU on lane 0.07 cores, wall outlier rounds none

Rounds: 10 planned, 10 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 0 (alone 0), `cand` 0 (alone 0). Kept orders: AB 5, BA 5.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s.

### `cand` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 10 | -21.843 | -21.940..-21.738 | -22.054..-21.667 | -21.985..-21.683 (97.9%) | 0.154 | 0+/10- p=0.00195 | -74.78% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -21.855 s (n=5), first -21.832 s (n=5); cost of running second -0.012 s.
Paired differences (s): -21.855, -21.985, -22.054, -21.832, -21.749, -21.936, -21.734, -21.683, -21.941, -21.667

## Product identity

Instrument: lib/identity.py: complete MRC header + extended header + payload, writer clock masked, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 12 | 2 | 6 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates). All MRC header/label and extended-header bytes are compared; only the known first-label Relion writer timestamp is masked.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

Movie wall (steady median): 12459.7 -> 2786.7 ms (-9672.99 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 2.40 | 2.41 | +0.01 | 0.50 | +0.01 | -3 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 3.28 | 1.49 | -1.79 | 13.26 | -1.73 | -2 |
| host read movie | 703.79 | 744.60 | +40.82 | 189.06 | +14.18 | -19 |
| allocate host sum | 0.02 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 165.08 | 164.77 | -0.31 | 7.28 | -0.25 | -1 |
| hot pixels | 20.40 | 13.08 | -7.32 | 8.46 | -7.28 | -4757 |
| **fix defects** | 2.84 | 2.91 | +0.08 | 0.89 | +0.08 | -136 * |
| release preprocessing | 0.26 | 0.30 | +0.05 | 0.50 | +0.05 | +0 |
| global fft | 241.18 | 241.79 | +0.61 | 11.92 | +0.75 | +2 |
| power spectrum | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| global alignment | 43.28 | 43.44 | +0.16 | 1.53 | +0.16 | -14 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 53.60 | 53.59 | -0.02 | 0.50 | -0.02 | +0 |
| **patch alignment** | 10413.84 | 1406.13 | -9007.71 * | 242.77 | -9003.81 * | -2652107 * |
| fit polynomial | 1.57 | 1.62 | +0.05 | 0.50 | +0.04 | -6 |
| release alignment | 2.55 | 2.51 | -0.04 | 0.51 | -0.04 | -12 |
| dose weighting | 124.39 | 107.68 | -16.71 | 78.08 | -16.77 | -15354 |
| **movie teardown** | 680.99 | 0.19 | -680.79 * | 56.92 | -680.27 * | -51 |
| submit model and plot | 0.13 | 0.08 | -0.06 | 0.50 | -0.05 | -1 |
