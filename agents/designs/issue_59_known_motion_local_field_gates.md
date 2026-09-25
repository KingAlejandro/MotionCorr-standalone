# Issue 59: Known-motion truth and applied displacement-field gates

Status: accepted (design fixed before any fixture was generated or any result inspected)
Owner: Issue #59
Source commit at design time: see `git log -1` on branch `t3code/known-motion-local-field-gates`
Scope boundary: this design owns new synthetic fixtures and a new displacement-field metric
tool. It does not change `tools/compare_motioncorr.py`, `docs/reference_gates.md`, Gate 1
(`--gate exact`) or Gate 2 (`--gate relaxed`). Gate-semantics documentation belongs to #58,
perturbation calibration to #60, downstream scientific evaluation to #61.

---

## 1. Problem

The existing synthetic ground truth is a list of eight per-frame integer rolls compared against
the `data_global_shift` block. That check cannot see:

* whether the **sign and axis convention** of the reported field match the motion actually
  injected (a transposed or negated field can still produce a self-consistent STAR file);
* the **spatially varying** part of the correction, which lives in the
  `data_local_motion_model` polynomial and is never compared to anything;
* whether the reported field is the field the program **actually applied to pixels**;
* whether an agreement is real or an agreement with a flawed reference.

The corrected-image RMSE cannot substitute for this. Corrected pixels are a lossy, heavily
smoothed function of the field: a residual local error of a few tenths of a pixel changes the
image by roughly the local image gradient times that error, which is comparable to the noise
floor, while it is exactly the quantity that destroys high-resolution signal.

## 2. Conventions, fixed and named

These are read out of the source, not assumed. All are asserted by the checker.

**Field definition.** For frame `f` (1-indexed) and pixel `(ix, iy)` (0-indexed, `ix` = column
= fast axis = "x", `iy` = row = slow axis = "y"), the *applied displacement field* is

```
D_x(f, ix, iy) = globalShiftX[f-1] + Lx(z, u, v)
D_y(f, ix, iy) = globalShiftY[f-1] + Ly(z, u, v)
z = f - rlnMicrographStartFrame        # 0 at the first summed frame
u = ix / nx - 0.5,  v = iy / ny - 0.5  # normalised, note nx for x and ny for y
```

`Lx, Ly` are the third-order polynomial of `src/micrograph_model.cpp`
(`ThirdOrderPolynomialModel::getShiftAt`), 18 coefficients per axis over the basis
`{z, z^2, z^3} x {1, u, u^2, v, v^2, uv}`. Every basis term carries a factor of `z`, so the
local field is identically zero on the first summed frame. This reproduces
`Micrograph::getShiftAt(frame, x, y, ..., use_local=true, normalise=true)`.

**Sign.** `src/motioncorr_runner.cpp:2491` applies the global correction as a Fourier phase
ramp with argument `-cur_shift / n`, which displaces frame content by `+cur_shift`;
`realSpaceInterpolation_ThirdOrderPolynomial` samples the globally aligned frame at
`(ix - Lx, iy - Ly)`, which also displaces content by `+L`. Therefore

```
D = displacement applied to the frame content in order to correct it
  = -(motion injected into that frame relative to the first summed frame)
```

The fixture stores both `injected_motion_*` and `expected_applied_field_*` = `-injected`, so no
reader has to re-derive the sign.

**Order.** The local model is fitted on, and applied to, frames that have *already* been
globally aligned. The total field is the sum, not a composition; the checker uses the sum.

**Units.** The field is in pixels of the working (unbinned, `bin_factor = 1`) grid.
Angstroms = pixels x `rlnMicrographOriginalPixelSize`. Fixtures use **0.885 A/px**, never 1.0,
so that a pixel/angstrom confusion changes every number.

**Known upstream caveat, out of scope.** Global shifts are written back multiplied by
`prescaling` (`motioncorr_runner.cpp:1546`) but the polynomial coefficients are not, so with
`bin_factor != 1` the two halves of the field are in different units. All fixtures here use
`bin_factor = 1`, where `prescaling == 1` and the question does not arise. Recorded, not fixed.

**Interpolation boundary.** The local resampling clamps to the edge pixel and skips bilinear
interpolation when the source coordinate leaves the array
(`motioncorr_runner.cpp:2095-2103`). Pixels within `ceil(max|D|) + 2` of an edge are therefore
not faithfully corrected. The checker reports interior and border statistics **separately** and
never crops, re-centres or re-registers anything to make a number pass.

**Dose-weighting boundary.** Dose weighting is a real, radially symmetric, per-frame Fourier
weight applied *after* alignment. It cannot change the geometry. The checker asserts the
recovered field is bit-identical with and without `--dose_weighting`; any difference is a defect.

## 3. Fixtures

Generator: `test-data/generate_known_motion_fixture.py`, one seeded call per case. The base
image is a sum of analytic Gaussians, so a warped frame is produced by **evaluating the
Gaussians at the warped coordinates** rather than by resampling an image. The fixture therefore
carries no interpolation error of its own.

Injected motion, in pixels, with `tau = z / (n_frames - 1)`:

```
Mx(f)        =  3.20 * (1 - exp(-z/1.7)) + 0.28 * z          # global, doming + drift
My(f)        = -2.40 * (1 - exp(-z/1.3)) - 0.10 * z
Px(tau,u,v)  =  2.40*tau*u + 1.40*tau*v + 1.10*tau^2*u^2 - 0.90*tau^2*u*v   # local
Py(tau,u,v)  = -1.90*tau*v + 1.20*tau*u + 0.80*tau^2*v^2 + 0.70*tau^2*u*v
M(f,u,v)     = (Mx, My) + local_scale * (Px, Py)
```

The local term is deliberately inside the span of the third-order model, so a correct
implementation can represent it exactly and any residual is estimation error, not model error.
Peak local deviation is about 2.4 px = 2.1 A, within the range of real beam-induced local motion.

| case | size | frames | patches | local_scale | noise | defects |
|:--|:--|:--:|:--:|:--:|:--|:--|
| `km_global_hisnr`    | 512x512 | 12 | 1x1 | 0   | 0.05 | none |
| `km_local_hisnr`     | 512x512 | 12 | 4x4 | 1.0 | 0.05 | none |
| `km_local_noisy`     | 512x512 | 12 | 4x4 | 1.0 | 10.0 | 6 hot pixels |
| `km_local_nonsquare` | 384x256 | 10 | 4x4 | 1.0 | 0.05 | none |

`noise` is the per-pixel Gaussian sigma as a multiple of the noise-free image standard
deviation; 10.0 is a per-pixel SNR of 0.1, in the cryo-EM range. Noise and hot pixels are
generated in detector coordinates and are **not** warped, which is what a detector does.
The non-square case exists because `u` is normalised by `nx` and `v` by `ny`; if those are ever
swapped, only a non-square movie can see it.

The two SNR tiers separate two different questions. The high-SNR cases test whether the
*implementation* is correct - conventions, indexing, units, sign - where estimator noise is
negligible. The noisy case tests *estimation accuracy* under realistic conditions.

## 4. Metrics

Let `T(f,p)` be the expected applied field from the fixture and `R(f,p)` the field recovered
from the output STAR, both in pixels, on a declared `Ng x Ng` grid of positions `p` at
`x_i = (i + 0.5) * nx / Ng` (same for y), `Ng = 9`, all frames `f`. Let `E = R - T`.

Reported, per case, in **both pixels and angstroms**:

1. **Constant offset** `c = mean_{f,p} E`. A field that is wrong by a constant in both `f` and
   `p` is a rigid translation of the output micrograph; it changes no relative geometry. It is
   reported on its own line and never folded into the other statistics.
2. **Offset-removed error** `E~ = E - c`: RMS, 95th percentile, and maximum of `|E~|`, over the
   interior grid and, separately, over the border grid.
3. **Global component** `g(f) = mean_p E~(f,p)`: RMS/P95/max. This is trajectory error.
4. **Local component** `l(f,p) = E~(f,p) - g(f)`: RMS/P95/max. This is spatially varying error,
   and it is the quantity that has never been checked before.
5. **Frame-to-frame change** `d(f,p) = E~(f+1,p) - E~(f,p)`: RMS/max. Independent of every
   constant, in `f` or otherwise.
6. **Per-frame distribution**: for each frame, RMS/P95/max of `|E~(f,.)|` over the grid.
7. **Boundary accounting**: `ceil(max|R|) + 2` as the unfaithful margin, and the fraction of
   output pixels inside it. Reported, never applied as a crop.

## 5. Thresholds, declared now, derived from physics

Residual displacement error acts as an incoherent average over frames. For a residual with
isotropic 2D RMS magnitude `sigma` (per-axis variance `sigma^2/2`), the amplitude envelope at
resolution `d` is `exp(-pi^2 sigma^2 / d^2)`, equivalent to a B-factor `B = 4 pi^2 sigma^2`.
Evaluated at a 3 A target:

| tier | sigma (A) | amplitude loss at 3 A | equivalent B (A^2) |
|:--:|:--:|:--:|:--:|
| A | 0.05 | 0.27 % | 0.10 |
| B | 0.10 | 1.09 % | 0.39 |
| C | 0.20 | 4.3 % | 1.58 |
| D | 0.40 | 16.1 % | 6.32 |

Assignments, chosen from this table alone. No tutorial-movie measurement was consulted, and
none of these numbers is derived from the 24-movie results.

| quantity | limit | tier | why this tier |
|:--|:--:|:--:|:--|
| global component RMS | 0.10 A | B | a global trajectory error is common to the whole field and the cheapest to get right; 1 % loss at 3 A is negligible against every other loss term |
| local component RMS | 0.20 A | C | fitted from a finite number of patches, so intrinsically noisier; 4 % loss at 3 A is below refinement-to-refinement variation |
| total offset-removed RMS | 0.20 A | C | dominated by the local term |
| total offset-removed P95 | 0.40 A | D | a tail at 5 % of positions contributes about 0.05 tier-C-equivalent to the envelope |
| total offset-removed max | 0.80 A | 2xD | a single grid point contributes negligibly to an average envelope; this is an outlier alarm, not an envelope limit |
| frame-to-frame RMS | 0.20 A | C | same physical basis, applied to increments |
| constant offset | reported; alarm above 1.0 px | - | scientifically harmless, but a value this large means an indexing or convention defect |

Border-grid statistics are reported and not gated: those pixels are knowingly unfaithful.

The equivalent limits in pixels at 0.885 A/px are 0.113 px (tier B), 0.226 px (tier C),
0.452 px (tier D).

## 6. Applied-field self-consistency

A field check that only reads the STAR file proves the program *reported* a field. To prove it
*applied* it, the checker re-implements the corrector in Python - global Fourier phase ramp with
the C++ Nyquist-row convention, then bilinear resampling at `(ix - Lx, iy - Ly)` with the same
edge clamping - drives it with the recovered field, sums the frames, and compares to the
program's own non-dose-weighted output.

The residual of that comparison is dominated by float32 versus float64 arithmetic and by FFT
rounding, and is expected near `1e-6` relative. That floor is **measured**, not assumed: the same
reconstruction is repeated with the field perturbed by known amounts to give a response curve.
Rounding-scale disagreement is reported as a separate `numerical_noise` diagnostic and does not
fail; a field defect sits orders of magnitude above it and does.

## 7. Negative controls, all automated

Each rewrites the output STAR and re-runs the checker; each must fail, with the named metric
being the one that fails.

| control | injected defect | must fail |
|:--|:--|:--|
| `wrong_global_frame` | +0.30 px on `rlnMicrographShiftX` of one frame | global component |
| `wrong_local_field` | scale the `u`-linear coefficients so the field changes by ~0.5 px at the corners | local component, while global still passes |
| `sign_flip` | negate the whole field | everything |
| `axis_swap` | exchange x and y | everything (and the non-square case most loudly) |
| `constant_translation` | +0.75 px on every frame and position | constant offset alarm only; frame-to-frame still passes |
| `fft_rounding` | perturb by 1e-6 px | nothing; reported under `numerical_noise` |

`constant_translation` and `fft_rounding` are the two that must *not* fail the motion gates.
They are the evidence that the gate distinguishes a real defect from an accounted-for
translation and from harmless arithmetic.

## 8. Deliverables

* `test-data/generate_known_motion_fixture.py` - fixture generator, seeded, self-describing JSON
* `tools/motion_field.py` - STAR parsing and field evaluation, a faithful port of `getShiftAt`
* `tools/check_known_motion.py` - metrics, thresholds, JSON + human report, nonzero exit on fail
* `tools/test_known_motion.py` - unit tests and the six negative controls
* `tools/run_known_motion_gates.sh` - one command, end to end
* `docs/known_motion_validation.md` - results, provenance, commands, per-frame tables

Existing exact CPU parity and corrected-image metrics are untouched and remain available
through `tools/run_regression_tests.sh` and `tools/compare_motioncorr.py`.

---

## Amendment 1 - fixture roles, and why the realistic-noise case is not a gate

Recorded after the first full run. **No tolerance was changed by this amendment.**

`km_local_noisy` failed every gated metric: local component RMS 0.62 A against a 0.20 A limit.
Three measurements established that this is the estimator running out of information, not a
defect in the applied field:

1. **Noise response.** Sweeping the per-pixel noise from sigma/signal = 0.05 to 10 on the same
   injected field gives local-component RMS 0.089, 0.076, 0.105, 0.262, 0.580 A. The error is
   proportional to the noise amplitude above a floor, which is the signature of estimator
   variance.
2. **Bias versus variance.** Eight replicates that differ only in the detector-noise stream give
   per-replicate RMS 0.76-1.53 A, a scatter component of 1.05 A, and a mean error field of
   0.50 A - consistent with zero bias at the resolution eight replicates can provide. A
   systematic field defect would survive averaging; this does not.
3. **Information content.** A 4x4 patch grid on 512x512 with 12 frames gives 128*128*12 =
   197k pixel-frames per patch. A 5x5 grid on a 3710x3838 tutorial movie with 24 frames gives
   13.7M - seventy times more. Error scales as the inverse square root of that product across a
   patch-size sweep, so the small fixture is expected to be about 8x less precise.

`km_local_realscale` (2048x2048, 24 frames, 5x5 patches, **identical** injected field and
identical per-pixel SNR) was then added and **passes every declared tolerance**: global 0.053 A,
local 0.146 A, total 0.155 A. Predicted from the scaling law: 0.16 A. Measured: 0.146 A.

Cases therefore carry an explicit `role`:

* `role: "gate"` - must meet the declared tolerances. `km_global_hisnr`, `km_local_hisnr`,
  `km_local_nonsquare`, `km_local_realscale`.
* `role: "characterization"` - measured and reported in full, excluded from the aggregate.
  `km_local_noisy`, whose failing numbers stay visible in every report and in the JSON.

A tolerance on recovery accuracy is only enforceable on a fixture carrying enough information to
resolve it. That is a property of the fixture, measured independently of the gate. The design
declared the tolerances; it did not, and could not, declare which fixtures could supply enough
information to reach them.

`km_local_nonsquare` was enlarged from 384x256x10 to 768x512x12 for the same reason: at 61k
pixel-frames per patch its estimator floor straddled the tier-C limit (measured 0.14-0.26 A
across seeds). A square control at matched information content was no better, so the geometry,
not the non-squareness, was the limit - which is also the evidence that the nx/ny normalisation
is handled correctly. The case exists to catch an axis swap and does that at any size.

## Amendment 2 - the constant-offset limit is tightened from 1.0 px to 0.10 A

**This is stricter than declared, and it closes a blind spot found in the metric itself.**

The mean error `c` is not a free gauge. Truth and recovery are both anchored at the first summed
frame, so `E(first) == 0` identically and `c` is algebraically tied to the other frames' errors.
For an error constant across frames 1..N-1, `c = k(N-1)/N`, and removing `c` before computing the
scatter shrinks the statistic by about `N/sqrt(N-1)` - 3.6x at 12 frames. At the declared 1.0 px
alarm, a genuine 0.25 px per-frame bias passed every gate. The limit is now tier B, 0.10 A, the
same as the global component. All gate-role cases pass it with margin.

A bias-inclusive `total_rms_interior_with_offset` is also now reported, ungated, so the
offset/scatter split cannot hide anything from a reader.

## Amendment 3 - the base image is periodic

**A fixture correctness fix, found by validating the truth against its own pixels.**

The first build rendered particles without wrapping. A Fourier shift is cyclic, so a band of
width `|shift|` along two edges held content in one frame and nothing in the other, and any
full-frame cross-correlation optimum was dragged toward zero shift. The measured consequence was
a 1.2 % low bias in the apparent global trajectory - which presented exactly as a MotionCorr
defect, and would have been reported as one.

It was caught by measuring the frame-to-frame displacement straight out of the pixels with an
estimator that shares no code with MotionCorr: it reproduced MotionCorr's answer, not the
declared truth, and cropping 20 px of border recovered the declared truth to 1.5e-4 px. The base
image now renders each particle together with its eight neighbouring tiles. After the fix the
global trajectory bias is 0.024 px, and the pixel-level estimator agrees with the declared field
to 1.4e-3 px on the full frame.

That check is now permanent: `tools/test_known_motion.py` section 2 runs it on every invocation.
Nothing else in this design means anything if the ground truth is not actually true.

## Amendment 4 - negative controls are sized from the tolerances, and sensitivity is measured

The first two controls - 0.30 px on one frame, 0.5 px at the field corners - were **not**
rejected, and should not have been. A single frame displaced by `d` contributes `d/sqrt(N)` to an
RMS over `N` frames, so at 12 frames a 0.30 px single-frame error is 0.077 A: below tier B by
construction. Demanding its rejection would demand that the gate violate its own specification.

Control amplitudes are now derived from the declared tolerances, and the suite additionally
**measures** the smallest rejected defect of each kind by bisection rather than asserting a
binary outcome:

| defect | detected above |
|:--|:--|
| one frame displaced | 0.408 px = 0.361 A |
| trajectory scale error on every frame | 2.36 % |
| local field error at the corners, last frame | 0.681 px = 0.603 A |
| constant bias on every frame but the first | 0.126 px = 0.111 A |

The 2.36 % scale sensitivity is worth stating plainly: the 1.2 % fixture artefact of Amendment 3
was **below** it. This gate would not have caught that artefact, which is why the pixel-level
truth validation of Amendment 3 exists as a separate check and not as one more metric.
