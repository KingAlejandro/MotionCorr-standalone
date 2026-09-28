# Issue #85 lane A — where the ~7 s of TIFF ingest actually goes

Attribution benchmark for the `read movie` stage of the native-CUDA tutorial
run. Measurement only: `src/rwTIFF.h`, `src/image.h` and
`src/motioncorr_runner.cpp` are byte-identical to `5ada983`.

Lane source `fbf1ccb`. Venues, methods, regimes and the correctness gate are in
[`README.md`](README.md). The follow-on lane calls are in
[`verdicts.md`](verdicts.md). Raw matrices are in `raw/`.

---

## 1. The answer

The production arm calls `Image<float>::read()` exactly as
`MotioncorrRunner` does, scoped to the same region as `RCTIC(TIMING_READ_MOVIE)`.
On all 24 tutorial movies, warm page cache, local ext4, 8 decode workers — the
configuration #109 measured — it totals **7.382 s** against the **7.127 s**
that report records, so this decomposition is of the real stage.

| component | seconds / 24 movies | share of stage |
| :-- | --: | --: |
| **Deflate decompression** | **3.409** | **46.2%** |
| **per-frame open + `Image`/`fImageHandler` lifecycle + frame allocation** | **2.922** | **39.6%** |
| storage access + LibTIFF strip bookkeeping | 0.394 | 5.3% |
| uint16 → float conversion | 0.318 | 4.3% |
| write decoded rows to destination | 0.279 | 3.8% |
| Y-flipped placement | 0.060 | 0.8% |
| **total (`production_image_read`)** | **7.382** | **100%** |

Two components carry the stage. Everything #85 identified as a structural
defect in the reader — directory handling, the Y flip, per-frame opens —
together accounts for under 7%.

### The second component is mostly a kernel setting, not code

`production_image_read` minus `production_image_read_prealloc` — the identical
reader with its frame buffers already allocated — is ~40% of the stage on the
4-GPU VM and **2.5%** on SCARF. The difference is transparent hugepages:

| | 4-GPU VM | SCARF `cn3121` |
| :-- | :-- | :-- |
| `transparent_hugepage/enabled` | `always [madvise] never` | `[always] madvise never` |
| predicted minor faults, 1.273 GiB first touch | 333,726 (4 KiB) | 651 (2 MiB) |
| **measured** | **333,727** | **1,066** |
| allocation term inside the production reader | **40.7%** | **2.0%** |

The 4 KiB prediction was 333,726 and the VM measured 333,727, so this is a
confirmed mechanism rather than a correlation between two hosts.

MotionCorr allocates 24 × 57 MB per movie and frees them at the end of that
movie. glibc caps its dynamic mmap threshold at 32 MiB, so every one of those
allocations always goes to `mmap` and always faults fresh. At THP=`madvise`
that is ~3×10⁵ minor faults per movie; at `always` it is ~10³.

So the honest statement of the headline is: **of the 7.127 s, roughly 46% is
Deflate and roughly 40% is page-fault cost that a hugepage setting or buffer
reuse removes.** The second figure is specific to hosts configured like the VM.

---

## 2. Which lanes are justified

Full reasoning and ceilings in [`verdicts.md`](verdicts.md).

| lane | verdict | measured ceiling or basis |
| :-- | :-- | :-- |
| **B** persistent TIFF handles | **NO-GO** | entire addressable cost is 2.2% of the stage, and per-frame opens measured *faster* on both hosts |
| **D** bounded pinned staging | **GO, and before C** | pageable H2D runs at 10.7 GB/s vs 25.8 GB/s pinned; saves 1.79 s / 24 movies, more than C's 1.50 s, for a much smaller change |
| **C** native uint16 staging | **GO on transfer, after D** | halves H2D (1.50 s / set) and composes with D (3.061 → 0.673 s); its *allocation* argument is the THP effect and mostly vanishes at THP=`always` |
| **E** strip-batch decode | **GO** | granularity alone gives −16.5% at W=16 and 1.8× at W=64; a `schedule(dynamic)` control shows policy contributes −0.2%, so the win is real |
| **F** custom CPU Deflate | **GO, bounded** | attacks the largest component (46%), but must not use the sketched per-strip `pread` — 42× worse on PanFS |
| **G** nvCOMP GPU Deflate | **NO-GO** | ~1.4 KB items, no published characterisation at that size, and it spends SM time to save host time |
| *(not a lane)* hugepages / buffer reuse | **do first** | same ~40% as C's allocation case, far smaller change, all input formats |
| *(not a lane)* raise decode workers | **free** | stage halves from 7.382 s at W=8 to 3.486 s at W=24, no code change |

---

## 3. Correctness

Every arm that materialises pixels is compared to the production reference by
**exact ordered equality over all 341,735,520 floats**, at every worker count
and every repeat, on both venues. All pass.

Two deliberately weaker oracles run alongside so their blind spots are on the
record:

| mutation class | exact ordered | global sum | ordered row sums |
| :-- | :-- | :-- | :-- |
| one pixel, 1 ULP | detects | detects | detects |
| two pixels swapped within a row | detects | **blind** | **blind** |
| two rows swapped within a frame | detects | **blind** | detects |
| one frame's rows reversed | detects | **blind** | detects |
| two frames swapped | detects | **blind** | detects |

Each weaker oracle has a mutation class it cannot see; only the exact
comparison sees all five. A checksum alone would have passed four of them.

The gate is falsifiable, not structural. All five mutations were injected into
the **live output of a real arm** and each turned the gate red, while the
uninjected control stayed green. Separately, the non-pixel arms — including
`tiff_decode_only`, which carries the 46% Deflate figure — now count the strips
they actually processed against the expected 92,112, and that witness has its
own negative control: `--fault-witness` drops one strip and the run exits 1
(92,111/92,112), while the clean run exits 0.

---

## 4. Caveats that bound these numbers

- **The VM was not exclusive.** Other users' work ran throughout, including
  another #85 lane whose compile initially landed inside the measurement mask;
  that run was discarded and re-run on a disjoint mask with a 30 s interference
  sampler. Absolute VM seconds carry that residual; component *shares* are
  robust because all arms are interleaved inside one process.
- **The two venues use different LibTIFF** (4.5.1 vs 4.4), so Deflate timings
  are never compared across them.
- **`production_image_read` is a faithful proxy, not the runner.** It omits the
  two header-only opens per movie the runner performs outside the timed region,
  and the runner's per-frame exception capture.
- **The cold regime is cold-*file*, not cold-machine.**
  `posix_fadvise(DONTNEED)` evicts that file's clean pages only. That it worked
  is observable rather than asserted: storage-only arms are 5.3–5.9× slower
  cold, which cannot happen if the pages stayed resident.
- **No application speedup is claimed.** A decode microbenchmark cannot
  establish one, and the Amdahl ceiling is explicit: making ingest free takes a
  29.8 s run to about 22.7 s at best.

### Defects found in this harness, in flight

Recorded because they changed numbers that were nearly published:

1. The `pread` "storage floor" measured a kernel path the decoder never takes —
   `TIFFOpen(path,"r")` leaves `TIFFMapFileContents` enabled, so libtiff arms
   fault through a `MAP_SHARED` mapping and issue no per-strip read syscall.
   The subtraction went negative. The pread arms are now a separate reference
   and the chain starts at the first libtiff arm.
2. The production arm initially charged the previous movie's 1.37 GiB
   deallocation to the read timer, inflating the headline by ~60%.
3. The "persistent handle" arms originally opened a `TIFF*` per *frame*,
   measuring nothing about persistence.
4. The strip-batch arm changed granularity and OpenMP schedule together; a
   frame-level `schedule(dynamic)` control now separates them.
5. The non-pixel arms had no completion witness, so the Deflate figure could
   not have failed.
6. `source_revision=unknown` recorded a *failed* git call as though the tree
   were clean; replaced by a 238-file content manifest on the VM and by a real
   git revision from a bundle on SCARF.
