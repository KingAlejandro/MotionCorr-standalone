# MotionCorr standalone

An experimental standalone build of RELION 5.1's CPU implementation of the MotionCor2-style motion correction algorithm. This repository contains the command-line motion correction entry point and its required RELION source files, without the full RELION application.

## Source and license

Extracted from [`3dem/relion` `ver5.1`](https://github.com/3dem/relion/tree/ver5.1) at commit `ad0b230ca22095700f6392479326836efb1c911d`. Original notices are retained in the source files; see `SOURCE_MANIFEST.txt` for the imported files. RELION's GPL-2.0-or-later terms apply; see `LICENSE` and `COPYING`. The included `d3x3` sources retain their copyright notices in their directories.

## Build

Requires a C++17 compiler, CMake 3.21+, FFTW (double and float), OpenMP, libtiff, libpng, libjpeg, and zlib. Ghostscript (`gs`) is needed for the optional summary PDF; without it, image and STAR outputs are written but `logfile.pdf` is empty.

### Prerequisites

#### Linux (Ubuntu / Debian)
```sh
sudo apt-get update
sudo apt-get install -y cmake build-essential pkg-config libfftw3-dev libtiff-dev libpng-dev libjpeg-dev zlib1g-dev ghostscript python3
```
*Note: GCC includes OpenMP (`libgomp`) by default. If building with Clang on Linux, install `libomp-dev`.*

#### Linux (Fedora / RHEL)
```sh
sudo dnf install -y cmake gcc-c++ pkgconf fftw-devel libtiff-devel libpng-devel libjpeg-turbo-devel zlib-devel ghostscript python3
```

#### macOS
Requires Homebrew and an OpenMP-capable compiler (such as `libomp` with AppleClang).
```sh
brew install cmake fftw libomp libtiff libpng jpeg ghostscript
```

### Compiling and Testing

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

The output binary is `build/motioncorr`. Linux builds and synthetic regression parity tests are continuously validated via GitHub Actions CI.

For a RELION-compatible movie STAR file, the command line follows RELION's CPU motion correction program:

```sh
./build/motioncorr --i movies.star --o MotionCorr --use_own --j 4
```

The `--use_own` flag selects the CPU implementation. The extracted runner still accepts RELION's external `--use_motioncor2` option, but this repository does not include that GPU program. This project does not include RELION's GUI or MPI executable.

You can also supply a movie file or quoted file wildcard directly when `--angpix` and `--voltage` are specified. This standalone build repairs a RELION 5.1 direct-input crash caused by missing per-movie metadata.

```sh
./build/motioncorr --i 'Movies/*.mrcs' --o MotionCorr --use_own --angpix 1.0 --voltage 300 --j 4
```

## Status

The experimental [RELION SPA tutorial movie dataset](test-data/README.md) is
the project's shared test dataset. Its source and preparation instructions are
kept in `test-data/`.

The standalone and a CPU-only build of full RELION from the exact upstream commit were run on the same inputs on macOS:

- A 16-frame, 512 × 512 synthetic MRC movie with known integer frame shifts. In the global run, recovered shifts differed from the known shifts by at most 0.0711 pixel (coordinate RMS 0.0301 pixel). Both the default global alignment and a 3 × 3 patch run with dose weighting produced pixel-identical corrected images (maximum absolute difference 0), including the non-dose-weighted image. Motion STAR files and logs matched after normalizing output paths.
- A 24-frame, 78 × 78 TIFF fixture. Corrected images, motion STAR files, and logs matched exactly after normalizing output paths. This tiny fixture is useful for I/O comparison, not for judging scientific alignment quality.
- Direct input of the synthetic movie now runs successfully in this standalone build and produces the same corrected image and motion metadata as STAR-file input. Full RELION 5.1 crashes on direct input before processing; the fix is in `src/motioncorr_runner.cpp`.
- A 32-frame, 1536 × 1536 synthetic movie (302 MB) with 3 × 3 patches and dose weighting. Corrected pixels and motion STAR files matched full RELION 5.1 exactly. Recovered shifts had 0.0046-pixel coordinate RMS error against the known integer shifts (maximum absolute error 0.0133 pixel). The only corrected MRC header difference was the run timestamp.
- One experimental movie from the RELION SPA tutorial (`20170629_00021_frameImage.tiff`, 24 frames, 3710 × 3838 pixels), with gain correction, 5 × 5 patches, and dose weighting. Standalone and full RELION 5.1 produced pixel-identical corrected images and identical motion STAR files with one thread. Multi-threaded runs now also achieve complete determinism and bit-for-bit parity with the single-thread baseline, using deterministic defect replacement PRNG seeding (`--seed`, default: 1).

This establishes parity for the cases above on both macOS and Linux. The remaining 23 tutorial movies and broader numerical/scientific validation across the full dataset are tracked in open project milestones.
