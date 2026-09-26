# Preregistered protocol — scientific non-inferiority of CPU, native CUDA and all-FFTW hybrid motion correction

Issue: [#61](https://github.com/KingAlejandro/MotionCorr-standalone/issues/61).
Design note: [`agents/designs/issue_61_scientific_noninferiority.md`](../../agents/designs/issue_61_scientific_noninferiority.md).

**Status: PREREGISTRATION.** Every threshold, endpoint, analysis set and decision rule below was
fixed and committed before any endpoint value for any arm was computed. The confirmatory
(held-out) data had not been processed through any endpoint when this file was committed. The
commit that introduces this file is the preregistration timestamp; any later change to a margin,
an endpoint definition or the analysis set must appear as a separate commit labelled
`PROTOCOL AMENDMENT` with its reason, and the original remains in history.

---

## 1. Question

Do the native CUDA backend and the opt-in all-FFTW hybrid backend preserve the cryo-EM signal that
is recoverable from a movie, relative to the fixed standalone CPU implementation on the same
source, inputs and options?

This is **not** the Gate 2 question. Corrected-image relative RMSE is recorded here as a
descriptive covariate only. No scientific conclusion is drawn from it, no numerical gate is
evaluated, and no threshold is proposed or changed by this work.

## 2. Arms

All arms derive from one source commit and one input set.

| Arm | Description | Execution |
| --- | --- | --- |
| `cpu` | Fixed standalone CPU, reference/oracle | `cpu64`, `CUDA=OFF` build, `OMP_NUM_THREADS=1`, `--j 1`, one movie per process, under `/tmp/motioncorr-cpu64-bench.lock` |
| `default` | Native CUDA global + local alignment | `4GPUs` GPU 0 (A100 80GB), `--gpu 0 --j 1`, one movie per process, under `taskset -c 96-103` + `/tmp/motioncorr-bench.lock` |
| `allfftw` | Opt-in all-FFTW hybrid (`MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1`) | same binary and discipline as `default` |

These three arms are **consumed, not re-run**: they are the completed Issue #36 24-movie
three-arm comparison. Re-running them is explicitly out of scope.

Two further arms are **instrument controls**, constructed by transforming the `cpu` arm's
corrected micrographs. They exist to establish that the primary endpoint can observe what it
asserts, and are not backends:

| Control | Construction | Purpose | Prespecified expectation |
| --- | --- | --- | --- |
| `ctrl_noise_f005` | `cpu` micrograph + independent Gaussian noise of variance `0.05 x var(micrograph)` | sensitivity: a known 5% effective-data loss | primary endpoint `rho ~ 1/(1+f) = 0.952` |
| `ctrl_noise_f020` | as above with `f = 0.20` | sensitivity at a clearly-unacceptable loss | `rho ~ 0.833` |
| `ctrl_envelope_b20` | `cpu` micrograph multiplied in Fourier space by `exp(-B s^2 / 4)` with `B = 20 A^2`, applied identically to every micrograph | specificity: a deterministic envelope produces a large corrected-image RMSE but, being identical in both half-sets, cannot change FSC | large relative image RMSE, `rho ~ 1.00` |

`ctrl_envelope_b20` is the direct empirical demonstration of this issue's premise: image RMSE and
recoverable signal are not interchangeable. These three controls are a two-point instrument
calibration of one endpoint. The systematic perturbation matrix for diagnostic calibration is
Issue #60's scope and is not duplicated here.

## 3. Movie options (identical across arms)

```
--use_own --j 1 --seed 1 --dose_weighting --dose_per_frame 1.277
--patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc
```

`default` and `allfftw` add `--gpu 0`; `allfftw` additionally sets
`MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1`. Each movie is driven by its own one-row STAR file, because
batch invocation changes the per-process `rand()` stream used by hot-pixel replacement and would
make only the first movie comparable.

Known deviation from the RELION 5.0 tutorial's own motion-correction job: these runs omit
`--grouping_for_ps 3`, `--save_noDW` and `--float16`. Consequences are stated in section 8.

## 4. Datasets and analysis sets

Only one movie collection is available on the project hosts: the 24 RELION SPA tutorial movies
(beta-galactosidase, EMPIAR-10204; 24 frames of 3710 x 3838 at 0.885 A/pixel, 1.277 e/A^2/frame,
200 kV, Cs 1.4 mm). A second, genuinely independent collection (different specimen, session or
detector) is **not available** and is not obtainable within this issue's resources. This is a
stated limit on generalisation, not a held-out set.

The held-out structure is therefore *within* the collection:

- **Development set (2 movies): `20170629_00021`, `20170629_00046`.** These two carried every
  Issue #36 diagnostic and the entire hybrid development. They are used only to build and debug
  the analysis pipeline and to confirm each endpoint is computable. `00021` in particular is the
  least representative of the 24 (it has the worst CTF fit in the reference set, 4.875 A against a
  set mean of 3.336 A) and no endpoint is reported from it alone.
- **Confirmatory held-out set (22 movies): the remaining 22.** All primary results come from
  these. Margins are frozen by this document before they are evaluated.

All-24 values are reported as a secondary, clearly-labelled figure.

## 5. Downstream pipeline (identical across arms)

Source of matched downstream inputs: the RELION 5.0 tutorial precalculated project for this exact
24-movie set, at
`/home/alex/relion-container-tests/data/spa-relion50-precalculated/extracted` on `4GPUs`
(`Refine3D/job019`, 4452 particles, box 360 scaled to 256, 1.244531 A/pixel, D2,
`MaskCreate/job020/mask.mrc`, `mtf_k2_200kV.star`, `CtfFind/job003/micrographs_ctf.star`).

Each arm is placed in its own RELION project directory in which
`MotionCorr/job002/Movies/<name>.mrc` is a symlink to that arm's corrected micrograph. Every
downstream command is then **byte-identical across arms**, and only the symlink target differs.

### Stage A — CTF fit / high-frequency screen (per micrograph)

CTFFIND 4.1 (the RELION 5.1 container's `ctffind`) is run on each arm's corrected micrograph with
the tutorial's own search parameters: box 512, ResMin 30 A, ResMax 5 A, dFMin 5000 A, dFMax
50000 A, FStep 500 A, dAst 100 A, fast search, no phase shift; 0.885 A/pixel, 200 kV, Cs 1.4 mm,
amplitude contrast 0.1. Exact stdin is logged per micrograph.

### Stage B — matched-orientation reconstruction (controlled diagnostic, primary)

1. `relion_preprocess --extract --reextract_data_star Refine3D/job019/run_data.star --recenter
   --extract_size 360 --scale 256 --norm --bg_radius 71 --invert_contrast --i
   CtfFind/job003/micrographs_ctf.star`. `--float16` is deliberately **not** used, so extraction
   does not quantise away the differences under test.
2. The extracted particle STAR inherits, unchanged from `run_data.star`: coordinates, per-particle
   orientations (`rlnAngleRot/Tilt/Psi`), origins, CTF parameters, optics group, and
   `rlnRandomSubset`. Nothing is re-estimated. Half-set membership is identical across arms.
3. `relion_reconstruct --ctf --subset 1` and `--subset 2` per arm.
4. `relion_postprocess --mask MaskCreate/job020/mask.mrc --angpix 1.244531 --mtf mtf_k2_200kV.star
   --mtf_angpix 0.885 --auto_bfac --autob_lowres 10` per arm.

Because orientations, CTF and selection are fixed and externally derived, the resulting FSC is a
valid *relative* measure across arms but is **not** a gold-standard resolution estimate; its
absolute value is biased identically for all arms. Stage B measures the corrected output before
any later motion re-estimation can mask a difference.

### Stage C — normal refinement workflow (secondary)

Per arm, `relion_refine --auto_refine --split_random_halves` from the same starting reference,
particles, mask and settings as `Refine3D/job019`, followed by the same `relion_postprocess`.
This stage requires a coordinated exclusive GPU window. **If it is not run, it is reported as
UNRUN, not as absent evidence of equivalence.**

## 6. Endpoints, directions and margins

`lambda = 0.0250785 A` at 200 kV. Reference dispersion below is from the tutorial's own
`CtfFind/job003` over the same 24 micrographs — reference data, not arm results.

### Stage A (paired per micrograph; n = 22 held-out)

| ID | Endpoint | Test | Margin | Derivation |
| --- | --- | --- | --- | --- |
| A1 | `rlnCtfMaxResolution` (A, lower is better) | non-inferiority | arm may be at most **+0.10 A** worse in the paired mean | 3.0% of the reference mean (3.336 A); 0.27x the between-micrograph SD (0.365 A); ~4 CTFFIND spectrum shells (shell spacing 0.025 A at 3.3 A for box 512 at 0.885 A/pixel). Well below the ~0.5 A granularity at which micrograph QC cuts (4 A, 5 A) are set, so a shift of this size cannot change a QC decision. |
| A2 | mean defocus `(U+V)/2` (A) | equivalence, two-sided | **+/- 45 A** | Defocus error giving a `pi/8` (22.5 deg) CTF phase error at 3.0 A: `dz = d^2/(8 lambda) = 44.9 A`. Half of the conventional `pi/4` tolerance (89.7 A). Independent of the between-micrograph defocus spread (SD 1299 A), because this is a paired comparison of the same micrograph. |
| A3 | `rlnCtfFigureOfMerit` (higher is better) | non-inferiority | at most **-5% relative** in the paired mean | 5% of the reference mean (0.1677) is 0.0084, i.e. 0.40x the between-micrograph SD. |
| A4 | rotationally averaged power in 6-3 A relative to CPU | descriptive | none | CTFFIND-independent spectral check; reported, not tested. |

### Stage B (whole held-out set; delete-one-movie jackknife)

| ID | Endpoint | Test | Margin | Derivation |
| --- | --- | --- | --- | --- |
| **B1 (primary)** | `rho` = effective-data fraction vs CPU = **median over qualifying shells of `SSNR_arm(s)/SSNR_cpu(s)`**, with `SSNR(s) = 2*FSC(s)/(1-FSC(s))` from the unmasked-corrected half-map FSC; qualifying shells are those with `8.0 A >= d(s) >= 3.0 A` **and** `FSC_cpu(s) >= 0.143` | non-inferiority | lower one-sided 95% bound of `rho` must be **>= 0.95** | Per-shell SSNR is proportional to the number of contributing particles, so `rho` is directly the fraction of effective data retained. At d = 3.15 A with a Rosenthal-Henderson B of 100 A^2, a 5% effective-particle loss corresponds to only 0.016 A of resolution and a 20% loss to 0.070 A; the 5% margin is therefore strict rather than permissive. If fewer than 20 shells qualify, B1 is reported INCONCLUSIVE. |
| B2 | resolution at FSC = 0.143 (A) | non-inferiority | at most **+0.05 A** worse | 1.6% of the 3.15 A reference; 1.6 Fourier shells (shell spacing 0.031 A at box 256, 1.244531 A/pixel). This endpoint is quantisation-limited: the 5% loss that B1 targets corresponds to 0.016 A, which is *below* one shell, so B2 cannot be made as strict as B1 and is reported as a coarse secondary. |
| B3 | `rlnBfactorUsedForSharpening` (A^2) | supportive | `B_arm - B_cpu >= -10 A^2` | A more negative auto-sharpening B indicates a steeper Guinier falloff. The auto-B fit is itself unstable, so this is supportive only and never decides the verdict. |

### Stage C (if run)

| ID | Endpoint | Test | Margin |
| --- | --- | --- | --- |
| C1 | resolution at FSC = 0.143 after independent auto-refinement (A) | non-inferiority | at most **+0.05 A** worse |
| C2 | `rlnBfactorUsedForSharpening` (A^2) | supportive | `>= -10 A^2` |

### Descriptive covariates (never tested, never used for acceptance)

Gate 2 corrected-image relative RMSE and absolute RMSE per movie; wall time; peak memory;
global-trajectory and local-patch RMS differences. These are carried so that the relationship
between image agreement and downstream signal can be inspected by #58 and #60.

## 7. Uncertainty and decision rules

- **The unit of replication is the movie.** Pixels within a micrograph are not independent
  replicates and are never treated as such.
- **Stage A:** paired differences across the 22 held-out movies. Report the paired mean
  difference, its 95% CI from a paired BCa bootstrap over movies (10,000 resamples, seed 61), and
  the paired-t interval as a cross-check. Non-inferiority is one-sided at 95%; equivalence (A2) is
  the two-sided 90% CI against `+/- 45 A` (TOST).
- **Stage B:** delete-one-movie jackknife over the 22 held-out movies. Each replicate removes all
  particles from one movie and repeats extraction-free re-reconstruction and post-processing for
  every arm, preserving the pairing. 95% bounds use `t(0.95, 21)` with the jackknife SE of the
  paired quantity. **Cost rule fixed in advance:** if one `relion_reconstruct` of a half-set
  exceeds 180 s wall on `cpu64` with 8 threads, switch to a delete-`d` block jackknife with 6
  disjoint blocks (`d` = 3 or 4 movies) and the corresponding delete-`d` variance estimator,
  `t(0.95, 5)`. This rule is triggered by measured cost only, never by a result.
- **Verdicts,** stated per arm per endpoint:
  - **PASS (non-inferior)** — the one-sided 95% bound is inside the margin.
  - **FAIL** — the whole one-sided 95% interval lies outside the margin.
  - **INCONCLUSIVE** — the interval spans the margin. This is an expected, reportable outcome and
    is never rounded up to a pass.
- A point estimate favouring an accelerated arm is reported but is **not** claimed as an
  improvement: the design has no power for superiority and no superiority margin was set.
- No multiplicity adjustment is applied across endpoints, because each endpoint carries its own
  separate claim rather than contributing to one omnibus claim. B1 is the single primary endpoint
  per arm; A1-A3 are a prespecified screen; B2, B3, C1, C2 are secondary or supportive. This is
  stated so that readers can discount the secondary family appropriately.
- **Validity precondition.** If `ctrl_noise_f005` does not yield a `rho` whose interval contains a
  detectable loss distinguishable from 1.0, the primary endpoint is declared unable to resolve its
  own margin, and every Stage B verdict is reported as INCONCLUSIVE regardless of the arm values.

## 8. What this design cannot establish (declared in advance)

1. **Generalisation beyond one specimen and one collection.** One 24-movie beta-galactosidase set
   at 0.885 A/pixel on a K2 at 200 kV. Nothing here speaks to other pixel sizes, dose rates,
   detectors, EER data, thicker specimens, or movies with large beam-induced motion.
2. **Absolute resolution.** Stage B orientations are imported, so its FSC is comparative only.
3. **CTF fit on non-dose-weighted sums.** The consumed arms wrote only the dose-weighted sum
   (`--save_noDW` and `--grouping_for_ps 3` were not used), so Stage A fits dose-weighted
   micrographs rather than the tutorial's grouped power spectrum. Dose weighting attenuates exactly
   the high frequencies Stage A probes, so Stage A is **less sensitive** than the tutorial route.
   The treatment is identical across arms, so the paired comparison stays valid; the loss is power,
   not validity.
4. **Per-arm CTF in the reconstruction.** Stage B uses one common set of CTF parameters across arms
   by design. Whether a per-arm CTF fit would change the reconstruction is not tested.
5. **Particle picking sensitivity.** Coordinates are imported and identical across arms, so any
   effect of the backend on *which* particles would be found is outside this design.
6. **Motion re-estimation / Bayesian polishing.** Not run; a later polishing step could mask or
   amplify differences and is not evaluated.
7. **Multi-worker and multi-GPU behaviour, and non-default option sets.** All arms are `--j 1`,
   one GPU, 5x5 patches, dose weighting on.
8. **Superiority of any arm**, and **any statement about numerical gate thresholds.**

## 9. Provenance to be recorded

Source commit and `git` tree checksum; per-host binary SHA-256; per-movie input TIFF and gain
SHA-256 verified identical on both hosts; per-arm corrected-MRC **pixel-payload** digests (bytes
1024+) and core-header digests (bytes 0-223) separately, because the MRC label region carries a
`strftime` timestamp and whole-file hashes give false mismatches; exact commands for every stage;
host, lock and CPU-affinity discipline for every run; RELION and CTFFIND versions and container
digests; all machine-readable endpoint values as JSON under `docs/issue61_noninferiority/results/`.
