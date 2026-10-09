# MotionCorr trace

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 18.8, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- CUDA device timing in trace passes: `main` off
- input: `movies.star` in `/home/alex/mc-small/runs/trace12_EAGER/input`, 12 movies, STAR sha256 `3b86c74aa7e62301`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_MODULE_LOADING=EAGER`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py trace main=/home/alex/mc-small/build-main/motioncorr --data /home/alex/mc-small/data96 --star movies.star --movies 12 --work /home/alex/mc-small/runs/trace12_EAGER --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --settle-timeout 600 --env CUDA_MODULE_LOADING=EAGER --commit main=7d64043 --keep sqlite -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Device

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 4472.0 ms, 12 movies. Device busy (union of kernels, copies, memsets) 1750.9 ms (39.2%); idle 2721.1 ms. Kernels 12612 (1491.0 ms summed), copies 1629 (262.4 ms, 17910.8 MiB). Overlap between kernels and copies 2.78 ms. Streams with kernels: 25.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.25 | 0.00 | 0.00 | 0.00 | 0% | 0.25 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.26 |
| setup | 1.48 | 0.00 | 0.00 | 0.00 | 0% | 1.48 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.72 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 97.34 |
| session and device ingest | 83.42 | 39.52 | 28.71 | 11.21 | 47% | 42.72 | 59 | 12 | 27 | 0.90 | 5/0 | 128.8 | 18 | 2932 | 563.34 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 19.93 | 0.31 | 0.30 | 0.01 | 2% | 19.62 | 12 | 6 | 10 | 1.38 | 6/6 | 0.0 | 4 | 2933 | 71.97 |
| fix defects | 2.16 | 0.02 | 0.01 | 0.01 | 1% | 2.14 | 10 | 2 | 9 | 0.51 | 3/3 | 0.0 | 7 | 2932 | 3.81 |
| release preprocessing | 0.44 | 0.00 | 0.00 | 0.00 | 0% | 0.44 | 1 | 0 | 2 | 0.30 | 0/1 | 0.0 | 0 | 2932 | 0.35 |
| global fft | 22.01 | 21.56 | 21.56 | 0.00 | 98% | 0.42 | 170 | 169 | 1 | 0.15 | 0/0 | 0.0 | 0 | 2877 | 22.13 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.09 |
| global alignment | 10.89 | 7.14 | 7.12 | 0.02 | 66% | 3.79 | 34 | 19 | 15 | 0.65 | 0/0 | 0.0 | 14 | 2877 | 8.39 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.15 | 21.78 | 20.03 | 1.75 | 98% | 0.37 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.32 |
| patch alignment | 42.64 | 19.89 | 19.83 | 0.05 | 47% | 22.80 | 497 | 456 | 51 | 2.16 | 17/3 | 0.0 | 38 | 3026 | 43.84 |
| fit polynomial | 1.71 | 0.00 | 0.00 | 0.00 | 0% | 1.71 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.69 |
| release alignment | 3.21 | 0.00 | 0.00 | 0.00 | 0% | 3.21 | 1 | 0 | 15 | 2.11 | 0/14 | 0.0 | 0 | 3026 | 3.20 |
| dose weighting | 41.24 | 34.24 | 27.04 | 7.19 | 83% | 6.80 | 221 | 217 | 4 | 0.52 | 0/0 | 54.3 | 2 | 2877 | 93.78 |
| movie teardown | 5.86 | 0.00 | 0.00 | 0.00 | 0% | 5.86 | 1 | 0 | 5 | 3.45 | 0/4 | 0.0 | 0 | 2877 | 7.29 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.15 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 5.22 | 0.00 | 5.22 | 0 | 0/0 |
| between movies | 1.99 | 0.00 | 1.99 | 0 | 0/0 |
| after last movie | 658.63 | 0.00 | 658.63 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 2892 | 511.12 | 176.7 | 237.5 | 34.3% |
| inflate_kernel | 48 | 290.63 | 6054.7 | 6169.5 | 19.5% |
| regular_fft_factor | 2892 | 216.34 | 74.8 | 84.8 | 14.5% |
| regular_bluestein_fft | 300 | 92.50 | 308.3 | 314.9 | 6.2% |
| fourierShiftKernel | 640 | 65.96 | 103.1 | 1769.0 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 288 | 50.64 | 175.8 | 181.7 | 3.4% |
| postprocess_kernel | 588 | 39.56 | 67.3 | 74.4 | 2.7% |
| preprocess_kernel | 576 | 37.43 | 65.0 | 67.6 | 2.5% |
| cropAndGroupPatchResidentKernel | 300 | 31.10 | 103.7 | 105.6 | 2.1% |
| applyDoseWeightKernel | 288 | 30.14 | 104.7 | 107.2 | 2.0% |
| adler32StripsKernel | 48 | 27.46 | 572.1 | 583.0 | 1.8% |
| fusedU16FlipGainAndSumKernel | 48 | 25.08 | 522.5 | 552.8 | 1.7% |
| scaleComplexKernel | 12 | 20.02 | 1668.0 | 1670.3 | 1.3% |
| regular_fft | 652 | 13.61 | 20.9 | 234.1 | 0.9% |
| regular_fft_c2r | 640 | 11.56 | 18.1 | 181.7 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 1245 | 488.49 | 47.00 |
| device sync | 108 | 336.84 | 7.46 |
| event sync | 192 | 126.76 | 5.69 |
| free (implicit sync) | 376 | 125.83 | 125.83 |
| stream sync | 60 | 10.68 | 2.77 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 288 | 15651.8 | 21.03 | 780.28 |
| Host-to-Device Pinned->Device | 192 | 1524.9 | 125.83 | 12.71 |
| Device-to-Host Device->Pageable | 315 | 652.0 | 105.89 | 6.46 |
| Host-to-Device Pageable->Device | 690 | 65.1 | 8.20 | 8.33 |
| Device-to-Host Device->Pinned | 144 | 16.9 | 1.42 | 12.42 |

Byte counts are invariant across captures; rates are not (contention, tracing).
