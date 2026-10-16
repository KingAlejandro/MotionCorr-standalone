# Analysis plan — 16 October 2026

Recorded before any completed matched A/B series from the new attempts was read.
The original 11 October protocol and `paired.py` analysis remain unchanged.
This note only specifies how to present the requested overall number.

- A = exact frozen `6b6adf4420ec09403a7b655dce6cdc2d8ee004a7`
  compact LibTIFF reader; B = private nvTIFF 0.8.0.82. Positive **A−B**
  is a saving; the retained driver uses the opposite sign, B−A.
- Five immutable real U8 LZW files, default SDK allocator, batch one,
  synchronized bottom-up device samples; no gain/FFT/application integration.
- Per input: one fresh-process warmup per arm, six adjacent same-arm null
  pairs **per arm**, then twelve alternating AB/BA pairs (six each).
- Preserve the driver's exact per-file calculation: median of paired B−A;
  seeded (`20261011`) balanced-order bootstrap, 10,000 resamples, descriptive
  2.5/97.5 percentiles; null magnitude = maximum absolute adjacent difference
  over both arms. Required saving = max(0.15 seconds, observed null magnitude).
  Both complete-ingest and external checked-exit must clear that threshold
  throughout the descriptive interval. No inferred confidence/population claim.
- For presentation, per-file saving intervals negate/reverse the driver's
  B−A interval. Null bands are ± observed magnitude, not confidence intervals.
- **Overall is an equal-file arithmetic mean of the five paired medians**
  (one movie/file; not weighted by pixels, samples, size or trial count).
  The overall descriptive envelope is the arithmetic mean of their respective
  lower and upper bounds. This is not a new pooled confidence interval.
  Use the **maximum per-file null magnitude** as its conservative null band;
  do not manufacture adjacent overall-null trials from nonadjacent files.
  Report every file so heterogeneity is visible. No cross-venue pooling.
- GO is narrowly a resolved >=0.15 s/movie standalone endpoint result beyond
  null on both clocks, not permission to integrate, merge or change defaults.
  A complete result confidently below that requirement is NO-GO; a missing
  series, resource failure, or interval crossing the decision boundary is
  UNRESOLVED. The historical driver's `NO_GO_TO_APPLICATION_PILOT` means
  "GO criterion not met", and is not by itself proof of a resolved loss.
- One bad row aborts the campaign under the retained fail-closed controller.
  Incomplete warmup/null/pair fragments remain evidence, never selected into
  a successful series. No gate, numerical tolerance, decoder or default changes.

Raw logs stay on the venues. Exact paths, hashes, commands, allocation identities,
exit status and the retained 13 October failure are included in the result receipt.
