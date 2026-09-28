# Issue #69 — hand-off: known, unfixed, and unrun

Everything here was found by review and **deliberately left unfixed**, either because
it is non-blocking and the round instruction was to document rather than churn, or
because it needs a GPU slot that was never assigned. Nothing in this list is a claim
that it does not matter.

Source frozen at `e191aab`. Latest head is docs-only on top of it.

## A. Run natively on GPU2 (28 Sep), and what is still not run

| Layer | Status |
|---|---|
| CUDA build of every fix, incl. P1b/P2 | **ran** — 0 compile errors, 0 warnings in changed files |
| Bounded CUDA fault matrix | **ran** — 132 trials, 0 failures, 0 leaks, 0 damaged inputs |
| Device-free predicate / session-state / capacity suites | **ran** — 43 cases, 0 failures |
| Wrapper upload-failure regression | **ran** — passes |
| Healthy all-24 same-backend CUDA control | **ran** — 24 images, 341,735,520 pixels, 0 differing, negative control able to fail |
| Forced-nonconvergence retry witness | **ran, and F5 DID NOT REPRODUCE** — see below |
| Early-binning streaming control | **UNRUN** — no valid bin factor for this geometry; every arm errors identically |
| Genuine poisoned context (illegal address / ECC) | **UNRUN** — cannot be synthesised. P1/P1b/P1c are exercised by *injected error codes* and session-state sequences only; no hardware was ever poisoned or reset |
| Any build on a CUDA toolkit older than 12.8 | **UNRUN** — the `CUDART_VERSION` guards are reasoned, not exercised |
| Pass criterion 3 (retry reprocesses partial even/odd/DW products) | not this task's; #99/#53's completion contract |

**F5 is source-demonstrated and CPU-demonstrated but not natively reproduced.** Across
2,472 patch alignments on 24 movies at `max_iter` 1/2/3/4 — including `max_iter=1` where
all 1224 device alignments reported nonconvergence — base and candidate output was
byte-identical. Both attempts share the same `max_iter` on the same data, so the retry
almost always fails to converge too and `if (!converged) continue` skips the patch in
both arms, discarding the accumulated shift before it reaches the polynomial fit. The
double count needs the retry to converge where the device did not, i.e. the float/double
borderline near the 0.5 px tolerance. **Consequence for whoever picks this up: the
skip-on-nonconvergence alternative rejected in the ADR is now the better-looking
option**, because the retry it removes essentially never changes the outcome.

No timing was recorded or claimed: #53 was running concurrently on GPU0/1 throughout.

## B. Known gaps## B. Known gaps in what the controls can observe

1. **The predicates are tested; the paths are not.** `cudaErrorPoisonsContext` and
   `cudaRetryDecisionFor` have 34 unit cases between them. The real resident
   nonconvergence path, a genuinely poisoned context, and asynchronous execution
   failure are not exercised by anything in this branch.
2. **The fault matrix never enters `motioncorr_runner.cpp`.** It drives
   `CudaMovieSession` and `cudaAlignPatchDevice` directly, so F5, F6, F7 and the P1
   fix get no coverage from it even once a slot is assigned.
3. **cuFFT's internal workspace** is allocated inside `libcufft`, below the interposed
   `cudaMalloc`, so it is outside the matrix's leak accounting.
4. **`reloc_check.sh`'s "0 bypasses"** counts direct `call`/`jmp` to a `@plt` entry and
   assumes a shared CUDA link. Register-indirect calls are not matched, and production
   inlined into the test's own functions is exempted with them.
5. **Destroy-failure undercount**: the destroy wrappers erase only on success, so a
   failed destroy followed by handle recycling could collapse two lifetimes into one
   set entry. Needs a real runtime failure to reach.
6. **Deliverable 1's Fourier-input capture** on a forced-nonconverged patch is argued
   from source, not captured. Needs a device.
7. ~~**The P1c fallback-boundary plumbing has no automated coverage.**~~ **CLOSED** by
   `tests/run_fallback_boundary_control.sh` + `tests/cuda_fault_inject_shim.cpp`:
   production binary, injected poisoning code at `cudaPreparePatch` (ordinal 35,
   `cuda_fft_prep.cu:344`), fix refuses and fails closed, mutant without the recording
   does not refuse. **Still injected-code scope, not a genuine fault.** Original text: The `failure`
   out-parameter, `cuda_fft_prep.cu`'s recording handlers and the runner's post-prep
   check are covered by compilation and review only. The control added with them tests
   the *predicate* given a correctly-carried status and would pass against the pre-fix
   source; the fault matrix never touches `cudaPreparePatch`; the healthy run only takes
   the success path. **Closing this needs a control that drives `cudaPreparePatch` with
   an injected fault** — the `--wrap` harness could do it, since that helper's
   allocations and copies already pass through the interposed primitives
   (`cudaMalloc`, `cudaMemcpy`, `cufftPlanMany`, `cufftExecR2C`, all already wrapped).
   **One detail a future implementer must not miss:** the wrappers currently return only
   *recoverable* codes (`cudaErrorMemoryAllocation`, `cudaErrorInvalidValue`,
   `CUFFT_ALLOC_FAILED`). Injecting those exercises the recording path and the PERMITTED
   branch but **not** the FATAL refusal, which needs a poisoning code. The injected code
   set must be widened, not just an ordinal added.
8. **The `decisive`-code assertion in `cuda_error_class.cpp` cannot fail** against the
   current implementation — both fatal branches assign a code they have just proven
   poisons. It is a ratchet against a future refactor, not evidence about present
   behaviour, and should not be reported as the latter.

## C. Code items, unfixed

9. ~~**Fatal message can misattribute the location.**~~ **Fixed** in the P1b change: the
   message now names the stage that latched the poisoning code, or says the code was
   pending with no stage. Original text retained for traceability: `motioncorr_runner.cpp` appends
   `", recorded at <stage>:<line>"` unconditionally. When the *pending* code forced the
   verdict — the exact compound path the P1 fix addresses — it prints the fatal code
   with the location of the earlier benign failure, and `recorded at :0` when nothing
   was recorded. Remedy: emit the clause only when `decision.decisive == recorded`.
10. **`cudaRetryDecisionFor` discards `recorded_cufft`.** Documented and pinned by two
   test rows, but a parameter that is never consulted is a trap for a future reader.
11. **Sticky-first attribution.** A benign early failure supplies the stage and line
    reported for a later unrelated patch failure. The verdict is unaffected after the
    P1 fix; only the attribution can mislead.
12. **Three dead fields** on the per-movie `TrialResult`, all sourced from globals.
13. **`friend struct MotioncorrRunnerTestAccess;`** grants the test access to every
    private member, not just `alignPatch`. Accepted as the minimum hook, but it is a
    permanent test hook in a production header and a precedent for the class.
14. **F6's `cudaGetLastError` residual**: the robust form is returning the failing code
    out of `preparePatchInVram`. Deferred because it widens an interface PR93 also
    edits. **Should become a tracked issue rather than an ADR paragraph.**

## D. Documentation items, unfixed

15. **`RESULTS.md` §5's classifier block quotes a superseded version of
    `cuda-interposition.log`** — stale but true, and it under-claims (the current log
    says `21 classifier cases … [CUDART_VERSION 12080]` plus `13 retry cases`). The
    omitted line is quoted correctly elsewhere in the same file. Refresh next time that
    section is touched.
16. `RESULTS.md` summary row says "all three test binaries linked" — off by one against
    §5's five, and now unevidenced because the regenerated `cuda-compile.log` no longer
    lists the binaries.
17. ~~**`RESULTS.md` never mentions the early-binning control.**~~ **Fixed** — it is now
    in the summary table and §5d. Retained for traceability; a hand-off list carrying an
    already-fixed finding is itself a defect, and this one was caught by review.
18. ADR "lands near `S`" phrasing — ambiguous rather than false in ADR context.
19. `preprocessed_tu_control.sh` buckets any differing line containing `RelionError(`
    as `__LINE__` metadata, so a changed error *string* would be classified benign.
20. The coordination-file exclusion is in `.git/info/exclude` — clone-local, does not
    travel to a fresh clone.
21. `RESULTS.md` "source hashes on the GPU host match the cpu64 hashes exactly" — true,
    but the GPU log now carries three files against provenance's five.

## E. Integration

**PR93 overlap is a hard conflict on four of four production files.** F1, F2 and F3
must be reconciled with whichever lands first — PR93 hoists the same eight buffers and
the cuFFT plan into a process-static cache, an independent and mutually exclusive fix.
F4, F5, F6, F7, the P1 fix and all three tests are independent. Coordinate with PR108
as well. Do not concatenate two independently reviewed ownership implementations
without validating the combined source.
