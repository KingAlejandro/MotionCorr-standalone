# MotionCorr compare: noC vs rc

## Provenance

- kit: `d873993522986893eb2a7d6346828a53771d35ed`
- arm `noC`: `/home/alex/mc-rc/build-noC/motioncorr` sha256 `5f5b93294ae51d82`; source `e583cafeee539ce0ff7a533c840c88e7d141e42b` (git in /home/alex/mc-rc/src-noC); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `rc`: `/home/alex/mc-rc/build-rc/motioncorr` sha256 `ff1bc2679a040bc9`; source `c0f82c2d65bcfc6c68042313d22c1fe132c1a306` (git in /home/alex/mc-rc/src-rc); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 16.2, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 13 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `noC` on, `rc` on
- CUDA device timing in trace passes: `noC` off, `rc` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-rc/src-kit/tools/profiling/mcprof.py compare noC=/home/alex/mc-rc/build-noC/motioncorr rc=/home/alex/mc-rc/build-rc/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work /home/alex/mc-rc/camp/loo_noC --source noC=/home/alex/mc-rc/src-noC --source rc=/home/alex/mc-rc/src-rc -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| noC | 12 | 7.685 | 1.125 | 7.090-9.324 | 19.856 | 368 | 138690 | 14 | 3558 | 3567 |
| rc | 12 | 7.310 | 0.364 | 7.077-8.814 | 18.406 | 368 | 150421 | 13 | 3558 | 3567 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `noC`: load1 15.8-23.8, max foreign CPU on lane 0.11 cores, wall outlier rounds none
- `rc`: load1 15.7-24.4, max foreign CPU on lane 0.14 cores, wall outlier rounds [5, 11, 12]

Rounds: 13 planned, 12 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `noC` 0 (alone 0), `rc` 1 (alone 1). Kept orders: AB 6, BA 6.

Discarded rounds:
- round 9 (AB): rc: foreign CPU on lane 0.57 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s.

### `rc` vs `noC`: **not resolved (below noise 0.695 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.336 | -0.933..+0.036 | -2.025..+1.095 | -1.296..+0.094 (96.1%) | 0.672 | 4+/8- p=0.388 | -4.37% |

Reason: CI of median includes 0. Positive differences mean `rc` is slower.
Positional: median B-A when `rc` ran second -0.640 s (n=6), first -0.336 s (n=6); cost of running second -0.152 s.
Paired differences (s): +0.016, -0.418, -1.397, +0.094, +1.095, -0.050, -1.296, -0.254, -0.442, +0.439, -0.812, -2.025

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| rc | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `noC` 3, `rc` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noC`

Movie wall (steady median): 244.9 -> 233.3 ms (-11.60)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.55 | 1.43 | -0.12 | 0.80 | -0.12 | +0 |
| read gain | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| session and device ingest | 71.20 | 67.69 | -3.51 | 30.75 | -6.63 | +2 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 19.55 | 19.17 | -0.38 | 9.67 | -0.63 | +0 |
| fix defects | 1.72 | 1.93 | +0.20 | 1.47 | +0.22 | +0 |
| release preprocessing | 0.24 | 0.24 | +0.00 | 0.50 | +0.00 | +0 |
| global fft | 23.99 | 21.92 | -2.08 | 5.02 | -2.07 | +0 |
| power spectrum | 0.06 | 0.06 | -0.00 | 0.50 | -0.00 | +0 |
| global alignment | 11.98 | 11.77 | -0.21 | 2.77 | -0.17 | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| **global ifft** | 23.60 | 22.10 | -1.49 * | 0.50 | -1.49 * | +0 |
| patch alignment | 32.97 | 32.95 | -0.03 | 6.34 | -0.10 | +0 |
| fit polynomial | 1.76 | 1.69 | -0.08 | 0.69 | -0.04 | +0 |
| release alignment | 1.13 | 1.15 | +0.02 | 0.93 | +0.02 | +0 |
| dose weighting | 49.45 | 45.12 | -4.32 | 8.07 | -4.28 | +1 |
| movie teardown | 4.63 | 4.59 | -0.05 | 1.39 | -0.07 | +0 |
| submit model and plot | 0.08 | 0.08 | +0.00 | 0.50 | +0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `noC` 2, `rc` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noC`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | -0.49 | +0.00 | -0.49 | 3.88 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.02 | +0.00 | -0.02 | 0.50 | +0 | +0 | +0.0 | +0 |
| setup | -0.08 | +0.00 | -0.08 | 2.90 | +0 | +0 | +0.0 | +0 |
| read gain | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| session and device ingest | +1.31 | +0.42 | +1.16 | 149.62 | +0 | +0 | +0.0 | +0 |
| host read movie | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | +2.46 | -0.00 | +2.45 | 97.41 | +0 | +0 | +0.0 | +0 |
| fix defects | +0.01 | +0.00 | +0.01 | 1.97 | +0 | +0 | +0.0 | +0 |
| release preprocessing | +0.03 | +0.00 | +0.03 | 2.37 | +0 | +0 | +0.0 | +0 |
| **global fft** | -3.54 * | +0.16 | -3.74 * | 2.56 | +0 | -24 * | +0.0 | +0 |
| power spectrum | -0.15 | +0.00 | -0.15 | 0.50 | +0 | +0 | +0.0 | +0 |
| global alignment | -0.06 | -0.00 | -0.08 | 4.24 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global ifft** | -1.55 | +0.09 | -1.64 | 1.78 | +0 | -23 * | +0.0 | +0 |
| patch alignment | -0.54 | +0.12 | -0.64 | 11.02 | +0 | +0 | +0.0 | +0 |
| fit polynomial | +0.01 | +0.00 | +0.01 | 0.67 | +0 | +0 | +0.0 | +0 |
| release alignment | -0.11 | +0.00 | -0.11 | 2.91 | +0 | +0 | +0.0 | +0 |
| **dose weighting** | -0.28 | -1.27 | +0.85 | 78.53 | +0 | -28 * | -1304.3 * | -4 * |
| movie teardown | +0.05 | +0.00 | +0.05 | 10.19 | +0 | +0 | +0.0 | +0 |
| submit model and plot | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | -0.70 | +0.00 | -0.70 | 28.38 | +0 | +0 | +0.0 | +0 |
| after last movie | -24.40 | +0.00 | -24.40 | 609.91 | +0 | +0 | +0.0 | +0 |

Traced device allocation high-water per pass: base 3221, 3221 MiB, arm 3221, 3221 MiB.

## Device: `noC` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8028.2 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3622.1 ms (45.1%); idle 4406.1 ms. Kernels 25206 (3112.3 ms summed), copies 3823 (540.8 ms, 67088.0 MiB). Overlap between kernels and copies 31.09 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.28 |
| setup | 1.52 | 0.00 | 0.00 | 0.00 | 0% | 1.52 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.83 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 108.39 |
| session and device ingest | 78.10 | 39.38 | 28.97 | 11.50 | 50% | 38.36 | 54 | 12 | 27 | 0.87 | 5/0 | 130.7 | 18 | 2932 | 375.74 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 19.71 | 0.31 | 0.30 | 0.01 | 2% | 19.39 | 12 | 6 | 10 | 1.10 | 6/6 | 0.0 | 4 | 2933 | 71.80 |
| fix defects | 2.23 | 0.02 | 0.01 | 0.01 | 1% | 2.21 | 10 | 2 | 9 | 0.62 | 3/3 | 0.0 | 7 | 2932 | 4.01 |
| release preprocessing | 0.44 | 0.00 | 0.00 | 0.00 | 0% | 0.44 | 1 | 0 | 2 | 0.37 | 0/1 | 0.0 | 0 | 2932 | 0.34 |
| global fft | 25.63 | 21.43 | 21.43 | 0.00 | 84% | 4.24 | 170 | 169 | 25 | 2.63 | 0/0 | 0.0 | 0 | 2877 | 25.45 |
| power spectrum | 0.23 | 0.00 | 0.00 | 0.00 | 0% | 0.23 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.10 |
| global alignment | 14.23 | 7.13 | 7.11 | 0.02 | 50% | 7.17 | 34 | 19 | 24 | 2.22 | 9/9 | 0.0 | 14 | 3143 | 12.78 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 23.86 | 21.74 | 20.03 | 1.71 | 91% | 2.10 | 193 | 168 | 48 | 1.70 | 0/0 | 1304.3 | 0 | 2877 | 24.06 |
| patch alignment | 46.97 | 24.94 | 24.88 | 0.05 | 53% | 21.97 | 497 | 456 | 51 | 2.22 | 17/3 | 0.0 | 38 | 3221 | 49.33 |
| fit polynomial | 1.72 | 0.00 | 0.00 | 0.00 | 0% | 1.72 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.85 |
| release alignment | 1.84 | 0.00 | 0.00 | 0.00 | 0% | 1.84 | 1 | 0 | 8 | 1.40 | 0/8 | 0.0 | 0 | 3221 | 1.93 |
| dose weighting | 45.96 | 36.19 | 27.31 | 8.92 | 79% | 9.72 | 245 | 217 | 33 | 1.83 | 5/5 | 1358.6 | 2 | 3172 | 78.96 |
| movie teardown | 7.49 | 0.00 | 0.00 | 0.00 | 0% | 7.49 | 1 | 0 | 11 | 4.15 | 0/10 | 0.0 | 0 | 2982 | 8.77 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.15 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.94 | 0.00 | 4.94 | 0 | 0/0 |
| between movies | 4.64 | 0.00 | 4.64 | 0 | 0/0 |
| after last movie | 928.13 | 0.00 | 928.13 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1021.19 | 176.6 | 239.1 | 32.8% |
| inflate_kernel | 96 | 586.57 | 6110.2 | 6216.8 | 18.8% |
| regular_fft_factor | 5784 | 435.93 | 75.4 | 85.9 | 14.0% |
| fourierShiftKernel | 1277 | 215.07 | 168.4 | 1769.6 | 6.9% |
| regular_bluestein_fft | 600 | 185.27 | 308.8 | 316.3 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.14 | 175.6 | 183.0 | 3.2% |
| scaleComplexKernel | 624 | 79.02 | 126.6 | 1669.0 | 2.5% |
| postprocess_kernel | 1176 | 77.71 | 66.1 | 73.6 | 2.5% |
| preprocess_kernel | 1152 | 75.24 | 65.3 | 69.1 | 2.4% |
| applyDoseWeightKernel | 576 | 63.38 | 110.0 | 117.8 | 2.0% |
| cropAndGroupPatchResidentKernel | 600 | 62.74 | 104.6 | 114.3 | 2.0% |
| adler32StripsKernel | 96 | 55.23 | 575.3 | 582.6 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.84 | 529.5 | 552.5 | 1.6% |
| regular_fft | 1301 | 26.96 | 20.7 | 231.2 | 0.9% |
| regular_fft_c2r | 1277 | 22.91 | 17.9 | 182.3 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 3055 | 987.28 | 113.71 |
| device sync | 1320 | 843.70 | 109.20 |
| event sync | 384 | 292.21 | 10.73 |
| free (implicit sync) | 1084 | 286.35 | 286.35 |
| stream sync | 120 | 22.08 | 6.42 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 1152 | 62607.4 | 82.09 | 799.67 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 269.44 | 11.98 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 176.50 | 7.75 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 9.87 | 6.96 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.94 | 12.02 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `rc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8402.5 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3779.4 ms (45.0%); idle 4623.1 ms. Kernels 25206 (3110.2 ms summed), copies 3247 (681.4 ms, 35784.3 MiB). Overlap between kernels and copies 12.92 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.24 | 0.00 | 0.00 | 0.00 | 0% | 0.24 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.25 |
| setup | 1.56 | 0.00 | 0.00 | 0.00 | 0% | 1.56 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.79 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 131.10 |
| session and device ingest | 85.98 | 40.46 | 28.90 | 12.22 | 47% | 44.75 | 59 | 12 | 27 | 0.95 | 5/0 | 130.7 | 18 | 2932 | 384.92 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 25.62 | 0.31 | 0.30 | 0.01 | 1% | 25.31 | 12 | 6 | 10 | 1.06 | 6/6 | 0.0 | 4 | 2933 | 90.70 |
| fix defects | 2.28 | 0.02 | 0.01 | 0.01 | 1% | 2.26 | 10 | 2 | 9 | 0.52 | 3/3 | 0.0 | 7 | 2932 | 4.89 |
| release preprocessing | 0.36 | 0.00 | 0.00 | 0.00 | 0% | 0.36 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.34 |
| global fft | 21.98 | 21.58 | 21.58 | 0.00 | 98% | 0.39 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 21.96 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 14.35 | 7.13 | 7.11 | 0.02 | 50% | 7.23 | 34 | 19 | 24 | 2.21 | 9/9 | 0.0 | 14 | 3143 | 13.22 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.36 | 21.83 | 20.06 | 1.77 | 98% | 0.53 | 193 | 168 | 25 | 0.21 | 0/0 | 1304.3 | 0 | 2877 | 22.41 |
| patch alignment | 46.76 | 25.06 | 25.01 | 0.05 | 54% | 21.81 | 497 | 456 | 51 | 2.48 | 17/3 | 0.0 | 38 | 3221 | 48.83 |
| fit polynomial | 1.75 | 0.00 | 0.00 | 0.00 | 0% | 1.75 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.66 |
| release alignment | 1.61 | 0.00 | 0.00 | 0.00 | 0% | 1.61 | 1 | 0 | 8 | 1.21 | 0/8 | 0.0 | 0 | 3221 | 1.75 |
| dose weighting | 48.91 | 35.60 | 27.05 | 8.52 | 73% | 13.17 | 221 | 217 | 5 | 0.90 | 1/1 | 54.3 | 2 | 3117 | 117.62 |
| movie teardown | 7.90 | 0.00 | 0.00 | 0.00 | 0% | 7.90 | 1 | 0 | 11 | 4.22 | 0/10 | 0.0 | 0 | 2982 | 8.89 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.16 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.41 | 0.00 | 4.41 | 0 | 0/0 |
| between movies | 5.09 | 0.00 | 5.09 | 0 | 0/0 |
| after last movie | 911.08 | 0.00 | 911.08 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1022.10 | 176.7 | 238.8 | 32.9% |
| inflate_kernel | 96 | 585.56 | 6099.6 | 6200.3 | 18.8% |
| regular_fft_factor | 5784 | 433.43 | 74.9 | 84.7 | 13.9% |
| fourierShiftKernel | 1277 | 215.26 | 168.6 | 1768.2 | 6.9% |
| regular_bluestein_fft | 600 | 186.52 | 310.9 | 320.0 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.25 | 175.8 | 184.0 | 3.3% |
| postprocess_kernel | 1176 | 79.59 | 67.7 | 74.8 | 2.6% |
| scaleComplexKernel | 624 | 79.09 | 126.7 | 1670.4 | 2.5% |
| preprocess_kernel | 1152 | 75.41 | 65.5 | 69.1 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.99 | 105.0 | 114.3 | 2.0% |
| applyDoseWeightKernel | 576 | 60.30 | 104.7 | 107.7 | 1.9% |
| adler32StripsKernel | 96 | 54.97 | 572.6 | 582.2 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.59 | 527.0 | 549.1 | 1.6% |
| regular_fft | 1301 | 27.04 | 20.8 | 231.6 | 0.9% |
| regular_fft_c2r | 1277 | 22.98 | 18.0 | 182.0 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 1116.63 | 100.91 |
| device sync | 192 | 649.19 | 15.97 |
| event sync | 384 | 296.79 | 28.07 |
| free (implicit sync) | 988 | 264.25 | 264.25 |
| stream sync | 120 | 23.19 | 9.80 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.90 | 765.08 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 283.44 | 11.38 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 337.91 | 4.05 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 15.10 | 4.55 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.07 | 17.12 |

Byte counts are invariant across captures; rates are not (contention, tracing).
