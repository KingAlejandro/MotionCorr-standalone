# Lane A verdicts — which follow-on lanes the measurement justifies

Each verdict states the measured ceiling on what the lane could win, because a
lane whose entire addressable cost is small cannot be rescued by a good
implementation. Shares are of the `read movie` stage; the #109 report puts that
stage at 7.127 s inside a 29.779 s run, so divide by roughly four again for the
effect on the application.

**Two venues, and they disagree in a way that matters.** The 4-GPU VM
(`taskset`ed, shared, THP=`madvise`, LibTIFF 4.5.1, local ext4) is where the
7.127 s figure was measured. SCARF `cn3121` (exclusive node, THP=`always`,
LibTIFF 4.4, PanFS and local xfs) reproduces the same stage total but with a
different composition. Where they disagree the verdict says so rather than
averaging them.

---

## The finding that reorders the rest: ~40% of the VM's stage is a hugepage setting

On the VM, `production_image_read` minus `production_image_read_prealloc` —
the same production reader with its frame buffers already allocated — is about
40% of the stage. On SCARF the same difference is **2.5%**.

This is not a code property. It is transparent hugepages:

| | 4-GPU VM | SCARF cn3121 |
| :-- | :-- | :-- |
| `/sys/kernel/mm/transparent_hugepage/enabled` | `always [madvise] never` | `[always] madvise never` |
| prediction, minor faults for a 1.273 GiB first touch | 333,726 (4 KiB) | 651 (2 MiB) |
| **measured** (`alloc_first_touch_f32`) | **333,727** | **1,066** |
| allocation term inside the production reader | **40.7%** of the stage | **2.0%** |
| extra minor faults for that term | 333,743 | 10,282 |

The 4 KiB prediction was 333,726 and the VM measured 333,727. The mechanism is
not inferred from a correlation between two hosts; it is predicted to one page
and confirmed. The allocation term is stable at 40.7 / 41.1 / 38.1% across
W=8 / 16 / 24, so it is not a scheduling artefact either.

At `madvise`, an anonymous `mmap` of a 57 MB frame buffer faults in 4 KiB
pages, so one movie costs on the order of 3×10⁵ minor faults. At `always` the
same buffer is backed by 2 MiB pages and costs ~10³. MotionCorr allocates 24 ×
57 MB per movie and frees them at the end of that movie; glibc caps its
dynamic mmap threshold at 32 MiB, so every one of those allocations always goes
to `mmap` and always faults fresh.

Consequences, in order of cheapness:

1. **`madvise(MADV_HUGEPAGE)` on the frame buffers**, or hoisting `Iframes` out
   of the per-movie loop so `coreAllocateReuse()` takes its existing early
   return (`data != NULL && nzyxdim <= nzyxdimAlloc`). Either removes most of
   the 40% on a `madvise` host and changes no numerical result. This is a much
   smaller change than any of lanes B–G and it is not currently one of them.
2. Only after that is the remaining allocation cost worth paying a
   representation change for.

Anyone quoting "40% of TIFF ingest is allocation" must name the host's THP
setting in the same sentence.

---

## B — persistent TIFF reader pool: **NO-GO**

Measured both ways: one `TIFF*` per worker opened inside the parallel region
and reused, against a fresh `TIFFOpen` per frame. Per-frame opens were **faster
on every production-relevant worker count and on both hosts** — on the whole
24-movie set, by 3.2% at W=8 and 9.1% at W=24.

The ceiling settles it independently of that sign. The complete per-frame
open-and-metadata cost (`tiff_open_per_frame_meta`) is 0.165 s across all 24
movies at W=8, against a 7.382 s stage: **2.2%**. A pool cannot win more than
that, and the measurement says it wins less than nothing.

**Mechanism.** LibTIFF 4.5.1's `TIFFSetDirectory` already has an offset cache
(`_TIFFGetOffsetFromDirNumber`) and a relative fast path, so a persistent handle
seeks straight to a known IFD. But both paths then call `TIFFReadDirectory`,
which with `RowsPerStrip = 1` parses a 3838-entry `StripOffsets` array and a
3838-entry `StripByteCounts` array per frame either way. Persistence removes the
`open(2)` and the walk; it cannot remove the parse, and the parse is the cost.

Not worth the implementation or the "never share a mutable `TIFF*`" hazard.

---

## E — strip-batch parallel decode: **GO, but only above the frame count**

Upgraded from DEFER by the SCARF 64-core sweep, which is the first place the
question can actually be asked. Movies have 24 frames, so frame-level decode
cannot use more than 24 workers.

Representative movie, SCARF, local xfs, seconds:

| workers | frame-level (static) | 256-strip batches |
| --: | --: | --: |
| 8 | 0.265 | 0.269 |
| 24 | 0.097 | 0.103 |
| 32 | 0.121 | **0.087** |
| 48 | 0.123 | **0.073** |
| 64 | 0.124 | **0.068** |

Frame-level bottoms out around W=24–32 and then **regresses**; strip batching
keeps improving to W=64, ending 1.8× faster. Same shape on PanFS.

Two conditions:

1. **At or below the frame count it wins nothing**, so this is not a change for
   the single-GPU tutorial run. Its case is the multi-GPU aggregate CPU budget
   of #53/#106, where decode workers exceed frames.
2. **The scheduling confound is resolved, in strip batching's favour.** The
   batch arms use `schedule(dynamic,1)` and the frame arm `schedule(static)`,
   so they changed granularity and policy together. A frame-level
   `schedule(dynamic)` control separates them, at W=16 where 24 frames across
   16 workers is maximally imbalanced:

   | arm (VM, W=16, movie 00021) | s | vs static frames |
   | :-- | --: | --: |
   | frames, `schedule(static)` | 0.1238 | — |
   | frames, `schedule(dynamic,1)` | 0.1236 | **−0.2%** |
   | 64-strip batches | 0.1033 | **−16.5%** |
   | 256-strip batches | 0.1008 | **−18.6%** |

   Scheduling policy contributes nothing; the whole win is granularity. So the
   case for strip batching is broader than "above the frame count": it also
   applies whenever the decode worker count does not divide the frame count,
   which for 24-frame movies is most worker counts.

---

## C — native uint16 staging with GPU conversion: **GO on transfer, not on allocation**

The transfer argument is sound, venue-independent and now measured on an idle
A100 80 GB PCIe (`GPU-b2cb2c39`, median of 9), per 24-movie set:

| path | s / 24 movies |
| :-- | --: |
| current: float32 pageable H2D | **3.061** |
| uint16 pageable + device widening | 1.565 |
| float32 **pinned** | 1.269 |
| uint16 pinned + device widening | **0.673** |

Device widening is 1.50 ms per movie against 67.7 ms for the equivalent host
pass — **45× cheaper on the GPU**, which settles the "convert on the device"
condition quantitatively rather than by argument.

**But read the third row before committing to this lane.** Simply pinning the
existing float32 staging buffer saves 1.79 s per set, *more* than the 1.50 s
that switching to uint16 saves, and it needs no new format handling, no device
kernel and no fallback table — it applies to every input format. The two
compose (0.673 s combined), but pinned memory is the cheaper half and should
be done first. That is lane D's territory, not C's.

The allocation argument is **venue-dependent and mostly evaporates on a
THP=`always` host**, where the whole allocation term is 2.5% of the stage. On
such a host, halving an already-negligible cost is negligible. Do not carry the
VM's 40% into PR C's justification without naming the THP setting, and try
`MADV_HUGEPAGE` or buffer reuse first — they address the same cost for far less
change and for every input format, not just 16-bit unsigned TIFF.

Unchanged conditions: convert **on the device** (45× cheaper, above; a host
pass over a resident movie costs 1.465 s against the 0.318 s the fused
strip-granular conversion it would replace costs); and scope to 16-bit
unsigned TIFF with an explicit fallback table.

---

## F — narrow custom CPU Deflate fast path: **GO for a bounded experiment, with one design constraint**

Deflate is the largest single component and is stable across both hosts and all
24 movies: **46.2%** of the stage at W=8 on the full set. It is also the one
component a library swap can attack without touching reader structure or
failure semantics. `libdeflate` is present on the measurement host, and its
advantage is largest exactly here — 92,112 independent streams averaging
~1.37 KB, where zlib's per-stream setup is a large fraction of the work.

**The design constraint comes from PanFS and it is not optional.** #85's sketch
for this lane specifies `pread()` of the compressed strip extents. On local
storage that is nearly free (0.012 s per movie at W=8). On PanFS it is
**0.503 s per movie — 42× worse, and larger than the entire decode it would
feed**. LibTIFF avoids this because `TIFFOpen(path,"r")` memory-maps the file
and reads through that mapping. A custom fast path must keep the mapped or
buffered access pattern; a per-strip `pread` loop would be a severe regression
on exactly the shared filesystems this project runs on.

Bounded means: declared supported subset (Deflate, predictor 1, uint16,
strip-organised), LibTIFF fallback for everything else, the existing
damaged-input controls, and an application measurement — not a decoder
microbenchmark — as the go/no-go.

---

## G — GPU Deflate / nvCOMP: **NO-GO as a production dependency**

The byte case is attractive: ~126 MB compressed per movie against a 1.273 GiB
float upload. Three things stack against it.

1. **Amdahl.** Deflate is 46% of a 7.1 s stage in a 29.8 s run. Eliminating CPU
   Deflate entirely is bounded by ~11% of the run, and only if nothing else
   grows.
2. **Item size.** 92,112 items averaging ~1.37 KB is close to the worst case for
   batched GPU decompression, where per-item overhead dominates. The
   verification pass looked for a published throughput characterisation for
   batched Deflate items this small and did not find one, so the upside here is
   unquantified rather than merely uncertain.
3. **It spends the scarce resource.** On A100 the decompression runs on the SMs.
   Lane A exists because the CUDA path is already fast; trading SM time for host
   time is backwards, most of all in the multi-GPU case where SM time is what
   is contended.

Keep as a feasibility note. Do not make it a dependency.

---

## D — bounded pinned staging: **promoted; do this before C**

Lane D was sequenced last in #85, to be integrated "only after the best
representation from B/C is known". The H2D measurement inverts that: pinning
the existing float32 buffer is the single largest transfer win available and
does not depend on choosing a representation at all.

| | s / 24 movies | change required |
| :-- | --: | :-- |
| current, float32 pageable | 3.061 | — |
| float32 pinned | **1.269** | staging buffer allocation only |
| uint16 pageable + device widen | 1.565 | new format path, device kernel, fallback table |
| uint16 pinned + device widen | 0.673 | both |

Pageable H2D runs at 10.7 GB/s against 25.8 GB/s pinned on this device — the
driver stages pageable memory through its own bounce buffers, and that is
2.4× of the transfer cost, paid on every movie regardless of format.

The #85 constraints on this lane still hold and are the hard part: bounded
reusable pinned chunks rather than pinned whole movies, byte budget acquired
before allocation, a staging buffer not reused until its completion event
fires, and the shared cuFFT workspace not silently shared with new streams.
The measurement says the prize is worth that care; it does not say the care
can be skipped.

---

## The result that needs no new code at all

The read stage is **not saturated at the `--max_io_threads 8`** the tutorial
runs use. On the full 24-movie set, warm, local ext4:

| decode workers | stage total |
| --: | --: |
| 8 | 7.382 s |
| 24 | 3.486 s |

Raising decode concurrency toward the frame count halves the stage with no code
change. #109 already saw this at the application level (j16/IO16 27.77 s against
j8/IO8 29.16 s); this lane shows why. The caveat is the one #85 already states:
under multi-GPU the decode budget is shared, so this is a per-movie setting to
schedule centrally, not a number to raise independently per worker.

---

## A — this lane

Complete on both venues, with the harness's own defects found and fixed in
flight: the `pread`-based storage floor measured a kernel path the production
decoder never takes and was removed from the chain; the production arm
initially charged the previous movie's deallocation to the read timer; the
strip-batch comparison confounded granularity with scheduling policy; and the
non-pixel arms had no completion witness, so the Deflate number could not have
failed. Each is corrected and the corrections are in the retained evidence.

No application speedup is claimed. A decode microbenchmark cannot establish one.
