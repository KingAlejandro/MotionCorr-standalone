# Mac replicate census, not hash-identical to the frozen census

**STOP before admission.** The first movie's recorded moments establish changed
integer detector counts, so the requested condition that the differences be
only floating-point rounding is not met. No additional movie was generated,
no native arm ran, and no `REPLICATE_AMENDMENT.md` was activated or committed.
P2/P3/P4/P5, pass counts, sign tests, regressions and native timings remain
**UNRUN**. This adds a quantified diagnosis to the previous stopped attempt;
it does not alter that evidence.

## What frozen data were available

The local [original metadata archive](../km_truth/raw.tar.gz) contains the
frozen `dose1-s00` receipt and expectation recipe/proof. Its SHA-256 is
`4b0afb906fa2b5f3118fd9dc31b3bd0afb06554a98cafa8c79edc043131ce8dd`.
The extracted [frozen receipt](replicate_preflight/frozen-RECEIPT.json) hashes to
`495ef90ef4a096071cf446f9956ae4fb0a180875455e8f5eca3bfedde0c96a1c`, exactly
the entry in [FIXTURE_INDEX.json](../km_truth/FIXTURE_INDEX.json).

No frozen census pixels, partial pixel array or saved Linux truth array were
found in the scoped local search: `/tmp`, the MotionCorr worktrees,
`Documents/MotionCorr`, and `Downloads`. Unrelated tiny-control/synthetic arrays
were excluded. The 9,198-member metadata archive contains no `.npy`, `.npz`,
`.mrc` or `.mrcs` member. Its
[frozen expectation record](replicate_preflight/frozen-expectation.json)
contains a recipe, hash and inverse-closure scalar, not expectation pixels.
The previous attempt's large Mac movie and expectation were already deleted,
as recorded in [cleanup.json](cleanup.json); their receipts remain available.

Therefore the **exact maximum absolute movie-pixel difference is UNAVAILABLE**,
as is the maximum difference between expectation pixels. A hash or scalar
moment cannot supply either exact maximum. No pixel-level equality claim is
made.

## What the retained moments establish

The frozen and [Mac receipts](generated-RECEIPT.json) have identical recipe
fields, including shape `40 × 4096 × 4096`, scene seed `238267`, noise seed `0`,
dose `1`, pedestal `1`, scale `1`, motion model, texture RMS and oversampling.
Both record NumPy 2.5.4. The frozen Python was 3.12.3; this Mac uses Python
3.15.1 with NumPy 2.5.4 / SciPy 1.18.1. No shape or parameter mismatch was found.

| Quantity | Frozen Linux receipt | Mac receipt |
|---|---:|---:|
| Number of pixels N | 671,088,640 | 671,088,640 |
| Mean | 1.0000130534172058 | 1.0000130534172058 |
| Standard deviation | 1.000798970083948 | 1.0007989641282418 |
| Derived sum, N × mean | 671,097,400 | 671,097,400 |
| Derived sum of squares, N × (std² + mean²) | 1,343,267,588 | 1,343,267,580 |

These sums are **derived from the receipts**, not measured by reopening pixel
arrays. They follow the unchanged generator's exact population-moment formula.
Reversing the recorded doubles gives the displayed integers; the difference
of eight in the sum of squares is far above double-rounding uncertainty at
this magnitude.

For this recipe the serialized pixels are integer Poisson counts:
`pixels = (1 + (counts - 1)).astype('<f4')`. Identical integer pixels would give
identical moments under the same generator. Equal sums and unequal sums of
squares imply **at least two changed pixels**, and the integer-valued output
implies a **maximum absolute pixel difference of at least 1 detector count**.
This is a proven lower bound from the receipts, not a measured exact maximum.
The hash mismatch cannot be explained solely by a different MRC header.

The changed count realization could have been triggered by tiny changes in
the noise-free expectation near Poisson decision boundaries. The available
records do not establish that mechanism, how many counts changed, whether
later RNG consumption diverged, or whether the scene itself differs only by
rounding. No independent reseeding or changed recipe is alleged. In particular,
the changed detector counts do **not** prove a large scene or truth difference;
they do prevent certifying the user's stricter rounding-only movie condition.

## Truth comparison and its limit

The frozen generator extracted from the archive and the local archived source
are byte-identical, SHA-256
`a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380`.
With the identical recipe, both analytic displacement functions were evaluated
on **this Mac** at all 40 frames of the unchanged 129 × 129 fixed-ROI lattice.
Their **maximum absolute component difference is 0 px**. Both little-endian
float64 field streams hash to
`cf325ba2190d353c07e0c0f77801f406d40327cd31a5a8e4f19d3de44db8cc97`.

This establishes unchanged analytic truth code, parameters and a same-stack
reconstruction. It is **not a measured Linux-versus-Mac truth-array comparison**:
saved original Linux truth pixels/arrays were unavailable. Thus no truth
definition change is observed, while the actual cross-venue array difference
remains unmeasured.

The retained Mac binary was rehashed and remains
`e978af21352295bfe2cf756fa2916703d2b7e6c6b34c352d58630e7975155946`;
no rebuild or source change occurred. All numerical results and scope details
are in [mismatch-analysis.json](replicate_preflight/mismatch-analysis.json).

**Disposition:** the conditional replicate is not admitted. The exact pixel
maximum and scene-rounding claim need a frozen pixel sample to measure; using
a changed detector-count realization would require an explicitly different
admission condition. No census result or P5 agreement count can be supplied
from this preflight.
