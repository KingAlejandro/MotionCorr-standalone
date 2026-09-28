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
| Same-backend CPU output, base vs candidate, with negative control | ran, identical — but see §3: this is a build-hygiene control, not a behavioural one |
| CPU-visible translation-unit identity, with negative control | ran, only `__LINE__` metadata differs |
| CUDA error classifier unit test (device-free) | ran, 21 cases, 0 failures, CUDART 12080 |
| Retry-verdict controls, incl. cleared-last-error fatal (device-free) | ran, 11 cases, 0 failures |
| CUDA compile of the changed sources and all three test binaries | ran, clean, zero warnings in changed files |
| Relocation-level check that `--wrap` actually redirects production call sites | ran, 0 bypasses |
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

`evidence/cpu-build-and-ctest.log` also preserves an **earlier candidate run that
failed**, at `2026-09-28T00:01:06`, `ctest exit=8`, `1 - PatchRetryState (Failed)`. That
was the first version of the control, whose setup assertion wrongly expected a single
iteration to recover the applied displacement. The assertion was replaced with a
converged truth anchor (commit `cbeaf99`) and the run at `00:04:49` passed 14/14. The
failing run is kept rather than overwritten; the `WORKER_STATUS.md` model-comparison
record counts it as one of two self-corrections.

The CPU suite was rebuilt from scratch and re-run after each review round. The run
backing the figures in this document is the one at the current head,
`2026-09-28T02:20:05` to `02:20:32` in
[`evidence/cpu-revalidation.log`](evidence/cpu-revalidation.log): configure 0, build 0,
**14/14 passed**, same-backend control passed with its negative control reporting
exactly two files, retry-state control passed, and the preprocessed-TU control passed
with
"anything else = 0". Lane and topology are recorded in
[`evidence/cpu-provenance.txt`](evidence/cpu-provenance.txt): cores 32-63, `cpubind: 1`,
i.e. NUMA-node-local, with the two long-running `ctffind` processes recorded as
interference and not altered.

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

**What this control is, and is not.** §4 below shows that in a CPU-only build the two
trees differ by no executable statement at all, so "0 differing" was *entailed* before
the run. It is therefore a **build-hygiene control**, not a behavioural one: it would
catch an edit that accidentally escaped an `#ifdef _CUDA_ENABLED` guard and leaked into
the CPU path, which is a real risk given how much of this change lives inside those
guards. It is **not** evidence about F1-F6, none of which can execute in a CPU-only
build. The behavioural control for the CUDA path is the 24-movie same-backend run,
which has not been done.

## 4. Why the CPU binaries differ, and why that is not a behaviour change

`motioncorr` base `cb1e1cb1…`, candidate `b750e237…` (measured at this head; see
[`evidence/cpu-provenance.txt`](evidence/cpu-provenance.txt), whose five source hashes
were verified identical to the pinned head before the binaries were quoted). Every change in this branch to
`motioncorr_runner.cpp` is inside `#ifdef _CUDA_ENABLED`, so a CPU-only build should
contain no new code — but the binaries are not identical, and a hash difference left
unexplained is exactly the kind of thing that later gets waved away.

**That invariant was briefly broken, by me, and this control is why it was caught.**
The review round added `#include <sstream>` at file scope, outside every guard, to
support `REPORT_ERROR_STR`. The file's only use of that macro is inside the guarded
patch block, so the include moved in there rather than the claim being reworded — but
for one commit the claim in this section was false while the section still asserted it.
The lesson is the one §3 already states: this comparison exists precisely to catch an
edit that escapes a CUDA guard, and it only earns that description if it is re-run
after every change.

[`evidence/cpu-preprocessed-identity.log`](evidence/cpu-preprocessed-identity.log),
regenerated at this head with
[`harness/preprocessed_tu_control.sh`](harness/preprocessed_tu_control.sh):

```
preprocessed lines: base=75615 cand=75616
differing lines total      : 93
  friend declaration lines : 1   (emits no code)
  RelionError __LINE__ lines: 92
  anything else            : 0   <- must be 0
negative control OK: an injected line is detected
PASS CPU-only translation unit differs only by a no-code friend declaration and __LINE__ metadata
```

Preprocessing both trees with the same flags and no CUDA, stripping line directives and
normalising the source root, leaves a 75,615-line translation unit whose entire
difference is one added line — `friend struct MotioncorrRunnerTestAccess;`, which emits
no code — and 92 `__LINE__` values inside `RelionError` constructions, shifted because
the guarded blocks moved the following lines down. No executable statement changed.
That accounts for the binary difference completely. The control fails if any difference
is neither of those two kinds, and it carries a negative control: an injected line must
be detected.

(The `__LINE__` count is 92 here against 10 in the first round, because the include move
shifted lines earlier in the file than the original edits did. The count is not the
claim; "anything else = 0" is.)

## 5. CUDA compile

[`evidence/cuda-compile.log`](evidence/cuda-compile.log). Host `4GPUs` / `4-gpu-vm`,
`taskset -c 96-103` (affinity read back from `/proc`), `-j8`, under
`flock -w 2400 /tmp/motioncorr-bench.lock`. Compile only; **nothing was executed on a
device**, and no timing was produced.

```
Cuda compilation tools, release 12.8, V12.8.61
configure=0
CXX_FLAGS = -O3 -DNDEBUG -std=gnu++17 -fopenmp
build=0
(no warnings in changed files)
```

All five binaries linked — `motioncorr`, `cuda_fault_matrix`, `cuda_error_class`,
`cuda_wrapper_upload_failure`, `patch_retry_state`. **Zero warnings in any changed
file**; the five warnings in the build are pre-existing, in `src/memory.h` and
`src/time.cpp`, and are listed in full in the evidence file.

GPU UUIDs are recorded even though nothing ran on a device, because a device index is
not an identity: GPU 0 is `GPU-eddb42fe-4f9a-adde-76d3-b924e14add54`.

The fault matrix's `__wrap_` symbols are defined in the binary; `nm` counts **14** —

```
__wrap_cudaMalloc  __wrap_cudaFree  __wrap_cudaMemcpy  __wrap_cudaMemset
__wrap_cudaDeviceSynchronize  __wrap_cudaEventCreate  __wrap_cudaEventDestroy
__wrap_cufftCreate  __wrap_cufftMakePlanMany  __wrap_cufftSetWorkArea
__wrap_cufftPlanMany  __wrap_cufftDestroy  __wrap_cufftExecR2C  __wrap_cufftExecC2R
```

**That shows the test translation unit defines the wrappers. On its own it does not
show the linker redirected `motioncorr_core`'s calls to them** — a defined `__wrap_`
symbol looks the same whether or not the interposition took effect. An earlier version
of this document asserted the stronger claim on this evidence, which it does not
support.

The relocation-level check does support it
([`evidence/cuda-interposition.log`](evidence/cuda-interposition.log),
[`harness/reloc_check.sh`](harness/reloc_check.sh)). Disassembling the linked binary and
attributing every call to its enclosing function:

```
motioncorr_core call sites routed through __wrap_*: 179
motioncorr_core call sites still reaching a bare interposed symbol
  (direct call/jmp to a @plt entry) -- must be 0: 0
negative control -- same filter with the test-own exemption removed, must be >0: 14
PASS interposition reaches every matched production call site, and the check
     demonstrably can fail
```

The per-function breakdown in the evidence file shows eight `__wrap_cudaEventCreate`,
eight `__wrap_cudaMalloc` and one `__wrap_cufftPlanMany` inside `cudaAlignPatchDevice`
— exactly the resources F1 leaks, now inside the detector rather than invisible to it.
The only bare calls left are the `__real_*` forwards inside the wrappers and the test's
own post-trial reclaim, both by construction.

The **scope of the zero** is stated in the script rather than implied: it counts direct
`call`/`jmp` to a `@plt` entry, and it depends on CUDA being linked shared. The script
refuses to report on a truncated disassembly and runs a negative control — the same
filter with the test-own exemption removed, which must find the 14 `__real_*` forwards
and fails the run if it finds none. An earlier version had none of those guards and
would have printed a confident "0" if `objdump` had failed.

Even so, the matrix has **not been run**; that needs an assigned GPU slot.

Source hashes on the GPU host match the `cpu64` hashes exactly, so both validations ran
against the same tree.

### CUDA error classifier

[`evidence/cuda-interposition.log`](evidence/cuda-interposition.log), first block.
`tests/cuda_error_class.cpp` ran on the GPU host and **creates no CUDA context** — the
predicate makes no CUDA call, which is why it lives in a header rather than in an
anonymous namespace in the runner.

```
21 cases (13 poisoning, 8 recoverable), 0 failures
PASS classifier separates poisoned-context codes from recoverable ones.
     This covers the predicate only; no real poisoned context is
     synthesised anywhere in this suite.
```

The recoverable half is the half that matters: classifying `cudaErrorMemoryAllocation`
as poisoning would turn every ordinary OOM into a whole-movie abort and remove a
working fallback. The table is also required to contain both outcomes, so a predicate
degraded to always-true or always-false fails rather than passing silently.

## 5b. P1 — absence of a pending error is not proof of a usable context

Raised in the [PR107 review](https://github.com/KingAlejandro/MotionCorr-standalone/pull/107#issuecomment-5861849287)
and fixed narrowly.

**The defect.** The retry asked "is this context usable?" and answered it with
`cudaGetLastError()`. That is the host thread's last-error slot, and reading it resets
it. `CudaMovieSession`'s handlers *consume* the error before returning false — they
read it, log it, return — so by the time the caller regains control the slot reports
`cudaSuccess` regardless of what happened. A fatal failure that had already been
consumed was therefore classified recoverable and retried, and the log said "Context is
still usable". Absence of a pending error is not a certificate of context health.

**The fix**, using existing mechanisms rather than a recovery framework:

| Piece | What it does |
|---|---|
| `CudaMovieSession::recordFailure` / `recordCufftFailure` | Two calls added inside the existing `HANDLE_ERROR` / `CUFFT_CHECK` macros. Record the **first** failure with its stage and line, sticky for the session's life |
| `getFirstError` / `getFirstCufftError` / `getFirstErrorStage` / `getFirstErrorLine` / `hasFailed` | Expose that preserved status across the helper boundary |
| `cudaRetryDecisionFor(recorded, recorded_cufft, pending)` → `CudaRetryDecision` | A pure predicate. Consults **both** sources: either the recorded status or the pending slot can independently force a fatal verdict. Only when neither poisons does the preference between them matter, and then only for which code the message names. It also returns that deciding code, so the caller's message cannot disagree with the verdict |

A cuFFT failure alone does not force a fatal verdict: `cufftResult` reports
library-level failures that do not themselves imply a dead CUDA context, and if the
context did die the accompanying CUDA code says so.

**The CUDA-versus-CPU distinction is preserved in the log text.** `alignPatch()`
dispatches `cudaAlignPatch()` again while `use_gpu` is true, so on a GPU run the
re-attempt is a CUDA re-dispatch on the same device, not a CPU fallback. The message now
says that explicitly and names the recorded stage and line.

**Controls, both device-free, executed on the GPU host without creating a CUDA context**
([`evidence/cuda-interposition.log`](evidence/cuda-interposition.log)):

```
21 classifier cases (13 poisoning, 8 recoverable), 0 failures  [CUDART_VERSION 12080]
13 retry cases (8 fatal, 5 permitted), 0 failures
```

The 13 retry cases include the negative control the review asked for — a fatal error
recorded by a helper that then left the last-error slot clear must **still** refuse the
retry, covered for illegal address, launch failure and uncorrectable ECC — and the
supported recoverable case, where a recorded `cudaErrorMemoryAllocation` must still
permit the re-attempt so an ordinary OOM does not begin aborting movies. The table is
required to contain both verdicts, so a predicate degraded to always-fatal or
always-permitted fails.

**A regression inside this fix, found by review and corrected.** The first version of
the predicate preferred the recorded status *unconditionally* and consulted the pending
slot only when nothing had been recorded. Because the session keeps the **first**
failure, that reintroduced the same hazard from the other side: a benign early
`cudaErrorMemoryAllocation` on one patch stayed recorded for the rest of the movie, so a
fatal fault on a **later** patch — discarded by the first-failure guard, but still
sticky in the pending slot — became invisible to the verdict and was retried. That was
strictly worse than the head before the fix, where the pending slot was what got read.

Both sources are now consulted and either alone forces a fatal verdict. That is sound
because poisoning is monotonic: a context does not recover, so a fatal code from either
source is decisive, and the preference between them only affects which code the message
names. The predicate also returns the deciding code, because the call site had been
re-deriving it with the old rule and would otherwise have printed the recorded
allocation miss while the verdict was forced by the pending fatal code. Two control rows
pin the masking case (illegal address and launch failure pending behind a recorded
allocation miss), which is why the retry table went from 11 rows to 13.

**What this does not cover.** These are predicate tests. The real resident
nonconvergence path, an actual poisoned context, and asynchronous execution failure are
**not** exercised, and the review is right that the CPU S1/S2 experiment does not
replace a GPU-path test. Those remain in `gpu_plan.md`, unrun.

**A build failure is preserved with this work.** The first commit of this fix did not
compile under `-DCUDA=ON`: `cuda_error_class.h` used `cufftResult` while including only
`<cuda_runtime.h>`, which was invisible inside `motioncorr_runner.cpp` because
`<cufft.h>` arrives there transitively, and broke only when the test included the header
standalone. 14 compile errors, `cuda_error_class` never linked, the control exited 127.
See [`evidence/cuda-build-failure-preserved.log`](evidence/cuda-build-failure-preserved.log).
Noted because the same commit passed **14/14 on cpu64** — none of this code compiles in
a CPU-only build, so the CPU suite cannot stand in for the CUDA one on any change that
touches these files.

## 6. Findings fixed

Against `4c952b3f`; full detail in the ADR. Seven, not six: F7 was found while acting
on a review finding.

| ID | Defect | Where |
|---|---|---|
| F1 | Eight device buffers, a cuFFT plan and eight events leaked on every error, because every error macro in the file throws and skipped the straight-line cleanup; the cleanup block was also not failure-safe against itself | `cuda_alignpatch.cu` `cudaAlignPatchDevice` |
| F2 | Owned staging buffer leaked on upload, device-call or copyback failure — the class #82 fixed elsewhere, in the wrapper #82 did not cover | `cuda_alignpatch.cu` `cudaAlignPatch` |
| F3 | Patch cache could hold a freed non-null pointer for `release()` to free twice, or a stale size/count describing a buffer that no longer exists | `cuda_movie_session.cu` `preparePatchInVram` |
| F4 | Pointer cleared after the free, so a failing `cudaFree` left it set for `release()` to free again | `cuda_movie_session.cu` `releasePreprocessingBuffers` |
| F5 | The local-patch retry accumulated a second independent correction, publishing roughly twice the true local shift | `motioncorr_runner.cpp` local-patch block |
| F6 | A poisoned context was retried as though it were an ordinary allocation miss, by a path that dispatches CUDA again | `motioncorr_runner.cpp` local-patch block |
| P1 | The retry decided context health from a later `cudaGetLastError()`, which the failing stage had already consumed and reset — so a fatal, consumed failure was retried as recoverable | `motioncorr_runner.cpp`, `cuda_movie_session.{h,cu}`, `cuda_error_class.h` |
| F7 | `d_patch_fcomplex_buffer` leaked on every throwing exit from the patch loop, including `alignPatchDevice`'s own throw on any CUDA error — so it leaked once per failing movie. Found while fixing a review finding against F6, but the `alignPatchDevice` path makes it pre-existing, not introduced here | `motioncorr_runner.cpp` local-patch block |

## 7. Independent review

Two independent read-only reviews were run — one code, one specification/scope/licence.
Both returned findings and both are reflected above and in the commit history. Eleven
findings were acted on, including three that were defects in this branch's own work:

- the retry-state control read `use_gpu`/`gpu_id`, which `MotioncorrRunner` does not
  initialise, and would have dispatched a "device-free" control onto a GPU in a
  `-DCUDA=ON` build;
- the poisoned-context `REPORT_ERROR` leaked `d_patch_fcomplex_buffer` — and
  investigating that showed `alignPatchDevice`'s own throw was already leaking it, so
  the review turned one self-inflicted bug into an additional pre-existing finding;
- the fault matrix claimed a classifier unit test that did not exist, would have
  blanked the stage column for every *throwing* fault (exactly the F1 trials), would
  have reported one guaranteed false failure from `release()`'s deliberately non-fatal
  synchronise, and tracked only `cudaMalloc` while F1's leak is mostly events and a
  cuFFT plan.

Three documentation overclaims were also corrected: the `nm`-based interposition claim
(§5), the same-backend CPU row's status (§3), and an ADR sticky-error list that did not
match the implementation.

### Second round, at the corrected head

Both reviewers were re-run against the pinned head. They verified every prior code
finding as fixed, and found five more, three of them mine:

- **The removal of an unrelated orchestrator file had silently regressed.** It was
  untracked in one commit and re-added by a `git add -A` in the next — the same mistake
  the first commit's message described fixing — while `WORKER_STATUS.md` asserted the
  removal had held. Untracked again and added to `.git/info/exclude` so it cannot
  recur.
- **`#include <sstream>` escaped the CUDA guard**, falsifying §4's own premise in the
  same commit that relabelled §3 as a control for catching exactly that. Moved inside
  the guard; §4 regenerated.
- **The classifier raised the minimum CUDA version for the production build.**
  `cudaErrorExternalDevice` needs CUDA ≥ 11.6 and there is no version floor in
  `find_package`, so an older toolkit would have failed to build the product. Now
  behind `CUDART_VERSION` guards.
- `reloc_check.sh` had no `set -euo pipefail`, a fixed temp path and no negative
  control — it could have printed a confident "0" on its own failure. Hardened.
- The PR93 disclosure said three of four production files (it is four of four), quoted
  insertions and deletions summed into a single `+N`, and claimed F3 was independent
  three lines after stating PR93 overlaps it. Corrected in `WORKER_STATUS.md`; **F1, F2
  and F3** need reconciliation, F4-F7 and the tests do not.

The licence verdict was clean in both rounds: no new dependency, no vendored or
third-party code, nothing licence-incompatible.

## 8. Limitations, stated rather than worked around

- The fault matrix, the end-to-end retry witness and the 24-movie CUDA control have not
  run. Nothing here should be read as evidence about them.
- The fault matrix cannot synthesise a genuinely poisoned context, so F6's branch will
  not be exercised by a real fault even once a slot is assigned.
- F5 changes behaviour on purpose when a device patch attempt does not converge.
  Pre-fix and post-fix outputs are not expected to be identical there.
- Same-backend equality is not scientific equivalence and not a CPU/RELION Gate-2 pass.
- Clean nonzero failure is the supported contract where safe recovery is unavailable.
  It is not a successful CPU fallback and is not described as one.
