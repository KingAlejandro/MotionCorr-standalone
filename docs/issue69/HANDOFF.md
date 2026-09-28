# Issue #69 — hand-off: known, unfixed, and unrun

Everything here was found by review and **deliberately left unfixed**, either because
it is non-blocking and the round instruction was to document rather than churn, or
because it needs a GPU slot that was never assigned. Nothing in this list is a claim
that it does not matter.

Source frozen at `e191aab`. Latest head is docs-only on top of it.

## A. Not run, and not claimed anywhere

| Layer | Status |
|---|---|
| Bounded CUDA fault matrix (`tests/cuda_fault_matrix.cpp`) | built, linked, interposition verified at relocation level — **never executed** |
| Forced-nonconvergence end-to-end witness for the retry fix | **unrun**; `gpu_plan.md` item 4 |
| Early-binning streaming control (pass criterion 4) | **unrun**; `gpu_plan.md` item 5 |
| Healthy same-backend all-24 CUDA control | **unrun**; `gpu_plan.md` item 6 |
| Any build on a CUDA toolkit older than 12.8 | **unrun** — the `CUDART_VERSION` guards are reasoned, not exercised |
| Pass criterion 3 (retry reprocesses partial even/odd/DW products) | not this task's; #99/#53's completion contract |

No GPU slot was ever assigned to this task and no GPU execution occurred. The bench
lock being free and the devices idle is availability, not authorization.

## B. Known gaps in what the controls can observe

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
7. **The `decisive`-code assertion in `cuda_error_class.cpp` cannot fail** against the
   current implementation — both fatal branches assign a code they have just proven
   poisons. It is a ratchet against a future refactor, not evidence about present
   behaviour, and should not be reported as the latter.

## C. Code items, unfixed

8. **Fatal message can misattribute the location.** `motioncorr_runner.cpp` appends
   `", recorded at <stage>:<line>"` unconditionally. When the *pending* code forced the
   verdict — the exact compound path the P1 fix addresses — it prints the fatal code
   with the location of the earlier benign failure, and `recorded at :0` when nothing
   was recorded. Remedy: emit the clause only when `decision.decisive == recorded`.
9. **`cudaRetryDecisionFor` discards `recorded_cufft`.** Documented and pinned by two
   test rows, but a parameter that is never consulted is a trap for a future reader.
10. **Sticky-first attribution.** A benign early failure supplies the stage and line
    reported for a later unrelated patch failure. The verdict is unaffected after the
    P1 fix; only the attribution can mislead.
11. **Three dead fields** on the per-movie `TrialResult`, all sourced from globals.
12. **`friend struct MotioncorrRunnerTestAccess;`** grants the test access to every
    private member, not just `alignPatch`. Accepted as the minimum hook, but it is a
    permanent test hook in a production header and a precedent for the class.
13. **F6's `cudaGetLastError` residual**: the robust form is returning the failing code
    out of `preparePatchInVram`. Deferred because it widens an interface PR93 also
    edits. **Should become a tracked issue rather than an ADR paragraph.**

## D. Documentation items, unfixed

14. **`RESULTS.md` §5's classifier block quotes a superseded version of
    `cuda-interposition.log`** — stale but true, and it under-claims (the current log
    says `21 classifier cases … [CUDART_VERSION 12080]` plus `13 retry cases`). The
    omitted line is quoted correctly elsewhere in the same file. Refresh next time that
    section is touched.
15. `RESULTS.md` summary row says "all three test binaries linked" — off by one against
    §5's five, and now unevidenced because the regenerated `cuda-compile.log` no longer
    lists the binaries.
16. **`RESULTS.md` never mentions the early-binning control**, though `gpu_plan.md`, the
    PR body and the issue comments all do.
17. ADR "lands near `S`" phrasing — ambiguous rather than false in ADR context.
18. `preprocessed_tu_control.sh` buckets any differing line containing `RelionError(`
    as `__LINE__` metadata, so a changed error *string* would be classified benign.
19. The coordination-file exclusion is in `.git/info/exclude` — clone-local, does not
    travel to a fresh clone.
20. `RESULTS.md` "source hashes on the GPU host match the cpu64 hashes exactly" — true,
    but the GPU log now carries three files against provenance's five.

## E. Integration

**PR93 overlap is a hard conflict on four of four production files.** F1, F2 and F3
must be reconciled with whichever lands first — PR93 hoists the same eight buffers and
the cuFFT plan into a process-static cache, an independent and mutually exclusive fix.
F4, F5, F6, F7, the P1 fix and all three tests are independent. Coordinate with PR108
as well. Do not concatenate two independently reviewed ownership implementations
without validating the combined source.
