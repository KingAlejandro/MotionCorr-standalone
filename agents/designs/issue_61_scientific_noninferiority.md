# Issue 61: scientific non-inferiority evaluation of CPU, native CUDA and all-FFTW hybrid motion correction

## Problem this design addresses

Gate 2 asks whether an accelerated backend reproduces the CPU reference *image*. Issue #61 asks a
different question: whether an accelerated backend preserves *recoverable cryo-EM signal*. A
corrected-image relative RMSE of 0.0047 answers the first question and is silent on the second.
The two can diverge in both directions — a backend can fail an image-agreement limit while losing
no usable signal, and it can pass one while destroying high-frequency information. Nothing in the
repository currently measures the second quantity, so no scientific acceptance statement about the
CUDA or hybrid backends is presently supportable in either direction.

## Decision

Treat this as an **evaluation-protocol** issue, not an implementation issue. No change is made to
`src/`, to `tools/compare_motioncorr.py`, or to any numerical gate. The deliverable is a
preregistered protocol plus its executed results, living entirely under
`docs/issue61_noninferiority/`.

The evaluation is a **paired, matched-everything downstream comparison**. The three arms
(fixed CPU, native CUDA, all-FFTW hybrid) are run from one source commit on one input set with one
set of movie options; every downstream step — particle selection, coordinates, orientations, CTF
parameters, half-set assignment, mask, box, pixel size, symmetry, sharpening settings — is held
byte-identical across arms. The *only* thing that varies is the corrected micrograph. Any
difference in the reconstruction endpoint is therefore attributable to the corrected image content
and to nothing else.

This matched design is deliberately chosen over three plausible alternatives:

- *Independent refinement per arm* confounds image quality with refinement stochasticity and
  orientation-assignment feedback, and needs many more GPU hours to reach usable precision. It is
  retained as a secondary, explicitly-labelled stage, not as the primary comparison.
- *Comparing each arm against RELION 5.1* imports the separate #20 RNG/extraction question.
- *Deriving acceptance from image RMSE* is precisely what #61 rejects.

## Numerical and statistical contract

**Unit of replication is the movie, never the pixel.** A 3710x3838 micrograph does not supply
14 million independent observations; it supplies one. All uncertainty is estimated across movies
(paired bootstrap for per-micrograph endpoints, delete-one-movie jackknife for whole-dataset
reconstruction endpoints).

**Margins are fixed before the confirmatory data are seen, and are derived from physics or from
reference-data dispersion, never from the arms' own results.** Movies `00021` and `00046` were used
throughout #36 and hybrid development and are therefore *development* data; they are excluded from
the confirmatory analysis set and used only to debug the pipeline and confirm that each endpoint is
computable. The remaining 22 movies are held out.

**Direction of the claim matters.** Non-inferiority tests are one-sided: the accelerated arm must
not be *worse* than CPU by more than the margin. A superior point estimate is reported but never
claimed as an improvement, because the design has no power for that and no margin was set for it.

**Inconclusive is a permitted and expected verdict.** With 22 movies and endpoints whose
between-arm differences may be far below the between-movie dispersion, a confidence interval that
spans the margin is the honest result and must be reported as such rather than rounded to a pass.

## Failure modes this design must not fall into

1. *A check that cannot observe what it asserts.* Each endpoint must be shown to move when the
   input degrades. The protocol therefore requires a positive control: an arm deliberately
   degraded by a known amount must fail the endpoint it is supposed to detect. Without it, three
   green endpoints prove only that the pipeline runs.
2. *Single-movie generalisation.* `00021` is the lowest-signal and least representative of the 24
   and is the worst CTF fit in the reference set; no endpoint may be reported from it alone.
3. *Whole-file hashing.* MRC headers carry a `strftime` label and are not byte-reproducible.
   Provenance uses pixel-payload digests and the existing split comparator, never whole-file hashes.
4. *Silent scope creep into sibling issues.* `docs/reference_gates.md` (#58), synthetic ground-truth
   fixtures (#59) and perturbation tooling (#60) are owned elsewhere and are not edited here.
5. *Equating "not measurable" with "not different".* Every outcome the available data cannot
   establish is listed explicitly as unrun or unsupported.

## Interface with #36 and #58

This work **consumes** #36's completed 24-movie three-arm artifacts; it does not re-run them and
does not restate Gate 2 status. Gate 2 relative RMSE is carried per movie as a descriptive
covariate so that the relationship between image agreement and downstream signal can be inspected,
which is the empirical input #58 and #60 need in order to calibrate or justify any threshold. This
protocol proposes no threshold and changes none.
