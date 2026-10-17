# MotionCorr compare: main vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/wu/b-t-main/motioncorr` sha256 `e19a63d2dbe11a7c`; source `116eb04a` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-small/wu/b-t-c2/motioncorr` sha256 `64b2fb452dcc3ed9`; source `c2fcb409` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 13.7, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 1543 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 12 run, 10 clean, target 12 clean, at most 12 (TARGET NOT REACHED)
- CUDA device timing in --profile passes: `main` on, `cand` on
- input: `movies.star` in `/home/alex/mc-small/wu/runs-kit24/input`, 24 movies, STAR sha256 `6d52c471e7ce4b5a`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --skip_report_pdf`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py compare main=/home/alex/mc-small/wu/b-t-main/motioncorr cand=/home/alex/mc-small/wu/b-t-c2/motioncorr --data /home/alex/mc-small/data96 --star movies.star --movies 24 --work /home/alex/mc-small/wu/runs-kit24 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --source main=/home/alex/mc-small/wu/src-main --source cand=/home/alex/mc-small/wu/src-c4 --commit main=116eb04a --commit cand=c2fcb409 --lock-timeout 28800 --settle-timeout 600 --pairs 12 --profile-pass 3 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp --skip_report_pdf`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 10 | 5.188 | 0.119 | 5.100-5.328 | 8.769 | 368 | 114113 | 0 | 3362 | 3371 |
| cand | 10 | 5.146 | 0.227 | 4.911-6.696 | 9.042 | 366 | 89402 | 0 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 13.4-14.5, max foreign CPU on lane 0.23 cores, wall outlier rounds none
- `cand`: load1 13.2-14.5, max foreign CPU on lane 0.25 cores, wall outlier rounds [1, 9]

Rounds: 12 planned, 10 retained, 2 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 2 (alone 2), `cand` 0 (alone 0). Kept orders: AB 4, BA 6.

WARNING: arm main alone triggered 2 of 2 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

WARNING: kept pairs are unbalanced by order (AB 4, BA 6): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 5 (AB): main: foreign CPU on lane 0.35 cores
- round 7 (AB): main: foreign CPU on lane 0.29 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 2 s, r5 3 s, r6 1 s, r7 1 s, r8 7 s, r9 1 s, r10 2 s, r11 1 s, r12 1 s.

### `cand` vs `main`: **not resolved (below noise 0.647 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 10 | -0.055 | -0.151..+0.101 | -0.190..+1.421 | -0.186..+1.109 (97.9%) | 0.174 | 5+/5- p=1 | -1.06% |

Reason: CI of median includes 0. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second +0.497 s (n=4), first -0.063 s (n=6); cost of running second +0.280 s.
Paired differences (s): +1.109, -0.131, -0.116, -0.186, +0.034, +0.123, +1.421, -0.158, -0.190, +0.006

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| cand | PASS | 73 | 24 | 24 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `cand` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

Movie wall (steady median): 179.0 -> 176.7 ms (-2.29)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.42 | 1.37 | -0.05 | 0.64 | -0.04 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 40.81 | 40.00 | -0.81 | 4.72 | -0.37 | -1 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 4.29 | 4.11 | -0.18 | 0.92 | -0.18 | +0 |
| fix defects | 1.12 | 1.03 | -0.08 | 0.50 | -0.09 | -0 |
| release preprocessing | 0.25 | 0.24 | -0.01 | 0.50 | -0.01 | +0 |
| global fft | 21.89 | 21.89 | +0.01 | 0.50 | +0.00 | +0 |
| power spectrum | 0.07 | 0.06 | -0.01 | 0.50 | -0.01 | +0 |
| global alignment | 9.15 | 8.96 | -0.19 | 1.15 | -0.18 | +0 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 22.18 | 22.17 | -0.01 | 0.50 | -0.01 | +0 |
| patch alignment | 28.07 | 27.24 | -0.83 | 5.74 | -0.82 | +0 |
| fit polynomial | 1.83 | 1.65 | -0.18 | 1.47 | -0.18 | +0 |
| release alignment | 1.97 | 1.80 | -0.17 | 1.62 | -0.17 | +0 |
| dose weighting | 45.15 | 45.04 | -0.12 | 3.04 | -0.11 | +1 |
| movie teardown | 0.16 | 0.15 | -0.01 | 0.50 | -0.01 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |
