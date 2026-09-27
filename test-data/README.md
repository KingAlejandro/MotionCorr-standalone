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
