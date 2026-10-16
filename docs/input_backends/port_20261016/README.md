# #138 nvCOMP Deflate widening, ported onto main `1db86902` (W-TIFF, #198)

Status: **draft, HOLD on #134 / D1.** Nothing here decides the trust question.

## What was ported

#137 is merged (`88785ffb` is an ancestor of main). #138 stacks on it, but its branch also carries the #151
checksum-repair composition, which main already has. Of its 38 commits only four change code, and they were
cherry-picked (`-x`, authorship kept) onto main's pipelined ingest:

| original | here | change |
|---|---|---|
| `40b60d04` | `883b6fd3` | 8/16-bit unsigned samples, any `RowsPerStrip` including a short final strip (templated kernel, per-chunk declared length) |
| `5ea94a29` | `90643a6c` | `StripGeometry` in `cuda_deflate_layout.h`, shared by planner and kernel; `test_deflate_layout` cases |
| `a86fb209` | `fe69b4f9` | `frameStageBytes` sized by strip count, not `ny` |
| `d6b8f035` | `157af3ce` | strip index hoisted out of the kernel's frame loop |

All four conflicted with main (the ingest function was rewritten), so the first two were re-applied by hand onto the
2-slot pipeline; the intermediate commits are not individually built. Two commits are new:

* `977a9cef`: main's span reader (`framePackedBytes` / `spreadPackedStrips`, added after #138) walked `ny` entries
  of the per-strip vector exactly as `frameStageBytes` did, so it has the same defect for any `RowsPerStrip > 1`.
  Fixed. The admission predicate moved into one named function, `admissionRefusal()` in `cuda_deflate_layout.h`.
* `25ff37c7`: `DeflateLayout` cases for multi-row strips inside a contiguous span read.

The docs commits of #138 (`docs/input_backends/RESULTS.md` rewrite, `FAILURE_POLICY.md`, `CHECKSUM_REPAIR.md`) were
not brought over: their timings are historical and were taken on the old loop.

### Pipeline structure is unchanged

`git diff 1db86902 HEAD -- src/acc/cuda/cuda_movie_session.cu` adds or removes no line containing `omp`, `TIFFOpen`,
`TIFFClose`, `runTeam`, `ChunkReaderPool`, `cudaStreamCreate`, `cudaEvent*`, `preadFully`, `cudaMemcpyAsync`,
`cudaStreamWaitEvent` or `n_slots`. The two-slot schedule, the once-per-movie `TIFF*` handles, the sleeping reader
team and the span reader are untouched; only strip count, per-chunk sizes, output pitch and the sample-type
dispatch changed. No per-batch OpenMP region or per-batch TIFF open is introduced.

## What newly reaches the GPU decoder (the D1 input)

`admissionRefusal(bits, rows_per_strip)`; both flags `true` is #138, both `false` is main.

| input | main | this branch |
|---|---|---|
| 16-bit unsigned, 1 row/strip, Deflate | nvCOMP | nvCOMP (unchanged) |
| 16-bit unsigned, `RowsPerStrip` > 1 (incl. whole frame) | compact | **nvCOMP** |
| 8-bit unsigned, any `RowsPerStrip` | compact | **nvCOMP** |
| predictor 2, big-endian, signed/float, planar, 12-bit etc. | host reader | host reader (refused before the library) |
| LZW, EER, MRC | not nvCOMP | not nvCOMP |

All other admission checks (zlib wrapper per strip, per-chunk status and decoded length, device Adler-32, pinned
route refusal) are the ones main already applies. They are unchanged; the population of files reaching nvCOMP is larger.

**If D1 is "GPU decoder only by explicit opt-in" (option 2):** the decision is made at the caller, not in
`admissionRefusal()`: `ingestCompressedTiffStrips` would be reached from `--ingest auto` only when nvCOMP was
requested, and `--ingest nvcomp` would keep working as now. That changes the existing 16-bit/1-row tutorial route too,
so the `docs/workload_corpus/gpu` witness (`nvcomp` for the tutorial) would become `compact`.
To keep this port's gain without option 2, the smallest fallback is setting both flags to `false` (main behaviour).
Option 1 (documented trusted-input precondition) needs no code. Option 3 (CPU inflate validation) is a separate change.

## Evidence

Source: branch `perf/138-nvcomp-widen-port`, binaries built from `977a9cef` (the later commits change only
`tests/test_deflate_layout.cpp` and docs; the final-head CTest below is re-run on the later head).
Hardware: 4GPUs, GPU3 (`GPU-b2cb2c39…`, A100 80 GB) via `CUDA_VISIBLE_DEVICES`, `taskset -c 72-79`, gpu3 correctness
lock per run, bench lock checked free (waited when held) before every run after the coordinator's steer.
Builds: Release, `-O3`, CUDA 12.8, nvCOMP 5.3.0.16, CMake 3.28.3, gcc 13.3, `CMAKE_CUDA_ARCHITECTURES=80`.
Binary sha256 (`logs/binary-sha256.txt`): port nvCOMP `49587b0c…`, main nvCOMP `1d2455a8…`, port CPU `db890c9e…`,
mutant `b592a233…`.
Inputs: tutorial movies 00021 and 00022 (sha256 `df298b1b…`, `cc55f13d…`; gain `8919cdc7…`) re-encoded by
`harness/gen_matrix.py` with identical sample values (max sample 68) into 16 variants. Options as
`run_matrix.sh`: `--use_own --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 --bfactor 150 --gainref … --seed 1 --j 8`.
Comparator: `docs/issue85_laneC/compare_output_trees.py` (complete tree, strict; the task text named `tools/…`, which does not exist on main).

### Tutorial movie tags (item 5)

`tifffile`, every directory of 00021 and 00022: BitsPerSample **16**, Compression **8** (Adobe Deflate), RowsPerStrip
**1**, Predictor tag absent (default 1), SampleFormat UINT, SamplesPerPixel 1, little-endian, ImageWidth 3710 ×
ImageLength 3838. So `corpus.md`'s "u8 Deflate TIFF" is wrong (the values fit in 8 bits, max 68, but are stored as
16-bit), which is consistent with the `nvcomp` witness on main. `corpus.md` also lists the geometry as 3838 × 3710; nx × ny is 3710 × 3838.
The corpus files were not edited here (per coordinator).

### Route matrix (item 7)

`logs/route-matrix-widened.out`, `logs/route-matrix-declines.out`. Each variant ran pinned `nvcomp`, `compact`,
`float` and `auto`, one process each, 2 movies, route read from `--ingest_witness`.

* 12 widened variants (u8, u16 × RowsPerStrip 1, 2, 8, 16, 512, 3838; 8/16/512 have a short final strip: 3838 mod 8 = 6, mod 16 = 14, mod 512 = 254):
  48/48 runs rc 0; pinned `nvcomp` and `auto` witnessed `nvcomp`, the other arms `compact` / `float` as pinned.
  **59/59 strict complete-tree comparisons PASS** (nvcomp vs compact, nvcomp vs float, auto vs nvcomp, compact vs float,
  and every variant's nvcomp tree vs the u16 RowsPerStrip-1 nvcomp tree). 28,477,960 pixels per arm.
* 4 decline variants (u16/u8 × predictor 2, big-endian): pinned `nvcomp` refuses (rc 1, "Refusing to continue on a
  different path under a pinned --ingest"), `auto` witnessed `compact`, auto vs compact and compact vs float PASS (8/8).
  The specific refusal reason line is in the per-movie log, which was deleted with the product trees; not retained.
* Negative controls: an exact copy of a product tree PASSES; the same copy with one float32 pixel changed by 1 ULP
  (1 of 28,477,960) FAILS on `Movies/20170629_00021_frameImage.mrc` (`logs/negctl_*.json`). A device-side mutant binary
  (`rowOffsetInFrame` dropping the row inside the strip) passes RowsPerStrip 1 and **fails** every multi-row variant
  against compact and float (`logs/route-matrix-mutant.out`).
* Real tutorial, main vs this branch, `--ingest auto`: 24 movies, route `nvcomp` on both, 24/24 MRC + 25 STAR strictly
  identical (341,735,520 pixels). 2-movie sets also PASS. See `logs/main-vs-port.out` (its first real24 line is a harness error:
  the 24-movie manifest pins the original STAR hash; the re-run used the manifest without it and is the PASS line
  appended below).
* Route change vs main (`auto`, witnessed): u8 any RowsPerStrip and u16 RowsPerStrip ≥ 2: `compact` → `nvcomp`, products identical (7/7 PASS: u8 RowsPerStrip 1, 8, whole frame; u16 RowsPerStrip 8, 16, 512, whole frame).

```
RUN real24 main: RC=0 routes=[24 nvcomp]
RUN real24 port: RC=0 routes=[24 nvcomp]
CMP real24 main-vs-port PASS Validated 24 movies, 24 MRC images, 25 STAR files, 341735520 pixels per arm
```

### CTest (item 6)

| suite | build | result |
|---|---|---|
| full CTest, CPU | `build-port-cpu` | 59/59 pass (`logs/ctest-port-cpu-all.log`) |
| CUDA+nvCOMP, non-hardware | `build-port-nvcomp` | 59/60; `ProfilingKit` failed a 30 s subprocess timeout while two generator processes shared the 8 CPUs (re-run below) |
| CUDA+nvCOMP, hardware label (GPU3) | `build-port-nvcomp` | 32/32 pass, including `CudaNvcompAcceptanceFailures`, `CudaNvcompReconstructionFailures`, `CudaPreprocessingFailurePaths`, `CudaAdler32` |

This first CTest batch ran before the steer to check the bench lock; its bench-lock state was not recorded.
`DeflateLayout` mutants against the production header (device-free build): full-length final strip 27 failing checks,
unaligned strip slots 18, padded rows 56, admission flag off 3, frame-stage size off by one 3; span-spread skipping one
strip 40; and a call-site walk over `ny` is an AddressSanitizer heap-buffer-overflow in `frameStageBytes`. The unmutated test passes under ASan/UBSan.
(The `DeflateLayout` "mutants" of #138 are in-test copies of `StripGeometry`, not separate CMake targets; unchanged here.)

### Device bytes and decode cost (item 8)

Nsight Systems 2024.6.2, `--trace=cuda`, one movie per run, GPU3, host-to-device bytes and `cuda_gpu_kern_sum`.
Bytes and GPU kernel time are not wall time. No wall-time claim is made from this lane.
`h2d/*.memsize.csv`, `h2d/*.kern.csv`.

| input (24 frames) | route | H2D MB (incl. 57 MB gain) | nvCOMP inflate, 8 calls |
|---|---|---|---|
| main, u16, 1 row/strip | nvcomp | 329.648 | 50.0 ms |
| port, u16, 1 row/strip | nvcomp | 329.648 (byte-identical) | 49.9 ms |
| main, u8, 8 rows/strip | compact | 751.351 | none |
| port, u8, 8 rows/strip | nvcomp | **255.266** | 49.1 ms |
| main, u16, 8 rows/strip | compact | 1434.822 | none |
| port, u16, 8 rows/strip | nvcomp | **318.724** | 50.9 ms |

**Caveat that needs a decision: very tall strips decode slowly.** One strip is one Deflate stream is one nvCOMP chunk,
so a tall strip leaves little decode parallelism. nvCOMP inflate per 8-frame chunk (same method), u16 unless noted:
RowsPerStrip 2: 5.9 ms (u8), 8: 6.4 ms, 16: 6.9 ms, **512 (8 strips/frame): 140.9 ms, whole frame (1 strip): 1044.8 ms** (u8 whole frame 967.4 ms).
Single unbalanced observations of process wall on the shared lane agree (whole-frame ≈ 9-10 s for 2 movies vs ≈ 2 s on the compact route);
those are not claims. #138's own matrix stopped at 512 rows. If the widened admission is accepted, a lower bound on
strips per frame belongs in `admissionRefusal()`; that threshold is not chosen here.

### Real deposited datasets that this widens (item 9)

None in the project's evidence. Containers recorded in `docs/workload_corpus` and `recipes.json`:
RELION tutorial (EMPIAR-10204 data) u16 Deflate 1 row/strip (already on nvCOMP); EMPIAR-10361, 10641 u8 **LZW** 3 rows/strip;
10441 u8 **LZW** 2 rows/strip; EMPIAR-10474 and 12963 EER; 10028, 10164, 10216 MRC. The u8 and multi-row files are LZW,
which this change does not touch (that is the #141/#152 nvTIFF question). So there is no corpus instance of u8 Deflate or
multi-row Deflate; the application value of this port for deposited data is unsupported by the retained evidence (vendor-specific
acquisition software that writes Deflate with `RowsPerStrip` > 1 may exist; not established here).

## Limitations

* 2-movie sets (24 for the real tutorial), one GPU, one host, one nvCOMP version.
* Malformed-input behaviour is exactly what main has; none of the #134 questions are exercised.
* Interior commits of the cherry-pick series do not build individually.
* Variants are re-encodes of the tutorial movies with identical values; no third-party u8/multi-row Deflate file was available.
