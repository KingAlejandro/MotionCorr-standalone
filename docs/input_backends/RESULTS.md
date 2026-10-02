# Input backends: census, routes, correctness and performance

Branch `experiment/input-backends-v2`, based on `main` at `c499b1d` (merged
#128). Not based on #133's ancestry: that PR rewrites the same CUDA session for
plan pooling, and keeping the input work off it is what lets the two be
reviewed apart.

## 0. Format census

Every variant is generated losslessly from the RELION tutorial movies by
`harness/gen_matrix.py` — one decode per source movie, every variant written
from the same in-memory sample array. The tutorial data is counting-mode: the
maximum sample over `20170629_00021` is **68**, so a uint8 re-encode is
value-lossless and the generator refuses it outright if any sample would not
fit. That is what makes "the same movie in another format must produce the same
products" an exact gate rather than an approximation.

Dimensions are read independently with `tifffile`, not inferred from the
filename. All variants: 3710 x 3838, 1 sample/pixel, contiguous planar,
little-endian native, `FillOrder` absent (MSB2LSB), 24 frames unless stated.

| variant | codec | sample | bits | predictor | rows/strip | strips/frame | frames | bytes (movie 00021) |
|---|---|---|---|---|---|---|---|---|
| `u16_deflate_rps1` *(the tutorial files, unmodified)* | Deflate | uint | 16 | 1 | 1 | 3838 | 24 | 126,550,106 |
| `u8_lzw_rps1` | LZW | uint | 8 | 1 | 1 | 3838 | 24 | 106,902,076 |
| `u8_lzw_rps64` | LZW | uint | 8 | 1 | 64 | 60 (last 2 rows) | 24 | 95,181,204 |
| `u8_deflate_rps1` | Deflate | uint | 8 | 1 | 1 | 3838 | 24 | 92,573,485 |
| `u8_deflate_rps16` | Deflate | uint | 8 | 1 | 16 | 240 (last 14 rows) | 24 | 92,629,682 |
| `u16_lzw_rps1` | LZW | uint | 16 | 1 | 1 | 3838 | 24 | 128,052,925 |
| `u16_deflate_rps2` | Deflate | uint | 16 | 1 | 2 | 1919 (exact) | 24 | 125,726,947 |
| `u16_deflate_rps8` | Deflate | uint | 16 | 1 | 8 | 480 (last 6 rows) | 24 | 123,795,665 |
| `u16_deflate_rps512` | Deflate | uint | 16 | 1 | 512 | 8 (last 254 rows) | 24 | 123,084,401 |
| `u16_deflate_pred2` | Deflate | uint | 16 | **2** | 1 | 3838 | 24 | 149,825,412 |
| `u16_raw_rps1` | none | uint | 16 | 1 | 1 | 3838 | 24 | 684,029,576 |
| `u16_deflate_rps1_48f` | Deflate | uint | 16 | 1 | 1 | 3838 | **48** | 255,681,005 |
| `u8_lzw_rps1_48f` | LZW | uint | 8 | 1 | 1 | 3838 | **48** | 213,804,156 |
| `u8_deflate_rps1_48f` | Deflate | uint | 8 | 1 | 1 | 3838 | **48** | 185,146,973 |

Two format classes are **out of scope and unchanged**: EER (rendered by
`renderEER`, never offered to either accelerated route) and compressed MRC
(`isCompressedMRC`, same). Nothing here was run on EER or MRC input and nothing
here claims anything about them.

The 48-frame variants are the 24 frames tiled twice. They exercise frame count,
the nvCOMP batch selector and the staging mapping; they are not a second
specimen and the per-frame content repeats.

### What a deposited uint8 LZW movie is, and is not, represented by

The deposited real-data files that motivated this work are LZW uint8. The
`u8_lzw_*` variants above hold **real cryo-EM counting-mode content at a real
detector geometry in exactly that encoding**, but they are re-encodes of the
tutorial collection, not the deposited files. Codec work, sample width, strip
geometry and frame count are faithful; the specimen, the detector and the
compression ratio a different collection would reach are not. No performance
figure here is a measurement of the deposited collection.

## 1. What changed

Two changes, separable and separately reviewable.

**A. The compact route admits unsigned 8-bit TIFF.** The compact route decodes
with LibTIFF into host staging held in the file's own sample type, then expands
to float on the device together with the gain and the unaligned sum. It existed
for `UShort` only, so an 8-bit TIFF — the sample type most deposited LZW movies
use — materialised a host float movie four times the size of its own samples
and uploaded it. The staging class, the conversion kernel and the gain/sum entry
point are now written once over the sample type and instantiated for
`unsigned char` and `unsigned short`. Admission is by sample-type name, not by
width: `SChar` shares `BitsPerSample == 8` and converts differently, and rwTIFF
gives IMOD's packed 4-bit K2/K3 format its own `UHalf` type.

**B. The nvCOMP route admits 8-bit samples and any `RowsPerStrip`.** Both
restrictions lived in the staging arithmetic, not in anything the decoder
requires: a TIFF strip is one independent Deflate stream whatever its row count,
so it is one nvCOMP chunk either way. Strip slots carry the output alignment and
rows inside a strip are contiguous, which reduces to the released one-row
arithmetic exactly when `RowsPerStrip` is 1. No stream is concatenated or split.
The per-chunk declared length, the Adler-32 recomputation and the decoded-length
check all follow the short final strip.

A defect found while building B is worth recording because the device could not
have shown it: `frameStageBytes` sized the compressed staging by walking `ny`
entries of a per-strip vector. With one row per strip those are the same number.
With any larger `RowsPerStrip` it read past the vector, and the resulting
nonsense size made every multi-row movie decline the fast path on the pinned
budget — a silent fallback to a correct slower route, with correct products.

## 2. Route matrix

`--ingest_witness` records the route every movie actually took; these are the
recorded values, not the intended ones. `main` is `c499b1d`; the candidate is
this branch.

| variant | route on main | route on this branch | changed by |
|---|---|---|---|
| `u16_deflate_rps1` | nvcomp | nvcomp | — (null control) |
| `u16_lzw_rps1` | compact | compact | — (null control) |
| `u16_deflate_pred2` | compact | compact | — (null control) |
| `u16_raw_rps1` | compact | compact | — (null control) |
| `u8_lzw_rps1` | **float** | **compact** | A |
| `u8_lzw_rps64` | **float** | **compact** | A |
| `u8_deflate_rps1` | **float** | **nvcomp** | A + B |
| `u8_deflate_rps16` | **float** | **nvcomp** | A + B |
| `u16_deflate_rps2` | compact | **nvcomp** | B |
| `u16_deflate_rps8` | compact | **nvcomp** | B |
| `u16_deflate_rps512` | compact | **nvcomp** | B |
| `u16_deflate_rps1_48f` | nvcomp | nvcomp | — |
| `u8_lzw_rps1_48f` | **float** | **compact** | A |
| `u8_deflate_rps1_48f` | **float** | **nvcomp** | A + B |

Four variants keep their route on both arms and are the null controls for
everything below. Predictor 2 and uncompressed input are *not* newly accepted
by the fast path: they were already served by the compact route, and still are.

## 3. Correctness

### 3.1 Decoded-sample oracle

`harness/dump_native_samples` dumps the movie exactly as the compact route
stages it — same `Image<T>::read`, same sample type, same memory order — and
`harness/compare_native_samples.py` compares every sample against an
independent `tifffile`/`imagecodecs` decode, a different codec implementation
from LibTIFF.

All 11 single-frame-count variants, movie `20170629_00021`:
**341,735,520 samples compared per variant, 0 differing, 11/11 PASS.**

The comparator is not merely returning "identical". Four controls fire on every
variant:

| control | what it would catch |
|---|---|
| unflipped row order detected | the TIFF→MRC row flip being absent or applied twice |
| within-row permutation detected, with row sums unchanged | two samples exchanged inside a row — invisible to any row-sum or row-hash check |
| single-bit flip detected | one sample wrong by one |
| dropped frame detected | a short movie compared as if complete |

### 3.2 Device-free staging and strip arithmetic

`tests/test_deflate_layout.cpp` exercises the strip geometry over both sample
widths, `RowsPerStrip` of 1/2/4/7/8/whole-frame, four output alignments, and a
height that no tested `RowsPerStrip` divides. It asserts that the declared chunk
bytes sum to exactly one frame, that row offsets strictly increase and stay
inside the frame slab, that rows inside a strip are contiguous, that each strip
slot meets the alignment, and that `RowsPerStrip == 1` reproduces the released
row-pitch addressing exactly.

Three compiled mutants of the production arithmetic each turn it red:

| mutant | checks that fail |
|---|---|
| final strip declared at full length | declared-chunk-byte sum, 27 checks |
| strip slots unaligned | strip-slot alignment, 18 checks |
| padding inserted between rows inside a strip | row contiguity, 56 checks |

`tests/test_native_movie_staging.cpp` runs the staging ownership contract for
both `unsigned short` and `unsigned char`: aliasing, `coreAllocateReuse`
retention, incremental `discardThrough` with a measured resident-set drop, and
`release()` returning the payload to the kernel. It carries its own instrument
self-check (the sampler must see the mapping arrive before an assertion about
it leaving means anything) and a per-frame-heap diagnostic control.

## 4. Measured

Venue: `4GPUs` (`4-gpu-vm`), 4x A100 80GB PCIe, 124 logical CPUs. Every run
under `taskset -c 96-103` (8 CPUs) with `--j 8 --gpu <free index>`, inside one
`flock /tmp/motioncorr-bench.lock` acquisition, on a GPU with no foreign compute
app on its UUID. **The box is shared**: two other MotionCorr sessions were
building and running throughout, load1 ranged 2.3-14, and that is recorded per
run in the campaign log. Both binaries were built from scratch inside the same
lock acquisition by one script with one set of flags, so build provenance is not
a variable.

Options for every run: `--use_own --dose_weighting --dose_per_frame 1.277
--patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc --seed 1`.
Six movies for the 24-frame single-row variants, two for the rest. All reads are
**warm cache** — the variants were written minutes earlier and read repeatedly.
No cold or network-storage figure is given; dropping the page cache needs root
on this host.

### 4.1 Per-movie wall, from the runner's own log

This is the headline metric, not process wall. A 6-movie run at this geometry
is startup-dominated — the CUDA context and first-use module loading land
inside movie 1 — so process wall divided by six is not a per-movie cost. The
figures below are the median of the movies after the first.

| variant | route change | main s/movie | branch s/movie | change | n |
|---|---|---|---|---|---|
| `u16_deflate_rps1` | nvcomp → nvcomp | 0.472 | 0.458 | −3.0% | 5 |
| `u16_lzw_rps1` | compact → compact | 0.954 | 0.963 | +0.9% | 5 |
| `u16_deflate_pred2` | compact → compact | 0.980 | 0.987 | +0.7% | 1 |
| `u16_raw_rps1` | compact → compact | 0.802 | 0.779 | −2.9% | 1 |
| `u16_deflate_rps1_48f` | nvcomp → nvcomp | 0.704 | 0.676 | −4.0% | 1 |
| `u8_lzw_rps1` | **float → compact** | 0.867 | 0.766 | **−11.6%** | 5 |
| `u8_lzw_rps64` | **float → compact** | 0.994 | 0.704 | **−29.2%** | 1 |
| `u8_lzw_rps1_48f` | **float → compact** | 1.924 | 1.406 | **−26.9%** | 1 |
| `u8_deflate_rps1` | **float → nvcomp** | 0.811 | 0.452 | **−44.3%** | 5 |
| `u8_deflate_rps16` | **float → nvcomp** | 0.930 | 0.462 | **−50.3%** | 1 |
| `u8_deflate_rps1_48f` | **float → nvcomp** | 1.736 | 0.693 | **−60.1%** | 1 |
| `u16_deflate_rps2` | **compact → nvcomp** | 0.806 | 0.449 | **−44.3%** | 1 |
| `u16_deflate_rps8` | **compact → nvcomp** | 0.810 | 0.471 | **−41.9%** | 5 |
| `u16_deflate_rps512` | **compact → nvcomp** | 0.783 | 0.583 | **−25.5%** | 1 |

The five unchanged-route rows span −4.0% to +0.9%. That is the noise floor of
this metric on this host, and every changed-route row is far outside it. Rows
with n=1 are single observations on the two-movie variants, not medians.

### 4.2 Host memory and CPU, whole process

`Maximum resident set size` from `/usr/bin/time -v`, and user+sys CPU seconds.

| variant | frames x movies | main RSS | branch RSS | main CPU-s | branch CPU-s |
|---|---|---|---|---|---|
| `u16_deflate_rps1` | 24 x 6 | 554 MiB | 552 MiB | 6.1 | 7.2 |
| `u16_lzw_rps1` | 24 x 6 | 905 MiB | 905 MiB | 25.2 | 23.5 |
| `u16_deflate_pred2` | 24 x 2 | 906 MiB | 906 MiB | 8.1 | 8.1 |
| `u16_raw_rps1` | 24 x 2 | 974 MiB | 993 MiB | 4.7 | 4.7 |
| `u8_lzw_rps1` | 24 x 6 | 1561 MiB | **581 MiB** | 22.9 | 18.4 |
| `u8_lzw_rps64` | 24 x 2 | 1557 MiB | **580 MiB** | 8.4 | 5.6 |
| `u8_deflate_rps1` | 24 x 6 | 1561 MiB | **486 MiB** | 21.4 | 5.8 |
| `u8_deflate_rps16` | 24 x 2 | 1557 MiB | **464 MiB** | 7.5 | 2.7 |
| `u16_deflate_rps8` | 24 x 2 | 907 MiB | **546 MiB** | 15.1 | 6.2 |
| `u16_deflate_rps2` | 24 x 2 | 906 MiB | **533 MiB** | 5.9 | 2.8 |
| `u16_deflate_rps512` | 24 x 2 | 928 MiB | **526 MiB** | 5.7 | 3.0 |
| `u8_lzw_rps1_48f` | 48 x 2 | 2864 MiB | **907 MiB** | 16.2 | 10.8 |
| `u8_deflate_rps1_48f` | 48 x 2 | 2865 MiB | **671 MiB** | 14.8 | 3.6 |
| `u16_deflate_rps1_48f` | 48 x 2 | 537 MiB | 538 MiB | 3.8 | 3.8 |

The 48-frame uint8 rows are the ones closest to the real-data shape that
motivated this work: **2.80 GiB of host resident set becomes 0.89 GiB on the
compact route and 0.66 GiB on nvCOMP.** That is per worker, so it is what
decides how many workers a host can carry.

The `u16_deflate_rps1` CPU-second row is the one anomaly: +1.1 s on an identical
route. It is a single cold-binary first run — the candidate executable's first
execution of the campaign — and the per-movie table above shows the same arm
3.0% *faster* in steady state. §4.4 measures it directly.

### 4.3 Transcoding as an operational mode

Measured on one core of the same host with `imagecodecs`, which wraps the same
C codecs LibTIFF uses, over the 683 MB of samples in one 24-frame movie:

| operation | throughput | per 24-frame movie, 1 core |
|---|---|---|
| Deflate decode, uint16 | 227 MB/s | 3.0 s |
| Deflate encode, uint16 | 9.0 MB/s | 75.7 s |
| Deflate encode, uint8 | 6.9 MB/s | 49.6 s |
| LZW encode, uint8 | 99 MB/s | 3.4 s |

Converting a uint8 LZW movie to uint8 Deflate therefore costs **~50 s of core
time per movie**, about 6-7 s wall at 8 cores. The per-pass saving it buys is
the compact-to-nvCOMP step for that movie: 0.766 s → 0.452 s, i.e. 0.314 s.

**Break-even is about 21 full repeated passes at 8 cores** (160 single-core).
Disk is not a cost here — uint8 Deflate is 13% *smaller* than uint8 LZW for this
content — but keeping the deposited original means holding both copies, and the
converted copy needs its own losslessness check (the decoded-sample oracle takes
about two minutes per movie on this host).

For a one-pass or two-pass workflow, transcoding does not pay. For a facility
that reprocesses the same collection tens of times it does. Either way it is an
operational decision made outside MotionCorr, and no performance figure in §4.1
or §4.2 includes or assumes a conversion.

## 5. What is still unsupported, and by what

| input | route | why |
|---|---|---|
| EER | `float` (via `renderEER`) | never offered to either accelerated route; untouched and untested by this work |
| compressed MRC | `float` | same |
| other MRC movies | `float` | not a TIFF |
| signed 8- or 16-bit TIFF (`SChar`, `SShort`) | `float` | different conversion; admitted by neither route, deliberately |
| 32-bit float TIFF | `float` | the staging and the kernels are integer-sample |
| IMOD packed 4-bit K2/K3 (`UHalf`) | `float` | rwTIFF doubles the logical width; excluded by name from compact and by the geometry check from nvCOMP |
| any TIFF with no resident CUDA session | `float` | CPU build, `--early_binning`, or a session that failed to initialise |
| Deflate TIFF with predictor 2, non-native byte order, non-MSB2LSB fill order, >1 sample/pixel, separate planes | `compact` if LibTIFF decodes it to `UChar`/`UShort`, else `float` | nvCOMP declines these by name and the log says which |

The compact route's admission rule is exactly "rwTIFF reports `UChar` or
`UShort`". That covers any codec, strip geometry and predictor LibTIFF can
handle, which is the point — the decode is LibTIFF's. Eleven encodings were
exercised end to end; the rule is broader than the set tested.

## 6. Memory and staging design

What each route holds, for a 24-frame 3710x3838 movie (and 48 frames in
brackets where it differs):

| | host, per movie | device staging | pinned |
|---|---|---|---|
| `float` | 1.27 GiB float movie [2.55 GiB] | none beyond the resident float movie | none |
| `compact`, uint16 | 0.64 GiB native mapping [1.27 GiB] | one frame, 27 MiB | none (pageable) |
| `compact`, uint8 | 0.32 GiB native mapping [0.64 GiB] | one frame, 14 MiB | none (pageable) |
| `nvcomp` | the compressed strips only, ~120 MiB | borrowed from the pre-FFT Fourier buffer, additional VRAM 0 | one pool per worker, `pinnedReserveBytes(payload)`, capped by `MOTIONCORR_NVCOMP_PINNED_MAX_MB` (default 256 MiB) |

The host mapping is one `mmap`, released by `munmap` rather than `free`, so the
kernel reclaims every page instead of returning them to a malloc arena. Frames
are widened and discarded in ascending order on the degraded paths, so a
fallback's peak stays where one allocation per frame left it.

**No deeper staging queue was built, deliberately.** A bounded slot queue only
pays if the decode is on the critical path, and it is not: the measured
consumer wait on this workload is under 5 s of a 100-180 s 24-movie run, and a
one-movie-ahead prefetch has already been measured here as a no-go that raised
host RSS 86% for no wall gain. The quantity that limits workers per host is
residency, and §4.2 is what moves it. General overlap policy belongs to a
separate owner and nothing here pre-empts it.

**Pinned vs pageable for the compact route is unmeasured and unimplemented.**
The compact route uses pageable host memory with a blocking per-frame copy.
Pinning it would cost 0.32-1.27 GiB of pinned memory per worker — the same
resource this change exists to reduce — to recover at most the H2D time in
§4.4. That trade is stated, not taken.
