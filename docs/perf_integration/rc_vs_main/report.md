# MotionCorr compare: main vs rc

## Provenance

- kit: `d873993522986893eb2a7d6346828a53771d35ed`
- arm `main`: `/home/alex/mc-prof-abc/build-main/motioncorr` sha256 `c73168a5ca85f908`; source `9d14275ab6c98ba73a5839065111a548030c7acb` (git in /home/alex/mc-prof-abc/src-main); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `rc`: `/home/alex/mc-rc/build-rc/motioncorr` sha256 `ff1bc2679a040bc9`; source `c0f82c2d65bcfc6c68042313d22c1fe132c1a306` (git in /home/alex/mc-rc/src-rc); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 15.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 15 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `main` on, `rc` on
- CUDA device timing in trace passes: `main` on (binary has no --profile_device_timing), `rc` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-rc/src-kit/tools/profiling/mcprof.py compare main=/home/alex/mc-prof-abc/build-main/motioncorr rc=/home/alex/mc-rc/build-rc/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work /home/alex/mc-rc/camp/rc_vs_main --source main=/home/alex/mc-prof-abc/src-main --source rc=/home/alex/mc-rc/src-rc -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| main | 12 | 9.379 | 1.638 | 8.117-17.261 | 17.009 | 642 | 208702 | 17 | 3512 | 3521 |
| rc | 12 | 7.100 | 0.165 | 6.847-8.464 | 17.822 | 368 | 150363 | 11 | 3558 | 3567 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `main`: load1 15.0-25.1, max foreign CPU on lane 0.13 cores, wall outlier rounds [12]
- `rc`: load1 14.8-25.3, max foreign CPU on lane 0.04 cores, wall outlier rounds [13]

Rounds: 15 planned, 12 retained, 3 discarded (a discard removes the whole round, every arm). Discards triggered by: `main` 3 (alone 2), `rc` 1 (alone 0). Kept orders: AB 6, BA 6.

WARNING: arm main alone triggered 2 of 3 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

Discarded rounds:
- round 3 (AB): main: foreign CPU on lane 0.52 cores
- round 11 (AB): main: foreign CPU on lane 0.91 cores | rc: foreign CPU on lane 0.81 cores
- round 14 (BA): main: foreign CPU on lane 0.40 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 242 s, r13 1 s, r14 34 s, r15 1 s.

### `rc` vs `main`: **resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -2.114 | -2.670..-1.127 | -10.026..-1.042 | -2.689..-1.086 (96.1%) | 1.148 | 0+/12- p=0.000488 | -22.54% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `rc` is slower.
Positional: median B-A when `rc` ran second -2.316 s (n=6), first -1.699 s (n=6); cost of running second -0.309 s.
Paired differences (s): -2.663, -2.259, -1.070, -3.291, -2.493, -1.042, -1.086, -1.675, -1.140, -10.026, -1.970, -2.689

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| rc | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `main` 3, `rc` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `main`

Movie wall (steady median): 276.1 -> 230.6 ms (-45.45 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.48 | 1.49 | +0.01 | 0.50 | +0.02 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | +0.00 | +0 |
| session and device ingest | 79.34 | 66.43 | -12.91 | 20.98 | +5.97 | -237 |
| host read movie | 0.05 | 0.04 | -0.01 | 0.50 | -0.01 | +0 |
| **allocate host sum** | 10.68 | 0.01 | -10.66 * | 1.96 | -10.67 * | +0 |
| gain and sum | 0.06 | 0.04 | -0.02 | 0.50 | -0.01 | +0 |
| hot pixels | 17.73 | 18.78 | +1.04 | 3.17 | +1.08 | +0 |
| **fix defects** | 1.15 | 1.94 | +0.80 * | 0.50 | +0.79 * | -0 |
| release preprocessing | 0.24 | 0.31 | +0.08 | 0.50 | +0.06 | +0 |
| global fft | 22.82 | 21.93 | -0.89 | 1.69 | -0.89 | +0 |
| power spectrum | 0.05 | 0.06 | +0.01 | 0.50 | +0.01 | +0 |
| global alignment | 11.51 | 11.68 | +0.17 | 2.41 | +0.19 | +0 |
| **allocate reconstruction** | 5.25 | 0.01 | -5.24 * | 0.93 | -5.24 * | +0 |
| **global ifft** | 23.99 | 22.07 | -1.91 * | 1.00 | -1.87 * | +0 |
| **patch alignment** | 46.94 | 32.71 | -14.23 * | 5.07 | -14.26 * | +0 |
| fit polynomial | 1.63 | 1.65 | +0.02 | 0.50 | +0.01 | +0 |
| release alignment | 0.74 | 1.10 | +0.36 | 0.65 | +0.37 | +0 |
| dose weighting | 47.30 | 44.96 | -2.33 | 5.35 | -2.26 | +1 |
| movie teardown | 4.33 | 4.50 | +0.17 | 0.76 | +0.16 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `main` 2, `rc` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `main`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +0.24 | +0.00 | +0.24 | 9.77 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.08 | +0.00 | -0.08 | 0.53 | +0 | +0 | +0.0 | +0 |
| setup | -0.07 | +0.00 | -0.07 | 3.74 | +0 | +0 | +0.0 | +0 |
| read gain | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| **session and device ingest** | -14.33 | +0.45 | -14.43 | 174.35 | +9 * | +6 * | -0.7 * | +0 |
| host read movie | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| **allocate host sum** | -11.40 * | +0.00 | -11.40 * | 10.17 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | +0.90 | +0.00 | +0.89 | 31.64 | +0 | +0 | +0.0 | +0 |
| fix defects | +0.01 | +0.00 | +0.01 | 2.51 | +0 | +0 | +0.0 | +0 |
| release preprocessing | -0.06 | +0.00 | -0.06 | 1.28 | +0 | +0 | +0.0 | +0 |
| **global fft** | -3.54 * | +0.18 | -3.72 * | 1.28 | +0 | -24 * | +0.0 | +0 |
| power spectrum | -0.14 | +0.00 | -0.14 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global alignment** | -2.33 | +0.02 | -2.35 | 4.35 | +0 | -15 * | +0.0 | +0 |
| allocate reconstruction | -5.08 | +0.00 | -5.08 | 6.39 | +0 | +0 | +0.0 | +0 |
| **global ifft** | -1.90 | +0.18 | -2.15 | 6.58 | +0 | -23 * | +0.0 | +0 |
| **patch alignment** | -59.02 * | -0.00 | -58.92 * | 44.05 | +0 | -489 * | -0.0 * | -2 * |
| fit polynomial | -0.01 | +0.00 | -0.01 | 1.28 | +0 | +0 | +0.0 | +0 |
| **release alignment** | +0.07 | +0.00 | +0.07 | 1.17 | +0 | -1 * | +0.0 | +0 |
| **dose weighting** | -13.22 * | -1.31 | -12.14 * | 9.43 | +0 | -100 * | -1304.3 * | -4 * |
| movie teardown | -0.95 | +0.00 | -0.95 | 28.82 | +0 | +0 | +0.0 | +0 |
| submit model and plot | -0.03 | +0.00 | -0.03 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | -0.76 | +0.00 | -0.76 | 28.66 | +0 | +0 | +0.0 | +0 |
| after last movie | +31.07 | +0.00 | +31.07 | 1760.92 | +0 | +0 | +0.0 | +0 |

Traced device allocation high-water per pass: base 3236, 3236 MiB, arm 3221, 3221 MiB.

## Device: `main` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: on (binary has no --profile_device_timing).

Traced window 11733.8 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3612.9 ms (30.8%); idle 8120.9 ms. Kernels 24990 (3064.8 ms summed), copies 8639 (547.2 ms, 67104.9 MiB). Overlap between kernels and copies 0.00 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.34 | 0.00 | 0.00 | 0.00 | 0% | 0.34 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3056 | 0.31 |
| setup | 1.57 | 0.00 | 0.00 | 0.00 | 0% | 1.57 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 1.90 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 93.95 |
| session and device ingest | 88.69 | 39.42 | 27.88 | 11.51 | 44% | 49.50 | 30 | 3 | 21 | 0.70 | 5/0 | 131.4 | 25 | 2996 | 423.91 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 0.07 |
| allocate host sum | 11.10 | 0.00 | 0.00 | 0.00 | 0% | 11.10 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 43.01 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2996 | 0.07 |
| hot pixels | 18.42 | 0.31 | 0.30 | 0.01 | 2% | 18.11 | 12 | 6 | 10 | 1.22 | 6/6 | 0.0 | 4 | 2997 | 74.05 |
| fix defects | 2.16 | 0.02 | 0.01 | 0.01 | 1% | 2.14 | 10 | 2 | 9 | 0.64 | 3/3 | 0.0 | 7 | 2996 | 2.52 |
| release preprocessing | 0.45 | 0.00 | 0.00 | 0.00 | 0% | 0.45 | 1 | 0 | 2 | 0.29 | 0/1 | 0.0 | 0 | 2996 | 0.33 |
| global fft | 25.53 | 21.41 | 21.41 | 0.00 | 84% | 4.12 | 170 | 169 | 25 | 2.68 | 0/0 | 0.0 | 0 | 2941 | 25.53 |
| power spectrum | 0.22 | 0.00 | 0.00 | 0.00 | 0% | 0.22 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2941 | 0.09 |
| global alignment | 16.58 | 7.11 | 7.09 | 0.02 | 43% | 9.46 | 34 | 19 | 39 | 2.93 | 9/9 | 0.0 | 14 | 3207 | 13.86 |
| allocate reconstruction | 5.30 | 0.00 | 0.00 | 0.00 | 0% | 5.30 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2941 | 5.21 |
| global ifft | 24.03 | 21.67 | 19.98 | 1.69 | 90% | 2.36 | 193 | 168 | 48 | 1.78 | 0/0 | 1304.3 | 0 | 2941 | 23.97 |
| patch alignment | 106.19 | 25.05 | 24.71 | 0.33 | 24% | 81.03 | 717 | 456 | 540 | 24.84 | 19/4 | 0.0 | 258 | 3108 | 1385.07 |
| fit polynomial | 1.72 | 0.00 | 0.00 | 0.00 | 0% | 1.72 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3056 | 1.84 |
| release alignment | 1.59 | 0.00 | 0.00 | 0.00 | 0% | 1.59 | 1 | 0 | 9 | 0.97 | 0/9 | 0.0 | 0 | 3056 | 2.05 |
| dose weighting | 55.83 | 35.84 | 26.68 | 9.12 | 64% | 20.22 | 245 | 217 | 105 | 5.81 | 5/5 | 1358.6 | 2 | 3236 | 78.93 |
| movie teardown | 7.40 | 0.00 | 0.00 | 0.00 | 0% | 7.40 | 1 | 0 | 11 | 4.11 | 0/10 | 0.0 | 0 | 3046 | 7.84 |
| submit model and plot | 0.15 | 0.00 | 0.00 | 0.00 | 0% | 0.15 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 225 | 0.15 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.83 | 0.00 | 4.83 | 0 | 0/0 |
| between movies | 4.38 | 0.00 | 4.38 | 0 | 0/0 |
| after last movie | 924.54 | 0.00 | 924.54 | 0 | 0/3 |

Device 0 allocation high-water 3236 MiB at stage `dose weighting` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1018.16 | 176.0 | 234.6 | 33.2% |
| inflate_kernel | 24 | 568.09 | 23670.5 | 23888.3 | 18.5% |
| regular_fft_factor | 5784 | 426.15 | 73.7 | 86.7 | 13.9% |
| fourierShiftKernel | 1277 | 215.59 | 168.8 | 1769.2 | 7.0% |
| regular_bluestein_fft | 600 | 183.74 | 306.2 | 310.1 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 100.74 | 174.9 | 181.0 | 3.3% |
| scaleComplexKernel | 624 | 78.95 | 126.5 | 1669.4 | 2.6% |
| postprocess_kernel | 1176 | 77.14 | 65.6 | 75.3 | 2.5% |
| preprocess_kernel | 1152 | 74.91 | 65.0 | 67.1 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.05 | 103.4 | 112.0 | 2.0% |
| applyDoseWeightKernel | 576 | 59.71 | 103.7 | 104.4 | 1.9% |
| adler32StripsKernel | 24 | 51.81 | 2158.9 | 2163.0 | 1.7% |
| fusedU16FlipGainAndSumKernel | 24 | 46.41 | 1933.9 | 1941.5 | 1.5% |
| regular_fft | 1301 | 27.04 | 20.8 | 235.1 | 0.9% |
| regular_fft_c2r | 1277 | 22.90 | 17.9 | 181.5 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| event sync | 8785 | 1155.33 | 548.13 |
| device sync | 1320 | 809.29 | 92.01 |
| synchronous memcpy | 8351 | 764.48 | 551.35 |
| free (implicit sync) | 1132 | 305.03 | 305.03 |
| stream sync | 120 | 50.86 | 5.35 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 1152 | 62607.4 | 80.61 | 814.36 |
| Host-to-Device Pinned->Device | 24 | 3026.7 | 263.88 | 12.03 |
| Device-to-Host Device->Pageable | 2770 | 1337.7 | 186.39 | 7.53 |
| Host-to-Device Pageable->Device | 4693 | 133.1 | 16.35 | 8.54 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `rc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8063.9 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3619.0 ms (44.9%); idle 4445.0 ms. Kernels 25206 (3113.4 ms summed), copies 3247 (517.9 ms, 35784.3 MiB). Overlap between kernels and copies 12.87 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.28 | 0.00 | 0.00 | 0.00 | 0% | 0.28 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.27 |
| setup | 1.66 | 0.00 | 0.00 | 0.00 | 0% | 1.66 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.87 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 101.90 |
| session and device ingest | 82.22 | 39.99 | 28.93 | 11.58 | 49% | 42.49 | 59 | 12 | 27 | 0.95 | 5/0 | 130.7 | 18 | 2932 | 390.63 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.09 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 20.67 | 0.31 | 0.30 | 0.01 | 2% | 20.36 | 12 | 6 | 10 | 1.27 | 6/6 | 0.0 | 4 | 2933 | 85.66 |
| fix defects | 2.28 | 0.02 | 0.01 | 0.01 | 1% | 2.26 | 10 | 2 | 9 | 0.68 | 3/3 | 0.0 | 7 | 2932 | 4.29 |
| release preprocessing | 0.36 | 0.00 | 0.00 | 0.00 | 0% | 0.36 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.34 |
| global fft | 21.98 | 21.58 | 21.58 | 0.00 | 98% | 0.37 | 170 | 169 | 1 | 0.13 | 0/0 | 0.0 | 0 | 2877 | 22.10 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.23 |
| global alignment | 14.35 | 7.13 | 7.11 | 0.02 | 50% | 7.21 | 34 | 19 | 24 | 2.21 | 9/9 | 0.0 | 14 | 3143 | 13.05 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.03 |
| global ifft | 22.31 | 21.83 | 20.07 | 1.77 | 98% | 0.43 | 193 | 168 | 25 | 0.19 | 0/0 | 1304.3 | 0 | 2877 | 22.26 |
| patch alignment | 47.61 | 25.09 | 25.03 | 0.05 | 53% | 22.60 | 497 | 456 | 51 | 2.42 | 17/3 | 0.0 | 38 | 3221 | 47.97 |
| fit polynomial | 1.73 | 0.00 | 0.00 | 0.00 | 0% | 1.73 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.78 |
| release alignment | 1.69 | 0.00 | 0.00 | 0.00 | 0% | 1.69 | 1 | 0 | 8 | 1.26 | 0/8 | 0.0 | 0 | 3221 | 1.53 |
| dose weighting | 42.91 | 34.90 | 27.04 | 7.89 | 81% | 7.92 | 221 | 217 | 5 | 0.85 | 1/1 | 54.3 | 2 | 3117 | 74.37 |
| movie teardown | 7.51 | 0.00 | 0.00 | 0.00 | 0% | 7.51 | 1 | 0 | 11 | 4.20 | 0/10 | 0.0 | 0 | 2982 | 7.67 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.29 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.05 | 0.00 | 5.05 | 0 | 0/0 |
| between movies | 4.48 | 0.00 | 4.48 | 0 | 0/0 |
| after last movie | 1019.25 | 0.00 | 1019.25 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1023.36 | 176.9 | 241.7 | 32.9% |
| inflate_kernel | 96 | 587.25 | 6117.2 | 6227.8 | 18.9% |
| regular_fft_factor | 5784 | 433.37 | 74.9 | 84.5 | 13.9% |
| fourierShiftKernel | 1277 | 215.05 | 168.4 | 1775.8 | 6.9% |
| regular_bluestein_fft | 600 | 186.68 | 311.1 | 318.5 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.18 | 175.7 | 181.7 | 3.2% |
| postprocess_kernel | 1176 | 79.67 | 67.7 | 75.6 | 2.6% |
| scaleComplexKernel | 624 | 79.08 | 126.7 | 1670.0 | 2.5% |
| preprocess_kernel | 1152 | 75.38 | 65.4 | 71.1 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 63.05 | 105.1 | 114.6 | 2.0% |
| applyDoseWeightKernel | 576 | 60.32 | 104.7 | 107.4 | 1.9% |
| adler32StripsKernel | 96 | 55.10 | 574.0 | 582.3 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.69 | 528.0 | 548.7 | 1.6% |
| regular_fft | 1301 | 27.08 | 20.8 | 231.7 | 0.9% |
| regular_fft_c2r | 1277 | 23.01 | 18.0 | 183.4 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 936.54 | 105.10 |
| device sync | 192 | 626.44 | 14.13 |
| event sync | 384 | 283.71 | 15.22 |
| free (implicit sync) | 988 | 265.92 | 265.92 |
| stream sync | 120 | 21.26 | 5.73 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.42 | 773.75 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 268.01 | 12.04 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 195.16 | 7.01 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 9.44 | 7.28 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.81 | 12.57 |

Byte counts are invariant across captures; rates are not (contention, tracing).
