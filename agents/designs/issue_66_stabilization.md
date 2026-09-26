# Architectural Design Specification: CPU/CUDA stabilization

- Issue: #66; related #12, #20, #36, #50, #53, #58–#61.
- Baselines: main `3e3a196`; CUDA `0c7d68f`.
- Architect: independent MotionCorr architecture review, 2026-09-26.
- Authorization: Alex requested the assessment recommendations be implemented, with relative image RMSE retained as a diagnostic rather than the sole acceptance decision.
- Status: approved for implementation by the integrating agent under that authorization. Independent exact-candidate review remains required.
- Milestone: integrated **experimental** native CUDA candidate; wider support requires the declared unrun cases.

## 1. Scope and invariants

Fix demonstrated metadata, failure, RNG-cache and output-ordering faults. Repair validation verdicts. Preserve native CUDA residency and simplify only proven redundant state/lifetimes. Keep FFT engines, weighting formulas, interpolation precision, normal reduction order, and numerical defaults. Explicit correctness exceptions are Gaussian cache reset, late-binning sum order, original-pixel exported motion units and CPU-order tied-peak selection. Unaffected outputs must remain exact.

No hybrid FFTW integration, new smoothing/backend, multistream pipeline, general allocator framework or automatic whole-movie CPU retry in this package.

## 2. Shared runner contract

Keep filename, optics and input pre-exposure associated during pending-list filtering and original-list aggregation. Maintain separate pending and original pre-exposure vectors to mirror the existing filename vectors; do not add the command-line offset twice.

Reject nonpositive frame grouping, EER grouping and thread counts during option validation. Accumulate native false-return failures, retain successful per-movie artifacts, and throw before joint success STAR/PDF generation if any requested movie failed. Existing decoder/numerical exceptions remain fail-fast. An already completed movie skipped intentionally is not a failure.

Resume requires the movie metadata written after successful correction plus all requested numerical products. In particular, EVN alone is not completion: even/odd files may precede dose-weighted output. Check readable/structurally complete requested outputs without reprocessing all image pixels. Preserve existing completed files; no broad deletion. Tomography's existing full-row aggregation requirement is unchanged; test its complete interrupted/resumed run separately from SPA `--do_at_most`.

Late binning sums aligned full-size frames before binning the requested final sums, including odd/even. Extract the existing corrected CUDA-branch order onto CPU main.

With early binning factor b, runtime polynomial coefficients remain in binned pixels, while exported local displacement must share global shifts' original-pixel units. Reproduce the mismatch, then scale only a serialized copy of the native polynomial model. Do not mutate the live model or double-scale on repeated saves.

## 3. CUDA contract and memory

Use existing scoped cleanup for wrapper-owned allocations, immediately after allocation; borrowed pointers remain borrowed. Keep safe existing fallbacks, but fail nonzero with a movie/stage diagnostic when valid recovery is unavailable. Do not promise transparent CPU completion for fatal CUDA alignment errors. No successful movie metadata on failure, and resume must retry incomplete products.

Equal finite CCF maxima choose the lowest CPU raster index before unchanged subpixel interpolation. Unique maxima are unchanged.

Free session gain and initial-sum storage only after preprocessing/sparse repair, retaining host data needed by existing recovery. Remove unreachable tail plans with batch=1 unchanged. Share duplicated polynomial expansion without changing types, casts or evaluation order.

Detailed timing may be disabled independently of a cheap stable backend/stage marker. Preserve required synchronization/error boundaries and session per-frame workspace synchronization. Profiling log labels distinguish small shift uploads, function-local scratch and whole-process allocation peaks.

## 4. Explicit backend comparator

Keep old `exact`/`relaxed` profiles and historical results unchanged. Add `--gate backend`, requiring complete image+STAR pairs, finite values, geometry/schema/static metadata, and:

| Check | Required limit |
|---|---:|
| Absolute image RMSE | 0.020 |
| Maximum absolute pixel error | 5.0 |
| Global trajectory vector RMS | 0.02 pixels |
| Maximum per-axis global shift difference | 0.05 pixels |
| Static STAR discrepancies | 0 under existing normalization rules |
| Relative image RMSE | report at 0.001 with `blocking: false` |

Require a successful parseable process log for backend candidate acceptance, or an explicit run-status contract in the invoking harness; the comparator must not invent evidence of execution. Report historical relative diagnostic PASS/FAIL and new profile verdict separately. Comparator success alone does not approve a release.

PR #63 must enforce its applied-image self-consistency witness at the existing 1e-4 threshold, enforce declared thread/dose invariance and reject nonfinite metrics. Add explicit CPU/CUDA selection and verify the requested backend actually executed. Keep the noisy characterization failure visible. Do not adopt PR #64's two-metric proposal as a complete replacement gate.

## 5. Ownership and commit boundaries

- CPU worker: runner/header, narrowly necessary motion-model serialization, RNG port, focused CPU tests and corresponding CMake registrations. Separate RNG, selected-row metadata, resume/failure, late-bin and exported-unit commits.
- CUDA worker: `src/acc/cuda/`, focused CUDA controls, helper interfaces. Root alone integrates requested runner call sites. Separate leaks, ties, storage lifetime, dead state, coefficient helper and profiling commits.
- Truth worker: PR #63 tools/fixtures/docs only. No comparator, CMake, workflow or production edits.
- Root: comparator/policy, CI, evidence/report corrections, issues/PRs and integration. Scheduler follows shared-runner fixes in its own branch.

All workers use isolated worktrees and preserve others' work. Production source and large evidence are separate commits where practical.

## 6. Verification and release evidence

Focused tests reproduce the old failure then establish corrected behavior: resumed different exposures (including non-prefix completion), missing/truncated optional output, good/failed movie mixtures, invalid options, late-bin dose/noDW/odd/even, early-bin serialized field roundtrip, Gaussian odd-draw reseeding, CUDA upload failures and tied peaks. Fix-specific outputs may change; unaffected same-backend outputs must be exact.

Candidate evidence includes explicit native CUDA execution; declared global/local/nonsquare/realistic known-motion cases; repeat/batch/shard/resume equality on all 24 tutorial movies; frame grouping/selection, binning and output variants; failure behavior; exact source/binary/input/configuration hashes; paired same-host timing and peak memory with measurement scope stated. Reuse scientific artifacts only for proven equivalent outputs. Retain historical Gate 2 failures and PR #65's single-collection limits.

CI must cover stacked PRs, required comparator/truth controls and CUDA compilation, clearly distinguishing compilation from hardware execution. Do not silently skip required suites for missing Python dependencies.

CPU-only builds/validation use cpu64 with at most eight build jobs after load inspection. GPU work prefers dedicated SCARF allocations, serialized by the root. Shared 4GPUs work retains total affinity 96–103 and one benchmark at a time; defer around colleagues' jobs and leave llama untouched.
