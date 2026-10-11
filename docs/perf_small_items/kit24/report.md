# MotionCorr compare: main vs cand

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `cand`: `/home/alex/mc-small/build-cand/motioncorr` sha256 `711196168ce32414`; source `28a290d` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 18.6, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 4 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 20 run, 9 clean, target 12 clean, at most 20 (TARGET NOT REACHED)
- CUDA device timing in --profile passes: `main` on, `cand` on
- CUDA device timing in trace passes: `main` off, `cand` off
- input: `movies.star` in `/home/alex/mc-small/runs/kit24/input`, 24 movies, STAR sha256 `6d52c471e7ce4b5a`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py compare main=/home/alex/mc-small/build-main/motioncorr cand=/home/alex/mc-small/build-cand/motioncorr --data /home/alex/mc-small/data96 --star movies.star --work /home/alex/mc-small/runs/kit24 --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --source main=/home/alex/mc-small/src-main --source cand=/home/alex/mc-small/src-cand --commit main=7d64043 --commit cand=28a290d --settle-timeout 600 --pairs 12 --movies 24 --profile-pass 3 --trace-pass 2 --max-rounds 20 --lane-wait 300 --warmup 1 --lock-timeout 14400 -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 9 | 7.271 | 1.037 | 6.940-8.193 | 18.890 | 368 | 128341 | 18 | 3362 | 3371 |
| cand | 9 | 6.108 | 0.249 | 5.735-7.487 | 10.078 | 367 | 126988 | 14 | 3362 | 3371 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 14.9-21.5, max foreign CPU on lane 0.23 cores, wall outlier rounds none
- `cand`: load1 14.7-21.1, max foreign CPU on lane 0.24 cores, wall outlier rounds [20]

Rounds: 20 planned, 9 retained, 11 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 8 (alone 0), `cand` 11 (alone 3). Kept orders: AB 6, BA 3.

WARNING: arm cand alone triggered 3 of 11 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

WARNING: kept pairs are unbalanced by order (AB 6, BA 3): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 1 (AB): main: foreign CPU on lane 0.54 cores | cand: foreign CPU on lane 0.51 cores
- round 2 (BA): cand: foreign CPU on lane 0.68 cores
- round 5 (AB): cand: foreign CPU on lane 0.36 cores
- round 6 (BA): cand: foreign CPU on lane 3.05 cores | main: foreign CPU on lane 3.01 cores
- round 7 (AB): main: foreign CPU on lane 2.99 cores | cand: foreign CPU on lane 3.00 cores
- round 8 (BA): cand: foreign CPU on lane 0.67 cores | main: foreign CPU on lane 0.28 cores
- round 10 (BA): cand: foreign CPU on lane 0.74 cores | main: foreign CPU on lane 0.63 cores
- round 13 (AB): main: foreign CPU on lane 1.12 cores | cand: foreign CPU on lane 0.81 cores
- round 14 (BA): cand: foreign CPU on lane 1.55 cores | main: foreign CPU on lane 0.99 cores
- round 16 (BA): cand: foreign CPU on lane 0.65 cores
- round 18 (BA): cand: foreign CPU on lane 1.29 cores | main: foreign CPU on lane 1.03 cores

Lane wait before round: r1 15 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 301 s (timed out at 3.08 busy cores), r7 301 s (timed out at 3.01 busy cores), r8 266 s, r9 2 s, r10 1 s, r11 1 s, r12 2 s, r13 1 s, r14 300 s (timed out at 2.47 busy cores), r15 87 s, r16 1 s, r17 1 s, r18 1 s, r19 10 s, r20 1 s.

### `cand` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 9 | -1.173 | -1.609..-1.038 | -2.067..+0.155 | -2.019..-0.855 (96.1%) | 0.471 | 1+/8- p=0.0391 | -16.13% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `cand` is slower.
Positional: median B-A when `cand` ran second -1.407 s (n=6), first -1.038 s (n=3); cost of running second -0.185 s.
Paired differences (s): -1.205, -1.173, -1.171, -0.855, -1.038, -2.019, -2.067, -1.609, +0.155

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

Movie wall (steady median): 235.0 -> 179.2 ms (-55.78 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.71 | 1.49 | -0.23 | 0.94 | -0.22 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| **session and device ingest** | 73.41 | 40.81 | -32.60 * | 30.95 | -31.92 * | +16 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| **hot pixels** | 19.64 | 4.26 | -15.38 * | 2.84 | -15.32 * | +0 |
| fix defects | 1.53 | 1.14 | -0.39 | 1.32 | -0.39 | -1 |
| release preprocessing | 0.28 | 0.24 | -0.04 | 0.50 | -0.03 | +0 |
| global fft | 21.85 | 21.88 | +0.03 | 0.50 | +0.03 | +0 |
| power spectrum | 0.06 | 0.05 | -0.01 | 0.50 | -0.01 | +0 |
| global alignment | 9.24 | 9.11 | -0.13 | 1.83 | -0.13 | +0 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 22.02 | 22.22 | +0.20 | 0.50 | +0.20 | +0 |
| patch alignment | 27.65 | 28.01 | +0.36 | 2.67 | +0.37 | +0 |
| fit polynomial | 1.72 | 1.71 | -0.01 | 0.50 | -0.01 | +0 |
| release alignment | 1.83 | 1.85 | +0.02 | 0.69 | +0.05 | +0 |
| dose weighting | 44.77 | 44.87 | +0.11 | 2.87 | +0.09 | -0 |
| **movie teardown** | 4.39 | 0.15 | -4.24 * | 2.70 | -4.25 * | +0 |
| submit model and plot | 0.09 | 0.08 | -0.01 | 0.50 | -0.01 | +0 |

WARNING: `main` pass 1 met a discard condition (kept): foreign CPU on lane 0.39 cores.

WARNING: `cand` pass 3 met a discard condition (kept): foreign CPU on lane 0.35 cores.

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `main` 2, `cand` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `cand` vs `main`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | -0.09 | +0.00 | -0.09 | 14.44 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| setup | -0.04 | +0.00 | -0.04 | 1.83 | +0 | +0 | +0.0 | +0 |
| read gain | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **session and device ingest** | -43.47 | -8.15 * | -34.81 | 123.46 | +0 | -18 * | -0.0 * | -4 * |
| host read movie | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **hot pixels** | -14.60 * | +0.00 | -14.60 * | 14.16 | +0 | +0 | +0.0 | +0 |
| fix defects | +0.02 | +0.00 | +0.01 | 4.23 | +0 | +0 | +0.0 | +0 |
| release preprocessing | -0.05 | +0.00 | -0.05 | 1.17 | +0 | +0 | +0.0 | +0 |
| global fft | +0.11 | +0.08 | +0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| power spectrum | +0.02 | +0.00 | +0.02 | 0.52 | +0 | +0 | +0.0 | +0 |
| global alignment | +0.10 | +0.00 | +0.10 | 5.29 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| global ifft | +0.34 | +0.06 | +0.21 | 1.37 | +0 | +0 | +0.0 | +0 |
| patch alignment | +0.51 | +0.03 | +0.61 | 30.77 | +0 | +0 | +0.0 | +0 |
| fit polynomial | -0.02 | +0.00 | -0.02 | 1.05 | +0 | +0 | +0.0 | +0 |
| release alignment | +0.11 | +0.00 | +0.11 | 7.12 | +0 | +0 | +0.0 | +0 |
| dose weighting | +0.48 | +0.26 | +0.19 | 7.40 | +0 | +0 | +0.0 | +0 |
| **movie teardown** | -5.72 * | +0.00 | -5.72 * | 1.69 | +0 | -4 * | +0.0 | +0 |
| submit model and plot | +0.01 | +0.00 | +0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | -0.93 | +0.00 | -0.93 | 14.96 | +0 | +0 | +0.0 | +0 |
| **after last movie** | -21.38 | +0.00 | -21.38 | 1831.74 | +0 | +4 * | +0.0 | +0 |

Traced device allocation high-water per pass: base 3026, 3026 MiB, arm 3026, 3026 MiB.

## Device: `main` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8017.2 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3503.4 ms (43.7%); idle 4513.8 ms. Kernels 25206 (2987.3 ms summed), copies 3247 (530.2 ms, 35784.3 MiB). Overlap between kernels and copies 14.58 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.27 |
| setup | 1.45 | 0.00 | 0.00 | 0.00 | 0% | 1.45 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.61 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 101.30 |
| session and device ingest | 82.84 | 39.34 | 28.88 | 11.16 | 47% | 43.36 | 59 | 12 | 27 | 0.84 | 5/0 | 130.7 | 18 | 2932 | 363.55 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.42 |
| hot pixels | 20.19 | 0.32 | 0.31 | 0.01 | 2% | 19.86 | 12 | 6 | 10 | 1.32 | 6/6 | 0.0 | 4 | 2933 | 142.22 |
| fix defects | 2.27 | 0.02 | 0.01 | 0.01 | 1% | 2.25 | 10 | 2 | 9 | 0.62 | 3/3 | 0.0 | 7 | 2932 | 3.88 |
| release preprocessing | 0.37 | 0.00 | 0.00 | 0.00 | 0% | 0.37 | 1 | 0 | 2 | 0.29 | 0/1 | 0.0 | 0 | 2932 | 0.33 |
| global fft | 22.00 | 21.58 | 21.58 | 0.00 | 98% | 0.41 | 170 | 169 | 1 | 0.14 | 0/0 | 0.0 | 0 | 2877 | 22.25 |
| power spectrum | 0.11 | 0.00 | 0.00 | 0.00 | 0% | 0.11 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.11 |
| global alignment | 11.12 | 7.13 | 7.11 | 0.02 | 64% | 4.00 | 34 | 19 | 15 | 0.66 | 0/0 | 0.0 | 14 | 2877 | 8.65 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.23 | 21.79 | 20.04 | 1.75 | 98% | 0.42 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.50 |
| patch alignment | 45.32 | 19.95 | 19.90 | 0.05 | 44% | 25.37 | 497 | 456 | 51 | 2.32 | 17/3 | 0.0 | 38 | 3026 | 46.14 |
| fit polynomial | 1.75 | 0.00 | 0.00 | 0.00 | 0% | 1.75 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.86 |
| release alignment | 3.63 | 0.00 | 0.00 | 0.00 | 0% | 3.63 | 1 | 0 | 15 | 2.30 | 0/14 | 0.0 | 0 | 3026 | 3.32 |
| dose weighting | 41.91 | 34.43 | 27.03 | 7.47 | 82% | 7.41 | 221 | 217 | 4 | 0.53 | 0/0 | 54.3 | 2 | 2877 | 90.73 |
| movie teardown | 6.02 | 0.00 | 0.00 | 0.00 | 0% | 6.02 | 1 | 0 | 5 | 3.39 | 0/4 | 0.0 | 0 | 2877 | 6.35 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.29 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.90 | 0.00 | 4.90 | 0 | 0/0 |
| between movies | 5.48 | 0.00 | 5.48 | 0 | 0/0 |
| after last movie | 1020.28 | 0.00 | 1020.28 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1023.45 | 176.9 | 239.5 | 34.3% |
| inflate_kernel | 96 | 585.59 | 6099.9 | 6212.4 | 19.6% |
| regular_fft_factor | 5784 | 432.78 | 74.8 | 85.1 | 14.5% |
| regular_bluestein_fft | 600 | 186.11 | 310.2 | 317.7 | 6.2% |
| fourierShiftKernel | 1277 | 130.34 | 102.1 | 1773.5 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.44 | 176.1 | 184.7 | 3.4% |
| postprocess_kernel | 1176 | 79.21 | 67.4 | 74.5 | 2.7% |
| preprocess_kernel | 1152 | 74.45 | 64.6 | 66.8 | 2.5% |
| cropAndGroupPatchResidentKernel | 600 | 62.33 | 103.9 | 105.6 | 2.1% |
| applyDoseWeightKernel | 576 | 60.28 | 104.7 | 107.2 | 2.0% |
| adler32StripsKernel | 96 | 55.00 | 572.9 | 582.0 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.41 | 525.1 | 557.2 | 1.7% |
| scaleComplexKernel | 24 | 40.03 | 1667.8 | 1671.0 | 1.3% |
| regular_fft | 1301 | 27.10 | 20.8 | 235.6 | 0.9% |
| regular_fft_c2r | 1277 | 23.01 | 18.0 | 182.7 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 928.28 | 100.05 |
| device sync | 216 | 640.56 | 17.54 |
| event sync | 384 | 265.83 | 15.52 |
| free (implicit sync) | 748 | 225.77 | 225.77 |
| stream sync | 120 | 20.54 | 6.30 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.09 | 779.84 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 258.43 | 12.49 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 216.69 | 6.31 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 10.21 | 6.73 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.76 | 12.81 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `cand` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 6569.9 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3309.4 ms (50.4%); idle 3260.4 ms. Kernels 25206 (2995.0 ms summed), copies 2833 (435.0 ms, 35784.3 MiB). Overlap between kernels and copies 121.41 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.27 |
| setup | 1.46 | 0.00 | 0.00 | 0.00 | 0% | 1.46 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 1.93 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 98.89 |
| session and device ingest | 43.62 | 31.21 | 29.02 | 7.74 | 72% | 12.50 | 29 | 12 | 9 | 0.23 | 1/0 | 130.7 | 0 | 2932 | 427.49 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 5.29 | 0.32 | 0.31 | 0.01 | 6% | 4.97 | 12 | 6 | 10 | 1.34 | 6/6 | 0.0 | 4 | 2933 | 73.44 |
| fix defects | 2.29 | 0.02 | 0.01 | 0.01 | 1% | 2.26 | 10 | 2 | 9 | 0.72 | 3/3 | 0.0 | 7 | 2932 | 4.24 |
| release preprocessing | 0.36 | 0.00 | 0.00 | 0.00 | 0% | 0.36 | 1 | 0 | 2 | 0.30 | 0/1 | 0.0 | 0 | 2932 | 0.38 |
| global fft | 22.14 | 21.70 | 21.70 | 0.00 | 98% | 0.42 | 170 | 169 | 1 | 0.16 | 0/0 | 0.0 | 0 | 2877 | 22.15 |
| power spectrum | 0.12 | 0.00 | 0.00 | 0.00 | 0% | 0.12 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.12 |
| global alignment | 11.12 | 7.14 | 7.12 | 0.02 | 64% | 3.99 | 34 | 19 | 15 | 0.65 | 0/0 | 0.0 | 14 | 2877 | 9.40 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.03 |
| global ifft | 22.65 | 21.90 | 20.11 | 1.75 | 97% | 0.65 | 193 | 168 | 25 | 0.38 | 0/0 | 1304.3 | 0 | 2877 | 22.22 |
| patch alignment | 44.95 | 19.97 | 19.92 | 0.05 | 44% | 25.14 | 497 | 456 | 51 | 2.34 | 17/3 | 0.0 | 38 | 3026 | 46.83 |
| fit polynomial | 1.69 | 0.00 | 0.00 | 0.00 | 0% | 1.69 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.74 |
| release alignment | 3.56 | 0.00 | 0.00 | 0.00 | 0% | 3.56 | 1 | 0 | 15 | 2.20 | 0/14 | 0.0 | 0 | 3026 | 3.39 |
| dose weighting | 42.06 | 34.53 | 27.04 | 7.39 | 82% | 7.54 | 221 | 217 | 4 | 0.46 | 0/0 | 54.3 | 2 | 2877 | 71.88 |
| movie teardown | 0.26 | 0.00 | 0.00 | 0.00 | 0% | 0.26 | 1 | 0 | 1 | 0.04 | 0/0 | 0.0 | 0 | 2877 | 0.31 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.13 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.10 | 0.00 | 5.10 | 0 | 0/0 |
| between movies | 4.48 | 0.00 | 4.48 | 0 | 0/0 |
| after last movie | 928.72 | 0.00 | 928.72 | 0 | 0/7 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1027.39 | 177.6 | 239.7 | 34.3% |
| inflate_kernel | 96 | 589.18 | 6137.3 | 6303.6 | 19.7% |
| regular_fft_factor | 5784 | 432.79 | 74.8 | 84.5 | 14.5% |
| regular_bluestein_fft | 600 | 186.59 | 311.0 | 321.8 | 6.2% |
| fourierShiftKernel | 1277 | 130.42 | 102.1 | 1771.8 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.42 | 176.1 | 182.6 | 3.4% |
| postprocess_kernel | 1176 | 79.23 | 67.4 | 74.0 | 2.6% |
| preprocess_kernel | 1152 | 74.98 | 65.1 | 67.1 | 2.5% |
| cropAndGroupPatchResidentKernel | 600 | 62.47 | 104.1 | 106.6 | 2.1% |
| applyDoseWeightKernel | 576 | 60.31 | 104.7 | 107.3 | 2.0% |
| adler32StripsKernel | 96 | 54.00 | 562.5 | 575.5 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 49.87 | 519.5 | 549.4 | 1.7% |
| scaleComplexKernel | 24 | 40.02 | 1667.5 | 1671.9 | 1.3% |
| regular_fft | 1301 | 27.26 | 20.9 | 236.8 | 0.9% |
| regular_fft_c2r | 1277 | 23.12 | 18.1 | 184.9 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2065 | 939.90 | 90.33 |
| device sync | 216 | 617.88 | 19.98 |
| event sync | 384 | 361.65 | 11.84 |
| free (implicit sync) | 656 | 141.15 | 141.15 |
| stream sync | 120 | 26.28 | 9.48 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.91 | 765.04 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 183.05 | 17.63 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 195.71 | 6.99 |
| Host-to-Device Pageable->Device | 959 | 65.6 | 10.74 | 6.40 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.60 | 13.60 |

Byte counts are invariant across captures; rates are not (contention, tracing).
