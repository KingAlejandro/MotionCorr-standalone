# ADR — Bounded frame/chunk staging and compact transfers (issue #95)

| field | value |
| --- | --- |
| issue | #95 |
| status | **Proposed — partial no-go.** See [Decision](#8-decision-and-gono-go). |
| base | main `4c952b3f54479653512c4d208e09c9a8c02f3726` |
| branch | `round96/95-claude-opus-5` |
| supersedes | nothing |
| coordinates with | #94 (next-movie prefetch, owns runner integration), #53 (admission), #69 (failure contracts), #92 (input integrity), #26 (measurement), #85 (decoder) |

> Every byte figure in this document is a **calculated array size**, derived from
> the declared geometry and the allocations in the source. None of it is a
> measured RSS or a measured device high-water. Measurement requests are
> collected in [§10](#10-measurement-request-for-26). The one thing here that is
> *executed and tested* is the repair draw schedule in
> [§5.2](#52-the-repair-rng-stream-is-data-independent).

---

## 1. Scope

Decide whether decoding/uploading frames or small chunks just in time — instead
of retaining every raw float host frame for a movie — reduces peak memory enough
to justify the change, and deliver one bounded component prototype.

Out of scope, deliberately: any generic allocator framework, any pipeline
rewrite, any arithmetic/FFT/precision change, any default promotion, and any
second movie loader. Runner integration stays with #94.

Precisely what this branch does to the build: `src/frame_staging_plan.cpp` is
picked up by the existing `GLOB_RECURSE` in `CMakeLists.txt`, so it compiles
into `motioncorr_core` and is linked into the `motioncorr` executable. It has
**zero call sites** and no namespace-scope dynamic initialisers, so no existing
target changes behaviour — but "does not modify the production pipeline" should
be read as "adds an unreferenced object file", not "does not touch the binary".

---

## 2. What the pipeline actually does with frame data

Traced from `MotioncorrRunner::executeOwnMotionCorrection`
(`src/motioncorr_runner.cpp:1260`) at main `4c952b3f`.

```
read  ──►  gain × frame, accumulate Isum   ──►  global hot-pixel statistics
                                                  (BARRIER: needs all F frames)
       ──►  ordered sparse repair          ──►  forward FFT
       ──►  iterative global alignment     ──►  inverse FFT
       ──►  patch extract / local align    ──►  reconstruction (± dose weighting)
```

### 2.1 Per-stage host buffer lifetime and ownership

`F` = frames processed, `W`×`H` = pixels, `nfx = floor(W/2)+1`.
"resident" means the buffer holds all `F` frames at once.

| buffer | bytes | created | last consumer | owner | resident? |
| --- | --- | --- | --- | --- | --- |
| `Iframes` | `4·F·W·H` | read loop, `:1409` | CPU path: forward FFT, cleared per frame at `:1865`. Resident CUDA path: **never cleared**, kept as the fallback mirror for the whole movie. | runner | yes |
| `Iframes` (2nd life) | `4·F·W·H` | global inverse FFT, `:2024` | reconstruction | runner | yes |
| `Fframes` | `8·F·H·nfx` | forward FFT, `:1858` | dose weighting. Explicitly *not* freed after the inverse FFT (`:2026`, "cannot deallocate Fframes here because of dose-weighting"). | runner | yes |
| `Irefframes` | `4·F·W·H` | `:2394`, only when `!do_dose_weighting \|\| save_noDW \|\| even_odd_split` | the reduction into `Iref`/`Iref_even`/`Iref_odd` immediately after | runner | yes |
| `Isum` | `4·W·H` | `:1432` | hot-pixel detection; `Isum.clear()` at `:1709` | runner | no |
| `bBad` | `1·W·H` | `:1522` | repair loop | runner | no |
| `Igain` | `4·W·H` | cached across movies, `gainReferenceFor()` | every movie | runner (static cache) | no |
| `resident_bad_replacements` | `4·n_bad·F` | `:1729` | `updateDefectPixels()` | runner | sparse |
| `PS_sum`, `F_ps`, `F_ps_small` | `O(W·H)` | PS block, `:1872` | PS write | runner | no |
| `Iref`, `Iref_even`, `Iref_odd` | `3·4·W·H` | `:1995` | output write | runner | no |

Device buffers (`CudaMovieSession`, `src/acc/cuda/cuda_movie_session.h`):
`d_Iframes` `4·F·W·H`, `d_Fframes` `8·F·H·nfx`, `d_Isum` `4·W·H`, `d_gain`
`4·W·H`, `d_fft_work` (cuFFT workspace, `max(r2c, c2r)`, batch 1),
`d_inverse_tile` `8·H·nfx`, plus the patch cache `d_Ipatches` and the caller's
`d_patch_fcomplex_buffer` `8·n_groups·patch_h·patch_nfx`.

### 2.2 Copies and passes

| path | decodes of the encoded input | H2D | D2H |
| --- | --- | --- | --- |
| CPU | 1 | — | — |
| legacy CUDA (`use_gpu`, no session) | 1 | per-stage, frames up and down around each CUDA call | same |
| resident CUDA session | 1 | `4·F·W·H` once (`applyGainDefectsAndSum`, `cuda_movie_session.cu:403`) + `4·W·H` gain | `4·W·H` sum only, plus whatever a fallback downloads |

The resident session already achieves the "upload once" property. There is no
per-frame bounce left to remove on the happy path.

---

## 3. Replay and random-access consumers

This is not a one-pass streaming algorithm. The consumers that genuinely revisit
data:

1. **Global hot-pixel statistics.** `mean`, `std` and `threshold` are reductions
   over the complete unaligned sum. No repair decision can be made until the
   last frame has been added. This is a hard barrier and no design removes it.
2. **Hot-pixel repair neighbourhoods.** For each masked pixel and each frame,
   the repair reads a `(2·D_MAX+1)²` window (`D_MAX` = 2, or 4 for EER) of that
   same frame. Reads are frame-local and never cross frames.
3. **Iterative global/local alignment.** Operates entirely on `Fframes` /
   `d_Fframes` and revisits all frames many times. Input pixels are not involved.
4. **Reconstruction.** Consumes real frames regenerated from `Fframes` by the
   inverse FFT — not the input.
5. **Fallbacks.** `materialize_host_frames()` (`:1440`) and
   `downloadRealFrames()` require a retained host frame stack. See [§7](#7-fallback-contracts).

So the **encoded input is consumed exactly twice** on the current code path, both
in ascending frame order, with one barrier between them: pass A is the fused
gain+sum (`:1493`), pass B is repair + forward FFT. Everything after the forward
FFT is derived data.

---

## 4. Memory formula

Implemented and tested in `src/frame_staging_plan.{h,cpp}` — the ADR and the test
suite share one implementation so they cannot drift.

```
real  = 4·F·W·H
r2c   = 8·F·H·(floor(W/2)+1)

staged_host   = staged_bytes_per_sample · C · W · H        # C = chunk frames
resident_host = [Iframes]·real + [Irefframes]·real + [Fframes]·r2c
host_total    = staged_host + resident_host + extra_host
device_total  = [resident]·(real + r2c) + extra_device
h2d           = staged_bytes_per_sample · F · W · H · input_passes
```

`extra_host` must name, not omit: decoder strip scratch, the gain reference, the
defect mask, `Isum`, the three output images, pinned staging, and allocator
overhead. `extra_device` must name the cuFFT workspace, the inverse tile and the
patch cache. Every product above is overflow-checked; the calculator refuses
rather than wrapping.

Published geometries, reproduced exactly by `tests/test_frame_staging.cpp`:

| geometry | real | r2c | real+r2c |
| --- | --- | --- | --- |
| tutorial `3710×3838×24` | 1.2731 GiB | 1.2738 GiB | **2.5468 GiB** |
| `8192²×80` | 20.0000 GiB | 20.0049 GiB | **40.0049 GiB** |

### 4.1 Where the high-water actually sits

Applying the formula phase by phase to the tutorial geometry:

| phase | live whole-movie stacks | GiB |
| --- | --- | --- |
| A. read → gain+sum → repair | `Iframes` | 1.273 |
| B. forward FFT loop (CPU: frames cleared as transformed) | `Iframes` draining into `Fframes` | ≈1.274 |
| C. after global inverse FFT | `Iframes` + `Fframes` | 2.547 |
| D. CPU reconstruction, `!do_dose_weighting \|\| save_noDW \|\| even_odd_split` | `Iframes` + `Irefframes` + `Fframes` | **3.820** |
| A′. resident CUDA, whole movie | host `Iframes` (raw mirror) | 1.273 host **+ 2.547 device** |

**Phase A is not the peak on the CPU path.** Bounded input staging shrinks phase
A and nothing else, because phases C and D hold frames that were regenerated from
`Fframes`, not read from the input. This is the single most important result in
this ADR and it is what drives [§8](#8-decision-and-gono-go).

---

## 5. Findings

### 5.1 A third full-movie host stack is uncharged

The `real`/`r2c` arithmetic in the #95 task comment covers `Iframes` and
`Fframes`. The CPU reconstruction branch also allocates `Irefframes` at `:2394`
via `Irefframes[iframe]().initZeros(Iframes[iframe]())`, while `Iframes` is live
and `Fframes` is explicitly retained. Calculated high-water for that branch is
`2·real + r2c` = **3.820 GiB**, not 2.547 GiB.

`realSpaceInterpolation_withoutsum` (`:2607`) writes each frame independently
(`Ialignedframes[iframe] = 0 + val`), and the caller (`:2408`) immediately
reduces the stack into `Iref` and, for the even/odd split, into `Iref_even` /
`Iref_odd`, in ascending frame order. Fusing the two loops to one scratch frame
gives `0 + val` then the same ascending accumulation — arithmetically identical,
bit for bit — and removes `4·F·W·H`.

That is a **calculated 33% reduction of the CPU high-water with no streaming, no
chunking and no re-decode** — an argument from the source, not a measurement and
not a run. It is not implemented here: it edits the shared runner that
#94 and #53 are working in, and it is a different change from staging. It is
recorded so it is not double-implemented, and so no future "staging saves X"
claim credits staging for it.

### 5.2 The repair RNG stream is data-independent

The repair loop (`:1732`) is bad-pixel-major, frame-minor, drawing from one
`rand()` / `rnd_gaus()` stream seeded once by `init_random_generator(random_seed)`.
That loop order appears to force full-movie residency: chunking by frame would
reorder the draws and change every replacement value.

It does not, because `n_ok` — the count of in-bounds, non-masked neighbours —
reads `bBad` and the image bounds only. It never reads a pixel. So for a given
masked pixel `n_ok` is **identical for every frame**, and therefore:

- the branch `n_ok > NUM_MIN_OK` is fixed before any frame is decoded;
- the number and kind of draws consumed per (pixel, frame) is fixed;
- the entire draw schedule can be materialised in the original order with zero
  frame data, and then applied to frames in any chunking.

**Scope of that statement, stated precisely.** The schedule can be built before
the *second* residency pass, not "before any frame is decoded". Both of its
inputs come out of the completed first pass: `bad_mask` is `bBad`, thresholded
from the unaligned sum over every frame, and `frame_std` is `std / n_frames`
from the same statistics. Since `rnd_gaus` consumes zero draws when
`sigma == 0`, even the draw *count* is only fixed once that pass is done. What
Claim 2 buys is that the second pass may then be chunked — which is exactly the
pass a staged design wants to chunk. An earlier draft of this ADR overstated
this; the implementation was always correct, the prose was not.

Repair also writes only masked pixels and reads only non-masked neighbours, so
no repair ever reads another repair's output: the (pixel, frame) decisions are
mutually independent given the schedule.

This is implemented as `motioncorr::staging::buildSchedule` / `applyChunk` and
tested differentially against a transcription of the production loop for chunk
sizes 1, 2, 3, 5, uneven and full, over sparse/blocked/corner/non-square/EER-radius
masks, odd frame counts, single-frame movies, empty masks and `sigma == 0` (where
`rnd_gaus` returns `mu` without consuming the stream). The tests assert
bit-identical frames, identical recorded sparse replacements, an identical
process RNG tail, and that both branches were actually reached. A deliberately
broken naive frame-major chunking is run through the same comparison and must be
rejected.

`buildSchedule` calls the real `rnd_gaus` rather than reimplementing Box–Muller,
because `rnd_gaus` caches its second deviate in a file-static across calls
(`src/funcs.cpp:575-576`) and short-circuits on `sigma == 0`. A reimplementation
would have to reproduce both to stay in step; calling it does so by construction.

### 5.3 On the resident CUDA path the host frame stack is a pure mirror

With a live `CudaMovieSession`, `host_frames_are_raw` is set and `Iframes` is
never cleared (the clear loop at `:1844` is guarded by `if (!movie_session)`).
The host stack has exactly two remaining consumers: the repair neighbourhood
gather (`:1752`, which multiplies by gain on the fly) and the fallbacks. It
contributes nothing to the happy path.

The device already holds `d_Iframes` gain-corrected, computed as `val *= gain_val`
by `fusedGainAndSumKernel` — the same single float multiply as the host's
`neighbor *= Igain`, so a device-side gather would be bit-identical. Combined
with §5.2, both host consumers of the raw mirror are removable *in principle*.
That change belongs to the CUDA session (#50/#69 territory) and is not proposed
here; it is recorded as the prerequisite for any host-side staging on the GPU path.

---

## 6. The two bounded alternatives

### A. Two-pass input (replay)

Pass 1 decodes each frame, applies gain, accumulates `Isum`, discards. Barrier:
statistics, `bBad`, draw schedule. Pass 2 decodes each frame again, applies gain,
applies the schedule, FFTs into `Fframes`, discards.

| | value |
| --- | --- |
| host saving | `4·(F−C)·W·H`, **in phase A only** |
| host high-water after the change (CPU, tutorial) | still 3.820 GiB (phase D), or 2.547 GiB (phase C) — **unchanged** |
| device | unchanged |
| input decodes | 1 → **2** |
| H2D | unchanged on CPU; ×2 on the GPU path |
| ascending frame arithmetic | preserved (both passes ascending; `Isum` accumulation order unchanged) |
| #92 interaction | **re-reads a file that may be growing or truncated.** Pass 2 can observe different bytes from pass 1 with no detection. Requires an input-stability contract that does not exist. |

### B. Resident device + bounded host ring

Host stages `C` frames; the device keeps the full `d_Iframes` / `d_Fframes`.

| | value |
| --- | --- |
| host saving | `4·(F−C)·W·H` = 1.273 GiB for the tutorial, **for real**, because on the GPU path the stack survives the whole movie (§5.3) |
| device | **unchanged — still `real + r2c` resident.** Bounded host is not a bounded pipeline. |
| input decodes | 1 |
| H2D | unchanged |
| prerequisites | §5.2 schedule (delivered) **and** a device-side repair gather (not delivered) **and** a changed fallback contract (§7) |
| binding constraint | the geometry that motivates this work, `8192²×80`, needs **40.0 GiB of VRAM**. Host RAM is not the limit there; device memory is. B does not move that number by one byte. |

### C. Compact unsigned-16 upload (variant, orthogonal to A/B)

Upload raw `uint16` samples and convert + apply gain on the device, for the one
explicitly supported `bitsPerSample == 16, SAMPLEFORMAT_UINT` TIFF path
(`src/rwTIFF.h:106`).

| | value |
| --- | --- |
| staged host term | halved (`2·C·W·H`) |
| H2D | halved: 1.273 → 0.637 GiB per tutorial movie |
| device | unchanged |
| must preserve | the per-row Y flip applied during strip decode (`src/rwTIFF.h:262`), decoded ordering, the float conversion and gain rounding, and the defect statistics computed from them |
| explicitly **unrun** | packed 4-bit, `int16`, `uint8`/`int8`, `float32` TIFF, EER, compressed MRC. One format is supported; the rest are separate rows, not generalisation. |

Halving payload bytes is arithmetic. Whether it changes wall time is a
measurement, not a claim — see [§10](#10-measurement-request-for-26).

---

## 7. Fallback contracts

Bounded staging deletes exactly the buffer the advertised fallbacks need. There
are three honest options and each path must pick one:

| failing path | today | under bounded staging | verdict |
| --- | --- | --- | --- |
| CUDA fused gain+sum fails (`:1473`) | reset `Isum`, redo on host from retained raw frames | raw frames are gone | **re-decode** — the only option that does not depend on the device that just failed. Requires the #92 input-stability contract. |
| hot-pixel host-statistics fallback (`:1581`) | `downloadUnalignedSum` | unchanged — the sum is one frame, never staged | **no change** |
| Gaussian replacement needs host statistics (`:1687`) | redo detection with host statistics | unchanged | **no change** |
| resident forward FFT fails (`:1850`) | `materialize_host_frames()` from the raw mirror | mirror is gone | **re-decode**, or fail closed |
| patch prep falls back (`:2111`) | `downloadRealFrames` | frames are *aligned* and only exist on the device | **download** — valid, the device is alive by construction here |
| unweighted / DW reconstruction falls back | `downloadRealFrames` / `downloadFourierFrames` | same | **download** — valid |
| **device allocation itself fails** | session never starts; CPU path with full host frames | — | staging must **not** be enabled on the CPU path at all (§8), so this stays as it is |

Where the answer is "re-decode", the contract change must be explicit: on
re-decode failure the movie fails with a clean nonzero status and no output
file, log line or STAR row claiming success. No partial-success marker. This is
a change to #69's failure matrix and must be agreed there before implementation.

---

## 7a. Index mapping, aggregate budgets, and cancellation

An independent spec audit found these three required by the issue body and
absent from an earlier draft of this ADR. Two are designed below; the third is
declared undesigned, with an owner.

### 7a.1 Frame index, exposure and grouping mapping

There are three index spaces and a staged chunk must carry the map between
them, or exposure and STAR rows silently shift.

| space | definition | consumers |
| --- | --- | --- |
| original | 0-indexed position in the file, `0 .. nn-1` | readers |
| selected | `frames[]`, built at `:1326` by filtering on `first_frame_sum` / `last_frame_sum` | everything below |
| group | `group_start[]` / `group_size[]` over the **selected** space, `:1347` | local patch alignment |

`frames[iframe]` maps selected → original and is *not* generally `iframe`. It is
read by: dose weighting, `doses[iframe] = pre_exposure + dose_per_frame *
(frames[iframe] + 1)` (`:2475`); the global trajectory,
`mic.setGlobalShift(frames[i] + 1, ...)` (`:1992`); and `mic.first_frame =
frames[0] + 1` (`:2553`). Local trajectories use a different origin again:
`mic.patchZ.push_back(z + first_frame_sum)` (`:2304`).

Therefore a staged chunk is a contiguous range **in the selected space**, and
the staging record must carry `frames[]` for its range, not just a start and a
count. A chunk that carries only `[first, first+C)` and lets the consumer assume
`original == selected` produces correct pixels with wrong exposures whenever
`--first_frame_sum > 1`, which no pixel comparison would catch.

Grouping is a second, independent partition of the selected space, and the group
boundaries do **not** align with staging chunk boundaries in general. Groups are
consumed only after the forward FFT, from `Fframes`/`d_Fframes`, so a staged
input chunk never has to respect them — but a design that tried to stage the
*patch* stage would, and that is a different change.

EER multiplies the mapping: selected frame `f` renders original EER frames
`[f*eer_grouping + 1, (f+1)*eer_grouping]` (`:1405`), so one staged frame is
`eer_grouping` decode units. Compressed MRC uses `readFrameInto(.., frames[i])`
directly. Both are **unrun** here; only the mapping is stated.

### 7a.2 Multi-GPU aggregate host-staging budget

`staging::computeBudget` is **per process**. The issue's requirement that "one
reader per GPU must not multiply memory without a bound" is a property of the
caller, not of this calculator, and must be written down as such:

```
host_total_across_workers = n_workers · (staged_host + resident_host + extra_host)
```

with `n_workers` the number of concurrent MotionCorr processes on the host, not
the number of GPUs — they differ whenever a GPU is idle or oversubscribed. The
bound that matters is `host_total_across_workers ≤ host_budget`, so the
per-process staged bound must be derived by **dividing** the host budget by
`n_workers` before calling `largestChunkWithin()`, not by sizing each worker
independently against the whole host. Charging each worker the full host budget
is the failure mode this requirement exists to prevent, and nothing in the
calculator stops a caller doing it — hence this paragraph.

This interacts with #53's admission and #66's aggregate CPU budget. It is
**stated, not enforced and not tested**: there is no multi-process test here,
because there is no staged pipeline to run in multiple processes.

### 7a.3 Cancellation, producer/consumer abort and resume

**Declared undesigned in this ADR, with an owner.**

The delivered component has no cancellation surface: `buildSchedule` and
`applyChunk` are synchronous, own no memory beyond their outputs, start no
threads and hold no file handles, so there is nothing to cancel, join or leak.
That is a property of the component, not an answer to the requirement.

A staged *pipeline* would need: waking a producer blocked on staging capacity,
joining before destroying shared state, not freeing a buffer still referenced by
a pending upload, and preserving #91's per-movie failure isolation and the
existing non-prefix resume contract. All four are the same contracts #94 is
already building for the prefetch producer, and #69 owns the failure matrix.
Designing a second, competing set here is exactly the duplication #66 forbids.
Under the §8 no-go there is no staged pipeline to attach them to; if the compact
upload variant is ever built, it inherits #94's contracts rather than defining
new ones.

---

## 8. Decision and go/no-go

**No-go on bounded frame/chunk input staging as a peak-memory measure, on
calculated evidence, for both paths — for different reasons.**

- **CPU path: no-go, and the reason is structural.** Input staging shrinks
  phase A (1.273 GiB), which is not the high-water. The high-water is phase D
  (3.820 GiB) and phase C (2.547 GiB), both dominated by data regenerated from
  `Fframes`. Staging the input cannot reduce the CPU high-water by a single
  byte. Adding a second decode (alternative A) buys nothing and costs a full
  re-read plus a #92 hazard.
- **GPU path: no-go as scoped, deferred rather than refused.** Alternative B
  does remove a real 1.273 GiB host mirror, but (i) it needs a device-side
  repair gather and a changed fallback contract before it is even correct,
  (ii) it leaves the device at `real + r2c`, so the pipeline is not bounded, and
  (iii) on `8192²×80` the binding constraint is 40.0 GiB of VRAM, which B does
  not touch. Spending a runner-integration slot on it now, while #94 owns that
  interface, is not justified by 1.273 GiB of host RAM.
- **Compact upload (C): conditional go, measure first.** It is the only variant
  with a benefit that is not cancelled by a stack left resident: it halves H2D
  unconditionally, for one declared format, without changing residency anywhere.
  It should not be built before #26 reports whether H2D is on the critical path.

**Go on two things, both small and both separate PRs:**

1. **The draw schedule component** — delivered and tested in this PR. It is the
   prerequisite for every design above, and it is worth landing on its own
   because it converts "the RNG order forbids chunking" from an assumption into
   a tested fact.
2. **`Irefframes` fusion** (§5.1) — calculated 1.273 GiB, 33% of the calculated
   CPU high-water, **argued bit-exact from the source but not built and not
   run**, no streaming. Not in this PR: it belongs to whoever holds the runner
   integration slot, and it needs its own test and its own 24-movie evidence
   before the bit-exactness claim is more than an argument. Recommended as the
   next memory change, ahead of any staging work.

**Not proposed:** any generic allocator, any staging in the runner, any default
change, any second loader, any precision or gate change.

---

## 9. Interface agreement with #94

#94 owns the input-buffer ownership interface and runner integration; this ADR
does not define a competing one. The two properties #95 asks #94 to preserve so
that staging remains possible later, at zero cost today:

1. **A decoded movie record must be able to describe a partial frame range.**
   Not implement it — just not hard-code "one record = all frames" into the type,
   so a chunked producer is a later change rather than a rewrite.
2. **The byte reservation must be charged per live allocation, not per record.**
   Already #94's corrected position: the reservation transfers with ownership and
   is released exactly once on actual destruction or reuse-accounting. A staged
   producer charges `staged_bytes_per_sample · C · W · H` per in-flight chunk,
   which is the same accounting with a different multiplier.

Nothing else is required. `staging::computeBudget` is a calculator, not an
allocator, and #94 is free to ignore it.

**Confirmed with #94 on 2026-09-28** (branch `round96/94-claude-opus-5`, ADR
`agents/designs/issue_94_bounded_prefetch.md`): both properties already hold.
`MoviePrefetchRecord` carries an explicit `std::vector<int> frames` rather than
an implicit whole-movie range, and reservations are taken before allocation,
transferred on move and released exactly once. #94 independently reproduced both
memory findings in §5.1 and §5.3.

#94 also raised a point this ADR should adopt. Their `movieio::ByteBudget`
distinguishes **three** outcomes, not two: "cannot ever be admitted, fall back",
"must wait for capacity", and "granted over budget but counted". A capacity
calculator that only answers "how many bytes" can recommend a chunk that can
never fit, and an evidence trail that only records success cannot tell "the
bound held" from "the bound was overridden N times". `largestChunkWithin()` in
the component returns the first of those three explicitly, so a caller cannot
silently proceed with an inadmissible chunk.

---

## 10. Measurement request for #26

Not requesting a slot; these ride along with work #26 is already doing.

| # | question | what to record |
| --- | --- | --- |
| M1 | Is the calculated 3.820 GiB CPU high-water real? | peak process RSS for one tutorial movie with `--save_noDW` and with `--even_odd_split`, versus the dose-weighting-only run. Allocator trace, not a sampled maximum. |
| M2 | Is the resident-CUDA host mirror real? | simultaneous host RSS and device high-water for one tutorial movie on the resident path. Expect ≈1.27 GiB host that never falls until the movie ends. |
| M3 | Is H2D on the critical path? | H2D bytes and time for `applyGainDefectsAndSum` as a fraction of movie wall time. If it is under a few percent, variant C is not worth building. |
| M4 | What does a second decode cost? | wall time of the read loop alone, cold and warm page cache, for one tutorial TIFF movie. This prices alternative A's re-read. |

M1 and M4 are CPU-only and could run on cpu64 under the existing lock without a
GPU slot. M2 and M3 need the device.

---

## 11. What is unrun

- No GPU execution of any kind in this task. All device figures are calculated.
- No measured RSS. All host figures are calculated array sizes.
- No end-to-end run of the 24 tutorial movies for this change, because this
  change does not touch the pipeline.
- Formats: only the `uint16` TIFF path is analysed for variant C. Packed 4-bit,
  `int16`, 8-bit, `float32` TIFF, EER and compressed MRC are **unrun**, not
  assumed equivalent.
- The device-side repair gather of §5.3 is analysed, not implemented or tested.
- `Irefframes` fusion is argued to be bit-exact from the source; it is **not**
  built or run. That claim needs its own PR and its own 24-movie evidence.
- The multi-GPU aggregate host budget of §7a.2 is **stated, not enforced and not
  tested**. The calculator is per-process and cannot see its siblings.
- The index mapping of §7a.1 is **stated, not implemented**. No staged record
  type exists to carry `frames[]`, and the EER and compressed-MRC mappings are
  written down but unrun.
- Cancellation, producer/consumer abort and resume are **undesigned here** by
  the deliberate choice in §7a.3, not overlooked.
- The intentional-bug control injected bugs into the component only, never into
  the test's transcription of the production loop. It therefore cannot detect
  drift between that transcription and `motioncorr_runner.cpp:1732`; that was
  checked by reading, twice, not by execution.
