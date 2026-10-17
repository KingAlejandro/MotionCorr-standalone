# Format coverage of the workload corpus (#186 follow-up)

The ten #186 families cover four decode paths. This note lists every on-disk encoding MotionCorr
reads, measures which ones EMPIAR actually holds, adds eight real families for the encodings the
corpus lacked, and records which encodings exist only as synthetic fixtures because none was
found among the EMPIAR files read. It makes decode-coverage claims only. Timing baselines for the new families have
not been run (Limitations).

## Result in brief

- **Census.** 2,940 EMPIAR entries were catalogued through the EMPIAR API. Of 2,273 imagesets
  probed, 2,057 yielded at least one header read by HTTP range request (2,651 probe records: 2,420
  headers read, 221 imagesets where the crawler found no movie file, 10 fetch failures). 1,461
  distinct movie imagesets ("micrographs - multiframe") were classified by their actual encoding
  (1,464 entries: three imagesets hold two encodings), which often disagrees with the deposited
  metadata (e.g. EMPIAR-10216 says unsigned 16-bit; its header is mode 1).
- **Common encodings the corpus lacked:** signed 16-bit Deflate TIFF (EPU Falcon; 70 imagesets with
  code 32946, 16 with code 8), 16-bit LZW TIFF (143), bzip2-compressed MRC (48), uint16 MRC (23),
  float32 TIFF (12). Rarer: SerialEM 4-bit MRC (1), zstd MRC (1), 8192^2 frames (DE Apollo).
- **Added:** eight real families (two movies each, 10.8 GB): `e10500f3`, `e10342`, `e10740`,
  `e10374`, `e11217`, `e10202`, `e10666`, `e11404` (`families-formats.json`).
- **Not found in the files read:** EER 65000, 65002, 2K EER or the legacy EER container (EER headers
  were read from 361 files in 211 imagesets, 196 of them movie imagesets: all are 65001 at 4096^2); IMOD packed 4-bit TIFF; float16, signed 8-bit or PackBits
  movies; xz-compressed MRC. These are covered by the synthetic fixtures (`InputFormats`, test-data
  README section 1c), which also cover every rejected encoding.
- **Decode smoke runs** (SCARF CPU and A100 GPU, main's source): all eight new families decode and
  correct with exit 0 and the expected frame counts; each GPU route matches the reader table.
- **Findings from real data:**
  - a linked `.mrc.zst` movie fails to open (`zstd -cdk` ignores symbolic links); copied, it works;
  - EMPIAR-10342's defect list is in SerialEM format and is refused;
  - EMPIAR-10740's gain is transposed against its movies and needs `--gain_rot 3`, identified by a pixel-correlation test;
  - nine imagesets deposit compressed TIFF (`.tif.bz2`), which MotionCorr cannot read;
  - EPU EER and `.gain` files carry TIFF orientation tags 2, 4, 5, 6 or 7, which the readers ignore.
- **Label corrections, made in #201:** the RELION tutorial movies are unsigned 16-bit Adobe-Deflate
  TIFF (compression 8, RowsPerStrip 1, no predictor, little-endian), width 3710 x height 3838, and
  EMPIAR-10164 is MRC mode 0, read as signed int8 (its largest byte is 90, so no value changes).
  The release-docs PR #201 corrects `corpus.md` and `families.json`; this PR leaves both files
  unchanged so the two do not conflict. Main's nvCOMP route admits only 16-bit samples, and the
  tutorial took that route in the #186 GPU runs.

## What the readers accept

| container | accepted | refused | CUDA ingest route (`--ingest auto`) |
|---|---|---|---|
| MRC | modes 0 (read as signed int8), 1, 2, 6, 12, 101 (4-bit; not odd x odd); either byte order; extended headers skipped | modes 3, 4 and unknown modes | modes 0, 1, 6: compact staging; 2, 12, 101: float |
| compressed MRC | `.mrc(s).bz2/.xz/.zst` through `pbzip2`, `xz` or `zstd` pipes | | float |
| TIFF / BigTIFF | u8, s8, u16, s16, f32; any LibTIFF codec and predictor; either byte order; strips; IMOD packed 4-bit at eight K2/K3 geometries | u32, f64, f16, tiled, more than one sample per pixel, mixed frame sizes | **nvCOMP** only when every condition holds: unsigned 16-bit samples, Deflate (code 8 or 32946), predictor 1, MSB-to-LSB fill order, one sample per pixel, contiguous planes, one full row per strip, native byte order, the same geometry in every frame, a `USE_NVCOMP` build and a resident CUDA session (`cuda_movie_session.cu` tag scan). **compact**: any other u8/u16 TIFF, including predictor-2 u16 Deflate, multi-row strips and byte-swapped files. **float**: s8, s16, f32, packed 4-bit |
| EER | 65000 and 65001 at 4096^2 (upsampling -1/1/2/3) or 2048^2 (1/2); 65002 (7-bit runs, 1+1 subpixel bits) at upsampling **1 or 2 only** | other sizes and codes, other 65002 depths, 65002 at upsampling -1 or 3 (`renderEER.cpp`) | compact (uint16 render) when grouping x (4 at upsampling -1, else 1) <= 65535; otherwise float |

Every compact or nvCOMP route needs a CUDA build with a resident session and is not taken under
`--ingest float`; `--ingest compact` or `--ingest nvcomp` refuses a movie its route does not admit.
A CPU build reads every movie through the float reader.

**Eligibility, admission and trust.** The table gives *encoding eligibility*. On current main two
further conditions apply to the nvCOMP route:

- **Checked admission (#217).** Before any decode, a strip offset that LibTIFF cannot supply, or an
  overflow in the file span, row pitch, staging, layout or reservation arithmetic, is a named
  decline (`nvCOMP ingestion declined (...)` in the movie log) with no CUDA error. Under
  `--ingest auto` the movie then falls back to the host route (compact or float); a pinned
  `--ingest nvcomp` refuses it. A decline says nothing about whether the host reader will accept
  a malformed file.
- **Trusted, immutable input (decision D1, adopted for RC0).** `--ingest auto` on a `USE_NVCOMP`
  build assumes the movie is trusted and does not change while it is read. Matching tags and a
  successful witness do not validate the compressed Deflate body before nvCOMP decodes it (NVIDIA
  documents undefined behaviour for corrupt input), and a file replaced between the tag scan and
  the strip reads is not detected; that check is deferred to #215. See the decision brief
  [`docs/rc0/decoder_trust_and_dependencies.md`](../rc0/decoder_trust_and_dependencies.md).

The routes recorded in this note were measured on main `d7171b81`, before #217 (the synthetic
matrix and the GPU smoke runs below). The RC0 review's rerun of the synthetic ingest matrix on main
`483e881d`, which includes #217, reported no route failures (#202 review, round 2).

The routes were measured, not inferred: the synthetic suite's `--ingest-matrix` run on a SCARF A100
recorded each fixture's route with `--ingest_witness` and found `--ingest auto` products
byte-identical to `--ingest float` for every fixture (254 checks pass; test-data README 1c).

## EMPIAR census

Method: `tools/empiar_catalogue.py` read the API record of entries 10001-13399 (2,940 entries,
3,098 movie imagesets by metadata). `tools/probe_formats.py` listed each selected imageset
directory and parsed only headers: the MRC header, the TIFF/BigTIFF header and first (and second)
directory, or the compression suffix. All EER, MRC, non-8-bit TIFF and other imagesets were
selected; 8-bit TIFF was sampled (every sixth entry), so its counts below are about a sixth of the
total. One or two files per imageset were read; 221 imagesets had no movie file the crawler could
find within three directory levels and 10 fetches failed, so absence claims cover only the files
read.
`tools/summarize_census.py` counts imagesets in the "micrographs - multiframe" category and
excludes gain, reference and single-frame files. Raw output: `evidence/formats/census/`.

| encoding | imagesets | examples | corpus family | synthetic case |
|---|---:|---|---|---|
| BigTIFF u8 LZW | 267 (sampled) | 12081, 10408, 11967 | e10361, e10641, e10441 | `tiff_u8_bigtiff_lzw` |
| TIFF u8 LZW | 224 (sampled) | 11890, 11980, 10168 | (same decode) | `tiff_u8_lzw`, `tiff_u8_lzw_pred2` |
| EER 65001 4096^2 | 196 | 10973, 10947, 10424 | e10474f3, e10474f4, e12963 | `eer_4k_65001_*`, `eer_2k_65001_*` |
| MRC mode 2 (incl. extended headers) | 105 | 12494, 10384 | e10028 | `mrc_mode2_f32`, `_bigendian` |
| MRC mode 1 (incl. FEI1/FEI2/SERI headers) | 133 | 10050, 10844, 11554 | e10216 | `mrc_mode1_s16`, `_bigendian`, `_seri` |
| BigTIFF / TIFF u16 LZW | 143 | 10334, 10342, 10200 | **e10342**, **e11404** (8192^2) | `tiff_u16_lzw`, `_pred2` |
| TIFF s16 Deflate, code 32946 | 70 | 10500, 10518, 10608 | **e10500f3** | `tiff_s16_deflate_old_epu`, `tiff_s16_wide_deflate_old_epu` |
| TIFF s16 Deflate, code 8 | 16 | 10243, 10264, 10308 | | (same decode path) |
| MRC mode 0 | 72 | 10025, 10164 | e10164 | `mrc_mode0_s8` |
| MRC compressed `.bz2` | 48 | 10130, 11217 | **e11217** | `mrc_compressed_bz2` |
| MRC mode 6 (incl. extended headers) | 23 | 10096, 10740, 10292 | **e10740** | `mrc_mode6_u16`, `_fei2` |
| TIFF s16 LZW (incl. BigTIFF) | 19 | 10567, 10480 | | `tiff_s16_lzw` |
| TIFF u16 uncompressed (incl. big-endian) | 20 | 11339, 10151 | | `tiff_u16_none`, `_bigendian` |
| TIFF f32 LZW / Deflate | 12 | 10666, 10340, 12067 | **e10666** | `tiff_f32_lzw_pred3`, `tiff_f32_deflate` |
| TIFF u16 Deflate | 4 | 10204, 10285 | tutorial | `tiff_u16_deflate_rps1`, `_rps16`, `_pred2`, `_old` |
| compressed TIFF (`.tif.bz2`) | 9 | 12876, 10933 | not readable | none |
| TIFF with 3 or 4 samples per pixel | 2 | 12316, 13057 | refused | `tiff_rgb` |
| MRC mode 5 | 1 | 10287 | refused | `mrc_mode5` |
| MRC mode 101 | 1 | 10374 | **e10374** | `mrc_mode101_4bit` |
| MRC compressed `.zst` | 1 | 10202 | **e10202** | `mrc_compressed_zst` |
| TIFF u8 uncompressed (incl. big-endian) | 98 | 10463, 12239 | | `tiff_u8_none` |
| EER 65000 / 65002 / 2K / legacy | 0 (of 211 imagesets with an EER header read) | | | `eer_2k_65000`, `eer_*_65002`, `eer_legacy_container` |
| IMOD packed 4-bit TIFF | 0 | (10251, 12550 are labelled 4-bit; both are 8-bit) | | `tiff_4bit_packed_k2` (heavy) |
| float16, s8, PackBits movies; `.mrc.xz` | 0 | (mode 12 files found are particle stacks) | | `mrc_mode12_f16`, `tiff_s8`, `*_packbits`, `mrc_compressed_xz` |

Most uncompressed 8-bit and big-endian TIFF stacks in the category are volume-EM or SEM series,
not cryo-EM movies. EER orientation tags: absent in 20 imagesets, 2 in 127, 5 in 33, 4 in 14, 6 and
7 in one each; `.gain` files carry the same values.

## New families

`families-formats.json` uses the `families.json` schema, so `tools/setup_corpus.py` and
`tools/run_matrix.py` run them unchanged; two optional fields were added to those tools:
`copy_movies` (copy instead of link, needed for zstd) and `extra_options` (here the gain
orientation of e10740). Pixel sizes are the EMPIAR values; dose and voltage are placeholders except
e10740's dose (from its description file).

| id | accession, producer | container | geometry (nx x ny x frames) | angpix | gain / side files |
|---|---|---|---|---:|---|
| `e10500f3` | EMPIAR-10500, EPU Falcon 3 | s16 TIFF, Deflate 32946, one strip per frame | 4096 x 4096 x 60 | 0.827 | none (EPU XML kept) |
| `e10342` | EMPIAR-10342, K2 counting | u16 BigTIFF, LZW, 2 rows per strip | 3838 x 3710 x 50 | 1.1 | f32 MRC gain; SerialEM defect list |
| `e10740` | EMPIAR-10740, Leginon K2 | MRC mode 6 | 3838 x 3710 x 43 | 1.03 | f32 MRC gain, 3710 x 3838: `--gain_rot 3` |
| `e10374` | EMPIAR-10374, SerialEM K2 super-res. | MRC mode 101 (4-bit) | 7676 x 7420 x 50 | 0.42 | none |
| `e11217` | EMPIAR-11217, K3 super-res. | int8 MRC in `.mrcs.bz2` | 11520 x 8184 x 32 | 0.25955 | none |
| `e10202` | EMPIAR-10202, Leginon K2 super-res. | int8 MRC in `.frames.mrc.zst` | 7420 x 7676 x 70 | 0.394 | none |
| `e10666` | EMPIAR-10666 | f32 TIFF, LZW, one strip per frame | 3838 x 3710 x 40 | 1.043 | f32 MRC gain |
| `e11404` | EMPIAR-11404, DE Apollo | u16 BigTIFF, LZW, 3 rows per strip | 8192 x 8192 x 45 | 0.387 | f32 MRC gain, 8192^2 |

Identity: fetched with `tools/fetch_corpus.py` from `https://ftp.ebi.ac.uk/empiar/world_availability/`
on SCARF (`evidence/formats/formats-download-manifest.json`, results in
`evidence/formats/result-formats-download-manifest.json`, 23 of 23 pass). These files had no earlier
hash; the size matched the HTTP Content-Length and the SHA-256 below is the one observed.

| file (relative to data root) | bytes | SHA-256 |
|---|---:|---|
| `EMPIAR-10500/data/XFEG-Falcon3/GridSquare_14725129/Data/FoilHole_14730491_Data_14726927_14726929_20200316_135927_Fractions.tif` | 1,097,982,987 | `17f6b2d39497feb6f93046c9370a595678121b66fdc10aa0a71230b52655d629` |
| `EMPIAR-10500/data/XFEG-Falcon3/GridSquare_14725129/Data/FoilHole_14730491_Data_14731585_14731587_20200316_140015_Fractions.tif` | 1,098,109,805 | `f3fdf93b7ac63f3d65b4ad30e472c4b1ffd9a452be41cd2d51569db4c007d50d` |
| `EMPIAR-10500/data/XFEG-Falcon3/GridSquare_14725129/Data/FoilHole_14730491_Data_14726927_14726929_20200316_135927_Fractions.xml` | 38,777 | `8c4a946b6be9853d08f686964e5a8da4a940fbfbde5e5732a2a586578da3b746` |
| `EMPIAR-10342/data/Movies/190830/bna_h1_s1_i0001_movie_Aug30_21.13.54.tif` | 235,714,806 | `baf58aebb09f236678fe51215b726e5e7885918d1dd21ea9c8f25e9d3bd428b1` |
| `EMPIAR-10342/data/Movies/190830/bna_h1_s1_i0001_movie_Aug30_22.52.32.tif` | 228,954,690 | `961e028b459323e5b8e6eb3eb4a0ea4f204b10902e318d7af003f6ca81c75640` |
| `EMPIAR-10342/data/Movies/GainRef/190830_gainref.mrc` | 56,956,944 | `fb59c58c436ce5f7474f59f6c40c96b09e04591aa307451c95c78b3d5eded7e8` |
| `EMPIAR-10342/data/Movies/Defect/190830_defects.txt` | 1,934 | `e03fe718546e89c559c9b4ac83ca516b24e242661ba2bacb53e9c5fdd63776bd` |
| `EMPIAR-10740/data/EMPIAR_sjojoa/frames/19may24k/rawdata/19may24k_1_00001gr_00001sq_00002hl_00002ed.frames.mrc` | 1,224,553,304 | `3499f58ba49e7977de805ff5ce4f836d37a7719307c1ddff7b172a3b474b9697` |
| `EMPIAR-10740/data/EMPIAR_sjojoa/frames/19may24k/rawdata/19may24k_1_00001gr_00001sq_00002hl_00003ed.frames.mrc` | 1,224,553,304 | `8c9599b3933811ca74d06fc87582d80be320573bcdaa9fecf67b855be5ecf311` |
| `EMPIAR-10740/data/EMPIAR_sjojoa/gains/19may24k_ref.mrc` | 56,956,944 | `66f8d3fdff1f2a230c466491f241d5fee77718f76633a793b7cb4d0d6a00ba28` |
| `EMPIAR-10740/data/EMPIAR_sjojoa/Description_FLYC1datasets_v2.txt` | 1,040 | `33e5c48aa89ba52a88fc2ec1413f68aecc11bb77bff50f2aa01ce4d0b36178dc` |
| `EMPIAR-10374/data/Movies/2017-05-04/May04_14.24.37.mrc` | 1,423,899,024 | `225e837f40c723b3b5b0fa9dfa4782023c26c71750b0e4ae7df532bd3ef9099d` |
| `EMPIAR-10374/data/Movies/2017-05-04/May04_14.25.55.mrc` | 1,423,899,024 | `9c5e08871817acdd06b5ece87fe9ff21547ec6676beb835f9167fd6fb33f669f` |
| `EMPIAR-11217/data/Compressed-frames/stack_0015.mrcs.bz2` | 270,212,111 | `b4b9d9fdd175a7a88ec1de01c715409ba6a1e2f2521f55c599e2f3f915dcb10d` |
| `EMPIAR-11217/data/Compressed-frames/stack_0016.mrcs.bz2` | 270,487,284 | `05cfd395611982860393cd144524cea0d899b2b2841bf961eef2c816645d2db3` |
| `EMPIAR-10202/data/01_Raw_Frames_Compressed/17aug31d_00001sq_v01_00002hl_00002ed3.frames.mrc.zst` | 343,655,513 | `8c0113e8e66323df10ba78c7924aa4fd54545f8e6a7fab3020046430fb23486b` |
| `EMPIAR-10202/data/01_Raw_Frames_Compressed/17aug31d_00001sq_v01_00002hl_00003ed3.frames.mrc.zst` | 339,895,481 | `98f05dfba2ae4a8e5ce377f95867c65e4e3364f7dbe2a8e77304363218c989d1` |
| `EMPIAR-10666/data/eTG-movies-EMPIAR/FoilHole_16376725_Data_16377678_16377679_20171016_1214-38093.tif` | 229,078,133 | `02a282ea850e1956e0348647a391e05790f36087a5344e6d1b2c9313f4c8bec1` |
| `EMPIAR-10666/data/eTG-movies-EMPIAR/FoilHole_16376725_Data_16377702_16377703_20171016_1213-38091.tif` | 227,393,349 | `44c492ea9c51c728b9ae9568747f18576a8d107e2472d6662fb64b81e64c6509` |
| `EMPIAR-10666/data/eTG-movies-EMPIAR/gain-reference.mrc` | 56,956,944 | `02837ee1aedba06a9f36422e138d4b22203fa9bf118b525ea093c5f7a65d49bb` |
| `EMPIAR-11404/data/20221014_76242_12_8_integrated_movie.tif` | 375,460,454 | `b0933727670930509c6fc179d0e3da4cdbd06b0341652d0361cac5ed6fbab831` |
| `EMPIAR-11404/data/20221014_76243_13_1_integrated_movie.tif` | 379,875,532 | `53ecbfacd86a3509e3a1260391a4e71373e7ad34dfdde71c02f5450f317f4ad8` |
| `EMPIAR-11404/data/gain.mrc` | 268,436,480 | `bc5546d11943aa4c39fc98c9124dd114161a2269b1852530d0d49eb11f7e4d2d` |

The #186 families were fetched to the same SCARF data root in the same pass and all 28 files
matched their recorded sizes; the 19 movie and gain files with a SHA-256 in `corpus.md` matched it
(`evidence/formats/result-selected-*.json`, `result-gap-*.json`; tutorial `sha256-check.txt`).
SCARF data root: `/work4/scd/scarf1415/mc-corpus-formats/data`.

## Decode smoke runs

SCARF node `cn038`, Slurm allocation of 16 cores, 96 GiB; binary built from
`test/input-format-fixtures` at `54b4b883` (main `d7171b81` plus test code only: `src/` is
unchanged), Release, CPU. One process per family, both movies, global alignment,
`--j 16 --dose_weighting --bfactor 150 --seed 1 --expected_frames <n>`, the family's gain.
`tools/format_smoke.py`; results in `evidence/formats/smoke-cpu-3633155.json`. Wall times are
single runs on a shared cluster and are not timing baselines.

| run | exit | products | frames per movie | wall s | note |
|---|---:|---:|---|---:|---|
| `e10500f3` | 0 | 2 | 4096x4096x60 | 17.8 |  |
| `e10342` | 0 | 2 | 3838x3710x50 | 15.0 |  |
| `e10740` | 0 | 2 | 3838x3710x43 | 13.9 | `--gain_rot 3 --gain_flip 0` |
| `e10374` | 0 | 2 | 7676x7420x50 | 54.5 |  |
| `e11217` | 0 | 2 | 11520x8184x32 | 41.9 | linked (pbzip2 accepts links) |
| `e11217_copied` | 0 | 2 | 11520x8184x32 | 42.4 | copied |
| `e10202` | 1 | 0 | - | 0.1 | movies linked, as setup_corpus.py does: zstd refuses the links |
| `e10202_copied` | 0 | 2 | 7420x7676x70 | 85.7 | movies copied |
| `e10666` | 0 | 2 | 3838x3710x40 | 11.1 |  |
| `e11404` | 0 | 2 | 8192x8192x45 | 28.2 |  |
| `e10740_gain_unrotated` | 1 | 0 | 3838x3710x43 | 0.1 | gain not rotated: refused |
| `e10342_serialem_defect` | 1 | 0 | - | 0.1 | `--defect_file 190830_defects.txt` (SerialEM format): refused |

GPU runs of the same families: SCARF `gn0002`, NVIDIA A100-SXM4-40GB (driver 580.178.04), CUDA 12.8
with nvCOMP, Slurm allocation of 16 cores; binary built from `03fc40f7` of the fixtures branch (main
`d7171b81` source, test code only), `format_smoke.py --gpu` (`--gpu 0`, `--ingest auto`,
`--ingest_witness`); results in `evidence/formats/smoke-gpu-3633156.json`. Single runs; not timing
baselines.

| run | exit | products | frames per movie | `--ingest auto` route (witness) | wall s |
|---|---:|---:|---|---|---:|
| `e10500f3` | 0 | 2 | 4096x4096x60 | float | 16.3 |
| `e10342` | 0 | 2 | 3838x3710x50 | compact | 5.0 |
| `e10740` | 0 | 2 | 3838x3710x43 | compact | 16.3 |
| `e10374` | 0 | 2 | 7676x7420x50 | float | 22.1 |
| `e11217` | 0 | 2 | 11520x8184x32 | float | 15.5 |
| `e11217_copied` | 0 | 2 | 11520x8184x32 | float | 14.8 |
| `e10202` | 1 | 0 | - | - | 0.3 |
| `e10202_copied` | 0 | 2 | 7420x7676x70 | float | 20.3 |
| `e10666` | 0 | 2 | 3838x3710x40 | float | 4.2 |
| `e11404` | 0 | 2 | 8192x8192x45 | compact | 10.2 |
| `e10740_gain_unrotated` | 1 | 0 | 3838x3710x43 | - | 0.2 |
| `e10342_serialem_defect` | 1 | 0 | - | - | 0.1 |

Every route is the one the reader table predicts: signed 16-bit TIFF, 4-bit MRC, compressed MRC and
float32 TIFF take float; 16-bit LZW TIFF (both geometries) and uint16 MRC take compact. The GPU gain
search chose the same e10740 orientation (`--gain_rot 3 --gain_flip 0`), and the linked `.zst`
movies fail exactly as on the CPU.

**e10740 gain orientation.** The gain (3710 x 3838) does not match the movies (3838 x 3710)
without rotation, and MotionCorr refuses the unrotated gain. Six `--gain_rot/--gain_flip`
combinations give the right shape (four distinct transforms). For each, MotionCorr's own
transformed gain (`out/gain.mrc`) was correlated with the raw, unaligned frame sum after high-pass
filtering: a raw sum carries the detector's per-pixel sensitivity, and the gain is its inverse, so
only the right orientation correlates (`tools/gain_orientation.py`,
`evidence/formats/gain-orientation-e10740.txt`):

| options | corr(high-pass raw sum, high-pass 1/gain) | Fano factor of corrected high-pass |
|---|---:|---:|
| `--gain_rot 3 --gain_flip 0` | **+0.2795** | **1.145** |
| `--gain_rot 1 --gain_flip 2` (= rot 3, flip 1) | +0.0075 | 1.383 |
| `--gain_rot 1 --gain_flip 0` | +0.0001 | 1.393 |
| `--gain_rot 1 --gain_flip 1` (= rot 3, flip 2) | -0.0005 | 1.400 |

A product-based stripe metric pointed the same way but by only 9%, which is why this test was used.

## Findings

| finding | evidence | status |
|---|---|---|
| A linked `.mrc.zst` movie fails with "error in reading header": the reader runs `zstd -cdk FILE`, and zstd ignores a symbolic-link input without `-f`. `setup_corpus.py` and RELION projects link movies. `.bz2` (pbzip2) and `.xz` accept links. | e10202 linked vs copied (smoke table); synthetic `mrc_compressed_zst_symlink` | inherited from upstream; `copy_movies` works around it here |
| On main at the time of these runs (`d7171b81`), truncated raw MRC payloads were accepted with exit 0; the missing frames held stale pooled-buffer contents. | synthetic `mrc_truncated_payload` (all modes, macOS and Linux) | RC0 register F3/F3b: the approved fail-closed fix #205 (decision D5) refuses them, so this describes main only until #205 is integrated. Separate from F4 (#214): compressed-MRC damage that the decompressor reports only through its exit status after complete-looking data is a documented RC0 limitation (validate with `xz -t`, `zstd -t` or `pbzip2 -t`). |
| EMPIAR-10342 ships a SerialEM defect list; MotionCorr refuses it with its SerialEM message. | smoke `e10342_serialem_defect` | expected behaviour; such lists need IMOD `clip defect` first |
| EMPIAR-10740's gain is transposed against the movies; `--gain_rot 3` is right. | gain orientation table | data property |
| Nine imagesets deposit compressed TIFF (`.tif.bz2`); MotionCorr reads compressed MRC only. | census | user must decompress |
| EPU EER and `.gain` files carry TIFF orientation tags 2, 4, 5, 6, 7; the readers ignore them, consistently for movie and gain. | census | upstream behaviour |
| The tutorial movies are 16-bit (width 3710, height 3838), and EMPIAR-10164 is mode 0 read as signed int8, not as `corpus.md`/`families.json` label them on main. | nvCOMP route in the #186 GPU runs; headers | corrected in `corpus.md` and `families.json` by #201 |

Synthetic-only findings (no real file of that kind was found in EMPIAR) are in the test-data
README, section 1c: 4K EER 65002 at `--eer_upsampling 2` loses the y subpixel; 2K EER with 4-bit
symbols at upsampling 2 places electrons on the wrong subpixels (the OR in `render2K_to_4K` keeps
them inside the frame); the legacy EER path reads uninitialised members; odd-width 4-bit MRC is
read without IMOD's row padding.

## Limitations

- No CPU or GPU timing baselines for the new families; the smoke runs are single, unpinned runs on
  shared SCARF nodes and only show that each encoding decodes, corrects and takes its route.
- Dose and voltage are placeholders for most new families; gain orientation was established only
  for e10740. Products were not compared with another program.
- Two movies per family; the census reads one or two files per imageset, so encodings that vary
  within an imageset are not counted.
- 8-bit TIFF was sampled in the census, and EMPIAR metadata was used only to select imagesets.

## Files

| path | purpose |
|---|---|
| `families-formats.json` | the eight format families |
| `tools/empiar_catalogue.py`, `tools/probe_formats.py`, `tools/summarize_census.py` | census |
| `tools/inspect_movies.py` | full-header inventory with frame counts (`evidence/formats/inspect-formats.json`) |
| `tools/format_smoke.py`, `tools/gain_orientation.py` | decode smoke runs and the gain orientation test |
| `evidence/formats/` | download manifest and results, census raw data and summary, smoke results, gain test |
