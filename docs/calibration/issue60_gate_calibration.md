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

## 4. The instrument, and the defects its controls caught

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

---

## 8. Layer 1 -- response curves on real micrographs

Faults of exactly known magnitude injected into the six selection movies' own
CPU `--j 1` corrected micrographs, 252 cells. Median over the six movies. The
reference and the test differ by exactly the injected fault and nothing else.

| Fault | severity | relRMSE | **Δ*B* (Å²)** | shift px | eps_inc | max pixel | border/int |
|:---|---:|---:|---:|---:|---:|---:|---:|
| none (null control) | — | **0** | 4.6e-16 | 4.4e-20 | 4.0e-21 | **0** | — |
| translation | 0.10 px | 0.1681 | **6.4e-16** | 0.1000 | 3.1e-15 | 0.97 | 0.99 |
| translation | 0.25 px | 0.4136 | **1.0e-15** | 0.2500 | 3.1e-15 | 2.40 | 0.99 |
| translation | 1.00 px | 1.258 | **1.3e-15** | 1.0000 | 3.2e-15 | 7.08 | 0.99 |
| translation | 4.00 px | 1.395 | **1.4e-15** | 4.0000 | 3.2e-15 | 8.19 | 1.00 |
| jitter σ | 0.02 px | **0.00144** | 0.0251 | 7.6e-7 | 2.1e-4 | 0.009 | 0.99 |
| jitter σ | 0.05 px | 0.00906 | 0.1552 | 1.4e-5 | 1.4e-3 | 0.059 | 0.99 |
| jitter σ | 0.10 px | 0.0337 | 0.5962 | 1.6e-4 | 5.6e-3 | 0.215 | 0.99 |
| jitter σ | 0.20 px | 0.1389 | 2.719 | 7.1e-4 | 0.0166 | 0.96 | 0.99 |
| jitter σ | 0.40 px | 0.4097 | **9.911** | 6.0e-3 | 0.0748 | 2.83 | 0.99 |
| jitter σ | 0.80 px | 0.7743 | 40.02 | 0.0576 | 0.1289 | 5.18 | 0.99 |
| drift total | 0.05 px | 0.000517 | 0.0070 | 8.7e-18 | 3.3e-4 | 0.003 | 0.99 |
| drift total | 0.25 px | 0.0128 | 0.1753 | 5.3e-18 | 8.2e-3 | 0.071 | 0.99 |
| drift total | 1.00 px | 0.1809 | 2.815 | 1.1e-17 | 0.1133 | 1.03 | 0.99 |
| drift total | 2.00 px | 0.5022 | 11.38 | 1.6e-17 | 0.2958 | 2.99 | 0.99 |
| local field RMS | 0.05 px | 0.0756 | 1.489 | 4.9e-4 | 0.0516 | 0.77 | 0.91 |
| local field RMS | 0.20 px | 0.2829 | 6.208 | 1.5e-3 | 0.1816 | 2.61 | 1.08 |
| local field RMS | 1.00 px | 0.9889 | 44.98 | 0.0395 | 0.5816 | 7.57 | 0.99 |
| applied Δ*B* | 1 Å² | 0.0546 | **1.001** | 3.5e-18 | 3.7e-5 | 0.37 | 0.99 |
| applied Δ*B* | 5 Å² | 0.2332 | **5.004** | 1.2e-17 | 1.4e-4 | 1.60 | 0.99 |
| applied Δ*B* | 25 Å² | 0.6434 | **25.02** | 7.1e-18 | 2.0e-4 | 4.58 | 0.99 |
| applied Δ*B* | 50 Å² | 0.7957 | **50.04** | 1.5e-17 | 1.6e-4 | 5.69 | 0.99 |
| hot pixels | 1 | 0.0131 | 5.9e-4 | 5.2e-6 | 0.0131 | **42.8** | 0.00 |
| hot pixels | 100 | 0.1323 | 6.1e-3 | 1.0e-4 | 0.1323 | **44.9** | 1.06 |
| hot pixels | 10 000 | 1.325 | 0.0455 | 1.6e-3 | 1.325 | **46.5** | 1.01 |

Four things to read out of this table.

**The estimator is exact on real data.** Applied envelopes of 1, 5, 25 and 50 Å²
are recovered as 1.001, 5.004, 25.02 and 50.04. Translations of 0.1, 0.25, 1.0
and 4.0 px are recovered exactly, with Δ*B* at 1e-15 -- the floating-point floor.

**The closed-form prediction holds on real micrographs.** At σ = 0.4 px the
design record predicted Δ*B* = 8π²σ²a² = 9.895 Å² before any measurement; the
measurement is 9.911 Å².

**What relative RMSE = 0.001 actually means.** Three independent faults give the
same answer. Relative RMSE scales as σ² for jitter and as Δ² for drift, and
approximately linearly in Δ*B* for a direct envelope, so each row can be
extrapolated to the limit:

| Fault | severity at relRMSE = 0.001 | Δ*B* there | amplitude loss at 3 Å |
|:---|---:|---:|---:|
| random jitter | σ = 0.0167 px | 0.017 Å² | 0.048 % |
| systematic drift | 0.070 px total | 0.014 Å² | 0.038 % |
| applied envelope | — | 0.018 Å² | 0.051 % |

**The Gate 2 relative-RMSE limit of 0.001 sits at about 0.017 Å² of envelope
loss, or 0.05 % of amplitude at 3 Å. That is roughly 300x stricter than the
declared harm boundary of 5 Å².** It is not a scientific limit; it is close to a
bit-identity requirement expressed in floating point.

**Hot pixels are the one fault the envelope diagnostic cannot see**, and the
region split names them: the border/interior ratio is exactly 0.00 for a single
hot pixel, because the whole difference is one interior pixel. `eps_incoherent`
equals the relative RMSE to four figures in every hot-pixel row, which is the
signature of a difference the decomposition can explain none of.

---

## 9. Hold-out validation

The movie split and the severity split were frozen in `prespecification.py` and
committed at `2946770` before any measurement existed. The hold-out movies
`00042 00044 00046 00047 00048 00049` were not run until the selection matrix
was complete, and twelve further movies were never touched at all.

Two things were checked on the hold-out set, once.

**The zero floor holds on unseen movies.** All 114 hold-out runs exited 0. Every
harmless cell -- `--j 2/4/8`, `OMP_PROC_BIND` close/spread, five `--j 1` repeats,
five `--j 4` repeats, the unchanged-gain rewrite -- was bit-identical, on all six
movies. Largest value on any diagnostic across the whole harmless hold-out set:
`1.195e-15`, again the estimator's own floor.

**The fault response reproduces.** Maximum over six selection movies against
maximum over six different hold-out movies:

| Fault | Δ*B* selection | Δ*B* hold-out | relRMSE selection | relRMSE hold-out |
|:---|---:|---:|---:|---:|
| dose x 0.95 | 0.1943 | 0.1935 | 2.263e-2 | 2.237e-2 |
| dose x 1.25 | 0.7745 | 0.7655 | 9.935e-2 | 9.818e-2 |
| dose x 0.50 | 3.551 | 3.560 | 2.852e-1 | 2.824e-1 |
| gain x (1 + 1e-4) | 2.9e-3 | 4.8e-3 | 7.71e-3 | 6.74e-3 |
| gain x (1 + 1e-2) | 3.4e-3 | 1.3e-2 | 6.21e-2 | 6.33e-2 |
| one column +5 % gain | 2.5e-3 | 5.3e-3 | 8.11e-3 | 7.93e-3 |

The dose responses agree to better than 1.5 %, which is the well-behaved regime:
dose weighting is a deterministic filter and the same fault does the same thing
on every movie. The gain responses agree only to within a factor of about 4 on
Δ*B* -- these are the alignment-mediated faults, where the chaotic peak
selection makes the *particular* value movie-dependent even though its scale is
not. Both facts are used in section 10: thresholds are set against the stable
quantity, not the chaotic one.

---

## 10. Recommendation

**Nothing in this section has been applied.** It is a proposal, for review under
#58, supported by the measurements above. The `0.001` limit remains in force
until that review concludes.

### 10.1 How each candidate diagnostic performed

Across all three layers: 1129 cells, of which 481 are negligible-tier
(Δ*B* ≤ 1 Å², no translation above 0.1 px, no scale error above 1 %), 512 are
unacceptable-tier, and 136 are marginal. "Max on negligible" and "min on
unacceptable" are what determine whether a false-positive-free threshold exists
at all; a ratio above 1 means one does.

| Diagnostic | max on negligible | min on unacceptable it owns | ratio | verdict |
|:---|---:|---:|---:|:---|
| `image_relative_rmse` | 4.884 | 0.0592 | **0.012** | distributions overlap 80x; no threshold separates |
| `image_rmse` | 20.54 | 0.0477 | 0.0023 | no threshold separates |
| `image_max_abs_error` | 228 | 0.765 | 0.0034 | no threshold separates |
| `rel_rmse_low / mid / high` | 2.88 / 4.84 / 9.24 | 0.0041 / 0.0106 / 0.0119 | ≤ 0.0022 | no threshold separates |
| `rel_rmse_interior / border` | 4.94 / 4.91 | 0.0591 / 0.0606 | 0.012 | no threshold separates |
| `std_eps_incoherent` | 4.883 | 1.6e-15 | 3e-16 | no threshold separates |
| `traj_max_shift_error` | 0.0274 | 0 | 0 | blind to geometry and dose faults |
| `traj_coord_rms_error` | 0.0162 | 0 | 0 | blind to geometry and dose faults |
| `field_rms_px` | 0.0315 | 0.0054 | 0.17 | no threshold separates (see note) |
| `hf_signal_retention_dev` | 4.454 | 0 | 0 | screen only |
| **`std_delta_b_a2`** | **1.705** | **5.004** | **2.93** | **separates** |
| **`std_shift_px`** | 0.1 | 0.1 | 1 | **separates**, see 10.3 |
| **`std_scale_dev`** | 0.01 | 0.01 | 1 | **separates**, see 10.3 |

Note on `field_*`: the displacement-field metrics are only available for the
layer-3 cells, where no fault reached the unacceptable tier through local
motion, so their ratio is not a fair test. They are reported, not judged.
Issue #59 owns that gate.

### 10.2 Why relative RMSE cannot be rescued by moving the number

The negligible-tier maximum for `image_relative_rmse` is 4.884 and the
unacceptable-tier minimum is 0.0592. The two populations overlap by a factor of
80, so **no value of the limit gives both a low false-positive and a low
false-negative rate.**

That maximum is set by hot pixels, which this report's harm criterion cannot
see. Excluding them, and then also excluding translation and uniform scale --
the most generous possible reading -- still leaves:

| Negligible-tier subset | cells | max relRMSE | fraction exceeding 0.001 |
|:---|---:|---:|---:|
| all | 481 | 4.884 | **57.8 %** |
| excluding hot pixels | 381 | 0.176 | 46.7 % |
| excluding hot pixels, translation and uniform scale | 336 | 0.137 | **41.4 %** |

Even on the most generous subset, the current limit fires on 41 % of cells that
cost essentially no recoverable signal, and the worst of them (0.137, 137x the
limit) is a σ = 0.05 px residual jitter costing 0.16 Å², i.e. 0.45 % of
amplitude at 3 Å.

### 10.3 Measured clean band for each discriminator

Before proposing a limit, the honest question is how wide the gap is between the
largest value a diagnostic takes on something harmless and the smallest value it
takes on the thing it is supposed to catch. Measured over all 1129 cells:

| Discriminator | largest on negligible cells outside its own fault class | smallest on the fault it must catch | clean band |
|:---|---:|---:|---:|
| `std_delta_b_a2` | 1.705 Å² (any negligible cell) | 5.004 Å² (smallest unacceptable envelope) | **2.9x** |
| `std_shift_px` | 1.42e-2 px (10 000 hot pixels) | 0.1 px (smallest injected translation) | **7.0x** |
| `std_scale_dev` | 9.79e-3 (10 000 hot pixels); 9.29e-3 (σ = 0.05 px jitter) | 9.89e-4 (a 0.1 % gain error) | **none** |

`std_scale_dev` fails this test and the reason is a property of the estimator,
not of the fault: when the envelope fit is rejected for low R², the
least-squares scale absorbs part of the blur, so motion faults push `scale_dev`
up to about 9e-3. It can separate a 1 % gain error from the rest with a margin of
only 1.02x, and it cannot detect a 0.1 % gain error at all without alarming on
blur. **It is therefore recommended as a warning, not as a blocking check**,
despite separating cleanly when scored against the declared 1 % clause.

### 10.4 Proposed classification

| Check | Class | Proposed limit | Basis |
|:---|:---|:---|:---|
| every metric exactly 0 | **strict CPU regression** | exact equality, same platform | measured: 228 runs over twelve movies, `--j 1/2/4/8`, three thread placements, five repeats, all bit-identical. Strictly stronger than the present `--gate exact` 1e-7 tolerances, and it costs nothing because it is already met. |
| `std_delta_b_a2` | **blocking** | **≤ 2 Å²** | the only diagnostic that separates a boundary it was not handed: 2.9x clean band, FP 0/391 and FN 0/146 on selection, FP 0/90 and FN 0/168 on hold-out, unchanged at harm boundaries of 2, 5 and 10 Å². 2 Å² is 5.4 % amplitude loss at 3 Å. |
| `std_shift_px` | **blocking** | **≤ 0.05 px** | 7.0x clean band (1.42e-2 px on any non-translation cell against 0.1 px for the smallest injected translation). Catches the accounted-for-translation case that the trajectory metrics miss entirely. |
| exit status, STAR schema, static metadata | **blocking** | unchanged | no evidence to revise |
| `std_scale_dev` | **warning** | report | no clean band; see 10.3. It still *identifies* a uniform gain error exactly once one is suspected, which is its real value. |
| `image_relative_rmse` | **warning** | report the value, do not fail | 41--58 % false-positive rate on negligible cells at 0.001; no separating value exists at any limit |
| `image_rmse`, `image_max_abs_error` | **warning** | report | same; `max_abs_error` additionally cannot distinguish 1 defect from 10 000 |
| `traj_max_shift_error`, `traj_coord_rms_error` | **warning** outside strict CPU regression | report | never approached their current limits by any CLI-reachable fault (largest observed 0.0274 px against a 0.05 px limit), and exactly zero for every dose fault and for an accounted-for translation |
| `std_eps_incoherent`, band and region splits | **warning / attribution** | report | they explain *what kind* of difference occurred; none separates |
| displacement-field metrics | deferred to **#59** | — | measured here, not proposed as a gate |

### 10.4.1 Panel behaviour

No single diagnostic can do the job: a rigid translation has zero envelope loss
by construction. The two blocking checks are a panel, and its measured behaviour
at the declared 5 Å² harm boundary is:

| Panel | Split | Detection | False alarms |
|:---|:---|---:|---:|
| Δ*B* ≤ 2 Å² alone | combined | 340/512 (0.664) | 0/481 (0.000) |
| Δ*B* ≤ 2 Å² + shift ≤ 0.05 px | selection | 199/242 (0.822) | 18/391 (0.046) |
| Δ*B* ≤ 2 Å² + shift ≤ 0.05 px | hold-out | 253/270 (0.937) | 0/90 (0.000) |
| Δ*B* ≤ 2 Å² + shift ≤ 0.05 px + scale ≤ 0.01 | selection | 242/242 (1.000) | 18/391 (0.046) |
| Δ*B* ≤ 2 Å² + shift ≤ 0.05 px + scale ≤ 0.01 | hold-out | **270/270 (1.000)** | **0/90 (0.000)** |
| Δ*B* ≤ 2 Å² + shift ≤ 0.05 px + scale ≤ 0.01 | combined | **512/512 (1.000)** | 18/481 (0.037) |

All 18 false alarms are the same cell: the layer-1 and layer-2 translation cells
at exactly 0.1 px, which the declared clause (`> 0.1 px` is unacceptable) puts in
the negligible tier by strict inequality. Any translation limit below 0.1 px
alarms on them by construction. They are not evidence of a real false-alarm
mode, and they do not appear in the hold-out split, whose translation severities
are 0.25, 1.0 and 4.0 px.

The two blocking checks alone reach 88.3 % detection, missing only the uniform
gain errors, which is exactly what section 10.3 predicts. Adding `scale_dev` as
a *warning* rather than a gate leaves those reported but not failing, which is
the right outcome for a fault that costs no signal.

The recommendation does not depend on the declared harm boundary: moving it from
5 Å² to 2 or 10 Å² leaves every classification and every limit unchanged.

### 10.5 Uncertainty

* **Sampling.** Six selection and six hold-out movies from one collection on one
  platform. Movie-to-movie spread is the relevant unit and is reported in
  section 9: the deterministic faults reproduce to better than 1.5 %, the
  alignment-mediated ones only to within a factor of about 4 on Δ*B*. The
  proposed Δ*B* limit of 2 Å² sits 2.9x below the smallest unacceptable value
  measured and 1.2x above the largest negligible one, so the margin on the
  *negligible* side is thin and is the place a larger sample could move the
  answer.
* **Harm estimator.** Absolute harm from layer 2 scatters by up to ±1.8 Å² at
  the lowest signal-to-noise, so cells near the 2 Å² limit are assigned to a
  tier with real uncertainty. The reference-measured Δ*B* used by the gate
  itself has no such floor: it reads 1e-15 on identical inputs.
* **Harm currency.** Δ*B* measures envelope loss and nothing else. It is blind
  to incoherent damage, which is why `image_max_abs_error` is retained as a
  warning even though it grades nothing.
* **Estimator contamination.** `std_scale_dev` picks up blur when the envelope
  fit is rejected for low R², which is why it has no clean band. A better scale
  estimator would probably recover one; that was not attempted here because it
  would mean tuning the instrument after seeing the data.
* **Not established.** Section 11.

### 10.6 The single recommended next step

Run `tools/calibration/decompose_pair.py` on the CUDA corrected micrographs from
#36 against their CPU references. The files are already on disk, no GPU is
needed, and it takes seconds per movie. It converts the recorded relative-RMSE
range of 0.0029--0.0100 into an amplitude loss in percent at a stated resolution,
which is the number #36, #58 and #61 all actually need and none currently has.

---

## 11. What this does not establish

Stated plainly, because a calibration that only lists its successes is not
usable as evidence.

1. **No CUDA measurement was made.** No GPU run was launched. Section 1's remark
   that the recorded CUDA range sits inside the measured saturation band is a
   *consistency observation*, not a finding. The decisive test is cheap and
   GPU-free: run `tools/calibration/decompose_pair.py` on the CUDA corrected
   MRCs already on disk from #36. If Δ*B* is below 1 Å² and `eps_incoherent` is
   at the ~1e-2 saturation scale, the CUDA difference is arithmetic
   non-identity. If Δ*B* is several Å², it is real signal loss. That is a
   recommendation to #36's owner, not a claim here.

2. **Four faults were never exercised through the real binary.** Random
   inter-frame jitter, systematic drift bias, corrupted local deformation, and
   applied envelope attenuation are not reachable through the CLI without
   editing the alignment engine. Editing it would collide with the CUDA and
   optimisation branches and would make the perturbation itself a confound.
   They are measured in layers 1 and 2 only. Every claim about them rests on a
   model of the pipeline rather than the pipeline.

3. **Layer 1 overstates image error for a given harm.** Applying a shift-average
   to an already-summed micrograph blurs the summed noise as well as the
   signal; the real pipeline blurs only the signal, because each frame's noise
   is independent. Layer 2 handles this correctly and is the source of every
   harm number quoted.

4. **The harm boundary is a judgement.** Δ*B* > 5 Å² was declared in advance and
   corresponds to 13 % amplitude loss at 3 Å. Section 10 re-reports every
   conclusion at 2 and 10 Å². It is not derived from a reconstruction
   experiment; measuring the map-level consequence is issue #61's deliverable.

5. **The signal-quality screen is a screen.** `hf_signal_retention` is a
   band-limited power ratio. It cannot distinguish signal from noise, so a
   backend that adds high-frequency noise scores above 1.0. A CTF-fit or FSC
   measurement is #61's work and was deliberately not duplicated.

6. **Sample size is pilot scale.** Six selection and six hold-out movies, one
   dataset, one platform, one compiler. Uncertainty is quoted per movie, not per
   pixel; twelve movies of one collection are not twelve independent
   observations of "cryo-EM data".

7. **The zero floor is a property of this build on this host.** It is a strong
   result, but it does not prove that no CPU configuration anywhere produces
   nonzero variation -- only that thread count 1--8 and thread placement do not,
   on Linux/GCC 13.3/FFTW 3.3.10, over 228 runs on twelve movies. A macOS or
   different-FFTW measurement could differ and has not been made.

8. **The translated-movie cell uses a circular roll**, so a 2 px strip wraps.
   Its residual `eps_incoherent` of 0.081 includes that artefact; the
   translation and Δ*B* figures do not depend on it.

---

## 12. Reproduction

Every command below was run as written. Substitute your own paths.

**Build (Release is mandatory; an unqualified configure produces `-O0`):**

```sh
cmake -S src -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
cmake --build build -j 16
sha256sum build/motioncorr        # d88a6c02...84a4f8
```

**Controls -- run these first; nothing below is meaningful if they fail:**

```sh
python3 tools/calibration/test_calibration.py
python3 tools/calibration/prespecification.py      # prints the frozen matrix
```

**Layer 3, the real binary (CPU only):**

```sh
python3 tools/calibration/layer3_pipeline.py --emit-manifest work/manifest_selection.json \
  --movies selection \
  --gain-variants '{"null":"Movies/gain_null.mrc","1e-04":"Movies/gain_1e-04.mrc","1e-02":"Movies/gain_1e-02.mrc","badcol":"Movies/gain_badcol.mrc"}'

python3 tools/calibration/layer3_pipeline.py --execute work/manifest_selection.json \
  --binary $PWD/build/motioncorr --tutorial $PWD/work/tutorial \
  --stars $PWD/work/star --results $PWD/work/results --workers 8

python3 tools/calibration/layer3_pipeline.py --collect work/manifest_selection.json \
  --results $PWD/work/results --out work/layer3_selection.json
```

Repeat with `--movies holdout` for the hold-out matrix.

**Movie-space faults (note `--flip-y`; see section 7.3):**

```sh
python3 tools/calibration/make_perturbed_movies.py \
  --tiff work/tutorial/Movies/20170629_00021_frameImage.tiff \
  --gain work/tutorial/Movies/gain.mrc \
  --outdir work/tutorial/Movies --tag 00021 --shift-px 2 --hot-counts 100 10000 --flip-y
```

**Layer 1 and layer 2:**

```sh
python3 tools/calibration/layer1_inject.py \
  --reference 00021=work/results/00021__j1_rep0/out/Movies/20170629_00021_frameImage.mrc \
  ... --out work/l1/layer1_selection.json

for ns in 3 10 20; do
  python3 tools/calibration/layer2_forward.py --trials 5 --size 1024 1024 \
    --frames 24 --noise-sigma $ns --out work/l2/layer2_ns${ns}.json
done
```

**Analysis and tables:**

```sh
python3 tools/calibration/analyze.py \
  --layer1 work/l1/layer1_selection.json \
  --layer2 work/l2/layer2_ns*.json \
  --layer3 work/layer3_selection.json work/layer3_holdout.json \
  --out docs/calibration/data/analysis.json

python3 tools/calibration/summarize.py --layer3 ... --layer1 ... --layer2 ... --stat max
```

**Decompose an existing pair, e.g. a CUDA output against its CPU reference
(read-only, no backend re-run):**

```sh
python3 tools/calibration/decompose_pair.py \
  --pair "cuda_00021=cpu/.../00021.mrc:cuda/.../00021.mrc" \
  --ref-star "cuda_00021=cpu/.../00021.star" \
  --test-star "cuda_00021=cuda/.../00021.star"
```

Wall time on `cpu64` with 8 workers: layer 3 selection 114 runs in about 10
minutes, hold-out the same, layer 2 about 10 minutes for 630 cells, layer 1
about 35 minutes for 246 cells on 3710 x 3838 micrographs.

---

## 13. Relationship to the neighbouring issues

* **#58 (gate semantics).** This report supplies the measurement #58 needs: the
  `0.001` relative-RMSE limit has no measured relationship to lost signal, and
  the "non-associative parallel reduction" justification is not supported on
  this CPU build. The threshold proposal in section 10 is offered to #58 as
  evidence, not as a change. `docs/reference_gates.md` was not edited.
* **#59 (known motion and local displacement field).** The displacement-field
  evaluator here reproduces `Micrograph::getShiftAt` and reports constant offset
  separately from frame-to-frame change, in px and Å, as #59 requires. It is
  used for calibration only; **no displacement-field gate is proposed here**, and
  none of #59's files were touched. The schema in the design record section 5.1
  is offered as a coordination point. The #59 known-motion framework was not
  available on `origin` while this work ran, so layer 2 builds its own forward
  model; if #59 publishes fixtures, layer 2's `make_object` and
  `true_trajectory` should be replaced by imports.
* **#36 (CUDA divergence).** Section 11.1 is the concrete, GPU-free next step.
  The chaotic-amplification mechanism measured in section 7.1 is a candidate
  explanation for the 0/24 failure that requires no CUDA defect.
* **#61 (scientific non-inferiority).** Δ*B* in Å² and its amplitude-loss
  conversion are offered as the pre-registrable non-inferiority margin currency.
  No downstream refinement work was done and none is claimed.
* **Movie I/O.** Section 7.3 reports a row-order asymmetry between the TIFF and
  MRC movie readers. It is reported, not fixed.

---

## 14. Files

| Path | Contents |
|:---|:---|
| `agents/designs/issue_60_gate_calibration.md` | design record and prespecification rationale |
| `tools/calibration/prespecification.py` | the frozen matrix, splits, harm tiers and decision rule |
| `tools/calibration/diagnostics.py` | existing Gate 2 metrics plus the candidate diagnostics |
| `tools/calibration/perturbations.py` | fault operators, each in declared physical units |
| `tools/calibration/test_calibration.py` | the eleven controls |
| `tools/calibration/layer1_inject.py` | layer 1 driver |
| `tools/calibration/layer2_forward.py` | layer 2 forward model |
| `tools/calibration/layer3_pipeline.py` | layer 3 manifest / execute / collect |
| `tools/calibration/make_perturbed_movies.py` | movie-space faults and container control |
| `tools/calibration/analyze.py` | noise floor, response curves, threshold search, hold-out |
| `tools/calibration/summarize.py` | the tables in this report |
| `tools/calibration/decompose_pair.py` | decompose any existing pair of corrected micrographs |
| `docs/calibration/data/*.json` | every measurement behind every number above |
