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
| `src/frame_staging_plan.h` | `ee63ab0b1f739924f8f6291cf0229aa4efbb03f850c59733095532e0959b3b40` |
| `src/frame_staging_plan.cpp` | `6cd456c40eb535acd9e88220b59c804b6d1a4dc7db8e1d922993d17ba922bd90` |
| `tests/test_frame_staging.cpp` | `942e7f7d4e9f372f46c5ee0dd054522a45a40ffdbe43cae979f152e7ca5be95e` |
| `CMakeLists.txt` | `56b061af41eea804d886bd82b4c8b2e5ae2d5f66893ea2c7793d753fbbf53875` |
| `build-cpu/frame_staging` (binary) | `e9c77ae5fe74a5f35469968bba0a3de2018297662b7eee1d4da9248a834de4a3` |

These are the hashes of the exact files committed on this branch, at the final
head, taken in the same locked run that produced the results below
(`raw/05-validationlock-final.log`). The pre-review hashes quoted in the first
revision of this report belonged to a source tree that no longer exists; they
are not reproduced here.

## 4. Commands and results

### 4.1 Component test

```
cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON     # exit 0
cmake --build build-cpu --target frame_staging -j8                        # exit 0
./build-cpu/frame_staging                                                 # exit 0
  -> 256 checks, 0 failures
```
(`raw/05-validationlock-final.log`)

Coverage of the 235 checks:

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

**Current epoch, final head** (`raw/04-validationlock-mutants.log`). These four
target the specific defects the independent review found, so that the fixes are
shown to be covered rather than merely applied:

| injected bug | result |
| --- | --- |
| replacement buffer transposed back to bad-pixel-major (review finding 1) | **test exit 1** — caught by "recorded sparse replacements match the reference, in the runner's frame-major layout", on every fixture and chunk size |
| gain multiply dropped on neighbour gather (review finding 2) | **test exit 1** — caught on `raw-gain-11f` only, at every chunk size, which is the fixture added for exactly this |
| `write_in_place` ignored, raw host frames clobbered (review finding 3) | **test exit 1** — caught by the frame comparison on `raw-gain-11f` |
| `d_max > 4` bound removed | **test exit 1** — 2 failures, both in the rejection-path group |

After reverting, the source hash returned to
`6cd456c40eb535acd9e88220b59c804b6d1a4dc7db8e1d922993d17ba922bd90`, which is the
pre-`largestChunkWithin` head, and the suite returned 247 checks, 0 failures.
The final head at 256 checks adds only the three-way admission group.

Two observations that limit what this control proves, recorded rather than left
implicit:

- The third old-epoch bug is caught even at chunk = full movie, because slot
  ordering is a correctness property independent of chunking. A control that
  only varied the chunk size would not have been sufficient on its own.
- **Every mutant was injected into the component, never into the oracle.** The
  oracle is `referenceRepair` in `tests/test_frame_staging.cpp`, a hand
  transcription of `motioncorr_runner.cpp:1732-1775`. This control therefore
  cannot detect drift between that transcription and the runner — the one
  failure mode that would invalidate the whole differential test. That was
  checked by reading, including by an independent reviewer who compared the two
  line by line, but it is not covered by execution.

### 4.3 Whole-project build and existing CTest suite

Run to show the `CMakeLists.txt` edit does not disturb the existing targets or
tests. See §5.

## 5. Existing test suite

```
cmake --build build-cpu -j8            # whole project, exit 0
ctest --output-on-failure              # exit 0
```

14/14 passed in 7.03 s, on the same CPU-only `Release` build described in §2.2
(`raw/05-validationlock-final.log`):

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
