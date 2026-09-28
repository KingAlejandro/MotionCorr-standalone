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

- `motioncorr::staging::buildSchedule` / `applyChunk` reproduce the production
  hot-pixel repair (`src/motioncorr_runner.cpp:1732`) bit-for-bit, for every
  tested chunk size, and leave the process RNG in the same state.
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

| field | value |
| --- | --- |
| host | `small-refmac-machine` (cpu64) |
| kernel | Linux 6.8.0-86-generic x86_64 |
| topology | 2 NUMA nodes; node0 = cpu 0–31, node1 = cpu 32–63; 115839 / 115862 MB |
| binding | `numactl --cpunodebind=1 --membind=1`, node-local; `-j8` |
| serialisation | `flock /tmp/motioncorr-issue96-cpu.lock` held for every build and run |
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

## 3. Source and binary hashes (SHA-256)

| file | sha256 |
| --- | --- |
| `src/frame_staging_plan.h` | `1821b8b006620a1444a9d5b8aff8e03b8a20af1b08e81f1f16585224a2050cf8` |
| `src/frame_staging_plan.cpp` | `636021bb65152b486c91f99144eadb9321c1f6313f54d20f7f928d6c17cb8369` |
| `tests/test_frame_staging.cpp` | `475b9fa723496e8de77ecd886c5b1c613e2d9613e31fcabe544c8911991f9bd7` |
| `CMakeLists.txt` | `56b061af41eea804d886bd82b4c8b2e5ae2d5f66893ea2c7793d753fbbf53875` |
| `build-cpu/frame_staging` (binary) | `dc46de2045840161a9db159ba7ba3b8ed0d463cecacb8e791043d85c7784f1d1` |

These are the hashes of the exact files committed on this branch.

## 4. Commands and results

### 4.1 Component test

```
cmake -S . -B build-cpu -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON     # exit 0
cmake --build build-cpu --target frame_staging -j8                        # exit 0
./build-cpu/frame_staging                                                 # exit 0
  -> 235 checks, 0 failures
```

Coverage of the 235 checks:

| group | cases |
| --- | --- |
| capacity: published geometries | tutorial `3710×3838×24` real = 1366942080 B, r2c = 1367678976 B, sum = 2.547 GiB; `8192²×80` sum = 40.005 GiB |
| capacity: uncharged third stack | tutorial CPU reconstruction resident = `2·real + r2c` = 3.820 GiB |
| capacity: declared bound | staged bytes constant as F grows 4 → 4096 at fixed chunk |
| capacity: degenerate chunk | chunk 0 and chunk > F both clamp to the whole movie |
| capacity: compact upload | staged term and H2D both exactly halved; device unchanged |
| capacity: replay | H2D exactly doubled; staged bound unchanged |
| capacity: rejection | overflowing geometry, zero width, negative chunk, zero passes, negative extra bytes |
| ordering: sparse defects, 24 frames | chunks 1, 2, 3, 5, 24 |
| ordering: solid 5×5 block, 13 frames (odd) | chunks 1, 2, 4, 13 — reaches the Gaussian branch |
| ordering: corner and edge defects, 9 frames | chunks 1, 2, 4, 9 |
| ordering: non-square 57×29, EER radius `D_MAX=4`, 7 frames | chunks 1, 2, 3, 7 |
| ordering: `sigma == 0`, 5 frames | chunks 1, 2, 5 — `rnd_gaus` returns `mu` without consuming the stream |
| ordering: single frame; empty defect mask | chunks 1, 4 |

Each ordering case asserts: bit-identical frame buffers against a transcription
of the production loop; identical recorded sparse replacement values; an
identical process RNG tail; that the branch the fixture targets was actually
reached; that every `(pixel, frame)` decision is accounted for; and that the
branch choice is constant across frames for each masked pixel.

### 4.2 Intentional-bug control

The differential test is only evidence if it can reject a wrong implementation.
Three bugs were injected into `src/frame_staging_plan.cpp`, each built and run
under the same lock, then reverted:

| injected bug | result |
| --- | --- |
| `kNumMinOk` 6 → 5 (wrong branch boundary) | **test exit 1** — caught on `corners-9f`: pixel mismatch, RNG state mismatch, and the Gaussian-branch coverage assertion |
| schedule built frame-major instead of pixel-major (reorders the RNG stream) | **test exit 1** — caught on every fixture with more than one frame, at every chunk size including full |
| neighbour slot list enumerated `dx`-major (transposes `pbuf`) | **test exit 1** — caught on every fixture at every chunk size |

After reverting, the source hash returned to
`636021bb65152b486c91f99144eadb9321c1f6313f54d20f7f928d6c17cb8369` and the suite
returned 235 checks, 0 failures.

Note that the third bug is caught even at chunk = full movie: the slot ordering
is a correctness property of the component independent of chunking, so a test
that only varied the chunk size would not have been sufficient on its own.

### 4.3 Whole-project build and existing CTest suite

Run to show the `CMakeLists.txt` edit does not disturb the existing targets or
tests. See §5.

## 5. Existing test suite

```
cmake --build build-cpu -j8            # whole project, exit 0
ctest --output-on-failure              # exit 0
```

14/14 passed in 7.67 s, on the same CPU-only `Release` build described in §2:

| # | test | result |
| --- | --- | --- |
| 1 | `FrameStaging` (new) | Passed, 0.00 s |
| 2 | `SyntheticRegression` | Passed, 1.12 s |
| 3 | `HotPixelRngDeterminism` | Passed, 0.56 s |
| 4 | `RunnerExposure` | Passed, 0.47 s |
| 5 | `Runner_failure` | Passed, 0.12 s |
| 6 | `Runner_invalid` | Passed, 0.11 s |
| 7 | `Runner_resume` | Passed, 2.11 s |
| 8 | `Runner_tomography` | Passed, 0.39 s |
| 9 | `RunnerLateBin` | Passed, 0.62 s |
| 10 | `RunnerExportedUnits` | Passed, 0.10 s |
| 11 | `GainCache` | Passed, 1.25 s |
| 12 | `TiffRead` | Passed, 0.55 s |
| 13 | `DamagedMovie` | Passed, 0.10 s |
| 14 | `RunnerModelParser` | Passed, 0.18 s |

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
