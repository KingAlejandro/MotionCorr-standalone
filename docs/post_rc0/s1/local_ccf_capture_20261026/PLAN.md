# Frozen two-patch same-state local CCF diagnostic

Before any new native producer. Sealed references e28ffb10 and factorial edda0062 remain unchanged. Numerical baseline production326f03a0, binary531a1b0984dfbb39bd1b43afa23561091365a4d0459967ef5ee24ca69344c2eb. This follow-up adds observation-only, default-off CPU diagnostics, not an estimator/default/acceptance/publication/gate change. INITIAL_PINS.json binds baseline source and retained noisy input; reviewed diagnostic source/new binary pins will be committed before producers.

## Scope and hypotheses

One retained128×96×5 noisy movie, UP-only (DCboth + coupledall), max_iter5/default0.5px, group1/bin1, patch3×3,j2, B2/other experiments off. Capture exactly centre(62,79), native patch(3,2), and comparison(62,47), patch(2,2), all5 frames in every actually executed iteration. Do not force extra iterations. Baseline both converge2iterations, guards0; endpoint tracking discrepancy14.81234px versus0.87624px. The UP coverage change9→8/dropped(104,47) with base23.00612px discrepancy remains explicit and is not an analytical exclusion.

Hypotheses to distinguish, not assumptions of an optimum:

- A: the physical-centre correction scores below a remote winning objective peak, so fractional peak-fit alone cannot recover that state.
- B: native integer basin agrees with an independent same-state refined/oversampled comparison, but fractional fitting is biased.
- C: reference/current-shift evolution places the failure before the current peak decision.

Truth-derived physical-centre residual is a scoring diagnostic; a finite noisy/nonrigid clipped-window objective need not peak there. Distinguish discrete native search maximum, multistart local continuous maximum, sampled fine-grid maximum, and mathematically certified global optimum. Global optimum UNPROVEN by default; no regional exclusion certificate until independently cleared. Native consumed real CCF map is primary for trig interpolation. Do not assume an unsupported half-plane projection/native FFT identity. Preserve oraclev1/v2 failures; oracle revision is coordinated through parent and does not block source capture implementation.

No native/fitter truth input: native working input directory contains only copied noisy.star/noisy.mrcs, no truth/target arrays; C++ observer sees only states already used by the native path. Truth enters separate saved-data analysis only.

## Diagnostic design and data contract

Default off via MC_DIAG_LOCAL_CCF_DIR. Refuse GPU and unsupported scope, require unique nonexisting capture root; exactly2 selected patch contexts created from actual coordinates. Explicit per-call pointer passed into alignPatch, never a global current-patch selector. No arithmetic replacement, Hermitian repair, extra FFT, changing peak/guard/shift/stop or clipping. Buffer copies only; all file writes serial outside OpenMP, with preallocated per-frame buffers and exclusive-create/no overwrite. Failure retains partial data and aborts before normal publication. No failure behavior outside the diagnostic changes.

Capture actual clipped globally aligned float patch samples before FFT; initial and per-iteration entering full/windowed FFT arrays; current cumulative shifts; actual per-iteration reference and sum-of-others; float weights; raw product (explicitly labeled observation-only recomputation if no stored native intermediate exists); actual weighted pre-DC and consumed post-DC spectrum, actual post-IFFT API input and real map; boundary-Hermitian residual measurements without changing any value or claiming internal FFT projection equivalence. Bind dimensions,strides,element/complex precision,byte order,NewFFT normalization/sign,group/frame/time,patch extents and reference identity. Actual float32 data are serialized losslessly; RFLOAT scalars recorded at full precision.

Record native selected integer/tie ordering and count,3×3 neighbourhood,separable candidate,coupled verdict and accepted offsets (no uninitialized outputs on rejection), final raw pre-scale shift, scaled raw shift, frame0 anchor adjustment, actual applied/cumulative shifts and post-shift spectra; per-iteration RMSD/stop/convergence and reported local trajectory/recentering. Rejected coupled uses native unbracketed separable fallback; its offset may exceed[-16,16]. Never clip it or clip M5. All actually selected states, even unexpected/large offsets, remain retained.

## Verification and two-producer budget

Independent exact source review by one reviewer, not author, BEFORE native capture. Notify parent of exact source commit; full CPU build plus minimal relevant existing tests and diagnostic writer/CLI tests may proceed while review runs. No native movie producer pending source review.

At most2 new tiny native producers after review:

1. New diagnostic build, capture OFF, compare to retained noisy UP-only from sealed factorial. Existing comparator (root-normalized aggregate outputs, exact caseSTAR, MRC header/payload/size), exact runtime and raw observations/global trajectory. Old all8 evidence is reused with exact-source limits, not transferred blindly.
2. Same build/input/config, capture ON, compare to that OFF with identical checks. Capture completeness must bind both selected patches/all5 frames/every executed iteration and all arrays/events. No other movie/seed/arm/affine/fullsize/N/GPU/100 producer.

Freeze new source/binary/config/input hashes and run order after build/review, before either producer. Technical exit/hash/source/lease/nonfinite/capture/write/completeness/identity failure stops affected work, preserves artifacts and needs a narrow versioned disposition; no silent producer retry or budget extension. All failed build/test/analysis attempts retained. No scientific estimator intervention is implemented from this task.

cpu64 only, whole-chain CPUs32-47, native/analytic≤2threads, compatible overlapping range leases and mandatory canonical benchmark lease append-open/held, fresh per-job occupancy/affinity/input/binary/scratch checks. Combined scratch≤25GiB, capture payload cap64MiB for the two tiny patches, no jobs stopped. No timing claim; wall/RSS are receipts only. No native device used. No merge/default/qualification/promotion/full100/CUDA-port claim.

After capture use saved states only and the independently revised oracle to diagnose objective/search versus interpolation versus reference/iteration, with coordinate/sign/normalization controls. Return the smallest evidence-supported default-off intervention proposal after diagnosis, or a precise unresolved blocker. All sealed harm, failed hypotheses and UNRUN limits remain unchanged.
