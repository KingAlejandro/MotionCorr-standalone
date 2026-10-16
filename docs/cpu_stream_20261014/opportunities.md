# What PR #177 teaches, and the next CPU experiments

## What was learned

PR #177 removes repeated inverse-CCF preservation copies and plan churn by
keeping one array-bound plan per worker. It passes exact-product, lifetime and
negative-control checks, but its measured whole-job time and peak RSS do not
establish a benefit. Its narrower inverse-CCF timer omits setup moved outside
that interval; a faster substage cannot be presented as a whole-job speedup.

The expanded baseline diagnostic found 1,248 inverse calls. At j1, preservation
copy + planning (including lock wait) + destruction cost 0.625 summed worker
seconds in a 160.9-second job. At j4 the same costs total 2.034 summed worker
seconds in a 76.7-second job; overlapping worker seconds are not wall seconds.
Lock wait is already included in planning/destruction, so adding it again would
double count. This explains why a large relative change in a small timer can be
lost in total-run variation. It does not prove the change can never help a
different shape, frame count or host.

The PR's tutorial measurements had no resolved speed gain or RAM gain. Its
strict inventory gate also found an extra partial temporary MRC on the baseline
side, despite canonical products matching. That failure remains recorded in
PR #177's evidence; it is not silently excluded or attributed to this candidate.

## Where time goes

`stages/summary.json` records one fresh profile per ordinary production binary
without the added CCF diagnostic probe. These are one-run observations with
profiling overhead, not replicated speed comparisons or forecasts. On the
3710 x 3838 x 24 tutorial at j4, the reference process takes 69.87 s:

- Global forward/inverse transforms: 14.21 + 12.64 s.
- Patch alignment: 5.55 s; patch FFTs alone take 2.05 s.
- Unweighted sums: 6.16 s, including allocation, interpolation and ordered
  total/even/odd additions.
- Dose weighting/reconstruction: 17.86 s, including inverse FFTs 9.32 s,
  interpolation 3.67 s and weight calculation 4.20 s.

Full-frame FFT intervals alone account for 36.17 s. The candidate's unweighted
stage is 7.46 s in its single profile, versus 6.16 s in reference; this does not
support a speed claim. Several unchanged stages also differ substantially.
Both profile output trees match exactly. The reliable observation is the
separately replicated peak-RSS reduction.

`baseline-stage-summary.json` also preserves the earlier PR #177 expanded-probe
profiles. Its j4 patch preparation was 14.37 s (including patch FFTs 12.32 s),
and its unweighted stage was 13.58 s. Instrumentation, run context and wall
variation differ. Do not pool these profiles or equate any timer delta with
an optimization benefit. Existing input-prefetch/TIFF work must not be counted
as a new CPU-compute improvement.

Nested intervals overlap their parents. Do not add them to the top-level totals.

## Ranked follow-ups

1. **Bound corrected-frame lifetime.** This PR streams the unweighted
   reconstruction through one float scratch frame instead of a full corrected
   stack. It targets an identifiable large live allocation and places
   interpolation and summation adjacent for each frame. It applies when unweighted reconstruction is
   requested, including no-dose, `--save_noDW`, or even/odd products. A
   dose-only job without those products skips that stage already.
2. **Measure full-frame FFT cost and the final inverse preservation copy.**
   There is much more transform work here than in CCF. The final CPU dose
   inverse currently preserves Fourier input, although the subsequent source
   has no spectral consumer. A disposable-input inverse is a focused next
   experiment after auditing power-spectrum/fallback/output ownership. Retain
   existing FFT flags and normalization and measure total time plus actual
   RSS. FFT plan reuse is a separate hypothesis; measure planning's share
   before generalizing #177 across all transforms.
3. **Reduce patch-preparation work.** Optimize the existing patch FFT and
   clipping/layout path first. A compact frequency representation must prove
   which frequencies are actually consumed and preserve full-frame data for
   reconstruction; it is more invasive than the lifetime change. The profile
   makes this a stronger speed target than another small CCF-only tweak.
4. **Tile dose-weight memory access.** The current inner frame loop visits a
   different full-frame allocation per frequency, twice. Try a bounded
   frequency tile while preserving each frequency's frame reduction order,
   intermediate float complex stores and scalar exp/pow semantics. The
   observed weight stage is 2.07-4.20 s in the fresh diagnostic pair, so its ceiling is modest compared
   with FFTs and interpolation.
5. **Tune threads within a fixed CPU budget.** Compare outer frame/row
   parallelism and placement using the same CPU mask. Do not confuse more
   available cores or a different host with a code speedup. Avoid oversubscribed
   nested FFT/OpenMP workers. The unweighted stage did not scale well in the
   diagnostic (12.90 s at j1 versus 13.58 s at j4), consistent with a memory
   traffic/serial-addition concern but not proof of its cause. That comparison
   comes from the older expanded-probe runs and needs a clean-host recheck.

Do not combine these hypotheses into one benchmark. Padding awkward FFT sizes,
changing backend, approximate weights or fast-math can change numerical output
and require their own explicitly different acceptance contract. The current
experiment preserves the existing exact-output contract.
