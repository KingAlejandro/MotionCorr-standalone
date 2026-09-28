# Design note: persistent TIFF reader handles (issue #85, lane B)

- **Issue**: #85, lane B of the [TIFF ingest optimization program](https://github.com/KingAlejandro/MotionCorr-standalone/issues/85#issuecomment-5876206372)
- **Status**: experiment, opt-in, default off. **Measured outcome: no-go for
  promotion.** The mechanism works and preserves every output exactly, but it
  removes 1.7% of a movie read and moves the application wall by less than the
  host's run-to-run noise. See `docs/issue85_laneB_evidence/`.
- **Base**: `origin/main` `8323c55`
- **Branch**: `feat/issue-85-laneB-persistent-tiff`
- **Independent of**: lane C (`feat/issue-85-laneC-uint16-staging`)

## Outcome

Keep the flag off. The pool is correct — 422 parity checks on two LibTIFF
error-context builds, byte-identical corrected images and STAR files across
all 24 tutorial movies — and it is not slower, including at 16 readers against
an 8-CPU budget. It is simply not faster in any way the application can see.

If a future lane revisits this, two results from here should carry over:

1. **Resolving the layout once buys nothing.** The arm that keeps the
   per-frame `readTIFF` call tracks the parse-once arm within 1% at every
   reader count. All of the (small) microbenchmark advantage comes from not
   reopening the file. The simpler variant needs no change to `src/rwTIFF.h`
   at all.
2. **Allocation and first touch of the decoded frames is 45% of a
   single-threaded movie read on a madvise-THP host**, as expensive as the
   92,112 inflate calls, and no lane in the current issue #85 program targets
   it. The percentage is host-dependent — THP `always` versus `madvise` is
   worth about 40x on frame allocation here — so re-measure before quoting it
   anywhere else. The underlying fact, that the runner reallocates 1.37 GiB
   per movie, is not host-dependent.

## Question

Does replacing one generic image open/read/close lifecycle per frame with a
small pool of persistent TIFF handles materially reduce the time to read a
movie, and does it help or hurt the whole application under a fixed CPU
budget?

## What the ordinary path does per frame

`Iframes[iframe].read(fn_mic, true, frames[iframe], false, true)` constructs an
`fImageHandler`, opens the file, resolves the movie layout from directory 0,
walks the IFD chain with `TIFFNumberOfDirectories`, seats the handle back on
directory 0, selects the requested directory, allocates a strip buffer,
decodes, and closes. For a 24-frame movie that is 24 opens, 24 layout
resolutions and 24 IFD walks.

## Design

`TiffMovieReader` (`src/tiff_movie_reader.{h,cpp}`) opens `N` handles once per
movie. Each worker owns

- its own `TIFF*`, and therefore its own descriptor and its own directory
  cursor — no shared mutable TIFF directory state;
- its own `TiffErrorContext`, bound to that handle;
- its own strip scratch, grown on demand and kept for the movie.

The shared state is the frame-index counter and two concurrency counters, all
`std::atomic<int>`, plus the destination vector and the per-slot error vector,
which are written only at each worker's own disjoint slot. A worker takes the
next unclaimed slot whenever it goes idle, so a slow frame does not stall the
others. The movie layout is resolved once, before any worker starts, and is
read-only afterwards. No TIFF handle, error context or scratch is shared.

Handles are created through `fImageHandler::openFile`, so the experiment
inherits the existence check, the `.gain`→`tif` rewrite, read-only
enforcement, the open-failure text and the per-handle LibTIFF error wiring
without a second copy of any of it.

### Why OpenMP and not std::thread

`OMP_PROC_BIND` is worth about 26% on this project's CPU scaling. A
`std::thread` pool escapes OpenMP's placement policy entirely, so the two arms
would differ in thread placement as well as in handle reuse and the
measurement could not attribute the difference. Both arms therefore run inside
the same OpenMP runtime.

### Sharing the decode logic

`src/rwTIFF.h` is split into three pieces that `readTIFF` then composes:

| piece | where | responsibility |
|---|---|---|
| `readTiffLayout` | `src/rwTIFF_layout.h` | directory-0 tags, packed-4-bit detection, datatype table, directory count |
| `applyTiffLayout` | `src/rwTIFF.h` | header metadata, stack bounds, dimensions, allocation |
| `readTIFFDirectory` | `src/rwTIFF.h` | directory selection, per-frame consistency check, strip validation, Y placement |

The pool calls the same three pieces through `readTIFFFrameFromHandle`. On the
production path there is one copy of the strip validation and the row
placement, not two, and no `if (cached)` branch inside either — a later edit
cannot add a check to one arm and miss the other, because there is only one
arm. The benchmark's stage-attribution routine does contain its own stripped
placement loop, deliberately: it exists to time the pieces separately and is
not on any product path. Its independence is what lets the benchmark's
whole-movie digest check catch a placement error in either copy.

`readTIFF` itself is unchanged from the outside, and `readTiffInMemory`
(`src/image.h`) still goes through it untouched.

### Failure association

Errors are captured per frame slot, never per worker — a worker that draws no
work must not mark anything failed. The lowest failing slot is rethrown, which
is the ordering the runner's serial rethrow loop already guarantees. Nothing
throws out of the OpenMP region.

After a frame fails, its worker reopens its handle, so no frame inherits
LibTIFF state from a failed one; the reference path gives every frame a fresh
handle. This is the conservative choice rather than a demonstrated fix:
deleting the reopen does not corrupt any surviving frame on the damaged
fixtures here, because `TIFFSetDirectory` re-seats the handle and LibTIFF
recovers. What deleting it does break is the dead-pool report below, and the
test fails there. If a reopen itself fails the pool is dead; `readFrames`
rejects a later call rather than handing a closed `TIFF*` to LibTIFF, which
previously segfaulted.

### Eligibility

`tiffMovieReaderApplies` mirrors the ordered dispatch chain in `Image::_read`,
not just the extension. Testing for `tif` alone would claim `.stif`, which
`_read` routes to `readMRC` through its `contains("st")` branch.

## Opt-in and removal

`--persistent_tiff_readers N`, default `0` (unchanged behaviour). Rejected
without `--use_own`, where it could not take effect. Only plain TIFF input
uses it; EER and compressed MRC keep the existing loop.

To remove the experiment:

```
git rm src/tiff_movie_reader.h src/tiff_movie_reader.cpp src/rwTIFF_layout.h \
       src/apps/tiff_reader_bench.cpp tests/test_tiff_persistent_reader.cpp
git checkout origin/main -- src/rwTIFF.h src/image.h
# drop from CMakeLists.txt: the tiff_reader_bench executable, the
# tiff_persistent_reader test, the TIFF_COMPAT_TEST block and the
# REMOVE_ITEM entry for the benchmark
# drop from motioncorr_runner.{h,cpp}: persistent_tiff_readers, its two
# validations, the include, and the use_persistent_tiff branch
```

`git diff origin/main -- src/ CMakeLists.txt` must then be empty.

### Thread budget

The pool size is the flag's value, deliberately not clamped to
`--max_io_threads`, so the sweep can test counts above the compute-thread
count. That means it can oversubscribe: the per-movie log records the pool
size alongside `--j` and the `--max_io_threads`-derived count, so a run that
oversubscribed is visible in its own log rather than only in the timings. If
this ever moved past an experiment it would have to be folded into one
aggregate host budget, as the multi-GPU section of issue #85 requires, not
multiplied independently by every GPU worker.

## What the parity matrix covers

`tests/test_tiff_persistent_reader.cpp` compares the two readers element by
element over the whole decoded buffer with `memcmp`, plus the datatype and
sampling-rate the reader sets, at reader counts 1/2/4/8/16/24 — including
counts above the frame count, so idle workers are exercised.

Fixture values are `(frame*7919 + y*131 + x*7)`, distinct per frame, per row
and per column, so a frame taken from the wrong directory, a row placed at the
wrong offset and a shift inside a row are each visible. Row sums, the oracle
the existing `TiffRead` test uses, cannot see the last of those.

Layouts: RowsPerStrip=1 Deflate (the tutorial movies), multi-row strips with a
short final strip both raw and Deflate, 8-bit UChar, 16-bit UShort, 16-bit
SShort, 32-bit Float, IMOD packed 4-bit, a non-contiguous selected subset, and
out-of-order frame indices — the only case that separates "decoded the wrong
directory" from "wrote it into the wrong slot". `tests/test_tiff_read.py`
already covers `img_select == -1`; nothing covered a non-monotonic selection.

Damaged inputs must fail with the reference's exact message: truncated IFD
chain, hard truncation, corrupt strip payload, frame index past the stack, and
a heterogeneous-directory file. That last one matters specifically because a
reused handle is parked on the previous frame: every frame must still be
validated against directory 0, never against frame k-1.

Negative controls assert the comparator can fail, one per property it claims
to cover: a 1 ULP change, a frame swap, a row reversal, an intra-row swap, a
shape change, a sampling-rate change and a datatype change. One fixture
carries resolution tags so the sampling-rate comparison is not two copies of
the same default.

The reader-count axis is only meaningful if the pool really ran on several
handles at once — identical pixels come out either way. `readFrames` therefore
reports the OpenMP team size it actually got and the peak number of frames
decoding simultaneously, and the test asserts both. Before that was added the
whole matrix passed under `OMP_NUM_THREADS=1`; it now fails there, which is
the point. A 700x700x12 fixture gives each frame enough decode work for the
peak to reach the pool size rather than one worker draining the queue.

A two-damaged-frame fixture checks that the error the caller sees belongs to
the lowest position in `frames` at 1/2/4/8 readers, not to whichever worker
failed first. A one-damaged-frame fixture, located by walking the IFD chain,
checks that every frame the reference decoded is still decoded correctly by
the pool after a sibling frame failed, and that a pool whose reopen failed is
reported on reuse rather than handing a closed `TIFF*` to LibTIFF.
`tiffMovieReaderApplies` has its own table of 16 names checked against
`Image::_read`'s dispatch order, including `.stif`, `.gain` and an explicit
`:mrc` override.

422 checks in total, passing on both the LibTIFF >= 4.5 per-handle build and
the forced < 4.5 `thread_local` build.

## Limitations

- The LibTIFF < 4.5 `thread_local` error-context path is never compiled by a
  normal build here: both project hosts ship 4.5 or newer.
  `-DTIFF_COMPAT_TEST=ON` builds a second copy of the library with that path
  forced on and runs the same matrix through it. Off by default because it
  doubles the library compile.
- ThreadSanitizer cannot establish the absence of races through an OpenMP
  barrier with an uninstrumented libomp; see the evidence directory for what
  the TSan runs do and do not show.
- `readTiffInMemory` deliberately stays on the reference path. It is not a
  movie-ingest entry point.
