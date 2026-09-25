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
