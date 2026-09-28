# Issue #85 lane A — where the TIFF ingest time actually goes

Attribution benchmark for the `read movie` stage of the native-CUDA tutorial run.
This lane measures. It changes no production behaviour: `src/rwTIFF.h`,
`src/image.h` and `src/motioncorr_runner.cpp` are byte-identical to `5ada983`.

## The question

The #109 operating-envelope report records, for the native-CUDA 24-movie tutorial
run (product `4c952b3f`, one A100 80 GB PCIe VM, `--j 8` / `--max_io_threads 8`,
warm, DW-only, 5×5 patches, gain, lane `taskset -c 96-111` = **16** logical CPUs):

| stage | s |
| :-- | --: |
| `read movie` | **7.127** |
| `apply gain and initial sum` | 4.403 |
| `write corrected image` | 2.754 |
| whole application | 29.779 |

Lane A asks what those 7.127 s consist of, so the follow-on lanes (persistent
handles, strip batching, native uint16 staging, custom CPU Deflate, nvCOMP) are
chosen from measurement rather than from the shape of the code.

## What the input is

Parsed from the IFDs of the tutorial movies by the harness itself, not assumed:

| property | value |
| :-- | :-- |
| geometry | 3710 × 3838 × 24 frames |
| sample | 16-bit unsigned (`BitsPerSample=16`, `SampleFormat=1`) |
| compression | 8 — Adobe Deflate |
| predictor | 1 — none |
| `RowsPerStrip` | 1 |
| strips per frame | 3838 |
| strips per movie | 92,112 |
| `TIFFStripSize` | 7,420 B (one row) |
| largest compressed strip | 1,493 B |
| compressed bytes / movie | 125,808,249 |
| decoded as uint16 | 683,471,040 B (0.637 GiB) |
| decoded as float32 | 1,366,942,080 B (1.273 GiB) |

Decoding one movie is 92,112 independent `inflate` calls averaging ~1.37 KB of
compressed input each.

## Method

`benchmarks/tiff_ingest_bench.cpp` times a chain of arms in which each arm adds
exactly one component to the one above it, so the differences are additive:

| arm | adds |
| :-- | :-- |
| `pread_strip_extents` | storage read of the compressed strip extents |
| `tiff_read_raw_strip` | + LibTIFF strip bookkeeping |
| `tiff_decode_only` | + Deflate |
| `decode_place_u16_natural` | + writing decoded rows to a destination |
| `persistent_handle_to_u16` | + Y-flipped placement |
| `persistent_handle_to_f32` | + uint16→float conversion |
| `openperframe_handle_to_f32` | + one `TIFFOpen` per frame |
| `production_image_read` | + the `Image`/`fImageHandler` lifecycle and allocation |

`production_image_read` calls `Image<float>::read(path, true, f, false, true)`
inside `#pragma omp parallel for`, which is the shipping code at
`src/motioncorr_runner.cpp` `RCTIC(TIMING_READ_MOVIE)`. Its scope matches that
region exactly: the per-frame pixel allocation inside `read()` is timed, because
production pays it there; the `Iframes` vector resize and its 1.37 GiB
destruction are not, because production does those outside the region.

Persistent arms open one `TIFF*` **per worker**, inside the parallel region, and
reuse it and its strip scratch across every frame that worker is given. Side
arms price the components that are not on the chain: metadata handling,
standalone conversion, allocation and first touch, OpenMP dispatch, and
strip-batch scheduling.

Worker counts 1, 2, 4, 8, 16, 24. Median of 3 per movie. Per-movie medians are
summed to a set total, because the production loop processes movies strictly one
after another.

## Correctness

Every arm that materialises pixels is compared to the production reference by
**exact ordered equality over all 341,735,520 floats of the movie**, at every
worker count and on every repeat — not a checksum, not row sums.

Two deliberately weaker oracles run alongside so their blind spots are on the
record, and five mutation classes are injected into a live arm's real output so
a PASS is falsifiable rather than structural. See `report.md`.

## Regimes

Kept separate, never merged into one table:

1. **warm page cache, local ext4** — the regime the 7.127 s figure was measured in.
2. **tmpfs (`/dev/shm`)** — no block layer at all.
3. **cold file, local ext4** — `posix_fadvise(POSIX_FADV_DONTNEED)` on the movie
   before each repeat. This evicts that file's clean pages only. It does not
   clear LibTIFF, allocator or CPU state, so it is a cold-*file* arm, not a cold
   machine, and it is named that way.

Neither the GPU host nor cpu64 has a network or shared filesystem mounted
(`/home` is local ext4 on both), so **no shared-storage regime was measured
here**. The only shared-storage datapoint for this workload remains the
historical #85 PanFS figure of 10.1 s cold for the 3.04 GB dataset (~306 MB/s),
which this lane did not reproduce.

## Files

| file | contents |
| :-- | :-- |
| `report.md` | the answer, the tables and the GO/NO-GO calls |
| `raw/` | every raw JSON arm result, unedited |
| `identity.txt` | host, mask, toolchain, GPU UUIDs, source and binary hashes |
| `source_manifest_sha256.txt` | sha256 of all 238 compiled source files |
| `input_sha256.txt` | sha256 of all 24 input movies |
| `interference.jsonl` | 30 s samples of foreign CPU on the measurement mask |
| `cpu_stat_delta.txt` | per-core busy jiffies across the whole run |
