# Issue 10: full-frame FFT memory cost on the CPU path

## Result

On a host with THP in `madvise` mode, asking for transparent huge pages on
large arrays cuts the CPU run from 19.4 s to 15.5 s (j4). All products are
byte-identical to main. A FFTW plan cache plus skipping the dose-weighting
inverse-FFT input copy saves a further 0.3–0.8 s and 220 MiB of peak RSS.

| arm (j4, rounds 7–9, median) | wall | user | sys | minor faults |
|---|---|---|---|---|
| main `116eb04` | 19.40 s | 65.3 s | 7.3 s | 3.37M |
| this branch | 15.56 s | 58.1 s | 1.4 s | 0.19M |
| this branch, `MOTIONCORR_HUGEPAGES=0` | 19.11 s | 65.1 s | 6.3 s | 2.89M |
| plan cache + `GLIBC_TUNABLES=glibc.malloc.hugetlb=1` | 15.24 s | 57.7 s | 1.4 s | 0.12M |

Huge pages shorten the global FFT (3.26 → 2.38 s), global iFFT (3.48 →
2.64 s), dose weighting, unweighted sums and the movie read. User time falls
by ~7 s, so most of the gain is fewer TLB misses in the strided FFT passes,
not only fewer faults. A single j1 pair (CPU 8) went from 44.6 s to 35.9 s.

Rounds 1–3 also measured the plan cache alone (20.2 vs 20.8 s for main) and
the existing `MOTIONCORR_MALLOC_REUSE=1` (19.6 s). The first hugetlb round was
an outlier (20.8 s, 12.6 s sys), likely kernel compaction. It did not recur in
the next eleven huge-page runs.

## Setup

- cpu64 (`small-refmac-machine`), Ubuntu glibc 2.39, THP `enabled=madvise`,
  `defrag=madvise`. Release build, `BUILD_TESTING=OFF`.
- Movie `20170629_00026_frameImage.tiff` with its gain, 5×5 patches, dose
  weighting, `--save_noDW --even_odd_split --profile`, `taskset -c 8-11 --j 4`.
- Arms interleaved per round after one warm run per binary, under
  `/tmp/motioncorr-cpu64-bench.lock`. Scripts: `scripts.txt`.
- Identity: SHA-256 of the data after header and extended header of all four
  MRCs (DW, noDW, EVN, ODD), plus the STAR files, against `main` round 1, for
  every run.

Files: `raw.txt` (per-run `/usr/bin/time` and per-stage medians),
`profiles.tar.gz` (`--profile` JSONL for every run).

## Limitations

- One movie, one host. A THP `always` host (e.g. SCARF) already gets huge
  pages, so the expected gain there is about zero; a THP `never` host is
  unchanged.
- With `defrag=madvise` the kernel may compact memory synchronously on fault,
  which can occasionally slow a run (see the outlier above).
- The CUDA path allocates the same host arrays but was not timed.
