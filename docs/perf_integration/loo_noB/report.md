# MotionCorr compare: noB vs rc

## Provenance

- kit: `d873993522986893eb2a7d6346828a53771d35ed`
- arm `noB`: `/home/alex/mc-rc/build-noB/motioncorr` sha256 `2b37c5f5ee468543`; source `644737630b08b9d0ca451e6bc0772b921217165b` (git in /home/alex/mc-rc/src-noB); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `rc`: `/home/alex/mc-rc/build-rc/motioncorr` sha256 `ff1bc2679a040bc9`; source `c0f82c2d65bcfc6c68042313d22c1fe132c1a306` (git in /home/alex/mc-rc/src-rc); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 15.6, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 12 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `noB` on, `rc` on
- CUDA device timing in trace passes: `noB` off, `rc` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-rc/src-kit/tools/profiling/mcprof.py compare noB=/home/alex/mc-rc/build-noB/motioncorr rc=/home/alex/mc-rc/build-rc/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work /home/alex/mc-rc/camp/loo_noB --source noB=/home/alex/mc-rc/src-noB --source rc=/home/alex/mc-rc/src-rc -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| noB | 12 | 7.565 | 0.192 | 7.312-8.806 | 15.482 | 567 | 197386 | 14 | 3558 | 3567 |
| rc | 12 | 7.328 | 0.741 | 7.074-8.365 | 18.820 | 368 | 150608 | 15 | 3558 | 3567 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `noB`: load1 15.1-17.7, max foreign CPU on lane 0.23 cores, wall outlier rounds [10]
- `rc`: load1 15.0-17.2, max foreign CPU on lane 0.17 cores, wall outlier rounds [2]

Rounds: 12 planned, 12 retained, 0 discarded (a discard removes the whole round, every arm). Discards triggered by: `noB` 0 (alone 0), `rc` 0 (alone 0). Kept orders: AB 6, BA 6.

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 20 s, r7 4 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 2 s.

### `rc` vs `noB`: **not resolved (below noise 0.683 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.238 | -0.355..+0.395 | -1.499..+1.053 | -0.399..+0.508 (96.1%) | 0.683 | 5+/7- p=0.774 | -3.14% |

Reason: CI of median includes 0. Positive differences mean `rc` is slower.
Positional: median B-A when `rc` ran second -0.238 s (n=6), first -0.073 s (n=6); cost of running second -0.082 s.
Paired differences (s): -0.728, +1.053, -0.235, -0.340, +0.585, -0.399, -0.240, +0.193, +0.508, -1.499, -0.267, +0.357

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| rc | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `noB` 3, `rc` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noB`

Movie wall (steady median): 243.5 -> 233.1 ms (-10.38)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.62 | 1.43 | -0.19 | 1.30 | -0.19 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| **session and device ingest** | 80.40 | 69.15 | -11.25 | 17.16 | -9.03 | -288 * |
| host read movie | 0.05 | 0.04 | -0.01 | 0.50 | -0.01 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | +0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 18.05 | 19.00 | +0.95 | 2.81 | +0.96 | +0 |
| **fix defects** | 1.25 | 1.99 | +0.74 * | 0.57 | +0.68 * | +0 |
| release preprocessing | 0.27 | 0.29 | +0.02 | 0.50 | +0.02 | +0 |
| global fft | 21.79 | 21.92 | +0.14 | 0.50 | +0.13 | +0 |
| power spectrum | 0.06 | 0.05 | -0.01 | 0.50 | -0.01 | +0 |
| global alignment | 11.78 | 11.67 | -0.11 | 2.18 | -0.08 | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | -0.00 | +0 |
| global ifft | 22.09 | 22.09 | +0.00 | 0.50 | -0.00 | +0 |
| patch alignment | 33.03 | 32.47 | -0.56 | 3.95 | -0.63 | +0 |
| fit polynomial | 1.67 | 1.67 | +0.00 | 0.50 | +0.00 | +0 |
| release alignment | 1.18 | 1.08 | -0.10 | 0.68 | -0.09 | +0 |
| dose weighting | 44.53 | 44.48 | -0.05 | 5.23 | -0.06 | +0 |
| movie teardown | 4.79 | 4.74 | -0.04 | 3.19 | -0.11 | +0 |
| submit model and plot | 0.09 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `noB` 2, `rc` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noB`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +0.29 | +0.00 | +0.29 | 11.36 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.06 | +0.00 | -0.06 | 0.63 | +0 | +0 | +0.0 | +0 |
| setup | -0.17 | +0.00 | -0.17 | 3.91 | +0 | +0 | +0.0 | +0 |
| read gain | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **session and device ingest** | -11.60 | +0.05 | -12.12 * | 11.44 | +9 * | +6 * | -0.7 * | +0 |
| host read movie | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | +0.64 | +0.00 | +0.64 | 47.30 | +0 | +0 | +0.0 | +0 |
| fix defects | +0.08 | +0.00 | +0.08 | 3.62 | +0 | +0 | +0.0 | +0 |
| release preprocessing | +0.02 | +0.00 | +0.02 | 0.87 | +0 | +0 | +0.0 | +0 |
| global fft | +0.04 | -0.01 | +0.04 | 0.50 | +0 | +0 | +0.0 | +0 |
| power spectrum | -0.02 | +0.00 | -0.02 | 0.50 | +0 | +0 | +0.0 | +0 |
| global alignment | -0.12 | +0.00 | -0.11 | 13.30 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| global ifft | +0.00 | +0.00 | +0.02 | 1.64 | +0 | +0 | +0.0 | +0 |
| patch alignment | +0.10 | -0.01 | -0.05 | 46.99 | +0 | +0 | +0.0 | +0 |
| fit polynomial | -0.01 | +0.00 | -0.01 | 1.49 | +0 | +0 | +0.0 | +0 |
| release alignment | -0.07 | +0.00 | -0.07 | 4.61 | +0 | +0 | +0.0 | +0 |
| dose weighting | +0.01 | +0.15 | +0.09 | 21.00 | +0 | +0 | +0.0 | +0 |
| movie teardown | -0.65 | +0.00 | -0.65 | 23.96 | +0 | +0 | +0.0 | +0 |
| submit model and plot | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | +0.28 | +0.00 | +0.28 | 27.21 | +0 | +0 | +0.0 | +0 |
| **after last movie** | -68.93 | +0.00 | -68.93 | 551.29 | +0 | +0 | +0.0 | +0 |

Traced device allocation high-water per pass: base 3285, 3285 MiB, arm 3221, 3221 MiB.

## Device: `noB` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8409.3 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3613.1 ms (43.0%); idle 4796.2 ms. Kernels 24990 (3090.9 ms summed), copies 2767 (521.2 ms, 35801.2 MiB). Overlap between kernels and copies 0.00 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.36 | 0.00 | 0.00 | 0.00 | 0% | 0.36 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3285 | 0.48 |
| setup | 1.76 | 0.00 | 0.00 | 0.00 | 0% | 1.76 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 1.81 |
| read gain | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 112.12 |
| session and device ingest | 92.41 | 39.51 | 27.96 | 11.53 | 43% | 52.57 | 30 | 3 | 21 | 0.90 | 5/0 | 131.4 | 25 | 2996 | 443.01 |
| host read movie | 0.09 | 0.00 | 0.00 | 0.00 | 0% | 0.09 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 0.07 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 0.07 |
| hot pixels | 20.67 | 0.31 | 0.30 | 0.01 | 2% | 20.36 | 12 | 6 | 10 | 1.36 | 6/6 | 0.0 | 4 | 2997 | 78.05 |
| fix defects | 2.38 | 0.02 | 0.01 | 0.01 | 1% | 2.35 | 10 | 2 | 9 | 0.66 | 3/3 | 0.0 | 7 | 2996 | 4.58 |
| release preprocessing | 0.46 | 0.00 | 0.00 | 0.00 | 0% | 0.46 | 1 | 0 | 2 | 0.35 | 0/1 | 0.0 | 0 | 2996 | 0.35 |
| global fft | 22.04 | 21.58 | 21.58 | 0.00 | 98% | 0.42 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2941 | 22.05 |
| power spectrum | 0.11 | 0.00 | 0.00 | 0.00 | 0% | 0.11 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2941 | 0.08 |
| global alignment | 14.44 | 7.13 | 7.11 | 0.02 | 49% | 7.33 | 34 | 19 | 24 | 2.20 | 9/9 | 0.0 | 14 | 3207 | 12.67 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2941 | 0.02 |
| global ifft | 22.39 | 21.86 | 20.08 | 1.77 | 98% | 0.47 | 193 | 168 | 25 | 0.22 | 0/0 | 1304.3 | 0 | 2941 | 22.33 |
| patch alignment | 46.95 | 25.07 | 25.02 | 0.05 | 53% | 21.93 | 497 | 456 | 51 | 2.40 | 17/3 | 0.0 | 38 | 3285 | 48.68 |
| fit polynomial | 1.71 | 0.00 | 0.00 | 0.00 | 0% | 1.71 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3285 | 1.78 |
| release alignment | 1.90 | 0.00 | 0.00 | 0.00 | 0% | 1.90 | 1 | 0 | 8 | 1.36 | 0/8 | 0.0 | 0 | 3285 | 1.82 |
| dose weighting | 43.29 | 34.45 | 27.05 | 7.44 | 80% | 8.76 | 221 | 217 | 5 | 1.02 | 1/1 | 54.3 | 2 | 3181 | 78.42 |
| movie teardown | 8.97 | 0.00 | 0.00 | 0.00 | 0% | 8.97 | 1 | 0 | 11 | 5.10 | 0/10 | 0.0 | 0 | 3046 | 9.26 |
| submit model and plot | 0.16 | 0.00 | 0.00 | 0.00 | 0% | 0.16 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 0.16 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.36 | 0.00 | 4.36 | 0 | 0/0 |
| between movies | 5.90 | 0.00 | 5.90 | 0 | 0/0 |
| after last movie | 957.27 | 0.00 | 957.27 | 0 | 0/3 |

Device 0 allocation high-water 3285 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1023.42 | 176.9 | 240.9 | 33.1% |
| inflate_kernel | 24 | 572.20 | 23841.8 | 24254.3 | 18.5% |
| regular_fft_factor | 5784 | 433.40 | 74.9 | 85.9 | 14.0% |
| fourierShiftKernel | 1277 | 215.13 | 168.5 | 1768.2 | 7.0% |
| regular_bluestein_fft | 600 | 186.56 | 310.9 | 319.3 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.31 | 175.9 | 183.0 | 3.3% |
| postprocess_kernel | 1176 | 79.64 | 67.7 | 74.5 | 2.6% |
| scaleComplexKernel | 624 | 79.08 | 126.7 | 1670.3 | 2.6% |
| preprocess_kernel | 1152 | 75.38 | 65.4 | 69.2 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.78 | 104.6 | 109.7 | 2.0% |
| applyDoseWeightKernel | 576 | 60.27 | 104.6 | 107.2 | 2.0% |
| adler32StripsKernel | 24 | 52.03 | 2167.9 | 2180.3 | 1.7% |
| fusedU16FlipGainAndSumKernel | 24 | 46.57 | 1940.3 | 1957.1 | 1.5% |
| regular_fft | 1301 | 27.08 | 20.8 | 234.0 | 0.9% |
| regular_fft_c2r | 1277 | 23.02 | 18.0 | 183.4 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 971.60 | 100.19 |
| device sync | 192 | 652.54 | 15.68 |
| free (implicit sync) | 988 | 316.67 | 316.67 |
| event sync | 240 | 68.39 | 10.33 |
| stream sync | 120 | 51.20 | 6.29 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.55 | 771.39 |
| Host-to-Device Pinned->Device | 24 | 3026.7 | 263.67 | 12.04 |
| Device-to-Host Device->Pageable | 698 | 1337.8 | 201.87 | 6.95 |
| Host-to-Device Pageable->Device | 1469 | 133.0 | 13.14 | 10.62 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `rc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8166.7 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3617.3 ms (44.3%); idle 4549.3 ms. Kernels 25206 (3112.6 ms summed), copies 3247 (521.8 ms, 35784.3 MiB). Overlap between kernels and copies 17.54 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.32 | 0.00 | 0.00 | 0.00 | 0% | 0.32 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.31 |
| setup | 1.46 | 0.00 | 0.00 | 0.00 | 0% | 1.46 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.61 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 113.72 |
| session and device ingest | 80.60 | 39.46 | 28.97 | 11.45 | 49% | 40.24 | 59 | 12 | 27 | 0.89 | 5/0 | 130.7 | 18 | 2932 | 389.61 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.09 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 20.71 | 0.31 | 0.30 | 0.01 | 2% | 20.39 | 12 | 6 | 10 | 1.29 | 6/6 | 0.0 | 4 | 2933 | 89.87 |
| fix defects | 2.30 | 0.02 | 0.01 | 0.01 | 1% | 2.28 | 10 | 2 | 9 | 0.68 | 3/3 | 0.0 | 7 | 2932 | 4.55 |
| release preprocessing | 0.48 | 0.00 | 0.00 | 0.00 | 0% | 0.48 | 1 | 0 | 2 | 0.41 | 0/1 | 0.0 | 0 | 2932 | 0.51 |
| global fft | 22.05 | 21.57 | 21.57 | 0.00 | 98% | 0.45 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 22.04 |
| power spectrum | 0.10 | 0.00 | 0.00 | 0.00 | 0% | 0.10 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.14 |
| global alignment | 14.92 | 7.13 | 7.12 | 0.02 | 48% | 7.79 | 34 | 19 | 24 | 2.24 | 9/9 | 0.0 | 14 | 3143 | 13.86 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.03 |
| global ifft | 22.40 | 21.86 | 20.10 | 1.77 | 98% | 0.52 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.26 |
| patch alignment | 49.02 | 25.04 | 24.99 | 0.05 | 51% | 23.93 | 497 | 456 | 51 | 2.62 | 17/3 | 0.0 | 38 | 3221 | 48.74 |
| fit polynomial | 1.77 | 0.00 | 0.00 | 0.00 | 0% | 1.77 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.85 |
| release alignment | 1.97 | 0.00 | 0.00 | 0.00 | 0% | 1.97 | 1 | 0 | 8 | 1.49 | 0/8 | 0.0 | 0 | 3221 | 1.91 |
| dose weighting | 43.76 | 34.72 | 27.03 | 7.73 | 79% | 9.05 | 221 | 217 | 5 | 1.08 | 1/1 | 54.3 | 2 | 3117 | 79.24 |
| movie teardown | 7.82 | 0.00 | 0.00 | 0.00 | 0% | 7.82 | 1 | 0 | 11 | 4.23 | 0/10 | 0.0 | 0 | 2982 | 7.93 |
| submit model and plot | 0.14 | 0.00 | 0.00 | 0.00 | 0% | 0.14 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.13 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.03 | 0.00 | 5.03 | 0 | 0/0 |
| between movies | 5.02 | 0.00 | 5.02 | 0 | 0/0 |
| after last movie | 910.20 | 0.00 | 910.20 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1023.08 | 176.9 | 240.6 | 32.9% |
| inflate_kernel | 96 | 587.67 | 6121.5 | 6223.1 | 18.9% |
| regular_fft_factor | 5784 | 433.21 | 74.9 | 85.2 | 13.9% |
| fourierShiftKernel | 1277 | 215.14 | 168.5 | 1774.6 | 6.9% |
| regular_bluestein_fft | 600 | 186.20 | 310.3 | 318.2 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.21 | 175.7 | 181.3 | 3.3% |
| postprocess_kernel | 1176 | 79.64 | 67.7 | 74.8 | 2.6% |
| scaleComplexKernel | 624 | 79.07 | 126.7 | 1669.9 | 2.5% |
| preprocess_kernel | 1152 | 75.36 | 65.4 | 69.2 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.69 | 104.5 | 112.7 | 2.0% |
| applyDoseWeightKernel | 576 | 60.26 | 104.6 | 107.3 | 1.9% |
| adler32StripsKernel | 96 | 55.13 | 574.3 | 582.8 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.73 | 528.4 | 549.1 | 1.6% |
| regular_fft | 1301 | 27.05 | 20.8 | 234.2 | 0.9% |
| regular_fft_c2r | 1277 | 23.00 | 18.0 | 182.8 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 932.60 | 107.33 |
| device sync | 192 | 623.98 | 27.06 |
| event sync | 384 | 281.14 | 15.69 |
| free (implicit sync) | 988 | 278.28 | 278.28 |
| stream sync | 120 | 27.41 | 11.52 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.72 | 768.29 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 260.03 | 12.41 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 205.93 | 6.64 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 10.40 | 6.61 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.75 | 12.85 |

Byte counts are invariant across captures; rates are not (contention, tracing).
