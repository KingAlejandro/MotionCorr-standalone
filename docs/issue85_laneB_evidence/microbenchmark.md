# Lane B microbenchmark: where a movie read's time actually goes

Source `a75f873`. Host `small-refmac-machine` (cpu64), 64 logical CPUs,
Ubuntu 24.04, g++ 13.3, LibTIFF 4.5.1, `-DCMAKE_BUILD_TYPE=Release`
(`optimized_build: true` is recorded in the JSON; the benchmark refuses to run
otherwise, because an unqualified configure builds `-O0` and inflates every
number here).

Input `20170629_00023_frameImage.tiff`: 3710 x 3838, 24 frames, 16-bit
unsigned, Adobe Deflate, `RowsPerStrip = 1`, 3838 strips per frame, **92,112
strips per movie**, 131,245,904 bytes on disk. Warm page cache. 5 reps,
medians. `OMP_PROC_BIND` and `OMP_PLACES` unset for both arms — both arms run
inside the same OpenMP runtime, so thread placement is not a variable between
them.

Every arm's decoded pixels are hashed and compared against a serial reference:
`all_arms_decoded_identical_pixels: true`. The gate is falsifiable —
`--inject-decode-fault` makes it report `false` and exit non-zero.

Raw JSON: `bench_single_00023.json`.

## Where the time goes

Single-threaded, one movie. The stage sum is **1.390 s** against a measured
`Image::read` of **1.392 s** at one thread, so this is a decomposition, not a
list of loosely related numbers.

| stage | s | share |
|---|---:|---:|
| strip decode (`TIFFReadEncodedStrip` x 92,112) | 0.6394 | 46.0% |
| allocation + first touch of the float frames | 0.6317 | 45.4% |
| conversion + Y placement (`castPage2T`) | 0.0951 | 6.8% |
| **open + close** | **0.0188** | **1.4%** |
| **layout: IFD chain walk + directory-0 tags** | **0.0043** | **0.3%** |
| **directory selection** | **0.0007** | **0.1%** |
| **total the persistent pool can remove** | **0.0239** | **1.7%** |

(`raw_pread`, a separate whole-file `read()` of the compressed bytes, is
0.0885 s. It is **not** part of `Image::read`, is listed separately in the
JSON, and must not be added to the decode stage to form a "storage floor":
LibTIFF memory-maps the file rather than issuing the same reads, so the two do
not compose. On PanFS the gap is worse still — per-strip `pread` has been
measured at 42x the mmap path on this project's shared storage.)

Two things follow.

**The lifecycle lane B removes is 1.7% of a movie read.** Everything else —
the 92,112 inflate calls, the page faults, the conversion — happens in both
arms.

**On this host, allocation and first touch is as expensive as the decode
itself** — 45% of a single-threaded movie read. That is 1.37 GiB of fresh
pages per movie: 24 `Image<float>` frames at 57 MB each, reallocated for every
movie because the runner rebuilds `Iframes` per movie.

That number is **not portable**. `small-refmac-machine` runs
`transparent_hugepage/enabled = always [madvise] never`, i.e. madvise, so each
57 MB frame faults in 4 KiB pages. Under `always` the same allocation is
served by hugepages and the fault cost collapses; the difference has been
measured at around 40x on this project's hosts, which is far larger than
anything lane B does. So this is a host-configuration-dependent cost, and
"45%" is a property of this machine's THP setting, not of the code. It is
still worth someone's attention — the runner reallocating 1.37 GiB per movie
is real on any setting — but the size of the prize has to be re-measured per
host before it is quoted.

Lane B's own verdict does not depend on it: the 1.7% lifecycle share is
computed against a total that includes this stage, so on an `always`-THP host
the lifecycle share would be *larger* in percentage terms while the absolute
0.024 s stays the same.

## Whole-movie read, both arms

| workers | `Image::read` per frame | persistent pool | pool without parse-once | pool vs baseline |
|---:|---:|---:|---:|---:|
| 1 | 1.3923 | 1.3768 | 1.3809 | −1.1% |
| 2 | 0.7224 | 0.7144 | 0.7137 | −1.1% |
| 4 | 0.4700 | 0.3661 | 0.3657 | −22.1% |
| 8 | 0.2521 | 0.2480 | 0.2445 | −1.6% |
| 16 | 0.1823 | 0.1701 | 0.1719 | −6.7% |
| 24 | 0.1044 | 0.0937 | 0.0938 | −10.3% |

The pool is slightly faster at every count, and the advantage grows with
worker count — roughly 5–10% at 16 and 24 readers. The −22.1% at 4 is mostly
baseline noise: that point's minimum is 0.381 s against a median of 0.470 s,
while the pool's minimum and median agree to 1%. Comparing minima instead of
medians gives −5%, −1%, −5%, −1%, −14%, −9%.

**`--persistent_tiff_readers` was not clamped to 2.** 24 readers is the best
point on a 64-CPU host, and 2 is among the worst; MotionCor3's hard-coded 2 is
not the right number here.

## What the parse-once refactor bought: nothing measurable

The third column is the same pool of persistent handles with every frame still
going through the whole of `readTIFF`, so the movie layout is re-resolved and
a strip buffer re-allocated per frame. It tracks the parse-once column within
1% at every worker count, in both directions.

That is consistent with the stage table: re-resolving the layout costs 0.0043 s
per movie. **The entire measurable benefit comes from not reopening the file,
not from resolving the layout once.** If this were ever promoted, the simpler
variant — persistent handles calling the unmodified `readTIFF` — would capture
all of it and would need no change to `src/rwTIFF.h` at all.

## Limitations

- Warm page cache only. Dropping the cache needs root, which this account does
  not have on a shared host. `raw_pread` is reported separately so the storage
  term is at least visible.
- One movie. The dataset-scale question is answered by the production A/B over
  all 24, not by repeating this.
- Local disk (`/dev/vda1`), not PanFS. Open cost is storage-dependent, and 24
  opens per movie would cost more on a shared filesystem than the 0.0188 s
  measured here. That is the one term that could make lane B look better
  elsewhere.
- `transparent_hugepage = madvise` on this host. See the note on the
  allocation stage above.
- `small-refmac-machine` is shared. Two long-running `ctffind` processes held
  two cores throughout; runs were gated on 1-minute load average below 6.0 and
  serialised against other MotionCorr work through
  `/tmp/motioncorr-cpu64-bench.lock`.
- The all-24 arm of the sweep was started and stopped after 40 minutes: its
  own per-repetition verification digests (~1.8 TB of hashing) dominated its
  runtime, and it answers the same question as the production A/B over the
  same 24 movies, which was run instead.
