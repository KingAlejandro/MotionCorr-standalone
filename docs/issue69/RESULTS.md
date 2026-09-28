# Issue #69 — results

Branch `round96/69-claude-opus-5`, base main `4c952b3f54479653512c4d208e09c9a8c02f3726`.
Contract and rationale: [`agents/designs/issue_69_cuda_failure_contracts.md`](../../agents/designs/issue_69_cuda_failure_contracts.md).
GPU work prepared but not run: [`gpu_plan.md`](gpu_plan.md).

## Summary of what ran, and what did not

| Layer | Status |
|---|---|
| CPU build, base and candidate, Release `-O3 -DNDEBUG` | ran, both clean |
| CPU CTest, base 13/13, candidate 14/14 | ran, all passed |
| Patch-retry shift-state contract control | ran, passed |
| Same-backend CPU output, base vs candidate, with negative control | ran, identical |
| CPU-visible translation-unit identity, with negative control | ran, only `__LINE__` metadata differs |
| CUDA compile of the changed `.cu` and the new fault matrix | **queued behind `/tmp/motioncorr-bench.lock`, not yet finished** |
| Bounded CUDA fault matrix | **NEEDS_GPU, not run** |
| Forced-nonconvergence end-to-end witness | **NEEDS_GPU, not run** |
| Healthy same-backend 24-movie CUDA control | **NEEDS_GPU, not run** |

No pass is claimed for anything in the second group.

## Provenance

Host `cpu64` / `small-refmac-machine`, 64 cores, cores 32-63 via top-level
`taskset -c 32-63`, serialised under `flock /tmp/motioncorr-issue96-cpu-validation.lock`,
`OMP_NUM_THREADS=8`, build `-j8`.

```
g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cmake version 4.4.3
Python 3.12.3
CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp
```

`-DCMAKE_BUILD_TYPE=Release` was passed explicitly and the resulting `flags.make` was
read back, because an unqualified configure in this project builds `-O0`.

Source, input and binary hashes: [`evidence/cpu-provenance.txt`](evidence/cpu-provenance.txt).
Fixture `test-data/synthetic/synthetic_movie.tiff`
`95b5f0d37d481355b8abe30f7380c33d9ea173a87bec6e8fc3e567c057622bd4`.

## 1. CPU test suites

[`evidence/cpu-ctest-base.log`](evidence/cpu-ctest-base.log),
[`evidence/cpu-ctest-candidate.log`](evidence/cpu-ctest-candidate.log),
[`evidence/cpu-build-and-ctest.log`](evidence/cpu-build-and-ctest.log).

Base: 13/13 passed. Candidate: 14/14 passed — the same 13 plus the new `PatchRetryState`.
Both configured and built with exit 0.

## 2. Patch-retry shift-state contract

[`evidence/patch-retry-state.log`](evidence/patch-retry-state.log).

```
  converged reference          ( +0.000, +0.000) ( -2.637, +1.755) ( +3.394, -2.198) ( -1.846, +3.041)   |v| = 6.2485
  max |recovered + truth| = 0.0630 px  (converged=yes)

  attempt 1 (S1)               ( +0.000, +0.000) ( -4.367, +3.041) ( +3.594, -2.307) ( -3.378, +4.726)   |v| = 8.9615
  arm A: reset (S2)            ( +0.000, +0.000) ( -4.367, +3.041) ( +3.594, -2.307) ( -3.378, +4.726)   |v| = 8.9615
  arm B: no reset (S1+S2)      ( +0.000, +0.000) ( -8.734, +6.081) ( +7.189, -4.615) ( -6.756, +9.452)   |v| = 17.9231
  |arm A| = 8.9615   |arm B| = 17.9231   ratio B/A = 2.0000
  max |armA - S1|              = 0.000e+00 px
  max |armB - (S1 + armA)|     = 0.000e+00 px
```

Read in order: the estimator recovers the applied displacement to 0.063 px when it is
allowed to converge, so the fixture is sound. At `max_iter=1` it cannot converge, which
is the state the resident CUDA path's fallback reacts to. The retry, given identical
input, re-derives *exactly* the same estimate — `max |armA - S1| = 0` — so it is not
refining the first attempt, it is repeating it. Re-entering without resetting the shift
vectors therefore publishes their exact sum, twice the single estimate.

**What this does and does not establish.** It establishes the premise of the fix on
production code with no device involved: `alignPatch` accumulates into the caller's
vectors and does not re-derive them. It does **not** validate the production retry
end-to-end — that code is inside `#ifdef _CUDA_ENABLED` and cannot execute in a
CPU-only build. The end-to-end witness is item 4 of `gpu_plan.md` and has not run.

## 3. Same-backend CPU output

[`evidence/cpu-same-backend.log`](evidence/cpu-same-backend.log). Base and candidate
binaries on the synthetic fixture with the invocation
`tests/test_synthetic_regression.py` uses.

10 files compared, 1 MRC image, 262,144 pixels, **0 differing**. The MRC payload and
the first 224 header bytes are byte-identical; the label block differs only by the
creation timestamp, which is never reproducible. STAR, EPS and log files are identical
after substituting each arm's own output root, which both arms necessarily write into
their own products. The four PDFs are reported but not compared, because ghostscript
stamps a creation date; that known PDF difference is preserved, not hidden.

The comparison carries a negative control: one pixel bit and one STAR character are
perturbed in a copy of the candidate output and the comparator is required to report
**exactly** those two files. It reported exactly two. A comparison that cannot fail
would prove nothing.

## 4. Why the CPU binaries differ, and why that is not a behaviour change

`motioncorr` base `cb1e1cb1…`, candidate `9dd05f93…`. Every change in this branch to
`motioncorr_runner.cpp` is inside `#ifdef _CUDA_ENABLED`, so a CPU-only build should
contain no new code — but the binaries are not identical, and a hash difference left
unexplained is exactly the kind of thing that later gets waved away.

[`evidence/cpu-preprocessed-identity.log`](evidence/cpu-preprocessed-identity.log)
settles it. Preprocessing both trees' `motioncorr_runner.cpp` with the same flags and
no CUDA, stripping line directives and normalising the source root, leaves a
75,615-line translation unit whose **entire** difference is:

- one added line, `friend struct MotioncorrRunnerTestAccess;`, which emits no code, and
- ten `__LINE__` values inside `RelionError` constructions, shifted because the guarded
  blocks moved the following lines down.

No executable statement changed. That accounts for the binary difference completely,
and the comparison has its own negative control: an injected line is detected.

## 5. Findings fixed

Against `4c952b3f`; full detail in the ADR.

| ID | Defect | Where |
|---|---|---|
| F1 | Eight device buffers, a cuFFT plan and eight events leaked on every error, because every error macro in the file throws and skipped the straight-line cleanup; the cleanup block was also not failure-safe against itself | `cuda_alignpatch.cu` `cudaAlignPatchDevice` |
| F2 | Owned staging buffer leaked on upload, device-call or copyback failure — the class #82 fixed elsewhere, in the wrapper #82 did not cover | `cuda_alignpatch.cu` `cudaAlignPatch` |
| F3 | Patch cache could hold a freed non-null pointer for `release()` to free twice, or a stale size/count describing a buffer that no longer exists | `cuda_movie_session.cu` `preparePatchInVram` |
| F4 | Pointer cleared after the free, so a failing `cudaFree` left it set for `release()` to free again | `cuda_movie_session.cu` `releasePreprocessingBuffers` |
| F5 | The local-patch retry accumulated a second independent correction, publishing roughly twice the true local shift | `motioncorr_runner.cpp` local-patch block |
| F6 | A poisoned context was retried as though it were an ordinary allocation miss, by a path that dispatches CUDA again | `motioncorr_runner.cpp` local-patch block |

## 6. Limitations, stated rather than worked around

- The fault matrix, the end-to-end retry witness and the 24-movie CUDA control have not
  run. Nothing here should be read as evidence about them.
- The CUDA sources in this branch had not finished compiling when this was written; the
  compile is queued behind the bench lock. Until it completes, the `.cu` changes are
  reviewed but not built.
- The fault matrix cannot synthesise a genuinely poisoned context, so F6's branch will
  not be exercised by a real fault even once a slot is assigned.
- F5 changes behaviour on purpose when a device patch attempt does not converge.
  Pre-fix and post-fix outputs are not expected to be identical there.
- Same-backend equality is not scientific equivalence and not a CPU/RELION Gate-2 pass.
- Clean nonzero failure is the supported contract where safe recovery is unavailable.
  It is not a successful CPU fallback and is not described as one.
