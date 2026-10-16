# W-MRC-Q: qualification of raw integer MRC staging (#194 / #195)

Source `1db86902` (main, includes #195 `faf5fbdf`). Parent for the CPU control: `4b849165`. Programme: #198, item M1.

**Result.** On valid movies, native staging for MRC modes 0, 1 and 6 produces products byte-identical to the float route on real data and on 28 synthetic cases, and routes as expected. Two inherited failure-semantics defects (not caused by #195) are escalated below: truncated raw MRC is accepted, and the compressed-MRC reader ignores the decoder's exit status. Nothing here changes a gate or a tolerance.

## Setup

| item | value |
|---|---|
| host | 4GPUs VM (`4-gpu-vm`), kernel 6.8.0-136, THP `madvise`, driver 570.86.10, CUDA 12.8.61, nvCOMP 5.3, g++ 13.3.0, cmake 3.28.3 |
| GPU | GPU3 = A100 80GB PCIe `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` (`CUDA_VISIBLE_DEVICES=3`, so `--gpu 0`) |
| CPUs | `taskset -c 88-95` on every run, CUDA and CPU |
| locks | per run: `/tmp/motioncorr-gpu3-correctness.lock`, plus an `nvidia-smi` compute-apps check by UUID. From the options runs (section 7) onward each run also waits for `/tmp/motioncorr-bench.lock` to be free (`flock -n`, poll 60 s); the earlier runs did not check that lock |
| builds | Release, `-DBUILD_TESTING=OFF`; flags in `evidence/logs/build.log` |
| binaries (sha256) | CUDA+nvCOMP `1db86902`: `45043787cf16…a75a`; CPU `1db86902`: `e846895b83f7…a6`; CPU `4b849165`: `1bbbd73826fa…c2` (full values in `evidence/binaries.sha256`) |
| comparator | `tools/profiling/lib/identity.py` (the one #195's own test uses). MRC: whole 1024-byte header incl. labels (writer clock masked), extended header, payload. Other files byte-identical after output-root normalisation. `.log` and `.pdf` are inventoried only. Inventories must match and at least one MRC must be compared. `tools/compare_output_trees.py` named in the brief does not exist in this tree |
| scratch | `/mnt/clathrin/alex-motioncorr-rc0/W-MRC-Q/` (4.7 GB used; bulk MRC removed after hashing) |

Input identity (all re-downloaded from `ftp.ebi.ac.uk/empiar/world_availability`; sha256 equals `docs/workload_corpus/corpus.md`):

| file | sha256 |
|---|---|
| EMPIAR-10164 `TS_01_000_0.0.mrc` (mode 0, 7420×7676×8) | `117c303163480aa6bd3a1c1298c5635486dd077babce770dfcaf4ca944245039` |
| EMPIAR-10164 `TS_01_020_30.0.mrc` (header analysis only) | `e6780acb0df21aae077fb9a5fdaf80a1553cd0fb4a339482aa59799b2642029d` |
| EMPIAR-10216 `…1739_Fractions.mrc` (mode 1, 4096²×59) | `f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56` |
| EMPIAR-10028 `031_movie.mrcs` (mode 2, 4096²×16) | `8ce479649ec00abf46b290aee2b43343d0ba0dc67f239f0e3fd0c6875b3c7213` |

Code in this directory: `real_data_identity.py` (items 1 and 7), `synth_mrc_matrix.py` (generator and runner, items 2–4 and 7), `mrc_header_stats.py` (item 5), `compare_tree_dirs.py` (item 6). Raw results are in `evidence/` (JSON per section, logs, per-movie logs and witnesses under `evidence/runlogs/`).

## 1. Real data, `--ingest auto` vs `--ingest float`

Options per `docs/workload_corpus/corpus.md`: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames N --j 8 --gpu 0 --ingest_witness`; config L adds `--patch_x 5 --patch_y 5`. One movie per family, one float/auto pair per config (n = 1; identity only, no timing claim).

| family | mode | config | witness float / auto | tree identity | files / MRC compared |
|---|---|---|---|---|---|
| 10164 | 0 (int8) | G | float / **compact** | identical | 9 / 1 |
| 10164 | 0 | L | float / **compact** | identical | 9 / 1 |
| 10216 | 1 (int16) | G | float / **compact** | identical | 9 / 1 |
| 10216 | 1 | L | float / **compact** | identical | 9 / 1 |
| 10028 | 2 (float32) | G | float / float | identical | 9 / 1 |
| 10028 | 2 | L | float / float | identical | 9 / 1 |

6/6 pass. Routes match expectation (compact for modes 0/1, float for mode 2).

## 2. Synthetic fixtures (CUDA, GPU3)

`synth_mrc_matrix.py` writes MRC movies from `test-data/generate_synthetic_fixture.py` content (known motion). Planted in every frame: modes 0/1/6 at their full range (−128/127, −32768/32767, 0/65535, plus 0, ±1, 32768/32767), plus the first and last sample in memory order. Arms: `float`, `auto`, and pinned `compact` where the route is compact.

| result | count |
|---|---|
| cases run | 36 (36 pass) |
| successful cases: tree identity auto = float (and compact = float) | 28/28 |
| witness as expected | 28/28 |
| float-route cases: pinned `--ingest compact` refuses and publishes nothing | 10/10 |
| expected-failure cases failing identically on every route, no products | 8/8 |
| modes 3 and 4: explicit refusal (`readMRC: only real-space images may be read into RELION.`) under float/auto/compact, no products | 2/2 |

The 28 successful cases: modes 0, 1, 6 (compact) and 2 (float), each at 128×128×8; with gain and geometry 134×98×9; 96×112×20 frames; frame selection (`--first_frame_sum 3 --last_frame_sum 10` of 12); big-endian header and payload (mode 0 at nx=120, see below); 1024-byte extended header (`nsymbt`). Modes 12 (float16) and 101 (4-bit) at 128² (and 12 with gain at 134×98, 101 with gain), all float route.

Expected failures (identical message on every route, no products):
- odd nx or ny (133, 97) for modes 0/1/2/6/101: `Patch size must be even` at `src/acc/cuda/cuda_alignpatch.cu:457`. Global alignment uses the whole frame, so odd dimensions are unsupported on every route. This is why "odd geometry" in the 28 uses even, non-square, non-power-of-two sizes.
- mode 101 with nx and ny both odd: `src/rwMRC.h:224`.
- big-endian mode 0 with nx = 128: see D3.

## 3. Compressed MRC (xz, zstd native; bz2 via shim)

`pbzip2` is not installed on 4GPUs (the reader calls `pbzip2`, `src/image.h:1893`). `xz` and `zstd` are native.

| check | result |
|---|---|
| modes 1, 0, 6, 2 × xz, zstd × `auto`/`float`: float route, products identical to the uncompressed movie (MRC strict; STAR/EPS after root and movie-name normalisation) | 16/16 |
| mode 1 `.bz2`, real PATH (no `pbzip2`): explicit failure, no products | 2/2 |
| mode 1 `.bz2` with a `pbzip2` shim that runs `bzip2 -cd`: float route, products identical | 2/2 (shim, not real pbzip2) |
| pinned `--ingest compact` on compressed (m1, m2 × xz, zstd) and on raw float32 MRC: refuses, no products | 5/5 |
| truncated stream (60 %), header-only stream, mid-stream corruption, zstd tail/trailer damage: explicit failure, no completion STAR | 16/16 (xz and zstd × auto/float) |
| **xz stream missing its last byte; xz with a corrupt index CRC (all payload delivered, decoder exit 1)** | **0/4: motioncorr exits 0, publishes products and STAR** |
| **shim decoder that emits the complete correct stream and exits 3 (xz and zstd)** | **0/2: motioncorr exits 0, publishes products and STAR** |

A control shim that exits 0 gives a normal run (2/2), so the exit-3 arms differ only in the decoder's exit status. A first version of the shims had a quoting bug and failed for the wrong reason (header read); that was caught because the control did not discriminate, and the results above are from the corrected shims. See D2.

## 4. Error routes (raw MRC)

26 variants: modes 1/0/6/2 × {truncated mid-frame, truncated by one byte, truncated inside the header, header only, header claims 12 or 24 frames but holds 8} plus `--expected_frames` mismatch for modes 1 and 2.

| result | count |
|---|---|
| same exit class and publication on every route (float/auto/compact) | 26/26 |
| fails explicitly with nothing published | 6/26 (4 × header truncated before 1024 bytes; 2 × `--expected_frames` mismatch) |
| **exit 0, products and completion STAR published** | **20/26** (every mid-frame, one-byte, header-only and header-claims-more variant, in all four modes including float32) |
| of those 20, float and auto trees byte-identical | 6 of 20; 14 differ |

The 14 differences are in the unread bytes only: the float route leaves them uninitialised (unaligned-sum mean printed as `nan` or `2e-44`), the compact route reads them as zero (mean `0`, or finite). The same 20/26 acceptance occurs with the CPU-only `4b849165` parent and the CPU `1db86902` build (`evidence/synth/cpu-errors-*.json`), so acceptance predates #195. #195 changes which garbage is published, not whether. See D1.

## 5. Mode-0 signedness (report only)

`mrc_header_stats.py`:

| movie | IMOD stamp | `imodFlags` | bit 0 (signed bytes) | raw byte min / max | bytes ≥ 128 | header amin / amax |
|---|---|---|---|---|---|---|
| 10164 `TS_01_000_0.0` | yes | 8 | clear | 0 / 90 | **0** of 455 647 360 | 0 / 90 |
| 10164 `TS_01_020_30.0` | yes | 8 | clear | 0 / 86 | **0** of 455 647 360 | 0 / 86 |

Reading mode 0 as signed (RELION behaviour kept by #195) changes no value for these two movies, so there is **no escalation for 10164**. Information only: with bit 0 clear, IMOD would treat the bytes as unsigned; a dataset with bytes ≥ 128 would be wrapped negative by the signed read. The mode-1 movie 10216 has stored values −26…293 (45 461 773 samples with bit 15 set), so signed int16 is correct there. Mode 1 = signed and mode 6 = unsigned are not in question.

## 6. CPU-only build against the pre-#195 parent

CPU `1db86902` vs CPU `4b849165`, same inputs, `taskset -c 88-95`:

| set | result |
|---|---|
| synthetic matrix (28 successful cases + 8 expected failures) | 28/28 trees identical; the 8 expected failures fail with rc 1 on both builds |
| 10164 config G (mode 0) | identical (9 files, 1 MRC) |
| 10216 config G (mode 1) | identical (9 files, 1 MRC) |
| truncated/error variants (section 4) | same 20/26 acceptance on both builds |

## 7. Option combinations (coordinator steer, R-DESIGN review)

Signed MRC: 10216 mode 1 (real, configs G and L) and synthetic mode 0 and mode 1 (192² × 12 frames; 768² for the power-spectrum case, because the PS is resized to `--ps_size 512` and a 192 px frame fails identically on every route with `Invalid size given to cropInFourierSpace`; the first synthetic attempt is kept as `evidence/synth/cuda-options.v1.json`).

Source reading. The resident CUDA session is created only when `use_gpu && !early_binning` (`src/motioncorr_runner.cpp:2264`), and compact staging requires that session (`movie_session` in the condition at `:2369`). `--early_binning` is **on by default** whenever `--bin_factor` ≠ 1 (`:214-219`), so a plain `--bin_factor 2` is early binning; late binning needs `--no_early_binning --bin_factor 2`. Option (a) was therefore run as `--no_early_binning --bin_factor 2`, and (b) both as plain `--bin_factor 2` and as explicit `--early_binning --bin_factor 2`.

| option set | real 10216 (G, L) | synthetic modes 0 and 1 | route (witness) | resident session |
|---|---|---|---|---|
| (a) late: `--no_early_binning --bin_factor 2` | identical (2/2) | identical (2/2) | float / compact | yes (in-VRAM FFT line in log) |
| (b) early: `--bin_factor 2` | identical (2/2) | identical (2/2) | float / **float** | **no** |
| (b) early: `--early_binning --bin_factor 2` | identical (G) | identical (2/2) | float / **float** | **no** |
| (c) `--save_noDW --even_odd_split` | identical (2/2; 4 MRC each: main, noDW, EVN, ODD) | identical (2/2) | float / compact | yes |
| (d) `--grouping_for_ps 4` | identical (2/2; 2 MRC each: main, PS) | identical (2/2) | float / compact | yes |

Early binning bypasses both the resident session and compact staging, so under `--ingest auto` the movie takes the float route and products are identical across the two `auto`/`float` runs by construction; pinned `--ingest compact` with early binning refuses with no products (3/3 real, 4/4 synthetic). All 10 synthetic and 9 real option runs pass.

Peak host RSS, 10216 (`/usr/bin/time -f %M`, one sample per cell, MiB; single runs, not a stability claim):

| options | float | auto (compact) |
|---|---:|---:|
| none (config G) | 3979 | 2131 |
| (a) late bin 2, G / L | 4061 / 4159 | 2110 / 2107 |
| (b) early bin 2, G / L | 4348 / 4376 | 4360 / 4356 |
| (b) `--early_binning --bin_factor 2`, G | 4384 | 4355 |
| (c) noDW + even/odd, G / L | 4171 / 4261 | 2142 / 2138 |
| (d) `--grouping_for_ps 4`, G / L | 7821 / 7862 | 4045 / 4086 |

(d) adds about 3.8 GiB on the float arm and 1.9 GiB on the compact arm. A full host Fourier movie for 59 frames of 4096×2049 complex floats is 59 × 67.1 MB = 3 777 MiB, which matches the float-arm delta; on the compact arm the host staging is released first, so the peak is that movie plus ~0.27 GiB (inference from the sizes, not separately instrumented). This is the `downloadFourierFrames` copy at `src/motioncorr_runner.cpp:3205-3212`; documented as pre-existing, not changed. Early binning removes the compact arm's RSS saving (4360 vs 2131 MiB) because it falls back to the float route.

## Defects and escalations

All three are inherited from before #195 (the CPU-only parent reproduces D1) and none is on the valid-input path that #195 changes.

- **D1, truncated or short raw MRC is accepted and published (escalation: failure/publication semantics).** `Image::read` returns a negative code when `readData` hits a short `fread` (`src/image.h:1286`, `-2`) or a failed seek (`:1260`, `:1299`, `-1`), but the frame-read loop discards that return (`src/motioncorr_runner.cpp:2465-2477`, all five read calls), unlike the compressed reader, which checks it (`src/image.h:1940`). A raw MRC cut by one byte, a header-only file, or a header that claims more frames than the file holds runs to completion and publishes products and the completion STAR, with the unread samples uninitialised (float route) or zero (compact route). This affects float32 MRC as well. TIFF is not affected (its reader throws). `docs/gate_contract.md` complete-product semantics point to failing the movie. Not fixed here; a minimal fix is to check the return of those reads and `REPORT_ERROR`, plus a fixture like `synth_mrc_matrix.py --section errors`.
- **D2, compressed-MRC reader ignores the decoder exit status (escalation: failure semantics).** `src/image.h:1953` `pclose(pipe)` discards the status, with a comment that header-only reads stop the decoder early. A complete, correct stream whose decoder exits nonzero (xz stream missing its last byte, corrupt xz index CRC, or the exit-3 shim) is accepted and published. zstd cases fail only because zstd withholds the last block until its checksum verifies. Checking status after the last needed frame is awkward when frame selection stops the decoder early (SIGPIPE), so this is a design decision, not a one-line fix.
- **D3, minor: big-endian mode-0 header with nx = 128 is not swap-detected.** `src/rwMRC.h:149`: `abs(INT_MIN)` is negative, so the `> SWAPTRIG` test is false and the header is read unswapped (`frame count mismatch: expected 8 frames, but decoded 134217728`). Fails explicitly and identically on every route. Other big-endian cases pass. No action proposed.

No defect found in the #195 compact route itself.

## UNRUN

- Native `pbzip2` (not installed): the `.bz2` success path was run only with a shim that runs `bzip2 -cd`.
- Second 10164 movie, and 10164 / 10028 under the section-7 options (only 10216 and synthetic were requested).
- Any performance or timing claim: none made; RSS is single-sample.
- Full CTest and nvCOMP/no-nvCOMP inventory: owned by Q1 (W-QUAL).
- Mode 101 and 12 on the compact route: not admitted by design; run on the float route only.
- cpu64, SCARF: not allocated.

## Recommended register status

M1: **GO stands** for valid raw integer MRC (modes 0/1/6) as merged. Open before RC0: a decision on D1 and D2 (both are inherited; D1 is cheap to fix). Binning, noDW/even-odd and PS options are consistent with that status; the RC0 documentation should state that `--bin_factor` ≠ 1 (early binning is the default) disables compact staging and the resident session, and that `--grouping_for_ps` costs about one full host Fourier movie of RSS.
