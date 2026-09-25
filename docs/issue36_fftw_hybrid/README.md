# Issue 36: experimental FFTW correlation on the resident CUDA path

This experiment branches from PR #51 head `0c7d68f71c252aacd43d4e4d97ac31dd8ea47c6c`. The normal CUDA path remains the default. `MOTIONCORR_EXPERIMENTAL_GLOBAL_FFTW=1` applies FFTW C2R and the CPU peak decision only to global alignment; `MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1` applies it to global and local patch alignment. Both options keep movie frames resident on the GPU and retain the GPU Fourier-shift and reconstruction stages. They transfer the weighted CCF spectra to host for FFTW and peak finding.

## Result

Same-source CPU references were run on `cpu64`; CUDA runs used GPU 0 (A100) on `4GPUs`. All runs used one movie worker, seed 1, dose weighting, gain correction, and the full 5×5 patch configuration unless noted. The comparator is the repository's `tools/compare_motioncorr.py` with the unchanged `relaxed` Gate 2 relative-image-RMSE limit of `0.001`.

| Full 5×5 CUDA mode | `00021` relative RMSE | `00046` relative RMSE | Gate 2 |
| --- | ---: | ---: | --- |
| Default CUDA | 0.006105328 | 0.010438802 | Fail both |
| FFTW global only | 0.003803134 | 0.003864369 | Fail both |
| FFTW global and local | **0.000618735** | **0.000392505** | **Pass both** |

The all-FFTW mode has zero difference from the CPU global shifts **at STAR output precision** (24 frames per movie), and the comparator finds no STAR field differences. This does not establish bit-identical internal shifts. The corrected images are not pixel identical. Their maximum absolute pixel differences are 0.646 and 0.569 respectively, within the relaxed gate's limit of 5.

An additional `--patch_x 2 --patch_y 2` control skips local alignment. With the global FFTW option, its relative RMSE is `1.1328e-6` for `00021` and `1.1249e-6` for `00046`, passing Gate 2. The full 5×5 global-only FFTW mode still fails, so the local CUDA correlation/peak path accounts for the remaining gate failure in these movies. The earlier diagnostic FFT replay explains why FFT backends can move a flat peak; this result does not establish that FFTW alone explains every internal difference.

The unflagged experimental executable was compared with a separate pristine `0c7d68f` CUDA build. On both movies the corrected pixels, motion trajectory, and STAR fields passed the exact comparator. The output MRC headers include run-specific labels and are not compared as whole-file hashes.

## Time and memory

Three alternating paired repeats of the **final** CUDA binary, under one benchmark lock, gave:

| Movie | Default wall times, s | All-FFTW wall times, s | Median cost | Sampled GPU 0 peak |
| --- | --- | --- | ---: | ---: |
| `00021` | 4.60, 4.55, 4.55 | 5.24, 5.18, 5.30 | +0.69 s (+15.2%) | 4371.25 MiB in every run |
| `00046` | 4.58, 4.59, 4.60 | 5.27, 5.25, 5.26 | +0.67 s (+14.6%) | 4371.25 MiB in every run |

The whole-device peak was sampled every 20 ms with NVML, so identical observed values do not prove identical true peaks. The all-FFTW run transferred 360,562,176 CCF bytes per movie across the global and 25 local alignments. Its log attributes 118/123 ms to these transfers and 572/620 ms to host FFTW plus peak finding for `00021`/`00046`. The global alignment's own reported GPU allocation falls from 1569.59 to 1396.41 MiB because the device inverse-CCF images and batched cuFFT workspace are omitted; a different stage sets the measured whole-device peak. The CPU reference runs took 49.45/54.26 seconds on a different VM, so they are not paired speed benchmarks.

## Reproduction and provenance

The CUDA executable was built with CUDA 12.8.61, GCC 13.3, FFTW3f 3.3.10, Release, `TIMING=ON`, and architecture 80. Its SHA-256 is `e7f078904f5890aa435e7419b082df80382a679aa637345fa28a1e0538e06574`; the pristine base CUDA executable is `7f9e0e9b62caa650a58a94356aab475eae1bbc0d2606c9bfbd57413a1896edd8`. The CPU executable built from this source with `CUDA=OFF` is `c595f0685f83df446ac6b1b12498a4d35dd70dc7124269d6bc52460a82e7c14c`.

Input SHA-256: `00021` TIFF `df298b1b7741b1e5c9ec3b3e4514745a405d38b997b77a920f9f6b1bf30b99c0`, `00046` TIFF `61094383ce6750976275b13227033dcdb154c8214ef3db402aa6440a505ad377`, gain `8919cdc7bf0f481cdb3dd5bcb20d83c29e0263b2fcc78b212c74b33a81b1acd1`. Both hosts used identical input hashes and STAR selections: tutorial `movies.star` SHA-256 `fb998f70b375a4eb8d6972cf3964813c2c10fdfae039ec70c4e5365bf9cf0041` with `--do_at_most 1` for `00021`, and one-row `00046` STAR SHA-256 `29be387682e00c48da13d69e517709a8ff0b4583cca31fa037ee9366ffe32a31`.

Representative command, from the tutorial directory, was:

```sh
MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1 motioncorr \
  --i movies.star --o <fresh-output> --use_own --gpu 0 --j 1 \
  --do_at_most 1 --seed 1 --dose_weighting --dose_per_frame 1.277 \
  --patch_x 5 --patch_y 5 --bfactor 150 --gainref Movies/gain.mrc
```

For `00046`, `--i` selected the one-row STAR. For CPU, `--gpu 0` and the experimental flag were omitted. For default CUDA, the experimental flag was omitted. All `4GPUs` builds and movie runs were launched under top-level `taskset -c 96-103` with no more than eight build jobs and a shared `/tmp/motioncorr-bench.lock`; no other GPU compute job was present at the start of the paired run. The CPU-only reference was built and run on `cpu64` with `--j 1` and `OMP_NUM_THREADS=1`.

The exact and relaxed comparator JSON files are in [`comparisons/`](comparisons/); individual repeat times, sampled memory values, binary hashes, and CCF profile totals are in [`timing.json`](timing.json). Raw MRC outputs and process logs are retained outside Git in `/home/alex/MotionCorr-issue36-fftw-hybrid-results/` on `4GPUs` and `/home/ubuntu/MotionCorr-issue36-fftw-hybrid-results/` on `cpu64`.

**Decision:** keep this opt-in on an experimental branch. Both selected movies pass with all-patches FFTW, but the 24-movie tutorial gate, other inputs, and multi-worker behavior remain unverified. No tolerance was changed.
