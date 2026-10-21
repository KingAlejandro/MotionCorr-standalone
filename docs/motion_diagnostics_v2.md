# Versioned motion diagnostics v2

This is an additive extension of merged #63 and integrated #79 for #238/#262.
The 2026-10-21 check of open PRs, synthetic/known-motion PR history and all 234
remote branches found no active implementation of this new family. Operator
repairs #254/#260 and evidence #261 remain separate. Base: `3691374061f782bc84531fd1c79d017ddcb5a7c2`.

## Why a separate version

The historical generator evaluates `B(p-M(p))` and records `-M(q)` as the correction.
For a spatially varying field, `p-M(p)` is generally not the inverse of `p=q+M(q)`.
Consequently the historical claim that every local residual is estimator error is
too strong. This is a fixture-truth limitation, not evidence of an estimator bug.
The old generator, manifests, results and thresholds are untouched; do not silently
regenerate them. The new controls explicitly fail the naive-negation inverse.

The first increment uses analytically invertible affine controls. Nonlinear
fields need independently converged inversion and Jacobian/closure checks in a
later version; they are deliberately absent here.

## Coordinate contract

- `q=(x,y)` is a continuous material/reference coordinate; integer pixel centers
  start at (0,0). x increases by column, y by row. `p` is a detector coordinate.
- Frames are zero-based internally, five frames, reference frame 0. STAR frames
  are 1-based with start frame 1. Pixel size is 0.885 Å/px, binning 1 only.
- Forward map: `p=F_f(q)=q+g_f+A_f(q-c)`, `c=(nx/2,ny/2)`.
  Inverse: `q=(I+A_f)^-1(p-g_f+A_f c)`. Movies evaluate the continuous image
  at this inverse, then add independent detector-coordinate Gaussian noise.
- Truth is the **output-coordinate pull displacement** `D_f(q)=q-F_f(q)`.
  Correction samples raw frame `f` at `q-D_f(q)`. It is not a detector-coordinate
  forward displacement. This distinction prevents the historical inverse error.
- Global correction is `-g_f`; the local correction is `-A_f(q-c)` evaluated in
  output/reference coordinates. Applying global translation first and then local
  resampling samples the raw image at `q-L_f(q)-G_f`. The sum here is valid because
  the first operation is a constant translation. Do not generalize it to two
  spatially varying fields. Affine local terms and their linear time dependence
  lie in the existing polynomial model.
- The continuous scene is defined on the plane, without clipping/wrapping in
  synthesis. Fourier modes are periodic; localized Gaussians are not. Detector
  samples are finite. Evaluation uses the fixed half-open ROI `y=[12,84),
  x=[12,116)`, declared before estimator runs and valid for every true map.
  Candidate samples outside the detector are errors, never used to shrink the ROI.
  Full-grid border field statistics remain separately visible. Production Fourier
  wrapping and two-stage resampling can introduce additional differences.
- Gauge is fixed to frame-0 material coordinates. No constant subtraction,
  per-frame registration, fitted gain, or image recentering is permitted.

The generator validates both map round trips on every detector pixel and continuous
signal closure. A separate scalar determinant inverse, translated pixel slices,
and a naive-negation mutant test check the convention without production warping.

## Small deterministic family

All cases are 128×96×5; the entire generated directory is about 10 MB. Inputs are
float32 MRC, dense truth is float64 NPY, target is float32 NPY, and input STAR is
provided. Only recipes, generation receipts and small control reports are committed.

| Case | Motion / signal variation | Role |
|---|---|---|
| zero | no motion | field gate |
| integer | `(f,-2f)` px | field gate |
| fractional | `(3.25,-2.125) f/4` px | field gate |
| affine | fractional plus smooth shear/strain | field gate |
| pedestal | affine; DC 4096, contrast 0.25 vs 100, 1 | field gate |
| noisy | affine; detector Gaussian sigma 4, PCG64 seed 238262 | characterization |
| flat | constant scene, nonzero motion | unidentifiable characterization |
| repeated | x cosine of period 16, no y signal | ambiguous characterization |

The ordinary scene combines four declared cosine modes `(kx,ky)` = `(3,2)`,
`(7,-3)`, `(11,5)`, `(19,-13)` cycles per full image, plus asymmetric analytic
Gaussian landmarks. This provides known frequency content below Nyquist without
using a production FFT/warp to generate pixels. No CTF, dose damage or detector
MTF is claimed. The affine movie is not strictly band limited. Non-unit pixel size
and nonsquare geometry exercise units and axis normalization. Pedestal changes
occur before detector preprocessing, so this is not a stage-isolated CCF DC test.

## Reproduce and evaluate offline

```sh
OPENBLAS_NUM_THREADS=1 python3 tools/test_motion_diagnostics.py -v
python3 test-data/generate_motion_diagnostics.py --outdir /tmp/km-v2-new
# An exact-truth positive control, NOT an estimator result:
python3 tools/check_motion_diagnostics.py --fixtures /tmp/km-v2-new \
  --case affine --candidate /tmp/km-v2-new/affine_field.npy --json /tmp/control.json
# After separately running MotionCorr on affine.star from the fixture directory:
python3 tools/check_motion_diagnostics.py --fixtures /tmp/km-v2-new \
  --case affine --candidate /path/to/output/affine.star \
  --summed-image /path/to/output/affine.mrc --json /tmp/estimated.json
```

Use all five frames, binning 1, no dose weighting for the optional summed-image
comparison. A dense candidate NPY must have shape `(5,96,128,2)`, in pixels, with
this exact coordinate/gauge convention. It also provides an offline adapter
boundary for other estimators; no external dataset or network access is required.
STAR evaluation reuses the existing metadata reader only, not its corrector.
It measures serialized coefficients; full-precision native coefficients and their
separate serialization losses (#265) remain future work. Missing/invalid/nonfinite
inputs fail with exit 2. Fixture file hashes are checked against the generated
manifest, whose recipe and ROI must match this version.

Generation refuses an existing directory. `GENERATION_RECORD.json` records one
NumPy 2.3.5 generation, not a portable golden-byte assertion across libm/NumPy
versions. Repeated generation in the tested environment is byte-identical.
Each run records its own input hashes. Preserve old receipts and use a new version
for any changed recipe; do not rewrite historical acceptance baselines.

## Metrics and verdicts

Field error is reported as vector RMS/P95/max in pixels and Å, with per-frame,
spatial-mean and local residual components, plus a separate border report.
The field gate uses the existing 0.20/0.40/0.80 Å total RMS/P95/max limits,
without offset removal; it does not replace the historical global/local gates.
These tiny scenes are diagnostic controls, not a realistic low-SNR population.

Signal metrics compare uncorrected, true-motion bilinear corrected, and candidate
bilinear corrected averages with the independent motion-free target. The true
correction is a measured sampling/noise floor for this **independent one-stage
bilinear evaluator**, not a prediction of the production two-stage floor. A supplied
non-DW published sum is divided by five and compared separately. Absolute RMSE,
contrast-normalized RMSE (null on a flat target), and mean error are reported; a
large pedestal cannot hide error by inflating the normalization denominator.
Frequency-resolved transfer and resampling-matched production floors are follow-ups.

Signal is always labeled **CHARACTERIZATION** in this increment: there is no
calibrated signal acceptance limit. A field PASS never claims correct published
pixels. Application consistency is explicitly **NOT_TESTED** here; the historical
application witness remains available separately. Flat/repeated cases report
**UNIDENTIFIABLE**, plus numerical distance to the generated field; matching a
stored vector cannot establish measured motion in such images.

Characterization accuracy FAIL remains FAIL in JSON/text even though exit 0 allows
an experiment to complete. There is deliberately no overall scientific PASS.
The historical `km_local_noisy` failure remains unchanged and must accompany any
subsequent larger accuracy report; this new single seed cannot establish low-SNR
accuracy. No threshold was tuned from estimator output.

## Validation in this PR

CPU only, Python/NumPy 2.3.5, `OPENBLAS_NUM_THREADS=1`:
8 diagnostic unit/CLI tests, 8 historical verdict controls, 8 historical runner
controls pass. New tests cover analytic inverses, integer pixels, local closure,
sign/axis/unit/frame/local-field mutants, an independent bilinear plane, invalid
coordinates/nonfinite/shape inputs, ambiguous roles, deterministic artifact hashes,
refusal to overwrite, corrupt fixtures and CLI exit codes. CI runs the new suite.

`CONTROL_REPORT.json` is explicitly **generator/evaluator positive controls**, not
MotionCorr execution: the candidate is the exact stored truth. Affine uncorrected
RMSE is 0.4541, true-motion bilinear RMSE 0.02154 (contrast units); this illustrates
sampling loss, not native estimator accuracy. No MotionCorr binary, FFTW development
headers, nvcc or nvidia-smi are installed here. Native CPU/CUDA, full CTest, performance,
large/noisy seed campaigns and downstream science were not run. No merge is requested.

## Published-data reuse decision

[Střelák et al., 2023](https://www.mdpi.com/2072-666X/14/10/1835)
compare aligners using phantom movies, but the paper's phantom EMPIAR accession is
still printed as pending. Their [experiment scripts](https://github.com/danielmarchan3/ComparisonMovieAlignment-cryoEM)
provide a useful optional replication route, not a verified downloadable truth
corpus. No external movie or script is copied into this PR.

The [Xmipp phantom source](https://github.com/I2PC/xmipp3/blob/main/src/xmipp/libraries/reconstruction/phantom_movie.cpp)
carries GPL-2.0-or-later notices, compatible with this repository. Its current
implementation reverses time and uses backward sampling; paper equations alone
are insufficient to translate its motion convention. Before importing a phantom,
pin the generator commit, command, input/output hashes, software and data licenses;
export its clean target and independently validated forward/inverse maps, convert
them to the documented frame-0 gauge and dense candidate contract, and test closure.
The source link here is discovery provenance, not a pinned executable dependency.
The script repository's reuse license must be verified separately before copying.

**Decision:** retain the tiny independent analytic family for routine CI. Treat
Xmipp as a later optional offline cross-generator comparison, once its provenance,
truth sidecar and target are validated. Do not download a large corpus in CI or
label static particle/micrograph datasets as motion truth. Larger realism studies
should separately add nonlinear inverse closure, seed populations, CTF/dose/detector
models, grouping/binning, frequency transfer and Nyquist controls, then held-out
real-data scientific validation under #238/#61. They must retain every noisy or
ambiguous result rather than hiding it inside a gate-only aggregate.
