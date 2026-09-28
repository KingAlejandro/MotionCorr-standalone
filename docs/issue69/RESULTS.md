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
| Retry-verdict controls, incl. cleared-last-error fatal (device-free) | 13 cases, 0 failures — **at the previous head; NOT re-run, see §5c** |
| P1/P2 fixes from the Codex PR107 review | built clean on GPU2 (0 compile errors) and exercised by the device-free suites |
| Early-binning streaming control | **UNRUN** — no valid bin factor exists for this geometry, see §5d |
| CUDA compile of the changed sources and all three test binaries | ran, clean, zero warnings in changed files |
| Relocation-level check that `--wrap` actually redirects production call sites | ran, 0 bypasses |
| Bounded CUDA fault matrix | **ran natively on GPU2: 132 trials, 0 failures, 0 leaks** |
| Forced-nonconvergence end-to-end witness | ran natively; **F5 did not reproduce** — see §5d |
| Healthy same-backend 24-movie CUDA control | **ran natively: 24 images, 341,735,520 pixels, 0 differing** |

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

`motioncorr` base and candidate hashes are in the `=== binaries ===` block of
[`evidence/cpu-provenance.txt`](evidence/cpu-provenance.txt), whose source hashes are
verified identical to the pinned head before the binaries are quoted. **Read them
there, not here** — a hand-typed copy of the candidate hash has gone stale twice. At
the time of writing: base `cb1e1cb1…`, candidate `4a6abab1…`. Every change in this branch to
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
| `getFailureState()` | Exposes the preserved status across the helper boundary. (This originally listed five separate accessors; §5c replaced them with a single `CudaFailureState` handle, and this row went stale until a review caught it.) |
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

## 5c. Codex PR107 review: monotonic poisoning, and fixed-capacity registries

Two demonstrated findings, both fixed. **Neither is compiled.** See the limitation at
the end of this section before reading anything else here as verified.

### P1 — a later fatal error could still be discarded (`discussion_r4119217930`)

`recordFailure` kept only the **first** failure. So a recoverable
`cudaErrorMemoryAllocation` recorded on an early patch suppressed the recording of a
later `cudaErrorIllegalAddress` on another. Because `HANDLE_ERROR(cudaGetLastError())`
*consumes* that fatal code before the record is attempted, the runner's own later
last-error read was clean as well — and both sources the §5b fix consults were
therefore blind. `cudaRetryDecisionFor(old_oom, …, cudaSuccess)` permitted another
dispatch on a poisoned context.

**This falsifies an explicit earlier source-review claim. The reconciliation below was
itself corrected by that reviewer for being too generous to it**, and the corrected
version is the one that matters.

The round-4 code review enumerated all 26 `return false` sites in
`cuda_movie_session.cu` and concluded *"No gap. The P1 defect is genuinely fixed in its
primary form."* My first write-up of this said the enumeration "asked whether each path
records, not whether the record survives an earlier recoverable one" — true, but it
reads as a scoping slip, and the reviewer pointed out the failure was worse and more
interesting than that.

What actually happened: the round-4 review **did** find the masking — it was that
round's blocking finding, with this exact trace. The error was in the **remedy**. It
argued that under the then-current code "the old code read `pending`, and a sticky
`cudaErrorIllegalAddress` is still pending there, so it would have returned FATAL", and
proposed the OR form on that basis. That premise was false, because
`preparePatchInVram` calls `HANDLE_ERROR(cudaGetLastError())` at `cuda_movie_session.cu`
`:741` and `:773`, which **reads and clears** the slot — a consuming read the same
review had already catalogued. The reviewer had even hedged the underlying sticky-error
assumption in an earlier round, then confirmed the OR form in round 5 without
re-testing it against its own catalogue. So the §5b fix was proposed and signed off by
the same party that found the defect, on an assumption that party had previously
flagged as unverified, and it did not close the trace it described.

The design lesson is the one the current code embodies: **do not make a safety decision
depend on whether an error is still sitting in a slot that somebody else may already
have read.** Hence a latched state that no read can clear, rather than a better rule for
interrogating the slot.

`CudaFailureState` now tracks two independent facts:

| Field group | Semantics |
|---|---|
| `firstError` / `firstCufftError` / `firstStage` / `firstLine` | Diagnostic provenance. First-wins, so the cause a human reads is the earliest failure |
| `fatalError` / `fatalStage` / `fatalLine` | Poisoning, latched **monotonically**. The first poisoning code is recorded and never afterwards discarded, whatever was recorded before or after. A context does not recover, so this may only go clean → poisoned |

The predicate consults the sticky state first, then the recorded status, then the
pending slot. The fatal message also stops misattributing: it names the stage that
recorded the poisoning code, or states that the code was pending with no stage, instead
of always printing the first failure's location.

### P2 — per-patch heap allocation in the cleanup registries (`discussion_r4119217937`)

The registries were `std::vector`, rebuilt for every global and local-patch alignment,
so a *healthy* patch loop paid host heap allocations for them. The maxima are proved by
counting call sites — **8 buffers, 8 events, 1 plan** in `cudaAlignPatchDevice` and
**1 staging buffer** in the wrapper, with **no `add()` inside any loop** — so they are
now fixed-capacity arrays plus counters in `cuda_scoped_resources.h`.

RAII and error behaviour are unchanged: `releaseAll()` still continues past the first
failure, still reports the first error, is still idempotent, and now also skips null
slots. Capacity is a **hard error, not a silent drop**: `add()` refuses and sets an
overflow flag, and both call sites check it, so a future ninth resource fails loudly
instead of leaking on a throwing path.

### Controls written — and not executed

Six **production session-state sequences** driving the real `CudaFailureState` through
recoverable → consumed-fatal → cleared-slot, fatal-then-noise, recoverable-only,
cuFFT-then-fatal, clean, and pending-only; plus three capacity controls for counting,
refusal, overflow reporting and idempotency. The sequences drive the production object
rather than feeding synthetic inputs to the predicate, because the defect was never in
the predicate.

### Limitation: none of §5c is built

**#53 holds the shared GPU slot, so no CUDA compilation was queued and none of this
code has been compiled or executed.** Every file involved is CUDA-only and invisible to
the `cpu64` build — the CPU run at this head records
`grep -c cuda_error_class <build log>` = **0** as an explicit witness that nothing new
was compiled there. The control counts quoted in §5b (`13 retry cases`) are from the
**previous** head and were not re-run.

Accessors and call sites were cross-checked against their declarations by hand. Hand
checking is not a compiler, and on this branch an unbuilt CUDA change has already
shipped once with 14 compile errors while the CPU suite was green (§5b). **Nothing in
§5c should be treated as validated until it builds.**

## 5d. Native acceptance on GPU2

Alex authorised parallel GPU use on 28 Sep; #69 was assigned **GPU2**
(`GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598`), CPUs **112-119** on node1, all
descendants ≤ 8, `j4`/`io2`, under `/tmp/motioncorr-gpu2-correctness.lock`. #53 retained
GPU0/1 and 96-111 and was **active throughout** — its processes are visible in the
provenance with 426 MiB each on GPU0/1, and were not touched. GPU2 read 1 MiB before and
after every run.

**No timing is recorded or claimed from any of this.** Competing MotionCorr arms were
running on the same VM, so wall times here would be characterisation at best. All
comparisons normalise measured durations out.

Full evidence: [`evidence/native-gpu2/`](evidence/native-gpu2/), provenance in
[`07-provenance.txt`](evidence/native-gpu2/07-provenance.txt).

### Build — the unbuilt gap is closed

`configure=0`, `build=0`, **0 compile errors**, zero warnings in changed files, all
binaries linked, at the frozen source. Both reviewers had bounded their confirmations
as reads and asked that "must compile under `-DCUDA=ON`" remain a merge gate; it now
does compile.

### The bounded fault matrix, executed for the first time

```
Clean run uses: cudaMalloc=42 H2D=19 D2H=16 D2D=8 memset=5 sync=12
                cufftCreate=2 cufftMakePlanMany=2 cufftSetWorkArea=2 cufftPlanMany=4 cufftExec=17
132 trials, 0 failures
```

Every ordinal of every wrapped primitive, plus successive-movie trials with the fault on
the third movie. **Zero leaks and zero damaged inputs in all 132 trials.** The row that
matters most for F1 is `cudaMalloc 16 | global alignment | threw RelionError | owned=0` —
the exact path that previously leaked eight buffers, a cuFFT plan and eight events, now
releasing cleanly on the throwing path with events and plans tracked, not just memory.

The existing wrapper upload-failure control still passes (no regression), and the
device-free suites pass: 21 classifier + 13 retry + 6 production session-state + 3
capacity controls, 0 failures.

### Healthy all-24 same-backend — identical

24 movies, base `4c952b3f` versus candidate, both CUDA Release on GPU2:

```
106 files compared, 24 MRC images, 341735520 pixels, 0 differing
negative control reported 2 differing files (expected 2 = 0 already differing + 2 perturbed)
PASS outputs identical over 24 images / 341735520 pixels, and the comparison is able to fail
```

Device-backend witnesses confirm the resident CUDA path actually executed rather than
silently falling back: **24** global alignments, **600** patch alignments (24 × 25), **24**
dose-weighted resident-VRAM reconstructions.

### F5 did not reproduce natively, and that narrows my own earlier claim

This is the result I would most want a reader not to miss.

| `--max_iter` | device alignments nonconverged | converged | images differing |
|---|---|---|---|
| 1 | 1224 | 0 | **0** |
| 2 | 37 | 595 | **0** |
| 3 | 0 | 624 | **0** |
| 4 | 0 | 624 | **0** |

At `max_iter=1` **every** patch reported `converged=no`, so the retry path engaged
everywhere — and the outputs were still byte-identical. At `max_iter=2` the path engaged
for 37 patches, same result.

The reason is structural and I had missed it. Both attempts use the **same** `max_iter`
on the **same** data: `alignPatchDevice` and `alignPatch` are each passed the same
member. So when the device attempt fails to converge, the retry almost always fails too,
and `if (!converged) continue` **skips the patch in both arms** — the accumulated shift
is discarded before it ever reaches the polynomial fit. The double count is only
*observable* when the retry converges where the device attempt did not, which given
identical algorithm, data and budget requires the float/double borderline near the
0.5 px tolerance. That window did not occur in 2,472 patch alignments across four
configurations on 24 movies.

**So F5 is source-demonstrated and CPU-demonstrated, but not natively reproduced.** The
defect is real — `alignPatch` accumulates, the vectors are not reset, and the CPU
control shows the exact doubling — but §5b/the ADR framed it as though it routinely
reached the fit, and the hardware says otherwise. Two consequences worth recording:
the fix is a correctness guard against a narrow window rather than a repair of a
commonly-hit bug, and the **skip-on-nonconvergence** alternative the ADR rejected now
looks better than when it was rejected, because the retry it removes is one that
essentially never changes the outcome.

### Early-binning: UNRUN

Four bin factors (1.855, 2.5, 3.71, 1.9175) all fail on this 3710×3838 geometry with
*"The dimensions of the image after binning must be even"* — 3710/2 = 1855 is odd. Base
and candidate fail **identically**, which is consistent with no regression, but a
control whose every arm errors out is not a pass and is not counted as one. Pass
criterion 4's early-binning half remains **unsatisfied**; it needs a geometry where the
option is usable.

### A failed first attempt, preserved

[`03-e2e-FAILED-first-attempt.log`](evidence/native-gpu2/03-e2e-FAILED-first-attempt.log)
is kept. That attempt was invalid and I nearly reported it as a result: `--i` took an
**unquoted** glob, so the parser saw 24 arguments and used only the first — one movie,
and `20170629_00021`, which is documented as unrepresentative. The output count was also
wrong, because products nest under the input's absolute path and a flat `ls` found none,
so it read as `mrc=0` — a zero-file comparison, the precise anti-pattern the round
instructions prohibit. Both are harness defects, both are fixed, and the broken run is
retained rather than deleted.

## 5e. Second boundary: fatal error consumed by the FALLBACK preparation

Codex PR107 `discussion_r4119570895`, and it was right.

The §5c health check runs **before** `cudaPreparePatch`, so it structurally cannot see a
fatal error raised *by* that preparation. The surviving sequence:

1. the resident attempt is nonconverged, or fails recoverably — nothing fatal yet;
2. the pre-fallback check therefore **permits**, correctly;
3. `cudaPreparePatch` hits a fatal fault. Its own handler **consumes** the code, logs
   it and returns `false`, clearing the thread's last-error slot;
4. the caller CPU-prepares, then `alignPatch` **re-dispatches CUDA** because `use_gpu`
   is still true — onto the context step 3 just killed.

Neither thing a caller can inspect afterwards sees it: the session state never observed
this failure, and the slot is empty. **A peek at a cleared slot is not a health check.**

The fix carries the status out of the helper. `cudaPreparePatch` takes an optional
`CudaFailureState *failure` (defaulted `nullptr`, so no other caller changes) and
`cuda_fft_prep.cu`'s consuming handlers record into it. The runner checks that state
immediately after a failed fallback preparation and refuses the re-dispatch on a
poisoning code, naming the stage and line **the fallback itself** recorded rather than
the resident attempt's unrelated earlier failure. A recoverable fallback failure still
permits the host path.

The control is ordered as production orders it and is discriminating: it asserts the
pre-fallback check permits, the post-fallback check refuses, the refusal names the code
the fallback consumed, and — the part that makes it discriminating — that **the resident
state alone still reads permitted** and **a cleared slot alone never justifies a fatal
verdict**. A fix consulting only the session, or only peeking at the slot, fails it.

### Executed on the corrected source

`cpu64`, validation lock, cores 32-63, `cpubind`/`nodebind` 1, 215 GB available, 16 MB /
686-file payload, both `ctffind` processes recorded and untouched: configure 0, build 0,
**14/14 CTest**, same-backend identical with negative control, retry-state control
passing, preprocessed-TU `anything else = 0`.

GPU2 `GPU-063e5232-…`, CPUs 112-119, per-device lock, after an occupancy and identity
recheck ([`evidence/native-gpu2/08-corrected-source-gpu2.log`](evidence/native-gpu2/08-corrected-source-gpu2.log)):

```
configure=0  build=0  compile errors=0
21 classifier cases (13 poisoning, 8 recoverable), 0 failures  [CUDART_VERSION 12080]
13 retry cases (8 fatal, 5 permitted), 0 failures
8 session-state sequences, 0 failures      <- was 6; the two new ones are this boundary
3 capacity controls, 0 failures
132 trials, 0 failures                     <- fault matrix re-run, FAIL rows: 0
all-24: 106 files compared, 24 MRC images, 341735520 pixels, 0 differing
        negative control reported 2 differing files (expected 2)
```

Source hashes match byte-for-byte across the worktree, `cpu64` and the GPU host.

**Unchanged and still true:** F5 **did not reproduce** natively (§5d); a genuine
poisoned context, the early-binning control and any older-toolkit build remain
**UNRUN**; no timing is recorded or claimed.

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
| P1c | A fatal error consumed by the **fallback** `cudaPreparePatch` was invisible to a health check that ran before it, so `alignPatch` re-dispatched CUDA onto a context that preparation had just killed | `cuda_fft_prep.{h,cu}`, `motioncorr_runner.cpp` |
| P1b | A later fatal error could be discarded because the session kept only the first failure, so a recoverable code recorded earlier masked it while the consuming handler had already cleared the pending slot | `cuda_failure_state.h`, `cuda_movie_session.{h,cu}`, `cuda_error_class.h` |
| P2 | Per-patch `std::vector` cleanup registries performed host heap allocation on every healthy alignment | `cuda_scoped_resources.h`, `cuda_alignpatch.cu` |
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
