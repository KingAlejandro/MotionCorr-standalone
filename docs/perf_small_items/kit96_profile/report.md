# MotionCorr compare: main vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-small/build-cand/motioncorr` sha256 `711196168ce32414`; source `28a290d` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 16.5, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 1330 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 5.4}
- rounds: 6 run, 2 clean, target 6 clean, at most 6 (TARGET NOT REACHED)
- CUDA device timing in --profile passes: `main` on, `cand` on
- input: `movies.star` in `/home/alex/mc-small/data96`, 96 movies, STAR sha256 `b906a827b28fc122`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py compare main=/home/alex/mc-small/build-main/motioncorr cand=/home/alex/mc-small/build-cand/motioncorr --data /home/alex/mc-small/data96 --star movies.star --work /home/alex/mc-small/runs/kit96 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --source main=/home/alex/mc-small/src-main --source cand=/home/alex/mc-small/src-cand --commit main=7d64043 --commit cand=28a290d --settle-timeout 600 --pairs 6 --profile-pass 3 --warmup 1 --lane-wait 120 --lock-timeout 14400 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 2 | 24.827 | 0.657 | 24.170-25.484 | 69.156 | 369 | 183972 | 0 | 3362 | 3371 |
| cand | 2 | 20.599 | 0.760 | 19.839-21.359 | 36.121 | 395 | 202370 | 17 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 14.7-15.9, max foreign CPU on lane 0.02 cores, wall outlier rounds none
- `cand`: load1 17.7-20.2, max foreign CPU on lane 0.19 cores, wall outlier rounds none

Rounds: 6 planned, 2 retained, 4 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 3 (alone 0), `cand` 4 (alone 1). Kept orders: AB 1, BA 1.

Discarded rounds:
- round 3 (AB): cand: foreign CPU on lane 0.53 cores
- round 4 (BA): cand: foreign CPU on lane 0.83 cores | main: foreign CPU on lane 1.01 cores
- round 5 (AB): main: foreign CPU on lane 1.32 cores | cand: foreign CPU on lane 1.45 cores
- round 6 (BA): cand: foreign CPU on lane 1.30 cores | main: foreign CPU on lane 0.36 cores

Lane wait before round: r1 1 s, r2 1 s, r3 12 s, r4 2 s, r5 120 s (timed out at 2.03 busy cores), r6 121 s (timed out at 1.15 busy cores).

### `cand` vs `main`: **not resolved (2 retained pairs, 6 needed)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 2 | -4.228 | -4.936..-3.520 | -5.645..-2.811 | n/a | 2.101 | 0+/2- p=0.5 | -17.03% |

Reason: fewer than 6 retained pairs (2): no verdict and no resolution. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -2.811 s (n=1), first -5.645 s (n=1); cost of running second +1.417 s.
Paired differences (s): -2.811, -5.645

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 297 | 96 | 100 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

Movie wall (steady median): 224.3 -> 179.5 ms (-44.74 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.51 | 1.55 | +0.05 | 0.73 | +0.05 | +0 |
| read gain | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| **session and device ingest** | 68.32 | 40.92 | -27.40 * | 10.17 | -25.04 * | +25 |
| host read movie | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| **hot pixels** | 19.20 | 4.32 | -14.88 * | 1.73 | -14.78 * | +0 |
| fix defects | 1.65 | 1.11 | -0.55 | 1.21 | -0.55 | -0 |
| release preprocessing | 0.25 | 0.26 | +0.01 | 0.50 | +0.01 | +0 |
| global fft | 21.91 | 21.90 | -0.01 | 0.50 | -0.01 | +0 |
| power spectrum | 0.05 | 0.06 | +0.01 | 0.50 | +0.01 | +0 |
| global alignment | 8.97 | 9.21 | +0.24 | 2.13 | +0.23 | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| global ifft | 22.01 | 22.26 | +0.25 | 0.50 | +0.25 | +0 |
| patch alignment | 27.04 | 28.25 | +1.20 | 7.02 | +1.20 | +0 |
| fit polynomial | 1.66 | 1.88 | +0.21 | 1.70 | +0.22 | +0 |
| release alignment | 1.69 | 2.03 | +0.34 | 2.46 | +0.33 | +0 |
| dose weighting | 44.91 | 45.14 | +0.23 | 2.88 | +0.23 | +0 |
| **movie teardown** | 3.88 | 0.16 | -3.72 * | 0.50 | -3.68 * | +0 |
| submit model and plot | 0.08 | 0.08 | +0.01 | 0.50 | +0.01 | +0 |

WARNING: `cand` pass 3 met a discard condition (kept): foreign CPU on lane 1.13 cores.
