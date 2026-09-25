# Calibrating the MotionCorr numerical gates by controlled perturbation

Evidence report for [issue #60](https://github.com/KingAlejandro/MotionCorr-standalone/issues/60).

> **This report changes no gate.** `tools/compare_motioncorr.py` is untouched, the
> `0.001` relative-RMSE limit is unchanged, and no recorded PASS/FAIL result is
> reclassified. Section 10 is a *proposal* for separate review.

---

## 1. What was asked, and what was measured

Gate 2's six numerical limits were written down as provisional values. None was
derived from a measurement of how much motion-correction signal a violation
costs. This work injected faults of known physical magnitude into motion
correction, measured how each candidate diagnostic responds, and independently
measured how much signal each fault actually costs.

The four results that matter:

1. **The harmless-variation floor on this CPU build is exactly zero.** Across
   178 identical-configuration and thread-varied runs on twelve movies --
   `--j 1/2/4/8`, `OMP_PROC_BIND` unset/close/spread, five repeats each -- every
   corrected micrograph and every STAR trajectory was **bit-identical**. The
   largest value seen on any of fifteen diagnostics across every harmless cell
   was `1.478e-15`, which is the measuring instrument's own floating-point
   floor, not the pipeline's. Gate 2's stated justification, that "parallel
   reductions and different FFT implementations can alter results", is not
   supported for thread count or thread placement on this build.

2. **Relative RMSE does not measure lost signal, and cannot be made to.** A
   rigid coordinate translation of 2.83 px through the real binary gives a
   relative RMSE of **1.3993** -- 1399x the limit -- while costing **0.10 Å²** of
   envelope, i.e. 0.28 % of amplitude at 3 Å. A uniform 10 % gain error gives
   0.6292, 629x the limit, at 0.018 Å². In the forward model, two perturbations
   with identical harm (10 Å²) give relative RMSEs differing by 1.9x depending
   only on the micrograph's signal-to-noise ratio.

3. **The alignment amplifies arithmetic differences by about three orders of
   magnitude, then saturates.** Perturbing the gain reference by **one part per
   million** -- far below the float-versus-double difference in the CUDA path --
   already produces a relative RMSE of `2.04e-3`, twice the Gate 2 limit, at an
   envelope cost of `3.8e-4` Å² (0.001 % of amplitude at 3 Å). Increasing the
   input perturbation by four further decades does not increase the
   non-scale part of the output difference: it plateaus at about `1e-2`. Relative
   RMSE therefore behaves as a saturated detector of "arithmetic is not
   bit-identical", not as a graded measure of quality.

4. **A four-parameter decomposition of the same difference does separate harm
   from harmless.** Splitting a test-versus-reference difference into scale,
   translation, envelope loss (Δ*B*, in Å²) and an incoherent residual gives a
   measure of envelope loss that tracks absolute signal loss with a ratio of
   1.00 for envelope faults and 0.9--1.1 for motion faults, and is independent of
   signal-to-noise ratio, where relative RMSE varies by 1.9x over the same range.

An honest summary of the consequence: the recorded CUDA relative-RMSE range of
0.0029--0.0100 sits inside the band this work measures for *generic arithmetic
non-identity with negligible signal loss*. That is consistent with, but does not
prove, the CUDA differences being harmless; establishing which it is requires
running the decomposition on the CUDA outputs, which is a GPU-free analysis of
files already on disk. Section 11 states this as a recommendation to #36, not as
a finding of this report.

---

## 2. Provenance

Everything below is reproducible from the commands in section 12.

| Item | Value |
|:---|:---|
| Prespecification commit (frozen before any result was read) | `2946770eecf281112d552b29879f50167a073098` |
| Design record | [`agents/designs/issue_60_gate_calibration.md`](../../agents/designs/issue_60_gate_calibration.md) |
| Source tree | this branch, from `origin/main` at `3e3a19679337d3de61327c02eef1a2947cf13517` |
| Binary SHA-256 | `d88a6c028892fb55f10e42e0fc18ccf8e9d047b391785af8e2601675c384a4f8` |
| Build | `cmake -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF`, verified `-O3 -DNDEBUG` |
| Host | `cpu64` (`small-refmac-machine`), Linux 6.8.0-86, 64 cores, 226 GiB |
| Toolchain | GCC 13.3.0, FFTW 3.3.10 (`fftw3f`), CMake 4.4.3 |
| Analysis | Python 3.12.3, NumPy 1.26.4 |
| GPU host | **not used.** No GPU run was launched by this work. |

Input SHA-256, all matching the documented `spa-tutorial-data-v1` release:

```
df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0  20170629_00021_frameImage.tiff
87c2640f5c2200c2f8e62e7dd50f4aa2d694fac2238743560b7c705fb0e61f3f  20170629_00023_frameImage.tiff
798cf7b0cd24aef070d69525543214bdd60a3900667d7d3a32dfe3bffe9fce1a  20170629_00025_frameImage.tiff
adb4fbf597ca78387b22c4a2452c7351499f7b78fb2da67bc5fdd52e4bc58a39  20170629_00027_frameImage.tiff
91a985fddf18a7388740d601d6909c6de3a28c7df98d2d263126c8dd90e9f234  20170629_00029_frameImage.tiff
fa2699a1203a2ee278a5973e10105ea3e56b18a1c1d5ee153482767cb7e71d8d  20170629_00031_frameImage.tiff
8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1  gain.mrc
```

Common options for every layer-3 run:
`--use_own --seed 1 --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc`,
with `--j`, `--dose_per_frame` and `--gainref` varied as the matrix specifies.
Pixel size 0.885 Å (Nyquist 1.77 Å), 200 kV, 24 frames of 3710 x 3838.

---

## 3. What the diagnostics are

Relative RMSE collapses four physically distinct differences into one number.
Writing a corrected micrograph as

> S(**r**) = g · (h ∗ T)(**r** − **t**) + n(**r**)

the four terms are a scale *g*, a rigid translation **t**, a blur *h* from
residual motion, and everything else *n*. Their scientific consequences are not
comparable: a uniform scale and a recorded translation cost nothing, while blur
is a direct loss of high-resolution signal and *n* can be arbitrary damage.

The **Spectral Transfer Decomposition** estimates all four from the shell-wise
complex transfer Γ(κ) = Σ Ŝ R̂\* / Σ |R̂|², giving

| Output | Meaning | Units |
|:---|:---|:---|
| `scale_dev` | \|*g* − 1\| | dimensionless |
| `shift_px` | \|**t**\| | pixels (also reported in Å) |
| `delta_b_a2` | envelope loss from the slope of ln\|Γ\| against −k²/4 | Å² |
| `eps_incoherent` | residual power after removing all three, as a fraction of reference power | dimensionless |

Δ*B* converts to a stated amplitude loss: `A_test/A_ref = exp(−ΔB / 4d²)`.

| Δ*B* (Å²) | amplitude loss at 3 Å | at 4 Å | equivalent residual jitter σ |
|---:|---:|---:|---:|
| 0.001 | 0.003 % | 0.002 % | 0.0040 px |
| 0.01 | 0.028 % | 0.016 % | 0.0127 px |
| 0.1 | 0.277 % | 0.156 % | 0.0402 px |
| 1 | 2.740 % | 1.550 % | 0.1272 px |
| **5** | **12.968 %** | **7.515 %** | **0.2843 px** |
| 10 | 24.253 % | 14.465 % | 0.4021 px |
| 50 | 75.065 % | 54.217 % | 0.8992 px |

The harm boundary Δ*B* > 5 Å² was **declared before measurement**; every
conclusion is re-reported at 2 and 10 Å² in section 10.

The last column uses the closed-form prediction Δ*B* = 8π²σ²a², derived in the
design record before any measurement. The forward model confirms it: at
σ = 0.4 px the prediction is 9.90 Å² and the measurement is 9.90 ± 0.04 Å².

Note what that column already implies. Gate 2's coordinate-RMS limit of 0.02 px
corresponds to Δ*B* = 0.0247 Å², or 0.07 % of amplitude at 3 Å. In harm terms
the trajectory gate is roughly 200x stricter than the declared harm boundary.

---

## 4. The instrument, and the four defects its controls caught

Eleven controls run in under a minute (`tools/calibration/test_calibration.py`):
a null control that must read exactly zero, analytic controls against
closed-form answers, a control that the existing Gate 2 metrics are reproduced
bit-for-bit from `tools/compare_motioncorr.py`, and a control that the
decomposition can never leave more residual than doing nothing.

They caught four defects in this work's own tooling. They are listed because a
calibration whose instrument was never falsified is not evidence:

1. **Biased subpixel shift estimation.** Parabolic fitting of the
   cross-correlation peak was wrong by up to 0.05 px on a broadband image --
   the same size as the entire Gate 2 max-shift limit. Replaced by a
   power-weighted phase-ramp fit, now exact to machine precision.
2. **Nyquist-line contamination.** A fractional Fourier shift of a real image is
   not representable on the self-conjugate Nyquist row and column. Including
   them gave every subpixel translation a spurious incoherent residual of
   `5e-3` of reference power -- five times the whole Gate 2 limit. That line is
   now excluded.
3. **Wrong noise handling in the forward model.** Per-frame noise was added
   *after* realignment, so two runs with different applied shifts shared an
   identical noise sum. This made a pure translation read as a 53 Å² envelope
   loss. The noise is laid down in detector coordinates and must be realigned
   with the frame.
4. **A decomposition that could increase the residual.** The scale was read off
   a single low shell rather than fitted by least squares; on a structured
   fault (one mis-gained detector column) it left a residual 4x larger than
   doing nothing. The scale is now the projection coefficient.

A fifth was caught by an experiment control rather than a unit test: see
section 7.

---

## 5. Layer 3 -- the harmless-variation floor is exactly zero

228 runs on twelve movies (six selection, six hold-out), all exit status 0.

| Harmless variation | cells | largest value on **any** diagnostic |
|:---|---:|---:|
| `--j 2`, `--j 4`, `--j 8` vs `--j 1` | 36 | 0 (bit-identical) |
| `OMP_PROC_BIND` close / spread at `--j 4` | 24 | 0 (bit-identical) |
| five identical `--j 1` repeats | 48 | 0 (bit-identical) |
| five identical `--j 4` repeats | 48 | 0 (bit-identical) |
| gain reference rewritten unchanged through this work's MRC writer | 6 | 0 (bit-identical) |
| movie re-encoded TIFF → MRC, row order matched | 2 | 0 (bit-identical) |
| **all harmless cells, 1246 diagnostic values** | **178** | **1.478e-15** |

The `1.478e-15` is this report's estimator evaluating Δ*B* on two identical
arrays; it is the instrument's floor, not the pipeline's. No output pixel, no
STAR field, and no trajectory differed anywhere in the harmless matrix.

Two consequences:

* Any nonzero difference from a CPU backend on this platform is **not**
  attributable to reduction order or thread placement, and a threshold justified
  by that mechanism has no measured basis here.
* Because the measured floor is exactly zero, the frozen negligible-tier rule
  ("Δ*B* ≤ 1 Å² **and** ε_inc ≤ noise floor") admits only bit-identical outputs.
  That is degenerate for threshold selection, so section 10 uses the Δ*B*
  criterion alone and reports ε_inc as a separate axis. **This is a documented
  deviation from the prespecification**, forced by the floor being zero, and it
  makes the recommendation *more* permissive rather than less.

A third observation, from an independent build: `#36`'s CPU reference binary
(`10e61a80…`, built from a different branch) and the CPU build of its FFTW-hybrid
branch (`c595f068…`) produce **bit-identical** corrected micrographs and STAR
files on movies `00021` and `00046`. Two independently configured Release CPU
builds of different source revisions agree exactly.

---

## 6. Layer 2 -- does a reference comparison measure real harm?

A gate never sees the truth; it sees another backend's output. The forward model
builds a synthetic movie from a *known noiseless object*, so absolute harm can be
measured and compared against what a gate would see. 630 cells: 5 trials x 3
noise levels x 42 fault cells, 1024 x 1024, 24 frames.

The bridge, median over 5 trials at each cell (full table in
`data/layer2_ns*.json`):

| Fault | Gate-visible Δ*B* | Absolute harm Δ*B* | ratio |
|:---|---:|---:|---:|
| applied envelope, 2 → 50 Å² | 2.01 → 50.13 | 2.01 → 50.19 | **1.00** at every point, every noise level |
| random jitter, σ = 0.1 → 0.8 px | 0.59 → 35.6 | 0.75 → 33.9 | 0.79 → 1.05 |
| systematic drift, 0.25 → 2 px | 0.17 → 11.4 | 0.14 → 10.9 | 1.04 → 1.28 |
| local deformation, 0.05 → 0.1 px | 1.49 → 3.04 | 1.63 → 3.36 | 0.90 → 0.94 |
| rigid translation, 0.1 → 4 px | **0.000 everywhere** | 0.04 → 1.79 (estimator noise) | — |
| hot pixels, 1 → 10 000 | ≈ 0 | not meaningful | — |

**Δ*B* measured against a reference is a faithful proxy for absolute signal
loss.** That is the claim that licenses using it in a gate, and it is measured,
not assumed.

Two further properties, both of which relative RMSE lacks:

* **Δ*B* is insensitive to image signal-to-noise.** At σ = 0.4 px jitter it reads
  9.97 / 9.93 / 9.90 Å² at the three noise levels. Relative RMSE over the same
  three reads 0.469 / 0.806 / 0.872 -- a 1.9x spread at identical harm.
* **Δ*B* is zero for a pure translation** at every severity up to 4 px, while
  relative RMSE climbs to 1.39.

Hot pixels are the complementary case: they produce no envelope signature at
all, and are caught only by `eps_incoherent`, which equals the raw difference
because the decomposition can explain none of it. The two diagnostics are
designed to be complementary and the measurements confirm they are.

### Estimator uncertainty

The absolute-harm estimator is noise-limited: on the translation cells, where
true harm is zero, it scatters by up to ±1.8 Å² at the lowest signal-to-noise.
**Absolute-harm claims below about 2 Å² from layer 2 are within that scatter.**
The gate-visible Δ*B* has no such floor (it reads 0.000 on the same cells)
because it compares two sums that share their noise.


---

## 7. Layer 3 -- real faults through the real binary

All values are the **maximum** over the six selection movies, so they are the
worst case a gate would face, not an average. The full per-movie records are in
`data/layer3_selection.json`.

| Fault | relRMSE | absRMSE | max pixel | scale_dev | shift px | **Δ*B* (Å²)** | eps_inc | traj max | field RMS px | border/int |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gain x (1 + 1e-6) | 2.04e-3 | 1.72e-3 | 1.60 | 1.19e-6 | 3.3e-4 | **3.8e-4** | 2.06e-3 | 2.9e-3 | 2.2e-3 | 9.07 |
| gain x (1 + 1e-4) | 7.71e-3 | 6.60e-3 | 1.79 | 1.02e-4 | 8.4e-4 | **2.9e-3** | 7.68e-3 | 9.9e-3 | 5.1e-3 | 2.71 |
| gain x (1 + 1e-3) | 8.80e-3 | 8.07e-3 | 2.18 | 1.00e-3 | 8.2e-4 | **1.5e-2** | 6.18e-3 | 1.0e-2 | 6.2e-3 | 1.50 |
| gain x (1 + 1e-2) | 6.21e-2 | 5.31e-2 | 2.43 | 1.00e-2 | 1.5e-3 | **3.4e-3** | 7.46e-3 | 9.6e-3 | 1.1e-2 | 1.03 |
| gain x (1 + 1e-1) | 6.29e-1 | 5.71e-1 | 3.06 | 1.00e-1 | 8.5e-4 | **1.8e-2** | 1.48e-2 | 1.6e-2 | 1.3e-2 | 1.03 |
| one detector column +5 % gain | 8.11e-3 | 6.54e-3 | 2.14 | 1.5e-5 | 1.7e-3 | **2.5e-3** | 8.45e-3 | 1.3e-2 | 1.0e-2 | 3.71 |
| dose x 0.95 | 2.26e-2 | 1.97e-2 | 0.18 | 6.2e-5 | 1.3e-4 | **0.194** | 2.15e-2 | **0** | **0** | 1.04 |
| dose x 1.25 | 9.94e-2 | 8.64e-2 | 0.79 | 6.2e-4 | 6.1e-4 | **0.775** | 9.93e-2 | **0** | **0** | 1.04 |
| dose x 0.50 | 2.85e-1 | 2.49e-1 | 2.14 | 6.7e-4 | 1.4e-3 | **3.551** | 2.65e-1 | **0** | **0** | 1.04 |
| movie translated 2.83 px (gain moved with it) | **1.399** | 1.182 | **7.79** | 8.2e-5 | **2.850** | **0.103** | 8.1e-2 | **0** | 8.5e-2 | 1.00 |
| 100 stuck-hot detector pixels | 1.57e-2 | 1.32e-2 | **7.04** | 1.7e-5 | 2.3e-3 | **9.5e-3** | 1.57e-2 | 1.1e-2 | 2.1e-2 | 1.98 |
| 10 000 stuck-hot detector pixels | 4.57e-2 | 3.86e-2 | **7.07** | 3.2e-5 | 6.4e-3 | **5.8e-2** | 4.54e-2 | 2.7e-2 | 3.2e-2 | 1.40 |

Gate 2 limits for comparison: relRMSE 0.001, absRMSE 0.020, max pixel 5.0,
traj max 0.05 px, traj coord-RMS 0.02 px. Bold entries above are where a
diagnostic is doing something a gate should care about.

### 7.1 A one-part-per-million input change already fails Gate 2

Perturbing the gain reference by 1e-6 -- one part per million, smaller than the
difference between a `float` and a `double` accumulation -- gives a relative
RMSE of `2.04e-3`. That is **2.0x the Gate 2 limit**, from an input change of
one part in a million, at an envelope cost of `3.8e-4` Å², which is 0.001 % of
amplitude at 3 Å.

Reading down the gain column, the *non-scale* part of the response does not grow
with the input perturbation. Between 1e-6 and 1e-1 the input changes by five
decades while `eps_incoherent` moves only from `2.1e-3` to `1.5e-2` and the
trajectory difference sits at 1e-2 px throughout. The alignment's peak selection
is chaotically sensitive: once the arithmetic differs at all, the trajectory
difference jumps to its own characteristic scale and stops growing.

This is the mechanism behind #36, demonstrated on the CPU with no GPU involved.
It means **relative RMSE cannot rank backends by quality**: it is close to a
binary detector of "not bit-identical", saturating at a value of order 1e-2 that
carries almost no information about signal loss. The recorded CUDA range of
0.0029--0.0100 falls squarely inside the saturated band measured here.

### 7.2 Two archetypal false alarms

**An accounted-for coordinate translation.** The movie and its gain reference
were rolled 2 px in each axis, so the same specimen lands on a different part of
the detector. The correct output is the same micrograph, translated. Gate 2's
image checks fail spectacularly -- relative RMSE 1.399 (1399x), absolute RMSE
1.182 (59x), max pixel error 7.79 (above the 5.0 limit) -- while the *trajectory*
checks pass with **exactly zero** difference, because the global shifts are
relative to frame 1 and so are unchanged.

The decomposition reads: translation 2.850 px (the construction applies
2√2 = 2.828 px), Δ*B* = 0.103 Å², `eps_incoherent` 0.081, explaining 99.8 % of a
raw difference of 1.399 as rigid translation. Amplitude cost at 3 Å: 0.28 %.

Two caveats, both from the construction rather than the pipeline: the roll is
circular, so a 2 px strip wraps; and the residual `eps_incoherent` of 0.081
includes that wrap.

**A uniform gain error.** A 10 % uniform gain scale gives relative RMSE 0.629,
629x the limit. `scale_dev` recovers the error as exactly `0.1000`, and Δ*B* is
0.018 Å². Particle extraction renormalises, so a uniform scale costs nothing
scientifically -- yet it is one of the largest Gate 2 failures in the whole
matrix.

### 7.3 The fifth defect, caught by an experiment control rather than a test

The movie-space arm needed the tutorial TIFF re-encoded as an MRC stack. Its
**null control** -- re-encode unchanged, run, compare -- came back at relative
RMSE **1.435**, which is larger than most of the deliberate faults.

The cause is that the TIFF and MRC movie readers disagree on row order. Flipping
rows on write makes the MRC path reproduce the TIFF run **bit-for-bit**
(relative RMSE exactly 0, max pixel difference exactly 0). Without that control,
every movie-space number in this report would have been the sum of a real fault
and an upside-down gain correction.

Two notes for whoever owns movie I/O: this is a real asymmetry between the two
input paths, and it is reported here rather than fixed, because fixing it is
outside this issue's scope. Separately, the first version of the translated-movie
cell rolled the gain *opposite* to the row flip; the probe in
`data/layer3_movies.json` compares both conventions and establishes empirically
that the gain imprint moves with the recorded movie (`eps_incoherent` 0.081
against 0.203, field max 0.20 px against 1.09 px).

### 7.4 Blind spots found

| Diagnostic | Blind to |
|:---|:---|
| `traj_max_shift_error`, `traj_coord_rms_error` | **every** dose-weighting fault (exactly zero at 5 %, 25 % and 50 % dose error), and an accounted-for translation (exactly zero at 2.83 px). Dose weighting is applied after alignment, so the global trajectory cannot see it. |
| `image_max_abs_error` | defect *count*. One hot pixel and ten thousand hot pixels give max errors within 6 % of each other. It is also the only Gate 2 limit crossed by the translation case (7.79 vs 5.0), and it is crossed at 1.6--3.1 by gain perturbations down to 1 ppm, so it is noisy as well as insensitive. |
| `std_delta_b_a2` | incoherent additive damage. Hot pixels give Δ*B* ≈ 0 regardless of count; `eps_incoherent` is what sees them. |
| `image_relative_rmse` | the difference between harm and reparameterisation. It is the largest number in the matrix for the two cases that cost nothing (translation 1.399, gain scale 0.629) and one of the smallest for a real 50 % dose error (0.285 at Δ*B* = 3.55 Å²). |
| `std_scale_dev`, `std_shift_px` | everything except their own term -- by design. They are discriminators, not detectors. |

The `border/interior` ratio is a useful signature: it reaches 9.07 for the 1 ppm
gain perturbation and 3.71 for a single mis-gained column -- faults that act
through alignment -- but sits at 1.03--1.04 for dose faults and 1.00 for the
translation, which act uniformly. It distinguishes *where* a difference lives,
which no current Gate 2 metric does.
