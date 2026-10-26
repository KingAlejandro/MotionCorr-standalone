# MotionCorr trace

## Provenance

- kit: `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`
- arm `A`: `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr` sha256 `34e768128b83f7c9`; source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-101, load1 1.4, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d (index 3), driver 570.86.10, CUDA 12.8, persistence Disabled
- settle: {"settled": true, "waited_s": 0.1}
- CUDA device timing in trace passes: `A` off
- input: `input.star` in `/mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01`, 1 movies, STAR sha256 `ba3a39e59ca796b5`
- payload options: `--use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/ingest-witness.txt --gpu 0`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/src/tools/profiling/mcprof.py trace A=/mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb/build-cuda/motioncorr --work /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/kit-trace --data /mnt/clathrin/alex-motioncorr-km-truth/fixtures/dose1-s01 --star input.star --cpus 96-101 --runner-cpus 102-103 --gpu-uuid GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d --no-lock --commit A=e77a51a220cb0d91f4ac3c7fac211876d0c6833f -- --use_own --j 6 --patch_x 5 --patch_y 5 --group_frames 1 --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 40 --ingest float --ingest_witness /mnt/clathrin/alex-motioncorr-c1-20261022-e77a51a220cb-bp-20261026/ingest-witness.txt --gpu 0`

## Device

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 2889.9 ms, 1 movies. Device busy (union of kernels, copies, memsets) 516.1 ms (17.9%); idle 2373.8 ms. Kernels 749 (83.5 ms summed), copies 143 (432.5 ms, 5195.7 MiB). Overlap between kernels and copies 0.00 ms. Streams with kernels: 1.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.28 | 0.00 | 0.00 | 0.00 | 0% | 0.28 | 19 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5661 | 0.28 |
| setup | 0.46 | 0.00 | 0.00 | 0.00 | 0% | 0.46 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 0 | 0.46 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 0 | 0.07 |
| session and device ingest | 176.48 | 1.66 | 0.00 | 1.66 | 1% | 174.82 | 6 | 0 | 5 | 0.54 | 6/0 | 6.5 | 5 | 5320 | 176.48 |
| host read movie | 1277.93 | 0.00 | 0.00 | 0.00 | 0% | 1277.93 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5320 | 1277.93 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5320 | 0.03 |
| gain and sum | 434.14 | 421.58 | 1.76 | 419.82 | 97% | 12.56 | 42 | 1 | 41 | 10.70 | 0/0 | 2560.0 | 40 | 5320 | 434.14 |
| release preprocessing | 20.02 | 0.69 | 0.12 | 0.56 | 3% | 19.33 | 31 | 15 | 35 | 2.22 | 16/16 | 3.9 | 9 | 5320 | 20.02 |
| global fft | 14.98 | 14.67 | 14.67 | 0.00 | 98% | 0.31 | 82 | 81 | 1 | 0.09 | 0/0 | 0.0 | 0 | 5260 | 14.98 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5260 | 0.08 |
| global alignment | 14.18 | 10.46 | 10.45 | 0.01 | 74% | 3.72 | 26 | 15 | 11 | 0.41 | 0/0 | 0.0 | 10 | 5260 | 14.18 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5260 | 0.02 |
| global ifft | 14.95 | 14.45 | 11.03 | 3.42 | 97% | 0.50 | 161 | 120 | 41 | 0.17 | 0/0 | 2561.2 | 0 | 5260 | 14.95 |
| patch alignment | 67.14 | 36.11 | 36.05 | 0.05 | 54% | 31.03 | 522 | 477 | 63 | 2.62 | 28/9 | 0.0 | 38 | 5661 | 67.14 |
| fit polynomial | 2.73 | 0.00 | 0.00 | 0.00 | 0% | 2.73 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5661 | 2.73 |
| release alignment | 3.66 | 0.00 | 0.00 | 0.00 | 0% | 3.66 | 1 | 0 | 20 | 2.55 | 0/19 | 0.0 | 0 | 5661 | 3.66 |
| unweighted sums | 159.15 | 16.43 | 9.42 | 6.97 | 10% | 142.72 | 43 | 40 | 3 | 0.67 | 1/1 | 64.0 | 1 | 5324 | 159.15 |
| movie teardown | 359.07 | 0.00 | 0.00 | 0.00 | 0% | 359.07 | 1 | 0 | 1 | 0.04 | 0/0 | 0.0 | 0 | 5260 | 359.07 |
| submit model and plot | 0.22 | 0.00 | 0.00 | 0.00 | 0% | 0.22 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 5260 | 0.22 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 3.94 | 0.00 | 3.94 | 0 | 0/0 |
| after last movie | 340.38 | 0.00 | 340.38 | 0 | 0/6 |

Device 0 allocation high-water 5661 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| regular_bluestein_fft | 50 | 24.31 | 486.2 | 569.6 | 29.1% |
| regular_fft_factor | 80 | 15.06 | 188.2 | 192.9 | 18.0% |
| interpolateAndAccumulatePolynomialKernel | 40 | 9.42 | 235.6 | 243.7 | 11.3% |
| fourierShiftKernel | 50 | 9.42 | 188.4 | 4380.4 | 11.3% |
| cropAndGroupPatchResidentKernel | 25 | 4.98 | 199.2 | 209.9 | 6.0% |
| vector_fft_symm_c2r | 42 | 3.82 | 90.9 | 213.1 | 4.6% |
| vector_fft_symm_r2c | 40 | 3.81 | 95.2 | 98.6 | 4.6% |
| scaleComplexKernel | 1 | 3.28 | 3282.4 | 3282.4 | 3.9% |
| postprocess_kernel | 25 | 3.16 | 126.3 | 127.8 | 3.8% |
| fusedGainAndSumKernel | 1 | 1.76 | 1758.9 | 1758.9 | 2.1% |
| regular_fft | 52 | 1.16 | 22.2 | 259.0 | 1.4% |
| computeCCFKernel | 50 | 0.94 | 18.8 | 241.6 | 1.1% |
| computeReferenceKernel | 50 | 0.72 | 14.3 | 140.1 | 0.9% |
| vector_fft_c2r | 48 | 0.59 | 12.3 | 12.5 | 0.7% |
| projectHermitianColumnsKernel | 90 | 0.32 | 3.6 | 9.2 | 0.4% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 143 | 476.81 | 14.01 |
| device sync | 24 | 21.09 | 1.10 |
| free (implicit sync) | 51 | 10.22 | 10.22 |
| event sync | 9 | 4.64 | 0.33 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Host-to-Device Pageable->Device | 84 | 2570.4 | 422.08 | 6.39 |
| Device-to-Device Device->Device | 40 | 2561.2 | 3.42 | 785.31 |
| Device-to-Host Device->Pageable | 19 | 64.0 | 7.01 | 9.58 |

Byte counts are invariant across captures; rates are not (contention, tracing).
