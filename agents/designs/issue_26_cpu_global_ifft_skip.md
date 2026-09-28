# Architectural Design Specification: skipping the unused global inverse FFT (Issue #26)

Status: **specification only — the implementation this governs is not yet written.**
PR #57 is the prototype; it is superseded by the port described in §7 and must not
be merged as it stands (§3.2).

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
reads those frames before the post-dose-weighting inverse transform overwrites
them, so the transform is dead work. On the measured hardware it was ~24% of a
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

Two consumers the 2026-09-27 note asked to check specifically, both resolved:

* **Binning** is *not* an independent consumer. `binNonSquareImage` (`:2436–2437`)
  operates on `Iref`, `Iref_odd`, `Iref_even` — products of the `:2340` block, so
  it is covered transitively. `early_binning` acts before the forward FFT
  (`cropInFourierSpace`) and never reads post-global-iFFT frames.
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

The sharing is the requirement, not a stylistic preference. A restated copy is
what failed: PR #57 wrote `do_local || !do_dose_weighting || save_noDW`, which
mirrored the guard *as it stood at its base commit `3e3a196`*. Commit `0f508e0`
(#67) later widened the guard with `|| even_odd_split`; the copy did not follow,
and nothing in the build or test suite connected the two. Binding both sites to
one `const bool` makes that drift impossible to reintroduce.

### 3.2 PR #57 as it stands is incorrect against main

Measured, not inferred (§5): with `--dose_weighting --even_odd_split --patch_x 1`
on current main, PR #57's predicate elides a transform that the `:2340` block
then reads, corrupting `_EVN.mrc` and `_ODD.mrc`. The dose-weighted micrograph is
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

**I4 — Fail closed.** If liveness cannot be established for a configuration, the
transform runs. The predicate is a disjunction of *reasons to keep* the work.

---

## 5. Evidence executed

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

All **13** CTests pass on the `pr57` build. `tests/test_runner_contract.py:105`
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

### 5.5 The merge into main auto-resolves — which is the hazard

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

## 6. UNRUN gaps

Not executed here. None of these may be described as passing.

| gap | why it matters |
| :-- | :-- |
| local 5×5 exact-output control **on main** | run at base `3e3a196` only; main's patch path now has CUDA branches |
| `--save_noDW` exact-output control **on main** | run at `3e3a196` only |
| non-square dimensions | required by the 2026-09-27 note; not run |
| binning modes (`--bin_factor`, `--no_early_binning`) | traced as transitively covered (§2), **not** executed |
| CUDA resident and `cudaInverseFFT2D` paths | no GPU in this task; declared unoptimized (§3.3), unverified |
| tomography / pre-exposure even-odd path (`test_runner_contract` exposure case) | not run |
| paired CPU benchmark on current main | deliberately excluded — no new benchmark series in this task |
| the ported implementation itself | does not exist yet (§7) |
| CI on the PR #57 head | cannot run while the PR conflicts (§5.5); build + CTests were run directly on cpu64 instead |

The ~24% figure for global-only dose-weighted runs comes from base `3e3a196`
measurements. It is **not** a current-main performance result and must not be
quoted as one.

---

## 7. Implementation contract

For the agent that does the port. This restates the 2026-09-27 plan with §2–§5
filled in.

1. Branch from main; leave `feat/issue-26-skip-dead-global-ifft` intact as the
   prototype and evidence record.
2. Introduce one `const bool pre_dw_sum_needed` before the global inverse FFT and
   use it **both** in `need_real_space_before_dw` and at the `:2340` guard.
3. Gate only the CPU loop inside `if (!cuda_global_ifft_done)`. Keep the
   `reshape` so allocation behaviour and peak RSS are unchanged.
4. Add a content-checking regression test for `--dose_weighting --even_odd_split`
   using the §5.4 invariant, and verify it **fails** against a build with the
   `even_odd_split` disjunct removed. A guard whose power has not been
   demonstrated does not count as coverage (§5.2 is why).
5. Execute the §6 matrix and report any configuration that cannot be optimized
   as unoptimized rather than changing its output.
6. The prototype branch already carries `|| even_odd_split` as an inert
   forward-compatibility term (§5.3). Keep it; in the ported code it stops being
   inert and must come from the shared `pre_dw_sum_needed`, not from a copy.

**Rejected alternative.** Widening the `:2340` guard, or making even/odd
independent of it, to enlarge the set of skippable cases. That changes which
products are written, breaking I1 and the resume contract, for a saving that only
applies when even/odd output was requested — i.e. when the frames are wanted
anyway.
