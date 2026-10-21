# Prospective counting-statistics truth census

Scope: test/diagnostic infrastructure only; base #267 `88b34ae0`. Main native
controls use `36913740`. Numerical arms use diagnostic `97fd8107` (#254+#260),
with the retained observation-only runtime-model patch. No production source
changes or inherited CPU fixes are proposed here.

Freeze before large-movie estimator results: ten conditions, seeds 0–9 each,
40 frames, 4096×4096 except nonsquare 5760×4092, pixel size 0.885 Å, 5×5
patches, grouping/binning 1, default B/search/convergence/fit policies. Eight
float arms are CPU/CUDA × none/global/local/both CCF DC removal; CPU double
CCF with no DC removal is the numerical reference. A double/both control
checks numerical offset neutrality. The reference retains float movie spectra
and feedback, so it is neither a fully double movie pipeline nor motion truth.

Conditions are dose 0.5/1/2/4 e/px/frame; out-of-model at dose 1; nonsquare at
dose 1; pedestal 0/32 at dose 1; positive amplitude .25/4 at dose 1 with pedestal
1. Baseline dose1 supplies pedestal1/amplitude1. These are ten declared
conditions, not a complete geometry×dose×motion×offset factorial. Same scene
and matched seed draws support intensity comparisons. Each condition contains
ten independent Poisson detector-noise realizations; repeated arms/pixels are
not independent samples. No seed selection from estimator outputs.

Synthesis: random weak multiscale texture, 4% RMS expectation contrast, radial
Fourier envelope with .007/.055 cycles/px scales and cutoff .16. FFT is used
only to construct the oversampled scene. An independent SciPy cubic B-spline
represents it continuously at 2× sampling with a 32-pixel halo. Inverse motion
is solved by contraction with per-tile forward closure ≤1e-8 px. Photon counts
are drawn independently in detector coordinates after evaluating each warped
expectation. No MotionCorr shift/crop/warp helper synthesizes pixels. This is
a texture/counting proxy, without CTF, radiation damage, detector MTF or event
coincidence; it does not replace held-out scientific data.

Forward map is `F_f(q)=q+g_f+L_f(q)`. Global drift has fast exponential early
motion and slow later drift. In-model L has six spatial monomials and cubic
time dependence, within the 18-term polynomial. Out-of-model adds sinusoidal
space/time terms. Correction truth is `D_f(q)=q-F_f(q)` in fixed frame-0
material coordinates. No origin subtraction or per-frame registration is
allowed. MRC is written directly in native row order. TIFF must store reversed
rows to yield identical internal coordinates; a generic re-encode can invert
the truth convention. Native zero and integer-translation controls precede
large generation.

Injected intensities are `P+C*(Poisson(dose*expectation)-dose)`, retaining
original dose in the receipt. No gain and `--skip_defect` are mandatory: CPU
preprocessing does not write frame pixels, CUDA applies identity gain, and
hot-pixel replacement is bypassed. Consequently injecting at file creation is
exactly equivalent to injecting after detector preprocessing in this restricted
path. The offset/amplitude sweep does not test defect thresholds. It neither
removes movie DC for reconstruction nor uses different peak policies.

Primary field statistics use a fixed 129×129 endpoint-inclusive lattice from
(32,32) to (nx−33,ny−33), all 40 frames. Report vector RMS/P95/max in px and Å,
per-frame tails, declared global drift error and local component separately.
These are lattice statistics, not all detector pixels. Border statistics use
a separate fixed edge lattice. Total field error is never re-gauged. Native
pre-write coefficients are captured; serialized STAR loss is measured separately.
Existing 0.20/0.40/0.80 Å field-distance limits remain descriptive for this new
characterization family, with failures retained. The v2 native checker is run
unchanged; native out-of-ROI failures are recorded with independent field-only
metrics rather than interpreted as passes.

Record process exit and global incremental RMSD/convergence (<.5 px), accepted
local model and patch convergence separately. Exit 0 does not establish recovery.
Residual frequency transfer is UNRUN until an independent large-frame adapter
exists; field accuracy does not imply correct published pixels. Historical
`km_local_noisy` characterization FAIL remains part of interpretation.

Paired unit is one noise seed within condition. Compare per-seed total-field
RMS, global trajectory RMS, local RMS and maxima, retaining all seeds. Report
exact two-sided sign tests (ties omitted and counted), paired deltas/ratios and
all worse cases. No pooled-pixel p-values, cross-condition averaging or cutoff
tuning. CPU/CUDA distance is a continuity diagnostic; truth decides accuracy.
Float-vs-double error and double-vs-truth are distinct. No downstream science
or performance claim is made from these shared-host correctness runs.

Resources: cpu64 generation/CPU, eight pinned CPUs per process; 4GPUs Release
CUDA, UUID selection, one movie/process, at most one per-GPU advisory lock,
released between seed batches. Raw movies stay in task scratch; commit only
scripts, small receipts/hashes, metrics/logs and this evidence. No merge.

Interpretation frozen before paired analysis: use exact two-sided sign-test p<.05
plus median paired RMS direction to call an improvement or harm; otherwise label
neutral/mixed (absence of evidence, not equivalence). Report effect sizes and
worst regressions alongside the category. Numeric reference proximity is a
separate descriptive maximum field distance ≤0.001 px, not a release threshold.
Sign-test ties use absolute RMS delta ≤1e-9 px; no multiple-condition claim is
made without noting the exploratory multiplicity.
