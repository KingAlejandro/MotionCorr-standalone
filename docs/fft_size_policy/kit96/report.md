# MotionCorr compare: default vs fast

## Provenance

- kit: `None`
- arm `default`: `/home/alex/mc-fft/arms/default.sh` sha256 `03c0a46dcebcafc0`; source `7d6404349d4ba8e4b749f979ac28d49099446b06` dirty (git in /home/alex/mc-fft/src); --profile present
- arm `fast`: `/home/alex/mc-fft/arms/fast.sh` sha256 `47cf0f458a8b4896`; source `7d6404349d4ba8e4b749f979ac28d49099446b06` dirty (git in /home/alex/mc-fft/src); --profile present
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 80-87, load1 22.0, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 34 s), /tmp/motioncorr-gpu3-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.4}
- rounds: 13 run, 12 clean, target 12 clean, at most 20
- CUDA device timing in --profile passes: `default` on, `fast` on
- CUDA device timing in trace passes: `default` off, `fast` off
- input: `movies96.star` in `/home/alex/mc-fft/data96`, 96 movies, STAR sha256 `b906a827b28fc122`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `kit/profiling/mcprof.py compare default=/home/alex/mc-fft/arms/default.sh fast=/home/alex/mc-fft/arms/fast.sh --data /home/alex/mc-fft/data96 --star movies96.star --cpus 80-87 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --runner-cpus 119 --lane-wait 600 --settle-timeout 600 --pairs 12 --max-rounds 20 --profile-pass 3 --trace-pass 2 --allow-product-difference --work /home/alex/mc-fft/kit96run --source default=/home/alex/mc-fft/src --source fast=/home/alex/mc-fft/src -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## PRODUCTS DIFFER

`fast` does not produce the baseline's products (see Product identity). Every verdict for it is speed only, products differ: it compares wall time only and says nothing about whether the products are acceptable.

## Unprofiled wall and resources

Instrument: mcprof run: unprofiled process, wall from CLOCK_MONOTONIC, CPU/RSS/faults from wait4, VRAM from NVML sampling.

| arm | runs | wall med s | wall IQR s | wall range s | CPU med s | peak RSS MiB | minflt med | majflt max | VRAM proc MiB | VRAM dev delta MiB |
|---|---|---|---|---|---|---|---|---|---|---|
| default | 12 | 25.882 | 2.105 | 24.606-32.461 | 76.249 | 368 | 170129 | 14 | 3362 | 3371 |
| fast | 12 | 22.643 | 1.089 | 21.427-23.953 | 73.505 | 363 | 173808 | 14 | 3372 | 3381 |

VRAM columns are sampled peaks and therefore lower bounds. "proc" is NVML's per-process used memory (includes the CUDA context); "dev delta" is device used memory minus the idle baseline taken just before the run.

- `default`: load1 13.1-20.2, max foreign CPU on lane 0.22 cores, wall outlier rounds [12]
- `fast`: load1 14.1-23.4, max foreign CPU on lane 0.15 cores, wall outlier rounds none

Rounds: 13 planned, 12 retained, 1 discarded (a discard removes the whole round, every arm). Discards triggered by: `default` 1 (alone 1), `fast` 0 (alone 0). Kept orders: AB 7, BA 5.

WARNING: kept pairs are unbalanced by order (AB 7, BA 5): the position cost no longer cancels; see the positional line.

Discarded rounds:
- round 10 (BA): default: foreign CPU on lane 0.97 cores

Lane wait before round: r1 1 s, r2 1 s, r3 1 s, r4 1 s, r5 1 s, r6 1 s, r7 1 s, r8 1 s, r9 1 s, r10 159 s, r11 96 s, r12 3 s, r13 1 s.

### `fast` vs `default`: **speed only, products differ: resolved faster**

| pairs | median B-A s | IQR s | range s | CI of median s | noise s | sign test | relative |
|---|---|---|---|---|---|---|---|
| 12 | -3.475 | -4.572..-2.156 | -10.513..-1.179 | -5.586..-2.096 (96.1%) | 1.985 | 0+/12- p=0.000488 | -13.43% |

Reason: CI of median excludes 0 and |median| exceeds noise. Positive differences mean `fast` is slower.
Positional: median B-A when `fast` ran second -3.380 s (n=7), first -4.204 s (n=5); cost of running second +0.412 s.
Paired differences (s): -1.179, -2.177, -3.345, -2.096, -1.893, -5.586, -3.380, -4.204, -3.570, -4.234, -10.513, -6.934

## Product identity

Instrument: lib/identity.py: MRC core header + payload, path-normalised STAR/EPS, round 1.

| arm vs base | result | files compared | MRC compared | excluded | problems |
|---|---|---|---|---|---|
| fast | FAIL | 297 | 96 | 100 | 295 file(s) differ |
- `fast` Movies/r1_20170629_00021_frameImage.mrc: core header differs at byte 76
- `fast` Movies/r1_20170629_00021_frameImage.star: differs after root normalisation (sha256 00efcf2d491e vs 47bc1f40d85b)
- `fast` Movies/r1_20170629_00021_frameImage_shifts.eps: differs after root normalisation (sha256 0842ec8bc43d vs 442224f402c8)
- `fast` Movies/r1_20170629_00022_frameImage.mrc: core header differs at byte 76
- `fast` Movies/r1_20170629_00022_frameImage.star: differs after root normalisation (sha256 09ae93291f08 vs 5b6c994ed9c6)
- `fast` Movies/r1_20170629_00022_frameImage_shifts.eps: differs after root normalisation (sha256 ac492f2e1138 vs 51afe21f2e94)
- `fast` Movies/r1_20170629_00023_frameImage.mrc: core header differs at byte 76
- `fast` Movies/r1_20170629_00023_frameImage.star: differs after root normalisation (sha256 6fc85483b78f vs 3758f8933dad)
- `fast` Movies/r1_20170629_00023_frameImage_shifts.eps: differs after root normalisation (sha256 e163c450db0b vs 85a2082757f9)
- `fast` Movies/r1_20170629_00024_frameImage.mrc: core header differs at byte 76

Excluded: per-movie `.log` (timing values) and `.pdf` (Ghostscript dates); MRC label bytes 224-1023.

## Stage profile deltas

Instrument: --profile (docs/stage_profile.md): profiled process, per-stage main-thread wall/CPU/faults.

Passes per arm: `default` 3, `fast` 3. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `fast` vs `default`

Movie wall (steady median): 234.6 -> 199.1 ms (-35.53 *)

| stage | base wall ms | arm wall ms | delta wall ms | threshold ms | delta CPU ms | delta minflt |
|---|---|---|---|---|---|---|
| setup | 1.51 | 1.52 | +0.01 | 0.67 | +0.00 | +0 |
| read gain | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| session and device ingest | 78.70 | 80.18 | +1.48 | 9.04 | +1.06 | -2 |
| host read movie | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| allocate host sum | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| gain and sum | 0.04 | 0.04 | -0.00 | 0.50 | -0.00 | +0 |
| hot pixels | 19.62 | 15.61 | -4.01 | 4.64 | -3.87 | +0 |
| **fix defects** | 1.23 | 0.51 | -0.73 * | 0.50 | -0.71 * | +0 |
| **release preprocessing** | 0.26 | 1.93 | +1.66 * | 0.50 | +1.66 * | +0 |
| **global fft** | 21.80 | 13.97 | -7.83 * | 0.50 | -7.84 * | +0 |
| power spectrum | 0.05 | 0.05 | -0.00 | 0.50 | -0.00 | +0 |
| **global alignment** | 8.96 | 9.51 | +0.54 * | 0.50 | +0.53 * | +0 |
| allocate reconstruction | 0.01 | 0.01 | -0.00 | 0.50 | -0.00 | +0 |
| **global ifft** | 22.01 | 14.91 | -7.10 * | 0.50 | -7.10 * | +0 |
| **patch alignment** | 27.14 | 16.36 | -10.77 * | 1.20 | -10.70 * | +0 |
| fit polynomial | 1.67 | 1.69 | +0.02 | 0.50 | +0.02 | +0 |
| release alignment | 1.74 | 1.43 | -0.32 | 0.50 | -0.31 | +0 |
| **dose weighting** | 43.64 | 34.36 | -9.28 * | 1.79 | -9.27 * | +0 |
| movie teardown | 4.08 | 4.04 | -0.05 | 0.88 | -0.10 | +0 |
| submit model and plot | 0.08 | 0.08 | -0.00 | 0.50 | -0.00 | +0 |

WARNING: `default` pass 3 met a discard condition (kept): foreign CPU on lane 0.56 cores.

## Device deltas

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

Passes per arm: `default` 2, `fast` 2. busy = union of kernel and copy time inside the stage; idle = stage wall - busy; counts are per movie. Outside-movie rows use each pass's total. Each pass is one process; its value for a stage is the median over its steady-state movies (all but the first). Movies within a process are not independent samples, so the noise is the spread of pass values within each arm. A delta is flagged (*, stage in bold) when it exceeds t(0.999, df) x SE of the pass values and an absolute floor; the threshold column shows the bound. With one pass per arm deltas are shown without flags. Flags locate a change; the verdict decides it.

### `fast` vs `default`

| stage | wall ms | busy ms | idle ms | idle threshold ms | kernels | sync calls | copy MiB | mallocs |
|---|---|---|---|---|---|---|---|---|
| before first movie | +0.43 | +0.00 | +0.43 | 9.16 | +0 | +0 | +0.0 | +0 |
| movie: unattributed | -0.01 | +0.00 | -0.01 | 0.50 | +0 | +0 | +0.0 | +0 |
| setup | -0.09 | +0.00 | -0.09 | 6.78 | +0 | +0 | +0.0 | +0 |
| read gain | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **session and device ingest** | -3.28 | +0.07 | -3.68 | 64.99 | +0 | -12 * | -0.0 * | +2 * |
| host read movie | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| allocate host sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| gain and sum | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| hot pixels | -0.52 | -0.01 | -0.52 | 134.51 | +0 | +0 | +0.0 | +0 |
| fix defects | -0.65 | -0.00 | -0.64 | 1.47 | +0 | +0 | +0.0 | +0 |
| **release preprocessing** | +1.68 * | +0.00 | +1.68 * | 0.50 | +0 | +0 | +0.0 | +0 |
| **global fft** | -7.82 * | -7.69 * | -0.14 | 0.61 | -70 * | +0 | +0.0 | +0 |
| power spectrum | -0.01 | +0.00 | -0.01 | 0.65 | +0 | +0 | +0.0 | +0 |
| **global alignment** | +0.49 | +0.57 * | -0.07 | 4.10 | +0 | +0 | +0.0 | +0 |
| allocate reconstruction | -0.00 | +0.00 | -0.00 | 0.50 | +0 | +0 | +0.0 | +0 |
| **global ifft** | -7.14 * | -7.00 * | -0.13 | 0.65 | -48 * | +0 | +14.7 * | +0 |
| **patch alignment** | -13.67 | -8.01 * | -5.63 | 21.09 | -53 * | -10 * | -0.0 * | -5 * |
| fit polynomial | -0.05 | +0.00 | -0.05 | 0.74 | +0 | +0 | +0.0 | +0 |
| **release alignment** | -0.86 | +0.00 | -0.86 | 4.54 | +0 | -2 * | +0.0 | +0 |
| **dose weighting** | -7.63 | -8.27 * | +0.66 | 12.03 | -72 * | +0 | +0.0 | +0 |
| **movie teardown** | -0.70 | +0.00 | -0.70 | 24.28 | +0 | +2 * | +0.0 | +0 |
| submit model and plot | -0.00 | +0.00 | -0.00 | 0.54 | +0 | +0 | +0.0 | +0 |
| between movies | -0.78 | +0.00 | -0.78 | 60.32 | +0 | +0 | +0.0 | +0 |
| **after last movie** | +76.91 | +0.00 | +76.91 | 2914.44 | +0 | -1 * | +0.0 | +0 |

Traced device allocation high-water per pass: base 3026, 3026 MiB, arm 3040, 3040 MiB.

## Device: `default` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 29259.1 ms, 96 movies. Device busy (union of kernels, copies, memsets) 13716.5 ms (46.9%); idle 15542.6 ms. Kernels 100824 (11941.8 ms summed), copies 12979 (1789.1 ms, 142943.2 MiB). Overlap between kernels and copies 17.35 ms. Streams with kernels: 193.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.28 |
| setup | 1.55 | 0.00 | 0.00 | 0.00 | 0% | 1.55 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.95 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 111.81 |
| session and device ingest | 86.60 | 38.71 | 28.85 | 9.87 | 45% | 48.51 | 59 | 12 | 27 | 0.85 | 5/0 | 130.7 | 18 | 2932 | 377.55 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 19.27 | 0.32 | 0.31 | 0.01 | 2% | 18.96 | 12 | 6 | 10 | 1.26 | 6/6 | 0.0 | 4 | 2933 | 76.68 |
| fix defects | 2.18 | 0.02 | 0.01 | 0.01 | 1% | 2.15 | 10 | 2 | 9 | 0.58 | 3/3 | 0.0 | 7 | 2932 | 4.22 |
| release preprocessing | 0.37 | 0.00 | 0.00 | 0.00 | 0% | 0.37 | 1 | 0 | 2 | 0.30 | 0/1 | 0.0 | 0 | 2932 | 0.74 |
| global fft | 22.05 | 21.61 | 21.61 | 0.00 | 98% | 0.43 | 170 | 169 | 1 | 0.16 | 0/0 | 0.0 | 0 | 2877 | 22.08 |
| power spectrum | 0.12 | 0.00 | 0.00 | 0.00 | 0% | 0.12 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.14 |
| global alignment | 11.08 | 7.13 | 7.11 | 0.02 | 64% | 3.96 | 34 | 19 | 15 | 0.61 | 0/0 | 0.0 | 14 | 2877 | 9.30 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.29 | 21.80 | 20.04 | 1.76 | 98% | 0.47 | 193 | 168 | 25 | 0.22 | 0/0 | 1304.3 | 0 | 2877 | 22.36 |
| patch alignment | 45.26 | 19.89 | 19.83 | 0.05 | 44% | 25.42 | 497 | 456 | 51 | 2.23 | 17/3 | 0.0 | 38 | 3026 | 45.42 |
| fit polynomial | 1.74 | 0.00 | 0.00 | 0.00 | 0% | 1.74 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.81 |
| release alignment | 3.56 | 0.00 | 0.00 | 0.00 | 0% | 3.56 | 1 | 0 | 15 | 2.22 | 0/14 | 0.0 | 0 | 3026 | 3.38 |
| dose weighting | 41.67 | 33.50 | 26.95 | 6.49 | 80% | 8.10 | 221 | 217 | 4 | 0.46 | 0/0 | 54.3 | 2 | 2877 | 78.92 |
| movie teardown | 6.27 | 0.00 | 0.00 | 0.00 | 0% | 6.27 | 1 | 0 | 5 | 3.53 | 0/4 | 0.0 | 0 | 2877 | 7.70 |
| submit model and plot | 0.14 | 0.00 | 0.00 | 0.00 | 0% | 0.14 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.18 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.58 | 0.00 | 4.58 | 0 | 0/0 |
| between movies | 21.74 | 0.00 | 21.74 | 0 | 0/0 |
| after last movie | 2382.68 | 0.00 | 2382.68 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 23136 | 4090.59 | 176.8 | 239.2 | 34.3% |
| inflate_kernel | 384 | 2344.56 | 6105.6 | 6229.4 | 19.6% |
| regular_fft_factor | 23136 | 1731.25 | 74.8 | 86.0 | 14.5% |
| regular_bluestein_fft | 2400 | 741.34 | 308.9 | 317.6 | 6.2% |
| fourierShiftKernel | 5108 | 521.34 | 102.1 | 1777.4 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 2304 | 404.97 | 175.8 | 182.9 | 3.4% |
| postprocess_kernel | 4704 | 316.66 | 67.3 | 74.7 | 2.7% |
| preprocess_kernel | 4608 | 298.08 | 64.7 | 67.4 | 2.5% |
| cropAndGroupPatchResidentKernel | 2400 | 248.68 | 103.6 | 113.4 | 2.1% |
| applyDoseWeightKernel | 2304 | 241.01 | 104.6 | 107.3 | 2.0% |
| adler32StripsKernel | 384 | 219.50 | 571.6 | 583.0 | 1.8% |
| fusedU16FlipGainAndSumKernel | 384 | 201.13 | 523.8 | 555.5 | 1.7% |
| scaleComplexKernel | 96 | 160.11 | 1667.8 | 1671.5 | 1.3% |
| regular_fft | 5204 | 108.26 | 20.8 | 237.2 | 0.9% |
| regular_fft_c2r | 5108 | 91.82 | 18.0 | 182.3 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 9907 | 3475.64 | 389.70 |
| device sync | 864 | 2617.81 | 75.57 |
| event sync | 1536 | 962.47 | 47.02 |
| free (implicit sync) | 2980 | 817.02 | 817.02 |
| stream sync | 480 | 83.33 | 26.28 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 2304 | 125214.8 | 168.78 | 777.94 |
| Host-to-Device Pinned->Device | 1536 | 12309.3 | 932.26 | 13.85 |
| Device-to-Host Device->Pageable | 2504 | 5216.1 | 663.64 | 8.24 |
| Device-to-Host Device->Pinned | 1152 | 134.9 | 8.32 | 17.01 |
| Host-to-Device Pageable->Device | 5483 | 68.1 | 16.13 | 4.43 |

Byte counts are invariant across captures; rates are not (contention, tracing).

## Device: `fast` (trace pass 1 of 2)

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 25671.5 ms, 96 movies. Device busy (union of kernels, copies, memsets) 10818.0 ms (42.1%); idle 14853.5 ms. Kernels 77496 (8977.3 ms summed), copies 11442 (1863.4 ms, 144354.5 MiB). Overlap between kernels and copies 25.13 ms. Streams with kernels: 193.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.28 | 0.00 | 0.00 | 0.00 | 0% | 0.28 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3040 | 0.29 |
| setup | 1.76 | 0.00 | 0.00 | 0.00 | 0% | 1.76 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 1.73 |
| read gain | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 118.97 |
| session and device ingest | 85.05 | 38.61 | 28.82 | 10.00 | 45% | 46.25 | 47 | 12 | 15 | 0.50 | 7/0 | 130.7 | 6 | 2944 | 386.09 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.08 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2944 | 0.09 |
| hot pixels | 24.33 | 0.31 | 0.30 | 0.01 | 1% | 24.01 | 12 | 6 | 10 | 0.46 | 6/6 | 0.0 | 4 | 2945 | 74.91 |
| fix defects | 1.60 | 0.02 | 0.01 | 0.01 | 1% | 1.57 | 10 | 2 | 9 | 0.35 | 3/3 | 0.0 | 7 | 2944 | 4.05 |
| release preprocessing | 2.06 | 0.00 | 0.00 | 0.00 | 0% | 2.06 | 1 | 0 | 2 | 2.00 | 0/1 | 0.0 | 0 | 2944 | 0.75 |
| global fft | 14.23 | 13.93 | 13.93 | 0.00 | 98% | 0.30 | 100 | 99 | 1 | 0.09 | 0/0 | 0.0 | 0 | 2889 | 14.28 |
| power spectrum | 0.10 | 0.00 | 0.00 | 0.00 | 0% | 0.10 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2889 | 0.08 |
| global alignment | 11.62 | 7.70 | 7.68 | 0.02 | 66% | 3.94 | 34 | 19 | 15 | 0.65 | 0/0 | 0.0 | 14 | 2889 | 9.00 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2889 | 0.21 |
| global ifft | 15.18 | 14.80 | 13.11 | 1.68 | 98% | 0.37 | 145 | 120 | 25 | 0.17 | 0/0 | 1319.1 | 0 | 2889 | 15.15 |
| patch alignment | 31.99 | 11.88 | 11.83 | 0.05 | 37% | 20.16 | 438 | 403 | 41 | 1.86 | 12/0 | 0.0 | 34 | 3040 | 32.97 |
| fit polynomial | 1.73 | 0.00 | 0.00 | 0.00 | 0% | 1.73 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3040 | 1.80 |
| release alignment | 2.69 | 0.00 | 0.00 | 0.00 | 0% | 2.69 | 1 | 0 | 13 | 1.92 | 0/12 | 0.0 | 0 | 3040 | 2.53 |
| dose weighting | 34.01 | 25.36 | 18.26 | 7.06 | 75% | 8.65 | 149 | 145 | 4 | 0.40 | 0/0 | 54.3 | 2 | 2889 | 88.16 |
| movie teardown | 6.64 | 0.00 | 0.00 | 0.00 | 0% | 6.64 | 1 | 0 | 7 | 4.43 | 0/6 | 0.0 | 0 | 2889 | 6.00 |
| submit model and plot | 0.16 | 0.00 | 0.00 | 0.00 | 0% | 0.16 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 157 | 0.33 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.32 | 0.00 | 5.32 | 0 | 0/0 |
| between movies | 23.55 | 0.00 | 23.55 | 0 | 0/0 |
| after last movie | 2374.11 | 0.00 | 2374.11 | 0 | 0/2 |

Device 0 allocation high-water 3040 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| inflate_kernel | 384 | 2336.27 | 6084.0 | 6155.4 | 26.0% |
| regular_fft | 14420 | 2045.10 | 141.8 | 242.0 | 22.8% |
| fourierShiftKernel | 5108 | 569.58 | 111.5 | 1966.0 | 6.3% |
| vector_fft | 6912 | 539.28 | 78.0 | 84.4 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 2304 | 408.48 | 177.3 | 185.9 | 4.6% |
| kernel_wrapper | 4608 | 354.84 | 77.0 | 83.3 | 4.0% |
| preprocess_kernel | 4608 | 319.23 | 69.3 | 71.7 | 3.6% |
| regular_fft_r2c | 2400 | 261.93 | 109.1 | 110.1 | 2.9% |
| cropGroupPadPatchKernel | 2400 | 251.72 | 104.9 | 105.9 | 2.8% |
| applyDoseWeightKernel | 2304 | 249.05 | 108.1 | 114.6 | 2.8% |
| adler32StripsKernel | 384 | 219.06 | 570.5 | 578.8 | 2.4% |
| cropFrameKernel | 2304 | 201.97 | 87.7 | 100.1 | 2.2% |
| fusedU16FlipGainAndSumKernel | 384 | 200.77 | 522.8 | 556.5 | 2.2% |
| padFrameKernel | 2304 | 199.65 | 86.7 | 87.6 | 2.2% |
| postprocess_kernel | 2304 | 174.42 | 75.7 | 81.2 | 1.9% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 8370 | 2658.69 | 327.95 |
| device sync | 576 | 1584.86 | 53.67 |
| event sync | 1536 | 977.57 | 51.81 |
| free (implicit sync) | 2691 | 860.51 | 860.51 |
| stream sync | 480 | 80.91 | 29.04 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 2304 | 126630.0 | 161.66 | 821.35 |
| Host-to-Device Pinned->Device | 1536 | 12309.3 | 955.04 | 13.51 |
| Device-to-Host Device->Pageable | 2504 | 5216.1 | 724.36 | 7.55 |
| Device-to-Host Device->Pinned | 1152 | 134.9 | 8.11 | 17.44 |
| Host-to-Device Pageable->Device | 3946 | 64.2 | 14.18 | 4.75 |

Byte counts are invariant across captures; rates are not (contention, tracing).
