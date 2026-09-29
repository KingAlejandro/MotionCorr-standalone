# Issue #95 / #118 — the compact-ingest no-gain memory regression

Follow-up to [#118](https://github.com/KingAlejandro/MotionCorr-standalone/pull/118). Pinned
source, commands, raw records and every failed control are in this directory. No merge, no
promotion and no scientific claim is made here.

## 1. What was measured before this work

PR118's retained record reports an approximately **+0.230 GiB** no-gain peak-RSS increase over
current main with **no float widening recorded**, from SCARF jobs `3513069` and `3513072`, and
calls it reproducible and unexplained. Those runs are preserved; this directory does not replace
them.

Two things in the old explanation did not hold:

- The retained text attributes the no-gain behaviour to "non-converging patches materialise the
  float movie anyway". That is true and it happens in both arms, but it is a property of *main*
  as well, so it cannot explain a difference between the arms.
- `widen_fallback_logs: 0` was read as "no float movie was materialised". The widening fallback
  (`expand_u16_to_float`) is the only materialisation that logs. `downloadRealFrames()`, which
  the patch fallback calls and which allocates the full 1.2731 GiB float movie, logs nothing.

## 2. Attribution

**Job `3514042`, SCARF `gn0003`, gpu-devel, 1x A100-SXM4-40GB `GPU-460457fe-b9d1-4f25-66f4-e4bbb8bfd14f`,
8 logical CPUs `4-7,36-39`, glibc 2.34, THP `always`, `khugepaged/max_ptes_none=511`,
CUDA 12.8.61, g++ 11.5.0, Release `sm80` `-DTIMING=ON`.**
Main `a75a3f87f7ef17e0a29b1c91a1edecda08ebed34` (sha256 `347e11b6…c237b6`), candidate
`6827b314c013475a8c297cb27f3e6c19e030376d` (sha256 `b0311f96…9aaf6b`). 24 tutorial movies,
`--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150
--seed 1 --gpu 0 --j 8`, no gain. Peak RSS from `/usr/bin/time -v`.

| arm | peak RSS kB | vs main |
|---|---:|---:|
| main, run 1 | 1,607,748 | |
| main, run 2 | 1,608,096 | |
| **candidate, run 1** | **1,790,232** | **+182,484 kB** |
| **candidate, run 2** | **1,789,816** | **+182,102 kB** |
| candidate + `MALLOC_MMAP_THRESHOLD_=131072` | 1,593,452 | −14,470 kB |
| candidate + `MALLOC_ARENA_MAX=1` | 1,594,348 | −13,574 kB |
| candidate + `MALLOC_TRIM_THRESHOLD_=131072` | 1,597,292 | −10,630 kB |
| main + `MALLOC_MMAP_THRESHOLD_=131072` | 1,594,388 | −13,534 kB |

Three independent glibc tuning interventions each remove the whole increase, and each leaves the
candidate at or below main. The environment variables are diagnostics: none of them is the fix.

### Where the bytes are

A 5 ms external sampler snapshotted `/proc/<pid>/smaps` at every new high-water mark. Both arms
peak in the second movie (`20170629_00025`) during patch alignment, at the point where a patch
reports `converged=no` and `downloadRealFrames()` materialises the float movie.

| mapping class at peak | main | candidate | candidate + `MALLOC_MMAP_THRESHOLD_` |
|---|---:|---:|---:|
| `[heap]` (brk) size | 101,204 kB | **600,116 kB** | 15,108 kB |
| `[heap]` (brk) Rss | 61,976 kB | **232,816 kB** | 10,880 kB |
| `[heap]` AnonHugePages | 0 kB | 118,784 kB | 0 kB |
| anonymous mappings Rss | 1,398,572 kB | 1,426,572 kB | 1,448,120 kB |
| nvidia/driver file-backed Rss | 100,164 kB | 100,164 kB | 100,164 kB |
| **total Rss** | **1,591,520 kB** | **1,790,428 kB** | **1,589,968 kB** |

The brk heap accounts for **170,840 kB of the 199,152 kB difference (86%)**.

### Mechanism

One uint16 frame of the tutorial geometry is 3710 x 3838 x 2 = 28,477,960 B = 27.16 MiB. glibc's
dynamic mmap threshold is capped at `DEFAULT_MMAP_THRESHOLD_MAX` = 32 MiB, and it ratchets up to
the size of the largest mmapped chunk that has been freed. After the first movie the threshold
therefore exceeds one frame, and the remaining 23 movies' frames are served from the heap instead
of private mappings. Freeing them returns them to a free list; `malloc_trim(0)` then has to give
those pages back through `madvise(MADV_DONTNEED)` on a THP-backed heap, which on this host leaves
233 MB of a 600 MB heap resident. The float movie downloaded afterwards is added on top.

The float path is not affected because a float frame is 56,955,920 B = 54.32 MiB, above the 32 MiB
cap, so every float frame is its own mapping and `free()` unmaps it. This is the same 32 MiB cap
already recorded in the [lane A attribution](https://github.com/KingAlejandro/MotionCorr-standalone/issues/85#issuecomment-5874431759);
halving the frame size moved the allocation from one side of it to the other.

This is why the retained 4-GPU-VM measurement of the same candidate reported no-gain **−0.9%**
while SCARF reports **+0.17 to +0.23 GiB**: the two hosts differ in THP setting and allocator
behaviour. Both records stand; neither is wrong.

## 3. The change

`NativeU16MovieStaging` (`src/native_u16_staging.h`) maps one movie's native uint16 frames as a
single `MAP_PRIVATE|MAP_ANONYMOUS` region and binds each frame to a slice of it. Release is
`munmap`, so it does not depend on allocator policy, and the process-wide `malloc_trim(0)` is
removed. Per movie the allocation count goes from 24 allocations + 24 frees + 1 `malloc_trim` to
1 `mmap` + 1 `munmap`.

Capacity is exactly `n_frames * ceil64(nx*ny*2)` bytes for the movie being processed, re-derived
on every movie and released before any float movie is materialised. Nothing is retained between
movies, so no high-water cache can grow across geometries; the per-movie bound is written to each
movie log.

The decoder is untouched: `Image::read` reuses a bound slice because
`MultidimArray::coreAllocateReuse()` keeps an allocation whose `nzyxdimAlloc` already covers the
requested frame. Same reader, same guards, same per-row Y-flip, same bytes.

The widening fallback keeps its previous high-water mark: `discardThrough()` returns each frame's
pages as `expand_u16_to_float` consumes it, matching the per-frame `clear()` the old code relied
on. Without that, holding the whole mapping while building a float movie twice its size would have
traded one regression for another.

## 4. Does the staging want to be reused across movies?

No, and the measurement says why. The staging has to be released before the float movie a
non-converging patch downloads is materialised, otherwise the two are live together: 0.6365 GiB
plus 1.2731 GiB instead of 1.2731 GiB. Keeping one buffer alive across movies would therefore
raise the no-gain peak by roughly the whole staging payload, which is the regression this work
removes, not a saving.

What is reusable here is the mapping discipline, not the buffer. #95's "source-owned reusable
buffers only where lifetimes permit" is answered for this path: the lifetimes do not permit it.
The churn the reuse would have avoided is instead removed by collapsing 24 allocations and 24
frees into one `mmap` and one `munmap`.

`MADV_HUGEPAGE` on the mapping was considered and is not included. On a `THP=always` host the
mapping already gets huge pages, so it would change nothing here, and on a `THP=madvise` host it
is a separate, separately measurable change to first-touch cost, not to the high-water mark this
issue is about.

## 5. What this does not establish

- One geometry family, one codec, one GPU, one worker. No multi-GPU aggregate-budget result.
- Same-backend byte parity against the same main. No scientific-equivalence claim.
- The wall-time figures are matched alternating pairs on a shared node, with foreign GPU compute
  apps and load average recorded at each run start. They bound whether this change traded memory
  for speed; they are not a speedup measurement.
- The attribution reads `/proc/<pid>/smaps` at a sampled high-water mark, so the mapping-level
  split is accurate to the sampling interval, not an allocator trace.
- `CiFailClosedControls` still fails its three canonical-fixture hash controls. That failure is
  reproduced with the same three names on main `a75a3f87`, on PR118's frozen `6827b314` and on
  this branch, so it is preexisting and unrelated; it is not relabelled as a pass.

## 6. Harness defects found while running this, and fixed

Recorded because each one changed a reported number or would have.

1. The first requested-modes comparison compared raw STAR bytes and reported one differing
   product out of 145. The difference was the absolute output directory embedded in the joint
   STAR: 24 rows x 4 path occurrences x 1 character = 96 bytes. All 120 MRCs and all 24 per-movie
   STARs were identical. `compare_output_trees.py` does not have this problem because it
   validates that product paths resolve inside the tree instead of comparing them byte for byte.
2. The same driver's negative controls deep-copied the 8 GiB arm under test, four times. They
   hard-link now, with the single mutated file written privately.
3. The output-root substitution initially used only the resolved path. A run records the `--o`
   argument it was given, which is not the resolved path when a parent is a symlink, so the
   substitution missed entirely. Both spellings are substituted now.
4. `compare_mixed_geometry.py` shipped with defect 1 still in it and was caught by the
   independent review before it produced a number.
5. The first version of the contract test used a square, page-aligned geometry, so a transposed
   `bind(frames, n, ny, nx)` could not fail its shape check and `discardThrough()`'s page
   rounding was never exercised.
