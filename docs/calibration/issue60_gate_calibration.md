# Calibrating the MotionCorr numerical gates by controlled perturbation

Evidence report for [issue #60](https://github.com/KingAlejandro/MotionCorr-standalone/issues/60).

> **This report changes no gate.** `tools/compare_motioncorr.py` is untouched, the
> `0.001` relative-RMSE limit is unchanged, and no recorded PASS/FAIL result is
> reclassified. Section 10 is a *proposal* for separate review.
>
> **Revised 28 September 2026** after four confirmed review findings on PR #64.
> **All three** proposed blocking checks are withdrawn as inconclusive and the
> published hold-out figures are superseded. Start at **§0**.

---

## 0. Review round, 28 September 2026 — corrections and superseded claims

Four findings were raised against this report at commit `059d8dd3`
([#64 review](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64)).
All four are real. Each is reproduced against the pre-review code by
`tools/calibration/reproduce_review_findings.py` and guarded going forward by
`tools/calibration/test_contracts.py`.

**No threshold was changed and no gate was relaxed to resolve them.** All three
proposed blocking checks are withdrawn as inconclusive as a result — including
the one that initially survived the split and tiering corrections, because the
Layer-2 dose arm restored by finding 4 is the arm it fails on (§6.1). The
withdrawal of the *blocking* status holds at all three declared harm boundaries;
at the loosest of them the envelope diagnostic does earn a **warning**-tier
limit, which §10.4.1 reports rather than suppresses.

| # | Finding | Status | Effect |
|:--|:---|:---|:---|
| [r4119255250](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255250) | Hold-out split lost | **confirmed** | `collect()` never copied `split` into Layer-3 records: **0 of 247** carried one, so all **120** hold-out-movie cells fell into the selection bucket and the published hold-out of 420 cells contained **no Layer-3 data at all**. Every hold-out FP/FN figure in the published §10 is superseded. |
| [r4119255253](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255253) | Accounted translation tiered harmful | **confirmed** | **112 of 130** X1 cells were harmful positives, so the proposed `std_shift_px` limit was derived from the benign reparameterisation this calibration exists to identify. Now 0. |
| [r4119255256](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255256) | Uniform scale tiered as frame-dependent harm | **confirmed** | The prespecification reserves its 1 % clause for a *frame-dependent* error; it was applied to the global scale estimate. 86 cells were tiered `unacceptable:scale`, of which 6 were uniform-gain faults and 80 were blur faults whose envelope fit had been rejected. Now 0. |
| [r4119255261](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255261) | Prespecified Layer-2 X6 dose arm absent | **confirmed** | The dose fault had no ground-truth harm bridge. Arm added and run; §6.1. |

A fifth item, raised on [#66](https://github.com/KingAlejandro/MotionCorr-standalone/issues/66),
is also confirmed: the PR body quoted **270/270** hold-out detection for the two
blocking checks, when two checks gave **253/270** and 270/270 required the scale
criterion that was itself only recommended as a warning. That figure is
withdrawn along with the rest of §10's published hold-out numbers.

### 0.1 What is superseded

| Published claim | Status |
|:---|:---|
| "hold-out 270/270 detection, 0/90 false alarms" | **withdrawn** — computed on a leaked split, and overstated even within it |
| `std_shift_px ≤ 0.05 px` blocking, "7.0x clean band" | **withdrawn, inconclusive** — its positive class was the accounted translation |
| `std_scale_dev` "separates cleanly against the declared 1 % clause" | **withdrawn, inconclusive** — its positive class was the uniform gain error, and the new C2 control shows the diagnostic is blind to the frame-dependent error the clause actually names (§10.3) |
| `std_delta_b_a2 ≤ 2 Å²` blocking | **withdrawn, inconclusive** — it survived the split and tiering corrections, then failed once the restored dose arm was included: the highest value on a negligible cell is 27x the lowest on an unacceptable one, and the instrument rejects its own fit in all 90 dose cells (§6.1, §10.1) |
| §5 zero floor, §7 real-pipeline response, §8 layer-1 curves | **unchanged** — none depends on the split or the tiering |
| §6 harm bridge "reference-measured Δ*B* tracks absolute harm" | **scope narrowed** — the measurement stands for applied attenuation (ratio 1.00) and motion faults (0.9–1.1), and is now shown **not** to extend to dose-weighting faults, where it is anti-correlated with harm (§6.1) |

### 0.2 The hold-out is no longer blind, and that is not repairable

The corrected split recovers 120 movie-axis and 426 severity-axis hold-out
cells. But the published §8 and §9 already tabulated hold-out severities and
hold-out-movie fault responses **before** §10's recommendation was written.
Re-partitioning the same data now cannot restore blindness.

The corrected hold-out figures below are therefore a **consistency check, not an
independent validation**, and are labelled as such throughout. A genuinely blind
hold-out would need the twelve reserved movies
(`00022 00024 00026 00028 00030 00035 00036 00037 00039 00040 00043 00045`),
which remain untouched. No historical split provenance is claimed that the
commit history does not support.

### 0.3 A further limitation the corrected split exposes

The hold-out movies carry **no unacceptable-tier cells at all** — 114 negligible
and 6 marginal out of 120. Layer 3 only ever ran harmless variations plus dose
and gain faults on them, and none of those reaches the harm boundary. So the
movie axis can test false alarms and nothing else: **detection has never been
validated on an unseen micrograph**, before or after this correction. Detection
evidence rests entirely on the severity axis and on synthetic Layer-2 cells.


---

## 1. What was asked, and what was measured

Gate 2's six numerical limits were written down as provisional values. None was
derived from a measurement of how much motion-correction signal a violation
costs. This work injected faults of known physical magnitude into motion
correction, measured how each candidate diagnostic responds, and independently
measured how much signal each fault actually costs.

The five results that matter:

1. **The harmless-variation floor on this CPU build is exactly zero.** Across
   176 identical-configuration and thread-varied cells on twelve movies --
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

4. **A four-parameter decomposition separates harm from harmless for the fault
   classes whose signature is an envelope — and only those.** Splitting a
   test-versus-reference difference into scale, translation, envelope loss
   (Δ*B*, in Å²) and an incoherent residual gives a measure of envelope loss
   that tracks absolute signal loss with a ratio of 1.00 for applied
   attenuation and 0.9--1.1 for motion faults, independent of signal-to-noise
   ratio where relative RMSE varies by 1.9x over the same range.

5. **It does not extend to dose-weighting faults, and that is why this
   calibration proposes no numerical limit.** On the Layer-2 dose arm added in
   this review round (§6.1) the reference-measured estimate is *anti-correlated*
   with the absolute harm: at double dose the true envelope loss is +19 to
   +25 Å² — about 50 % of amplitude at 3 Å — and the estimate reads 0.0004 to
   0.045 Å². The instrument rejects its own Gaussian fit in all 90 dose cells; the
   published analysis consumed the number regardless.

An honest summary of the consequence: **this calibration does not establish a
blocking numerical acceptance limit** (§10), and all three previously proposed
ones are withdrawn. What it does establish is that the current limit cannot be
repaired by changing its value: the recorded CUDA relative-RMSE range of
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
| GPU host | **not used.** No GPU run was launched by this work, in either round. |

Review round (28 September 2026), same binary `d88a6c02…` and same input hashes:

| Item | Value |
|:---|:---|
| Host / cpuset | `cpu64`, `taskset -c 32-63` (exactly NUMA node 1) |
| Concurrency | 3 workers, cap 16 |
| Payload NUMA residency | heap 102.5 MiB entirely on node 1; 12.6 MiB of shared library text on node 0 (`numastat -p`, cross-checked against `/proc/<pid>/numa_maps`: 117 MiB vs 116.8 MiB on node 1) |
| Peak RSS per worker | 158 MiB |
| Load at launch / during | 4.6 / 8.6–20.2 |
| Memory | 226 GiB total, 215 GiB available |
| Contention | colleagues' `ctffind` processes are unpinned (affinity 0-63) and one occupied cpu32 during the run. They were **not** re-pinned or disturbed. This work measures correctness, not wall time, so contention affects elapsed time only. |
| Scope | analysis and data contracts only; no engine run, no dataset download, no performance measurement |

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

247 runs on twelve movies (six selection, six hold-out), all exit status 0. Of
those, 176 cells are harmless variations and should read zero.

| Harmless variation | cells | largest value on **any** diagnostic |
|:---|---:|---:|
| `--j 2`, `--j 4`, `--j 8` vs `--j 1` | 36 | 0 (bit-identical) |
| `OMP_PROC_BIND` close / spread at `--j 4` | 24 | 0 (bit-identical) |
| five identical `--j 1` repeats | 48 | 0 (bit-identical) |
| five identical `--j 4` repeats | 48 | 0 (bit-identical) |
| gain reference rewritten unchanged through this work's MRC writer | 6 | 0 (bit-identical) |
| movie re-encoded TIFF → MRC, row order matched | 2 | 0 (bit-identical) |
| each reference against itself | 12 | 0 (bit-identical) |
| **all harmless cells** | **176** | **1.478e-15** |

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


### 6.1 The dose arm, and where the harm bridge stops

The published matrix never generated the Layer-2 dose cells the frozen
`FAULT_LAYERS` declares reachable there
([r4119255261](https://github.com/KingAlejandro/MotionCorr-standalone/pull/64#discussion_r4119255261)).
The arm is now run, against a **correctly dose-weighted ideal** so the
measurement is "wrong dose versus right dose" rather than "dose weighting
versus none". 90 cells, 5 trials x 3 noise levels x 6 dose scales.

It changes the report's central conclusion.

| dose scale | gate-visible Δ*B* | absolute harm Δ*B* | Gaussian fit accepted | relRMSE |
|---:|---:|---:|:---:|---:|
| 0.50 | **+3.20** | **−15.80** | 0 of 15 | 2.88e-1 |
| 0.80 | +0.71 | −6.40 | 0 of 15 | 9.73e-2 |
| 0.95 | +0.14 | −1.57 | 0 of 15 | 2.25e-2 |
| 1.05 | −0.12 | +1.54 | 0 of 15 | 2.15e-2 |
| 1.25 | −0.44 | +7.43 | 0 of 15 | 9.83e-2 |
| 2.00 | **−0.95** | **+24.13** | 0 of 15 | 3.00e-1 |

(medians at noise 10; the other two noise levels agree, full data in
`data/layer2_ns*.json`.)

**The gate-visible envelope estimate is anti-correlated with the absolute harm
across the whole dose arm.** At double dose the absolute envelope loss is
+19 to +25 Å² — roughly 50 % of amplitude at 3 Å — and the reference-measured
estimate reads **0.0004 to 0.045 Å²**. At half dose the sign flips: the estimate
reads +2.8 to +3.3 Å² of "loss" where the true spectral change is *less*
attenuation, not more.

The instrument had already flagged this and the analysis ignored it. A
dose-weighting difference is not a Gaussian in k², so
`spectral_transfer_decomposition` rejects the B-factor fit — `envelope_used` is
false in **all 90** dose cells, with gate-side R² from 0.0000 to 0.8361 — and the published
analysis consumed `std_delta_b_a2` anyway. `analyze.envelope_measurable` now
makes that visible; the cells are kept rather than excluded, because dropping
them would restore the diagnostic's separation by deleting the evidence against
it.

Why the absolute-harm number is still trustworthy here while the gate-side one
is not: `harm_delta_b_a2` is a *difference* of two truth-side fits, so the
common signal-to-noise roll-off cancels and only the incremental envelope
change survives. That it works is checkable on the X5 arm, where the applied
value is known: 1, 2, 5, 10, 25 and 50 Å² are recovered as 1.004, 2.008, 5.019,
10.038, 25.095 and 50.190 despite individual truth-side R² as low as 0.0003.
The direction is also what the weighting algebra predicts, checked
independently of the simulation. Normalised critical-exposure weights
concentrate on early frames as dose rises, so the coherent signal transfer
Σ𝑤 falls. Evaluated directly from `dose_weight_map` at 3 Å, relative to the
correct dose:

| dose scale | 0.50 | 0.80 | 1.25 | 2.00 |
|:---|---:|---:|---:|---:|
| Σ𝑤 at 3 Å, relative to correct dose | 1.280 | 1.098 | 0.902 | **0.719** |

A 0.719 amplitude ratio at 3 Å is an equivalent Δ*B* of about 12 Å², against a
fitted absolute harm of +24 Å². Same sign, same order; they do not agree
closely because the fit is a slope over 20–3 Å and the underlying change is not
Gaussian — which is the point of this subsection. The direction is solid; the
magnitude should be read as "tens of Å²", not as a calibrated value.

**Scope of the §6 harm bridge, restated.** Reference-measured Δ*B* tracks
absolute harm for the faults whose spectral signature *is* an envelope —
applied attenuation (ratio 1.00), random jitter, systematic drift and local
deformation (0.9–1.1). It does **not** extend to dose-weighting faults. The
published report did not state that limit because the arm that demonstrates it
was missing.


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

## 9. Hold-out validation — corrected, and no longer blind

**The published version of this section drew on a broken split** and is
superseded; see §0.1. The split is now derived from the frozen prespecification
on two independent axes (`analyze.cell_axes`).

| Bucket | Cells | Meaning |
|:---|---:|:---|
| joint selection | 619 | selection on every axis that applies; thresholds are searched here only |
| joint hold-out | 441 | hold-out on every axis that applies |
| mixed | 144 | hold-out on one axis, selection on the other; used for **neither** |
| movie-axis hold-out | 120 | unseen micrographs, any severity |
| severity-axis hold-out | 471 | unseen perturbation strengths, any movie |

Two results survive the correction unchanged, because neither depends on the
split:

**The zero floor holds on unseen movies.** All 114 hold-out-movie harmless cells
are bit-identical; the largest value on any diagnostic is `1.195e-15`, the
estimator's own floor.

**The fault response reproduces across movies.** Dose responses agree between
the selection and hold-out movie sets to better than 1.5 %; gain responses, which
are alignment-mediated and therefore chaotic, agree only to within a factor of
about 4 on Δ*B*. Table unchanged from the published version.

Two things this section can **no longer** claim:

1. **It is not a blind validation.** §8 and §9 tabulated hold-out severities and
   hold-out-movie responses before §10 was written. Re-partitioning the same
   data cannot restore blindness (§0.2). A blind hold-out needs the twelve
   reserved movies, which remain untouched (§15.2).
2. **It contains no detection evidence.** The hold-out movies carry 114
   negligible and 6 marginal cells and **zero** unacceptable ones, because
   Layer 3 only ran harmless variations plus dose and gain faults on them
   (§0.3). The movie axis can measure false alarms and nothing else.

---

## 10. Recommendation — withdrawn; the calibration is inconclusive for a numerical limit

**Nothing in this section has been applied.** The `0.001` limit remains in
force, `tools/compare_motioncorr.py` is untouched, and no recorded result is
reclassified.

**Revised 28 September 2026.** The published §10 proposed three blocking
numerical checks. After the four confirmed review findings, **all three are
withdrawn**. This calibration does not establish a blocking numerical
acceptance limit. Issue #60 states that an inconclusive result is allowed; this
is one.

### 10.1 Why each was withdrawn

| Published proposal | Disposition | Reason |
|:---|:---|:---|
| `std_delta_b_a2 ≤ 2 Å²` blocking | **withdrawn, inconclusive** | the prespecified dose arm that was missing from the published analysis is the one it fails on. Including it, the highest value on a negligible cell (3.296) is **27x larger** than the lowest on an unacceptable one (0.121): separation ratio 0.037, no value of the limit works at the declared 5 Å² boundary. §6.1. At a 10 Å² boundary it does separate and the frozen rule rates it **warning**, not blocking — §10.4.1. |
| `std_shift_px ≤ 0.05 px` blocking | **withdrawn, inconclusive** | its entire positive class was the accounted-for translation, which the frozen `FAULT_CLASS` labels benign. With that corrected the class is empty. Under the alternative reading of the clause it separates only at exactly 0.1 px, the clause value itself — a tautology, not a measurement. §10.2. |
| `std_scale_dev ≤ 0.01` blocking (already demoted to warning pre-review) | **withdrawn, inconclusive** | its positive class was the uniform gain error, which the prespecification's own clause excludes. The new C2 control supplies the frame-dependent error the clause actually names, and shows the diagnostic **cannot see it**. §10.3. |
| exact equality, same-platform CPU regression | **retained** | the one blocking check with measured support, and it needs no calibration: 176 harmless cells over twelve movies are bit-identical. §5. |

Every other diagnostic remains a **warning / attribution** measurement, as
before: report the value, do not fail on it. Their value is demonstrated and
unchanged — `std_shift_px` explains 99.8 % of a relative RMSE of 1.399 as a
rigid translation (§7.2), `std_scale_dev` recovers an injected uniform gain
error exactly, `eps_incoherent` separates incoherent damage from envelope loss.
None of that requires a threshold.

### 10.2 The translation clause is not decidable from this data

The frozen prespecification contradicts itself and this review does not resolve
it by choosing the reading that makes a gate pass. Both are carried in
`analyze.GEOMETRY_READINGS` and every result is reported under each.

* **benign** — `FAULT_CLASS["X1_translation_px"] = "benign_but_alarming"`, and
  the design record's consequence table gives a translation's cost as "none:
  particle coordinates move with the micrograph". The geometry class is empty.
* **harmful** — the harm tier declares a translation "not recorded in the STAR
  metadata" unacceptable, and in a gate's real use case, two backends on the
  *same* input, an output offset with unchanged metadata is exactly that.

| Reading | negligible | geometry positives | `std_shift_px` max negligible | min unacceptable | band |
|:---|---:|---:|---:|---:|---:|
| benign | 727 | 0 | — | — | no positive class |
| harmful | 624 | 112 | 0.1 | 0.1 | **1.0 (tautological)** |

Under neither reading is a threshold earned. Deciding whether a cross-backend
origin offset is a signal-loss question or a workflow-integration question is a
scientific call, referred to #58. The measurement that *would* settle the gate
use case is a composite one — image translation compared against the
STAR-recorded shift difference on identical inputs — which is not
`std_shift_px` alone and is not proposed here.

### 10.3 C2: the scale diagnostic is blind to the fault its clause names

A post-hoc control, declared outside the frozen matrix and used to set no
threshold. Frame *f* is scaled by `1 + ε·(f/(N−1) − 0.5)`: zero-mean across
frames, so the uniform component is unchanged by construction and only the
frame weighting is wrong — the "frame-dependent scale error" the
prespecification's 1 % clause names.

| ε | `std_scale_dev` | gate Δ*B* | absolute harm Δ*B* | relRMSE | `eps_incoherent` |
|---:|---:|---:|---:|---:|---:|
| 0.01 | 3.3e-6 | −0.000 | +0.001 | 2.70e-3 | 2.70e-3 |
| 0.05 | 1.7e-5 | −0.002 | +0.006 | 1.35e-2 | 1.35e-2 |
| 0.20 | 6.6e-5 | −0.010 | +0.025 | 5.41e-2 | 5.41e-2 |
| 0.50 | 1.7e-4 | −0.025 | +0.057 | 1.35e-1 | 1.35e-1 |

(medians at noise 10; 60 cells total across three noise levels.)

At a **50 % frame-dependent ramp** `std_scale_dev` reads `1.7e-4` — three
orders of magnitude below the 1 % clause it is supposed to enforce, and
indistinguishable from its value on an unperturbed pair. The diagnostic named
for scale cannot see the scale error the specification declares harmful.

The control also shows the fault is mild by the declared harm currency: at
ε = 0.5 the absolute envelope change is +0.057 Å², far inside the negligible
tier. So the clause has no positive example that is both *declared* harmful and
*measurably* harmful, and is withdrawn rather than reinterpreted.

### 10.4 Corrected separation and hold-out

Selection 619 cells, joint hold-out 441, mixed 144 (hold-out on one axis only,
used for neither), movie-axis hold-out 120, severity-axis hold-out 471.

| Diagnostic | max on negligible | min on unacceptable it owns | band | verdict |
|:---|---:|---:|---:|:---|
| `std_delta_b_a2` | 3.296 | 0.1207 | **0.037** | no separating value |
| `image_relative_rmse` | 4.885 | 0.0605 | 0.012 | no separating value |
| `std_eps_incoherent` | 4.884 | 1.3e-4 | 2.8e-5 | no separating value |
| `std_shift_px` | — | — | — | no positive class (benign reading) |
| `std_scale_dev` | — | — | — | no positive class |

For `std_delta_b_a2` the analysis also reports what the separation would be if
the **353 of 619** selection-bucket cells whose Gaussian fit the instrument
rejected were dropped (757 of 1279 over the whole corpus): max negligible 0.713,
min unacceptable 5.004, band **7.02**. That is quoted only to show how much of
the published result depended on silently consuming rejected fits. It is **not**
the recommended reading: the excluded set covers 51 of the 63 dose cells in the
selection bucket and every harmless cell, and a gate cannot condition on whether
its own fit converged.

**These hold-out figures are a consistency check, not a blind validation** (§0.2),
and the hold-out movies contain no unacceptable cells at all, so detection has
never been tested on an unseen micrograph (§0.3).

### 10.4.1 Sensitivity to the harm boundary, and three properties of the negative result

The published §3.3 promised every conclusion re-reported at Δ*B* boundaries of
2, 5 and 10 Å². The first revision of this section did not do that and asserted
boundary-independence instead. It is not independent, and the omitted boundary
is the one where the result is least negative. Corrected, for
`std_delta_b_a2` on the joint-selection bucket:

| Harm boundary | Separable | θ | band | hold-out FP | hold-out FN | frozen rule's verdict |
|:---|:---:|---:|---:|---:|---:|:---|
| 2 Å² | no | — | 2.7e-16 | — | — | not recommended |
| **5 Å² (declared)** | **no** | — | **0.037** | — | — | **not recommended** |
| 10 Å² | **yes** | 5.72 | 3.01 | 0/228 (0.000) | 15/134 (**0.112**) | **warning** |

At the loosest of the three boundaries the diagnostic does separate, and the
frozen decision rule rates it **warning** — not blocking, because 11.2 % of
unacceptable hold-out cells slip under the threshold. So the accurate statement
is narrower than "inconclusive at every boundary":

> **The withdrawal of the *blocking* recommendation holds at all three declared
> boundaries. The claim that the outcome is boundary-independent does not: at
> 10 Å² the diagnostic earns a warning-tier limit.**

Since 10 Å² corresponds to 24 % amplitude loss at 3 Å, a reader who considers
that an acceptable harm ceiling should read this result as "a warning-tier
limit near 5.7 Å² is defensible", not as "nothing works". This report does not
recommend that boundary — 5 Å² was the declared one — but hiding the result
would have made the negative conclusion look stronger than the data supports.

Three further properties of the negative result, none of which were visible in
the first revision:

**1. Two cells set the headline bands, and both have *negative* measured harm.**
The declared currency counts only envelope *loss*, so a cell that retained
*more* high-frequency amplitude than its reference scores zero harm and lands in
the negligible tier. The cells that cap the negligible side are exactly those:

| Diagnostic | max-negligible cell | value | raw harm before clamping |
|:---|:---|---:|---:|
| `std_delta_b_a2` | X6 dose ρ=0.5 | 3.296 | **−16.0 Å²** |
| `image_relative_rmse` | X7 hot pixels n=10⁴ | 4.885 | **−0.87 Å²** |

So "no diagnostic separates" is partly a statement about the harm model and not
only about the diagnostics: under-dose-weighting and incoherent additive damage
are both real faults that this currency prices at zero. §11 already records that
Δ*B* cannot price incoherent damage; the dose arm shows it also cannot price a
re-weighting of frames in the direction that *retains* amplitude.

**2. 301 cells are tiered from a fit the instrument rejected.** Layers 1 and 3
have no noiseless object, so `harm_of` falls back to the gate-side
`std_delta_b_a2` — the quantity `envelope_measurable` may declare unusable. 78
Layer-1 and 223 Layer-3 cells get their ground-truth label that way. The
counterfactual above removes rejected fits from the *diagnostic* side only, so
those cells keep a label derived from a rejected fit. `analyze.
harm_tiered_from_rejected_fit` exposes this; it is not repaired here, because
repairing it means measuring absolute harm on real micrographs, which requires a
noiseless object that does not exist for them.

**3. Layer 1 can never appear in the joint hold-out, by construction.** Layer 1
runs only on selection movies, so every Layer-1 hold-out-severity cell is
`{movie: selection, severity: hold-out}` → mixed → used for neither bucket:
132 selection, 120 mixed, **0 hold-out**. The corrected split traded one
systematic absence (Layer 3, which the leak excluded) for another (Layer 1,
which the strict two-axis rule excludes). The `severity_axis_holdout` view (471
cells) is what recovers Layer-1 generalisation evidence, and it is reported
alongside the joint view for that reason.


### 10.5 What the calibration does still establish

Withdrawing the limits does not withdraw the measurements. Unchanged by this
review round:

* the harmless-variation floor is exactly zero, so exact equality is an
  achievable same-platform CPU regression bar (§5);
* relative RMSE 0.001 corresponds to ≈ 0.017 Å² of envelope loss, 0.05 % of
  amplitude at 3 Å (§8), and its negligible and unacceptable populations
  overlap by a factor of 80, so **no value of that limit separates harm from
  harmless** — the strongest surviving statement, and the one #58 needs;
* a 1 ppm input perturbation already doubles the limit, and the response
  saturates (§7.1);
* accounted translations and uniform gain errors produce the largest relative
  RMSE values in the whole matrix while costing essentially nothing (§7.2) —
  now *strengthened*, because they are correctly tiered benign rather than
  counted as harmful positives;
* the decomposition attributes those differences correctly, which is useful
  without being a gate.

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
   on Linux/GCC 13.3/FFTW 3.3.10, over 176 harmless cells on twelve movies. A
   macOS or
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

* **#58 (gate semantics).** PR #62 is the gate-contract work and owns
  `tools/compare_motioncorr.py` and `docs/reference_gates.md`; PR #64 touches
  neither and the two PRs have zero files in common. This report supplies the
  measurement #58 needs: the
  `0.001` relative-RMSE limit has no measured relationship to lost signal, and
  the "non-associative parallel reduction" justification is not supported on
  this CPU build. The threshold proposal in section 10 is offered to #58 as
  evidence, not as a change. `docs/reference_gates.md` was not edited.
* **#59 (known motion and local displacement field).** The displacement-field
  evaluator here reproduces `Micrograph::getShiftAt` and reports constant offset
  separately from frame-to-frame change, in px and Å, as #59 requires. It is
  used for calibration only; **no displacement-field gate is proposed here**, and
  none of #59's files were touched -- PR #64 and PR #63 have zero files in
  common.

  #59's PR #63 appeared while this work was running. Its `tools/motion_field.py`
  and this report's `tools/calibration/mrcio.displacement_field` were written
  independently from the same source, and they agree: evaluated on the real
  `00021` motion model over 600 grid points (24 frames x a 5 x 5 detector grid,
  fields up to 13.94 px), the largest disagreement is **3.6e-15 px**. Two
  independent readings of the same convention landing on the same numbers is a
  useful cross-check on both.

  When #63 merges, this module should be replaced by an import of
  `tools/motion_field.py`, and layer 2's `make_object` and `true_trajectory`
  should be replaced by #59's fixtures.
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
| `tools/calibration/verify_report_numbers.py` | re-derives every number in this report from the data; exits non-zero on drift |
| `docs/calibration/data/*.json` | every measurement behind every number above |

---

## 15. Evidence deliberately left UNRUN, with prepared commands

This review round was scoped to analysis and data contracts. Nothing below was
executed, and nothing above depends on it.

**No GPU run was required or performed for any of the four findings.** All four
are defects in the CPU-only calibration's analysis layer, reproducible and
verifiable from the committed JSON. Dedicated SCARF GPU capacity was available
for this round and was deliberately not used, because no bounded GPU control
would change any conclusion here. `4GPUs` was not touched. Colleagues' GPU3 and
running jobs were left alone.

### 15.1 UNRUN — decompose the native CUDA outputs (still the highest-value next step)

Needs no GPU compute, only read access to outputs already on disk from the #66
experimental milestone. It converts the recorded relative-RMSE range into an
amplitude loss in percent at a stated resolution.

```sh
python3 tools/calibration/decompose_pair.py \
  --pair "cuda_00021=<cpu_ref>/20170629_00021_frameImage.mrc:<cuda>/20170629_00021_frameImage.mrc" \
  --ref-star  "cuda_00021=<cpu_ref>/20170629_00021_frameImage.star" \
  --test-star "cuda_00021=<cuda>/20170629_00021_frameImage.star" \
  --out docs/calibration/data/cuda_decomposition.json
```

Read-out rule, fixed in advance: Δ*B* below 1 Å² with `eps_incoherent` at the
~1e-2 saturation scale means arithmetic non-identity; Δ*B* of several Å² means
real envelope loss. Owner: #36 / #66.

### 15.2 UNRUN — a genuinely blind hold-out

The twelve reserved movies are untouched and remain the only way to obtain a
blind validation (§0.2), and the only way to obtain *any* detection evidence on
unseen micrographs (§0.3). Requires injecting faults that reach the harm
boundary, which is not reachable through the CLI for the motion faults (§11.2).

```sh
# CPU-only, cpu64, cpuset 32-63, <=16 workers
python3 tools/calibration/layer3_pipeline.py --emit-manifest work/manifest_reserved.json \
  --movies reserved   # requires a "reserved" choice to be added to --movies
taskset -c 32-63 python3 tools/calibration/layer3_pipeline.py --execute \
  work/manifest_reserved.json --binary $PWD/build/motioncorr \
  --tutorial $PWD/work/tutorial --stars $PWD/work/star \
  --results $PWD/work/results --workers 16
```

### 15.3 UNRUN — scientific (map-level) confirmation of the harm boundary

Δ*B* > 5 Å² is a declared judgement, not a measured reconstruction outcome
(§11.4). Converting it into an FSC or B-factor statement is #61's deliverable
and is not duplicated here.

