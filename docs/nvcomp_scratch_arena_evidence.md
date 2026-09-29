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

## 6. The integrated path is still slower end to end

Application wall, same 24 movies, one run each: arena **48.4 s** vs control **34.3 s**.
Ingestion saves only 237 ms per movie and the integration gives more than that back.
Two costs only this path pays, both measured on the same host:

- per-movie pinned staging: `cudaHostAlloc` 126 MiB = 110 ms, `cudaFreeHost` = 43 ms;
- the hot-pixel defect path downloads frames back, which all 24 movies enter: a cold
  1.27 GiB host allocation plus D2H measures ~1.0 s, plus 151 ms to free.

The split between these two is **inferred, not isolated**. The component costs are
measured. The direction is not in doubt: the regression is entirely outside ingestion.

The first is a defect in this change — the staging buffer belongs at session lifetime.
The second is the resident-path problem from #118/#125: the download exists only
because the runner derives `frame_mean`/`frame_std` from host frames before calling
`updateDefectPixels`, which already applies replacements on the device.

## Limitations

Wall-clock figures in section 6 are single runs taken without box-wide exclusivity and
are not a timing study; the section 5 medians are. One host only. The added
`nvCOMP ingestion:` log line breaks byte-exact log parity with the host-read path.
