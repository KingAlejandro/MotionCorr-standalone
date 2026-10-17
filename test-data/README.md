# Test Datasets, Reference Gates, and Fixtures

This directory contains test datasets, synthetic fixture recipes, and verification tooling for MotionCorr Standalone. Detailed numerical acceptance gates and baseline benchmarks are documented in [docs/reference_gates.md](../docs/reference_gates.md).

The Python fixture generator and comparison tool require Python 3 and NumPy. Set `PYTHON=/path/to/python3` for `tools/run_regression_tests.sh` when NumPy is installed in a different environment.

---

## 1. Quick Verification with Synthetic Fixture (< 1s)

A small synthetic movie fixture is versioned directly in `test-data/fixtures/` along with exact reference outputs and ground truth shifts. This allows immediate smoke testing and parity verification without downloading multi-gigabyte files.

```sh
# Generate test output
cd test-data/fixtures
../../build/motioncorr \
  --i synthetic_128x128_8frames.star \
  --o test_run \
  --use_own --j 1

# Check parity against reference output
python3 ../../tools/compare_motioncorr.py \
  --ref reference_output \
  --test test_run \
  --ground-truth synthetic_128x128_8frames_ground_truth.json \
  --gate exact
```

To regenerate or scale the synthetic fixtures, use `generate_synthetic_fixture.py`:

```sh
# Generate small fixture (128x128, 8 frames)
python3 test-data/generate_synthetic_fixture.py --profile small

# Generate standard benchmark movie (512x512, 16 frames)
python3 test-data/generate_synthetic_fixture.py --profile standard

# Generate large stress-test movie (1536x1536, 32 frames)
python3 test-data/generate_synthetic_fixture.py --profile large
```

---

## 1b. Known-Motion and Local-Field Gate (Issue #59)

`test-data/known_motion/` holds synthetic movies with a **known global and spatially varying
displacement field**, used to check the field MotionCorr actually applies -- at declared
positions and frames, in pixels and angstroms -- rather than only the corrected pixels. This is
separate from `tools/compare_motioncorr.py`: that tool compares a run to a reference run, this
one compares a run to ground truth. Gates 1 and 2 are untouched.

The movies are not versioned; they regenerate deterministically in about 2 s and their SHA-256
hashes are recorded in `test-data/known_motion/MANIFEST.json`.

```sh
# fixtures (add --include-heavy for the opt-in 400 MB real-scale case)
python3 test-data/generate_known_motion_fixture.py

# run everything: MotionCorr, the field gate, dose-weighting and thread invariance,
# and the applied-field self-consistency witness
python3 tools/run_known_motion_gates.py --outdir /tmp/km59 --json /tmp/km59/all.json

# unit checks, fixture self-validation, negative controls, detection sensitivity
python3 tools/test_known_motion.py
```

Tolerances, their physical derivation, results, and the negative controls are in
[docs/known_motion_validation.md](../docs/known_motion_validation.md); the design record is
[agents/designs/issue_59_known_motion_local_field_gates.md](../agents/designs/issue_59_known_motion_local_field_gates.md).

---

## 1c. Input-Format Fixtures (every container, sample type and codec)

`generate_format_fixtures.py` writes one integer-valued movie (counts 0..15) in every encoding
the readers accept, plus encodings they must refuse. Every value is exact in every sample type,
so each accepted encoding must decode to the same array and give byte-identical products to the
float32 MRC reference. The encoders (`formats/encoders.py`) are pure Python and NumPy and were
cross-checked against LibTIFF and tifffile/imagecodecs during development. Nothing is versioned:
the fixtures regenerate in about 15 s (about 100 MB) and `manifest.json` records every SHA-256.

| group | what it covers |
|---|---|
| MRC | modes 0, 1, 2, 6, 12, 101; big-endian; FEI2 and SERI extended headers; `.mrcs.xz/.bz2/.zst` |
| TIFF | u8, u16, s8, s16, f32; none, LZW, Deflate (8 and 32946), PackBits; predictors 2 and 3; big-endian; BigTIFF; one and many rows per strip; orientation tag |
| full sample ranges | u16 up to 65535, s16 down to -32768, u8 above 127, s8 negative, in TIFF (several codecs) and MRC, so signed/unsigned confusion cannot pass |
| EER | 65000, 65001, 65002 at 2048^2 and 4096^2; upsampling 1, 2, -1; trailing fractions; EPU `.gain` and count-reference gains |
| gain, defect | gain as MRC f32/f16/s16/u16/s8 and TIFF f32/u16/u8; defects as text and as MRC/TIFF maps |
| rejected | MRC modes 3, 4, 5, odd-by-odd mode 101; TIFF u32, f64, f16, tiled, RGB, mixed frame sizes; EER 3072^2, unknown code, 65002 with 8-bit runs, upsampling -1 on 65002; SerialEM defect lists |
| heavy (opt-in) | IMOD packed 4-bit TIFF at the K2 super-resolution geometry it is recognised by |

```sh
python3 tests/test_input_formats.py --binary build/motioncorr --helper build/runner_numerics
# add --include-heavy for the packed 4-bit TIFF (about 20 s more)
# on a CUDA build: --ingest-matrix --nvcomp yes|no also runs --ingest float and auto on the GPU
```

`--ingest-matrix` requires exactly one `--ingest_witness` line per movie: `float` under
`--ingest float`, and under `auto` the route the generator derives from the file's encoding
(manifest `e2e.route`, mirroring main's admission rules; nvCOMP-eligible movies take compact on a
build without nvCOMP). Products must be byte-identical across the two modes, and a few pinned
`--ingest compact/nvcomp` runs must take the pinned route or refuse. Exhaustive pinned-route and
boundary qualification stays with the MRC staging matrix (#204) and the EER qualification (#208).

The CTest entry is `InputFormats`. Compressed-MRC cases need `pbzip2` and `zstd` (CI installs
both); a missing decoder is reported UNRUN and fails the suite unless it was absent at configure
time.

Cases that document current behaviour rather than a pass. A characterised case must match the
current output exactly (computed from the reader's own formulas) and differ from the format's
definition; a known failure records the current outcome and fails when it changes:

| case | behaviour |
|---|---|
| `mrc_truncated_payload`, `mrc_mode0_imod_4bit_flag` | **refused** (reject cases): non-signal failure naming the movie ("is truncated or unreadable"), no product, no completion STAR. This needs the fail-closed short-read fix (F3/F3b, #205, decision D5); main before it accepted these movies and corrected stale frame-buffer contents. Truncated compressed MRC streams are a separate RC0 limitation (F4, #214). |
| `mrc_compressed_zst_symlink` | **known failure.** `zstd -cdk` ignores a symbolic-link input, so a linked `.mrc.zst` movie fails to open. |
| `eer_4k_65002_render_up2` | **characterised.** 4K EER with 1+1 subpixel bits at `--eer_upsampling 2` uses the 4-bit masks; y subpixel is always 0. |
| `eer_2k_65000_render_up2`, `eer_2k_65001_render_up2` | **characterised.** 2K EER with 4-bit symbols at upsampling 2 takes x from symbol bit 0 and ORs three bits into y: wrong subpixels, always inside the frame. |
| `mrc_mode101_odd_width` | **characterised.** IMOD pads odd-width 4-bit rows; the reader does not. |
| `mrc_mode0_unsigned_bytes` | **characterised.** Mode 0 is read signed, as upstream (IMOD writes it unsigned). |
| `eer_legacy_container` | **not run.** The legacy EER path reads uninitialised members. |

All of these are inherited from upstream RELION 5.1 unless stated otherwise.

### Cut-down real movies

`real_cutdown_manifest.json` lists one cut-down movie per corpus family
(`docs/workload_corpus/corpus.md` and `formats.md`): a few frames, or 30 EER fractions, of a real
EMPIAR movie in its producer's exact encoding. `tools/cut_down_movie.py` copies raw TIFF/EER strips
without re-encoding; raw MRC is cropped to 2048^2 where the frame is large. About 436 MB in all,
not versioned in Git: the files are assets of the GitHub release
[`real-cutdown-v1`](https://github.com/KingAlejandro/MotionCorr-standalone/releases/tag/real-cutdown-v1)
(a draft until the maintainer publishes it; until then anonymous `--download` does not work and
`gh release download real-cutdown-v1` needs repository access). Asset names fold the item directory
into the name (`<item>__<file>`).

Licence: the source movies are EMPIAR data, which EMPIAR releases under CC0
([EMPIAR policies](https://www.ebi.ac.uk/empiar/policies/)); the tutorial movie is from
EMPIAR-10204. The manifest records each source accession and path, the source SHA-256, the frame
and crop selection, and the cut file's SHA-256.

```sh
python3 tests/test_real_cutdown.py --binary build/motioncorr --helper build/runner_numerics \
  --assets DIR [--download RELEASE_URL]
# or configure with -DMC_REAL_CUTDOWN_DIR=DIR to register the RealCutdown CTest entry
```

`CutDownMovie` (default suite) checks the cut tool itself on generated inputs in every container,
including MRC whose byte order only the machine stamp or payload size can decide.

Each item checks file SHA-256, the SHA-256 of MotionCorr's decoded samples (decoding is exact, so
this is portable), a correction run with the expected frame count, and, for EMPIAR-10342, that its
SerialEM defect list is refused. `tools/make_real_cutdown.py` rebuilds the files and manifest from
`real_cutdown_plan.json` on a host with the corpus data.

---

## 2. Experimental RELION SPA Tutorial Dataset

The experimental benchmark dataset is the **beta-galactosidase movie subset used by the [RELION SPA tutorial](https://relion.readthedocs.io/en/latest/SPA_tutorial/Introduction.html)**.
It contains 24 compressed TIFF movies and a gain reference. The full acquisition is [EMPIAR-10204](https://www.ebi.ac.uk/empiar/EMPIAR-10204/) (CC0 license).

Download the movies from this repository's release:

```sh
mkdir -p relion30_tutorial/Movies
gh release download spa-tutorial-data-v1 \
  --repo KingAlejandro/MotionCorr-standalone \
  --dir relion30_tutorial/Movies
(cd relion30_tutorial/Movies && shasum -a 256 -c SHA256SUMS.txt)
python3 test-data/prepare_movies_star.py relion30_tutorial --limit 1
```

Alternatively, fetch individual assets directly via curl:

```sh
URL="https://github.com/KingAlejandro/MotionCorr-standalone/releases/download/spa-tutorial-data-v1"
mkdir -p relion30_tutorial/Movies && cd relion30_tutorial/Movies
curl -fLO "${URL}/20170629_00021_frameImage.tiff"
curl -fLO "${URL}/gain.mrc"
curl -fLO "${URL}/SHA256SUMS.txt"
awk '$2 == "20170629_00021_frameImage.tiff" || $2 == "gain.mrc" { print }' SHA256SUMS.txt | shasum -a 256 -c -
cd ../..
python3 test-data/prepare_movies_star.py relion30_tutorial --limit 1
```

From `relion30_tutorial`, execute MotionCorr in CPU mode:

```sh
# Single-thread reproducible baseline
../build/motioncorr --i movies.star --o MotionCorr_j1 --use_own --j 1 \
  --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
  --bfactor 150 --gainref Movies/gain.mrc

# Multi-threaded run
../build/motioncorr --i movies.star --o MotionCorr_j4 --use_own --j 4 \
  --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
  --bfactor 150 --gainref Movies/gain.mrc
```

Adjust the executable path for your checkout. For parity, run RELION 5.1's
`relion_run_motioncorr` with the same input and options, using another output
The first movie (`20170629_00021_frameImage.tiff`) gave exact pixel and motion STAR parity
with `--j 1` on macOS. Four-thread runs are also fully deterministic and produce
bit-for-bit identical outputs to the single-thread baseline with the `--seed` option
(default: 1). The remaining 23 movies have not been compared yet.
---

## 3. Comparing Outputs and Acceptance Gates

Use `tools/compare_motioncorr.py` to compare any output against a reference:

```sh
# Verify exact CPU parity
python3 tools/compare_motioncorr.py \
  --ref path/to/reference_output \
  --test relion30_tutorial/MotionCorr_j1 \
  --gate exact

# Verify multi-threaded or GPU accelerated run against relaxed gate
python3 tools/compare_motioncorr.py \
  --ref relion30_tutorial/MotionCorr_j1 \
  --test relion30_tutorial/MotionCorr_j4 \
  --gate relaxed
```

See [docs/reference_gates.md](../docs/reference_gates.md) for full gate specifications, error thresholds, and benchmark data.
