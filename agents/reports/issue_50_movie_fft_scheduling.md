# Issue #50: resident movie FFT scheduling — bounded barrier removal

**Owner scope:** CUDA session FFT lifecycle only (`src/acc/cuda/cuda_movie_session.cu`,
cuFFT plan / shared workspace / transform paths) plus this report. No other production
source was modified.

**Status:** Implemented and measured. Numerically exact against the base commit.
Performance effect is real but small and **not** demonstrable at process level.

---

## 1. Provenance

| Item | Value |
|---|---|
| Base commit | `a11f2f15d8a3f6a8c93f43ca0458e7ff63e08267` (tip of `origin/feat/issue-50-cuda-end-to-end-residency`) |
| Branch | `t3code/optimize-movie-fft-scheduling` (isolated worktree; not pushed) |
| Host | `4GPUs` / `4-gpu-vm`, NVIDIA A100 80GB PCIe, GPU 1, driver 570.86.10 |
| CUDA toolkit | 12.8.61 |
| Build | `-DCUDA=ON -DTIMING=ON -DCMAKE_CUDA_ARCHITECTURES=80`, `CMAKE_BUILD_TYPE` empty |
| Actual CUDA flags | `-std=c++17 --generate-code=arch=compute_80,code=[compute_80,sm_80]` |
| Matched case | movie `00021`, 3710 × 3838 × 24, gain + dose weighting, 5 × 5 patches, `--j 8 --group_frames 3 --bfactor 150 --angpix 1.06 --dose_per_frame 1.277 --seed 1` |

Source SHA-256 of `src/acc/cuda/cuda_movie_session.cu`:

| Build | Source SHA-256 | Binary SHA-256 |
|---|---|---|
| baseline (`a11f2f1`) | `b47d63cb2338b3a59d682764f2a54e019f5c0509a4bd0a20f3f288889fdfddc6` | `c92f90c5b5271541e15200e19791dbb3a61d892b960d64fe0c8288fef12f69db` |
| candidate | `403b485c6bda6b33a51f95a683a89c20bfd59990a402c62c6446cbb9a39936ec` | `b76499792c9bbab0e7f78c07d8280bddfea2bb1c3a95b14fd4631507df4ff090` |

Inputs: STAR `afc1445e…`, movie TIFF `df298b1b…`, gain `8919cdc7…`, 24-movie STAR `669a4e65…`.
Raw artifacts on the host under `/home/alex/MotionCorr-issue50-fftsched/`
(`evidence2/`, `evidence-nsys/`, `evidence-full24/`, `evidence-sanitizer/`).

---

## 2. The change

In `computeGlobalForwardFFT` and `computeGlobalInverseFFT`, the per-frame
`cudaDeviceSynchronize()` inside each transform loop is replaced by a non-blocking
`cudaGetLastError()`, and a single `cudaDeviceSynchronize()` is added after the
inverse loop. The forward loop needed no new barrier: one already exists after
`scaleComplexKernel`.

With `fft_batch_size = 1` and 24 frames this reduces **48 whole-device barriers per
movie to 2**. Nothing else changes — no plan shape, no batch size, no allocation, no
transfer, no arithmetic.

## 3. Why this is ordering-safe

Every operation touching `d_fft_work`, `d_inverse_tile`, `d_Fframes` and `d_Iframes`
is issued by one host thread onto the **legacy default stream**, so the two hazards
the removed barriers appeared to guard are already resolved by stream ordering:

- **Shared cuFFT work area.** All plans are bound to one `d_fft_work` via
  `cufftSetWorkArea`. Two executions issued back to back on the same stream cannot
  overlap, so the reuse hazard is resolved by issue order. `cudaDeviceSynchronize()`
  adds ordering only *across* streams, and there are none.
- **Inverse tile reuse.** Iteration *k+1*'s `cudaMemcpy` into `d_inverse_tile` is
  write-after-read against iteration *k*'s `cufftExecC2R`. Same-stream ordering covers
  it. Note the code already depended on this: `cudaMemcpy` device-to-device performs
  **no host-side synchronization**, so the barrier was never what ordered the copy.

Verified on the build host, not merely in source: `flags.make` contains no
`--default-stream=per-thread`, `CMAKE_CUDA_FLAGS` is empty and `CUDAFLAGS` is unset.
No `cufftSetStream`, `cudaMemcpyAsync` or explicit stream appears anywhere in
`src/acc/cuda/`. The micrograph loop is serial; none of the `movie_session->` call
sites sit inside an OpenMP region (`--j 8` binds only to `parallel for` loops that
contain no session calls).

**Error reporting is preserved, and one gap was closed.** Asynchronously detected CUDA
faults are sticky, so a later synchronization still returns them — nothing is missed.
Per-batch `cudaGetLastError()` keeps launch-failure attribution at the batch that
caused it. The added post-loop barrier in the inverse is **required**, not cosmetic:
without it `computeGlobalInverseFFT` would return `true` after an asynchronous fault,
and the error would surface later in `alignPatchDevice` — which does not override
`HANDLE_ERROR` and therefore aborts the process instead of taking the designed CPU
fallback. The change as committed converts that latent hard-abort path into the
intended graceful fallback.

## 4. Performance evidence

Twelve unprofiled runs, ABBA-balanced (`base cand cand base` alternating) to cancel
ordering bias, whole-device VRAM sampled at 5 ms (~740 samples/run). Profiled and
unprofiled runs are never compared.

| Metric | baseline (n=6) | candidate (n=6) | delta |
|---|---:|---:|---:|
| Process wall, median | 3.505 s (sd 0.150) | 3.485 s (sd 0.067) | −0.020 s — **not resolvable** |
| `global FFT`, median | 22.471 ms (sd 0.140) | 21.741 ms (sd 0.066) | **−0.729 ms** |
| `global iFFT`, median | 23.286 ms (sd 4.025) | 22.135 ms (sd 0.084) | **−1.151 ms** |
| Whole-device VRAM peak | 3537 MiB (sd 0) | 3537 MiB (sd 0) | **0** |
| Host peak RSS, median | 1,633,726 KiB | 1,633,782 KiB | unchanged |

Both FFT stages separate cleanly — baseline FFT min 22.277 > candidate max 21.913;
baseline iFFT min 22.834 > candidate max 22.261 — so the ~1.88 ms combined gain is a
real effect, not sampling noise. A standalone cuFFT microbenchmark at the exact
production shape independently predicts it: −2.15 ms at `-O0`, −2.76 ms at `-O2`.

**The process-level number is noise and is not claimed as a win.** −0.020 s against a
standard deviation of 0.150 s is unresolvable; `apply gain and initial sum` alone
swings 373 → 461 ms between baseline runs, roughly 50× the size of this effect. The
honest summary is: **measurable at the stage timer, invisible at process level,
exactly VRAM-neutral.**

### Scale of the opportunity

| Component | Cost | Share of ~3,500 ms process |
|---|---:|---:|
| Whole cuFFT lifecycle (forward + inverse + plans) | ~53 ms | ~1.5% |
| — of which per-frame barriers (this change) | ~1.9 ms | **~0.05%** |
| cuFFT plan construction (R2C 5.5 ms + C2R 2.1 ms) | 7.6 ms | 0.22% |

The barriers were not a material cost. This change is justified as free and safe —
and for closing the inverse error-reporting gap — not as a speedup.

## 5. Numerical gates

All exact against the `a11f2f1` baseline binary on the same host:

- **Movie 00021, all 12 runs:** MRC pixel data identical — 0 differing bytes of
  56,955,920 (14,238,980 float pixels), single shared data-block hash
  `09680a6a4b3914f97c5befbf87c53c2425ab0658`.
- **Per-movie STAR bit-identical** across all 12 runs, covering all five blocks:
  `data_general`, the 24 `data_global_shift` rows, `data_local_motion_model`,
  `data_hot_pixels`, `data_local_shift`.
- **Joint STAR identical** after normalising the run-specific output path.
- **Full 24-movie dataset: 24/24 exact** on pixel data and per-movie STAR.
- **Nsight:** peak active traced allocation **3,097.0 MiB on both**; transfer volumes
  identical to the byte — 2,735.358 MB device-to-device, 1,434.797 MB host-to-device,
  113.915 MB device-to-host, 57.011 MB memset.
- **`compute-sanitizer --tool memcheck`: 0 errors.**

### On the VRAM claim specifically

The whole-device figure above is a **5 ms NVML sample peak, which is a lower bound on
the true instantaneous peak** — a sampler can step over a short transient. This is not
hypothetical on this dataset: on the pre-optimization baseline a 50 ms sampler missed
the real peak by more than 1 GiB (6,033 MiB sampled against 6,636 MiB traced), because
the peak was a ~22 ms transient. 5 ms sampling reduces but does not eliminate that risk.

The VRAM-neutrality claim here therefore does **not** rest on sampling. It rests on the
change performing no allocation at all: the Nsight allocation-event traces for baseline
and candidate are identical — same peak active traced allocation (3,097.0 MiB), same
transfer volumes to the byte. Barriers were removed; no buffer, plan, workspace or copy
was added, resized or reordered. The sampled 3537 MiB agreeing exactly across both arms
(sd 0 over ~740 samples per run, 12 runs) is corroboration of that, not the basis for it.

What this does **not** establish is that 3,537 MiB is the true whole-device peak, or
that the 3,584 MiB ceiling is met with certainty. It establishes that this change does
not move whichever peak is real.

Comparison is against the **data block only**: `rwMRC.h` writes a
`"Relion <date> <time>"` label at header offset 224, so whole-file MRC hashes differ
between two runs of the *same* binary. Any gate hashing whole MRC files is unsound.

**CPU Gate 2 is not addressed and is not relaxed.** The inherited relative-image-RMSE
failure (0.007130747 against the 0.001 limit) is untouched by this change and remains
open. Nothing here supports any claim of cuFFT/FFTW parity.

## 6. Rejected: larger FFT batch

Measured at production shape, the cuFFT work area is 54.35 MiB and the one-frame
inverse tile is 54.35 MiB. Moving to `fft_batch_size = 2` grows the inverse tile alone
by **+54.35 MiB** against **47 MiB** of headroom (3,584 MiB cap − 3,537 MiB sampled
peak), before any growth in the work area. **Batch increase is blocked by the VRAM
gate**, which confirms the existing in-code comment with a measured number. Double
buffering the inverse tile to overlap copy with transform is blocked for the same
reason, and would be worth at most ~1.8 ms.

## 7. Integration risks

1. **The invariant is now load-bearing but still implicit.** Correctness rests on
   "one thread, one default stream." The removed barriers were accidental insurance.
   If `--default-stream=per-thread` is ever added to `CMAKE_CUDA_FLAGS`, or if
   micrograph processing is parallelised across host threads, the shared `d_fft_work`
   and `d_inverse_tile` become a silent data race — wrong pixels, no error. The
   durable fix, deliberately **not** bundled here to keep the change narrow: create one
   `cudaStream_t` in `initialize()`, `cufftSetStream` all four plans onto it, and issue
   every kernel and copy in the class on it. That is what the design addendum §5.1 asks
   for and it should be a follow-up.
2. **Error attribution is coarser in the forward path.** An asynchronous fault is now
   reported at the post-scaling barrier rather than at the faulting batch. Detection,
   the `false` return and the fallback are unchanged; only the logged line moves. The
   inverse path is strictly *better* than before (§3).
3. **VRAM headroom is 47 MiB and this change consumes none of it** — but it also frees
   none. Concurrent Issue #50 work (GPU hot-pixel statistics, which adds reduction and
   compaction scratch) must be re-measured on the combined commit; deltas must not be
   added.
4. **Unexercised paths.** `CUDA=OFF` builds clean from this commit on the same host
   (the change sits inside `#ifdef _CUDA_ENABLED`, so this is expected rather than
   informative). Still **not** covered: CPU fallback under injected allocation failure,
   EER, early binning, explicit defect maps, gain rotation/flip, no-dose-weighting, and
   power-spectrum mode. The change is inside two transform loops and is mode-independent,
   but that is an argument, not evidence.
5. **One-shot 24-movie walls** were 54.14 s baseline and 55.05 s candidate. **n=1 each
   — no timing conclusion should be drawn from these**; they were correctness runs.

## 8. Reproduction

```
# microbenchmark (isolates barrier cost at production shape)
nvcc -O2 -arch=sm_80 fft_sched_bench.cu -o fft_sched_bench -lcufft && ./fft_sched_bench 1 20

# matched balanced A/B, 12 runs
flock -w 1800 /tmp/motioncorr-bench.lock -c ./run_evidence2.sh 3

# Nsight allocation high-water and transfer bytes
./nsys_run.sh

# full 24-movie exactness
./full24.sh
```
