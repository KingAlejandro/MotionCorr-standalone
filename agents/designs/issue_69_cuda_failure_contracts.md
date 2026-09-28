# Issue #69 — CUDA failure ownership, error signalling and retry-state contracts

Status: proposed
Base: main `4c952b3f54479653512c4d208e09c9a8c02f3726`
Branch: `round96/69-claude-opus-5`
Scope owner: round96 worker for #69. Related: #50, #66, #82 (merged wrapper leak fix),
#83 (consumes the support result), #99/#53 (completion semantics), PR93 (two
candidate-specific fault controls, does not close this matrix).

This ADR is deliberately narrow. It adds **no allocator framework, no asynchronous
pipeline, no exception/restart framework, no precision change** and makes **no universal
CPU-fallback claim**.

---

## 1. State and error taxonomy

The codebase currently carries one `bool` out of the alignment entry points and that
`bool` has been read, in different places, as three different things. The four states
below are distinct and are named here so the rest of the document can be precise.

| State | Meaning | How it is signalled at the pinned base | Correct caller response |
|---|---|---|---|
| **completed / converged** | Alignment ran to completion and the RMSD test passed | `cudaAlignPatchDevice` / `alignPatch` return `true` | Publish shifts |
| **completed / nonconverged** | Alignment ran to completion; the RMSD test did not pass within `max_iter` | return `false` | Verdict is final for that input. Upstream CPU behaviour is to skip the patch |
| **recoverable resource failure** | An owned allocation, plan, copy or memset failed *before or without* producing a result; the device context is still usable | `CudaMovieSession::*` return `false` (file-local `HANDLE_ERROR` returns false); `preparePatchInVram` → `prep_ok == false` | Release owned resources, then either use a genuine alternative path or fail the movie cleanly |
| **fatal device execution error** | Kernel fault, ECC error, illegal address, destroyed/uninitialised context. The context is *poisoned*: every later CUDA call in this process returns the same sticky error | `cuda_alignpatch.cu` uses the `cuda_settings.h` `HANDLE_ERROR`, which is `CRITICAL(ERRGPUKERN)` → `REPORT_ERROR` → `throw RelionError` | Fail the movie cleanly. **Do not** retry on the same context and **do not** reset the device — the device may be shared with another process |

**A nonconvergence boolean is not an error channel.** Rows 2 and 3 are different
questions with different correct answers, and `motioncorr_runner.cpp:2103` currently
answers them identically.

The publication point for the whole movie is unchanged and already correct: a movie that
throws is caught at `motioncorr_runner.cpp:626`, recorded in `failed_movies`, and the job
withholds the joint STAR/PDF and exits nonzero at `:640-645`. This ADR does not touch
that and does not need to.

---

## 2. Owned versus borrowed buffers, per stage

"Owned" = this frame allocated it and must release it on every exit path.
"Borrowed" = supplied by the caller; releasing it here is a bug.

### `CudaMovieSession` (`cuda_movie_session.cu`) — session lifetime

| Buffer | Owner | Lifetime | Released by |
|---|---|---|---|
| `d_Iframes`, `d_Fframes`, `d_Isum`, `d_gain` | session | movie | `release()`, and `releasePreprocessingBuffers()` for `d_gain`/`d_Isum` |
| `plan_r2c`, `plan_c2r`, `d_fft_work`, `d_inverse_tile` | session | movie | `release()` |
| `plan_patch_r2c`, `d_Ipatches`, `d_group_start`, `d_group_size` | session | movie, cached across patches | `release()` |
| `StatsScratch`, `CollectScratch`, `DefectScratch` | method | one call | RAII destructor — already correct |
| `raw_frames`, `gain_ref`, `unaligned_sum`, `Isum`, `Fframes`, `Iframes` arguments | caller | — | never here |

The session is a `std::unique_ptr` local to `executeOwnMotionCorrection`, so its
destructor runs on every exit from the movie, including an exception. Session-scope
buffers therefore do **not** need per-method unwinding; they need their bookkeeping to
stay truthful so `release()` frees each pointer exactly once. Findings F3 and F4 below
are violations of that, not leaks.

### `cudaAlignPatchDevice` (`cuda_alignpatch.cu`) — call lifetime

| Resource | Owner |
|---|---|
| `d_Fref`, `d_weight`, `d_Fccs`, `d_Iccs`, `d_cur_xshifts`, `d_cur_yshifts`, `d_shiftx`, `d_shifty` | this call — owned |
| `plan_c2r` | this call — owned |
| eight `cudaEvent_t` | this call — owned |
| `d_Fframes_in` | **borrowed** — the resident `d_Fframes`, or the caller's patch scratch. Modified in place (Fourier phase shifts) and never freed here |
| `xshifts` / `yshifts` | **borrowed and mutated** — accumulated into, see §3 |

### `cudaAlignPatch` (host wrapper)

Owns `d_Fframes` (its own staging copy). Borrows `Fframes`, which it writes back to only
when `is_global`.

### `cuda_realspace_dw.cu`

Already conforms after #82: every wrapper allocation is registered with
`CudaMemoryCleanup` immediately after a successful `cudaMalloc` and before any use, and
events/plans use `CudaEventCleanup`/`CufftPlanCleanup`. This ADR uses that file as the
reference pattern rather than inventing a new one.

### `cuda_fft_prep.cu`

Named in Deliverable 1, audited, and **no change required** — recorded here rather than
left as an unexplained omission.

| Function | Owned | Borrowed | Verdict |
|---|---|---|---|
| `cudaForwardFFT2D` | `d_real`, `d_comp`, `plan_r2c` | `Iframes`, `Fframes` | Conforms. Each allocation is registered with `CudaMemoryCleanup` on the statement after it succeeds; the two early `return false` paths (`d_comp` allocation, `cufftPlanMany`) exit before the failing resource exists, and the already-registered `d_real` unwinds |
| `cudaInverseFFT2D` | `d_comp`, `d_real`, plan, and the module-static frame cache | caller images | Conforms; the static cache is released through its own cleanup |
| `cudaPreparePatch` | `d_Ipatches`, `d_Fpatches`, `d_group_start`, `d_group_size`, `plan_batched` | `Iframes`, `Fpatches`, the module-static cached frames | Conforms; all four buffers registered immediately, plan taken immediately after creation |

Unlike `cuda_alignpatch.cu`, this file **does** define its own returning-`false`
`HANDLE_ERROR`, so its error paths do not leave by exception — which is why the same
defect class did not arise here.

---

## 3. Shift-state contract, and what the retry actually does

Both alignment implementations share one contract that is nowhere written down:

> `alignPatch` / `cudaAlignPatchDevice` **accumulate** into `xshifts`/`yshifts`
> (`xshifts[i] += cur_xshifts[i]`) and **never read** the incoming values. The caller is
> responsible for the invariant that the incoming shifts already describe the state of
> the supplied `Fframes`.

At `4c952b3f` the local-patch retry breaks that invariant:

```
motioncorr_runner.cpp:2072   std::vector<RFLOAT> local_xshifts(n_groups), local_yshifts(n_groups);   // zero
motioncorr_runner.cpp:2099   converged = alignPatchDevice(d_patch_fcomplex_buffer, ..., local_xshifts, local_yshifts, ...);
motioncorr_runner.cpp:2103   if (!converged)
motioncorr_runner.cpp:2152       converged = alignPatch(Fpatches, ..., local_xshifts, local_yshifts, ...);
```

The first attempt leaves `S1` in the vectors. Its Fourier phase shifts were applied to
`d_patch_fcomplex_buffer` only — the wrapper's own scratch, rewritten wholesale by the
next `preparePatchInVram`. The resident real frames `d_Iframes` and the host `Iframes`
are **not** modified by a patch attempt. The second attempt therefore re-extracts the
same unshifted patch data and accumulates an independent `S2` on top of `S1`, so the
published local trajectory is `S1 + S2` — approximately twice the true local shift for
that patch.

Because the first attempt modified nothing except the two shift vectors, **resetting
those two vectors is a complete restoration** of everything it touched. This is the rare
case where the "restore every input/output the first attempt modified" requirement is
fully discharged by a two-line reset, and that is checkable from the source rather than
assumed.

### Decision: reset-then-retry, not skip

Two policies close the defect.

- **(A) Reset the shift vectors before the fallback attempt.** Chosen.
- **(B) Skip the patch when a *completed* device attempt did not converge**, matching the
  CPU-only upstream behaviour where nonconvergence means `continue`, and keep the
  fallback only for `prep_ok == false`. Rejected for now.

(A) is chosen because it has the smaller behavioural delta: no patch that contributes an
observation today stops contributing, so the polynomial fit's observation count cannot
newly drop below `n_params` and fail a movie that currently succeeds. (B) is probably the
more faithful long-run semantics — the two implementations run the same algorithm on the
same data, so a patch the device declares nonconverged will almost always be declared
nonconverged by the host too, which makes the retry redundant work — but establishing
"almost always" needs the measured nonconvergence rate on real data, which this round has
not run. (B) is recorded as the follow-up, gated on that evidence.

Global alignment (`motioncorr_runner.cpp:1983`) has no retry and discards the convergence
verdict, matching upstream. It is out of scope here and is left alone.

---

## 4. Findings and the change each one justifies

| ID | Location at `4c952b3f` | Defect | Change |
|---|---|---|---|
| F1 | `cuda_alignpatch.cu` `cudaAlignPatchDevice` | 8 buffers + 1 plan + 8 events freed only on the straight-line success path; every error leaves by `throw` and skips it. Leak accumulates across movies because `run()` continues after a per-movie `RelionError`. The cleanup block is also not failure-safe against its own first failing `cudaFree` | Register each resource with the existing `CudaMemoryCleanup` / `CufftPlanCleanup` / `CudaEventCleanup` immediately after it is created. Make the success path release through the same RAII objects so there is exactly one release mechanism |
| F2 | `cuda_alignpatch.cu` `cudaAlignPatch` | Owned staging buffer `d_Fframes` leaks on upload, device-call or copyback failure | Same helper, registered immediately after `cudaMalloc` |
| F3 | `cuda_movie_session.cu` `preparePatchInVram` | Free-without-null: a failed realloc can leave a freed non-null pointer for `release()` to free again, and can leave `sz_cached_Ipatches` / `cached_ngroups_alloc` describing buffers that no longer exist | Null the pointer and clear its size/count bookkeeping *before* the reallocation attempt, so any failure exit leaves "no buffer, no claim" |
| F4 | `cuda_movie_session.cu` `releasePreprocessingBuffers` | `HANDLE_ERROR(cudaFree(p)); p = nullptr;` — a failing free returns with `p` still non-null, and `release()` frees it again | Clear the pointer first, free the saved copy, then report |
| F5 | `motioncorr_runner.cpp:2072-2152` | Retry accumulates a second independent correction into the same shift vectors | Reset both vectors before the fallback attempt, with the invariant stated in a comment |
| F6 | `motioncorr_runner.cpp:2079-2103` | A poisoned context is retried as though it were an ordinary allocation miss | Classify the pending CUDA error after a failed device patch attempt. On a sticky/unrecoverable code, fail the movie cleanly via `REPORT_ERROR`; otherwise allow the existing fallback. No `cudaDeviceReset`, no interference with other processes or devices |

### Sticky error set used by F6

The authoritative list is the `switch` in
[`src/acc/cuda/cuda_error_class.h`](../../src/acc/cuda/cuda_error_class.h), which also
records why `cudaErrorUnsupportedPtxVersion` is *excluded* — it is a deterministic
toolchain mismatch that will fail the alternative path too, but it does not make
unrelated calls fail, which is what "poisoned" means here. An earlier draft of this ADR
listed a set that did not match the code; the list now lives in exactly one place, is
`inline` in a header rather than in an anonymous namespace so it can be unit tested, and
is covered by `tests/cuda_error_class.cpp`.

Everything else — notably `cudaErrorMemoryAllocation` — is treated as recoverable and
keeps today's behaviour. The classifier is a pure predicate over an error code: it makes
no CUDA call, never calls `cudaDeviceReset()`, and never touches state belonging to
another process or another device.

**Known weakness, deliberately accepted for now.** The call site obtains the code with
`cudaGetLastError()`, which reports the last error recorded on this thread rather than
the one the failing stage hit — the session's own file-local `HANDLE_ERROR` may already
have consumed it, and the host-side buffer guard records none at all. The *decision* is
still sound, because the question being asked is "is this context usable", and a sticky
code pending from anywhere answers it. But the *attribution* is not reliable, so the
message says where the state was observed rather than what caused it, and prints
explicitly when nothing is pending instead of "no error". The robust fix is to return
the failing code out of `preparePatchInVram`; that widens an interface shared with
other in-flight work, so it is recorded here as a follow-up rather than taken now.

---

## 5. Verification plan and its honest boundaries

### Runnable without a GPU

- `tests/test_patch_retry_state.cpp` — a device-free control that characterises the
  accumulate contract of §3 against the real `MotioncorrRunner::alignPatch`. It forces
  nonconvergence with `max_iter = 1` on a synthetic patch carrying a known shift, then
  re-enters with the same vectors and with reset vectors, and asserts that the
  non-reset arm lands near `2S` while the reset arm lands near `S`.
  **This is a contract characterisation, not whole-application validation**: the
  production retry it justifies is inside `#ifdef _CUDA_ENABLED` and cannot execute in a
  CPU-only build. It proves the premise of F5 on production code; it does not prove the
  end-to-end fix.
- The 13 existing CPU CTests, as a no-regression gate on the shared runner file.

### Requires a GPU slot — prepared, not run

`tests/cuda_fault_matrix.cpp`, extending the `--wrap=cudaMalloc/cudaFree/cudaMemcpy`
link-interposition already used by `tests/cuda_wrapper_upload_failure.cpp` (and matching
PR93's separate LD_PRELOAD shim in spirit). Fault switches are test-only, live in the
test translation unit, and are never compiled into `motioncorr` — so no production fault
switch exists and none can be active during timing.

Matrix: session real / Fourier / sum / gain allocation; cuFFT create, plan and work-area
attachment; patch scratch allocation; H2D and D2H; kernel launch and completion;
reconstruction allocation. For each: movie and stage identified in the log, exit
mechanism, owned allocations released, borrowed inputs preserved, requested-product
state, and retry behaviour. Plus failure *after* an earlier optional product was written,
and several successive movies to expose leaks and stale cache state.

Also requiring a slot: a forced-nonconvergence end-to-end witness for F5, and the healthy
same-backend 24-movie control showing ordinary CUDA output is unchanged.

### What will not be claimed

- No pass for any layer that has not run.
- Same-backend equality is not scientific equivalence and not a CPU/RELION Gate-2 pass.
- Clean nonzero failure is the supported contract where safe recovery is unavailable; it
  will not be described as a successful CPU fallback.
- F5 changes behaviour on purpose in the nonconvergence case. Pre-fix and post-fix
  outputs are *not* expected to be identical there, and an identity assertion would be
  the wrong test. Healthy-path outputs are expected to be identical and that is what the
  same-backend control checks.
