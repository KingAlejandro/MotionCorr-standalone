# Known-Motion Truth and Applied Displacement-Field Validation

Resolves [Issue #59](https://github.com/KingAlejandro/MotionCorr-standalone/issues/59).

Design record, written and committed **before** any fixture was generated or any result
inspected: [`agents/designs/issue_59_known_motion_local_field_gates.md`](../agents/designs/issue_59_known_motion_local_field_gates.md).
Every tolerance in this report comes from that record. Four amendments are appended to it; each
says what changed, why, and whether it made the gate stricter or weaker.

This check is **separate from** `tools/compare_motioncorr.py`. That tool compares a run to a
reference run. This one compares a run to synthetic ground truth, and it compares the
**displacement field applied at each position and frame** rather than only corrected pixels.
Gate 1 (`--gate exact`) and Gate 2 (`--gate relaxed`) are untouched; so is
`docs/reference_gates.md`.

---

## 1. What is compared

For frame `f` (1-based) and pixel `(ix, iy)` the applied field is

```
D_x(f, ix, iy) = globalShiftX[f-1] + Lx(z, u, v)
D_y(f, ix, iy) = globalShiftY[f-1] + Ly(z, u, v)
z = f - rlnMicrographStartFrame,  u = ix/nx - 0.5,  v = iy/ny - 0.5
```

with `Lx, Ly` the 18-coefficient third-order polynomial of `src/micrograph_model.cpp`. This
reproduces `Micrograph::getShiftAt`. Read out of the source, not assumed, and asserted by the
checker:

| property | value | where it comes from |
|:--|:--|:--|
| sign | `D` = displacement applied to the frame to correct it = **minus** the injected motion | `motioncorr_runner.cpp:2491` applies a phase ramp of `-shift/n`, which displaces content by `+shift`; `realSpaceInterpolation_ThirdOrderPolynomial` samples at `(ix - Lx, iy - Ly)`, also `+L` |
| axes | `x` = column = fast axis, `y` = row | `Image(X, Y)` has `MultidimArray(Y, X)` |
| normalisation | `u` by `nx`, `v` by `ny` -- not interchangeable | `Micrograph::getShiftAt`, `normalise=true` |
| frame origin | local model is identically zero at `z = 0`; every basis term carries a factor of `z` | `ThirdOrderPolynomialModel::getShiftAt` |
| composition | local model is fitted on, and applied to, **already globally aligned** frames, so the total field is the **sum** | `motioncorr_runner.cpp:1562-1795` |
| units | pixels of the unbinned grid; angstrom = pixel x `rlnMicrographOriginalPixelSize` | fixtures use **0.885 A/px**, never 1.0, so a px/A confusion changes every number |

**Known upstream caveat, out of scope and not fixed here.** Global shifts are written back
multiplied by `prescaling` (`motioncorr_runner.cpp:1546`) but the polynomial coefficients are
not, so with `bin_factor != 1` the two halves of the field are in different units. Every fixture
here uses `bin_factor = 1`, where `prescaling == 1` and the question does not arise.

## 2. Fixtures

`test-data/generate_known_motion_fixture.py`. The base image is an analytic sum of Gaussians
evaluated **at the warped coordinates**, so no image is ever resampled and the fixture carries no
interpolation error of its own. The base image is periodic (see Amendment 3). The injected local
field lies inside the span of the model MotionCorr fits, so any residual is estimation error, not
model-mismatch error. Detector noise and hot pixels are generated in detector coordinates and are
not warped.

| case | role | size | frames | patches | local motion | per-pixel SNR | defects |
|:--|:--|:--|:--:|:--:|:--:|:--:|:--:|
| `km_global_hisnr` | gate | 512x512 | 12 | 1x1 | none | 20 | none |
| `km_local_hisnr` | gate | 512x512 | 12 | 4x4 | 2.4 px peak | 20 | none |
| `km_local_nonsquare` | gate | 768x512 | 12 | 4x4 | 2.4 px peak | 20 | none |
| `km_local_realscale` | gate (opt-in, 400 MB) | 2048x2048 | 24 | 5x5 | 2.4 px peak | 0.1 | 6 hot px |
| `km_local_noisy` | characterization | 512x512 | 12 | 4x4 | 2.4 px peak | 0.1 | 6 hot px |

Movies are **not** committed: they are regenerated deterministically in about 2 s (12 s with the
real-scale case) and their SHA-256 hashes are versioned in
`test-data/known_motion/MANIFEST.json`. Ground-truth JSON and input STAR files are committed.

The non-square case exists because `u` is normalised by `nx` and `v` by `ny`; only a non-square
movie can catch a swap. The unit suite confirms the checker itself is sensitive to that swap
(28.6 px difference at a corner).

## 3. Thresholds

A residual displacement error averages incoherently across frames. For an isotropic 2D RMS
magnitude `sigma`, the amplitude envelope at resolution `d` is `exp(-pi^2 sigma^2 / d^2)`,
equivalent to `B = 4 pi^2 sigma^2`. At a 3 A target:

| tier | sigma (A) | amplitude loss at 3 A | equivalent B (A^2) |
|:--:|:--:|:--:|:--:|
| A | 0.05 | 0.27 % | 0.10 |
| B | 0.10 | 1.09 % | 0.39 |
| C | 0.20 | 4.3 % | 1.58 |
| D | 0.40 | 16.1 % | 6.32 |

| gated quantity | limit | tier |
|:--|:--:|:--:|
| global component RMS (spatial mean per frame) | 0.10 A | B |
| local component RMS (spatially varying) | 0.20 A | C |
| total RMS, interior | 0.20 A | C |
| total P95, interior | 0.40 A | D |
| total max, interior | 0.80 A | 2xD |
| frame-to-frame change RMS | 0.20 A | C |
| constant offset (mean error) | 0.10 A | B |

**No limit was derived from, or tuned against, the 24 tutorial movies**, and none was changed to
make a measurement pass. The one limit that moved -- the constant offset, from the declared
1.0 px to 0.10 A -- was made **stricter**, to close a blind spot in the metric (Amendment 2).

Border-grid statistics are reported and not gated: those pixels are knowingly unfaithful because
the corrector clamps to the edge pixel there. Nothing is cropped, re-centred or re-registered.

## 4. Commands

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel

# fixtures (add --include-heavy for the 400 MB real-scale case)
python3 test-data/generate_known_motion_fixture.py --include-heavy

# everything: run, gate, dose-weighting and thread invariance, self-consistency
python3 tools/run_known_motion_gates.py --outdir /tmp/km59 --include-heavy --json /tmp/km59/all.json

# unit checks, fixture self-validation, negative controls, sensitivity
python3 tools/test_known_motion.py

# a single case by hand
cd test-data/known_motion
../../build/motioncorr --i km_local_hisnr.star --o /tmp/out --use_own --j 1 \
    --patch_x 4 --patch_y 4 --bin_factor 1 --seed 1 --save_noDW --skip_defect
python3 ../../tools/check_known_motion.py \
    --ground-truth km_local_hisnr_ground_truth.json --test /tmp/out \
    --movie km_local_hisnr.mrcs --summed-image /tmp/out/km_local_hisnr.mrc
```

## 5. Results

Source commit `e07fdec235d38f152356b136fb7038394eb8c919`. macOS 26.6.2 arm64, Apple clang 21.0.0, FFTW 3.3.11,
Python 3.14.7 / NumPy 2.5.3, `--j 1`, `--seed 1`, `bin_factor 1`. Machine report:
`run_known_motion_gates.py --json`.

| case | role | status | global RMS (A) | local RMS (A) | total RMS (A) | P95 (A) | max (A) | offset (A) | wall (s) |
|:--|:--|:--:|--:|--:|--:|--:|--:|--:|--:|
| `km_global_hisnr` | gate | **PASS** | 0.0082 | 0.0000 | 0.0082 | 0.0208 | 0.0208 | 0.0208 | 0.13 |
| `km_local_hisnr` | gate | **PASS** | 0.0077 | 0.0514 | 0.0527 | 0.1071 | 0.1904 | 0.0087 | 0.18 |
| `km_local_nonsquare` | gate | **PASS** | 0.0072 | 0.0394 | 0.0414 | 0.0869 | 0.1418 | 0.0089 | 0.24 |
| `km_local_realscale` | gate | **PASS** | 0.0532 | 0.1458 | 0.1547 | 0.2625 | 0.5240 | 0.0579 | 2.07 |
| `km_local_noisy` | characterization | **FAIL** | 0.2609 | 0.6161 | 0.6542 | 1.0794 | 1.4243 | 0.4124 | 0.18 |

Limits for reference: global 0.10, local 0.20, total 0.20, P95 0.40, max 0.80, offset 0.10 A.
Every gate-role case passes; the tightest is `km_local_realscale` at 0.146 A against the 0.20 A
local limit, 1.4x margin. `km_local_noisy` fails and its numbers are printed in full by every
report -- section 7 explains why, and nothing was relaxed to accommodate it.

Boundaries, all cases:

| check | result |
|:--|:--|
| dose weighting on vs off | recovered field **bit-identical**, 0.000e+00 px, every case |
| `--j 1` vs `--j 4` | recovered field **bit-identical**, 0.000e+00 px, every case |
| hot pixels, `km_local_noisy` | 6 injected, 6 detected |
| hot pixels, `km_local_realscale` | 6 injected, 8 detected -- 2 noise pixels also crossed the mean+6sigma threshold over 4.2 M pixels; reported, not gated |
| interpolation boundary | margin `ceil(max\|D\|)+2`: 6.9 % of output pixels on `km_global_hisnr`, reported separately, never cropped |

### Per-frame distribution, `km_local_hisnr` (interior grid, offset removed)

| frame | z | applied dx (px) | applied dy (px) | interior RMS (px) | P95 (px) | max (px) | RMS (A) | max (A) |
|:--:|:--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 0 | 0.0000 | 0.0000 | 0.00982 | 0.00982 | 0.00982 | 0.00869 | 0.00869 |
| 2 | 1 | -1.6964 | 1.3860 | 0.01248 | 0.01857 | 0.02378 | 0.01105 | 0.02105 |
| 3 | 2 | -2.7728 | 2.0818 | 0.01833 | 0.02640 | 0.03680 | 0.01623 | 0.03256 |
| 4 | 3 | -3.5018 | 2.4494 | 0.02658 | 0.04126 | 0.05348 | 0.02352 | 0.04733 |
| 5 | 4 | -4.0307 | 2.6720 | 0.03482 | 0.05484 | 0.07410 | 0.03081 | 0.06558 |
| 6 | 5 | -4.4535 | 2.8233 | 0.04342 | 0.07018 | 0.09547 | 0.03843 | 0.08449 |
| 7 | 6 | -4.8213 | 2.9427 | 0.05312 | 0.08677 | 0.11374 | 0.04701 | 0.10066 |
| 8 | 7 | -5.1561 | 3.0432 | 0.06268 | 0.10264 | 0.13513 | 0.05547 | 0.11959 |
| 9 | 8 | -5.4713 | 3.1381 | 0.07144 | 0.11782 | 0.15656 | 0.06322 | 0.13855 |
| 10 | 9 | -5.7838 | 3.2228 | 0.08269 | 0.13536 | 0.17797 | 0.07318 | 0.15750 |
| 11 | 10 | -6.0929 | 3.3086 | 0.09395 | 0.15252 | 0.19601 | 0.08315 | 0.17347 |
| 12 | 11 | -6.3949 | 3.3951 | 0.10312 | 0.16581 | 0.21515 | 0.09126 | 0.19041 |

## 6. The reported field is the field that was applied

A STAR-only comparison proves what the program *reported*. To prove what it *applied*, the
checker re-implements the corrector in Python -- global Fourier phase ramp with the C++
Nyquist-row convention, then bilinear resampling at `(ix - Lx, iy - Ly)` with the same edge
clamping -- drives it with the recovered field, sums the frames, and compares to the program's
own non-dose-weighted output.

| case | relative RMSE | classification |
|:--|--:|:--|
| `km_global_hisnr` | 6.83e-08 | numerical_noise |
| `km_local_hisnr` | 2.78e-07 | numerical_noise |
| `km_local_nonsquare` | 1.89e-06 | numerical_noise |

The defect-bearing cases are excluded from this check: hot-pixel replacement rewrites pixel
values from `rand()`, so the Python side is not driving the same input.

## 7. Harmless rounding versus a wrong field, measured

The residual above is dominated by the program working in float32 while the witness works in
float64. That floor is **measured**, not assumed. Walking the reported field away from the truth
and re-running the same comparison:

| injected field error (px) | relative RMSE | classification |
|--:|--:|:--|
| 0 | 2.778e-07 | numerical_noise |
| 1e-06 | 2.726e-07 | numerical_noise |
| 1e-03 | 1.005e-05 | numerical_noise |
| 0.01 | 1.018e-04 | field_defect |
| 0.1 | 1.019e-03 | field_defect |
| 0.5 | 5.087e-03 | field_defect |

A rounding-scale field change is indistinguishable from no change at all. A 0.1 px field error
sits 3669x above the floor. The decision boundary, 1e-04 relative RMSE, is two and a half orders
of magnitude above the measured floor and an order of magnitude below a 0.1 px defect.

The same separation holds in the motion metrics themselves: perturbing the field by 1e-06 px
leaves every gated metric unchanged to five digits and the case passes, and it is reported under
`numerical_noise` rather than silently ignored.

## 8. Negative controls

`tools/test_known_motion.py`, 27 checks, all passing. Each control rewrites a field MotionCorr
itself produced and requires the checker to fail **on the metric that should notice**.

| control | amplitude | outcome | metric |
|:--|:--|:--|:--|
| one frame displaced | 0.60 px | rejected | global component 0.147 A |
| trajectory scale error | 5 % | rejected | constant offset |
| local field error at corners | 1.00 px | rejected | local component 0.271 A, **global still passes** at 0.008 A |
| whole field sign-flipped | - | rejected | 3.750 A |
| x and y exchanged | - | rejected | 3.511 A |
| constant bias on frames 2..N | 0.25 px | rejected | constant offset 0.201 A, **frame-to-frame still passes** at 0.068 A |
| rounding-scale perturbation | 1e-06 px | **accepted** | worst gated metric 5.27e-02 A, unchanged |

The last two rows are the point of the exercise: the gate separates a real field defect from an
accounted-for constant and from harmless arithmetic, and the local-field control fails *only* the
local metric while the global trajectory still passes -- which is the defect class the previous
gates could not see at all.

Amplitudes are derived from the declared tolerances, not from what happens to trip the gate. A
single frame displaced by `d` contributes `d/sqrt(N)` to an RMS over `N` frames, so at 12 frames a
0.30 px single-frame error is 0.077 A and is **below tier B by construction**; demanding its
rejection would demand that the gate violate its own specification. The suite therefore also
measures where the boundary falls, by bisection:

| defect | detected above |
|:--|:--|
| one frame displaced | 0.408 px = 0.361 A |
| trajectory scale error on every frame | 2.36 % |
| local field error at the corners, last frame | 0.681 px = 0.603 A |
| constant bias on every frame but the first | 0.126 px = 0.111 A |

## 9. Ground-truth error versus reference disagreement

The first build of these fixtures produced a clean, reproducible, monotonic 2.2 % under-estimate
of the global trajectory, reaching 0.138 px by frame 12. It looked exactly like a MotionCorr
defect and would have been reported as one.

It was not. Rendering particles without periodic wrapping leaves a band of width `|shift|` along
two edges holding content in one frame and nothing in the other, and a Fourier shift is cyclic,
so any full-frame cross-correlation optimum is dragged toward zero. An estimator sharing no code
with MotionCorr reproduced MotionCorr's answer rather than the declared truth, and cropping 20 px
of border recovered the declared truth to 1.5e-4 px. The base image is now periodic; the residual
trajectory bias is 0.024 px and the pixel-level estimator agrees with the declared field to
1.4e-3 px on the full frame.

That check is now permanent -- `tools/test_known_motion.py` section 2, run on every invocation.
It is also worth noting that the gate's own scale sensitivity is 2.36 %, so it would **not** have
caught this 1.2 % artefact. Validating the truth against its own pixels is a separate obligation
from gating the program, and neither substitutes for the other.

## 10. Why `km_local_noisy` fails, and why the limit was not moved

`km_local_noisy` fails every gated metric at realistic per-pixel SNR. Three measurements
establish that this is the estimator running out of information, not a defect in the field.

**Noise response**, same injected field, per-pixel noise sigma as a multiple of the noise-free
image standard deviation:

| noise sigma / signal | per-pixel SNR | global RMS (A) | local RMS (A) |
|--:|--:|--:|--:|
| 0.05 | 20 | 0.0136 | 0.0893 |
| 0.5 | 2 | 0.0204 | 0.0764 |
| 2 | 0.5 | 0.0563 | 0.1054 |
| 5 | 0.2 | 0.1293 | 0.2621 |
| 10 | 0.1 | 0.2508 | 0.5796 |

The error is proportional to the noise amplitude above a floor: estimator variance.

**Bias versus variance**, eight replicates differing only in the detector-noise stream: per
replicate 0.76-1.53 A, scatter component 1.05 A, mean error field 0.50 A -- consistent with zero
bias at the resolution eight replicates provide. A systematic defect would survive averaging.

**Information content.** A 4x4 grid on 512x512 with 12 frames gives 197k pixel-frames per patch.
A 5x5 grid on a 3710x3838 tutorial movie with 24 frames gives 13.7 M -- seventy times more. A
patch-size sweep confirms error scaling as the inverse square root of that product. At that SNR,
local correction on this fixture is measurably *worse than doing nothing*: the injected local
deviation is 0.61 A RMS and the corrected residual is 0.72-0.93 A across patch grids.

`km_local_realscale` settles it: **identical** injected field, **identical** per-pixel SNR,
2048x2048 x 24 frames with 5x5 patches, 4.0 M pixel-frames per patch. Predicted from the scaling
law, 0.16 A. Measured, 0.146 A. It passes every declared tolerance.

So the tolerance is achievable at realistic noise given realistic scale, and `km_local_noisy`
stays in the suite as a characterization case -- reported in full, excluded from the aggregate,
numbers never hidden or relaxed. The "local correction is worse than no correction below a
patch-information threshold" observation is relevant to
[#11](https://github.com/KingAlejandro/MotionCorr-standalone/issues/11).

## 11. Scope, and what this does not establish

* Exact CPU parity and the corrected-image metrics are unchanged and still available through
  `tools/run_regression_tests.sh` and `tools/compare_motioncorr.py`. No source file under
  `src/`, no CI workflow, no `CMakeLists.txt`, and neither `docs/reference_gates.md` nor
  `tools/compare_motioncorr.py` was modified.
* All results here are CPU, `--use_own`, single-movie, on one macOS arm64 host. The tooling is
  backend-agnostic -- it reads an output STAR -- so a CUDA, Metal or hybrid run can be gated with
  the same command, but no accelerated backend was run for this report.
* Synthetic recovery accuracy is not a statement about scientific output quality on real data.
  That is [#61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61).
* Threshold calibration against controlled perturbations of *real* movies is
  [[#60](https://github.com/KingAlejandro/MotionCorr-standalone/issues/60)]; the local-field
  metric here is the one that issue can consume.
* `ctest`'s pre-existing `SyntheticRegression` test fails on this host against the committed
  `test-data/synthetic/expected/` baseline (image max pixel difference 23.6). It fails
  identically without any change from this work -- nothing under `src/` or `tests/` was touched
  -- and is not addressed here.
