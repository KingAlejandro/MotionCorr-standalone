# Workload corpus (issue #186)

Ten movie families for timing and memory work on MotionCorr. Every performance number
before this corpus came from the RELION tutorial geometry. This file defines the corpus
so the CPU baselines (`cpu/README.md`) and a later GPU pass use the same inputs and
options. It makes timing and memory claims only; correctness and science stay in the
validation issues.

Source revision measured: main `116eb04a`. Data root on cpu64: `/home/ubuntu/mc-corpus-186/data`.
Run directories (`corpus/<id>/`, symlinks plus `movies.star`) are rebuilt by
`tools/setup_corpus.py families.json DATA_ROOT CORPUS_ROOT`.

## Families

| id | family | container | geometry (nx × ny × frames) | Mpx-frame / movie | angpix | kV | gain | movies |
|---|---|---|---|---:|---:|---:|---|---:|
| `tutorial` | RELION tutorial | u16 Deflate TIFF (label corrected; see below) | 3838 × 3710 × 24 | 342 | 0.885 | 200 | yes | 2 of 24 |
| `e10028` | EMPIAR-10028 | float32 MRC | 4096 × 4096 × 16 | 268 | 1.34 | 300* | no | 2 |
| `e10361` | EMPIAR-10361 | u8 LZW BigTIFF | 5760 × 4092 × 62 | 1461 | 0.826 | 300 | no (pre-normalised) | 2 |
| `e10641` | EMPIAR-10641 | u8 LZW BigTIFF | 5760 × 4092 × 70 | 1650 | 0.4 | 300* | yes | 2 |
| `e10441` | EMPIAR-10441 | u8 LZW BigTIFF | 11520 × 8184 × 50 | 4714 | 0.5685 | 200* | yes | 1 |
| `e10474f3` | EMPIAR-10474 Falcon 3 | EER | 4096 × 4096 × 58 (grouping 40) | 973 | 1.06 | 300* | no | 2 |
| `e10474f4` | EMPIAR-10474 Falcon 4 | EER | 4096 × 4096 × 144 (grouping 40) | 2416 | 1.64 | 300* | no | 2 |
| `e12963` | EMPIAR-12963 | EER | 4096 × 4096 × 39 (grouping 49) | 654 | 0.97 | 300* | yes | 1 |
| `e10164` | EMPIAR-10164 tilt series (added) | u8 MRC | 7420 × 7676 × 8 | 456 | 0.675 | 300* | no (pre-corrected) | 2 |
| `e10216` | EMPIAR-10216 apoferritin (added) | int16 MRC | 4096 × 4096 × 59 | 990 | 0.517 | 300* | no | 2 |

The tutorial movies are 16-bit Deflate TIFF with one row per strip. Earlier versions of this table
said 8-bit; `families.json` keeps that label so its SHA-256, cited by the CPU and GPU reports, stays
valid. The sample type did not change any run: main's nvCOMP route admits only 16-bit samples and the
tutorial took it.

**Format coverage.** `formats.md` lists every encoding the readers accept, an EMPIAR census of the
encodings actually deposited, and eight further real families (`families-formats.json`) for the
encodings these ten lack.

`*` voltage is a characterisation placeholder (the accession does not state it); dose
weighting cost does not depend on it. Mpx-frame is nx·ny·frames/1e6 and is the unit used
to compare shapes (for EER it counts grouped frames, not electron events).

## Selection rationale

**Held families** are the ones in the #96 validation corpus (recipes in
`evidence/recipes-from-96-corpus.json`, manifests in `evidence/selected-download-manifest.json`).
Together they cover frame sizes from 3.5 to 94 Mpx, 8 to 144 frames, four decode paths
(Deflate TIFF, LZW BigTIFF, float32 MRC, EER) and gain / no-gain.

**Added families** fill two shapes the held set lacks:

- **EMPIAR-10164 (short tilt-series movies).** 8 frames of 7420 × 7676, u8 MRC, gain-corrected, 3° tilt
  steps. With 8 frames per movie the per-movie fixed costs (gain, hot-pixel detection, patch set-up,
  dataset report, process start) are a large share, and the frame is the largest non-EER frame
  after 10441. Two tilts: 0° and +30° (`TS_01_000_0.0`, `TS_01_020_30.0`). Pixel size 0.675 Å is the raw
  super-resolution sampling (the accession lists 1.35 Å for the binned tilt-series).
- **EMPIAR-10216 (16-bit MRC).** 59 frames of 4096², int16 MRC (header mode 1; the accession says
  unsigned 16-bit), 1.98 GB per movie. Tests the 16-bit MRC read and convert path at a size
  comparable to the EER and 10028 frames, so MRC format effects can be separated from frame size.
  First two movies in the entry (`..._1739_Fractions.mrc`, `..._1742_Fractions.mrc`).

Both are linked as `.mrcs`: main requires that extension for MRC movie stacks, and the
files are served as `.mrc`.

**Considered and not added**

- `.mrc.bz2` / `.xz` / `.zst` MRC. Main decodes these through an external `pbzip2`, `xz` or
  `zstd` process; `pbzip2` is not installed on cpu64, and the cost would measure that tool, not MotionCorr.
  They are now covered for decoding by `e11217` and `e10202` in `families-formats.json` (`formats.md`).
- EMPIAR-10304 (int16 MRC, 4092 × 5760). Fast-incremental tilt series: one frame per tilt, not movies.
- Falcon 4 TIFF or other detectors. The frame sizes already span 3838×3710, 4096², 5760×4092,
  7420×7676 and 11520×8184, and the container paths are Deflate, LZW, MRC (u8/i16/f32) and EER.
  No remaining shape was missing enough to justify another download.

Added downloads: 4.9 GB (10164: 0.91 GB, 10216: 3.96 GB of movies, plus two XML files). Total corpus on disk: 21 GB.

## Identity

All files were downloaded again on cpu64 directly from `https://ftp.ebi.ac.uk/empiar/world_availability/<accession>/...`
with `tools/fetch_corpus.py` (curl, no laptop relay). Held-family files were verified against the SHA-256
values of the #96 manifests (22 of 22 pass, `evidence/selected-fetch.json`). The added files have
no earlier hash: size matched the HTTP Content-Length and the SHA-256 below is the one observed
on first fetch (`evidence/gap-fetch.json`). No download failed, so there are no `.failed-*` or `.partial` files.
The tutorial files are a copy of the tutorial set already on cpu64 and match
`docs/spa_24_movies_manifest.json` (24 movies and `gain.mrc`, 26 of 26 sums checked, `evidence/tutorial.sha256`).
The accession XML files (`10028.xml` … `12963.xml`) are also fetched and verified but are not run inputs.
The held-family download ran with the first version of `tools/fetch_corpus.py` (SHA-256 `20702bd5…a0fa16`), which required a hash for every file; the later version in this directory adds the size-only path used for the two added accessions and is otherwise the same.

| family | file (relative to data root) | bytes | SHA-256 |
|---|---|---:|---|
| tutorial | `tutorial/Movies/20170629_00026_frameImage.tiff` | 132,754,590 | `f989391b9d0e3e3b927a8de59d60179ade0b7ae5075ce7c3a9a5002ae2254ae3` |
| tutorial | `tutorial/Movies/20170629_00031_frameImage.tiff` | 132,157,138 | `fa2699a1203a2ee278a5973e10105ea3e56b18a1c1d5ee153482767cb7e71d8d` |
| tutorial | `tutorial/Movies/gain.mrc` | 56,956,944 | `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1` |
| e10028 | `EMPIAR-10028/data/Micrographs/Micrographs_part1/031_movie.mrcs` | 1,073,742,848 | `8ce479649ec00abf46b290aee2b43343d0ba0dc67f239f0e3fd0c6875b3c7213` |
| e10028 | `EMPIAR-10028/data/Micrographs/Micrographs_part1/091_movie.mrcs` | 1,073,742,848 | `75fb041c286c211dae1562f1746b948db45eefe2bb0603173fd7d8a5d7103bf2` |
| e10361 | `EMPIAR-10361/data/PS_18_2_4/PS.18.2.4_CTEM_103-12_0007_Jan20_08.57.33.tif` | 710,039,128 | `79efffaa086d56c799a234e3768843cb429c02c05d024f6a553a462acf8a6736` |
| e10361 | `EMPIAR-10361/data/PS_18_2_4/PS.18.2.4_CTEM_103-18_0004_Jan20_09.12.45.tif` | 708,051,618 | `3948c91b8f223f5ef860c05d974bfea42dc08f19bbcfe14332cc473a8737661b` |
| e10641 | `EMPIAR-10641/data/Movies/Dataset/HM70-1_10-A-002_0002_Oct28_23.00.41.tif` | 170,391,276 | `5f50686d7d32b9635fd64e550a91fc7d192849deeda30b7349a2827d17478c6d` |
| e10641 | `EMPIAR-10641/data/Movies/Dataset/HM70-1_10-A-004_0008_Oct28_23.06.04.tif` | 170,864,882 | `d0a4df43c93f694d792a9822a0f5d970ec866a0a9345d6bc44eb84e50020a617` |
| e10641 | `EMPIAR-10641/data/Movies/CountCDSRef_HM70-1_65-9_0000_Oct28_19.44.32.mrc` | 94,280,704 | `bdb0bb58f33d1b0dbf011222da0700f513ecb674e4085ed4708cce701dff7d95` |
| e10441 | `EMPIAR-10441/data/frames/20May09_3A-3_109-21_0003.tif` | 732,798,334 | `70f850d3deff2274fac8515d7d38c6654aab1791f7aa2cca5a8b61b43b26eb7c` |
| e10441 | `EMPIAR-10441/data/frames/200509_gain.mrc` | 377,119,744 | `b6036c9bab66fecb5c13fd5fed360c20405169b4d438d57b6a8d99801ff81b1e` |
| e10474f3 | `EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-39-45.801_eer_data_4096x4096.eer` | 1,215,708,772 | `fad4d37cc4b7b73076e3dd94c44be8a343f37f60b218e8057424b2154c9878ba` |
| e10474f3 | `EMPIAR-10474/data/EER_raw_movies_Falcon3_75K_magnification/2019-06-21_20-57-59.233_eer_data_4096x4096.eer` | 1,213,974,236 | `454cd504b40f00619e71312528af9ee9f2a4c19151611c2c7255ff19956d0214` |
| e10474f4 | `EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919949_Data_10919593_10919595_20200711_001116_Fractions.mrc.eer` | 2,931,223,304 | `2a46fd6123a7240e95acb324681c281964ec21da9037e05d66d9ab37319e9fed` |
| e10474f4 | `EMPIAR-10474/data/EER_raw_movies_Falcon4_47K_magnification/FoilHole_10919967_Data_10919593_10919595_20200711_002422_Fractions.mrc.eer` | 2,927,735,032 | `b440371d6a4b9648421633e2bfe36d8303ef88c21c27b4c3aa9031dcf99a04d5` |
| e12963 | `EMPIAR-12963/data/EMPIAR-Deposition/RawMicrographs/Images-Disc1/GridSquare_4650264/Data/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer` | 873,093,330 | `3fc5feb61f487f0f4f6ec1317ae033138fe50e7da80e3b5b16bab3aaff2403f5` |
| e12963 | `EMPIAR-12963/data/EMPIAR-Deposition/GainReference/20230326_221855_EER_GainReference.gain` | 33,874,221 | `6d4f3e5f9a6b837c637dc7098420e1c0cdfbbd61c9305a7780568f67c7134050` |
| e10164 | `EMPIAR-10164/data/frames/TS_01_000_0.0.mrc` | 455,648,384 | `117c303163480aa6bd3a1c1298c5635486dd077babce770dfcaf4ca944245039` |
| e10164 | `EMPIAR-10164/data/frames/TS_01_020_30.0.mrc` | 455,648,384 | `e6780acb0df21aae077fb9a5fdaf80a1553cd0fb4a339482aa59799b2642029d` |
| e10216 | `EMPIAR-10216/data/FoilHole_14961495_Data_14966722_14966723_20180615_1739_Fractions.mrc` | 1,979,712,512 | `f399bd30bfe1a9807bd494c348bfcf7d4aee312ccc18140b05abb1453ac23a56` |
| e10216 | `EMPIAR-10216/data/FoilHole_14961496_Data_14966722_14966723_20180615_1742_Fractions.mrc` | 1,979,712,512 | `c3b841e9ebcfb1e734a93c7bd7511033ded98c82b5c1cdb123f17e669e165ca1` |

Each family run reads `movies.star` from its run directory; paths inside are `Movies/<name>`.
Products land under `<out>/Movies/`, so absolute input paths are never used.

## Distinct and replayed inputs

Every movie in the table is a distinct file. Nothing is duplicated to make a family look larger.
A run processes the family's movies in one process, in STAR order. Repetitions re-run the same
files, so inputs are replayed across repetitions and read from a warm page cache (see the CPU
README). One-movie families (`e10441`, `e12963`) have no first-versus-steady split in the profile.

## Options

Common to every run (declared once, `cpu/README.md` repeats the placement):

```
--use_own --dose_weighting --dose_per_frame <per family> --bfactor 150 --seed 1
--expected_frames <decoded frames> --i movies.star --o out/<run>/ --j <1|4|8>
```

No `--save_noDW`, no `--even_odd_split`, no `--gpu`, no `--first_frame_sum/--last_frame_sum`
(none was required). `--expected_frames` makes a wrong decoded frame count fail the movie.

| config | added options |
|---|---|
| **G** (global only) | none (`--patch_x 1 --patch_y 1` are the defaults) |
| **L** (5×5 local) | `--patch_x 5 --patch_y 5` |

Per-family additions:

| id | `--dose_per_frame` | source | gain | EER |
|---|---:|---|---|---|
| `tutorial` | 1.277 | RELION tutorial value | `--gainref gain.mrc` | |
| `e10028` | 1.0 | placeholder | | |
| `e10361` | 1.032258 | recipe: 64 e/Å² over 62 frames | | |
| `e10641` | 1.0 | placeholder | `--gainref gain.mrc` | |
| `e10441` | 0.999033 | recipe: accession XML | `--gainref gain.mrc` | |
| `e10474f3` | 1.0 | placeholder | | `--eer_grouping 40 --eer_upsampling 1` |
| `e10474f4` | 1.0 | placeholder | | `--eer_grouping 40 --eer_upsampling 1` |
| `e12963` | 1.282051 | XML nominal 50 e/Å² / 39 frames | `--gainref gain.gain` | `--eer_grouping 49 --eer_upsampling 1` |
| `e10164` | 1.0 | placeholder | | |
| `e10216` | 1.0 | placeholder | | |

Gain orientation is the default (no `--gain_rot/--gain_flip`): these runs time the work and do not
establish gain correctness. `families.json` holds the same per-family values in machine-readable form.

## Files

| path | purpose |
|---|---|
| `families.json` | per-family geometry, options, movies, `skip_j` (CPU `--j 4` dropped for the two largest families) |
| `tools/fetch_corpus.py` | HTTPS fetch from EMPIAR with size and SHA-256 verification |
| `tools/setup_corpus.py` | per-family run directories (symlinks and `movies.star`) |
| `tools/run_matrix.py`, `runfilter.py`, `suspects.py`, `repair_loop.sh`, `analyse.py` | CPU baseline driver, run filter, repair pass and analyser (see `cpu/README.md`) |
| `evidence/` | download manifests and results, #96 recipes, tutorial checksums |
| `cpu/` | CPU baseline report, tables, raw runs and profiles |

## Reuse for the GPU pass

`families.json` and `tools/setup_corpus.py` define everything except placement. A GPU run adds
`--gpu <id>` and the ingest option and replaces the taskset lane; keep the options above and the
same two movies per family. Data and run directories on 4GPUs must be rebuilt from the same
manifests (`evidence/*-download-manifest.json`) and checked against the SHA-256 values above.
