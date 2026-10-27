# Two-patch native same-state CCF capture

The remaining noisy endpoint error is already a remote integer basin in iteration1. A continuous within-basin refinement changes its selected peak by0.01129642px, versus14.8123397721px physical endpoint error. The captured objective itself favours that remote candidate over the explicitly gauged truth-scoring point. Why that objective has the competing peak remains unresolved. No estimator, weight, filter, reference, gate, default or adoption change follows.

## Exact scope and source

PR287 research layer; sealed e28ffb10 pilot and edda0062 factorial remain unchanged. Plan7e1c0f28; source927a6890c8864f81ad58e44eac7281b080714af4 independently CLEAR by actual claudeAgent/claude-opus-5-5, effort HIGH, fastMode false. ea775cc5 only scopes a CMake CLI test to the required DC build; subsequent source remains identical927a. Exact review copied verbatim at reviews/OPUS_SOURCE_REPORT.md; all original review artifacts retained outside Git. Oracle v3 only; v1/v2 failures and all parent corrections remain archived.

Full CPU Release/DC-hook build PASS, binary `fd69d602f9c333b68f8ab4ccfaf32b56c586d872f4f7972fc1b379656806fd7d`. All eight selected checks have PASS evidence: LocalCcfCapture, LocalCcfCaptureCli, LocalB2Fit, CcfDcHook, ExperimentalFlagsCli, PatchRetryState, GlobalHalfGain, CoupledPeak. The last three initially ABORTED because the test launcher omitted the DC arm; original r3 failure remains, corrected invocation r4 used armnone. These are selected checks, **not full CPU qualification**. No new dependencies.

Pre-producer freeze991d5fd8/RUN_PINS.json binds all source/input/binary/driver/comparator hashes, review and OFF→ON order. Exactly2 tiny native producers, both exit0, original noisy128×96×5, UP-only DCboth+coupledall, j2/group1/bin1/patch3×3/max5/default.5px. No truth supplied to native; its input directory contains only unchanged noisy.star/noisy.mrcs. No further producer, fit, seed, GPU or full-size run.

## Native neutrality and capture completeness

| Comparison | Runtime JSON bytes | Raw case STAR bytes | Established product comparator |
|---|---|---|---|
| New capture OFF vs retained factorial UP-only | EXACT | EXACT | IDENTICAL |
| Capture ON vs new OFF | EXACT | EXACT | IDENTICAL |

Runtime SHA `9de5409895486ea04305a91fdf3c1350d5ddcb18559443fb3ca6a6fc99931325`; case STAR SHA `144b900f9e2283303b2966acb3d6261b906efda84fd1d857214e14efcfe93d3a`. Established compare_products.py enforces recursive equal filesets, MRC size/header0–223/pixels and root-normalized STAR/EPS. MRC timestamp label blocks are reported separately; logs/PDFs inventoried. Raw caseSTAR equality is an additional stricter witness. Existing comparator negative-control evidence is reused with the unchanged checker hash, not rerun native controls.

Both actual selected centres(62,47)/(62,79),42×32 patches, converge after2 actually executed iterations, all5frames captured each:20 states. Capture COMPLETE recorded1,475,994 bytes before its final receipt, below64MiB. No extra iteration or fallback clipping. All sample/spectrum/map arrays lossless float32, interleaved Re/Im for complex; shifts/scalars float64. Per-array dtype/shape/byte-strides, native strides/extents, normalization/sign/time and actual state metadata are retained.

Actual post-DC API input, actual C2R temporary-before and preserved API-after are identical in all20 states. Actual destroyed C2R temporary-after differs in1344 component positions per state, separate from API-after. No unsupported native Hermitian projection assumption. NumPy auxiliary inverse differs from the actual float map by at most2.980232238769531e-7 map units. Forward sample→NumPy FFT discrepancy max2.288818359375e-5 complex units, reported as cross-implementation precision, not a science gate.

Local supplemental saved-array verification reproduces scalar float tComplex raw and weighted expressions **exactly** all20states; full/window/previous-exit linkage and table-trig native Fourier shifts reproduce exactly (max component error0). This is saved arithmetic verification, no movie/fit. The earlier cpu64 supplement admission was rejected on a new foreign process; it never executed numerical work and remains recorded.

## Objective and iteration diagnosis

Analysis-v1 uses unchanged cleared v3 on actual saved real maps: strict native integer/tie/guard/fractional replay,32× sampled search-box/full-torus maxima, multistart local candidates, and explicit truth-point scoring. All20 native search/verdict/selected shifts reproduce. Maximum native-to-same-basin local candidate distance0.01786449608980448px. All20 best observed sampled/refined candidates share the native basin; none is a certified global optimum. `UNPROVEN_GLOBAL` throughout. Regional float64 Taylor bounds are diagnostics, not formal roundoff-certified or physical exclusion certificates.

Bad centre(62,79), frame4:

| State | Native integer | Native raw selected xy(px) | Refined local candidate xy(px) | Native objective | Truth-point objective |
|---|---|---|---|---|---|
| Iteration1 | (10,-8) | (10.0626881109,-7.8029257224) | (10.0650223292,-7.7918730974) |0.6859927335906874|0.6471161996582062|
| Iteration2 | (0,0) | (-0.0402482204,-0.2541907818) | (-0.0345252435,-0.2480988772) |0.6952255688898363|0.656694777991305|

Iteration1 truth-seeded local candidate(.7427115063,.5192413287) has value0.6746026346758596, below the remote candidate0.685994218076246. This direct point/local-candidate comparison is sufficient for the bounded observation; a dense search is not a global proof.

Truth scoring is deliberately explicit: physical desired anchored increment `D_f = truth(center,f)-global_f-entering_local_f`; raw objective point `D_f + actual_native_raw_frame0`. At bad iteration1 frame4 this is(-.7617316542871614,2.246762288086356). It uses the observed frame0 reference gauge and does not assume that a finite noisy/nonrigid leave-one-out window objective peaks at centre truth.

| Quantity(px) | Central(62,47) | Bad(62,79) |
|---|---|---|
| Iter1 anchored endpoint delta |(-1.6364227728,.9622331017)|(10.1265591158,-8.1682957625)|
| Iter2 anchored endpoint delta |(.4714658408,-.2512702458)|(-.2626990175,-.3356605331)|
| Physical final endpoint eta |(-.2110962826,-.8504293921)|(10.5617207477,-10.3853485436)|
| Physical endpoint eta norm |.8762372917923629|14.81233977208378|
| Native common observation Tr offset |(.0390765940,.0788509740)|(-.4239342203,-.6900696631)|
| Tr-reported endpoint eta norm |.7905213650479463|15.0146463204002|

All raw-minus-frame0, cumulative, final and `reported=final+.5*final_frame1` identities hold exactly. Physical and observed errors are distinct. Prior STAR-derived values differ by serialization rounding; the fullprecision capture reproduces the same mechanism.

Saved-spectrum isolated reference probes retain the remote endpoint with iteration2 sum-of-others and iteration1 current frame (refined10.0920413293,-8.4164056568). Iteration1 sum-of-others plus already-shifted iteration2 current frame has near-origin candidate(-.0615281279,.3764119323). These are auxiliary NumPy mixed-state algebraic probes, not a native rerun, changed trajectory or causal explanation of the objective's origin. The wrong basin already exists before iteration2 reference evolution.

The upstream coverage change9→8 remains explicit: dropped(104,47), BASE endpoint discrepancy23.00612px, not removed by a new filter. This two-patch capture does not diagnose that dropped patch.

## Independent result challenge and unchanged field harm

Parent saved-only audit independently verified all612 compact bundle files, all20 integer/tie/coupled fits (max2.22e-16px), direct symmetric-Nyquist Fourier/Newton same-basin refinements and exact iteration/Tr accounting. Exact report copied verbatim at reviews/PARENT_MAP_AUDIT.md; scripts/results/original failed Python preflight+absolute-Python successful audit archived. Parent did not rerun source/native/image/dense-global/regional-certificate checks. No source re-audit requested or implied.

Identical products permit exact reuse of sealed noisy UP-only characterization; no new checker/image run:

| Consumer | RMS Å | p95 Å | max Å | Numeric field gates | Checker accuracy | Sampling | Signal | Application |
|---|---:|---:|---:|---|---|---|---|---|
| Native runtime |1.6453708531561486|3.337290305991788|7.284025716813742|FAIL|FAIL|OUTSIDE_FIXED_ROI|CHARACTERIZATION|NOT_TESTED|
| Actual written/read STAR |1.6453973835300504|3.3372789185622946|7.283784224067593|FAIL|FAIL|OUTSIDE_FIXED_ROI|CHARACTERIZATION|NOT_TESTED|

The checker classes shown in both rows come from the single reused STAR checker receipt; no separate runtime/image checker was rerun. Identifiable=true in that reused noisy checker; this does not upgrade sampling/application status. No flat/repeated or new gate-role control rerun; their original unidentifiable classes remain in the sealed factorial. Local_enabled remains true, accepted8/rejected1; global converged in2iterations for this UP-only input. B2 nuisance-adjusted RMS estimand and prior noisy UP+B2 harm are unchanged. This capture is not an applied-image/science qualification.

## Resource deviations, failures and limits

All native admissions held eight leases including compatible overlapping leases and the mandatory append-open canonical benchmark lease; every recorded allowed mask32–47. j2/OMP2; actual OFF processThreads2, ON processThreads3 then2. The transient ON three-thread count is a deviation from intended process cap2; cause unresolved, no universal2-thread-enforcement or timing-comparability claim. Whole-job wall/RSS/product/exit/resource samples retained as receipts only, no performance inference. Combined scratch~1.25GB at admission, cap25GiB; at most tiny movies. No GPU/device use.

After primary analysis, a supplemental cpu64 saved-array launch was rejected before numerical work because new foreignPID3539553 overlapped the lane. No process signaled or stale lock bypassed. The allowed local continuation used existing absolute Python/NumPy with all numeric caps1, saved arrays only, and exited0. Failed archive-path/CMake-PATH/test-environment/report-schema/visual-preview/foreign-admission attempts remain in ATTEMPTS.md and raw receipts. All no-longer-needed owned processes completed; no native job left running.

UNRUN: full CPU CTest qualification/TierA formats, nativeGPU, new image/applicability/science qualification, formal global/regional/physical optimum certification, other patches/cases/seeds/fullsize/full100, estimator intervention. No merge, default, policy, gate or tolerance change. Native producer budget exhausted2/2. Prior promotion blockers remain.

## Smallest next discriminator — proposal only

**NO-GO for changing the fractional peak fitter as a remedy for this endpoint.** Its observed within-basin discrepancy is orders smaller than the remote error, and an accurate continuous maximizer still selects the remote objective basin in these states.

The unresolved blocker is why the inherited objective ranks that basin above the near-truth competitor: reference construction versus window/content/noise/global-alignment effects are not separated. The smallest next experiment is a separately frozen, saved-only reference contrast on these same initial captured FFTs: current leave-one-out sum versus frame0-only reference, all five frames at both patches, with the appropriate explicit common frame0 gauge and unchanged point/dense/local comparisons. No new producer or code/flag change is needed to test whether reference choice changes the objective ranking. No reference adoption is recommended before that discriminator; no robust fit, minimum-frame guard, filter, outlier removal, weight or large census is authorized by this package.

See RAW_INDEX.json pointer/hash in EVIDENCE_INDEX.json, compact results/states.csv and results/view.html. The raw compact bundle and parent audits are immutable; source927 remains unchanged.
