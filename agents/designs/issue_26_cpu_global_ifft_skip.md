# Architectural Design Specification: skipping the unused global inverse FFT (Issue #26)

Status: **implemented on this branch** (`perf/issue-26-global-ifft-elision-port`,
branched from pinned main `4c952b3`). This is the port §7 called for; the
specification is unchanged in substance and is carried here because it is the
artifact AGENTS.md requires alongside the code, not for re-approval.

PR #57 remains the prototype and its evidence is preserved at `0465ae1`. It is
**superseded by this branch** and should not be merged: its base predates
`0f508e0` (#67), it restates the consumer guard instead of sharing it, and it
carries no regression test. See §8 for the supersession mapping.

This document exists because a review of PR #57 found no Issue 26 architecture
artifact under `agents/designs`, which [AGENTS.md §1.1](../../AGENTS.md) requires
before a non-trivial change. It does **not** invent a new plan. The design was
already approved in three places and this specification consolidates them,
adds the source trace that none of them contained, and records what has and has
not been executed:

| approved source | what it fixed |
| :-- | :-- |
| [#57 integration note, 2026-09-26](https://github.com/KingAlejandro/MotionCorr-standalone/pull/57#issuecomment-5846036719) | "add `even_odd_split` to `need_real_space_before_dw` and include that combination in the exact-output control" |
| [#57 verified next steps, 2026-09-27](https://github.com/KingAlejandro/MotionCorr-standalone/pull/57#issuecomment-5860195454) | port onto main in a new branch; trace *every* consumer; required control matrix; report blocked configurations as unoptimized |
| [#66 work packages](https://github.com/KingAlejandro/MotionCorr-standalone/issues/66) | "#57 CPU inverse-FFT optimization must account for even/odd outputs before integration" |

Nothing below overrides those. Where this document is more specific, it is
because a source trace or an executed control settled a question they left open.

---

## 1. Problem and scope

After global alignment, `MotioncorrRunner::executeOwnMotionCorrection` inverse
transforms every frame into real space. In some option combinations no consumer
reads those frames at all before they are replaced, so the transform is dead
work. (On main with `use_gpu` and a successful `cudaDoseWeightAndInterpolate`
at `:2501` there is no post-dose-weighting inverse transform either — the frames
are simply never read again. The elision is safe for the same reason in both
cases: absence of a reader, not a later overwrite.) On the measured hardware it was ~24% of a
global-only dose-weighted run.

**In scope:** eliding that one transform, on the CPU path, when provably unread.

**Out of scope:** FFT engine or precision changes, plan reuse, threaded FFTW,
scheduling changes, and any change to what outputs are produced. This is not a
numerical approximation — it removes a computation whose result is discarded.

---

## 2. Consumer trace (current main `4c952b3`)

The optimization is only as correct as this list. Every read of the real-space
`Iframes` between the global inverse FFT (`src/motioncorr_runner.cpp:2025`) and
the post-dose-weighting inverse FFT (`:2525`):

| line | consumer | enclosing guard |
| --: | :-- | :-- |
| 2111 | `movie_session->downloadRealFrames` (CUDA patch prep) | `do_local` |
| 2121 | `cudaPreparePatch(Iframes, …)` | `do_local` |
| 2138 | `Ipatches[tid] += Iframes[iframe]` (CPU patch clipping) | `do_local` |
| 2370 | `cudaRealSpaceInterpolation(Iref, p_even, p_odd, Iframes, …)` | `:2340` |
| 2385, 2388–2389 | `downloadRealFrames` before the unweighted sum | `:2340` |
| 2394 | `Irefframes[i]().initZeros(Iframes[i]())` — **size only**, no pixels | `:2340` |
| 2399 | `realSpaceInterpolation_withoutsum(Irefframes, Iframes, …)` | `:2340` |

where `do_local = (patch_x > 2) && (patch_y > 2)` (`:2034`) and the guard at
`:2340` is `!do_dose_weighting || save_noDW || even_odd_split`.

**One expression that looks like a copy but is not.** The unweighted-micrograph
write guard (main `:2444`, `if (!do_dose_weighting || save_noDW)`) uses the same
three variables and *deliberately omits* `even_odd_split`: with
`--even_odd_split --dose_weighting` the unweighted sum is computed for EVN/ODD
only, and writing a `_noDW.mrc` there would add a product the run never
requested, violating I1. It must **not** be folded into the shared predicate.
The port annotates it in place so a future reader does not "finish the job".
This is the counterweight to §3.1: share what is one condition, and do not
merge what merely looks like one.

Two consumers the 2026-09-27 note asked to check specifically, both resolved:

* **Binning** is *not* an independent consumer. Both call sites take products of
  the `:2340` block, never `Iframes`: `binNonSquareImage(Iref, …)` at `:2434`
  with `Iref_odd`/`Iref_even` at `:2436–2437`, and the post-dose-weighting
  `binNonSquareImage(Iref, …)` at `:2539–2540`. So binning is covered
  transitively. `early_binning` crops at `:1863`, inside the forward-FFT loop —
  i.e. *after* `NewFFT::FourierTransform` at `:1861` but at the forward-FFT
  stage, well before global alignment — and never reads post-global-iFFT frames.
* **Resume/recovery** is not a pixel consumer but *is* a behavioural constraint.
  `:543` treats a movie as complete only if `_EVN.mrc`/`_ODD.mrc` are complete
  when `even_odd_split` is set. The optimization must therefore never change
  *which* products are written, only how they are computed — otherwise a
  wrongly-computed product is recorded as a completed one. See §4.

---

## 3. The requirement

### 3.1 Smallest exact-source requirement

> Elide the transform **iff** no consumer in §2 is enabled:
> `need_real_space_before_dw = do_local || pre_dw_sum_needed`
> where `pre_dw_sum_needed` is **the same named expression evaluated at the
> `:2340` guard**, not a restatement of it.

As implemented on this branch, `do_local` and `pre_dw_sum_needed` are each
declared exactly once, immediately before the transform, and every dependent
site reads those names; `do_local`'s former second definition below the patch
header is removed. The sharing is the requirement, not a stylistic preference. A restated copy is
what failed: PR #57 wrote `do_local || !do_dose_weighting || save_noDW`, which
mirrored the guard *as it stood at its base commit `3e3a196`*. Commit `0f508e0`
(#67) later widened the guard with `|| even_odd_split`; the copy did not follow,
and nothing in the build or test suite connected the two. Binding both sites to
one `const bool` makes that drift impossible to reintroduce.

### 3.2 PR #57 as originally written is incorrect against main

Measured, not inferred (§5): with `--dose_weighting --even_odd_split --patch_x 1`
on current main, the predicate as written at `13845fb` elides a transform that
the `:2340` block then reads, corrupting `_EVN.mrc` and `_ODD.mrc`. (The branch
head now carries the correction — §5.3 — so this describes the prototype as
authored, not the current head.) The dose-weighted micrograph is
unaffected, because the post-dose-weighting transform recomputes it — which is
exactly why single-configuration testing missed this.

The corruption is **non-deterministic**: the elided path leaves `Iframes` holding
a freshly `reshape`d, uninitialised buffer, so the digests vary between runs of
the same binary. A single clean run cannot demonstrate absence of this defect.

### 3.3 Call-site ownership

On main the global inverse FFT call site is shared three ways:

1. `movie_session->computeGlobalInverseFFT()` — CUDA in-VRAM resident path;
2. `cudaInverseFFT2D(…)` — CUDA non-resident path;
3. the CPU `#pragma omp parallel for` loop, reached only when `!cuda_global_ifft_done`.

**The optimization applies to (3) only.** (1) and (2) are explicitly left
unoptimized rather than silently altered, per the 2026-09-27 instruction to
report a blocked configuration as unoptimized. Two consequences to state rather
than discover later:

* After the change, CPU and CUDA perform different work under the same
  `TIMING_GLOBAL_IFFT` tag, so that stage is no longer a like-for-like
  CPU-versus-CUDA comparison.
* The CUDA-failure fallback path remains correct: it downloads the Fourier
  frames and resets the session before the CPU loop, and eliding the transform
  there is safe for the same reason it is safe generally — nothing reads it.

---

## 4. Invariants and fallback behaviour

**I1 — Product set unchanged.** Every configuration writes exactly the files it
wrote before, with unchanged names. Resume correctness (`:543`) depends on this.

**I2 — Even/odd behaviour unchanged.** `_EVN.mrc` and `_ODD.mrc` remain the
unweighted first/second-half sums and remain bit-identical to the unoptimized
build in every configuration that produces them. The even/odd path is never the
thing being optimized; it is a consumer that forces the transform to run.

**I3 — Bit-exactness, not tolerance.** No numerical tolerance applies. Comparison
is on the MRC pixel payload (bytes 1024+) and core header (bytes 0–223),
excluding the label area at offset 224, which carries a `strftime` timestamp and
is never reproducible between runs.

**I5 — Memory.** Eliding the transform does not increase peak RSS. Measured
(§5.6), it *reduces* it by 7.46% in the configuration where the elision fires,
and leaves it unchanged (−0.00%) where it does not. The earlier draft of this
document asserted "peak RSS unchanged"; that was unmeasured and is wrong in the
eliding case. No allocation is added: the `reshape` is retained, so the frame
buffers are still allocated at the same point (see §7.3 for a caveat that
follows from retaining it).

**I4 — Fail closed.** If liveness cannot be established for a configuration, the
transform runs. The predicate is a disjunction of *reasons to keep* the work.

---

## 5. Evidence executed

Raw record, including the commands' own output and the digests below:
[`logs/issue_26_cpu64_2026-09-28_evidence.md`](logs/issue_26_cpu64_2026-09-28_evidence.md).

Host `small-refmac-machine` (`cpu64`), AMD EPYC 7763, cpuset `32-63` (NUMA node 1),
build and runtime parallelism ≤ 16, serialised on
`flock /tmp/motioncorr-issue96-cpu-validation.lock`. Baseline main
`4c952b3f54479653512c4d208e09c9a8c02f3726`, `-O3 -DNDEBUG -std=gnu++17 -fopenmp`,
gcc 13.3.0. Three binaries built from identical sources except the predicate:

| build | sha256 |
| :-- | :-- |
| main (baseline) | `83e8749a55626b3268983bf9733b4276749539e025034a90ae98afa1f25b75b6` |
| `pr57` predicate (omits `even_odd_split`) | `95e1daf06e2fdb2b92c18b9ead0dd8a588955c33acb391ca111a9b8724450c03` |
| `fixed` predicate (shared with the guard) | `7e05817719790906d0aae46c70370b8794b140c6774ecc0864411a0bf51adcf9` |

Payload residency was witnessed on the **`motioncorr` process itself**, not on a
launcher wrapper: `comm=motioncorr`, `Cpus_allowed_list=32-63`,
`Mems_allowed_list=0-1` (cpuset restricted, memory policy deliberately not),
`VmHWM≈2.82 GiB`, 705372 of 706121 resident pages on node 1 by first touch.

### 5.1 Discriminating control — `--dose_weighting --even_odd_split --patch_x 1`

Tutorial movie `20170629_00021` (`df298b1b…`), gain `8919cdc7…`, one-row STAR
`6a851ed4…`, `--j 8`. Pixel digests (bytes 1024+, first 24 hex):

| output | main | `pr57` | `fixed` |
| :-- | :-- | :-- | :-- |
| `…_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | `ed33b6299dfc54782aa7f44c` | `ed33b6299dfc54782aa7f44c` |
| `…_frameImage_EVN.mrc` | `6e006ae913033f1c050e1fda` | **`117ad93bdd7b06e6b6080f64`** | `6e006ae913033f1c050e1fda` |
| `…_frameImage_ODD.mrc` | `62a9e0f978e254f3a6841ccb` | **`117ad93bdd7b06e6b6080f64`** | `62a9e0f978e254f3a6841ccb` |

`pr57` **diverges on both even/odd outputs**; `fixed` is bit-identical on all
three. In that run `pr57` produced *the same* digest for EVN and ODD — the
degenerate signature of summing frames that were never transformed. Reproduced
independently on the in-repo synthetic fixture (`95b5f0d3…`), where `pr57`'s EVN
digest differed again between runs, confirming §3.2's non-determinism.

### 5.2 The existing test suite has no power against this defect

All **13** CTests were executed and pass on the `pr57` build — that is the point:
they run, and they do not see the corruption. (This is a statement about the
CTests, not about the §6 configuration controls, none of which were run.) `tests/test_runner_contract.py:105`
does invoke the exact failing combination (`--dose_weighting --even_odd_split`)
but asserts only that the output files *exist*, never their content, so it cannot
observe the corruption. This is the gap the 2026-09-27 note means by "a test must
fail when a required consumer's reconstruction is incorrectly skipped".

### 5.3 PR #57's predicate was correct at its own base

Executed for completeness, because it decides where the regression test can
live. At base `3e3a196`, `--dose_weighting --even_odd_split --patch_x 1` writes
**no** `_EVN.mrc`/`_ODD.mrc` at all — the `:1800` guard there is
`(!do_dose_weighting || save_noDW)`, so the even/odd block never runs and nothing
reads the frames. PR #57 was therefore not wrong when written; it was made wrong
by `0f508e0` (#67) widening the guard underneath it.

Two consequences. First, the §5.4 regression test **cannot** be added to the
prototype branch — its oracle files do not exist at that commit — so it belongs
with the port. Second, the hazard is a rebase or merge, not the branch as it
stands, which is why the prototype now carries the `even_odd_split` disjunct as
an inert forward-compatibility term (§7.6).

### 5.4 A reference-free invariant for that test

`_EVN.mrc`/`_ODD.mrc` are unweighted sums, so they must not depend on
`--dose_weighting`. Verified as a usable oracle — true on correct code, false on
the defect — needing no new fixture:

| build | `_EVN` with vs without `--dose_weighting` | `_ODD` with vs without |
| :-- | :-- | :-- |
| main | equal | equal |
| `pr57` | **differs** | **differs** |

---

### 5.5 The control where the optimization actually fires

§5.1 demonstrates the *defect*; it does not demonstrate the *correctness* of the
corrected predicate, because with `even_odd_split` set the predicate is true and
nothing is elided. The configuration where the corrected predicate actually
elides is `--dose_weighting --patch_x 1` with neither `--even_odd_split` nor
`--save_noDW`. Same host and payload as §5.1, `--j 8`:

| config | elision? | output | main | `pr57` | `fixed` |
| :-- | :-- | :-- | :-- | :-- | :-- |
| `--dose_weighting`, patch 1×1 | **yes** | `…_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | same | same |
| `+ --save_noDW` (control) | no | `…_frameImage.mrc` | `ed33b6299dfc54782aa7f44c` | same | same |
| `+ --save_noDW` (control) | no | `…_frameImage_noDW.mrc` | `40361e827e571d3d5966a7dd` | same | same |

Bit-identical on pixel payload **and** core header (bytes 0–223) in both
configurations. This is the run that shows the optimization is output-preserving
when it fires.

### 5.6 Peak RSS

Measured in the same runs via `/usr/bin/time -f %M`:

| config | elision? | main | `fixed` | change |
| :-- | :-- | --: | --: | --: |
| `--dose_weighting`, patch 1×1 | yes | 3267840 kB | 3023924 kB | **−243916 kB (−7.46%)** |
| `+ --save_noDW` | no | 4714344 kB | 4714164 kB | −180 kB (−0.00%) |

So eliding the transform *reduces* peak RSS rather than leaving it unchanged.
Single run per cell; treat the −7.46% as an observation, not a characterised
figure. No wall-time claim is made from these runs.

### 5.7 The merge into main auto-resolves — which is the hazard

`git merge-tree origin/main <head>` on this branch:

| branch head | conflicts | resulting predicate | consumer guard it faces | outcome |
| :-- | :-- | :-- | :-- | :-- |
| `13845fb` (before the disjunct) | `CMakeLists.txt` only | `do_local \|\| !do_dose_weighting \|\| save_noDW` | `… \|\| even_odd_split` | **silently corrupting** |
| `75fde5f` (with the disjunct) | `CMakeLists.txt` only | `… \|\| save_noDW \|\| even_odd_split` | same | correct |

`src/motioncorr_runner.cpp` **auto-merges cleanly in both cases** — git reports no
conflict there, because the two sides edited different regions. So before the
disjunct, merging main into this branch would have produced the measured
EVN/ODD corruption with no conflict, no compiler warning and no failing test
(§5.2). That is the whole argument for carrying an otherwise inert term.

It also means CI cannot currently run on PR #57: GitHub will not build a merge
commit for a conflicting pull request, and `CMakeLists.txt` conflicts. The gates
in §5 were therefore executed directly on cpu64 instead, which is stronger
evidence than CI on a stale base would have been, but it is not the same thing
and is listed in §6.

### 5.8 Port evidence (this branch)

Same lane: cpu64, `taskset -c 32-63` (NUMA node 1, `Mems_allowed_list=0-1`,
policy default, `node1 cpulist=32-63`, `thread_siblings_list(cpu32)=32` i.e. no
SMT sibling visible in the guest), build and runtime ≤ 16,
`flock /tmp/motioncorr-issue96-cpu-validation.lock`, load1 3.1–3.6, two foreign
`ctffind` processes untouched throughout.

| build | predicate | binary sha256 (16) | `GlobalIfftElision` |
| :-- | :-- | :-- | :-- |
| main `4c952b3` | *(unmodified)* | `83e8749a55626b32` | n/a |
| **port** | `do_local \|\| pre_dw_sum_needed`, shared | `8ea55b8d289a7734` | **pass**; full suite **14/14** |
| neg-1 | pre-port: `… \|\| save_noDW` only | `765a669cd7a8165e` | **fail**, oracle A |
| neg-2 | over-broad: always elide | `478a32f43d5c9a56` | **fail**, oracle A |
| neg-3 | drops `do_local` only | `aa19af3f0f194739` | **fail**, oracle C |

Oracles A and C have demonstrated power; **oracle B's does not**, and should
not be counted as coverage. Every negative control trips A or C first, so no
build in this set reaches B in a failing state. B is defence in depth against
the uninitialised buffer, not a demonstrated detector — and note the buffer is
not reliably garbage either: a large fresh allocation usually arrives zero-filled
from the kernel, so the observed run-to-run variation (§5.1) comes from
intra-process reuse of a just-freed block, which is timing-dependent. A cannot
be carried by luck, but B might silently never fire.

neg-1 is the substitution the Sep-27 handoff asked for and fails with "`_EVN.mrc`: 36767 of 36864 pixel bytes differ
between no dose weighting and with dose weighting". neg-3 isolates oracle C
(neg-2 trips oracle A first) and additionally fails `SyntheticRegression` with
max pixel difference 10.315765.

**Oracle C needed the right fixture.** On the generated flat movie, patch 3×3
and patch 1×1 agree *on unmodified main too* (verified: identical digest
`af03af17642c38af`), because a motionless movie gives patch alignment nothing to
find. Asserting there would have been a false positive. Oracle C therefore runs
on the repository's `synthetic_movie.tiff`, where main separates the two by
630499 of 1048576 pixel bytes.

#### Bounded controls, port vs unmodified main

Existing fixtures only; every file compared on full pixel payload **and** core
header (bytes 0–223).

| arm | fixture | dims | result |
| :-- | :-- | :-- | :-- |
| local 5×5 | synthetic 512² | 512×512 | identical |
| binning ×2 (early) | synthetic | 256×256 | identical |
| binning ×2 (late, `--no_early_binning`) | synthetic | 256×256 | identical |
| binning ×2 late **+ `--even_odd_split`** (3 products) | synthetic | 256×256 | identical |
| **non-square**, elision path | tutorial `00021` | 3710×3838 | identical |
| **non-square**, local 5×5 | tutorial `00021` | 3710×3838 | identical |

8 output files across 6 arms, all bit-identical.

A seventh arm, non-square **combined with** binning ×2, could not be run: main
rejects it as invalid input (3710/2 and 3838/2 are both odd — *"The dimensions
of the image after binning must be even"*). Both builds reject it identically,
differing only in the reported source line (the port shifts it by the lines it
adds) and backtrace addresses. That is equal behaviour but not a control, so
non-square × binning stays UNRUN in §6.

## 6. UNRUN gaps

Not executed here. None of these may be described as passing.

Executed and therefore **not** listed here: the global-only dose-weighted
elision control and `--save_noDW` (§5.5), the even/odd defect control (§5.1),
peak RSS (§5.6), and — on the port itself — local 5×5, non-square, binning
(early/late/with even-odd), the full 14-test suite and three negative controls
(§5.8).

| gap | why it matters |
| :-- | :-- |
| non-square **combined with** binning | unreachable on the available fixtures: main rejects 3710×3838 at bin 2 as invalid input, identically on both builds (§5.8) |
| tomography / EER / compressed-MRC inputs | not exercised; no fixture in this lane |
| CUDA resident and `cudaInverseFFT2D` paths | no GPU in this task; declared unoptimized (§3.3), unverified |
| tomography pre-exposure even/odd path as an **exact-output** control | the `tomography` case (`test_runner_contract.py:141`) runs as part of the 13 CTests, but it carries `--save_noDW`, so the predicate is true and nothing is elided; it is not a control on this change. (The `exposure` case at `:31` has no `--even_odd_split` at all.) |
| paired CPU benchmark on current main | deliberately excluded — no new benchmark series in this task |
| CI on the PR #57 head | cannot run while the PR conflicts (§5.7); build + CTests were run directly on cpu64 instead |

The ~24% figure for global-only dose-weighted runs comes from base `3e3a196`
measurements. It is **not** a current-main performance result and must not be
quoted as one.

---

## 6a. Changed-file whitelist

This specification authorises changes to exactly these paths. Anything else in a
commit claiming to implement it is out of scope.

| path | permitted change |
| :-- | :-- |
| `src/motioncorr_runner.cpp` | the shared `pre_dw_sum_needed` and `do_local` declarations, their use at the `:2340` guard, the `need_real_space_before_dw` predicate, the guarded call in the CPU inverse-FFT loop, **removal of `do_local`'s second definition below the patch header** (required by §3.1 — one definition per predicate), an explanatory annotation on the unweighted-micrograph write guard marking it as deliberately *not* unified (§2), and the comments at those sites |
| `tests/test_runner_contract.py` *or* a new `tests/test_*.py` | the §5.4 content check |
| `CMakeLists.txt` | registration of a new test, if one is added as a new file |
| `agents/designs/issue_26_cpu_global_ifft_skip.md`, `agents/designs/logs/issue_26_*` | this specification and its evidence |

No change to FFT engine or precision, plan lifetime, scheduling, the set of
output products, or any CUDA source file is authorised here.

## 7. Implementation contract — status

Written for the porting agent; recorded here as delivered.

1. **Done.** Branched from pinned main `4c952b3`;
   `feat/issue-26-skip-dead-global-ifft` is untouched at `0465ae1`.
2. **Done.** `pre_dw_sum_needed` and `do_local` are each declared once before
   the transform; the `:2340` guard consumes `pre_dw_sum_needed`, and
   `do_local`'s duplicate definition is removed. The look-alike write guard is
   annotated as deliberately *not* unified (§2).
3. **Done.** Only the CPU loop inside `if (!cuda_global_ifft_done)` is gated;
   the CUDA resident and `cudaInverseFFT2D` paths are unchanged. The `reshape`
   is kept. Two consequences to carry deliberately rather than inherit:
   allocation stays at the same point (§I5), **and** keeping the reshape means
   `main:2388`'s `Iframes.empty() || Iframes[0]().nzyxdim == 0` test still
   passes over an elided, uninitialised buffer — so the one existing runtime
   sanity check on that buffer cannot detect the elided case. That check must
   not be relied on as a backstop; the predicate is the only guard.
4. **Done.** `tests/test_global_ifft_elision.py` (CTest `GlobalIfftElision`),
   four oracles, asserting full pixel payload, core header, STAR movie
   association and shift-table completeness, and MRC structural completeness —
   never file existence. Power demonstrated against three negative controls
   (§5.8), including the exact substitution this item names.
5. **Partly done.** Local 5×5, non-square and binning controls executed and
   bit-identical (§5.8). CUDA paths remain declared unoptimized and unverified;
   non-square × binning is unreachable on the available fixtures. Both are in
   §6, not claimed.
6. **Done.** In the port the term is no longer a separate disjunct at all: it
   reaches the predicate only through the shared `pre_dw_sum_needed`.

## 8. Supersession and overlap

| item | relationship to this branch |
| :-- | :-- |
| PR #57 / `feat/issue-26-skip-dead-global-ifft` @ `0465ae1` | **superseded.** Prototype and evidence; preserved, not merged. Its predicate restates the guard and its base predates `0f508e0`. |
| #26 | the investigation this implements. Measurement/tooling for #26 (PR #109) is a separate lane and is untouched. |
| #66 work package *"#57 CPU inverse-FFT optimization must account for even/odd outputs before integration"* | **discharged** by the shared predicate plus `GlobalIfftElision` and the §5.8 controls. |
| PR #110 (`integrate/round96-correctness-foundation`) | **merges cleanly — verified, not predicted.** `git merge-tree origin/pr110 HEAD` reports no conflict in any file. The merged `CMakeLists.txt` carries all of #110's `add_test` entries and `GlobalIfftElision`; the merged runner carries both `pre_dw_sum_needed` and `effective_expected_frames` with this predicate intact. No textual overlap in `src/motioncorr_runner.cpp`: #110's hunks end at `:1357` and resume at `:3329`; this change lives at `:1996–2468`. One semantic contact: #110 adds an `effective_expected_frames` parameter to `isMovieComplete` and a frame-count precondition, which is orthogonal to, and compatible with, I1's requirement that the product set is unchanged. Nothing from #110's tree is imported here. (An earlier draft of this document predicted a `CMakeLists.txt` conflict; that was inspection, and the merge check refutes it.) |

**Rejected alternative.** Widening the `:2340` guard, or making even/odd
independent of it, to enlarge the set of skippable cases. That changes which
products are written, breaking I1 and the resume contract, for a saving that only
applies when even/odd output was requested — i.e. when the frames are wanted
anyway.
