# MotionCorr standalone

An experimental standalone build of RELION 5.1's CPU implementation of the MotionCor2-style motion correction algorithm. This repository contains the command-line motion correction entry point and its required RELION source files, without the full RELION application.

> **Release status: EVALUATION RC0, not a stable release.** It is offered for evaluation and heavy testing. CUDA local alignment (`--patch_x`/`--patch_y` of 3 or more with `--gpu`) has **no unrestricted or stable support claim**: see known limitation **S1 (PROVISIONAL)** below and in [`docs/release/SUPPORT.md`](docs/release/SUPPORT.md).
>
> Coming from RELION? See [SUPPORT.md → Coming from RELION (#216)](docs/release/SUPPORT.md#0a-coming-from-relion-51-relion_run_motioncorr---use_own).

## Source and license

Extracted from [`3dem/relion` `ver5.1`](https://github.com/3dem/relion/tree/ver5.1) at commit `ad0b230ca22095700f6392479326836efb1c911d`. Original notices are retained in the source files; see `SOURCE_MANIFEST.txt` for the imported files. RELION's GPL-2.0-or-later terms apply; see `LICENSE` and `COPYING`. The included `d3x3` sources retain their copyright notices in their directories.

## Build

Requires a C++17 compiler, CMake 3.21+, FFTW (double and float), OpenMP, libtiff, libpng, libjpeg, and zlib. With `-DBUILD_TESTING=ON` (used below) CMake also needs a Python 3 that can import NumPy at configure time; pass `-DPython3_EXECUTABLE=<python>` (for example a virtual environment with `pip install numpy`) if the default Python lacks it. Ghostscript (`gs`) renders `logfile.pdf` and the other PDF reports. Without it a single-process run still writes the image, STAR and EPS products, but the PDF reports are absent or empty; `tools/multi_gpu/run_dataset.py` requires it. See [`docs/release/SUPPORT.md`](docs/release/SUPPORT.md) for failure behaviour.

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

The output binary is `build/motioncorr`. It has been compiled on macOS with AppleClang and Homebrew libraries, and on Ubuntu with GCC. On macOS, two CTest tests currently fail (`SyntheticRegression`, `MultiGpuScheduling`); they are under investigation and no macOS platform statement is made yet (see [`docs/release/SUPPORT.md`](docs/release/SUPPORT.md)). Linux builds and synthetic regression parity tests are continuously validated via GitHub Actions CI.

For a RELION-compatible movie STAR file, the command line follows RELION's CPU motion correction program:

```sh
./build/motioncorr --i movies.star --o MotionCorr --use_own --j 4
```

The `--use_own` flag selects the native implementation. With a CUDA build (`-DCUDA=ON`), `--gpu <id>` runs the motion-correction pipeline on one device: movie ingest and gain, global and local alignment, and dose-weighted reconstruction, with CPU fallbacks. `--use_own` accepts exactly one device id and rejects a list. To use several GPUs, run `tools/multi_gpu/run_dataset.py` (one process per device).

```sh
# Build with CUDA support (optional nvCOMP device Deflate decoding: add -DUSE_NVCOMP=ON -DNVCOMP_ROOT=<prefix>)
cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80
cmake --build build-cuda --parallel

# One GPU
./build-cuda/motioncorr --i movies.star --o MotionCorr --use_own --gpu 0 --j 4

# Several GPUs: one worker process per device (Linux). Needs Ghostscript (`gs`); --out must NOT already exist
python3 tools/multi_gpu/run_dataset.py \
  --binary "$PWD/build-cuda/motioncorr" --star movies.star --out MotionCorr_4gpu \
  --launcher-args="--devices 0,1,2,3" -- \
  --use_own --j 8
```

`--devices` takes `nvidia-smi` indices or GPU UUID prefixes, and everything after `--` goes to every worker. The multi-GPU run is verified for 1, 2 and 4 workers at `1db86902` (PR #209, which selected devices by UUID with explicit CPU masks); this exact command line has not been run by the author of this README text, and on macOS it stops with "Native multi-GPU worker cleanup requires Linux child-subreaper support" (checked). `--bin_factor` other than 1 turns on early binning by default, which bypasses the GPU-resident path: add `--no_early_binning` to keep the GPU-resident path with late binning (see [`docs/release/SUPPORT.md`](docs/release/SUPPORT.md) §3).

`./build/motioncorr --version` prints the version; `./build/motioncorr --use_own --help` lists the options.

**Validation status.** The gates and what each one measures are defined in [`docs/gate_contract.md`](docs/gate_contract.md). The CPU build is checked byte for byte against recorded CPU output (Tier A) and against known injected motion (Tier C). CUDA output is not byte-identical to CPU output. The strict CUDA-versus-CPU relative-RMSE diagnostic (limit 0.001) still fails: 0/24 tutorial movies in the historical [CUDA validation report](docs/cuda_global_alignment_validation.md), with relative RMSE 0.002899-0.010082. The explicit backend profile records that failure as non-blocking; it is a CPU-agreement diagnostic, not a measure of signal loss. No downstream scientific gate (CTF/FSC/B-factor) exists yet, so no scientific equivalence is claimed. Supported and experimental configurations are listed in the [RC0 support draft](docs/release/SUPPORT.md); the release checklist is [`docs/release/RELEASE_CHECKLIST.md`](docs/release/RELEASE_CHECKLIST.md).

**Known limitation S1 (PROVISIONAL, priority for heavy testing).** In the tested movies (EMPIAR-10216, 10474 Falcon 3 and 12963, 5×5 patches), CPU and CUDA local-alignment products differ substantially (relative RMSE 0.43–0.60). This was already present before RC0 (`116eb04a`). The difference is amplified by patch acceptance and the inherited unweighted polynomial fit. It also occurs among trajectories accepted on both backends; matching convergence status does not guarantee agreement. In the inspected cases the initiating events are frames where two cross-correlation peaks are within a few float ulps and the two backends order them differently. Making CUDA use the CPU tie rule (#70) changed two outputs slightly but did not explain the discrepancy. Whether the small map differences are pure rounding is not established. Other CUDA defects are not excluded, and no scientific equivalence or preference for either backend is established. Evidence: [PR #212](https://github.com/KingAlejandro/MotionCorr-standalone/pull/212) and [PR #209](https://github.com/KingAlejandro/MotionCorr-standalone/pull/209).

**Optional nvCOMP GPU decoder: input-trust precondition.** On builds configured with `-DUSE_NVCOMP=ON` (default OFF), `--ingest auto` sends eligible TIFFs (16-bit, Deflate/Adobe-Deflate, one row per strip, no predictor, native byte order) to NVIDIA nvCOMP's GPU Deflate decoder. nvCOMP 5.3 documents undefined behaviour for corrupt compressed input. MotionCorr checks the TIFF structure, zlib wrapper, sizes/offsets, decoder status, decoded length and an Adler-32 checksum before using any decoded data, but it cannot guarantee safe behaviour on a corrupt Deflate body. This route therefore assumes complete, unmodified acquisition files; use `--ingest compact` for files of unknown integrity or still being written. A file that changes between the tag scan and the read is not detected (follow-up [#215](https://github.com/KingAlejandro/MotionCorr-standalone/issues/215)). Checked arithmetic on the pre-decode path (T3, #217) is merged: an overflow or an unreadable strip offset gives a named decline (`--ingest auto` falls back to the host reader; a pinned `--ingest nvcomp` refuses); it does not change this precondition. Decision record: [`docs/rc0/decoder_trust_and_dependencies.md`](docs/rc0/decoder_trust_and_dependencies.md).

**Truncated raw MRC inputs fail.** A truncated raw MRC movie, gain reference or defect map now fails with "is truncated or unreadable" instead of publishing products (#205); compressed MRC is not covered by this.

**Compressed MRC inputs must be validated first.** `.bz2`/`.xz`/`.zst` MRC movies are read without checking the decompressor's exit status after a complete read, so some end-of-stream corruption is accepted. Run `xz -t`, `zstd -t` or `bzip2 -t`/`pbzip2 -t` on every file before processing (fix scheduled: [#214](https://github.com/KingAlejandro/MotionCorr-standalone/issues/214)). For EER, supply `--expected_frames <grouped_frames>` (or per-movie STAR frame counts), where grouped frames = raw fractions ÷ `--eer_grouping` with integer division (for example 2331 or 2330 fractions at `--eer_grouping 40` both give 58): a truncated EER file is otherwise processed as a shorter movie, and a fraction with a wrong pixel count is skipped with a warning. The check detects a mismatch in the grouped count only, not every shortened or damaged file. EER inputs, like nvCOMP inputs, are assumed complete and unmodified: memory safety of the inherited EER decoder on malformed or truncated input is not established, host out-of-bounds access and a process abort have been reported ([#221](https://github.com/KingAlejandro/MotionCorr-standalone/issues/221)), and the release disposition (fix or documented limitation) is pending; the EER input path is not claimed to be stable on damaged input. See [`docs/release/SUPPORT.md`](docs/release/SUPPORT.md) §6.

## Optional proprietary dependencies

- nvCOMP (tested 5.3.0.16) is optional and off by default (`-DUSE_NVCOMP`). It is not included or vendored in this repository, and it is licensed under NVIDIA's SDK agreement, which you obtain and accept from NVIDIA.
- This project distributes no binaries linked against nvCOMP or nvTIFF.
- Redistribution of such binaries remains subject to licensing review. Anyone who builds and distributes one must review both licences first.
- nvTIFF is not used by RC0.

Basis: the decision record [`docs/rc0/decoder_trust_and_dependencies.md`](docs/rc0/decoder_trust_and_dependencies.md), section 3.

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
- A fixed-code comparison of all 24 RELION SPA tutorial movies with full RELION 5.1 is documented in [`docs/spa_24_movies_validation.md`](docs/spa_24_movies_validation.md). It reports the single-thread and four-thread numerical gates separately, with a machine-readable [run manifest](docs/spa_24_movies_manifest.json).

The full dataset comparison was run on Linux x86_64. The macOS ARM64 checks above cover smaller fixtures. Linux builds and synthetic regression parity tests are continuously validated via GitHub Actions CI.
