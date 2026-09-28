# Issue #95 — bounded frame-staging component evidence

Companion to `agents/designs/issue_95_bounded_frame_staging.md`.

| field | value |
| --- | --- |
| issue | #95 |
| branch | `round96/95-claude-opus-5` |
| base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| scope of this evidence | the CPU-only component prototype and its tests. **No GPU execution, no pipeline run, no timing.** |

## 1. What is proven here, and what is not

**Proven by execution:**

- `motioncorr::staging::buildSchedule` / `applyChunk` reproduce a **transcription
  of** the production hot-pixel repair (`src/motioncorr_runner.cpp:1732-1775`)
  bit-for-bit, for every tested chunk size, and leave the process RNG in the
  same state. The oracle is `referenceRepair` in the test, not the runner
  itself; see the limit recorded in §4.2.
- The capacity formula reproduces the two published geometries exactly and
  rejects overflow and invalid policies instead of wrapping.
- The test suite **can fail**: three separate intentional bugs were injected
  into the component and all three were caught (§4).

**Not proven, and not claimed:**

- No measured host RSS or device high-water. Every byte figure in the ADR is a
  calculated array size.
- No GPU execution of any kind. No device was used and no GPU slot requested.
- No end-to-end pipeline run, no 24-movie comparison, no timing. The component
  is not wired into `MotioncorrRunner`, so there is no pipeline layer to test.
- The `Irefframes` fusion of ADR §5.1 is argued from the source. It is **not**
  built and **not** run.
- The device-side repair gather of ADR §5.3 is analysed only.
- Formats: only the `uint16` TIFF path was analysed for the compact-upload
  variant. Packed 4-bit, `int16`, 8-bit, `float32` TIFF, EER and compressed MRC
  are **unrun**.

## 2. Build provenance

### 2.1 Two lock epochs, not merged

A coordinator correction mid-task replaced the round's CPU lock. The two epochs
are recorded separately and **no earlier result is restamped with the newer
lock**:

| epoch | lock | cores | source tree | status |
| --- | --- | --- | --- | --- |
| old | `/tmp/motioncorr-issue96-cpu.lock` | `taskset -c 40-47` | pre-review | **superseded**, retained as non-timing evidence for a tree that no longer exists on this branch |
| current | `/tmp/motioncorr-issue96-cpu-validation.lock` | `taskset -c 48-55` | final head | the only source of results quoted for the final head |

The old lock did not serialise against the other workers in this round. Since no
timing is claimed anywhere in this document, nothing quoted from either epoch
depends on exclusivity — but the old-epoch runs are still not carried forward as
current, because they were built from different sources.

### 2.2 Current epoch (final head)

| field | value |
| --- | --- |
| host | `small-refmac-machine` (cpu64) |
| kernel | Linux 6.8.0-86-generic x86_64 |
| topology | 2 NUMA nodes; node0 = cpu 0–31, node1 = cpu 32–63; 115839 / 115862 MB |
| inherited cpuset | `Cpus_allowed_list: 0-63`; `cpuset.cpus.effective` = `0-63` — no cgroup restriction was inherited, so the binding below is the only thing constraining placement |
| chosen cores | `48-55` — 8 cores inside the required 32-63 range, leaving 0-31 free for #26's concurrent measurement |
| effective policy of the test process | `policy: bind; physcpubind: 48 49 50 51 52 53 54 55; cpubind: 1; nodebind: 1; membind: 1; preferred: 1` (captured from `numactl --show` inside the bound process, not asserted) |
| NUMA memory policy | `--membind=1`, node-local to the chosen cores |
| parallelism | `-j8` build, single-threaded test — both within the ≤16 cap |
| node free memory at run | node0 17923 MB, node1 16277 MB (payload is bound to node1) |
| load at start / end | 4.25 / 4.17 one-minute average |
| interference, not altered | two foreign `ctffind` processes at ~100% CPU each, on node0's share; the payload is bound to node1 cores 48-55 |
| serialisation | `flock /tmp/motioncorr-issue96-cpu-validation.lock` held across configure, build and every test |
| cmake | 4.4.3 |
| compiler | `c++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` |
| build type | `Release` |
| release flags | `-O3 -DNDEBUG` |
| CUDA | off (`-DCUDA` not set); this is a CPU-only build |

`Release` is stated explicitly because an unqualified CMake configure in this
project builds at `-O0`.

Interference observed on the host and deliberately not altered: two unrestricted
`ctffind` processes belonging to another user, each at ~100% CPU, present at the
start of the session (load avg 2.37 at 2026-09-27T23:47Z). No timing is reported
here, so this interference affects nothing that is claimed.

Raw unedited logs for both epochs are in `raw/`; see `raw/README.md`.

## 3. Source and binary hashes (SHA-256)

| file | sha256 |
| --- | --- |
| `src/frame_staging_plan.h` | `c7f6b8d7b9e45f778ef2bd03a914e43c8d4c3ae026d57be1b9c2103c7303fdd4` |
| `src/frame_staging_plan.cpp` | `113bb869d4a8918bfa73112321ec49a59260b3a7dae54b286161c989eff7863f` |
| `tests/test_frame_staging.cpp` | `4e0efbaeea67e758e215217632be7a8350b3c81606610e727f7fda40658a6a4b` |
| `CMakeLists.txt` | `56b061af41eea804d886bd82b4c8b2e5ae2d5f66893ea2c7793d753fbbf53875` |
| `build-cpu/frame_staging` (binary) | `6740791228187eb0dce63d40d3b668671654dfbcc35c5500aca961c5a3fe95a5` |

These are the hashes of the exact files committed on this branch, at the final
head, taken in the same locked run that produced the results below
(`raw/11-validationlock-final-mutants.log`). The pre-review hashes quoted in the first
revision of this report belonged to a source tree that no longer exists; they
are not reproduced here.

## 4. Commands and results

### 4.1 Component test

```
cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON     # exit 0
cmake --build build-cpu --target frame_staging -j8                        # exit 0
./build-cpu/frame_staging                                                 # exit 0
  -> 283 checks, 0 failures
```
(`raw/08-validationlock-codexfix-build.log`, and `raw/09-...-oldmodel.log` for
the baseline/restore pair). 248 -> 283 adds the corrected-accounting controls of
§4a. Earlier counts 235 / 256 / 248 are superseded, not comparable: assertions
were replaced as well as added. See §4.2.

Coverage of the current 283 checks:

| group | cases |
| --- | --- |
| capacity: published geometries | tutorial `3710×3838×24` real = 1366942080 B, r2c = 1367678976 B, sum = 2.547 GiB; `8192²×80` sum = 40.005 GiB |
| capacity: uncharged third stack | tutorial CPU reconstruction resident = `2·real + r2c` = 3.820 GiB |
| capacity: declared bound | staged bytes constant as F grows 4 → 4096 at fixed chunk |
| capacity: degenerate chunk | chunk 0 and chunk > F both clamp to the whole movie |
| capacity: compact upload | staged term and H2D both exactly halved; device unchanged |
| capacity: replay | H2D exactly doubled; staged bound unchanged |
| capacity: rejection | overflowing geometry, zero width, negative chunk, zero passes, zero staged sample width, negative extra host and device bytes |
| capacity: three-way admission | largest admissible chunk is exact; a part-frame surplus buys nothing; a budget under one frame is reported **inadmissible** rather than "chunk 0" and leaves the caller's variable untouched; a retained resident stack flips the same budget to inadmissible; a huge budget clamps to the frame count; extra named terms reduce the chunk |
| ordering: raw host frames + gain reference | chunks 1, 2, 3, 11 — the `_CUDA_ENABLED` path: gain applied on gather, replacement recorded, raw frame left untouched |
| ordering: gain is not inert | same movie with and without the gain arm produces different replacements |
| rejection paths | null mask, null frame pointers, negative first frame, chunk past the last frame, chunk longer than the movie, record-only with nowhere to record, mis-sized replacement buffer, mask changed since the schedule was built, inconsistent `bad_y`, out-of-range slot; `buildSchedule` rejects `d_max > 4`, null mask, zero width, zero frames, negative `d_max`, and leaves nothing half-populated on failure |
| ordering: sparse defects, 24 frames | chunks 1, 2, 3, 5, 24 |
| ordering: solid 5×5 block, 13 frames (odd) | chunks 1, 2, 4, 13 — reaches the Gaussian branch |
| ordering: corner and edge defects, 9 frames | chunks 1, 2, 4, 9 |
| ordering: non-square 57×29, EER radius `D_MAX=4`, 7 frames | chunks 1, 2, 3, 7 |
| ordering: `sigma == 0`, 5 frames | chunks 1, 2, 5 — `rnd_gaus` returns `mu` without consuming the stream |
| ordering: single frame; empty defect mask | chunks 1, 4 |

Each ordering case asserts: bit-identical frame buffers against a transcription
of the production loop; recorded sparse replacements equal to the reference's
own buffer **in the runner's frame-major layout**; an identical process RNG
tail; and that the branch the fixture targets was actually reached.

Two assertions present in the first revision were **removed rather than
fixed**: that the branch kind is constant across frames for a given masked
pixel, and that the two draw counters sum to `n_bad · n_frames`. Both were
tautologies over `buildSchedule`'s own loop nesting and would have passed
regardless of what the production loop does. The property they claimed to check
— frame-independence of `n_ok` — is genuinely covered by the differential
comparison, whose oracle recomputes `n_ok` per frame from real pixel data. The
check count therefore reflects fewer, more meaningful assertions.

### 4.2 Intentional-bug control

The differential test is only evidence if it can reject a wrong implementation.
Three bugs were injected into `src/frame_staging_plan.cpp`, each built and run
under the same lock, then reverted:

**Old epoch, pre-review tree** (`raw/03-oldlock-mutants.log`):

| injected bug | result |
| --- | --- |
| `kNumMinOk` 6 → 5 (wrong branch boundary) | **test exit 1** — caught on `corners-9f`: pixel mismatch, RNG state mismatch, and the Gaussian-branch coverage assertion |
| schedule built frame-major instead of pixel-major (reorders the RNG stream) | **test exit 1** — caught on every fixture with more than one frame, at every chunk size including full |
| neighbour slot list enumerated `dx`-major (transposes `pbuf`) | **test exit 1** — caught on every fixture at every chunk size |

**Current epoch, first post-review head** (`raw/04-validationlock-mutants.log`).
These four target the defects the first review found. Superseded by the round
below but retained, since they were run against a real tree:

| injected bug | result |
| --- | --- |
| replacement buffer transposed back to bad-pixel-major (review finding 1) | **test exit 1** — caught by "recorded sparse replacements match the reference, in the runner's frame-major layout", on every fixture and chunk size |
| gain multiply dropped on neighbour gather (review finding 2) | **test exit 1** — caught on `raw-gain-11f` only, at every chunk size, which is the fixture added for exactly this |
| `write_in_place` ignored, raw host frames clobbered (review finding 3) | **test exit 1** — caught by the frame comparison on `raw-gain-11f` |
| `d_max > 4` bound removed | **test exit 1** — 2 failures, both in the rejection-path group |

**Second post-review head, SUPERSEDED** (`raw/06-validationlock-rereview-mutants.log`).
A second review found four assertions that could not fail and two real defects.
These five mutants target that round. Retained because the round happened, not
because its numbers are current: the head and the check count below were both
superseded by the corrected-accounting round that follows.

An earlier revision printed this block under a "Final head" heading and cited
`raw/09` beside it, which is the *next* round's log. That was a careless global
find-and-replace on my part, caught by independent audit. It is the exact
failure this document exists to prevent -- a real result filed under the wrong
run -- so it is corrected here and recorded rather than quietly repaired.

| injected bug | result |
| --- | --- |
| `InvalidInput` collapsed into `Inadmissible` (finding A) | **exit 1**, 3 failures — the malformed-policy, negative-`chunk_frames` and malformed-geometry assertions |
| `out = Schedule()` deleted from `buildSchedule` (finding F) | **exit 1**, 1 failure — "a rejected buildSchedule clears a previously populated result" |
| `Movie` self-assignment guard removed (finding D) | **exit 1**, 3 failures — mask preserved, schedule sees the same defects, copy is deep |
| raw host frames written despite `write_in_place = false` (finding E) | **exit 1**, 4 failures — "raw host frames are left untouched", every chunk size |
| `largestChunkWithin` off-by-one, `best = mid - 1` | **exit 1**, 4 failures across the admission group |

Baseline and restore in that session both returned **248 checks, 0 failures** --
a superseded count, at a superseded head.

The two that matter most are **E and F**, because those assertions previously
*could not fail*: E compared two pristine buffers under a label claiming to
check repaired pixels, and F asserted emptiness on a `Schedule` that had never
been populated. Each was replaced by an assertion of the property genuinely at
risk — that raw frames come back untouched, and that a *pre-populated* result
is cleared — and the mutants above are the proof that the replacements are
observable rather than merely better worded.

**Final head** (`raw/11-validationlock-final-mutants.log`). Each mutant reverts
one fix, so each proves the corresponding control discriminates the **old**
model rather than merely agreeing with the new one:

| reverted fix | result |
| --- | --- |
| repair schedule omitted from the host budget | **exit 1**, 6 failures — the charge formula, chunk-independence, "dwarfs the staged chunk", and both dense-defect admission controls |
| `Iframes` double-counted (alias disabled) | **exit 1**, 6 failures — the alias flag, "charges Iframes once, not twice", the parts-over-sum check, and the alias-drop assertions |
| whole-movie probe removed from the search | **exit 1**, 4 failures — including "the search finds the aliased whole-movie point a monotone search would miss" |
| exact `reserve` removed from `buildSchedule` | **exit 1**, 1 failure — "the schedule's index vectors are reserved exactly, so the charge covers them" |

Baseline and restore in the same locked session both **287 checks, 0 failures**;
`ctest` 14/14; restored hashes match the committed tree.

### A mutant that survived, and the gap it exposed

`raw/10-validationlock-a1gap-survivor.log` is retained because it records a
**failure of this suite**, not a success. Two things went wrong in that run and
both are worth keeping:

- The `reserve` mutant **survived**: 285 checks, 0 failures with the fix
  reverted. Nothing observed vector capacity, which is the only thing that
  distinguishes an exactly-reserved vector from a `push_back`-grown one. The
  A1 fix was real but **untested**, and only the mutant exposed that. A direct
  capacity assertion was added and the mutant is now caught.
- The alias mutant **failed to build**, from a shell-escaping bug in the
  mutation script itself, so it was not evaluated at all. Had the script
  reported only exit codes, a three-mutant result would have been indistinguishable
  from a four-mutant one. It printed `BUILD_FAILED` explicitly, which is the
  only reason the gap was visible. The inline escaping was replaced with a
  standalone `mutate.py`.

Neither was caught by the reviewers; both were caught by running the controls
and reading the output rather than the exit status.

Two observations that limit what this control proves, recorded rather than left
implicit:

- The third old-epoch bug is caught even at chunk = full movie, because slot
  ordering is a correctness property independent of chunking. A control that
  only varied the chunk size would not have been sufficient on its own.
- **No mutant was injected into the oracle.** The oracle is `referenceRepair`
  in `tests/test_frame_staging.cpp`, a hand transcription of
  `motioncorr_runner.cpp:1732-1775`. This control therefore cannot detect drift
  between that transcription and the runner — the one failure mode that would
  invalidate the whole differential test. That was checked by reading, twice,
  by an independent reviewer comparing the two line by line, but it is not
  covered by execution. (The finding-D mutant does touch the test file, but it
  removes a copy-assignment guard, not any part of the oracle's logic.)
- `largestChunkWithin`'s `best < 1` guard is provably unreachable, so a
  mutation gate will report a permanent survivor there. It is retained
  deliberately: returning `Inadmissible` is the safe answer if the reasoning
  behind its unreachability is ever invalidated.
- The monotonicity precondition behind the binary search is now asserted across
  four policy shapes and the full chunk range, rather than left as a comment.
  That test would not catch a *non-monotone* term added to `Policy` unless the
  term is exercised by one of those four shapes.

### 4.3 Whole-project build and existing CTest suite

Run to show the `CMakeLists.txt` edit does not disturb the existing targets or
tests. See §5.

## 5. Existing test suite

```
cmake --build build-cpu -j8            # whole project, exit 0
ctest --output-on-failure              # exit 0
```

14/14 passed in 7.35 s, on the same CPU-only `Release` build described in §2.2
(`raw/11-validationlock-final-mutants.log`):

| # | test | result |
| --- | --- | --- |
| 1 | `FrameStaging` (new) | Passed |
| 2–12 | `SyntheticRegression`, `HotPixelRngDeterminism`, `RunnerExposure`, `Runner_failure`, `Runner_invalid`, `Runner_resume`, `Runner_tomography`, `RunnerLateBin`, `RunnerExportedUnits`, `GainCache`, `TiffRead` | Passed |
| 13 | `DamagedMovie` | Passed, 0.09 s |
| 14 | `RunnerModelParser` | Passed, 0.13 s |

Per-test durations are recorded in the raw log. They are **not** timing
evidence: the run shares the host with foreign processes and was never intended
as a measurement.

These 13 pre-existing tests were already passing on this base; running them
shows the `CMakeLists.txt` edit and the new source file do not disturb them. It
is **not** evidence about staging, because no staging code runs in any of them.

The CUDA-labelled tests (`CudaWrapperUploadFailure`) are not in this list: this
is a CPU-only build, so they were never configured. They are **unrun**, not
passing.

## 4a. Corrected capacity accounting (Codex review of `dba0891e`)

Two P2 findings on the capacity model, both confirmed against the source before
being fixed. Neither changes the §8 decision; both make the calculator honest
about costs that push in the same direction.

| finding | old model | corrected |
| --- | --- | --- |
| repair schedule omitted from the host budget | `schedule_host_bytes` not modelled at all | `3·n_bad·sizeof(int) + n_bad·F·(sizeof(Draw) [+ sizeof(float)])`, all products overflow-checked |
| `Iframes` double-counted with no staging | `2·real + r2c` | `real + r2c`, via an explicit `staged_aliases_resident` flag |

The alias is deliberately narrow — whole movie **and** retained real stack
**and** 4-byte samples. A partial chunk is a genuinely separate ring and a
compact `uint16` buffer is a genuinely separate narrower allocation, so neither
aliases; both are asserted.

The alias also makes `host_bytes` **non-monotone**: it drops at
`chunk == n_frames`. `largestChunkWithin` now evaluates the whole movie first
and binary-searches only `[1, n_frames-1]`. `MonotonicHostBytes` asserts both
the monotone interval and the drop.

### Why these were not caught here

Recorded because the pattern is the same one this task keeps hitting:

- The double count **contradicted this project's own ADR §4.1 phase table**, and
  nothing compared the two.
- It produced the **right number for the wrong reason** — the default policy
  reported 3.820 GiB, exactly the phase-D figure, but by double-counting
  `Iframes` rather than by charging `Irefframes`.
- An **existing test asserted the double count as correct**, labelled "reproduces
  today's numbers exactly". It did not. That assertion has been replaced.

### Discrimination controls

Each new control computes the **old** model's answer inline and asserts the two
disagree, so it cannot pass against either model. Backed by mutants that revert
each fix — see §4.2.

## 5a. Accepted limitations

Raised by independent review of the final head, judged non-blocking by that
reviewer, and **deliberately not fixed** — changing source after requesting a
corrected-head verdict would invalidate the verdict, which is the whole point of
having asked for one. Recorded here so they are not rediscovered as surprises.

- **The self-assignment test's discrimination is allocator-dependent, not
  structural.** Without the guard, `reset(new bool[n])` allocates the new block
  before freeing the old, so `std::copy` copies recycled heap onto itself.
  Whether `badCount()` then differs from 6 depends on what the allocator hands
  back. It is overwhelmingly likely to differ after `makeMovie` has churned the
  heap — and did, on this platform — but reading uninitialised memory cannot be
  observed deterministically, so this class of defect has no deterministic test.
  Treat that mutant kill as **platform evidence, not proof**. No better
  formulation is available.
- **A chunk-1 overflow reports `InvalidInput`.** `largestChunkWithin`'s header
  says `InvalidInput` means the geometry or policy is malformed. An overflow at
  chunk 1 — which needs `n_frames · nx · ny > ~4.6e18`, a representability limit
  on an absurd geometry rather than a caller mistake — also lands there. The
  forwarded `Budget::error` string is specific and truthful, so no caller is
  misled, and it does not reintroduce the malformed-policy-as-inadmissible
  failure that motivated the enum.
- **`"Movie copy is deep, not aliased"` overclaims in its label.** The
  "not aliased" half cannot fail: `unique_ptr` is non-copyable, so a shallow
  copy would not compile. What it observes is that `std::copy` ran with the
  right size.
- **`MonotonicHostBytes` samples four policy shapes, not the parameter space**,
  and checks value monotonicity rather than failure-set upward-closure. The
  latter needs overflow-scale geometries and was verified analytically by the
  reviewer instead of by execution.
- **The standalone raw-gain untouched-frames check is now subsumed** by the
  in-loop check across all four chunk sizes. Redundant, not wrong.

## 6. Negative controls that do not exist yet

Recorded so the gap is visible rather than implied:

- There is no negative control showing that a *correct* staged pipeline produces
  the same 24-movie outputs, because no staged pipeline exists.
- There is no control distinguishing a sampled RSS maximum from an allocator
  trace, because no memory was measured.
- The `Irefframes` bit-exactness argument has no test. It needs one before the
  change it motivates is made.
- The multi-GPU aggregate host budget (ADR §7a.2) is stated but not enforced and
  not tested: `largestChunkWithin` is per-process and cannot see its siblings.
  A caller that sizes every worker against the whole host budget will pass every
  check here and still exhaust the host.
- The index mapping of ADR §7a.1 is stated, not implemented: no staged record
  type exists to carry `frames[]`, and the EER and compressed-MRC mappings are
  written down but unrun.
- Cancellation, producer/consumer abort and resume are undesigned here by
  deliberate choice (ADR §7a.3), deferring to #94 and #69 rather than defining a
  competing contract.
- The two hazards in ADR §9.1 are recorded from #94's review of their own
  branch, not reproduced here. Neither is testable against this branch: nothing
  in the component owns a byte reservation or a heap allocation, so there is no
  destruction-order hazard to exercise and no override counter to overcount.
