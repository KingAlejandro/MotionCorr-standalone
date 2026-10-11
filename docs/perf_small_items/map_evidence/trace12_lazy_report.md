# MotionCorr trace

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 18.2, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- CUDA device timing in trace passes: `main` off
- input: `movies.star` in `/home/alex/mc-small/runs/trace12_LAZY/input`, 12 movies, STAR sha256 `3b86c74aa7e62301`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_MODULE_LOADING=LAZY`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py trace main=/home/alex/mc-small/build-main/motioncorr --data /home/alex/mc-small/data96 --star movies.star --movies 12 --work /home/alex/mc-small/runs/trace12_LAZY --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --settle-timeout 600 --env CUDA_MODULE_LOADING=LAZY --commit main=7d64043 --keep sqlite -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Device

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 4410.6 ms, 12 movies. Device busy (union of kernels, copies, memsets) 1742.0 ms (39.5%); idle 2668.5 ms. Kernels 12612 (1492.2 ms summed), copies 1629 (252.2 ms, 17910.8 MiB). Overlap between kernels and copies 2.71 ms. Streams with kernels: 25.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.29 | 0.00 | 0.00 | 0.00 | 0% | 0.29 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.26 |
| setup | 1.41 | 0.00 | 0.00 | 0.00 | 0% | 1.41 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.68 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 111.90 |
| session and device ingest | 84.79 | 39.50 | 28.80 | 10.61 | 47% | 44.98 | 59 | 12 | 27 | 0.82 | 5/0 | 128.8 | 18 | 2932 | 398.14 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 20.17 | 0.31 | 0.30 | 0.01 | 2% | 19.85 | 12 | 6 | 10 | 1.28 | 6/6 | 0.0 | 4 | 2933 | 78.95 |
| fix defects | 2.23 | 0.02 | 0.01 | 0.01 | 1% | 2.21 | 10 | 2 | 9 | 0.62 | 3/3 | 0.0 | 7 | 2932 | 4.30 |
| release preprocessing | 0.35 | 0.00 | 0.00 | 0.00 | 0% | 0.35 | 1 | 0 | 2 | 0.28 | 0/1 | 0.0 | 0 | 2932 | 0.48 |
| global fft | 22.03 | 21.62 | 21.62 | 0.00 | 98% | 0.40 | 170 | 169 | 1 | 0.14 | 0/0 | 0.0 | 0 | 2877 | 21.95 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 10.95 | 7.13 | 7.11 | 0.02 | 65% | 3.83 | 34 | 19 | 15 | 0.66 | 0/0 | 0.0 | 14 | 2877 | 8.27 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.02 |
| global ifft | 22.21 | 21.80 | 20.01 | 1.76 | 98% | 0.42 | 193 | 168 | 25 | 0.20 | 0/0 | 1304.3 | 0 | 2877 | 22.17 |
| patch alignment | 44.57 | 19.90 | 19.85 | 0.05 | 45% | 24.67 | 497 | 456 | 51 | 2.41 | 17/3 | 0.0 | 38 | 3026 | 45.14 |
| fit polynomial | 1.71 | 0.00 | 0.00 | 0.00 | 0% | 1.71 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.80 |
| release alignment | 3.30 | 0.00 | 0.00 | 0.00 | 0% | 3.30 | 1 | 0 | 15 | 2.06 | 0/14 | 0.0 | 0 | 3026 | 3.42 |
| dose weighting | 43.83 | 34.80 | 26.99 | 7.74 | 79% | 8.93 | 221 | 217 | 4 | 0.53 | 0/0 | 54.3 | 2 | 2877 | 77.23 |
| movie teardown | 5.98 | 0.00 | 0.00 | 0.00 | 0% | 5.98 | 1 | 0 | 5 | 3.37 | 0/4 | 0.0 | 0 | 2877 | 6.33 |
| submit model and plot | 0.13 | 0.00 | 0.00 | 0.00 | 0% | 0.13 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.14 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.22 | 0.00 | 4.22 | 0 | 0/0 |
| between movies | 2.70 | 0.00 | 2.70 | 0 | 0/0 |
| after last movie | 670.40 | 0.00 | 670.40 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 2892 | 511.18 | 176.8 | 238.0 | 34.3% |
| inflate_kernel | 48 | 291.28 | 6068.3 | 6195.5 | 19.5% |
| regular_fft_factor | 2892 | 216.42 | 74.8 | 84.2 | 14.5% |
| regular_bluestein_fft | 300 | 92.59 | 308.6 | 317.8 | 6.2% |
| fourierShiftKernel | 640 | 66.07 | 103.2 | 1774.8 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 288 | 50.63 | 175.8 | 181.8 | 3.4% |
| postprocess_kernel | 588 | 39.60 | 67.4 | 74.0 | 2.7% |
| preprocess_kernel | 576 | 37.23 | 64.6 | 66.7 | 2.5% |
| cropAndGroupPatchResidentKernel | 300 | 31.19 | 104.0 | 114.3 | 2.1% |
| applyDoseWeightKernel | 288 | 30.12 | 104.6 | 107.1 | 2.0% |
| adler32StripsKernel | 48 | 27.48 | 572.5 | 582.4 | 1.8% |
| fusedU16FlipGainAndSumKernel | 48 | 25.21 | 525.2 | 554.7 | 1.7% |
| scaleComplexKernel | 12 | 20.02 | 1668.5 | 1670.0 | 1.3% |
| regular_fft | 652 | 13.64 | 20.9 | 232.4 | 0.9% |
| regular_fft_c2r | 640 | 11.57 | 18.1 | 181.9 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 1245 | 457.65 | 48.85 |
| device sync | 108 | 330.52 | 7.26 |
| free (implicit sync) | 376 | 129.85 | 129.85 |
| event sync | 192 | 124.77 | 6.11 |
| stream sync | 60 | 10.83 | 2.92 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 288 | 15651.8 | 21.13 | 776.81 |
| Host-to-Device Pinned->Device | 192 | 1524.9 | 126.14 | 12.68 |
| Device-to-Host Device->Pageable | 315 | 652.0 | 92.52 | 7.39 |
| Host-to-Device Pageable->Device | 690 | 65.1 | 11.02 | 6.20 |
| Device-to-Host Device->Pinned | 144 | 16.9 | 1.37 | 12.88 |

Byte counts are invariant across captures; rates are not (contention, tracing).
