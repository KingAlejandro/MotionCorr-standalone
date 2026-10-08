# MotionCorr on one A100: full execution profile

**Date** 2026-10-01 · **Host** `4GPUs` (4-gpu-vm), CPU mask `96-103`, THP `madvise`
**Device** GPU 0 = `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`, A100 80GB PCIe, 108 SMs, driver 570.86.10, CUDA 12.8
**Source** `main` @ `1d7e13f` (tree `fbe9469`, clean) · **Build** Release `-O3`, `sm_80`, `-lineinfo`, `-g -fno-omit-frame-pointer`
**Workload** 1 movie `20170629_00022_frameImage.tiff` (3838×5760, 24 frames), canonical options:
`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1 --gpu 0 --j 8`

Every run took `flock /tmp/motioncorr-bench.lock` and passed a settle gate
(no `cc1plus`/`nvcc`/`cicc`/`ptxas`, zero foreign compute apps on the target GPU by UUID,
load1 < 2.0). The box was genuinely idle: all four GPUs at 1 MiB, load1 0.02 at start.

---

## 1. Measurement validity first

`perf_event_paranoid=4` blocks unprivileged CPU sampling, and GPU hardware counters
return `ERR_NVGPUCTRPERM`. Both were obtained by running **the profiler** under `sudo`.
No persistent sysctl or driver parameter was changed on this shared host.

Ten nsys profiles were taken at different instrumentation levels. The device-side
work is bit-stable across all of them, which is what licenses comparing them:

| quantity | across 9 profiles |
|---|---|
| kernel launches | **1066** in every single-movie profile |
| memcpy operations | **435** in every single-movie profile |
| H2D bytes | **1,434,806,904** in every single-movie profile |
| total kernel time | **109.53 – 109.64 ms** (0.1 % spread) |
| memcpy *time* for those same bytes | **176.6 – 383.4 ms** (2.2× spread) |

So: **report transfer bytes as a number and transfer time as a range.** The same
caution killed one early reading — `cuModuleLoadData` showed 732 ms in the
CPU-sampled profile but 27–58 ms everywhere else. It is a sampling artifact, not a cost.

Unprofiled baseline wall, 3 reps each, same binary source:
`build-plain` 2.526 / 2.628 / 2.574 s · `build-prof` (frame pointers) 2.631 / 2.496 / 2.508 s
— frame pointers cost nothing measurable, so the profiling binary is representative.

---

## 2. The headline

**The GPU is idle for 83 % of the run.** Not because the kernels are bad — because
almost nothing in the pipeline is on the GPU, and what is on it runs strictly serially.

| | one movie |
|---|---|
| traced span (least-perturbed profile `p7`) | 2375.8 ms |
| GPU busy (union of kernel ∪ memcpy ∪ memset) | **403.5 ms (17.0 %)** |
| ├ kernels | 109.6 ms |
| ├ transfers | 293.8 ms |
| └ memsets | 0.038 ms |
| GPU idle | **1972.3 ms (83.0 %)** |
| **device-side overlap achieved** | **exactly 0.000000 ms** |

That last line is not a rounding statement. `sum(all device intervals)` equals
`union(all device intervals)` to the nanosecond in all three clean profiles — **no two
device operations were ever in flight at the same time.** The cause is structural:

- all 1066 kernels and all 435 copies are on **one stream (id 7)**, in **one context**
- **one** host thread issues every CUDA call
- all 348 `cudaMemcpy` calls are the **synchronous** form
- all 274 H2D copies are from **pageable** host memory (which cannot overlap by construction)

---

## 3. Where the wall clock goes

Overhead-corrected: `p10` traces NVTX+OSRT but not CUDA, so it carries no CUPTI cost
(movie = 1789 ms); `p8` adds CUDA tracing (movie = 2101 ms). CUPTI inflation lands almost
entirely on the two stages that make many CUDA calls.

| stage | wall (p10, no CUPTI) | GPU busy | GPU idle | what it is |
|---|---|---|---|---|
| `read movie` | 420.7 ms | 0 | 100 % | TIFF decode, 8 threads |
| `write output` | 203.7 ms | 0 | 100 % | MRC write |
| `gain and sum` | 197.4 ms | ~97 % | 3 % | 1.36 GiB H2D + 1 kernel |
| *(unmarked)* after `read movie` | ~250 ms | ~0 | ~100 % | `CudaMovieSession::initialize` |
| *(unmarked)* after `write output` | ~192 ms | 0 | 100 % | session teardown |
| `patch align` ×25 | 115.6 ms | 10 % | 90 % | 25 serial patch solves |
| `read gain` | 108.9 ms | 0 | 100 % | re-reads gain.mrc **every movie** |
| `dose weighting` | 63.9 ms | ~60 % | 40 % | |
| `fix defect` | 56.1 ms | 0 | 100 % | |
| `detect hot` | 43.9 ms | ~1 % | 99 % | |
| `global ifft` / `global fft` | 24.0 / 22.3 ms | ~89 / 88 % | | |
| `prep patch` ×25 / `global alignment` | 19.5 / 15.1 ms | 35 / 43 % | | |
| `fit polynomial`, `power spectrum`, `binning` | ≤2 ms | | | |
| **after the movie** | **811 ms** | 0 | 100 % | STAR + `logfile.pdf` |

### The four things that are not compute

1. **TIFF decode — 421 ms.** `libdeflate_zlib_decompress` is **47 % of all CPU samples**
   and `Image<float>::read` is **64.7 % inclusive**. It is the one stage that uses all 8
   cores, which is why it dominates CPU time but only ~20 % of movie wall.
2. **Ghostscript — 790 ms**, four `system()` calls building `logfile.pdf`.
   **This is per *job*, not per movie**: the 3-movie run also made exactly 4 `system()`
   calls (876 ms). Across 24 movies it amortises to ~33 ms/movie. On a *one-movie* run it
   is 31 % of wall, which is a trap for anyone benchmarking with a single movie.
3. **CUDA session setup — ~250 ms** (3 GiB `cudaMalloc` + cuFFT plan creation), during
   which **70 % of CPU samples are the 7 idle OpenMP workers busy-spinning in `libgomp`**.
   Under the 8-CPU cap they are competing with the thread doing the real work.
4. **CUDA session teardown — ~192 ms**, of which 191.8 ms is the main thread blocked in
   `poll()` inside the driver, releasing the 3 GiB. Only 3 CPU samples land in this
   window — the thread is not running at all.

**Per-movie steady state** (3-movie run): 1850 / 1721 / 1645 ms. The first movie carries
~200 ms of warm-up (SM clock idles at 210 MHz of 1410 with persistence mode off).

---

## 4. Transfers: the one clear, measured win

All 274 H2D copies are pageable. I measured the headroom directly on the same device
with the same payload and the same 24-chunk pattern rather than quoting a spec sheet:

```
PAGEABLE (malloc)      1,434,806,880 B in 24 chunks: 173.37 ms =  8.28 GB/s
PINNED (cudaHostAlloc) 1,434,806,880 B in 24 chunks:  61.55 ms = 23.31 GB/s
```

**2.82×.** The measured pageable rate (8.28 GB/s) matches the fastest in-application
rate observed (8.13 GB/s in `p1`), which is good evidence that 8.1–8.3 GB/s is the real
unprofiled rate and the slower profiles are instrument effects. Pinning the frame
staging buffer is worth **~112 ms per movie** — ~6.5 % of steady-state movie wall, and it
is also the precondition for ever overlapping transfer with compute.

Size distribution: 27 large copies (≥2 MiB) carry 99.99 % of the bytes; 267 of the 435
copies are ≤128 B and cost 0.45 ms in total.

### Host blocked vs GPU working

| blocking call | n | host blocked | GPU working | pure overhead | efficiency |
|---|---|---|---|---|---|
| `cudaMemcpy` | 348 | 309.1 ms | 288.4 ms | 20.6 ms | 93.3 % |
| `cudaEventSynchronize` | 369 | 42.9 ms | 30.2 ms | 12.8 ms | 70.3 % |
| `cudaDeviceSynchronize` | 53 | 36.3 ms | 33.9 ms | 2.5 ms | 93.2 % |
| `cudaMalloc` | 231 | 20.4 ms | 5.9 ms | 14.5 ms | 28.9 % |
| `cudaFree` | 231 | 19.4 ms | **0.0 ms** | 19.4 ms | **0 %** |
| `cudaLaunchKernel` | 349 | 11.1 ms | 2.7 ms | 8.4 ms | 24.4 % |
| **total** | | **439.1 ms** | **361.0 ms** | **78.1 ms** | 82.2 % |

The synchronisations are *not* the problem — when the host blocks, the GPU is genuinely
working 82 % of that time. Removing a `cudaDeviceSynchronize` buys ~2.5 ms. The 78 ms of
pure overhead is dominated by allocator churn: **231 `cudaMalloc` + 231 `cudaFree` per
movie, 3.6 GiB of churn**, plus **109 `cuModuleLoadData` + 109 `cuModuleUnload`** (cuFFT
plans created and destroyed rather than cached) at 57.6 + 4.0 ms.

---

## 5. Kernel quality (Nsight Compute, all 1066 launches)

The big kernels are in good shape. Nothing here is the bottleneck.

| kernel | n | SM % | MEM % | occ % | reading |
|---|---|---|---|---|---|
| `prime_fft_factor<101>` (cuFFT) | 72 | 72.5 | **97.3** | 76.8 | at bandwidth peak |
| `prime_fft_factor<53>` (cuFFT) | 97 | 68.9 | **96.7** | 93.0 | at bandwidth peak |
| `prime_fft_factor<19>` (cuFFT) | 72 | **81.0** | 45.3 | 93.3 | compute-bound, good |
| `applyDoseWeightKernel` | 24 | **76.7** | 12.2 | 96.0 | compute-bound, good |
| `scaleComplexKernel` | 26 | 12.7 | **84.7** | 84.3 | pure bandwidth, near peak |
| `preprocess`/`postprocess` (cuFFT) | 97 | 42–48 | **84–85** | 89 | fine |
| `cropAndGroupPatchResidentKernel` | 25 | 62.9 | 50.3 | 83.0 | balanced |
| `interpolateAndAccumulatePolynomial` | 24 | 58.3 | 46.3 | 89.4 | balanced |
| `fourierShiftKernel` | 54 | 31.7 | 65.0 | 84.7 | memory-bound |
| `fusedGainAndSumKernel` | 1 | **6.2** | 45.5 | 97.5 | longest single kernel (2.84 ms), latency-bound |
| `computeReferenceKernel` | 54 | 4.0 | 28.8 | **12.0** | grid too small to fill 108 SMs |
| `findPeakAndInterpolateKernel` | 54 | 1.5 | 1.1 | **11.7** | grid = 24 blocks |
| `combinePartialsKernel` | 3 | 0.0 | 0.1 | **1.6** | single block (reduction finalizer) |
| `updateDefectKernel` | 1 | 0.0 | 0.4 | **3.5** | single block |

The underfilled kernels are real but immaterial — together they are well under 1 ms of
the 109.6 ms. **Kernel efficiency is not what is costing this run; device occupancy of
the wall clock is.**

---

## 6. Device memory

Peak **2.98 GiB** resident, reached at ~1450 ms, released completely at movie end
(residual 1.3 KiB). 436 allocations / 266 frees, 3.6 GiB of churn. On an 80 GB card the
run never exceeds **3.7 %** of the device — and the whole reservation is built and torn
down per movie, costing ~250 ms in and ~192 ms out.

---

## 7. What the evidence supports doing

Ordered by measured value, for steady-state per-movie wall of ~1.7 s:

1. **Pin the H2D staging buffer** — measured 2.82×, **~112 ms/movie**. Also the
   precondition for any transfer/compute overlap.
2. **Hoist `read gain` out of the per-movie loop** — ~109 ms/movie for a file that
   never changes (`Igain.read()` at `src/motioncorr_runner.cpp:1333`).
3. **Keep the `CudaMovieSession` alive across movies** — ~250 ms setup + ~192 ms
   teardown per movie, both ~100 % GPU-idle. Sizes are constant across a dataset.
4. **Cache the cuFFT plans** — 109 module load/unload pairs per movie, ~62 ms.
5. **`OMP_WAIT_POLICY=passive`** (or a smaller `GOMP_SPINCOUNT`) — stops 7 workers
   busy-spinning through the serial GPU phases under an 8-CPU cap. Free to test.
6. Only then: streams/async for overlap, and don't bother micro-optimising kernels.

Not worth doing: removing synchronisations (82 % of blocked time is real GPU work),
or tuning the small kernels (<1 ms total).

**One caveat on scope.** This is one movie on one GPU, and movie 00022 was chosen
because 00021 is documented as unrepresentative. Items 1–5 are per-movie costs and
should scale; the ghostscript 790 ms is per-job and must not be counted per movie.

---

## 8. Artifacts

| file | contents |
|---|---|
| `timeline.svg/.png` | stage timeline vs actual GPU activity |
| `flamegraph_motioncorr.svg/.png` | CPU flame graph, motioncorr process |
| `flamegraph_all.svg` | same, including ghostscript children |
| `vram.svg/.png` | device memory resident over time |
| `data/analysis_p3,p5,p7.txt` | full per-profile analysis |
| `data/stages_p8.txt`, `gaps_p8.txt` | stage and GPU-idle attribution |
| `data/syncs_p8.txt` | streams, blocking calls, transfer distribution |
| `data/compare.txt`, `xfer.txt` | cross-profile invariants and transfer rates |
| `data/ncu_summary.txt` | per-kernel hardware counters |
| `data/flame_main.folded` | folded stacks (re-renderable) |

Raw `.nsys-rep` / `.sqlite` / `ncu_all.csv` remain on `4GPUs` at
`/home/alex/mc-profile-20261001/`. The NVTX instrumentation is in `src-nvtx/` there
(one macro branch on the existing `RCTIC`/`RCTOC` markers, verified balanced 35/35);
it is **not** applied to this repo.
