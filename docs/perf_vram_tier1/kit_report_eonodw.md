# MotionCorr compare: main vs cand

## Provenance

- kit: `629fdc4f5ddecb88c4e62b0b4a18f26ee82b84ea`
- arm `main`: `/home/alex/mc-vram1-main/build/motioncorr` sha256 `46cc8482f6f2b3d6`; source `1a99da0b9fee92278ba3c26c174ec2b2e84156d6` (git in /home/alex/mc-vram1-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-vram1/build/motioncorr` sha256 `36132ee9a4d26d16`; source `866c14f5cadb8db9b77dc53a088457d77ce9b90e` (git in /home/alex/mc-vram1); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 15.1, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 14 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `main` on, `cand` on
- CUDA device timing in trace passes: `main` off, `cand` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --save_noDW --even_odd_split`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-vram1-kit/tools/profiling/mcprof.py compare main=/home/alex/mc-vram1-main/build/motioncorr cand=/home/alex/mc-vram1/build/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --source main=/home/alex/mc-vram1-main --source cand=/home/alex/mc-vram1 --work /home/alex/mc-vram1-kit-eonodw -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --save_noDW --even_odd_split`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 10.565 | 0.572 | 9.935-12.794 | 25.708 | 585 | 314894 | 19 | 3558 | 3567 |
| cand | 12 | 10.541 | 1.209 | 9.854-11.688 | 25.610 | 585 | 314256 | 15 | 3374 | 3383 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 13.4-17.2, max foreign CPU on lane 0.14 cores, wall outlier rounds [4]
- `cand`: load1 13.5-17.4, max foreign CPU on lane 0.25 cores, wall outlier rounds none

Rounds: 14 planned, 12 retained, 2 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 2 (alone 0), `cand` 2 (alone 0). Kept orders: AB 6, BA 6.

Discarded rounds:
- round 2 (BA): cand: foreign CPU on lane 0.95 cores | main: foreign CPU on lane 1.01 cores
- round 3 (AB): main: foreign CPU on lane 0.31 cores | cand: foreign CPU on lane 0.27 cores

Lane wait before round: r1 1 s, r2 172 s, r3 13 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s, r14 1 s.

### `cand` vs `main`: **not resolved (below noise 0.814 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.252 | -0.568..+0.683 | -2.649..+1.657 | -0.599..+1.029 (96.1%) | 0.584 | 5+/7- p=0.774 | -2.38% |

Reason: CI of median includes 0. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -0.343 s (n=6), first +0.396 s (n=6); cost of running second -0.370 s.
Paired differences (s): +0.075, -2.649, -0.692, +1.593, +0.568, +1.029, -0.267, -0.237, -0.599, -0.558, -0.419, +1.657

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 153 | 96 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

Movie wall (steady median): 340.7 -> 345.8 ms (+5.02)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.44 | 1.53 | +0.09 | 0.50 | +0.09 | +0 |
| read gain | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| session and device ingest | 67.59 | 70.83 | +3.24 | 32.73 | +2.87 | +1 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 19.16 | 19.09 | -0.06 | 1.59 | -0.01 | +0 |
| fix defects | 1.86 | 1.68 | -0.18 | 1.29 | -0.19 | +0 |
| release preprocessing | 0.24 | 0.25 | +0.00 | 0.50 | +0.01 | +0 |
| global fft | 21.89 | 21.86 | -0.04 | 0.50 | -0.04 | +0 |
| power spectrum | 0.05 | 0.06 | +0.01 | 0.50 | +0.01 | +0 |
| **global alignment** | 11.53 | 9.13 | -2.40 * | 1.25 | -2.35 * | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| global ifft | 22.10 | 22.05 | -0.04 | 0.50 | -0.05 | +0 |
| **patch alignment** | 32.34 | 27.48 | -4.86 * | 3.39 | -4.93 * | +0 |
| fit polynomial | 1.65 | 1.69 | +0.03 | 0.50 | +0.03 | +0 |
| release alignment | 1.04 | 1.82 | +0.78 | 0.84 | +0.79 | +0 |
| unweighted sums | 110.00 | 120.65 | +10.65 | 47.68 | +0.03 | +0 |
| dose weighting | 44.91 | 45.17 | +0.26 | 2.85 | +0.26 | +0 |
| **movie teardown** | 4.43 | 3.54 | -0.89 * | 0.50 | -0.87 * | +0 |
| submit model and plot | 0.08 | 0.08 | +0.00 | 0.50 | +0.00 | +0 |
