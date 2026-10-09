# MotionCorr compare: main vs cand

## Provenance

- kit: `629fdc4f5ddecb88c4e62b0b4a18f26ee82b84ea`
- arm `main`: `/home/alex/mc-vram1-main/build/motioncorr` sha256 `46cc8482f6f2b3d6`; source `1a99da0b9fee92278ba3c26c174ec2b2e84156d6` (git in /home/alex/mc-vram1-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-vram1/build/motioncorr` sha256 `36132ee9a4d26d16`; source `866c14f5cadb8db9b77dc53a088457d77ce9b90e` (git in /home/alex/mc-vram1); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 13.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 15 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `main` on, `cand` on
- CUDA device timing in trace passes: `main` off, `cand` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-vram1-kit/tools/profiling/mcprof.py compare main=/home/alex/mc-vram1-main/build/motioncorr cand=/home/alex/mc-vram1/build/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --source main=/home/alex/mc-vram1-main --source cand=/home/alex/mc-vram1 --work /home/alex/mc-vram1-kit-default -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 7.273 | 0.325 | 7.037-8.137 | 18.057 | 368 | 150534 | 15 | 3558 | 3567 |
| cand | 12 | 6.999 | 0.417 | 6.694-8.081 | 18.172 | 368 | 139338 | 2 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 12.1-17.6, max foreign CPU on lane 0.19 cores, wall outlier rounds [11]
- `cand`: load1 11.8-17.4, max foreign CPU on lane 0.02 cores, wall outlier rounds [2, 4, 6]

Rounds: 15 planned, 12 retained, 3 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 3 (alone 3), `cand` 0 (alone 0). Kept orders: AB 6, BA 6.

WARNING: arm main alone triggered 3 of 3 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

Discarded rounds:
- round 5 (AB): main: foreign CPU on lane 0.31 cores
- round 12 (BA): main: foreign CPU on lane 0.36 cores
- round 13 (AB): main: foreign CPU on lane 0.37 cores

Lane wait before round: r1 1 s, r2 55 s, r3 1 s, r4 2 s, r5 1 s, r6 329 s, r7 2 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 45 s, r14 1 s, r15 1 s.

### `cand` vs `main`: **not resolved (below noise 0.641 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.242 | -0.536..+0.111 | -1.305..+0.833 | -0.562..+0.719 (96.1%) | 0.448 | 3+/9- p=0.146 | -3.33% |

Reason: CI of median includes 0. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -0.435 s (n=6), first +0.314 s (n=6); cost of running second -0.374 s.
Paired differences (s): -0.527, +0.833, -0.266, +0.719, +0.807, -0.562, -0.792, -0.343, -0.219, -1.305, -0.091, -0.186

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

Movie wall (steady median): 234.3 -> 226.4 ms (-7.95)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.54 | 1.38 | -0.16 | 0.71 | -0.17 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 67.55 | 71.13 | +3.59 | 37.71 | +3.81 | +7 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 19.08 | 18.92 | -0.16 | 4.18 | -0.32 | +0 |
| fix defects | 1.99 | 1.38 | -0.61 | 2.11 | -0.61 | +0 |
| release preprocessing | 0.25 | 0.27 | +0.02 | 0.50 | +0.02 | +0 |
| global fft | 21.92 | 21.90 | -0.02 | 0.50 | -0.01 | +0 |
| power spectrum | 0.05 | 0.05 | -0.01 | 0.50 | -0.01 | +0 |
| **global alignment** | 11.83 | 8.88 | -2.95 * | 2.33 | -2.94 * | +0 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 22.08 | 22.01 | -0.07 | 0.50 | -0.07 | +0 |
| **patch alignment** | 32.82 | 26.98 | -5.84 * | 1.71 | -5.79 * | +0 |
| fit polynomial | 1.66 | 1.64 | -0.02 | 0.50 | -0.04 | +0 |
| **release alignment** | 1.10 | 1.69 | +0.59 * | 0.54 | +0.58 | +0 |
| dose weighting | 45.96 | 44.61 | -1.35 | 6.73 | -1.35 | +0 |
| movie teardown | 4.91 | 3.85 | -1.06 | 2.41 | -1.01 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.01 | +0 |
