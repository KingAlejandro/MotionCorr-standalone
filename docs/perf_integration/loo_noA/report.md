# MotionCorr compare: noA vs rc

## Provenance

- kit: `d873993522986893eb2a7d6346828a53771d35ed`
- arm `noA`: `/home/alex/mc-rc/build-noA/motioncorr` sha256 `473c07e60713e519`; source `b20f514b705270e9f815ea791daebe3b7c97feeb` (git in /home/alex/mc-rc/src-noA); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `rc`: `/home/alex/mc-rc/build-rc/motioncorr` sha256 `ff1bc2679a040bc9`; source `c0f82c2d65bcfc6c68042313d22c1fe132c1a306` (git in /home/alex/mc-rc/src-rc); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 16.5, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 14 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `noA` on, `rc` on
- CUDA device timing in trace passes: `noA` off, `rc` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-rc/src-kit/tools/profiling/mcprof.py compare noA=/home/alex/mc-rc/build-noA/motioncorr rc=/home/alex/mc-rc/build-rc/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work /home/alex/mc-rc/camp/loo_noA --source noA=/home/alex/mc-rc/src-noA --source rc=/home/alex/mc-rc/src-rc -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| noA | 12 | 7.304 | 0.332 | 7.175-8.573 | 18.173 | 368 | 150400 | 17 | 3476 | 3485 |
| rc | 12 | 7.148 | 0.220 | 7.057-7.813 | 18.150 | 368 | 128166 | 13 | 3558 | 3567 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `noA`: load1 15.5-17.6, max foreign CPU on lane 0.13 cores, wall outlier rounds [6, 8, 14]
- `rc`: load1 15.3-18.4, max foreign CPU on lane 0.12 cores, wall outlier rounds [11]

Rounds: 14 planned, 12 retained, 2 discarded (a discard removes the whole round, every arm). Discards triggered by: `noA` 0 (alone 0), `rc` 2 (alone 2). Kept orders: AB 6, BA 6.

WARNING: arm rc alone triggered 2 of 2 discards: the flagged condition may come from the arm itself, and dropping those pairs can bias the verdict.

Discarded rounds:
- round 3 (AB): rc: foreign CPU on lane 0.68 cores
- round 10 (BA): rc: foreign CPU on lane 0.37 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 144 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 2 s, r12 1 s, r13 2 s, r14 3 s.

### `rc` vs `noA`: **not resolved (below noise 0.549 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.171 | -0.477..-0.062 | -1.285..+0.490 | -1.127..-0.030 (96.1%) | 0.177 | 2+/10- p=0.0386 | -2.34% |

Reason: |median| does not exceed noise. Positive differences mean `rc` is slower.
Positional: median B-A when `rc` ran second -0.079 s (n=6), first -0.694 s (n=6); cost of running second +0.308 s.
Paired differences (s): +0.038, -0.261, -0.218, -0.185, -1.285, -0.084, -1.127, -0.156, +0.490, -0.030, -0.073, -1.159

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| rc | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `noA` 3, `rc` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noA`

Movie wall (steady median): 250.6 -> 228.2 ms (-22.48)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.53 | 1.49 | -0.04 | 0.62 | -0.04 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 67.62 | 64.97 | -2.65 | 29.26 | -4.30 | -1 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 23.56 | 18.91 | -4.65 | 18.14 | -4.66 | +0 |
| fix defects | 1.78 | 1.90 | +0.12 | 0.64 | +0.12 | +0 |
| release preprocessing | 0.26 | 0.24 | -0.02 | 0.50 | -0.01 | +0 |
| global fft | 21.89 | 21.92 | +0.02 | 0.50 | +0.03 | +0 |
| power spectrum | 0.05 | 0.05 | -0.00 | 0.50 | -0.00 | +0 |
| global alignment | 11.64 | 11.76 | +0.12 | 0.97 | +0.09 | +0 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| global ifft | 22.06 | 22.09 | +0.03 | 0.50 | +0.03 | +0 |
| **patch alignment** | 46.26 | 32.49 | -13.77 * | 3.59 | -13.81 * | +0 |
| fit polynomial | 1.65 | 1.66 | +0.00 | 0.50 | +0.00 | +0 |
| release alignment | 0.76 | 1.03 | +0.27 | 0.50 | +0.27 | +0 |
| dose weighting | 44.65 | 44.73 | +0.07 | 2.83 | -0.01 | +0 |
| movie teardown | 4.77 | 4.52 | -0.25 | 2.12 | -0.29 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `noA` 2, `rc` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `noA`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +0.14 | +0.00 | +0.14 | 3.78 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.03 | +0.00 | -0.03 | 0.50 | +0 | +0 | +0.0 | +0 |
| setup | -0.28 | +0.00 | -0.28 | 1.04 | +0 | +0 | +0.0 | +0 |
| read gain | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| session and device ingest | -11.57 | -0.25 | -11.05 | 151.13 | +0 | +0 | +0.0 | +0 |
| host read movie | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | -6.89 | +0.00 | -6.92 | 72.79 | +0 | +0 | +0.0 | +0 |
| fix defects | -0.27 | +0.00 | -0.27 | 8.55 | +0 | +0 | +0.0 | +0 |
| release preprocessing | -0.09 | +0.00 | -0.09 | 0.51 | +0 | +0 | +0.0 | +0 |
| global fft | +0.01 | +0.02 | -0.02 | 2.07 | +0 | +0 | +0.0 | +0 |
| power spectrum | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| global alignment | -0.97 | -0.00 | -0.97 | 30.14 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| global ifft | -0.08 | +0.00 | +0.03 | 1.69 | +0 | +0 | +0.0 | +0 |
| **patch alignment** | -20.20 | -0.17 | -20.31 | 147.57 | +0 | -191 * | +0.0 * | -2 * |
| fit polynomial | -0.34 | +0.00 | -0.34 | 9.55 | +0 | +0 | +0.0 | +0 |
| **release alignment** | -0.03 | +0.00 | -0.03 | 7.73 | +0 | -1 * | +0.0 | +0 |
| dose weighting | -1.08 | -0.64 | -0.42 | 23.96 | +0 | +0 | +0.0 | +0 |
| movie teardown | -1.63 | +0.00 | -1.63 | 10.25 | +0 | +0 | +0.0 | +0 |
| submit model and plot | -0.02 | +0.00 | -0.02 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | -2.19 | +0.00 | -2.19 | 41.16 | +0 | +0 | +0.0 | +0 |
| after last movie | +23.95 | +0.00 | +23.95 | 1375.63 | +0 | +0 | +0.0 | +0 |

Traced device allocation high-water per pass: base 3143, 3143 MiB, arm 3221, 3221 MiB.

## Device: `noA` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 9174.4 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3644.2 ms (39.7%); idle 5530.1 ms. Kernels 25206 (3105.7 ms summed), copies 7391 (538.2 ms, 35784.3 MiB). Overlap between kernels and copies 0.46 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.30 | 0.00 | 0.00 | 0.00 | 0% | 0.30 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2992 | 0.45 |
| setup | 1.81 | 0.00 | 0.00 | 0.00 | 0% | 1.81 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.61 |
| read gain | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 101.05 |
| session and device ingest | 90.07 | 39.36 | 28.87 | 10.58 | 44% | 50.67 | 59 | 12 | 27 | 0.97 | 5/0 | 130.7 | 18 | 2932 | 399.79 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.29 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 28.59 | 0.31 | 0.30 | 0.01 | 1% | 28.28 | 12 | 6 | 10 | 1.27 | 6/6 | 0.0 | 4 | 2933 | 76.89 |
| fix defects | 2.70 | 0.02 | 0.01 | 0.01 | 1% | 2.68 | 10 | 2 | 9 | 0.76 | 3/3 | 0.0 | 7 | 2932 | 4.22 |
| release preprocessing | 0.41 | 0.00 | 0.00 | 0.00 | 0% | 0.41 | 1 | 0 | 2 | 0.34 | 0/1 | 0.0 | 0 | 2932 | 0.35 |
| global fft | 22.10 | 21.58 | 21.58 | 0.00 | 98% | 0.51 | 170 | 169 | 1 | 0.13 | 0/0 | 0.0 | 0 | 2877 | 22.38 |
| power spectrum | 0.09 | 0.00 | 0.00 | 0.00 | 0% | 0.09 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.10 |
| global alignment | 15.95 | 7.13 | 7.11 | 0.02 | 45% | 8.86 | 34 | 19 | 24 | 2.76 | 9/9 | 0.0 | 14 | 3143 | 15.14 |
| allocate reconstruction | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.03 |
| global ifft | 22.34 | 21.83 | 20.06 | 1.77 | 98% | 0.40 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.32 |
| patch alignment | 70.91 | 25.14 | 24.85 | 0.28 | 35% | 45.94 | 669 | 456 | 242 | 13.86 | 19/4 | 0.0 | 210 | 3044 | 74.97 |
| fit polynomial | 2.32 | 0.00 | 0.00 | 0.00 | 0% | 2.32 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2992 | 2.55 |
| release alignment | 1.91 | 0.00 | 0.00 | 0.00 | 0% | 1.91 | 1 | 0 | 9 | 1.12 | 0/9 | 0.0 | 0 | 2992 | 2.05 |
| dose weighting | 44.71 | 35.37 | 26.95 | 8.42 | 79% | 9.15 | 221 | 217 | 5 | 1.10 | 1/1 | 54.3 | 2 | 3117 | 111.01 |
| movie teardown | 9.29 | 0.00 | 0.00 | 0.00 | 0% | 9.29 | 1 | 0 | 11 | 5.15 | 0/10 | 0.0 | 0 | 2982 | 10.35 |
| submit model and plot | 0.15 | 0.00 | 0.00 | 0.00 | 0% | 0.15 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.32 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.73 | 0.00 | 4.73 | 0 | 0/0 |
| between movies | 8.37 | 0.00 | 8.37 | 0 | 0/0 |
| after last movie | 920.94 | 0.00 | 920.94 | 0 | 0/3 |

Device 0 allocation high-water 3143 MiB at stage `global alignment` (movie 1); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1021.63 | 176.6 | 240.1 | 32.9% |
| inflate_kernel | 96 | 585.75 | 6101.6 | 6217.9 | 18.9% |
| regular_fft_factor | 5784 | 433.20 | 74.9 | 84.7 | 13.9% |
| fourierShiftKernel | 1277 | 215.59 | 168.8 | 1769.6 | 6.9% |
| regular_bluestein_fft | 600 | 185.23 | 308.7 | 317.3 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.17 | 175.6 | 180.9 | 3.3% |
| postprocess_kernel | 1176 | 79.11 | 67.3 | 74.3 | 2.5% |
| scaleComplexKernel | 624 | 79.02 | 126.6 | 1670.6 | 2.5% |
| preprocess_kernel | 1152 | 75.25 | 65.3 | 68.5 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.28 | 103.8 | 110.5 | 2.0% |
| applyDoseWeightKernel | 576 | 60.22 | 104.5 | 107.4 | 1.9% |
| adler32StripsKernel | 96 | 54.75 | 570.3 | 581.7 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.43 | 525.3 | 542.2 | 1.6% |
| regular_fft | 1301 | 27.11 | 20.8 | 234.1 | 0.9% |
| regular_fft_c2r | 1277 | 22.99 | 18.0 | 182.4 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 6623 | 1096.40 | 353.52 |
| device sync | 192 | 578.74 | 15.15 |
| free (implicit sync) | 1036 | 319.47 | 319.47 |
| event sync | 816 | 270.14 | 41.69 |
| stream sync | 120 | 21.36 | 7.00 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.38 | 774.50 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 251.38 | 12.84 |
| Device-to-Host Device->Pageable | 2698 | 1304.0 | 228.42 | 5.99 |
| Host-to-Device Pageable->Device | 3445 | 65.5 | 13.20 | 5.21 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.78 | 12.72 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `rc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 7795.9 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3583.0 ms (46.0%); idle 4212.9 ms. Kernels 25206 (3106.9 ms summed), copies 3247 (506.8 ms, 35784.3 MiB). Overlap between kernels and copies 30.58 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.27 |
| setup | 1.52 | 0.00 | 0.00 | 0.00 | 0% | 1.52 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.48 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 109.50 |
| session and device ingest | 74.93 | 39.14 | 28.93 | 11.41 | 52% | 35.71 | 54 | 12 | 27 | 0.87 | 5/0 | 130.7 | 18 | 2932 | 369.31 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.34 |
| hot pixels | 19.51 | 0.32 | 0.31 | 0.01 | 2% | 19.17 | 12 | 6 | 10 | 1.43 | 6/6 | 0.0 | 4 | 2933 | 76.51 |
| fix defects | 2.19 | 0.02 | 0.01 | 0.01 | 1% | 2.17 | 10 | 2 | 9 | 0.66 | 3/3 | 0.0 | 7 | 2932 | 4.35 |
| release preprocessing | 0.34 | 0.00 | 0.00 | 0.00 | 0% | 0.34 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.34 |
| global fft | 22.07 | 21.57 | 21.57 | 0.00 | 98% | 0.49 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 22.12 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 14.20 | 7.13 | 7.12 | 0.02 | 50% | 7.11 | 34 | 19 | 24 | 2.16 | 9/9 | 0.0 | 14 | 3143 | 13.48 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.33 | 21.83 | 20.06 | 1.77 | 98% | 0.49 | 193 | 168 | 25 | 0.21 | 0/0 | 1304.3 | 0 | 2877 | 22.28 |
| patch alignment | 46.84 | 24.94 | 24.89 | 0.05 | 53% | 21.76 | 497 | 456 | 51 | 2.36 | 17/3 | 0.0 | 38 | 3221 | 49.35 |
| fit polynomial | 1.68 | 0.00 | 0.00 | 0.00 | 0% | 1.68 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.81 |
| release alignment | 1.72 | 0.00 | 0.00 | 0.00 | 0% | 1.72 | 1 | 0 | 8 | 1.21 | 0/8 | 0.0 | 0 | 3221 | 1.86 |
| dose weighting | 42.76 | 34.30 | 26.89 | 7.35 | 80% | 8.28 | 221 | 217 | 5 | 0.86 | 1/1 | 54.3 | 2 | 3117 | 85.00 |
| movie teardown | 7.63 | 0.00 | 0.00 | 0.00 | 0% | 7.63 | 1 | 0 | 11 | 4.14 | 0/10 | 0.0 | 0 | 2982 | 8.15 |
| submit model and plot | 0.14 | 0.00 | 0.00 | 0.00 | 0% | 0.14 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.15 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.03 | 0.00 | 5.03 | 0 | 0/0 |
| between movies | 5.23 | 0.00 | 5.23 | 0 | 0/0 |
| after last movie | 970.05 | 0.00 | 970.05 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1020.23 | 176.4 | 239.3 | 32.8% |
| inflate_kernel | 96 | 586.35 | 6107.8 | 6226.7 | 18.9% |
| regular_fft_factor | 5784 | 433.49 | 74.9 | 84.6 | 14.0% |
| fourierShiftKernel | 1277 | 214.99 | 168.4 | 1771.1 | 6.9% |
| regular_bluestein_fft | 600 | 184.81 | 308.0 | 315.6 | 5.9% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.04 | 175.4 | 183.1 | 3.3% |
| postprocess_kernel | 1176 | 79.71 | 67.8 | 74.8 | 2.6% |
| scaleComplexKernel | 624 | 79.07 | 126.7 | 1669.9 | 2.5% |
| preprocess_kernel | 1152 | 75.36 | 65.4 | 69.7 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.66 | 104.4 | 115.0 | 2.0% |
| applyDoseWeightKernel | 576 | 60.17 | 104.5 | 107.6 | 1.9% |
| adler32StripsKernel | 96 | 55.16 | 574.6 | 582.6 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.82 | 529.4 | 550.8 | 1.6% |
| regular_fft | 1301 | 26.97 | 20.7 | 230.9 | 0.9% |
| regular_fft_c2r | 1277 | 22.90 | 17.9 | 182.0 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 940.46 | 97.94 |
| device sync | 192 | 649.93 | 14.30 |
| event sync | 384 | 298.30 | 24.51 |
| free (implicit sync) | 988 | 273.95 | 273.95 |
| stream sync | 120 | 22.64 | 5.80 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.46 | 773.10 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 267.85 | 12.05 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 183.66 | 7.45 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 9.85 | 6.98 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.97 | 11.90 |

Byte counts are invariant across captures; rates are not (contention, tracing).
