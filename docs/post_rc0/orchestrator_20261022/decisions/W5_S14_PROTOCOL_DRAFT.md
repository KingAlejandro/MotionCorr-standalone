# S1.4 / M6 protocol refresh — unapproved planning draft, 22 October 2026

This is preparation for the updated Notion W5 requirement, not preregistration,
permission to run, a source freeze, or a scientific result. C2 and the analysis
manifest do not yet exist. No held-out scientific outcomes were inspected and
no acquisition, reconstruction, refinement, or native experiment was started.

## Evidence that this refresh must preserve

Sources read: live issues #61 and #73 and all their comments, plus PR #65 source
`2afbb3140789a22121bec640983755932ab551d4`: PROTOCOL.md, README.md,
CERTIFICATE_VALIDATION.md, DESCRIPTIVE_CALIBRATION_PLAN.md and the 22 October
pilot README. The historical protocol and results remain unchanged. Stage B is
INCONCLUSIVE; the current certificate consumer intentionally has no positive
scientific-certification path. The already unblinded tutorial collection and
particle-count pilot are developmental/exploratory, not a fresh holdout.
Particle-count retention and noise variance alone do not establish known SSNR
harm. Historical control targets fitted using the endpoint cannot validate it.

The two-movie EMPIAR-12963 pilot is an independent collection pilot, not a
sufficient confirmatory particle/half-map study. Past acquisition proposals
(256/1024 movies or roughly 270 GiB) are not staged data or present permission
to acquire them. No larger acquisition is proposed by this draft.

## Freeze before outcomes

Prepare a metadata-only eligibility inventory of already acquired collections.
For each collection pin accession/license, session/specimen/detector, exact movie
IDs, raw/gain hashes, geometry/rendering/grouping/dose/pixel size, gain-transform
provenance, acquisition exposure, available matched particles/halfsets/mask and
remaining uncertainty. Unknown required values block that analysis. Record
whether prior scientific outcomes or tuning used the collection; correction
runtime/image diagnostics are a separate exposure field, not automatically a
claim of untouched scientific data.

Select at least one S1 family and an independent collection by a prospective
metadata-only rule, never by which candidate produced a favourable outcome.
Freeze eligibility, inclusion/exclusion rules, movie/collection identities,
particle accounting and failure handling before scientific endpoint access.
If existing data cannot meet the required collection/particle/metadata scope,
report the gap and a bounded resource request; do not silently substitute a
small pilot and call it confirmatory.

Pin the C2 commit/tree, input and gain hashes, build flags and CPU/CUDA binary
hashes, movie options, output manifests, and relevant M3/M4/M5 dispositions.
CPU and native CUDA are paired on the same frozen C2 source; CPU output is
a comparator, not ground truth. Hybrid is an optional separate claim requiring
an explicitly frozen and independently qualified route; historical hybrid
outputs do not qualify a changed C2. Baseline products remain immutable. Any
candidate change requires a versioned comparison and explicit treatment of
already exposed outcomes.

## Matched analysis and outcomes

1. CTF/high-frequency diagnostics are a screen. Record missing/failed CTF fits,
   product/refusal rates and denominator for every collection. CTF alone cannot
   establish signal noninferiority.
2. Evaluate corrected products before further motion re-estimation. Use common
   particle selection, coordinates, original half-set assignments, optics/CTF,
   orientations/origins, masks, box/pixel size and reconstruction settings.
   Verify completeness and named fields, including empty/missing/aliased-stack
   negatives. Match the entire intended design, not just a digest assertion.
   Fixed-orientation half-map FSC is a controlled comparative diagnostic, not
   an independent gold-standard absolute resolution claim.
3. Separately perform independently refined half-maps with frozen paired seeds,
   references, masks and refinement settings, then the complete intended
   workflow including motion re-estimation as a distinct result. A later
   workflow must not replace or erase the pre-re-estimation result. Prevent
   cross-half leakage and record masks/phase-randomization settings explicitly.
4. Report independent-half FSC curves and d143, relative B-factor/Guinier-fit
   range, signal/transfer diagnostics, failures and collection heterogeneity.
   An FSC-invariant deterministic envelope demonstrates a limitation of FSC,
   not universal harmlessness of filtering. Support-class scope is limited to
   the frozen evaluated modes and collections.

Resample/delete units at the paired movie level within collections; treat
collection-level heterogeneity explicitly. Do not use particles or pixels as
independent collection replicates. A small number of collections limits any
population-generalization statement. Freeze the missing-data/abstention rule,
analysis denominator and paired inclusion set. Refused/missing candidate
products remain failures or declared missing outcomes, not dropped successes.

## Margins, calibration and decision policy requiring M6

The historical rho margin 0.95, d143 allowance +0.05 A, and supportive B-factor
difference -10 A² are reference proposals, not an automatic approval for C2 or
new collections. Decide the primary endpoint and direction, physical meaning,
qualifying frequency shells, minimum information, collection-level estimand,
margin rationale and multiplicity/claim structure before held-out evaluation.
Do not tune these to observed candidate outcomes. Publish full curves and
continuous estimates even when a binary verdict is unavailable.

Before a positive noninferiority claim, independently justify the forward harm
model and control severities. The endpoint under validation cannot define the
control's true harm. Test null/identity, scientifically negligible, boundary and
clearly harmful cases with distinct simulation/noise seeds and precision regimes
covering the intended comparison. Freeze the operating-characteristic criterion
and acceptance confidence level prospectively; point estimates or hash equality
cannot open certification. Keep empirical harm detection, boundary false-pass
rate and real-arm inference separate. A negative/invalid certificate must force
INCONCLUSIVE while retaining numerical pre-gate decisions.

Planning arithmetic only: with zero false passes in N independent, genuinely
boundary-harm trials, the exact one-sided 95% binomial upper limit is
`1 - 0.05**(1/N)`. N=20 gives 13.91%; N=59 gives 4.95%. Thus merely running
20 trials with zero false passes does not demonstrate an upper rate <=5% at
95% confidence. This is a worked design constraint, not selection of N=59,
a harm model, a power guarantee or an adopted certification policy. Simulated
coverage applies only to its validated forward model/regimes. Lower-power or
miscalibrated instruments yield INCONCLUSIVE, never an easier margin.

## Execution gate and deliverable

All new S1.4 numerical work is UNRUN. Execution requires relevant M3/M4/M5
resolutions, required motion-truth criteria, explicit C2 freeze, independent
protocol review and M6 approval before held-out outcome inspection. A decision
of no DC change alone is insufficient. Resolve the eligibility manifest and
forward-harm/operating-characteristic design before requesting approval of a
concrete executable protocol.

After those gates, use current occupancy, per-venue CPU/GPU allocations,
nonblocking locks, fresh bounded scratch, private dependency/runtime identities,
and fail-closed driver/product accounting. Route CPU analysis to cpu64 under a
coordinated allocation; allocate GPU refinement separately. Revalidate actual
container mounts/read-only input and private output boundaries rather than
assuming wrapper arguments enforce them. No current lane is borrowed here.
Estimate storage from actual manifests and bound reconstruction/refinement jobs
before launch. Retain failed attempts, exact argv/env/PID/exits, source/input/
binary identities, products, and pre/post health. Publish the reviewed protocol
and eventual report on #61/#73 with PASS/FAIL/INCONCLUSIVE/UNRUN distinctions;
M7/support class and rc1 remain maintainer decisions.
