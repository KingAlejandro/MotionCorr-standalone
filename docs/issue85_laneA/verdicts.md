# Lane A verdicts — which follow-on lanes the measurement justifies

Each verdict states the measured ceiling on what the lane could win, because a
lane whose entire addressable cost is small cannot be rescued by a good
implementation. Percentages are of the `read movie` stage unless stated;
"of the run" scales them against the 29.779 s whole-application figure the same
#109 report records, so the Amdahl ceiling is visible next to the local one.

---

## B — persistent TIFF reader pool: **NO-GO**

**Measured, not inferred.** The harness runs the identical decode twice: once
with one `TIFF*` per worker opened inside the parallel region and reused across
that worker's frames (`persistent_handle_to_f32`), once with a fresh `TIFFOpen`
per frame (`openperframe_handle_to_f32`). Persistent handles were **not faster
at any worker count**, and were slower at both W=8 and W=24.

The ceiling is independent of that result and is what settles it. The complete
per-frame open-and-metadata cost — `TIFFOpen`, `TIFFNumberOfDirectories`,
`TIFFSetDirectory`, the tag reads — is `tiff_open_per_frame_meta`, and a single
persistent handle doing only the directory work is `tiff_dirscan_persistent`.
The difference between them is everything a reader pool could remove.

**Mechanism.** LibTIFF 4.5.1 already caches directory offsets
(`_TIFFGetOffsetFromDirNumber`, plus a relative fast path from the current
directory), so a persistent handle seeks straight to a known IFD instead of
walking. But both paths still call `TIFFReadDirectory` on the target, and with
`RowsPerStrip = 1` that parses a 3838-entry `StripOffsets` array and a
3838-entry `StripByteCounts` array — roughly 60 KB of tag data — once per frame
either way. Persistence removes the walk and the `open(2)`; it cannot remove
the parse, and the parse is the part that costs.

Not worth an implementation, a new ownership rule, or the "never share a mutable
`TIFF*`" hazard that comes with a pool.

---

## C — native uint16 staging with GPU conversion: **GO**

The strongest lane, and for a reason lane A did not expect: it is not mainly a
conversion or a transfer win, it is an **allocation** win.

Two independent measurements say the same thing:

- `production_image_read` minus `openperframe_handle_to_f32` isolates the
  `Image`/`fImageHandler` lifecycle and the per-frame pixel allocation. That
  single link is the joint-largest component of the stage — comparable to all of
  Deflate — and the only work in it that scales with the payload is allocating
  and first-touching 1.273 GiB of fresh float frame buffers per movie.
- `production_image_read` minus `production_image_read_prealloc` measures the
  same thing inside the real reader, by letting `coreAllocateReuse()` skip the
  allocation on a second read into buffers that are already the right size.

Staging uint16 halves that payload to 0.637 GiB. `alloc_first_touch_u16` is
about half `alloc_first_touch_f32`, as the byte count predicts, and the H2D arm
shows the same halving on the transfer.

Two conditions on the GO:

1. **Convert on the device, not the host.** `convert_u16_to_f32_resident`
   measures a standalone host pass over a resident movie, and it is expensive —
   far more than the conversion costs when it is fused into strip decode, where
   the source rows are still in cache. A host-side uint16→float pass after
   staging would give back more than the staging saves. The conversion has to
   happen on the GPU, which is what #85's PR C already proposes.
2. **Scope to 16-bit unsigned TIFF with an explicit fallback.** Every other
   format stays on the existing path, and the support table is part of the PR.

---

## The change lane A found that is not one of the five lanes: **reuse the frame buffers**

Native uint16 staging halves the allocation. Reusing the buffers removes most of
it, for any input format, with no change to the numerical contract.

`MotioncorrRunner` constructs a fresh `Iframes` vector per movie, so each of the
24 movies allocates and first-touches 24 × 57 MB and then frees it. The frames
have identical geometry across the whole dataset. A buffer pool keyed by
(geometry, type), or simply hoisting `Iframes` out of the per-movie loop, lets
`coreAllocateReuse()` take its early-return path — it already returns
immediately when `data != NULL && nzyxdim <= nzyxdimAlloc` — and the page faults
disappear after the first movie.

This is smaller and lower-risk than any of A–G, addresses the joint-largest
component, and is orthogonal to the representation change in C. It should be
measured as its own change before C is judged, or C will be credited with a
saving that buffer reuse would have delivered on its own.

---

## E — strip-batch parallel decode: **DEFER**

Measured directly rather than argued from the strip count. The harness runs the
same decode with the scheduling unit set to a batch of strips instead of a whole
frame, with per-worker handles and dynamic scheduling, at batch sizes 64 and 256.

Frame-level decode already scales usefully to 24 workers on this input, and with
24 frames and 24 workers it is perfectly balanced, so strip batching has nothing
to recover there. At worker counts that do not divide 24 the imbalance is real
but the batched arms did not beat frame-level consistently, and the differences
sit inside run-to-run spread.

Defer rather than reject: the case strip batching is actually for is **more
decode workers than there are frames**, which is the multi-GPU aggregate-budget
situation #53/#106 will create and which a 24-core mask with 24-frame movies
cannot exercise. Re-test it there, against the alternative of simply decoding
several movies concurrently — which needs no new code.

---

## F — narrow custom CPU Deflate fast path: **GO for a bounded experiment**

Deflate is the largest single decode component and the addressable budget is
real. It is also the one component that a drop-in library change can attack
without touching the reader's structure or its failure semantics.

`libdeflate` is already installed on the measurement host. Its advantage is
largest exactly where this input sits: 92,112 independent streams averaging
~1.37 KB, where zlib's per-call stream setup is a large fraction of the work and
`libdeflate`'s one-shot API has none.

Bounded means bounded: a declared supported subset (Deflate, predictor 1,
uint16, strip-organised), `pread` of the compressed extents which the harness
shows is nearly free, LibTIFF fallback for everything else, and the
damaged/truncated-input controls the merged reader already has. The go/no-go at
the end of that experiment is an application measurement, not a decoder
microbenchmark — halving Deflate moves the stage by its share, and the run by
much less.

---

## G — GPU Deflate / nvCOMP: **NO-GO as a production dependency**

The dataflow is genuinely attractive on bytes: ~126 MB of compressed input per
movie against a 1.273 GiB float upload. But three things stack against it here,
and the first is decisive.

1. **Amdahl.** Deflate is a fraction of a stage that is itself a fraction of the
   run. Even eliminating CPU Deflate entirely leaves the rest of the stage and
   the rest of the application untouched.
2. **Item size.** 92,112 items averaging ~1.37 KB is close to the worst case for
   batched GPU decompression, where per-item overhead dominates and the
   attainable throughput is far below the figures quoted for large blocks.
3. **It competes with the GPU for the GPU.** On A100, Deflate decompression runs
   on the SMs. Lane A exists because the CUDA path is fast; spending SM time to
   save host time is the wrong direction unless the host is the bound, and the
   multi-GPU case #85 cares about is precisely where SM time is scarcest.

Keep it as a feasibility note. Do not make it a dependency of anything.

---

## A — this lane

Complete. The harness, the raw matrices and the controls are retained. The
attribution it produces is what the other lanes should be argued from; no
application speedup is claimed here, because a decode microbenchmark cannot
establish one.
