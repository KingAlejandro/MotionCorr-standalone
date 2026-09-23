# RELION SPA tutorial data

The repository's test dataset is the **experimental beta-galactosidase movie
subset used by the [RELION SPA tutorial](https://relion.readthedocs.io/en/latest/SPA_tutorial/Introduction.html)**.
It contains 24 compressed TIFF movies and a gain reference. Download the
movies from the [spa-tutorial-data-v1 release](https://github.com/KingAlejandro/MotionCorr-standalone/releases/tag/spa-tutorial-data-v1),
or from the RELION team's original archive. The full acquisition is
[EMPIAR-10204](https://www.ebi.ac.uk/empiar/EMPIAR-10204/). EMPIAR's public
data are [CC0](https://www.ebi.ac.uk/empiar/policies/).

Download the movies from this repository's release:

```sh
mkdir -p relion30_tutorial/Movies
gh release download spa-tutorial-data-v1 \
  --repo KingAlejandro/MotionCorr-standalone \
  --dir relion30_tutorial/Movies
(cd relion30_tutorial/Movies && shasum -a 256 -c SHA256SUMS.txt)
python3 test-data/prepare_movies_star.py relion30_tutorial
```

Alternatively, fetch the original tutorial archive:

```sh
curl --fail --location --output relion30_tutorial_data.tar \
  ftp://ftp.mrc-lmb.cam.ac.uk/pub/scheres/relion30_tutorial_data.tar
tar -xf relion30_tutorial_data.tar
python3 test-data/prepare_movies_star.py relion30_tutorial
```

The archive is about 3.25 GB, so keep several GB of free disk space. The
preparation script writes `relion30_tutorial/movies.star` with the tutorial's
optics settings. Use `--limit 1` to prepare a single-movie comparison first.

From the extracted `relion30_tutorial` directory, run:

```sh
../build/motioncorr --i movies.star --o MotionCorr --use_own --j 4 \
  --dose_weighting --dose_per_frame 1.277 --patch_x 5 --patch_y 5 \
  --bfactor 150 --gainref Movies/gain.mrc
```

Adjust the executable path for your checkout. For parity, run RELION 5.1's
`relion_run_motioncorr` with the same input and options, using another output
The first movie (`20170629_00021_frameImage.tiff`) gave exact pixel and motion STAR parity
with `--j 1` on macOS. Four-thread runs are also fully deterministic and produce
bit-for-bit identical outputs to the single-thread baseline with the `--seed` option
(default: 1). The remaining 23 movies have not been compared yet.
