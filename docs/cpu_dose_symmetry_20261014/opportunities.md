# CPU work beyond full-frame plan reuse and first-touch tuning

Use the user's cpu64 main profile (movie 00026, j1, 47.7 s) for rough budgets,
not as this branch's before/after measurement. The other agent owns reusable
full-frame plans, the final inverse preservation copy and buffer/huge-page work.
Their estimated savings can overlap: faulting/copying is part of the gap between
in-job FFT stage time and standalone execution. Do not add 6 s and 5 s as a
demonstrated 11-second saving.

Full-frame FFTs alone occupy 8.9 + 9.9 + 8.4 = 27.2 s, about 57% of that job;
patch FFTs add more. Even halving everything outside the full-frame FFTs would
save only about 21.5% of elapsed time. An unchanged-arithmetic CPU path has
several modest opportunities, not evidence for another easy 2x speedup.

1. **Reuse dose weights across positive/negative frequency rows.** This branch
   implements this together with item 4: the scalar formula uses ky squared. It approximately halves
   exp/pow work but retains all complex pixel operations and frame order. There
   is no frame-sized extra storage. With a 3.3-second weighting stage, even a
   2x reduction of the entire stage saves 1.65 s, about 3.5% of the job. Symmetry
   alone removes only duplicated scalar work. Tiling can also reduce application
   cost, so the combined ceiling is the entire 3.3-second stage, about 6.9% of
   the job. Neither is a measured whole-job forecast.
2. **Precompute interpolation coordinates, using the same divisions.**
   `realSpaceInterpolation_ThirdOrderPolynomial` computes x = double(ix)/nx - .5
   inside every frame/row/pixel loop. The saved GCC 13.3 Release assembly still
   contains scalar `divsd` in that loop (`interpolation-divisions.txt`). Reuse
   an array of those exact RFLOAT values, about 30 KiB at nx=3710. This avoids
   repeating roughly 342 million divisions per 24-frame tutorial interpolation
   pass. Do not replace division with reciprocal multiplication or factor the
   polynomial into a different arithmetic order. The 3.5-second dose interpolation
   stage is the whole budget, not the expected saving. Measure whether coordinate
   loads beat divisions and whether the compiler already hoists other candidates.
3. **Fuse unweighted total/even/odd pixel passes.** In #178's streaming helper,
   total accumulation is parallel but even/odd accumulation is a separate serial
   image scan. Each output pixel can receive both additions from the same scratch
   load, while keeping ascending frame order for each output. This could help j4
   scaling and cache traffic. Keep separate owning output arrays and preserve the
   float interpolation store. The existing ~10% unweighted stage is the total
   ceiling and includes other work; #178 established a RAM saving, not a speedup.
4. **Tile dose-weight application (combined with item 1 in this branch).** Main's frequency-outer/frame-inner loop
   jumps among N allocations twice per frequency. The small frequency tile retains
   scalar weights and per-frequency frame-reduction order, then visits
   contiguous pixels per frame. It preserves both original complex operations and
   intermediate float rounding. Test long movies too: processing paired rows
   raises the active page count, so less arithmetic need not mean less wall time.
   This competes for the same 3.3-second budget as item 1; gains are not additive.
5. **Limit local patch phase updates to CCF support.** `alignPatch` builds Fref
   and CCF from a cropped low-frequency region, but shifts the whole patch spectrum
   each iteration. Local patches are discarded after fitting; full-frame global
   spectra are still needed for reconstruction. Begin with unchanged allocations
   and exact original frequency coordinates, updating only consumed local bins.
   The whole patch stage is ~11%, including FFT preparation, so the saved phase
   work is a smaller part. Never apply this elision to globally aligned spectra.

For deployment, compare independent movie workers against high thread counts
within the same core and RAM budget, with NUMA-local placement. That can improve
dataset throughput without changing FFT arithmetic, but is not a single-core
code speedup and can increase peak RAM. The existing guarded unused global iFFT,
gain/sum tiling, gain cache and LibTIFF/libdeflate work are already integrated.

A full dose-weight cache is not free: storing only the already rounded float
weights for 24 x 1856 x 3838 frequencies needs about 0.64 GiB, plus normalization
and cache metadata. A safe key includes geometry, sampling, every dose and frame
selection. That is a separate warm-dataset speed/RAM tradeoff, not a default
low-memory optimization. Bounded scalar/coordinate/tile reuse is preferable first.

## Larger reconstruction change under a different numerical contract

For global-only correction, inverse FFT is linear in exact arithmetic. One can
sum the already aligned, weighted Fourier frames first, then do one inverse per
requested total/even/odd output instead of one inverse per input frame. This
could remove many transforms while leaving alignment upstream untouched.
It changes floating-point rounding, so it does not meet the present bitwise
gate. Frame-specific local warps prevent applying that rearrangement to the
current local-motion reconstruction. Treat it as a separate opt-in experiment
with numerical/scientific validation, not a shortcut inside this exact branch.

FFTW MEASURE/PATIENT, another FFT backend, padded FFT sizes, approximate exp or
polynomial reassociation need a different output contract and scientific gates.
Do not relabel them exact just because a few fixtures happen to match.
