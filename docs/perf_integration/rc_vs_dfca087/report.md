# MotionCorr compare: abc vs rc

## Provenance

- kit: `d873993522986893eb2a7d6346828a53771d35ed`
- arm `abc`: `/home/alex/mc-prof-abc/build-ABC/motioncorr` sha256 `b94e835e6cec8ade`; source `dfca08767d300a39ef3fb522e0f9cf20fa30a163` (git in /home/alex/mc-prof-abc/src-ABC); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- arm `rc`: `/home/alex/mc-rc/build-rc/motioncorr` sha256 `ff1bc2679a040bc9`; source `c0f82c2d65bcfc6c68042313d22c1fe132c1a306` (git in /home/alex/mc-rc/src-rc); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 17.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- rounds: 13 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `abc` on, `rc` on
- CUDA device timing in trace passes: `abc` on (binary has no --profile_device_timing), `rc` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-rc/src-kit/tools/profiling/mcprof.py compare abc=/home/alex/mc-prof-abc/build-ABC/motioncorr rc=/home/alex/mc-rc/build-rc/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --work /home/alex/mc-rc/camp/rc_vs_dfca087 --source abc=/home/alex/mc-prof-abc/src-ABC --source rc=/home/alex/mc-rc/src-rc -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| abc | 12 | 7.303 | 1.042 | 6.874-8.383 | 18.467 | 441 | 125793 | 17 | 3558 | 3567 |
| rc | 12 | 7.182 | 0.600 | 6.955-8.258 | 18.102 | 368 | 150312 | 14 | 3558 | 3567 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `abc`: load1 15.5-18.1, max foreign CPU on lane 0.21 cores, wall outlier rounds none
- `rc`: load1 15.4-18.0, max foreign CPU on lane 0.16 cores, wall outlier rounds [3, 6, 11]

Rounds: 13 planned, 12 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `abc` 0 (alone 0), `rc` 1 (alone 1). Kept orders: AB 7, BA 5.

WARNING: kept pairs are unbalanced by order (AB 7, BA 5): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 10 (BA): rc: foreign CPU on lane 0.29 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 3 s, r5 1 s, r6 4 s, r7 1 s, r8 1 s, r9 1 s, r10 1 s, r11 1 s, r12 1 s, r13 1 s.

### `rc` vs `abc`: **not resolved (below noise 1.271 s)**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.193 | -0.942..+0.804 | -1.270..+1.247 | -0.972..+0.990 (96.1%) | 1.271 | 5+/7- p=0.774 | -2.64% |

Reason: CI of median includes 0. Positive differences mean `rc` is slower.
Positional: median B-A when `rc` ran second -0.005 s (n=7), first -0.380 s (n=5); cost of running second +0.188 s.
Paired differences (s): -1.243, -0.844, +1.120, +0.196, -0.972, +1.247, +0.742, -1.270, -0.932, +0.990, -0.380, -0.005

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| rc | PASS | 81 | 24 | 28 | - |

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `abc` 3, `rc` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `abc`

Movie wall (steady median): 237.8 -> 236.0 ms (-1.71)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.41 | 1.53 | +0.13 | 0.50 | +0.11 | +0 |
| read gain | 0.04 | 0.04 | +0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 68.64 | 69.55 | +0.91 | 37.49 | +0.67 | +13 |
| host read movie | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| gain and sum | 0.04 | 0.04 | +0.00 | 0.50 | +0.00 | +0 |
| hot pixels | 21.73 | 20.23 | -1.50 | 12.31 | -1.91 | +0 |
| fix defects | 1.78 | 1.69 | -0.10 | 1.74 | -0.13 | +0 |
| release preprocessing | 0.24 | 0.25 | +0.01 | 0.50 | +0.01 | +0 |
| global fft | 21.91 | 21.91 | +0.00 | 0.50 | -0.01 | +0 |
| power spectrum | 0.07 | 0.06 | -0.01 | 0.50 | -0.01 | +0 |
| global alignment | 11.90 | 12.04 | +0.14 | 1.48 | +0.15 | +0 |
| allocate reconstruction | 0.02 | 0.01 | -0.01 | 0.50 | -0.01 | +0 |
| global ifft | 22.08 | 22.07 | -0.00 | 0.50 | -0.01 | +0 |
| patch alignment | 33.09 | 33.04 | -0.05 | 3.47 | -0.05 | +0 |
| fit polynomial | 1.71 | 1.69 | -0.02 | 0.50 | -0.01 | +0 |
| release alignment | 1.17 | 1.11 | -0.07 | 0.76 | -0.07 | +0 |
| dose weighting | 45.08 | 45.60 | +0.52 | 2.68 | +0.57 | +1 |
| movie teardown | 4.51 | 4.88 | +0.37 | 2.71 | +0.29 | +0 |
| submit model and plot | 0.08 | 0.08 | +0.00 | 0.50 | +0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `abc` 2, `rc` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `rc` vs `abc`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +0.14 | +0.00 | +0.14 | 8.45 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | +0.01 | +0.00 | +0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| setup | +0.02 | +0.00 | +0.02 | 3.69 | +0 | +0 | +0.0 | +0 |
| read gain | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| session and device ingest | -4.10 | -0.06 | -3.66 | 116.18 | +0 | +0 | +0.0 | +0 |
| host read movie | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | +0.45 | +0.00 | +0.45 | 12.80 | +0 | +0 | +0.0 | +0 |
| fix defects | +0.07 | +0.00 | +0.07 | 1.00 | +0 | +0 | +0.0 | +0 |
| release preprocessing | -0.08 | +0.00 | -0.08 | 2.50 | +0 | +0 | +0.0 | +0 |
| global fft | +0.02 | +0.00 | +0.01 | 0.82 | +0 | +0 | +0.0 | +0 |
| power spectrum | +0.01 | +0.00 | +0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global alignment** | -2.10 | +0.02 | -2.09 | 8.34 | +0 | -15 * | +0.0 | +0 |
| allocate reconstruction | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| global ifft | +0.09 | -0.00 | +0.12 | 0.50 | +0 | +0 | +0.0 | +0 |
| patch alignment | +0.67 | +0.08 | +0.74 | 29.26 | +0 | +0 | +0.0 | +0 |
| fit polynomial | +0.01 | +0.00 | +0.01 | 0.81 | +0 | +0 | +0.0 | +0 |
| release alignment | +0.21 | +0.00 | +0.21 | 3.17 | +0 | +0 | +0.0 | +0 |
| **dose weighting** | -9.50 * | +0.26 | -9.86 * | 5.96 | +0 | -72 * | +0.0 | +0 |
| movie teardown | -0.04 | +0.00 | -0.04 | 5.09 | +0 | +0 | +0.0 | +0 |
| submit model and plot | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | +0.11 | +0.00 | +0.11 | 10.98 | +0 | +0 | +0.0 | +0 |
| after last movie | +12.80 | +0.00 | +12.80 | 1241.39 | +0 | +0 | +0.0 | +0 |

Traced device allocation high-water per pass: base 3221, 3221 MiB, arm 3221, 3221 MiB.

## Device: `abc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: on (binary has no --profile_device_timing).

Traced window 8703.5 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3613.0 ms (41.5%); idle 5090.5 ms. Kernels 25206 (3099.4 ms summed), copies 3247 (525.9 ms, 35784.3 MiB). Overlap between kernels and copies 12.88 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.26 | 0.00 | 0.00 | 0.00 | 0% | 0.26 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.27 |
| setup | 1.38 | 0.00 | 0.00 | 0.00 | 0% | 1.38 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.77 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 90.95 |
| session and device ingest | 85.94 | 39.22 | 28.81 | 10.57 | 46% | 46.73 | 59 | 12 | 27 | 0.81 | 5/0 | 130.7 | 18 | 2932 | 923.13 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.08 |
| hot pixels | 19.02 | 0.31 | 0.30 | 0.01 | 2% | 18.71 | 12 | 6 | 10 | 1.36 | 6/6 | 0.0 | 4 | 2933 | 66.34 |
| fix defects | 2.17 | 0.02 | 0.01 | 0.01 | 1% | 2.15 | 10 | 2 | 9 | 0.62 | 3/3 | 0.0 | 7 | 2932 | 2.37 |
| release preprocessing | 0.34 | 0.00 | 0.00 | 0.00 | 0% | 0.34 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.34 |
| global fft | 22.01 | 21.57 | 21.57 | 0.00 | 98% | 0.41 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 22.20 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.09 |
| global alignment | 16.53 | 7.12 | 7.10 | 0.02 | 43% | 9.40 | 34 | 19 | 39 | 2.72 | 9/9 | 0.0 | 14 | 3143 | 13.64 |
| allocate reconstruction | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.06 |
| global ifft | 22.24 | 21.83 | 20.06 | 1.77 | 98% | 0.42 | 193 | 168 | 25 | 0.21 | 0/0 | 1304.3 | 0 | 2877 | 22.40 |
| patch alignment | 46.04 | 24.97 | 24.91 | 0.05 | 54% | 20.87 | 497 | 456 | 51 | 2.30 | 17/3 | 0.0 | 38 | 3221 | 48.23 |
| fit polynomial | 1.71 | 0.00 | 0.00 | 0.00 | 0% | 1.71 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 1.71 |
| release alignment | 1.55 | 0.00 | 0.00 | 0.00 | 0% | 1.55 | 1 | 0 | 8 | 1.19 | 0/8 | 0.0 | 0 | 3221 | 1.53 |
| dose weighting | 52.33 | 34.31 | 26.77 | 7.60 | 66% | 18.04 | 221 | 217 | 77 | 4.08 | 1/1 | 54.3 | 2 | 3117 | 86.31 |
| movie teardown | 7.41 | 0.00 | 0.00 | 0.00 | 0% | 7.41 | 1 | 0 | 11 | 4.14 | 0/10 | 0.0 | 0 | 2982 | 7.39 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.13 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.53 | 0.00 | 4.53 | 0 | 0/0 |
| between movies | 4.79 | 0.00 | 4.79 | 0 | 0/0 |
| after last movie | 895.27 | 0.00 | 895.27 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1020.98 | 176.5 | 238.3 | 32.9% |
| inflate_kernel | 96 | 583.14 | 6074.4 | 6136.9 | 18.8% |
| regular_fft_factor | 5784 | 428.27 | 74.0 | 85.0 | 13.8% |
| fourierShiftKernel | 1277 | 214.97 | 168.3 | 1771.1 | 6.9% |
| regular_bluestein_fft | 600 | 185.47 | 309.1 | 318.1 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.31 | 175.9 | 182.9 | 3.3% |
| postprocess_kernel | 1176 | 79.69 | 67.8 | 74.3 | 2.6% |
| scaleComplexKernel | 624 | 79.07 | 126.7 | 1670.3 | 2.6% |
| preprocess_kernel | 1152 | 75.38 | 65.4 | 70.5 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.80 | 104.7 | 113.5 | 2.0% |
| applyDoseWeightKernel | 576 | 60.31 | 104.7 | 107.5 | 1.9% |
| adler32StripsKernel | 96 | 54.81 | 570.9 | 578.1 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.58 | 526.9 | 549.7 | 1.6% |
| regular_fft | 1301 | 27.04 | 20.8 | 232.6 | 0.9% |
| regular_fft_c2r | 1277 | 22.93 | 18.0 | 183.0 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| event sync | 2457 | 830.42 | 107.19 |
| device sync | 192 | 665.01 | 14.90 |
| synchronous memcpy | 2479 | 484.98 | 90.18 |
| free (implicit sync) | 988 | 257.55 | 257.55 |
| stream sync | 120 | 20.48 | 5.03 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.45 | 773.31 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 256.05 | 12.60 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 194.84 | 7.02 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 29.69 | 2.32 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.91 | 12.17 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `rc` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 8029.8 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3600.0 ms (44.8%); idle 4429.9 ms. Kernels 25206 (3112.8 ms summed), copies 3247 (492.3 ms, 35784.3 MiB). Overlap between kernels and copies 5.76 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.26 |
| setup | 1.56 | 0.00 | 0.00 | 0.00 | 0% | 1.56 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.79 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 100.04 |
| session and device ingest | 86.04 | 39.53 | 28.94 | 11.26 | 46% | 45.95 | 59 | 12 | 27 | 0.87 | 5/0 | 130.7 | 18 | 2932 | 392.68 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 19.78 | 0.31 | 0.30 | 0.01 | 2% | 19.47 | 12 | 6 | 10 | 1.26 | 6/6 | 0.0 | 4 | 2933 | 74.80 |
| fix defects | 2.28 | 0.02 | 0.01 | 0.01 | 1% | 2.26 | 10 | 2 | 9 | 0.63 | 3/3 | 0.0 | 7 | 2932 | 3.71 |
| release preprocessing | 0.34 | 0.00 | 0.00 | 0.00 | 0% | 0.34 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.33 |
| global fft | 22.05 | 21.58 | 21.58 | 0.00 | 98% | 0.44 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 22.14 |
| power spectrum | 0.11 | 0.00 | 0.00 | 0.00 | 0% | 0.11 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.09 |
| global alignment | 14.82 | 7.14 | 7.12 | 0.02 | 48% | 7.68 | 34 | 19 | 24 | 2.24 | 9/9 | 0.0 | 14 | 3143 | 12.53 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.35 | 21.83 | 20.06 | 1.77 | 98% | 0.53 | 193 | 168 | 25 | 0.22 | 0/0 | 1304.3 | 0 | 2877 | 22.21 |
| patch alignment | 47.62 | 25.08 | 25.02 | 0.05 | 53% | 22.68 | 497 | 456 | 51 | 2.55 | 17/3 | 0.0 | 38 | 3221 | 47.91 |
| fit polynomial | 1.75 | 0.00 | 0.00 | 0.00 | 0% | 1.75 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 2.03 |
| release alignment | 1.90 | 0.00 | 0.00 | 0.00 | 0% | 1.90 | 1 | 0 | 8 | 1.44 | 0/8 | 0.0 | 0 | 3221 | 1.78 |
| dose weighting | 42.85 | 34.31 | 27.04 | 7.30 | 80% | 8.40 | 221 | 217 | 5 | 1.01 | 1/1 | 54.3 | 2 | 3117 | 73.50 |
| movie teardown | 7.55 | 0.00 | 0.00 | 0.00 | 0% | 7.55 | 1 | 0 | 11 | 4.23 | 0/10 | 0.0 | 0 | 2982 | 7.47 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.13 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.62 | 0.00 | 4.62 | 0 | 0/0 |
| between movies | 5.27 | 0.00 | 5.27 | 0 | 0/0 |
| after last movie | 962.47 | 0.00 | 962.47 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1022.72 | 176.8 | 240.6 | 32.9% |
| inflate_kernel | 96 | 587.32 | 6117.9 | 6216.6 | 18.9% |
| regular_fft_factor | 5784 | 433.41 | 74.9 | 84.6 | 13.9% |
| fourierShiftKernel | 1277 | 215.24 | 168.5 | 1770.8 | 6.9% |
| regular_bluestein_fft | 600 | 186.46 | 310.8 | 318.8 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.35 | 176.0 | 183.2 | 3.3% |
| postprocess_kernel | 1176 | 79.62 | 67.7 | 74.2 | 2.6% |
| scaleComplexKernel | 624 | 79.08 | 126.7 | 1670.9 | 2.5% |
| preprocess_kernel | 1152 | 75.39 | 65.4 | 68.9 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 63.00 | 105.0 | 116.5 | 2.0% |
| applyDoseWeightKernel | 576 | 60.33 | 104.7 | 107.6 | 1.9% |
| adler32StripsKernel | 96 | 55.05 | 573.5 | 582.7 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.61 | 527.2 | 550.5 | 1.6% |
| regular_fft | 1301 | 27.07 | 20.8 | 231.3 | 0.9% |
| regular_fft_c2r | 1277 | 22.98 | 18.0 | 182.5 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 945.87 | 97.63 |
| device sync | 192 | 656.66 | 16.68 |
| free (implicit sync) | 988 | 282.10 | 282.10 |
| event sync | 384 | 269.34 | 11.77 |
| stream sync | 120 | 21.79 | 6.51 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.42 | 773.85 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 259.00 | 12.46 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 178.18 | 7.67 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 9.94 | 6.92 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.73 | 12.96 |

Byte counts are invariant across captures; rates are not (contention, tracing).
