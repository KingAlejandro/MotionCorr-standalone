# MotionCorr trace

## Provenance

- kit: `1d3c399de3128fbe31703775ec946a3adf086ae5`
- arm `main`: `/home/alex/mc-small/build-main/motioncorr` sha256 `795d671d57c45b8f`; source `7d64043` (given on command line); --profile present
  - linked: libcudart.so.12=/usr/local/cuda-12.8/lib64/libcudart.so.12, libcufft.so.11=/usr/local/cuda-12.8/lib64/libcufft.so.11, libfftw3.so.3=/lib/x86_64-linux-gnu/libfftw3.so.3, libfftw3f.so.3=/lib/x86_64-linux-gnu/libfftw3f.so.3, libnvcomp.so.5=/home/alex/nvcomp53/nvcomp-linux-x86_64-5.3.0.16_cuda12-archive/lib/libnvcomp.so.5, libtiff.so.6=/lib/x86_64-linux-gnu/libtiff.so.6
- host: 4-gpu-vm, AMD EPYC 7452 32-Core Processor, 124 CPUs, lane 96-103, load1 13.6, clocksource acpi_pm, THP always [madvise] never
- GPU: NVIDIA A100 80GB PCIe GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 (index 0), driver 570.86.10, CUDA 12.8, persistence Disabled
- locks: /tmp/motioncorr-bench.lock (waited 0 s), /tmp/motioncorr-gpu0-correctness.lock (waited 0 s)
- settle: {"settled": true, "waited_s": 0.2}
- CUDA device timing in trace passes: `main` off
- input: `movies.star` in `/home/alex/mc-small/data96`, 96 movies, STAR sha256 `b906a827b28fc122`
- payload options: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`
- payload env: `CUDA_VISIBLE_DEVICES=GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 CUDA_DEVICE_ORDER=PCI_BUS_ID`
- command: `/home/alex/mc-small/kit/tools/profiling/mcprof.py trace main=/home/alex/mc-small/build-main/motioncorr --data /home/alex/mc-small/data96 --star movies.star --work /home/alex/mc-small/runs/trace96_main --cpus 96-103 --gpu-uuid GPU-eddb42fe-4f9a-adde-76d3-b924e14add54 --runner-cpus 120-121 --settle-timeout 600 --source main=/home/alex/mc-small/src-main --commit main=7d64043 --keep sqlite -- --use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8 --ingest nvcomp`

## Device

Instrument: Nsight Systems trace (--trace=cuda,nvtx --cuda-memory-usage=true): traced process, host times inflated.

CUDA device timing in the traced process: off.

Traced window 28466.5 ms, 96 movies. Device busy (union of kernels, copies, memsets) 13833.8 ms (48.6%); idle 14632.8 ms. Kernels 100824 (11935.5 ms summed), copies 12979 (1987.0 ms, 142943.2 MiB). Overlap between kernels and copies 88.65 ms. Streams with kernels: 193.

Per stage, steady-state median per movie (movies after the first); first movie separately. Host walls here are inflated by tracing; use `mcprof run` or `--profile` for host time.

| stage | wall ms | busy ms | kernel ms | copy ms | busy % | idle ms | idle gaps | kernels | sync calls | sync blocked idle ms | malloc/free | copy MiB | pageable copies | mem peak MiB | first movie wall ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| movie: unattributed | 0.29 | 0.00 | 0.00 | 0.00 | 0% | 0.29 | 21 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 0.52 |
| setup | 1.85 | 0.00 | 0.00 | 0.00 | 0% | 1.85 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 1.67 |
| read gain | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 101.32 |
| session and device ingest | 81.41 | 38.91 | 28.83 | 11.19 | 48% | 41.54 | 55 | 12 | 27 | 0.97 | 5/0 | 130.7 | 18 | 2932 | 377.50 |
| host read movie | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| allocate host sum | 0.03 | 0.00 | 0.00 | 0.00 | 0% | 0.03 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.02 |
| gain and sum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2932 | 0.07 |
| hot pixels | 21.29 | 0.32 | 0.31 | 0.01 | 1% | 20.95 | 12 | 6 | 10 | 1.31 | 6/6 | 0.0 | 4 | 2933 | 87.51 |
| fix defects | 2.49 | 0.02 | 0.01 | 0.01 | 1% | 2.47 | 10 | 2 | 9 | 0.69 | 3/3 | 0.0 | 7 | 2932 | 4.57 |
| release preprocessing | 0.42 | 0.00 | 0.00 | 0.00 | 0% | 0.42 | 1 | 0 | 2 | 0.34 | 0/1 | 0.0 | 0 | 2932 | 0.35 |
| global fft | 22.02 | 21.58 | 21.58 | 0.00 | 98% | 0.43 | 170 | 169 | 1 | 0.14 | 0/0 | 0.0 | 0 | 2877 | 22.10 |
| power spectrum | 0.08 | 0.00 | 0.00 | 0.00 | 0% | 0.08 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.08 |
| global alignment | 10.90 | 7.13 | 7.11 | 0.02 | 65% | 3.81 | 34 | 19 | 15 | 0.63 | 0/0 | 0.0 | 14 | 2877 | 8.72 |
| allocate reconstruction | 0.02 | 0.00 | 0.00 | 0.00 | 0% | 0.02 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 2877 | 0.03 |
| global ifft | 22.20 | 21.76 | 20.00 | 1.76 | 98% | 0.41 | 193 | 168 | 25 | 0.21 | 0/0 | 1304.3 | 0 | 2877 | 22.17 |
| patch alignment | 44.17 | 19.88 | 19.82 | 0.05 | 45% | 24.30 | 497 | 456 | 51 | 2.28 | 17/3 | 0.0 | 38 | 3026 | 44.66 |
| fit polynomial | 1.74 | 0.00 | 0.00 | 0.00 | 0% | 1.74 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 3026 | 1.73 |
| release alignment | 3.26 | 0.00 | 0.00 | 0.00 | 0% | 3.26 | 1 | 0 | 15 | 2.06 | 0/14 | 0.0 | 0 | 3026 | 3.02 |
| dose weighting | 42.09 | 34.67 | 27.00 | 7.56 | 82% | 7.41 | 221 | 217 | 4 | 0.49 | 0/0 | 54.3 | 2 | 2877 | 76.06 |
| movie teardown | 7.15 | 0.00 | 0.00 | 0.00 | 0% | 7.15 | 1 | 0 | 5 | 4.05 | 0/4 | 0.0 | 0 | 2877 | 7.11 |
| submit model and plot | 0.16 | 0.00 | 0.00 | 0.00 | 0% | 0.16 | 1 | 0 | 0 | 0.00 | 0/0 | 0.0 | 0 | 161 | 0.31 |

Outside movies (totals):

| segment | wall ms | busy ms | idle ms | kernels | malloc/free |
|---|---|---|---|---|---|
| before first movie | 4.80 | 0.00 | 4.80 | 0 | 0/0 |
| between movies | 22.49 | 0.00 | 22.49 | 0 | 0/0 |
| after last movie | 2367.82 | 0.00 | 2367.82 | 0 | 0/3 |

Device 0 allocation high-water 3026 MiB at stage `patch alignment` (movie 0); residual at end 0 MiB. traced CUDA allocations (cudaMalloc/cuMemAlloc and static symbols); excludes CUDA context, cuFFT/driver internal and untraced memory.

Top kernels by device time:

| kernel | launches | total ms | mean us | max us | share |
|---|---|---|---|---|---|
| prime_fft_factor | 23136 | 4085.75 | 176.6 | 238.9 | 34.2% |
| inflate_kernel | 384 | 2344.42 | 6105.3 | 6268.8 | 19.6% |
| regular_fft_factor | 23136 | 1731.31 | 74.8 | 85.3 | 14.5% |
| regular_bluestein_fft | 2400 | 740.41 | 308.5 | 317.1 | 6.2% |
| fourierShiftKernel | 5108 | 521.18 | 102.0 | 1775.2 | 4.4% |
| interpolateAndAccumulatePolynomialKernel | 2304 | 405.31 | 175.9 | 183.9 | 3.4% |
| postprocess_kernel | 4704 | 316.75 | 67.3 | 74.7 | 2.7% |
| preprocess_kernel | 4608 | 297.65 | 64.6 | 66.9 | 2.5% |
| cropAndGroupPatchResidentKernel | 2400 | 248.46 | 103.5 | 113.4 | 2.1% |
| applyDoseWeightKernel | 2304 | 240.87 | 104.5 | 107.4 | 2.0% |
| adler32StripsKernel | 384 | 219.68 | 572.1 | 584.6 | 1.8% |
| fusedU16FlipGainAndSumKernel | 384 | 201.38 | 524.4 | 558.9 | 1.7% |
| scaleComplexKernel | 96 | 160.11 | 1667.9 | 1670.8 | 1.3% |
| regular_fft | 5204 | 108.01 | 20.8 | 233.6 | 0.9% |
| regular_fft_c2r | 5108 | 91.68 | 17.9 | 181.9 | 0.8% |

Blocking calls (whole trace; blocked idle = host time in the call while the device was idle):

| class | calls | host ms | blocked idle ms |
|---|---|---|---|
| synchronous memcpy | 9907 | 3625.56 | 397.28 |
| device sync | 864 | 2538.24 | 70.11 |
| event sync | 1536 | 1038.20 | 57.88 |
| free (implicit sync) | 2980 | 807.80 | 807.80 |
| stream sync | 480 | 83.56 | 24.92 |

Copies by direction and memory kind (whole trace):

| direction src->dst | n | MiB | device ms | GB/s |
|---|---|---|---|---|
| Device-to-Device Device->Device | 2304 | 125214.8 | 169.32 | 775.42 |
| Host-to-Device Pinned->Device | 1536 | 12309.3 | 1030.56 | 12.52 |
| Device-to-Host Device->Pageable | 2504 | 5216.1 | 760.29 | 7.19 |
| Device-to-Host Device->Pinned | 1152 | 134.9 | 11.98 | 11.81 |
| Host-to-Device Pageable->Device | 5483 | 68.1 | 14.84 | 4.81 |

Byte counts are invariant across captures; rates are not (contention, tracing).
