# MotionCorr compare: default vs fast

## Provenance

- kit: `None`
- arm `default`: `/home/alex/mc-fft/arms/default.sh` sha256 `03c0a46dcebcafc0`; source `7d6404349d4ba8e4b749f979ac28d49099446b06` dirty (git in /home/alex/mc-fft/src); --profile present
- arm `fast`: `/home/alex/mc-fft/arms/fast.sh` sha256 `47cf0f458a8b4896`; source `7d6404349d4ba8e4b749f979ac28d49099446b06` dirty (git in /home/alex/mc-fft/src); --profile present
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 80-87, load1 15.2, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 562 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.4}
- rounds: 18 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `default` on, `fast` on
- CUDA device timing in trace passes: `default` off, `fast` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `kit/profiling/mcprof.py compare default=/home/alex/mc-fft/arms/default.sh fast=/home/alex/mc-fft/arms/fast.sh --data /home/alex/mc-perf-20261001/data --star movies.star --cpus 80-87 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --runner-cpus 119 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --allow-product-difference --work /home/alex/mc-fft/kit24run --source default=/home/alex/mc-fft/src --source fast=/home/alex/mc-fft/src -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## PRODUCTS DIFFER

`fast` does not produce the baseline's products (see Product identity). Every verdict for it is speed only, products differ: it compares wall time only and says nothing about whether the products are acceptable.

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| default | 12 | 7.186 | 0.309 | 6.716-8.092 | 19.479 | 368 | 150540 | 18 | 3362 | 3371 |
| fast | 12 | 6.131 | 0.511 | 5.993-7.359 | 18.129 | 363 | 127706 | 17 | 3372 | 3381 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `default`: load1 13.7-18.8, max foreign CPU on lane 0.25 cores, wall outlier rounds [5]
- `fast`: load1 13.9-20.8, max foreign CPU on lane 0.13 cores, wall outlier rounds [3, 5, 8]

Rounds: 18 planned, 12 retained, 6 discarded (a discard removes the whole round, every arm). Discards triggered by: `default` 4 (alone 3), `fast` 3 (alone 2). Kept orders: AB 6, BA 6.

Discarded rounds:
- round 4 (BA): default: foreign CPU on lane 1.02 cores
- round 7 (AB): default: foreign CPU on lane 0.34 cores | fast: foreign CPU on lane 0.28 cores
- round 10 (BA): default: foreign CPU on lane 0.32 cores
- round 11 (AB): default: foreign CPU on lane 0.50 cores
- round 14 (BA): fast: foreign CPU on lane 0.45 cores
- round 17 (AB): fast: foreign CPU on lane 0.26 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 2 s, r5 480 s, r6 1 s, r7 1 s, r8 3 s, r9 1 s, r10 2 s, r11 3 s, r12 1 s, r13 1 s, r14 1 s, r15 1 s, r16 3 s, r17 3 s, r18 5 s.

### `fast` vs `default`: **speed only, products differ: resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -0.904 | -1.124..-0.707 | -1.361..+0.265 | -1.203..-0.626 (96.1%) | 0.349 | 2+/10- p=0.0386 | -12.58% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `fast` is slower.
Positional: median B-A when `fast` ran second -0.920 s (n=6), first -0.904 s (n=6); cost of running second -0.008 s.
Paired differences (s): -1.203, -1.249, +0.183, -0.734, -0.953, +0.265, -1.097, -0.626, -1.082, -0.758, -0.855, -1.361

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fast | FAIL | 81 | 24 | 28 | 79 file(s) differ |
- `fast` Movies/20170629_00021_frameImage.mrc: core header differs at byte 76
- `fast` Movies/20170629_00021_frameImage.star: differs after root normalisation (sha256 04810f874f47 vs 4dd73a726c1d)
- `fast` Movies/20170629_00021_frameImage_shifts.eps: differs after root normalisation (sha256 1b3ac147a167 vs 32be7e66f67a)
- `fast` Movies/20170629_00022_frameImage.mrc: core header differs at byte 76
- `fast` Movies/20170629_00022_frameImage.star: differs after root normalisation (sha256 66117779deaf vs c6aff0610b8b)
- `fast` Movies/20170629_00022_frameImage_shifts.eps: differs after root normalisation (sha256 8532d8470840 vs 63aa9531ff28)
- `fast` Movies/20170629_00023_frameImage.mrc: core header differs at byte 76
- `fast` Movies/20170629_00023_frameImage.star: differs after root normalisation (sha256 2cefbc8f6c20 vs 111b7b913f4b)
- `fast` Movies/20170629_00023_frameImage_shifts.eps: differs after root normalisation (sha256 4d3fafd0c2ed vs 6d9380f93e04)
- `fast` Movies/20170629_00024_frameImage.mrc: core header differs at byte 76

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `default` 3, `fast` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `fast` vs `default`

Movie wall (steady median): 227.9 -> 191.1 ms (-36.89)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.51 | 1.48 | -0.03 | 0.50 | -0.04 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 74.60 | 76.44 | +1.84 | 42.57 | +1.73 | -13 |
| host read movie | 0.04 | 0.04 | +0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | +0.00 | +0 |
| hot pixels | 20.74 | 15.26 | -5.47 | 22.71 | -5.40 | +0 |
| **fix defects** | 1.22 | 0.48 | -0.74 * | 0.58 | -0.72 * | -1 |
| **release preprocessing** | 0.24 | 1.89 | +1.65 * | 0.50 | +1.65 * | +0 |
| **global fft** | 21.79 | 13.97 | -7.82 * | 0.50 | -7.83 * | +0 |
| power spectrum | 0.05 | 0.05 | +0.00 | 0.50 | +0.00 | +0 |
| global alignment | 8.81 | 9.46 | +0.66 | 0.66 | +0.66 | +0 |
| allocate reconstruction | 0.01 | 0.01 | +0.00 | 0.50 | +0.00 | +0 |
| **global ifft** | 21.99 | 14.90 | -7.09 * | 0.50 | -7.08 * | +0 |
| **patch alignment** | 26.70 | 16.39 | -10.31 * | 1.00 | -10.30 * | +0 |
| fit polynomial | 1.64 | 1.67 | +0.03 | 0.50 | +0.04 | +0 |
| release alignment | 1.68 | 1.41 | -0.27 | 0.50 | -0.28 | +0 |
| **dose weighting** | 41.76 | 32.74 | -9.02 * | 4.62 | -9.02 * | -1 |
| movie teardown | 4.09 | 3.95 | -0.14 | 2.51 | -0.15 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `default` 2, `fast` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `fast` vs `default`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +85.79 | +0.00 | +85.79 | 2713.98 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | +0.07 | +0.00 | +0.07 | 1.85 | +0 | +0 | +0.0 | +0 |
| setup | +0.20 | +0.00 | +0.20 | 3.36 | +0 | +0 | +0.0 | +0 |
| read gain | +0.01 | +0.00 | +0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| **session and device ingest** | +3.95 | -0.11 | +3.88 | 95.44 | +0 | -12 * | -0.0 * | +2 * |
| host read movie | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **hot pixels** | +0.78 | -0.01 | +0.80 | 94.85 | +0 | +0 | +0.0 | +0 |
| fix defects | -0.64 | -0.00 | -0.64 | 1.61 | +0 | +0 | +0.0 | +0 |
| **release preprocessing** | +1.66 * | +0.00 | +1.66 * | 1.27 | +0 | +0 | +0.0 | +0 |
| **global fft** | -7.84 * | -7.68 * | -0.13 | 0.79 | -70 * | +0 | +0.0 | +0 |
| power spectrum | +0.02 | +0.00 | +0.02 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global alignment** | +0.76 | +0.57 * | +0.21 | 5.08 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | +0.00 | +0.00 | +0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global ifft** | -6.97 * | -6.99 * | +0.00 | 1.72 | -48 * | +0 | +14.7 * | +0 |
| **patch alignment** | -11.34 | -8.04 * | -3.23 | 19.93 | -53 * | -10 * | -0.0 * | -5 * |
| fit polynomial | +0.03 | +0.00 | +0.03 | 1.22 | +0 | +0 | +0.0 | +0 |
| **release alignment** | -0.49 | +0.00 | -0.49 | 1.31 | +0 | -2 * | +0.0 | +0 |
| **dose weighting** | -8.39 | -8.56 | +0.06 | 21.94 | -72 * | +0 | +0.0 | +0 |
| **movie teardown** | +0.15 | +0.00 | +0.15 | 14.16 | +0 | +2 * | +0.0 | +0 |
| submit model and plot | +0.02 | +0.00 | +0.02 | 0.50 | +0 | +0 | +0.0 | +0 |
| between movies | +0.78 | +0.00 | +0.78 | 16.17 | +0 | +0 | +0.0 | +0 |
| **after last movie** | +110.45 | +0.00 | +110.45 | 2932.80 | +0 | -1 * | +0.0 | +0 |

Traced device allocation high-water per pass: base 3026, 3026 MiB, arm 3040, 3040 MiB.

## Device: `default` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 7817.0 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3442.7 ms (44.0%); idle 4374.2 ms. Kernels 25206 (2987.7 ms summed), copies 3247 (469.9 ms, 35784.3 MiB). Overlap between kernels and copies 15.60 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.26 | 0.00 | 0.00 | 0.00 | 0% | 0.26 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.26 |
| setup | 1.52 | 0.00 | 0.00 | 0.00 | 0% | 1.52 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.52 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 108.59 |
| session and device ingest | 84.00 | 38.89 | 28.89 | 10.47 | 46% | 45.28 | 59 | 12 | 27 | 0.96 | 5/0 | 130.7 | 18 | 2932 | 383.97 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 19.04 | 0.32 | 0.31 | 0.01 | 2% | 18.71 | 12 | 6 | 10 | 1.21 | 6/6 | 0.0 | 4 | 2933 | 73.06 |
| fix defects | 2.23 | 0.02 | 0.01 | 0.01 | 1% | 2.20 | 10 | 2 | 9 | 0.66 | 3/3 | 0.0 | 7 | 2932 | 4.60 |
| release preprocessing | 0.34 | 0.00 | 0.00 | 0.00 | 0% | 0.34 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.35 |
| global fft | 22.09 | 21.59 | 21.59 | 0.00 | 98% | 0.47 | 170 | 169 | 1 | 0.14 | 0/0 | 0.0 | 0 | 2877 | 21.94 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 10.99 | 7.12 | 7.10 | 0.02 | 65% | 3.88 | 34 | 19 | 15 | 0.63 | 0/0 | 0.0 | 14 | 2877 | 8.68 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.18 | 21.79 | 20.03 | 1.75 | 98% | 0.40 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.15 |
| patch alignment | 44.29 | 19.96 | 19.90 | 0.05 | 45% | 24.19 | 497 | 456 | 51 | 2.20 | 17/3 | 0.0 | 38 | 3026 | 44.53 |
| fit polynomial | 1.71 | 0.00 | 0.00 | 0.00 | 0% | 1.71 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.74 |
| release alignment | 3.22 | 0.00 | 0.00 | 0.00 | 0% | 3.22 | 1 | 0 | 15 | 2.00 | 0/14 | 0.0 | 0 | 3026 | 3.52 |
| dose weighting | 40.60 | 33.22 | 27.04 | 6.15 | 82% | 7.34 | 221 | 217 | 4 | 0.46 | 0/0 | 54.3 | 2 | 2877 | 93.42 |
| movie teardown | 5.95 | 0.00 | 0.00 | 0.00 | 0% | 5.95 | 1 | 0 | 5 | 3.48 | 0/4 | 0.0 | 0 | 2877 | 6.76 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.16 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.60 | 0.00 | 4.60 | 0 | 0/0 |
| between movies | 4.47 | 0.00 | 4.47 | 0 | 0/0 |
| after last movie | 903.74 | 0.00 | 903.74 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1023.39 | 176.9 | 237.4 | 34.3% |
| inflate_kernel | 96 | 586.75 | 6112.0 | 6228.1 | 19.6% |
| regular_fft_factor | 5784 | 433.01 | 74.9 | 84.6 | 14.5% |
| regular_bluestein_fft | 600 | 185.78 | 309.6 | 317.9 | 6.2% |
| fourierShiftKernel | 1277 | 130.14 | 101.9 | 1773.7 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.24 | 175.8 | 182.3 | 3.4% |
| postprocess_kernel | 1176 | 79.15 | 67.3 | 73.8 | 2.6% |
| preprocess_kernel | 1152 | 74.53 | 64.7 | 67.2 | 2.5% |
| cropAndGroupPatchResidentKernel | 600 | 62.30 | 103.8 | 111.3 | 2.1% |
| applyDoseWeightKernel | 576 | 60.32 | 104.7 | 107.3 | 2.0% |
| adler32StripsKernel | 96 | 54.97 | 572.6 | 582.7 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.35 | 524.5 | 555.3 | 1.7% |
| scaleComplexKernel | 24 | 40.05 | 1668.8 | 1671.1 | 1.3% |
| regular_fft | 1301 | 27.10 | 20.8 | 236.8 | 0.9% |
| regular_fft_c2r | 1277 | 22.98 | 18.0 | 181.8 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 897.36 | 95.30 |
| device sync | 216 | 658.88 | 15.78 |
| event sync | 384 | 258.26 | 12.71 |
| free (implicit sync) | 748 | 218.03 | 218.03 |
| stream sync | 120 | 22.05 | 6.67 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 42.10 | 779.59 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 242.48 | 13.31 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 172.08 | 7.95 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 11.05 | 6.22 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.22 | 15.92 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `fast` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 7209.7 ms, 24 movies. Device busy (union of kernels, copies, memsets) 2666.7 ms (37.0%); idle 4543.0 ms. Kernels 19374 (2241.6 ms summed), copies 2862 (436.8 ms, 36134.2 MiB). Overlap between kernels and copies 12.30 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.39 | 0.00 | 0.00 | 0.00 | 0% | 0.39 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3040 | 0.27 |
| setup | 1.78 | 0.00 | 0.00 | 0.00 | 0% | 1.78 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 1.73 |
| read gain | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 101.46 |
| session and device ingest | 85.95 | 38.59 | 28.77 | 10.11 | 45% | 47.27 | 47 | 12 | 15 | 0.50 | 7/0 | 130.7 | 6 | 2944 | 366.43 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.07 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.07 |
| hot pixels | 23.07 | 0.31 | 0.30 | 0.01 | 1% | 22.76 | 12 | 6 | 10 | 0.47 | 6/6 | 0.0 | 4 | 2945 | 69.51 |
| fix defects | 1.51 | 0.02 | 0.01 | 0.01 | 1% | 1.49 | 10 | 2 | 9 | 0.34 | 3/3 | 0.0 | 7 | 2944 | 3.16 |
| release preprocessing | 2.05 | 0.00 | 0.00 | 0.00 | 0% | 2.05 | 1 | 0 | 2 | 1.99 | 0/1 | 0.0 | 0 | 2944 | 0.50 |
| global fft | 14.24 | 13.92 | 13.92 | 0.00 | 98% | 0.32 | 100 | 99 | 1 | 0.10 | 0/0 | 0.0 | 0 | 2889 | 14.40 |
| power spectrum | 0.10 | 0.00 | 0.00 | 0.00 | 0% | 0.10 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2889 | 0.09 |
| global alignment | 11.56 | 7.69 | 7.67 | 0.02 | 67% | 3.90 | 34 | 19 | 15 | 0.73 | 0/0 | 0.0 | 14 | 2889 | 8.87 |
| allocate reconstruction | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2889 | 0.02 |
| global ifft | 15.26 | 14.79 | 13.10 | 1.68 | 97% | 0.48 | 145 | 120 | 25 | 0.17 | 0/0 | 1319.1 | 0 | 2889 | 15.11 |
| patch alignment | 32.23 | 11.86 | 11.81 | 0.05 | 37% | 20.38 | 438 | 403 | 41 | 1.82 | 12/0 | 0.0 | 34 | 3040 | 31.16 |
| fit polynomial | 1.69 | 0.00 | 0.00 | 0.00 | 0% | 1.69 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3040 | 1.71 |
| release alignment | 2.79 | 0.00 | 0.00 | 0.00 | 0% | 2.79 | 1 | 0 | 13 | 2.02 | 0/12 | 0.0 | 0 | 3040 | 2.49 |
| dose weighting | 31.73 | 24.42 | 18.25 | 6.15 | 77% | 7.13 | 149 | 145 | 4 | 0.40 | 0/0 | 54.3 | 2 | 2889 | 63.01 |
| movie teardown | 6.57 | 0.00 | 0.00 | 0.00 | 0% | 6.57 | 1 | 0 | 7 | 4.53 | 0/6 | 0.0 | 0 | 2889 | 5.38 |
| submit model and plot | 0.16 | 0.00 | 0.00 | 0.00 | 0% | 0.16 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 0.13 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.55 | 0.00 | 4.55 | 0 | 0/0 |
| between movies | 5.90 | 0.00 | 5.90 | 0 | 0/0 |
| after last movie | 1128.28 | 0.00 | 1128.28 | 0 | 0/2 |

Device 0 allocation high-water 3040 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| inflate_kernel | 96 | 583.06 | 6073.6 | 6152.0 | 26.0% |
| regular_fft | 3605 | 510.62 | 141.6 | 239.5 | 22.8% |
| fourierShiftKernel | 1277 | 142.21 | 111.4 | 1958.6 | 6.3% |
| vector_fft | 1728 | 134.76 | 78.0 | 84.4 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.95 | 177.0 | 185.1 | 4.5% |
| kernel_wrapper | 1152 | 88.71 | 77.0 | 82.3 | 4.0% |
| preprocess_kernel | 1152 | 79.81 | 69.3 | 72.8 | 3.6% |
| regular_fft_r2c | 600 | 65.30 | 108.8 | 109.8 | 2.9% |
| cropGroupPadPatchKernel | 600 | 62.86 | 104.8 | 113.7 | 2.8% |
| applyDoseWeightKernel | 576 | 62.18 | 108.0 | 113.8 | 2.8% |
| adler32StripsKernel | 96 | 54.68 | 569.6 | 578.1 | 2.4% |
| cropFrameKernel | 576 | 50.41 | 87.5 | 98.2 | 2.2% |
| fusedU16FlipGainAndSumKernel | 96 | 50.18 | 522.7 | 554.7 | 2.2% |
| padFrameKernel | 576 | 49.87 | 86.6 | 87.4 | 2.2% |
| postprocess_kernel | 576 | 43.60 | 75.7 | 80.9 | 1.9% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2094 | 641.27 | 83.69 |
| device sync | 144 | 400.38 | 12.01 |
| free (implicit sync) | 675 | 252.92 | 252.92 |
| event sync | 384 | 248.94 | 10.40 |
| stream sync | 120 | 21.03 | 7.02 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31657.5 | 40.42 | 821.27 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 236.16 | 13.66 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 149.95 | 9.12 |
| Host-to-Device Pageable->Device | 988 | 61.7 | 8.30 | 7.79 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 1.98 | 17.85 |

Byte counts are invariant across captures; rates are not (contention, tracing).
