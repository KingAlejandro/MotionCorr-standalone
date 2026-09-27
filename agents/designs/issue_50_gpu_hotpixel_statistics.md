# Issue #50 Addendum: GPU Hot-Pixel Statistics and Detection

**Status**: Implementation design (PR #51 follow-on)
**Base**: `a11f2f1` (`origin/feat/issue-50-cuda-end-to-end-residency`)
**Scope owner**: resident CUDA session statistics + the hot-pixel section of `src/motioncorr_runner.cpp`

The Issue #50 addendum (§4, §"Next optimization decisions" item 3) defers removal of the
initial-sum download to "a separate GPU statistics and mask design that preserves mean/stddev,
threshold boundary decisions and mask order". This document is that design.

---

## 1. Goal and non-goals

Remove the 54.32 MiB initial-sum device-to-host copy (`cuda_movie_session.cu:358-360`) and the
host mean/std/threshold scan (`motioncorr_runner.cpp:1354-1400`) on the resident CUDA path,
**without changing a single corrected pixel, shift, or metadata field**.

Non-goals: changing the CPU path, the streaming CUDA path, `CUDA=OFF` behaviour, the FFT
lifecycle, or any Gate tolerance. Gate 2 is not relaxed; the target here is strictly stronger
than Gate 2 — bit-identical output against the pinned `a11f2f1` CUDA reference.

## 2. What the existing code actually requires

`mean`, `std` and `threshold` (all `RFLOAT` = `double`; `RELION_SINGLE_PRECISION` is never
defined) are consumed in exactly three places:

1. `motioncorr_runner.cpp:1395` — the comparison `Isum[n] > threshold`.
2. `motioncorr_runner.cpp:1407-1408` — `frame_mean = mean/n_frames`, `frame_std = std/n_frames`,
   passed to `rnd_gaus(float, float)` at `:1461` and therefore **narrowed to `float`**.
3. `motioncorr_runner.cpp:1367` — the log line. Not covered by Gate 1 or Gate 2.

Therefore bit-identical `mean`/`std` are **not** required. What is required is that (1) yields the
same set and (2) yields the same two `float`s. This is the enabling observation; everything below
is about proving those two conditions rather than assuming them.

Two further contract facts, verified in source:

- **No cross-index dependence in the threshold scan.** `:1394-1400` reads and writes only
  `bBad[n]` within iteration `n`, so
  `pushed(n) <=> (Isum[n] > threshold) AND NOT premask(n)`, where `premask` is the defect-file
  mask plus the gain-zero mask. A device that knows nothing of the pre-mask can emit the raw
  above-threshold set and the host can filter it afterwards in ascending `n`, reproducing `bBad`,
  `n_bad` and `mic.hotpixelX/Y` (contents **and** push order) exactly.
- **The RNG branch sequence is a pure function of `bBad` geometry.** `n_ok` (`:1436-1453`) depends
  only on `bBad` and the image bounds, never on frame pixel values or on `iframe`. `rand()` and
  `rnd_gaus` share one `srand` stream (`src/funcs.cpp:570-625`), so a single changed branch shifts
  every later draw — but the branch sequence can be predicted before any draw is consumed.

## 3. Exactness argument

The CPU reduction order is not fixed: it varies with `--j` (measured: at N = 3710x3838,
`std` = 2.8866805473739832 at `--j 1` vs 2.8866805473739943 at `--j 8`). It is, however,
bit-reproducible run-to-run at a fixed thread count (measured: 10/10 identical at `--j 8`).
So "match the CPU bitwise" is ill-posed, and the design does not attempt it.

For a fixed set of inputs, the summation-order bound uses
`gamma_N = N*u/(1 - N*u)`, `u = 2^-53`. The mean can have signed addends,
so its bound uses `sum|x|/N`, not `|sum x|/N`. The squared deviations are
non-negative. Error in the mean also contributes to their variance at second
order; near-constant input makes that contribution material. There is no
data-independent float-ULP argument for accepting GPU statistics.

**Guard 1 (threshold band).** Rather than rely on that bound, verify it per movie. The collect
kernel counts `band = #{n : |(double)Isum[n] - threshold| <= guard}` with
`guard = 4*gamma_N*mean(|Isum|) + 2*|hotpixel_sigma|*gamma_N*std +
2*|hotpixel_sigma|*gamma_N^2*mean(|Isum|)^2/std`. The absolute mean
accounts for signed values whose sum nearly cancels; the last term covers the
mean error's second-order contribution to std. A zero or non-finite std
falls back. Since the CPU and GPU
thresholds each lie within one bound of the exact value, they lie within `guard` of each other; if
no pixel lies within `guard` of the computed threshold, no pixel can lie between the two
thresholds, so the emitted set is provably identical to the CPU's. `band != 0` falls back.

**Guard 2 (`rnd_gaus` reachability).** `frame_mean`/`frame_std` are observable only if some bad
pixel has `n_ok <= NUM_MIN_OK`. Compute `n_ok` for every entry of `bad_xs`/`bad_ys` after `bBad`
is final and **before** `init_random_generator`. If all `n_ok > 6`, `rnd_gaus` is unreachable and
these values cannot affect output. If any `n_ok <= 6`, download the sum and run the
original host statistics and scan. This keeps the Gaussian RNG parameters exact
without a second floating-point proof.

Also fall back on non-finite `mean`/`std`, on any CUDA error, and on hit-buffer overflow.

## 4. Device API

```cpp
bool applyGainDefectsAndSum(raw_frames, gain_ref, unaligned_sum, bool download_sum);
bool reduceUnalignedSum(double &sum1, double &sum_abs);
bool reduceUnalignedSumSqDev(double mean, double &sum2);
bool collectAboveThreshold(double threshold, double guard,
                           std::vector<int> &indices_ascending,
                           size_t &guard_band_count);
```

`mean`, `std` and `threshold` are computed **on the host** from the two returned sums, reusing the
literal source expressions at `:1359`, `:1365`, `:1366`, so host rounding and contraction
decisions are unchanged.

Kernels use fixed-shape two-stage trees with no floating-point atomics (deterministic), and form
addends with `__dsub_rn`/`__dmul_rn`/`__dadd_rn` so nvcc's default `-fmad=true` cannot contract
`acc += d*d` into an FMA and change the addend multiset. `-fmad` is not altered translation-unit
wide, which would perturb every other kernel in the file.

The collect kernel appends via `atomicAdd` on an integer counter, so emission order is arbitrary;
the host sorts ascending, which restores determinism exactly. A block-scan compaction is not
needed: Chebyshev caps the hit count at `N/36` (395,527 here), and realistic counts are tens to
hundreds, so the host sort costs microseconds.

`applyGainDefectsAndSum` gains an explicit `cudaDeviceSynchronize()` and error check, because the
blocking D2H it removes was the **only** synchronisation point for `fusedGainAndSumKernel`.

## 5. Memory

Hit buffer `(N/36 + 1) * 4 B` = 1.51 MiB, allocated as RAII scratch inside
`collectAboveThreshold` and freed on every return path (the existing `DefectScratch` pattern at
`cuda_movie_session.cu:376-402`), plus two 8-byte counters and 16 KiB of partials. Because it is
freed before the alignment/reconstruction stage where the 3,537 MiB whole-device peak occurs, the
delta to reported peak VRAM is **0 MiB**. Buffer capacity and `guard` are computed from `N`, never
hard-coded, so EER super-resolution grids scale correctly.

## 6. Fallback

Every guard failure sets a **local** flag, copies `d_Isum` to the host (it is only ever read by the
new kernels, never written), and runs `:1354-1400` verbatim.

**The session must not be reset on a hot-pixel statistics failure.** `host_frames_are_raw` is set
at `:1324` but `resident_bad_xs/ys` are populated only at `:1477-1478`. Resetting the session
between those points leaves `:1465` still routing replacements into `resident_bad_replacements`
while `resident_bad_xs` stays empty, so `materialize_host_frames` (`:1296-1314`) applies gain and
silently discards every hot-pixel correction. That state is unreachable today; this change would
make it reachable. A local flag avoids it.

## 7. Free wins included, measured separately

1. **Parallelise the gain-zero loop** at `:1383`. It performs only idempotent `= true` writes with
   no reduction and no cross-index reads, so it is order-independent by construction and bitwise
   identical. It is currently serial over 54.32 MiB.
2. **Skip the D2H entirely when `--skip_defect` is set.** `Isum` is never read in that mode today,
   yet the copy is unconditional.

Both must be measured separately from the GPU statistics change so attribution is honest.

## 8. Expected payoff — corrected

`TIMING_DETECT_HOT` covers six steps; this change removes three (the two reductions and the
threshold scan). The `bBad` allocation/zeroing, `fillDefectMask`, and the serial gain-zero scan
remain. A standalone harness at real scale (N = 3710x3838, A100 host, g++ -O2 -fopenmp) measures
the two reductions plus the threshold scan at **39 ms at `--j 1` and ~20 ms at `--j 8`**, not the
0.186 s sometimes quoted for the whole stage. The D2H itself is 54.32 MiB, roughly 7-9 ms.

So the realistic recovery is **tens of milliseconds against a 3.46 s median (order 1%)**, plus
whatever item 7.1 contributes. This is a smaller prize than the framing in the addendum suggests,
and the final report must state the measured value rather than the projected one.

## 9. Validation

Bit-identity against `a11f2f1`, per `--j` value (never across). Matrix: gain/no-gain,
defects/no-defects (txt and map), `--skip_defect`, `--j 1` and `--j 8`, GPU 3, streaming path via
`--bin_factor 2`, no-`--gpu` CPU path, `CUDA=OFF` build, OOM fallback, zero-hot-pixel synthetic
fixture, and the 24-movie dataset. Log `band` and `n_hits` per movie; both guards must never fire.
Fault-injection build to force the fallback and confirm it reproduces the reference bit-for-bit
with the session still alive.
