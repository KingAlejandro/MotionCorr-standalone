# Scientific non-inferiority of CPU, native CUDA and all-FFTW hybrid motion correction

Issue [#61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61).
Preregistered protocol: [`PROTOCOL.md`](PROTOCOL.md), committed at `0693c28` **before** any
endpoint value was computed for any arm. Architecture note:
[`agents/designs/issue_61_scientific_noninferiority.md`](../../agents/designs/issue_61_scientific_noninferiority.md).
Exact commands: [`scripts/`](scripts/). Machine-readable results: [`results/`](results/).

No source file, comparator or numerical threshold was changed by this work.

---

## 1. What was asked and what was measured

Gate 2 asks whether an accelerated backend reproduces the CPU reference image. This work asks
whether it preserves *recoverable cryo-EM signal*. The two questions are not interchangeable, and
this report demonstrates that empirically rather than asserting it (section 6).

Three motion-correction arms were compared, all from one source commit on one input set with one
set of movie options, and all **consumed from Issue #36's completed 24-movie run rather than
re-run**:

| Arm | What it is | Where it ran |
| --- | --- | --- |
| `cpu` | fixed standalone CPU, the oracle | `cpu64`, `CUDA=OFF`, `OMP_NUM_THREADS=1`, `--j 1` |
| `default` | native CUDA global + local alignment | `4GPUs` A100 GPU 0 |
| `allfftw` | opt-in all-FFTW hybrid (`MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1`) | `4GPUs` A100 GPU 0 |

Source `5407373be31a6fe5f79a8cc5709be00723921b19`, tree checksum
`5db2b1ef3496442b300034a41def89ecffabaeaf1d41c9595ac041de01726a88` (identical on both hosts).
Movie options, identical in every arm and driven by a one-row STAR per movie:

```
--use_own --j 1 --seed 1 --dose_weighting --dose_per_frame 1.277
--patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc
```

All 72 corrected micrographs were verified present with identical geometry (3710 x 3838, MRC
mode 2, 0.885 A/pixel) and no accelerated arm bit-identical to CPU. Pixel payload (bytes 1024+)
and core header (bytes 0-223) are digested separately in
[`results/arm_provenance.json`](results/arm_provenance.json), because the MRC label region carries
a `strftime` timestamp and whole-file hashing gives false mismatches.

### The three instrument controls

The protocol requires that each endpoint be shown to observe what it asserts. Three controls were
built by transforming the `cpu` arm's micrographs:

| Control | Construction | What it tests |
| --- | --- | --- |
| `ctrl_noise_f005` | + independent Gaussian noise, variance `0.05 x var(micrograph)` | can the endpoint see a known 5% effective-data loss? |
| `ctrl_noise_f020` | same at `f = 0.20` | response at a clearly unacceptable loss |
| `ctrl_envelope_b20` | Fourier multiplication by `exp(-20 s^2 / 4)`, identical for every micrograph | does a large *image* change necessarily mean signal loss? |

### Analysis sets

Only one movie collection exists on the project hosts, so there is no independent second
collection (section 7). The held-out structure is within the collection: `00021` and `00046` are
**development** data because they carried every Issue #36 diagnostic and all hybrid development;
the other **22 movies are held out** and carry every primary result. All-24 values are reported
alongside as a secondary figure.

---

## 2. Stage A — CTF fit and high-frequency screen

CTFFIND 4.1 on each arm's corrected micrograph, tutorial search parameters (box 512, ResMin 30 A,
ResMax 5 A, dFMin 5000 A, dFMax 50000 A, FStep 500 A, dAst 100 A, fast search), 0.885 A/pixel,
200 kV, Cs 1.4 mm, amplitude contrast 0.1. Paired BCa bootstrap over movies, 10,000 resamples,
seed 61. Held-out set, n = 22.

| Arm | A1 CtfMaxResolution, A | one-sided 95% bound | margin | A2 mean defocus, A | 90% CI | margin | A3 CtfFoM, relative | one-sided 95% bound | margin | Verdicts |
| --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: | --- |
| `default` | -0.0188 | +0.0017 | +0.10 | -2.63 | [-10.5, -0.0] | +/-45 | +0.42% | -0.00% | -5% | **PASS / PASS / PASS** |
| `allfftw` | -0.0226 | +0.0020 | +0.10 | -2.06 | [-9.4, +0.5] | +/-45 | +0.44% | +0.00% | -5% | **PASS / PASS / PASS** |

Differences are negative, i.e. both accelerated arms fit marginally *better* than CPU, by about
0.02 A of CTF max resolution and 2-3 A of defocus. Neither is claimed as an improvement: the
design has no power for superiority and no superiority margin was set. The all-24 values agree
with the held-out values to within 0.004 A and 0.2 A respectively.

Absolute values are in the expected regime. Across the 24 micrographs, mean CtfMaxResolution is
3.519 A (`cpu`), 3.500 A (`default`), 3.496 A (`allfftw`), against 3.336 A for the tutorial's own
grouped-power-spectrum route — slightly worse, as expected when fitting dose-weighted sums
(section 7.3).

### What the controls say about Stage A's sensitivity

This is the part that stops three green rows from meaning nothing.

| Control | A1 CtfMaxResolution, A | A3 CtfFoM, relative (bound) | A3 verdict |
| --- | ---: | ---: | --- |
| `ctrl_noise_f005` (known 5% loss) | -0.017 | **-3.49%** (-4.43%) | PASS |
| `ctrl_noise_f020` (known 20% loss) | -0.019 | **-12.67%** (-13.74%) | **FAIL** |
| `ctrl_envelope_b20` (81% of 3-2 A power removed) | -0.009 | +3.71% | PASS |

Two things follow, and both limit Stage A rather than support it:

1. **`CtfMaxResolution` is a weak instrument here.** Adding noise at 20% of micrograph variance —
   a gross, clearly unacceptable degradation — moved it by *-0.019 A*, i.e. not at all, and in the
   wrong direction. On dose-weighted micrographs this endpoint cannot detect a degradation far
   larger than anything the backends produce. Its PASS therefore carries very little information.
2. **`CtfFigureOfMerit` does respond, monotonically and at the right order** (-3.5% at f = 0.05,
   -12.7% at f = 0.20), but the prespecified -5% margin is *not tight enough* to flag the 5%
   control, which passes at -4.43%. Stage A's A3 test can detect roughly a 10% effective-data loss
   and not a 5% one.

Stage A is therefore what the protocol called it — an initial screen. It is Stage B that carries
the claim.

### A4 — rotationally averaged power ratio (descriptive, no margin)

Mean over the 22 held-out movies of band power relative to CPU:

| Arm | 50-20 A | 20-10 A | 10-6 A | 6-4 A | 4-3 A | 3-2 A |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `default` | 1.000003 | 1.000003 | 1.000007 | 1.000018 | 1.000033 | 1.000060 |
| `allfftw` | 1.000001 | 1.000000 | 1.000000 | 0.999996 | 0.999994 | 0.999990 |
| `ctrl_noise_f005` | 1.0118 | 1.0310 | 1.0387 | 1.0410 | 1.0445 | 1.0521 |
| `ctrl_noise_f020` | 1.0468 | 1.1243 | 1.1546 | 1.1645 | 1.1779 | 1.2087 |
| `ctrl_envelope_b20` | 0.9885 | 0.9452 | 0.8364 | 0.6481 | 0.4314 | 0.1895 |

Both backends agree with CPU to within 6 parts in 100,000 even in the 3-2 A band, against controls
that move the same quantity by 5-81%.

---

## 3. Stage B — matched-orientation reconstruction (the primary result)

Every downstream input is imported from this dataset's own RELION 5.0 tutorial precalculated
project and is **byte-identical across arms**: 4452 particles, coordinates, per-particle
orientations and origins, CTF parameters, `rlnRandomSubset` half-set membership, box 360 scaled
to 256 (1.244531 A/pixel), D2 symmetry, `MaskCreate/job020/mask.mrc`, `mtf_k2_200kV.star`.
Nothing is re-estimated; `--float16` is deliberately not used, so extraction does not quantise
away the differences under test. Only the micrograph behind each particle differs.

Held-out set: 4095 particles from 22 movies, the same 4095 in every arm.

### Point estimates

| Arm | held-out 22: `d143`, A | held-out 22: auto-B, A^2 | all 24: `d143`, A | all 24: auto-B, A^2 |
| --- | ---: | ---: | ---: | ---: |
| `cpu` | 3.124 | -28.21 | 3.218 | -32.29 |
| `default` | 3.124 | -28.22 | 3.218 | -32.25 |
| `allfftw` | 3.124 | -28.22 | 3.218 | -32.30 |
| `ctrl_noise_f005` | 3.154 | -30.89 | 3.218 | -31.93 |
| `ctrl_noise_f020` | 3.154 | -32.23 | 3.218 | -32.03 |
| `ctrl_envelope_b20` | 3.124 | -48.67 | 3.218 | -52.60 |

The three real arms land on the identical Fourier shell in both sets.

### Non-inferiority verdicts, delete-one-movie jackknife over the 22 held-out movies

`rho` is the median over the 63 qualifying shells (8.0-3.0 A, `FSC_cpu >= 0.143`) of
`SSNR_arm(s)/SSNR_cpu(s)`, i.e. the fraction of effective data retained.

| Arm | Endpoint | Point | one-sided 95% bound | Margin | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `default` | **B1 `rho` (primary)** | 0.999959 | **0.99969** | >= 0.95 | **PASS** |
| `default` | B1 `rho`, unmasked FSC | 0.999931 | 0.99939 | >= 0.95 | PASS |
| `default` | B2 `d143` delta, A | 0.0000 | +0.0508 | <= +0.05 | INCONCLUSIVE |
| `default` | B3 auto-B delta, A^2 | -0.007 | -1.70 | >= -10 | PASS |
| `allfftw` | **B1 `rho` (primary)** | 0.999981 | **0.99992** | >= 0.95 | **PASS** |
| `allfftw` | B1 `rho`, unmasked FSC | 1.000000 | 0.99988 | >= 0.95 | PASS |
| `allfftw` | B2 `d143` delta, A | 0.0000 | +0.0000 | <= +0.05 | PASS |
| `allfftw` | B3 auto-B delta, A^2 | -0.014 | -0.13 | >= -10 | PASS |

**The primary endpoint passes for both accelerated backends, with an enormous margin to spare.**
The achieved jackknife precision is `SE(rho)` = 1.6e-4 for `default` and 3.8e-5 for `allfftw`, so
the data support a far stronger statement than the 0.95 margin: at 95% confidence the native CUDA
backend retains at least **99.97%** and the all-FFTW hybrid at least **99.99%** of the effective
data that the CPU reference recovers, on this set. On a Rosenthal-Henderson basis with B = 100 A^2
at 3.15 A, those bounds correspond to at most **1e-4 A** and **2.5e-5 A** of equivalent resolution
loss. This stronger bound is a post-hoc statement of achieved precision; the prespecified margin
was and remains 0.95.

### Why `default` B2 is INCONCLUSIVE, and why it is not evidence of inferiority

The `d143` delta is exactly **0.000 A** on the held-out set and on all 24. Of the 22 jackknife
replicates, 21 give a delta of exactly 0.000 and one gives **-0.031 A** — a single Fourier shell,
in `default`'s *favour*. The delete-one jackknife multiplies the replicate spread by `n - 1 = 21`,
so one discrete shell flip inflates `SE` to 0.0295 and pushes the upper bound to 0.0508, three
thousandths of an angstrom past the 0.05 margin. This is the quantisation limit the protocol
predicted in advance: one shell is 0.031 A at box 256 and 1.244531 A/pixel, while the 5% effective
loss that B1 targets is 0.016 A, below a shell. The verdict is reported as the rule produces it,
INCONCLUSIVE, and B2 is a coarse secondary for exactly this reason. `allfftw` has zero spread
across all 22 replicates and passes.

### Validity of the primary endpoint — the precondition the protocol set

| Control | `rho` (primary) | one-sided 95% bound | distance from 1.0 |
| --- | ---: | ---: | ---: |
| `ctrl_noise_f005` (known ~5% loss) | **0.9666** | 0.9567 | **5.8 SE** |
| `ctrl_noise_f020` (known ~20% loss) | **0.8775** | point estimate only | - |
| `ctrl_envelope_b20` (81% of 3-2 A power removed) | **1.0039** | 1.0021 | +3.7 SE, favourable |

The precondition is met: `rho` resolves the 5% control at 5.8 standard errors and orders the two
noise levels correctly. Measured losses (3.3%, 12.2%) are smaller than the naive `1/(1+f)`
prediction (4.8%, 16.7%) because the added noise is white while the micrograph's variance is
concentrated at low frequency, so the per-shell noise increase in the 8-3 A band is less than `f`.
The direction, ordering and magnitude are right, which is what the precondition requires.

### The specificity control is the point of this issue

`ctrl_envelope_b20` removes **81% of the power in the 3-2 A band** and 35% at 6-4 A. It is, by
any image-domain measure, a far larger change than anything either backend produces. Yet:

- its half-map FSC is unchanged — `rho` = 1.004, `d143` delta = **0.000 A**;
- its auto-sharpening B moves by **-20.5 A^2**, the largest B shift of any arm.

A deterministic envelope applied identically to both half-sets multiplies signal and noise by the
same factor in every shell, so it cannot change FSC, and the sharpening step recovers it. This is
the concrete demonstration, on this data, that **a large corrected-image difference does not imply
a loss of recoverable signal** — and conversely that the B-factor endpoint responds to envelope
shape rather than to information content. It is the empirical form of this issue's premise.

### Held-out 22 beats all 24 — a caution about single-movie claims

The 22 held-out movies reach 3.124 A while all 24 reach 3.218 A, three Fourier shells worse,
despite 357 *more* particles. Adding the two development movies makes the map worse. `00021` has
the worst CTF fit of the 24 (4.87 A in the tutorial reference against a set mean of 3.34 A). Any
claim resting on `00021` or `00046` alone should be treated as a pilot, not a result.

### Verification that the matched design is actually matched

Two checks, because "the arms are identical except for the micrograph" is an assertion that has
to be observable ([`scripts/i61_verify.sh`](scripts/i61_verify.sh)):

| Check | Result |
| --- | --- |
| Extracted particle stacks differ between arms (movie 00022, 42,730,496 bytes each) | six distinct SHA-256 digests — the arms really are different data |
| Coordinates, orientations, origins and `rlnRandomSubset` across the held-out 4095 particles | **byte-identical digest `d54438c50f9b83f8` in all six arms** |
| Held-out particle count | 4095 in all six arms |
| `relion_postprocess` phase-randomisation threshold, held-out set | **16.768418 A in all six arms**, so the solvent-corrected FSCs are directly comparable |

The one exception is in the secondary all-24 set, where `ctrl_noise_f020` randomises from
16.77 A while every other arm randomises from 11.80 A. That affects only that control's
all-24 figure, not any held-out result and not the three real arms.

---

## 4. Stage C — normal auto-refinement workflow

Stage B holds orientations fixed. Stage C lets each arm find its own: `relion_refine --auto_refine
--split_random_halves` from the same starting reference, the same 4095 held-out particles, the same
mask and the same settings as the tutorial's own `Refine3D/job019`, then the same
`relion_postprocess`. Gold-standard half-set refinement requires MPI, so the container's OpenMPI
ran 1 master plus 2 half-set workers at 3 threads each — 7 of the 8 permitted CPUs — across all
four A100s, under the bench lock.

**A first pass had to be discarded and repeated.** RELION's default `--random_seed` is time-derived,
so the three arms were refined under three *different* seeds (1790307166 / 1790307567 / ...). That
confounds the backend with the seed, and the effect is not negligible: rerunning the same `cpu` arm
under an explicit seed moved its resolution by a full Fourier shell. Stage C was therefore rerun
with `--random_seed` fixed and identical across arms, replicated over three seeds so that
seed-driven variation could be separated from any between-arm difference. **The unit of replication
in Stage C is the seed (n = 3), not the movie**, which makes it a deliberately under-powered
secondary analysis.

### Resolution at FSC = 0.143, held-out 22 movies

| Arm | seed 61 | seed 62 | seed 63 | within-arm spread | discarded uncontrolled-seed run |
| --- | ---: | ---: | ---: | ---: | ---: |
| `cpu` | 3.186 | 3.154 | 3.124 | **0.062** | 3.154 |
| `default` | 3.154 | 3.154 | 3.124 | **0.031** | 3.124 |
| `allfftw` | 3.186 | 3.154 | 3.124 | **0.062** | 3.124 |

Paired by seed:

| Arm | C1 `d143` delta per seed, A | mean | upper 95% (n = 3) | margin | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `default` | -0.032, 0.000, 0.000 | -0.0105 | +0.0202 | <= +0.05 | **PASS** |
| `allfftw` | 0.000, 0.000, 0.000 | 0.0000 | +0.0000 | <= +0.05 | **PASS** |

| Arm | C2 auto-B delta per seed, A^2 | mean | lower 95% (n = 3) | margin | Verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `default` | -1.71, +3.85, -2.43 | -0.10 | -5.90 | >= -10 | PASS |
| `allfftw` | -2.38, +10.24, -1.91 | +1.98 | -10.08 | >= -10 | INCONCLUSIVE |

**How to read this.** The within-arm, seed-driven spread in `d143` is up to 0.062 A — two Fourier
shells — which is *larger than any difference between arms*. Stage C therefore cannot resolve
anything below about 0.06 A on this data, and every observed between-arm difference is at or below
its own noise floor. `allfftw` reproduced CPU's resolution exactly at all three seeds. The
`allfftw` C2 verdict is INCONCLUSIVE only because the seed-to-seed B spread (up to 10 A^2 within
a single arm) swamps an n = 3 interval; its mean delta is +1.98 A^2, i.e. favourable. The
auto-sharpening B is not a usable discriminator at this replication level and should not be read
as one.

Wall time 5:31 - 6:54 per refinement, peak RSS 2.84 GB, 15-17 iterations to convergence.

---

## 5. Descriptive covariates — image agreement against downstream signal

Carried from Issue #36's own comparator output on the same 24 movies. **These are covariates, not
endpoints. No verdict here depends on them, no Gate 2 status is asserted, and no threshold is
proposed or changed by this work.**

| Arm | relative image RMSE, held-out 22 | range | Gate 2 status across all 24, per #36's comparator |
| --- | ---: | :---: | --- |
| `default` | median 0.00716 | 0.00503 - 0.00992 | 24 FAIL |
| `allfftw` | median 0.00110 | 0.00046 - 0.00302 | 12 PASS / 12 FAIL |

Two observations that #58 and #60 may find useful:

1. The all-FFTW hybrid's two-movie result (`00021` 0.00062, `00046` 0.00039, both passing) does not
   extend to the full set: across 24 movies its relative RMSE spans 0.00046-0.00302 and half the
   movies exceed 0.001. This is #36's and #58's matter to adjudicate; it is recorded here only
   because those same 24 outputs are this study's input.
2. Across the 22 held-out movies the per-movie relative image RMSE is **not** a consistent
   predictor of the per-movie CTF-fit difference: `r = -0.18` between relative RMSE and
   `|delta CtfMaxResolution|` for `default`, but `r = +0.40` for `allfftw`; for `|delta defocus|`,
   `r = -0.31` and `r = +0.36`. With n = 22 neither is distinguishable from zero and the sign flips
   between arms. Image agreement and downstream fit quality are not interchangeable at the
   per-movie level either.

Meanwhile the same 24 outputs that fail the 0.001 image limit 24/24 (`default`) retain, at 95%
confidence, at least 99.97% of the effective data recoverable by CPU. Both facts are true; they
measure different things. That is the answer to the question this issue posed.

---

## 6. Summary of verdicts

Held-out set of 22 movies. One-sided 95% for non-inferiority, TOST at 90% for the defocus
equivalence test.

| Stage | Endpoint | Margin (fixed in advance) | `default` | `allfftw` |
| --- | --- | --- | --- | --- |
| A | A1 CtfMaxResolution | +0.10 A | PASS | PASS |
| A | A2 mean defocus | +/- 45 A | PASS | PASS |
| A | A3 CtfFigureOfMerit | -5% relative | PASS | PASS |
| A | A4 band power ratio | descriptive | 1.00000-1.00006 | 0.99999-1.00000 |
| **B** | **B1 effective-data fraction `rho`** | **>= 0.95** | **PASS** (>= 0.99969) | **PASS** (>= 0.99992) |
| B | B2 `d143` delta | <= +0.05 A | INCONCLUSIVE (shell quantisation; point 0.000 A) | PASS |
| B | B3 auto-B delta | >= -10 A^2 | PASS | PASS |
| C | C1 `d143` after independent auto-refinement | <= +0.05 A | PASS | PASS |
| C | C2 auto-B after independent auto-refinement | >= -10 A^2 | PASS | INCONCLUSIVE (seed noise, favourable mean) |

**Conclusion.** On the 22 held-out movies of this collection, the native CUDA backend and the
all-FFTW hybrid are **non-inferior to the fixed CPU implementation in recoverable signal**, on
every prespecified endpoint that the data can resolve. The primary endpoint passes with the
observed difference roughly 150x inside the margin. Both INCONCLUSIVE results are artefacts of
endpoint granularity rather than evidence of inferiority: B2's comes from one Fourier-shell flip
in one of 22 jackknife replicates, in the accelerated arm's *favour*, with a point estimate of
exactly 0.000 A; C2's comes from an n = 3 interval against seed-driven B noise of up to 10 A^2
within a single arm, with a favourable mean.

This conclusion is **not** a statement that the backends are numerically equivalent, it is **not**
a claim of superiority anywhere a point estimate happens to favour them, and it is **not** a
recommendation to change any gate. Section 7 states what it does not cover.

### Outcomes declared unrun or unsupported

| Outcome | Status |
| --- | --- |
| Independent second collection (different specimen / session / detector) | **UNSUPPORTED** — none exists on the project hosts; the held-out split is within one collection |
| Bayesian polishing / motion re-estimation downstream | **UNRUN** by design, so nothing later can mask the corrected-output difference |
| Per-arm CTF parameters fed into the reconstruction | **UNRUN** — CTF is held common across arms by design |
| Particle-picking sensitivity to the backend | **UNRUN** — coordinates are imported and identical |
| CTF fitting on non-dose-weighted sums or grouped power spectra | **UNSUPPORTED** by the consumed artifacts (`--save_noDW` / `--grouping_for_ps` were not used) |
| Movie-level jackknife for Stage C | **UNRUN** — 22 x 3 refinements is ~7 h of exclusive GPU lock for a secondary endpoint |
| Multi-worker, multi-GPU, non-5x5-patch or dose-weighting-off configurations | **UNRUN** |
| Any statement about numerical gate thresholds | **OUT OF SCOPE** by design |

---

## 7. What this study does not establish

1. **Generalisation beyond one specimen and one collection.** One 24-movie beta-galactosidase set
   (EMPIAR-10204) at 0.885 A/pixel on a K2 at 200 kV, 1.277 e/A^2/frame. No second collection
   exists on the project hosts and acquiring one was outside this issue's resources. Nothing here
   speaks to other pixel sizes, dose rates, detectors, EER data, thicker specimens, larger
   beam-induced motion, or specimens where local motion dominates. **The held-out split is within
   one collection and is not a substitute for an independent dataset.**
2. **Absolute resolution.** Stage B imports orientations, so its FSC is comparative across arms
   only; its absolute value is biased identically in every arm and is not a gold-standard estimate.
3. **CTF fitting on non-dose-weighted sums.** The consumed arms wrote only the dose-weighted sum
   (`--save_noDW` and `--grouping_for_ps 3` were not used), so Stage A fits dose-weighted
   micrographs rather than the tutorial's grouped power spectrum. Dose weighting attenuates exactly
   the frequencies Stage A probes. The treatment is identical across arms so the paired comparison
   stays valid, but Stage A is measurably under-powered, as its own controls show: it cannot detect
   a 5% effective-data loss, and `CtfMaxResolution` cannot detect even a 20% one.
4. **Per-arm CTF in the reconstruction.** Stage B holds CTF parameters common across arms by
   design. Whether a per-arm CTF fit would change the reconstruction was not tested.
5. **Particle picking.** Coordinates are imported and identical in every arm, so any effect of the
   backend on *which* particles would be found is outside this design.
6. **Motion re-estimation and Bayesian polishing were never run**, deliberately: the corrected
   output is measured before any later step could mask a difference. Whether polishing would
   amplify or erase these differences is unmeasured.
7. **Multi-worker, multi-GPU and non-default option sets.** Every arm is `--j 1`, one GPU, 5x5
   patches, dose weighting on, seed 1.
8. **Superiority.** Several point estimates favour the accelerated arms. The design has no power
   for superiority and no superiority margin was set; these are reported, not claimed.
9. **Numerical gate thresholds.** This work proposes none, evaluates none, and changes none.

---

## 8. Reproduction, provenance, time and memory

### Source and inputs

| Item | Value |
| --- | --- |
| Motion-correction source | branch `exp/issue36-fftw-global-hybrid`, commit `5407373be31a6fe5f79a8cc5709be00723921b19` |
| Source tree checksum (`LC_ALL=C`) | `5db2b1ef3496442b300034a41def89ecffabaeaf1d41c9595ac041de01726a88`, identical on `4GPUs` and `cpu64` |
| CUDA binary (`4GPUs`, Release, `CUDA=ON`, `TIMING=ON`, arch 80) | `b6dead328d6c1f2abec144ef19e1111e59e85cd36e94dc5b64bab2f3086ce227` |
| Per-movie STAR set (24 one-row files), combined | `d4e71e92da0a079024c8deab0ac70a017e209d0f379a8f3f86e7814b3297f614`, identical on both hosts |
| 24 TIFF + gain manifest | verified identical on both hosts (Issue #36 provenance) |
| RELION | 5.1.0-commit-cb2683, byte-identical container on both hosts |
| CTFFIND | 4.1 from the same container, `sha256 33eab815...` |
| Downstream matched inputs | RELION 5.0 tutorial precalculated project for these same 24 micrographs; digests in [`results/environment.txt`](results/environment.txt) |

Per-arm, per-movie corrected-MRC **pixel-payload** (bytes 1024+) and **core-header** (bytes 0-223)
digests are in [`results/arm_provenance.json`](results/arm_provenance.json), recorded separately
because the MRC label region carries a `strftime` timestamp and is not byte-reproducible.
Control-arm digests are in [`results/control_manifest.json`](results/control_manifest.json).

### Exact commands

All scripts as executed are in [`scripts/`](scripts/). The command skeletons:

```sh
# Stage A - CTFFIND, per arm, cwd = proj/<arm>
relion_run_ctffind --i mics.star --o CtfFind61/ \
  --Box 512 --ResMin 30 --ResMax 5 --dFMin 5000 --dFMax 50000 \
  --FStep 500 --dAst 100 --ctffind_exe <ctffind> --ctfWin -1 \
  --is_ctffind4 --fast_search --j 8

# Stage B1 - matched re-extraction, per arm, cwd = proj/<arm>
relion_preprocess --i CtfFind/job003/micrographs_ctf.star \
  --reextract_data_star Refine3D/job019/run_data.star \
  --recenter --recenter_x 0 --recenter_y 0 --recenter_z 0 \
  --part_star Extract61/particles.star --pick_star Extract61/extractpick.star \
  --part_dir Extract61/ --extract --extract_size 360 --minimum_pick_fom -3 \
  --scale 256 --norm --bg_radius 71 --white_dust -1 --black_dust -1 --invert_contrast

# Stage B2 - reconstruction, per arm x subset x half
relion_reconstruct --i <subset>.star --o <name>_half<H>_class001_unfil.mrc \
  --ctf --sym D2 --subset <H> --pad 2

# Stage B3 - post-processing, identical mask and MTF in every arm
relion_postprocess --i <name>_half1_class001_unfil.mrc --o <out> \
  --mask MaskCreate/job020/mask.mrc --angpix 1.244531 \
  --mtf mtf_k2_200kV.star --mtf_angpix 0.885 --auto_bfac --autob_lowres 10

# Stage C - normal auto-refinement, per arm x seed in {61,62,63}
# MPI is required for --split_random_halves; --random_seed must be set explicitly,
# because RELION's default is time-derived and would confound seed with backend.
apptainer exec --nv <sif> mpirun -n 3 /opt/relion/bin/relion_refine_mpi \
  --o Refine61_held22_s<SEED>/run --auto_refine --split_random_halves --random_seed <SEED> \
  --i <arm>/held22.star --ref Class3D/job016/run_it025_class002_box256.mrc \
  --firstiter_cc --ini_high 50 --dont_combine_weights_via_disc --preread_images \
  --pool 30 --pad 1 --auto_ignore_angles --auto_resol_angles --ctf \
  --particle_diameter 200 --flatten_solvent --zero_mask --oversampling 1 \
  --healpix_order 2 --auto_local_healpix_order 4 --offset_range 5 --offset_step 2 \
  --sym D2 --low_resol_join_halves 40 --norm --scale --j 3 --gpu "0,1:2,3"
```

### Host discipline

Everything ran on `4GPUs` (4-gpu-vm, 432 GB RAM) under top-level `taskset -c 96-103` — eight
logical CPUs, inherited by every child — and behind `flock /tmp/motioncorr-bench.lock`, one phase
at a time, so no phase could perturb another session's measurement. No MotionCorr run was
launched: all three arms were consumed from Issue #36's completed artifacts.

The RELION analysis is CPU-bound and the project's convention routes CPU-only work to `cpu64`.
It stayed on `4GPUs` for a measured reason: cross-host staging ran at **0.66 MB/s** (57 MB in
86 s), so moving the 2.7 GB of accelerated-arm artifacts would have taken over an hour, against
roughly 30 minutes of actual compute, and Stage C needs the GPUs regardless. The 8-CPU cap and
the single-job mutex — the constraints that convention exists to enforce — were honoured
throughout.

### Time and peak memory

| Stage | Unit | Wall | Peak RSS |
| --- | --- | ---: | ---: |
| CTFFIND | 24 micrographs, one arm, `-j 8` | 37.5 - 37.8 s | 131 MB |
| Re-extraction | 4452 particles, one arm | 20.1 - 22.2 s | 195 MB |
| `relion_reconstruct` | one half-set, 2226 particles, box 256, pad 2, single-threaded | 46.9 s | 4.28 GB |
| Reconstruction batch | 156 jobs, 8-way parallel | 17 min 5 s | 8 x 4.3 GB |
| Control jackknife batch | 88 jobs, 8-way parallel | 9 min 42 s | 8 x 4.3 GB |
| `relion_postprocess` batch | 122 jobs, 8-way parallel | 4 min 30 s | - |
| `relion_refine_mpi` auto-refine | 4095 particles, 3 ranks x 3 threads, 4x A100, 15-17 iterations | 5 min 31 s - 6 min 54 s | 2.84 GB |
| Stage C total | 3 arms x 3 seeds = 9 refinements + 9 post-processing runs | 57 min | - |

244 reconstructions and 122 post-processing runs completed with zero failures. Four
post-processing logs contain an `ERROR` line from Ghostscript failing to write `logfile.pdf`
when concurrent jobs shared an output directory; this affects only the decorative PDF and no
numerical output.

The discarded first Stage C pass (uncontrolled time-derived seeds) is retained in
[`results/stageC_refinement.json`](results/stageC_refinement.json) under
`uncontrolled_seed_pass`, so the correction is auditable rather than merely asserted.
