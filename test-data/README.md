# MotionCorr test movies

These are **synthetic** movies with known frame shifts. Download both `.mrcs`
files from the [test-data-v1 release](https://github.com/KingAlejandro/MotionCorr-standalone/releases/tag/test-data-v1)
into this directory, or generate them locally. The STAR files are kept here so
each movie can be used with the standalone program or full RELION 5.1.

| Movie | Frames and size | File size | SHA-256 |
| --- | --- | ---: | --- |
| `synthetic_movie.mrcs` | 16 × 512 × 512 | 16,778,240 bytes | `fcfe8ec3131dff92bd0f62b63499fcd5d4c2413d73ccc44b60f1effa91daab22` |
| `large_movie.mrcs` | 32 × 1536 × 1536 | 301,990,912 bytes | `819837da89cd6655c2cd36e22f325ac6d55ceeb323e1ce092ab4609a8e3db429` |

Download with GitHub CLI:

```sh
gh release download test-data-v1 --repo KingAlejandro/MotionCorr-standalone \
  --dir test-data --pattern '*.mrcs'
shasum -a 256 test-data/*.mrcs
```

Alternatively, run `python3 test-data/generate_small.py` and
`python3 test-data/generate_large.py` with NumPy and SciPy installed. The
published assets were generated with NumPy 2.4.2 and SciPy 1.17.1; verify the
checksums when recreating them with another version.

Run the large comparison case from this directory:

```sh
../build/motioncorr --i large_movie.star --o large_output --use_own --j 4 \
  --patch_x 3 --patch_y 3 --dose_weighting --dose_per_frame 1.2
```

For a full RELION 5.1 comparison, use the same options with its
`relion_run_motioncorr` executable and a different output directory. In the
September 2026 macOS run, both implementations produced identical corrected
image pixels and motion STAR files. The measured shifts were within 0.0133
pixels of the known integer shifts (coordinate RMS 0.0046 pixels). MRC headers
record their separate run times, so whole-file hashes differ. The data do not
establish performance on experimental cryo-EM movies.
