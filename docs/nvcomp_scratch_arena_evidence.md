# nvCOMP ingestion: scratch arena, fail-closed controls, and corrected timings

Source revision: this commit. Host: `4-gpu-vm`, 4x NVIDIA A100 80GB PCIe, AMD EPYC,
CUDA 12.8 (nvcc V12.8.61), gcc 13.3.0, libtiff 4.5.1 linked against **libdeflate**,
THP `madvise`, nvCOMP **5.3.0.16** (`nvcomp-linux-x86_64-5.3.0.16_cuda12-archive`,
sha256 `1def6bb0…3ec23f6f`, matching the version used for the SCARF report).
Box quiet and all four GPUs idle at 0% / 1 MiB for every measurement; GPU selected by
UUID via `CUDA_VISIBLE_DEVICES`, host work pinned with `taskset -c 0-7`.
Movies: all 24 RELION 3.0 tutorial TIFFs, 3710 x 3838 x 24.

## 1. What the library actually requires

`nvcompBatchedDeflateDecompressGetRequiredAlignments` on the installed 5.3.0.16
returns **input = 4**, output = 1, temp = 1, and `deflate.h` states each compressed
chunk *must* meet `input`. Deflate decompression reports **temp_bytes = 0** at every
batch size tried, including 92,112 chunks.

The previous revision passed `cudaMalloc` base + 2 for every chunk, so roughly three
quarters of the 92,112 input pointers violated that requirement. It decoded correctly
on A100, which is why a pixel comparison could not observe the defect.

## 2. Peak VRAM

Per-process VRAM sampled every 20 ms for the whole run (`nvidia-smi
--query-compute-apps`, filtered on our own PID).

| Arm | Movies | Peak VRAM | vs control |
|---|---|---|---|
| control, `USE_NVCOMP=OFF` (host read) | 24 | 3484 MiB | — |
| scratch arena (this change) | 24 | **3484 MiB** | **0** |
| `f038e51` as pushed | 6 | 4046 MiB | +562 MiB |

The whole movie fits one batch: `scratch=813593088/1367678976 bytes borrowed from the
pre-FFT Fourier buffer`. Sampling can only understate a peak, so read +562 MiB as a
lower bound; the 0 is consistent with the design (no `cudaMalloc` for staging) rather
than independently proved by sampling.

## 3. Product equality

24/24 output MRC compared from byte 1024 (the header carries a timestamp): **0 data
mismatches**. 25/25 STAR files identical after dropping absolute-path lines.

Not vacuous: all 24 movies logged an `nvCOMP ingestion:` line with **0** fallbacks,
and the control arm logged 0 nvCOMP lines.

## 4. Fail-closed controls

Two fault classes injected into strip 100 of one movie, one fixture each.

| Fault | scratch arena | `f038e51` | control |
|---|---|---|---|
| corrupted Deflate payload | refuses, 0 micrographs | **1 micrograph** | refuses |
| FDICT set in the zlib header | refuses, 0 micrographs | **1 micrograph** | refuses |

Each guard identifies itself, so the two are distinguishable:
`nvCOMP rejected strip 100 … status=14 bytes=7520 expected=7420` for the payload case,
`unusable zlib wrapper` for the FDICT case. A healthy 2-movie run in the same build
produces 2 micrographs with 0 wrapper warnings, so neither guard fires spuriously.

`f038e51` allocates `device_statuses` and the actual byte counts and never reads
either, so a failed chunk leaves uninitialised device memory to be cast to float,
gain-applied and aligned, and the function returns success.

## 5. Ingestion speed, corrected methodology

`tools/bench_ingest.cu`, 24 movies x 5 **complete** pipelines per arm, arm order
alternated between reps, all observations retained, median reported. Every arm starts
at "movie bytes requested" and ends at "float32 frames resident in VRAM". Page cache
warm for all arms.

| Arm | Median / movie | Total |
|---|---|---|
| A libtiff decode -> host float32 -> H2D (current production) | 289 ms | 6948 ms |
| B libtiff decode -> host uint16 -> H2D -> convert | 214 ms | 5157 ms |
| C raw strips -> aligned pinned -> compressed H2D -> nvCOMP -> convert | **52.5 ms** | 1259 ms |

**C vs A 5.52x, C vs B 4.10x.** Arm C includes aligned repacking, wrapper validation,
metadata transfers and per-chunk status plus byte-count verification.

This supersedes the 12.4x figure, which summed independent per-stage minima from
different repetitions and began the GPU arm after the compressed bytes were already
in host RAM. Two further differences from the SCARF measurement, both reducing the
ratio here: this host's libtiff uses libdeflate rather than zlib, and the warm page
cache removes disk from all three arms equally.

## 6. End-to-end, after removing the two costs outside ingestion

The first measurement of the integrated path was *slower* than the host reader:
48.4 s against 34.3 s over 24 movies. Two costs outside ingestion accounted for it,
and both are now removed.

**Pinned staging moved to worker lifetime.** `CudaMovieSession` is constructed and
destroyed once per movie, so a session-owned buffer paid `cudaHostAlloc` (~110 ms for
126 MiB) and `cudaFreeHost` (~43 ms) on every movie. The pool is now `thread_local`
and outlives the session. Sized exactly it still reallocated on 7 of 24 movies,
because compressed size drifts a few MiB between movies of the same geometry; with
12.5% headroom rounded to 32 MiB it is **allocated once per run**, which the log
records ("pinned staging pool grown to 167772160 bytes for a 126069120-byte request").

**Hot-pixel replacement no longer downloads the movie.** See the section below.
`Could not download frames` appears 0 times and all 24 movies still report
`Fixed hot pixels`.

Repeated as a **matched interleaved study** on one head, arms alternating within each
repetition, every observation kept. `--j 4`, `taskset -c 0-7`, one A100 selected by
UUID, 24 movies, `--seed 1`.

| Arm | n | median | min | max |
|---|---|---|---|---|
| main `6393547` | 4 | 33.59 s | 32.57 | 33.84 |
| this branch, `USE_NVCOMP=OFF` | 4 | 33.31 s | 31.86 | 33.40 |
| this branch, nvCOMP | 4 | **15.88 s** | 15.67 | 15.91 |

**2.12x against main, 2.10x against the branch's own control** at this thread count,
peak VRAM unchanged at 3484 MiB. See the matched sweep below: at `--j 8` the baselines
are considerably faster and the defensible figure is 1.71x. A separate 5-repetition interleaved run of the latter two agreed: 33.25 s
versus 15.81 s.

Main and the branch control are within 1% of each other, so the #115 lineage this
branch carries is not inflating the baseline and the control is representative. These
figures include the Adler-32 verification added later, which is therefore not
measurably expensive at this scale.

The end-to-end saving (~730 ms/movie) is larger than the ingestion-stage saving
(237 ms/movie) predicts. The likely remainder is that the control materialises a
1.27 GiB host `Iframes` buffer per movie and the nvCOMP path never does; a cold
allocation of that size plus fill measured ~1.0 s. This attribution is **inferred**,
not isolated.

## Limitations

Wall-clock figures in section 6 are single runs taken without box-wide exclusivity
and are not a timing study, though the control was repeated three times at 34.3-35.3 s
and the two arms differ by more than 2x; the section 5 medians are proper repeats.
One host only. The added `nvCOMP ingestion:` lines break byte-exact log parity with
the host-read path. The scenario matrix uses 4 movies, since defect geometry rather
than movie content selects the branches; the 24-movie comparison is the default
auto-hot-pixel case only.

---

# Sparse hot-pixel neighbour gathering

## Why the whole-movie download was avoidable

The replacement loop reads exactly one neighbour per (defect, frame): it gathers every
valid neighbour into a buffer and takes entry `rand() % n_ok`. Two properties make a
sparse form exact rather than merely equivalent:

- `n_ok` depends only on the defect mask and the image bounds, never on pixel values,
  so it is computable before any frame data exists;
- the draw is therefore an index into a value-independent ordering, so the selected
  neighbour resolves to a coordinate that can be fetched afterwards.

`rand()` is still called on exactly the branch where `n_ok > NUM_MIN_OK`, and
`rnd_gaus()` on the other, in the same defect-then-frame order. Both draw from the
same stream, so preserving the branch pattern preserves the stream.

`src/defect_neighbours.h` holds the two functions; `tests/test_defect_neighbours.cpp`
checks the resolved coordinate against a literal transcription of the original gather
over isolated defects, every edge and corner, a 5x5 dense block, a full bad row and
column, a fully masked image, and the EER radius `d_max = 4`. Four mutants were
caught: rank off-by-one, reversed scan order, a clamped negative rank, and a count
that ignores the mask.

## Scenario matrix

Control build (`USE_NVCOMP=OFF`, original dense loop, host frames) versus nvCOMP build
(sparse gather), 4 movies, `--seed 1`, products compared as MRC data past the header
and STAR text.

| Scenario | bBad sources exercised | MRC data mismatches | STAR differing |
|---|---|---|---|
| gain | auto hot pixels (67) | 0 / 4 | 0 / 5 |
| nogain | auto hot pixels (237) | 0 / 4 | 0 / 5 |
| defectfile | defect file + gain-zero + auto | 0 / 4 | 0 / 5 |
| gainzero | gain-zero (41) + auto | 0 / 4 | 0 / 5 |
| dense_nogain | defect file + auto, no gain | 0 / 4 | 0 / 5 |

The defect fixture is deliberately dense: 312 defect-file pixels, of which
**102 take the neighbour branch and 210 take the Gaussian branch** (counted with the
same helper the runner uses, at `D_MAX = 2`, `NUM_MIN_OK = 6`). Both branches are
therefore exercised, and the 15x15 and 9x9 solid blocks are the dense-defect case.

## The two controls that make those zeros mean something

**The scenarios are distinct.** Each differs from its neighbours in all 4 micrographs:
gain vs defectfile, gain vs gainzero, gain vs nogain, and nogain vs dense_nogain all
report 4/4 data mismatches. A fixture that silently masked nothing would have shown 0.

**The oracle can see a wrong replacement.** A mutant build taking the neighbour one
rank along (`(rand() + 1) % n_ok`) produces **4/4 data mismatches in every one of the
five scenarios**. So MRC equality is sensitive to a single-rank change in one selected
neighbour, and the zeros above are a result rather than an insensitive comparison.

---

# Matched sweep across sources, one setting

> **This supersedes the 2.12x figure in section 6.** That was measured at `--j 4`,
> where the CPU decode baseline is starved. At `--j 8` on the same 8 logical CPUs the
> baselines are much faster and the correct statement is **1.71x over main**.

Every source built the same way (Release, `CUDA=ON`, `sm_80`) and run under one
setting: one A100 selected by UUID, `taskset -c 0-7`, `--j 8`, the same 24 tutorial
movies from the same directory, `--seed 1`, identical options. Arms rotate within
each repetition so drift is shared; 4 repetitions, all observations kept.

| Source | What it is | n | median | min | max |
|---|---|---|---|---|---|
| this head | nvCOMP + arena + hardening | 4 | **15.85 s** | 15.84 | 16.78 |
| `b16c228` | nvCOMP, before the format/integrity checks | 4 | 15.71 s | 15.43 | 15.90 |
| `584b1c5` | #118 compact uint16 | 4 | **21.63 s** | 21.45 | 21.80 |
| `8323c55` | #118 base | 4 | 26.92 s | 26.62 | 29.03 |
| `caf0375` | #121 tested source | 4 | 26.97 s | 26.77 | 27.64 |
| `main` `6393547` | current main | 4 | 27.05 s | 26.92 | 27.45 |
| `4c952b3f` | #109 source | 4 | 27.22 s | 27.07 | 29.09 |

- **1.71x over main**, and **1.36x over `584b1c5`**, the best non-nvCOMP source. The
  1.36x is the number that matters for integration: it is the incremental win over
  the compact-uint16 direction, not over the float baseline that is already being
  replaced.
- The format and integrity hardening costs **0.9%** (15.85 s against 15.71 s), about
  6 ms per movie. Adler-32 verification of 92,112 strips is not measurably expensive.
- Main, `8323c55`, `caf0375` and `4c952b3f` all sit within 1% of each other at
  26.9-27.2 s, so there is no regression among them and no advantage to `caf0375`
  under these conditions. Its original 17.63 s was measured with 24 logical CPUs and
  node-local storage; that advantage does not survive an 8-CPU setting.
- **All seven sources produce byte-identical micrograph data** across all 24 movies
  (compared past the MRC header), so the wall times are comparing the same work.

The published figures for these sources differ from the table above because they were
taken under different CPU counts and storage. Re-running them under one setting is
the point; the numbers here are not directly comparable to the originals and do not
contradict them.

---

# Format eligibility and integrity hardening

## The eligible encoding is enumerated positively

Raw Deflate decompression reproduces LibTIFF only for one exactly-specified encoding.
Pass A now refuses anything outside it with a named reason and falls back, rather than
defaulting tags it does not implement:

predictor 1, `SAMPLEFORMAT_UINT`, 16 bits, one sample per pixel, contiguous planar,
native byte order (`TIFFIsByteSwapped`), `FILLORDER_MSB2LSB`, Deflate, and one full
row per strip.

## Adler-32 is verified rather than discarded

Passing nvCOMP only bytes `[2, n-4)` drops the RFC 1950 checksum that LibTIFF's zlib
path verifies. Per-chunk status and decompressed length do not replace it: a
corruption that still inflates to the right number of bytes is reported as success.

`adler32StripsKernel` recomputes it per strip, one block each, using the closed forms
`A = 1 + sum(d_i)` and `B = n + sum((n - i) * d_i)` so the serial recurrence becomes
two reductions; the weighted sum needs 64 bits (~1.4e10 for a 7420-byte row). The
closed form was checked against the RFC 1950 recurrence over lengths 1 to 16384 and
all-zero, all-255 and random content.

## Results

Control build (`USE_NVCOMP=OFF`, LibTIFF) against the guarded nvCOMP build. Fixtures
are 4-frame re-encodings of a tutorial movie, one IFD per frame.

| Fixture | nvCOMP build | Products vs control |
|---|---|---|
| `ok` | accepted, ingest runs | identical |
| `predictor2` | declined: `TIFFTAG_PREDICTOR != 1` | identical (via fallback) |
| `signed16neg` | declined: `TIFFTAG_SAMPLEFORMAT != UINT` | identical (via fallback) |
| `bigendian` | declined: `non-native byte order` | identical (via fallback) |
| `adler_only` | refused: Adler-32 mismatch | both arms fail, 0 micrographs |

`adler_only` differs from `ok` in exactly **4 bytes** — only the stored trailer. The
Deflate payload is untouched and inflates to the correct length, so status and size
cannot see it; libdeflate rejects the file with `LIBDEFLATE_BAD_DATA`.

## Each check is demonstrated necessary

A build with the four checks removed, same fixtures:

| Fixture | Without the check |
|---|---|
| `predictor2` | **segmentation fault** |
| `signed16neg` | **differs from control** — silently wrong pixels |
| `bigendian` | **differs from control** — silently wrong pixels |
| `adler_only` | **produces a micrograph the control refuses** |

An earlier `signed16` fixture built from unmodified tutorial data came out *identical*
without the check, because those values are all below 32768 and the reinterpretation
is a no-op. That fixture proved nothing and was replaced with one whose samples are
genuinely negative. Recorded because a declared harm class with no instance trains a
gate on benign examples.

## Pinned staging is capped, and the cap bounds the batch

Default 256 MiB per worker, `MOTIONCORR_NVCOMP_PINNED_MAX_MB` to change it. Batch
selection respects it alongside the arena:

| Cap | Batch chosen | Pinned staging | Products |
|---|---|---|---|
| 256 MiB (default) | 24 / 24 | 126069120 | reference |
| 64 MiB | 12 / 24 | 63034560 | identical |
| 16 MiB | 3 / 24 | 15758640 | identical |
| 1 MiB | declines, falls back | — | produced by host reader |

Byte-identical output at batch 3, 12 and 24 also exercises the multi-batch path: the
unaligned sum is carried in `d_Isum` between batches specifically so the float
accumulation order matches the single-launch whole-movie kernel.
