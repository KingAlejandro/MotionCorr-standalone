# MotionCorr standalone

An experimental standalone build of RELION 5.1's CPU implementation of the MotionCor2-style motion correction algorithm. This repository contains the command-line motion correction entry point and its required RELION source files, without the full RELION application.

## Source and license

Extracted from [`3dem/relion` `ver5.1`](https://github.com/3dem/relion/tree/ver5.1) at commit `ad0b230ca22095700f6392479326836efb1c911d`. Original notices are retained in the source files; see `SOURCE_MANIFEST.txt` for the imported files. RELION's GPL-2.0-or-later terms apply; see `LICENSE` and `COPYING`. The included `d3x3` sources retain their copyright notices in their directories.

## Build

Requires a C++17 compiler, CMake 3.21+, FFTW (double and float), OpenMP, libtiff, libpng, libjpeg, and zlib. On macOS, a compiler with OpenMP support is required.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
```

The output is `build/motioncorr`. It was compiled on macOS with AppleClang and Homebrew libraries. Linux and other platforms have not yet been checked.

For a RELION-compatible movie STAR file, the command line follows RELION's CPU motion correction program:

```sh
./build/motioncorr --i movies.star --o MotionCorr --use_own --j 4
```

The `--use_own` flag selects the CPU implementation. The extracted runner still accepts RELION's external `--use_motioncor2` option, but this repository does not include that GPU program. This project does not include RELION's GUI or MPI executable.

## Status

This is an initial source extraction. Compilation succeeded on macOS. Processing of real movie data and numerical agreement with RELION's integrated motion correction have not yet been checked.
