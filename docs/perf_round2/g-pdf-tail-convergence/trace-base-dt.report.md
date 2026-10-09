# MotionCorr trace

## Provenance

- kit: `a4b18c9d1ce4253a43cac2fa7b9a821678ecd705`
- arm `base`: `/home/alex/mc-agent-G/build-dt/motioncorr` sha256 `aba53ad1813397b5`; source `93c38970cb0a39ce3e41b1088360c2a75be97cb5` (git in /home/alex/mc-agent-G/src-dt); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 14.1, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 276 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 52.0}
- CUDA device timing in trace passes: `base` off
- input: `movies.star` in `/home/alex/mc-perf-20261001/data`, 24 movies, STAR sha256 `fb998f70b375a4eb`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `kit/tools/profiling/mcprof.py trace base=build-dt/motioncorr --data /home/alex/mc-perf-20261001/data --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --settle-timeout 600 --work /home/alex/mc-agent-G/trace-base-dt --source base=/home/alex/mc-agent-G/src-dt --keep sqlite -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Device

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 14470.5 ms, 24 movies. Device busy (union of kernels, copies, memsets) 3691.1 ms (25.5%); idle 10779.4 ms. Kernels 25206 (3101.1 ms summed), copies 3247 (589.0 ms, 35784.3 MiB). Overlap between kernels and copies 0.00 ms. Streams with kernels: 49.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.27 | 0.00 | 0.00 | 0.00 | 0% | 0.27 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 0.44 |
| setup | 1.63 | 0.00 | 0.00 | 0.00 | 0% | 1.63 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.61 |
| read gain | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 150.02 |
| session and device ingest | 90.77 | 39.10 | 28.78 | 10.65 | 43% | 51.41 | 59 | 12 | 27 | 0.94 | 5/0 | 130.7 | 18 | 2932 | 464.87 |
| host read movie | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.07 | 0.00 | 0.00 | 0.00 | 0% | 0.07 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 22.24 | 0.31 | 0.30 | 0.01 | 1% | 21.93 | 12 | 6 | 10 | 1.40 | 6/6 | 0.0 | 4 | 2933 | 92.43 |
| fix defects | 2.30 | 0.02 | 0.01 | 0.01 | 1% | 2.28 | 10 | 2 | 9 | 0.69 | 3/3 | 0.0 | 7 | 2932 | 2.90 |
| release preprocessing | 0.49 | 0.00 | 0.00 | 0.00 | 0% | 0.49 | 1 | 0 | 2 | 0.41 | 0/1 | 0.0 | 0 | 2932 | 0.38 |
| global fft | 22.04 | 21.57 | 21.57 | 0.00 | 98% | 0.43 | 170 | 169 | 1 | 0.14 | 0/0 | 0.0 | 0 | 2877 | 21.96 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 14.60 | 7.13 | 7.11 | 0.02 | 49% | 7.47 | 34 | 19 | 24 | 2.32 | 9/9 | 0.0 | 14 | 3143 | 12.59 |
| allocate reconstruction | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.06 |
| global ifft | 22.39 | 21.83 | 20.06 | 1.77 | 97% | 0.55 | 193 | 168 | 25 | 0.24 | 0/0 | 1304.3 | 0 | 2877 | 22.25 |
| patch alignment | 47.75 | 24.87 | 24.81 | 0.05 | 52% | 22.64 | 497 | 456 | 51 | 2.64 | 17/3 | 0.0 | 38 | 3221 | 51.97 |
| fit polynomial | 1.79 | 0.00 | 0.00 | 0.00 | 0% | 1.79 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3221 | 2.27 |
| release alignment | 1.77 | 0.00 | 0.00 | 0.00 | 0% | 1.77 | 1 | 0 | 8 | 1.31 | 0/8 | 0.0 | 0 | 3221 | 2.35 |
| dose weighting | 49.62 | 35.79 | 26.90 | 8.80 | 72% | 13.80 | 221 | 217 | 5 | 0.98 | 1/1 | 54.3 | 2 | 3117 | 174.07 |
| movie teardown | 8.08 | 0.00 | 0.00 | 0.00 | 0% | 8.08 | 1 | 0 | 11 | 4.33 | 0/10 | 0.0 | 0 | 2982 | 8.90 |
| submit model and plot | 0.15 | 0.00 | 0.00 | 0.00 | 0% | 0.15 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.15 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.76 | 0.00 | 4.76 | 0 | 0/0 |
| between movies | 7.07 | 0.00 | 7.07 | 0 | 0/0 |
| after last movie | 920.49 | 0.00 | 920.49 | 0 | 0/3 |

Device 0 allocation high-water 3221 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 5784 | 1019.89 | 176.3 | 237.1 | 32.9% |
| inflate_kernel | 96 | 583.95 | 6082.8 | 6216.0 | 18.8% |
| regular_fft_factor | 5784 | 432.16 | 74.7 | 85.5 | 13.9% |
| fourierShiftKernel | 1277 | 215.10 | 168.4 | 1771.1 | 6.9% |
| regular_bluestein_fft | 600 | 184.83 | 308.0 | 314.3 | 6.0% |
| interpolateAndAccumulatePolynomialKernel | 576 | 101.04 | 175.4 | 182.1 | 3.3% |
| postprocess_kernel | 1176 | 79.61 | 67.7 | 74.6 | 2.6% |
| scaleComplexKernel | 624 | 79.08 | 126.7 | 1670.2 | 2.5% |
| preprocess_kernel | 1152 | 75.31 | 65.4 | 69.4 | 2.4% |
| cropAndGroupPatchResidentKernel | 600 | 62.43 | 104.0 | 110.9 | 2.0% |
| applyDoseWeightKernel | 576 | 60.12 | 104.4 | 107.5 | 1.9% |
| adler32StripsKernel | 96 | 54.54 | 568.1 | 583.3 | 1.8% |
| fusedU16FlipGainAndSumKernel | 96 | 50.33 | 524.3 | 545.4 | 1.6% |
| regular_fft | 1301 | 26.97 | 20.7 | 232.7 | 0.9% |
| regular_fft_c2r | 1277 | 22.90 | 17.9 | 182.1 | 0.7% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 2479 | 1182.78 | 317.16 |
| device sync | 192 | 614.61 | 35.70 |
| free (implicit sync) | 988 | 569.38 | 569.38 |
| event sync | 384 | 276.37 | 48.44 |
| stream sync | 120 | 33.31 | 19.69 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 576 | 31303.7 | 44.68 | 734.67 |
| Host-to-Device Pinned->Device | 384 | 3077.3 | 254.66 | 12.67 |
| Device-to-Host Device->Pageable | 626 | 1304.0 | 267.86 | 5.10 |
| Host-to-Device Pageable->Device | 1373 | 65.6 | 19.83 | 3.47 |
| Device-to-Host Device->Pinned | 288 | 33.7 | 2.02 | 17.49 |

Byte counts are invariant across captures; rates are not (contention, tracing).
