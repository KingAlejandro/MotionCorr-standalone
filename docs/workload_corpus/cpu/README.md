# CPU baselines on the workload corpus (cpu64, main `116eb04a`)

Timing and memory of the CPU backend (`--use_own`, no CUDA) for the ten corpus families in
[`../corpus.md`](../corpus.md). Issue #186 (corpus and baselines), closing the remaining item of #9.
These are timings and memory only. They make no correctness or science claim, and no product
comparison was run beyond the exit status, the product count and the retained output hashes.

## Result in brief

- **Cost per movie** at `--j 8`, L (5×5 local), ranges from 6.5 s (EMPIAR-10028) to 147 s (EMPIAR-10441). At `--j 1` it is 26 s to 553 s. Per megapixel-frame the CPU cost is **93–152 ms (L j1)** across families; the tilt-series family is the highest because 7420×7676 is an unfavourable FFT size.
- **Dose weighting is the largest stage in every family and both configurations** (37–48% of a G movie, 26–36% of an L movie at j8). With the global FFT and inverse FFT it is 63–86% of a G movie and 61–80% of an L movie. Patch alignment is 10–23% of an L movie.
- **Thread scaling is the same everywhere:** j8 speedup 3.7–4.4× (46–55% efficiency), j4 2.0–2.3× (51–58%). The family does not change it.
- **Input decode is small on CPU:** LZW read is 3–6 ms/Mpx-frame, the same as Deflate. EER read costs 2–4× more (10–13 ms/Mpx-frame at j1: 10–12% of an L movie, 17–19% of a G movie; 20–22% of a G movie at j8).
- **Fixed per-process and per-movie costs are not an issue:** time outside the movie stages is 0.2–0.4 s per run, and the first movie is not systematically slower than the second (first/second differs by −9% to +8% across cells, within run-to-run noise). The 8-frame tilt-series movies show no fixed-cost problem on CPU.
- **Peak RSS is about two full-frame stacks:** 36 GiB for EMPIAR-10441 and 21 GiB for the 144-frame EER at j1.
- **`--profile` overhead is not distinguishable from noise** (median −0.2% over 55 cells; 51 are within ±3%, the other four are +4% to +10%).
- **Cost of host noise:** another user's long-running `refmac5` jobs on cpus 2–3 inflated individual runs by up to 30% in CPU time even when they did not share the lane CPU (details under Limitations). Disturbed runs are excluded; the repetition count fell short in 18 of 56 cells.

## Settings (declared once)

- Source: main `116eb04ad359`, clean clone, `cmake -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF`, `flags.make` shows `-O3 -DNDEBUG -fopenmp`, GCC 13.3.0, FFTW 3.3.10, libtiff 4.5.1. Binary SHA-256 `86a43e9f…8bed53` (`provenance.json`).
- Options: per family as in `../corpus.md` (`--use_own --dose_weighting --bfactor 150 --seed 1 --expected_frames N`, gain and EER options where the family has them). **G** adds nothing; **L** adds `--patch_x 5 --patch_y 5`. No `--save_noDW`, no `--even_odd_split`.
- Placement: `taskset -c 0` for `--j 1`, `taskset -c 0-3` for `--j 4`, `taskset -c 0-7` for `--j 8`, all on NUMA node 0. `OMP_NUM_THREADS` equals `--j`. **`OMP_PROC_BIND` and `OMP_PLACES` are unset** (the driver removes them with `env -u`), so threads are not bound inside the cpuset. `--j 8` matches the GPU lane used elsewhere.
- Host: cpu64 (`small-refmac-machine`), AMD EPYC 7763, 64 cores, SMT off, 2 NUMA nodes, 226 GB RAM, Ubuntu 24.04, kernel 6.8.0-86. **THP is `madvise`** (defrag `madvise`); no `GLIBC_TUNABLES`; SCARF is `always`, so absolute times are not comparable with SCARF. The guest exposes no cpufreq control. The guest reports one L3 for cpus 0–31.
- Data: local disk on `/`, read from a warm page cache (each family has a discarded warm-up run first; 21 GB of corpus fits in the 190 GB page cache).
- Runs: process wall from the outside (`CLOCK_MONOTONIC` around the process) plus `/usr/bin/time -v` (user, sys, peak RSS, minor faults). Every run must exit 0 and write one `*.mrc` per movie; all 283 measured records and 10 warm-ups did. The unprofiled and profiled (`--profile <file>.jsonl`) arms of each family are interleaved in shuffled order per round (3 unprofiled and 2 profiled repetitions per cell, planned). The driver holds `/tmp/motioncorr-cpu64-bench.lock` for one round of one family at a time.
- Budget: the j8 L warm-ups summed to 623 s, which extrapolated to about 12.5 h of lock time. Following the task rule, `--j 4` was dropped for **EMPIAR-10441 and EMPIAR-10474 Falcon4 (144 frames)**. Repetitions were not dropped. The summed wall time of all 293 runs is 8.6 h (plus 0.9 h of pre-run settle waits); elapsed time was about a day because of queueing behind other users' runs on the lock.
- Retained: `raw/runs.jsonl` (one JSON line per run: command, cpuset, wall, user/sys, RSS, faults, foreign load, products), `raw/<family>/*.jsonl` (profiles), `*.time` (`time -v` output), `*.log.gz` (run stdout), `raw/<family>/tree-*.json` (SHA-256 of every file and the payload SHA-256 of every `.mrc` for the kept run of each family and configuration: the first unprofiled j8 run), `driver-logs/`, `provenance.json`. Tables below come from `../tools/analyse.py` (`tables.md`, `summary.json`).

## Run filtering

Records are excluded from every statistic when (1) the lane showed foreign CPU load above 0.25 core (from `/proc/stat` deltas, for the lane and for cpus 0–7) or the 300 s pre-run settle wait timed out, or (2) CPU time (user+sys) was more than 15% above the minimum of its cell. Rule 2 uses CPU time only, never wall, and exists because the lane counters missed some interference (see Limitations). Excluded runs are listed at the end of the tables with their reason, and `raw/runs.jsonl` keeps all of them. A repair pass re-ran the flagged arms and got one clean replacement before the host stayed too busy to continue; I stopped it rather than hold the lock waiting. Cells that ended below 3 unprofiled or 2 profiled repetitions are named in the last table.

## Tables (generated)

### Per-movie process wall (s), unprofiled: median [min-max]

Process wall / movies in the run (includes process start and the dataset report). n = unprofiled repetitions.

| family | movies | G j1 | G j4 | G j8 | L j1 | L j4 | L j8 | n |
|---|---:|---|---|---|---|---|---|---:|
| RELION tutorial | 2 | 24.8 [24.7-25.0] | 10.7 [10.6-10.7] | 5.8 [5.8-5.9] | 42.3 [42.2-42.7] | 18.6 [18.4-18.7] | 10.0 [9.9-10.0] | 2/3 |
| EMPIAR-10028 | 2 | 14.6 [14.5-14.8] | 6.5 [6.4-6.6] | 3.7 [3.7-3.9] | 25.6 [25.2-25.9] | 11.8 [11.5-11.8] | 6.5 [6.4-6.5] | 2/3 |
| EMPIAR-10361 | 2 | 88.1 [86.3-89.9] | 43.4 [43.2-44.3] | 24.1 [23.6-24.2] | 141.2 [139.3-149.2] | 69.5 [69.2-69.8] | 38.6 [38.1-39.0] | 2/3 |
| EMPIAR-10641 | 2 | 104.1 [101.2-105.1] | 50.5 [49.7-51.1] | 27.3 [26.8-27.7] | 170.5 [165.2-177.7] | 80.4 [78.8-82.5] | 44.4 [44.3-44.9] | 3 |
| EMPIAR-10441 | 1 | 342.9 [330.8-359.0] | - | 88.3 [84.9-94.8] | 553.4 [551.6-558.8] | - | 147.5 [147.1-152.4] | 3 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 | 60.9 [60.4-61.2] | 27.6 [27.5-27.7] | 15.5 [15.4-15.6] | 101.7 [101.2-101.9] | 46.5 [46.1-46.5] | 25.8 [25.7-25.9] | 3 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 | 153.4 [153.3-153.8] | - | 36.5 [35.4-38.2] | 262.0 [260.9-263.4] | - | 59.9 [59.6-64.4] | 3 |
| EMPIAR-12963 | 1 | 42.8 [42.6-43.5] | 19.2 [18.5-19.5] | 11.6 [10.7-11.6] | 71.9 [71.2-76.9] | 33.5 [32.0-34.7] | 18.8 [18.7-19.5] | 3 |
| EMPIAR-10164 tilt series (8 fr) | 2 | 42.4 [40.8-43.9] | 18.9 [18.6-19.6] | 10.6 [10.3-10.7] | 69.7 [69.6-72.6] | 32.2 [31.0-33.3] | 16.7 [16.7-17.6] | 2/3 |
| EMPIAR-10216 apoferritin (59 fr) | 2 | 52.5 [52.1-53.0] | 23.9 [23.4-23.9] | 13.2 [12.5-13.2] | 91.6 [91.1-103.9] | 41.5 [41.4-41.6] | 23.5 [23.3-23.5] | 2/3 |

### Scaling (median wall, j1 to j4 and j8)

| family | cfg | j4 speedup | j4 eff. | j8 speedup | j8 eff. |
|---|---|---:|---:|---:|---:|
| RELION tutorial | G | 2.33 | 58% | 4.25 | 53% |
| RELION tutorial | L | 2.27 | 57% | 4.25 | 53% |
| EMPIAR-10028 | G | 2.25 | 56% | 3.96 | 49% |
| EMPIAR-10028 | L | 2.17 | 54% | 3.93 | 49% |
| EMPIAR-10361 | G | 2.03 | 51% | 3.65 | 46% |
| EMPIAR-10361 | L | 2.03 | 51% | 3.66 | 46% |
| EMPIAR-10641 | G | 2.06 | 51% | 3.82 | 48% |
| EMPIAR-10641 | L | 2.12 | 53% | 3.84 | 48% |
| EMPIAR-10441 | G | - | - | 3.88 | 49% |
| EMPIAR-10441 | L | - | - | 3.75 | 47% |
| EMPIAR-10474 Falcon3 (58 fr) | G | 2.21 | 55% | 3.92 | 49% |
| EMPIAR-10474 Falcon3 (58 fr) | L | 2.19 | 55% | 3.95 | 49% |
| EMPIAR-10474 Falcon4 (144 fr) | G | - | - | 4.21 | 53% |
| EMPIAR-10474 Falcon4 (144 fr) | L | - | - | 4.38 | 55% |
| EMPIAR-12963 | G | 2.23 | 56% | 3.69 | 46% |
| EMPIAR-12963 | L | 2.15 | 54% | 3.82 | 48% |
| EMPIAR-10164 tilt series (8 fr) | G | 2.24 | 56% | 4.00 | 50% |
| EMPIAR-10164 tilt series (8 fr) | L | 2.17 | 54% | 4.18 | 52% |
| EMPIAR-10216 apoferritin (59 fr) | G | 2.20 | 55% | 3.99 | 50% |
| EMPIAR-10216 apoferritin (59 fr) | L | 2.21 | 55% | 3.90 | 49% |

### Peak RSS (GiB), minor faults (millions), user+sys (s): median over unprofiled runs

| family | cfg | j1 RSS | j4 RSS | j8 RSS | j1 faults | j8 faults | j1 user+sys | j8 user+sys | j1 sys % | j8 sys % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RELION tutorial | G | 2.75 | 2.90 | 3.08 | 3.91 | 3.20 | 50 | 84 | 15 | 11 |
| RELION tutorial | L | 2.75 | 2.96 | 3.19 | 4.95 | 4.19 | 85 | 149 | 11 | 8 |
| EMPIAR-10028 | G | 2.17 | 2.30 | 2.58 | 3.51 | 3.00 | 29 | 51 | 24 | 18 |
| EMPIAR-10028 | L | 2.17 | 2.40 | 2.67 | 4.46 | 3.80 | 51 | 95 | 17 | 11 |
| EMPIAR-10361 | G | 11.12 | 11.12 | 11.27 | 15.69 | 13.63 | 176 | 348 | 16 | 10 |
| EMPIAR-10361 | L | 11.24 | 11.38 | 11.99 | 22.33 | 17.94 | 282 | 570 | 13 | 8 |
| EMPIAR-10641 | G | 12.62 | 12.62 | 12.73 | 18.90 | 15.25 | 208 | 391 | 16 | 11 |
| EMPIAR-10641 | L | 12.75 | 13.01 | 13.50 | 26.98 | 20.70 | 341 | 656 | 13 | 8 |
| EMPIAR-10441 | G | 36.30 | - | 37.08 | 33.90 | 23.41 | 343 | 629 | 16 | 10 |
| EMPIAR-10441 | L | 36.31 | - | 39.09 | 55.72 | 34.48 | 553 | 1075 | 15 | 8 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 8.56 | 8.62 | 8.77 | 11.77 | 9.04 | 122 | 204 | 19 | 13 |
| EMPIAR-10474 Falcon3 (58 fr) | L | 8.62 | 8.78 | 9.16 | 15.50 | 11.73 | 203 | 362 | 14 | 9 |
| EMPIAR-10474 Falcon4 (144 fr) | G | 20.90 | - | 21.12 | 28.82 | 22.60 | 307 | 499 | 18 | 14 |
| EMPIAR-10474 Falcon4 (144 fr) | L | 21.19 | - | 21.35 | 48.75 | 28.86 | 524 | 868 | 16 | 10 |
| EMPIAR-12963 | G | 5.92 | 5.98 | 6.14 | 5.03 | 3.29 | 43 | 74 | 22 | 14 |
| EMPIAR-12963 | L | 5.91 | 6.20 | 6.47 | 6.71 | 4.23 | 72 | 129 | 16 | 10 |
| EMPIAR-10164 tilt series (8 fr) | G | 3.90 | 4.53 | 5.44 | 5.32 | 4.92 | 85 | 151 | 13 | 11 |
| EMPIAR-10164 tilt series (8 fr) | L | 3.89 | 4.58 | 5.57 | 7.16 | 6.55 | 139 | 248 | 10 | 8 |
| EMPIAR-10216 apoferritin (59 fr) | G | 7.55 | 7.60 | 7.67 | 10.86 | 9.70 | 105 | 177 | 20 | 16 |
| EMPIAR-10216 apoferritin (59 fr) | L | 7.62 | 7.73 | 8.15 | 14.30 | 12.95 | 183 | 336 | 15 | 11 |

### Profile overhead: median profiled wall minus median unprofiled wall (process, whole run)

| family | cfg | j | n unprof / prof | unprof s | prof s | overhead s | overhead % |
|---|---|---:|---|---:|---:|---:|---:|
| RELION tutorial | G | 1 | 3 / 2 | 49.7 | 50.6 | 0.95 | 1.9 |
| RELION tutorial | G | 4 | 3 / 2 | 21.3 | 21.2 | -0.14 | -0.6 |
| RELION tutorial | G | 8 | 3 / 2 | 11.7 | 11.6 | -0.12 | -1.0 |
| RELION tutorial | L | 1 | 3 / 2 | 84.7 | 85.0 | 0.26 | 0.3 |
| RELION tutorial | L | 4 | 3 / 2 | 37.2 | 37.1 | -0.18 | -0.5 |
| RELION tutorial | L | 8 | 2 / 2 | 19.9 | 19.8 | -0.13 | -0.7 |
| EMPIAR-10028 | G | 1 | 3 / 2 | 29.3 | 29.2 | -0.05 | -0.2 |
| EMPIAR-10028 | G | 4 | 3 / 2 | 13.0 | 13.0 | -0.01 | -0.1 |
| EMPIAR-10028 | G | 8 | 3 / 2 | 7.4 | 7.3 | -0.11 | -1.5 |
| EMPIAR-10028 | L | 1 | 2 / 2 | 51.2 | 51.3 | 0.14 | 0.3 |
| EMPIAR-10028 | L | 4 | 3 / 2 | 23.5 | 23.4 | -0.14 | -0.6 |
| EMPIAR-10028 | L | 8 | 3 / 2 | 13.0 | 12.8 | -0.18 | -1.4 |
| EMPIAR-10361 | G | 1 | 2 / 2 | 176.1 | 181.1 | 4.99 | 2.8 |
| EMPIAR-10361 | G | 4 | 3 / 1 | 86.9 | 85.4 | -1.49 | -1.7 |
| EMPIAR-10361 | G | 8 | 3 / 2 | 48.2 | 47.5 | -0.73 | -1.5 |
| EMPIAR-10361 | L | 1 | 3 / 2 | 282.3 | 294.0 | 11.61 | 4.1 |
| EMPIAR-10361 | L | 4 | 2 / 2 | 139.0 | 139.3 | 0.27 | 0.2 |
| EMPIAR-10361 | L | 8 | 3 / 2 | 77.2 | 76.7 | -0.52 | -0.7 |
| EMPIAR-10641 | G | 1 | 3 / 2 | 208.2 | 202.8 | -5.37 | -2.6 |
| EMPIAR-10641 | G | 4 | 3 / 2 | 101.0 | 99.7 | -1.30 | -1.3 |
| EMPIAR-10641 | G | 8 | 3 / 2 | 54.5 | 53.8 | -0.70 | -1.3 |
| EMPIAR-10641 | L | 1 | 3 / 2 | 341.0 | 333.3 | -7.76 | -2.3 |
| EMPIAR-10641 | L | 4 | 3 / 2 | 160.8 | 164.7 | 3.91 | 2.4 |
| EMPIAR-10641 | L | 8 | 3 / 1 | 88.8 | 89.3 | 0.47 | 0.5 |
| EMPIAR-10441 | G | 1 | 3 / 1 | 342.9 | 336.1 | -6.80 | -2.0 |
| EMPIAR-10441 | G | 8 | 3 / 1 | 88.3 | 87.9 | -0.46 | -0.5 |
| EMPIAR-10441 | L | 8 | 3 / 2 | 147.5 | 151.7 | 4.22 | 2.9 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 1 | 3 / 1 | 121.8 | 123.7 | 1.97 | 1.6 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 4 | 3 / 2 | 55.2 | 54.6 | -0.63 | -1.1 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 8 | 3 / 2 | 31.0 | 30.8 | -0.21 | -0.7 |
| EMPIAR-10474 Falcon3 (58 fr) | L | 1 | 3 / 2 | 203.4 | 204.0 | 0.55 | 0.3 |
| EMPIAR-10474 Falcon3 (58 fr) | L | 4 | 3 / 2 | 93.0 | 92.6 | -0.39 | -0.4 |
| EMPIAR-10474 Falcon3 (58 fr) | L | 8 | 3 / 2 | 51.5 | 51.1 | -0.36 | -0.7 |
| EMPIAR-10474 Falcon4 (144 fr) | G | 1 | 3 / 1 | 306.7 | 307.9 | 1.20 | 0.4 |
| EMPIAR-10474 Falcon4 (144 fr) | G | 8 | 3 / 1 | 72.9 | 70.8 | -2.12 | -2.9 |
| EMPIAR-10474 Falcon4 (144 fr) | L | 1 | 3 / 1 | 524.0 | 522.0 | -2.05 | -0.4 |
| EMPIAR-10474 Falcon4 (144 fr) | L | 8 | 3 / 1 | 119.7 | 121.5 | 1.79 | 1.5 |
| EMPIAR-12963 | G | 1 | 3 / 2 | 42.8 | 43.4 | 0.60 | 1.4 |
| EMPIAR-12963 | G | 4 | 3 / 2 | 19.2 | 20.3 | 1.13 | 5.9 |
| EMPIAR-12963 | G | 8 | 3 / 2 | 11.6 | 11.4 | -0.21 | -1.9 |
| EMPIAR-12963 | L | 1 | 3 / 2 | 71.9 | 73.6 | 1.74 | 2.4 |
| EMPIAR-12963 | L | 4 | 3 / 2 | 33.5 | 33.3 | -0.20 | -0.6 |
| EMPIAR-12963 | L | 8 | 3 / 2 | 18.8 | 18.8 | -0.00 | -0.0 |
| EMPIAR-10164 tilt series (8 fr) | G | 1 | 2 / 2 | 84.7 | 86.8 | 2.10 | 2.5 |
| EMPIAR-10164 tilt series (8 fr) | G | 4 | 3 / 2 | 37.8 | 37.9 | 0.06 | 0.2 |
| EMPIAR-10164 tilt series (8 fr) | G | 8 | 3 / 2 | 21.2 | 21.0 | -0.22 | -1.0 |
| EMPIAR-10164 tilt series (8 fr) | L | 1 | 3 / 2 | 139.4 | 140.5 | 1.04 | 0.7 |
| EMPIAR-10164 tilt series (8 fr) | L | 4 | 3 / 2 | 64.3 | 67.1 | 2.82 | 4.4 |
| EMPIAR-10164 tilt series (8 fr) | L | 8 | 3 / 2 | 33.4 | 33.9 | 0.55 | 1.7 |
| EMPIAR-10216 apoferritin (59 fr) | G | 1 | 2 / 2 | 105.1 | 105.2 | 0.11 | 0.1 |
| EMPIAR-10216 apoferritin (59 fr) | G | 4 | 3 / 2 | 47.7 | 47.3 | -0.40 | -0.8 |
| EMPIAR-10216 apoferritin (59 fr) | G | 8 | 3 / 2 | 26.3 | 26.0 | -0.33 | -1.3 |
| EMPIAR-10216 apoferritin (59 fr) | L | 1 | 3 / 1 | 183.2 | 200.9 | 17.74 | 9.7 |
| EMPIAR-10216 apoferritin (59 fr) | L | 4 | 3 / 2 | 83.0 | 83.4 | 0.43 | 0.5 |
| EMPIAR-10216 apoferritin (59 fr) | L | 8 | 3 / 1 | 47.0 | 46.9 | -0.08 | -0.2 |

### Time outside the per-movie stages (profiled runs): process wall minus the sum of movie walls (s)

Process start, option and STAR parsing, gain read where not in a movie, the dataset report and exit. Median over profiled runs.

| family | G j1 | G j8 | L j1 | L j8 | L j8 as % of run |
|---|---:|---:|---:|---:|---:|
| RELION tutorial | 0.29 | 0.23 | 0.29 | 0.25 | 1.3 |
| EMPIAR-10028 | 0.27 | 0.23 | 0.28 | 0.22 | 1.7 |
| EMPIAR-10361 | 0.33 | 0.20 | 0.31 | 0.27 | 0.4 |
| EMPIAR-10641 | 0.28 | 0.21 | 0.28 | 0.24 | 0.3 |
| EMPIAR-10441 | 0.35 | 0.30 | - | 0.36 | 0.2 |
| EMPIAR-10474 Falcon3 (58 fr) | 0.31 | 0.24 | 0.33 | 0.28 | 0.5 |
| EMPIAR-10474 Falcon4 (144 fr) | 0.28 | 0.20 | 0.35 | 0.27 | 0.2 |
| EMPIAR-12963 | 0.30 | 0.22 | 0.30 | 0.27 | 1.4 |
| EMPIAR-10164 tilt series (8 fr) | 0.33 | 0.27 | 0.33 | 0.28 | 0.8 |
| EMPIAR-10216 apoferritin (59 fr) | 0.27 | 0.23 | 0.40 | 0.27 | 0.6 |

### Top 3 stages (profiled; share of the movie wall, ms)

Movie 1 = first movie in the process; movie 2 = steady state. Median over profile repetitions.

| family | cell | n prof | movie | movie ms | top stage | 2nd | 3rd |
|---|---|---:|---|---:|---|---|---|
| RELION tutorial | L j1 | 2 | 1 | 43055 | dose weighting 36% (15657) | global ifft 22% (9657) | global fft 21% (8990) |
| RELION tutorial | L j1 | 2 | 2 | 41615 | dose weighting 37% (15374) | global ifft 23% (9475) | global fft 21% (8538) |
| RELION tutorial | L j8 | 2 | 1 | 9924 | dose weighting 34% (3411) | global ifft 22% (2145) | global fft 20% (1985) |
| RELION tutorial | L j8 | 2 | 2 | 9636 | dose weighting 35% (3338) | global ifft 22% (2166) | global fft 20% (1936) |
| RELION tutorial | G j8 | 2 | 1 | 5788 | dose weighting 47% (2720) | global fft 34% (1987) | global alignment 5% (302) |
| RELION tutorial | G j8 | 2 | 2 | 5560 | dose weighting 48% (2685) | global fft 35% (1940) | global alignment 5% (294) |
| EMPIAR-10028 | L j1 | 2 | 1 | 25940 | dose weighting 37% (9652) | global ifft 18% (4718) | global fft 17% (4284) |
| EMPIAR-10028 | L j1 | 2 | 2 | 25096 | dose weighting 38% (9448) | global ifft 18% (4599) | global fft 17% (4163) |
| EMPIAR-10028 | L j8 | 2 | 1 | 6345 | dose weighting 34% (2144) | global ifft 18% (1169) | global fft 17% (1091) |
| EMPIAR-10028 | L j8 | 2 | 2 | 6280 | dose weighting 33% (2102) | global ifft 19% (1174) | global fft 18% (1101) |
| EMPIAR-10028 | G j8 | 2 | 1 | 3592 | dose weighting 45% (1624) | global fft 31% (1098) | host read movie 10% (365) |
| EMPIAR-10028 | G j8 | 2 | 2 | 3466 | dose weighting 45% (1571) | global fft 32% (1098) | host read movie 10% (362) |
| EMPIAR-10361 | L j1 | 2 | 1 | 151358 | dose weighting 40% (59825) | global fft 20% (30157) | global ifft 20% (29621) |
| EMPIAR-10361 | L j1 | 2 | 2 | 142281 | dose weighting 39% (55583) | global fft 21% (29460) | global ifft 19% (26739) |
| EMPIAR-10361 | L j8 | 2 | 1 | 38023 | dose weighting 34% (12887) | global fft 24% (8980) | global ifft 21% (8167) |
| EMPIAR-10361 | L j8 | 2 | 2 | 38372 | dose weighting 36% (13706) | global fft 23% (8710) | global ifft 21% (8148) |
| EMPIAR-10361 | G j8 | 2 | 1 | 23761 | dose weighting 46% (10894) | global fft 38% (8921) | host read movie 7% (1553) |
| EMPIAR-10361 | G j8 | 2 | 2 | 23491 | dose weighting 46% (10707) | global fft 38% (8943) | host read movie 7% (1554) |
| EMPIAR-10641 | L j1 | 2 | 1 | 158951 | dose weighting 32% (50700) | global ifft 23% (36021) | global fft 22% (35003) |
| EMPIAR-10641 | L j1 | 2 | 2 | 174024 | dose weighting 41% (70798) | global ifft 20% (33942) | global fft 19% (33842) |
| EMPIAR-10641 | L j8 | 1 | 1 | 42544 | dose weighting 27% (11297) | global ifft 25% (10494) | global fft 25% (10443) |
| EMPIAR-10641 | L j8 | 1 | 2 | 46522 | dose weighting 35% (16088) | global ifft 22% (10389) | global fft 22% (10155) |
| EMPIAR-10641 | G j8 | 2 | 1 | 27081 | dose weighting 47% (12756) | global fft 38% (10341) | global alignment 5% (1420) |
| EMPIAR-10641 | G j8 | 2 | 2 | 26545 | dose weighting 48% (12823) | global fft 38% (10041) | global alignment 5% (1394) |
| EMPIAR-10441 | L j8 | 2 | 1 | 151392 | dose weighting 34% (51187) | global ifft 23% (35257) | global fft 22% (33655) |
| EMPIAR-10441 | G j8 | 1 | 1 | 87565 | dose weighting 47% (41030) | global fft 37% (32415) | global alignment 7% (5862) |
| EMPIAR-10474 Falcon3 (58 fr) | L j1 | 2 | 1 | 105045 | dose weighting 35% (37114) | global ifft 17% (17382) | patch alignment 15% (15667) |
| EMPIAR-10474 Falcon3 (58 fr) | L j1 | 2 | 2 | 98609 | dose weighting 37% (36409) | global ifft 17% (16796) | global fft 15% (15095) |
| EMPIAR-10474 Falcon3 (58 fr) | L j8 | 2 | 1 | 25921 | dose weighting 30% (7680) | global ifft 17% (4327) | patch alignment 16% (4083) |
| EMPIAR-10474 Falcon3 (58 fr) | L j8 | 2 | 2 | 24946 | dose weighting 31% (7609) | global ifft 17% (4312) | global fft 16% (3972) |
| EMPIAR-10474 Falcon3 (58 fr) | G j8 | 2 | 1 | 15665 | dose weighting 37% (5784) | global fft 26% (4032) | host read movie 20% (3155) |
| EMPIAR-10474 Falcon3 (58 fr) | G j8 | 2 | 2 | 14924 | dose weighting 39% (5788) | global fft 27% (3976) | host read movie 21% (3105) |
| EMPIAR-10474 Falcon4 (144 fr) | L j1 | 1 | 1 | 261821 | dose weighting 41% (106158) | global ifft 16% (41479) | global fft 14% (37652) |
| EMPIAR-10474 Falcon4 (144 fr) | L j1 | 1 | 2 | 259795 | dose weighting 41% (106655) | global ifft 16% (41882) | patch alignment 14% (37438) |
| EMPIAR-10474 Falcon4 (144 fr) | L j8 | 1 | 1 | 60281 | dose weighting 32% (19342) | global ifft 17% (10365) | global fft 16% (9663) |
| EMPIAR-10474 Falcon4 (144 fr) | L j8 | 1 | 2 | 60976 | dose weighting 33% (20338) | global ifft 17% (10211) | global fft 16% (9616) |
| EMPIAR-10474 Falcon4 (144 fr) | G j8 | 1 | 1 | 35151 | dose weighting 40% (13992) | global fft 27% (9518) | host read movie 22% (7854) |
| EMPIAR-10474 Falcon4 (144 fr) | G j8 | 1 | 2 | 35432 | dose weighting 40% (14115) | global fft 27% (9676) | host read movie 22% (7912) |
| EMPIAR-12963 | L j1 | 2 | 1 | 73320 | dose weighting 35% (25397) | global ifft 17% (12344) | patch alignment 16% (11683) |
| EMPIAR-12963 | L j8 | 2 | 1 | 18569 | dose weighting 30% (5527) | patch alignment 16% (3055) | global ifft 16% (3050) |
| EMPIAR-12963 | G j8 | 2 | 1 | 11167 | dose weighting 37% (4163) | global fft 26% (2891) | host read movie 22% (2480) |
| EMPIAR-10164 tilt series (8 fr) | L j1 | 2 | 1 | 71027 | dose weighting 36% (25553) | global ifft 24% (17319) | global fft 23% (16324) |
| EMPIAR-10164 tilt series (8 fr) | L j1 | 2 | 2 | 69102 | dose weighting 37% (25732) | global ifft 24% (16844) | global fft 22% (15456) |
| EMPIAR-10164 tilt series (8 fr) | L j8 | 2 | 1 | 17150 | dose weighting 34% (5823) | global ifft 23% (3967) | global fft 22% (3783) |
| EMPIAR-10164 tilt series (8 fr) | L j8 | 2 | 2 | 16505 | dose weighting 34% (5539) | global ifft 24% (3937) | global fft 23% (3723) |
| EMPIAR-10164 tilt series (8 fr) | G j8 | 2 | 1 | 10599 | dose weighting 48% (5077) | global fft 37% (3942) | movie teardown 4% (433) |
| EMPIAR-10164 tilt series (8 fr) | G j8 | 2 | 2 | 10107 | dose weighting 48% (4886) | global fft 38% (3848) | movie teardown 4% (362) |
| EMPIAR-10216 apoferritin (59 fr) | L j1 | 1 | 1 | 94759 | dose weighting 39% (37369) | global ifft 18% (17251) | patch alignment 18% (17223) |
| EMPIAR-10216 apoferritin (59 fr) | L j1 | 1 | 2 | 105758 | dose weighting 31% (32873) | patch alignment 27% (28366) | global ifft 18% (19050) |
| EMPIAR-10216 apoferritin (59 fr) | L j8 | 1 | 1 | 23999 | dose weighting 34% (8116) | patch alignment 19% (4658) | global ifft 19% (4540) |
| EMPIAR-10216 apoferritin (59 fr) | L j8 | 1 | 2 | 22610 | dose weighting 26% (5829) | patch alignment 23% (5217) | global ifft 20% (4450) |
| EMPIAR-10216 apoferritin (59 fr) | G j8 | 2 | 1 | 12663 | dose weighting 48% (6116) | global fft 34% (4289) | host read movie 6% (767) |
| EMPIAR-10216 apoferritin (59 fr) | G j8 | 2 | 2 | 13110 | dose weighting 46% (5988) | global fft 31% (4084) | global alignment 11% (1429) |

### Cost per megapixel-frame (ms per Mpx-frame), steady movie from the profile

Mpx-frame = nx*ny*frames/1e6 (EER: grouped frames). Lower is cheaper per unit of data. Movie 2 where the run has two movies, else movie 1.

| family | Mpx-frame | G j1 | G j8 | L j1 | L j4 | L j8 |
|---|---:|---:|---:|---:|---:|---:|
| RELION tutorial | 342 | 70.9 | 16.3 | 121.8 | 53.4 | 28.2 |
| EMPIAR-10028 | 268 | 52.6 | 12.9 | 93.5 | 42.7 | 23.4 |
| EMPIAR-10361 | 1461 | 63.6 | 16.1 | 97.4 | 47.3 | 26.3 |
| EMPIAR-10641 | 1650 | 60.9 | 16.1 | 105.5 | 51.9 | 28.2 |
| EMPIAR-10441 | 4714 | 71.2 | 18.6 | - | - | 32.1 |
| EMPIAR-10474 Falcon3 (58 fr) | 973 | 59.6 | 15.3 | 101.3 | 46.8 | 25.6 |
| EMPIAR-10474 Falcon4 (144 fr) | 2416 | 62.4 | 14.7 | 107.5 | - | 25.2 |
| EMPIAR-12963 | 654 | 65.8 | 17.1 | 112.1 | 50.5 | 28.4 |
| EMPIAR-10164 tilt series (8 fr) | 456 | 91.4 | 22.2 | 151.7 | 72.6 | 36.2 |
| EMPIAR-10216 apoferritin (59 fr) | 990 | 53.8 | 13.2 | 106.8 | 40.7 | 22.8 |

### Sub-stage shares at j1 (steady movie; % of the movie wall)

Sub-stages come from the RCTIC/RCTOC markers on the main thread, so they are complete only at j1. DW = dose weighting; DW iFFT is the per-frame inverse FFT of the weighted frames; interpolation is the real-space sum.

| family | cfg | n prof | movie s | DW weight | DW iFFT | interpolation | patch FFT | read movie |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| RELION tutorial | G | 2 | 24.2 | 11.6 | 39.6 | 0.5 | 0.0 | 5.7 |
| RELION tutorial | L | 2 | 41.6 | 7.0 | 21.4 | 8.4 | 9.9 | 3.8 |
| EMPIAR-10028 | G | 2 | 14.1 | 17.2 | 32.6 | 0.6 | 0.0 | 12.9 |
| EMPIAR-10028 | L | 2 | 25.1 | 10.0 | 16.5 | 11.1 | 13.0 | 7.2 |
| EMPIAR-10361 | G | 2 | 93.0 | 15.0 | 36.4 | 0.9 | 0.0 | 9.2 |
| EMPIAR-10361 | L | 2 | 142.3 | 10.3 | 17.7 | 11.0 | 8.2 | 6.0 |
| EMPIAR-10641 | G | 2 | 100.4 | 18.3 | 34.4 | 0.8 | 0.0 | 5.3 |
| EMPIAR-10641 | L | 2 | 174.0 | 11.4 | 19.0 | 10.3 | 7.5 | 3.1 |
| EMPIAR-10441 | G | 1 | 335.7 | 12.3 | 37.3 | 0.4 | 0.0 | 5.1 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 1 | 58.0 | 17.7 | 28.7 | 0.8 | 0.0 | 18.1 |
| EMPIAR-10474 Falcon3 (58 fr) | L | 2 | 98.6 | 11.2 | 15.3 | 10.4 | 12.1 | 10.5 |
| EMPIAR-10474 Falcon4 (144 fr) | G | 1 | 150.8 | 24.0 | 27.7 | 0.8 | 0.0 | 16.8 |
| EMPIAR-10474 Falcon4 (144 fr) | L | 1 | 259.8 | 14.6 | 16.2 | 10.2 | 11.5 | 10.3 |
| EMPIAR-12963 | G | 2 | 43.1 | 16.5 | 28.5 | 0.6 | 0.0 | 18.8 |
| EMPIAR-12963 | L | 2 | 73.3 | 10.4 | 14.8 | 9.4 | 11.6 | 11.5 |
| EMPIAR-10164 tilt series (8 fr) | G | 2 | 41.6 | 9.5 | 41.4 | 0.5 | 0.0 | 3.3 |
| EMPIAR-10164 tilt series (8 fr) | L | 2 | 69.1 | 6.2 | 24.1 | 6.8 | 9.2 | 1.9 |
| EMPIAR-10216 apoferritin (59 fr) | G | 2 | 53.3 | 20.1 | 32.1 | 0.6 | 0.0 | 6.4 |
| EMPIAR-10216 apoferritin (59 fr) | L | 1 | 105.8 | 11.7 | 18.9 | 0.4 | 18.2 | 3.2 |

### Stage cost per megapixel-frame, L j1, steady movie (ms per Mpx-frame)

Stages that reach 2% of a movie in any family. Rows are families; the same code and options, so differences are shape or format.

| family | dose weighting | global ifft | global fft | patch alignment | host read movie | global alignment |
|---|---:|---:|---:|---:|---:|---:|
| RELION tutorial | 45.0 | 27.7 | 25.0 | 14.8 | 4.6 | 3.1 |
| EMPIAR-10028 | 35.2 | 17.1 | 15.5 | 15.0 | 6.7 | 2.2 |
| EMPIAR-10361 | 38.0 | 18.3 | 20.2 | 10.7 | 5.8 | 3.2 |
| EMPIAR-10641 | 42.9 | 20.6 | 20.5 | 13.7 | 3.3 | 3.3 |
| EMPIAR-10474 Falcon3 (58 fr) | 37.4 | 17.3 | 15.5 | 15.3 | 10.7 | 3.4 |
| EMPIAR-10474 Falcon4 (144 fr) | 44.1 | 17.3 | 15.4 | 15.5 | 11.0 | 2.8 |
| EMPIAR-12963 | 38.8 | 18.9 | 17.1 | 17.9 | 12.9 | 3.4 |
| EMPIAR-10164 tilt series (8 fr) | 56.5 | 37.0 | 33.9 | 16.6 | 2.9 | 2.4 |
| EMPIAR-10216 apoferritin (59 fr) | 33.2 | 19.2 | 15.4 | 28.7 | 3.4 | 5.4 |

### Run filtering

283 measured run records. 261 usable arms are used in the tables above; 22 records are excluded (rules in `tools/runfilter.py`: foreign load or settle timeout on the lane, or CPU time more than 15% above the cell minimum). Arms with no usable record: 19.

| family | cfg | j | kind | rep | wall s | reason |
|---|---|---:|---|---:|---:|---|
| e10028 | L | 1 | unprof | 1 | 58.9 | cpu time +17% over cell minimum |
| e10164 | G | 1 | unprof | 1 | 97.1 | cpu time +19% over cell minimum |
| e10216 | G | 1 | unprof | 1 | 125.9 | cpu time +21% over cell minimum |
| e10216 | L | 1 | prof | 1 | 235.4 | cpu time +29% over cell minimum |
| e10216 | L | 8 | prof | 1 | 46.4 | foreign load or settle timeout |
| e10361 | G | 1 | unprof | 2 | 202.1 | cpu time +17% over cell minimum |
| e10361 | G | 4 | prof | 0 | 85.2 | foreign load or settle timeout |
| e10361 | L | 4 | unprof | 2 | 149.0 | foreign load or settle timeout |
| e10441 | G | 1 | prof | 1 | 408.4 | cpu time +23% over cell minimum |
| e10441 | G | 8 | prof | 0 | 88.4 | foreign load or settle timeout |
| e10441 | L | 1 | prof | 0 | 717.7 | cpu time +30% over cell minimum |
| e10441 | L | 1 | prof | 1 | 651.0 | cpu time +18% over cell minimum |
| e10474f3 | G | 1 | prof | 0 | 143.0 | cpu time +18% over cell minimum |
| e10474f4 | G | 1 | prof | 1 | 365.1 | cpu time +19% over cell minimum |
| e10474f4 | G | 8 | prof | 1 | 71.9 | foreign load or settle timeout |
| e10474f4 | L | 1 | prof | 1 | 663.2 | cpu time +27% over cell minimum |
| e10474f4 | L | 8 | prof | 1 | 120.9 | foreign load or settle timeout |
| e10641 | L | 8 | prof | 0 | 89.8 | foreign load or settle timeout |
| tutorial | G | 1 | prof | 0 | 64.8 | cpu time +31% over cell minimum |
| tutorial | G | 1 | prof | 0 | 63.8 | foreign load or settle timeout |
| tutorial | L | 8 | unprof | 0 | 23.2 | foreign load or settle timeout |
| tutorial | L | 8 | unprof | 0 | 28.7 | foreign load or settle timeout |

Sensitivity of the unprofiled medians to the exclusions: using every ok record instead of the usable ones changes a cell median by at most 8.4% (tutorial/L/8); the next largest are 3.7% (e10164/G/1), 2.0% (e10361/G/1), 1.3% (e10028/L/1).

Cells below the planned 3 unprofiled / 2 profiled usable repetitions: 18 of 56. tutorial L j8 (2 unprof, 2 prof); e10028 L j1 (2 unprof, 2 prof); e10361 G j1 (2 unprof, 2 prof); e10361 G j4 (3 unprof, 1 prof); e10361 L j4 (2 unprof, 2 prof); e10641 L j8 (3 unprof, 1 prof); e10441 G j1 (3 unprof, 1 prof); e10441 G j8 (3 unprof, 1 prof); e10441 L j1 (3 unprof, 0 prof); e10474f3 G j1 (3 unprof, 1 prof); e10474f4 G j1 (3 unprof, 1 prof); e10474f4 G j8 (3 unprof, 1 prof); e10474f4 L j1 (3 unprof, 1 prof); e10474f4 L j8 (3 unprof, 1 prof); e10164 G j1 (2 unprof, 2 prof); e10216 G j1 (2 unprof, 2 prof); e10216 L j1 (3 unprof, 1 prof); e10216 L j8 (3 unprof, 1 prof)


## Reading the tables

**Shape versus format (L j1, ms per Mpx-frame, steady movie).** The tutorial costs 122 ms; the 4096² families cost 93 (float32 MRC), 107 (int16 MRC) and 101–112 (EER); the 5760×4092 LZW families 97–106; the 7420×7676 tilt series 152. The difference is almost entirely FFT cost, which depends on the frame size and not on the container: global FFT is 15.4–17.1 ms/Mpx-frame for every 4096² family whatever its format (EER, float32 MRC, int16 MRC), 20.2–20.5 for 5760×4092, 25.0 for 3838×3710 and 33.9 for 7420×7676 (7676 = 2²·19·101 and 3838 = 2·19·101 both contain large primes). Decode shows the format effect directly: `host read movie` is 3.3–5.8 ms/Mpx-frame for Deflate and LZW TIFF (no LZW penalty on CPU), 6.7 for float32 MRC (4 bytes per sample), 2.9–3.4 for the 8- and 16-bit MRC, and 10.7–12.9 for EER. The share of dose weighting that is weight calculation grows with frame count (9.5% of a G movie at 8 frames, 24% at 144 frames); the per-frame inverse FFT share (DW iFFT) is 28–41% of a G movie and is lowest where weight calculation is highest.

**Content effects.** Patch alignment varies with content: EMPIAR-10216 movie 2 spends 27% of its time in patch alignment against 18% for movie 1, and its real-space interpolation stage is 0.4 s against 10 s for movie 1, so the two movies take different motion-model paths (not investigated). Use more than one movie when a patch-alignment change is under test.

**Memory.** Peak RSS at j1 is about two full-frame stacks: the real frames and the Fourier frames coexist through dose weighting. It grows from j1 to j8 by 1–9% for the larger families, 16–23% for the tutorial and EMPIAR-10028, and 43% for the 8-frame tilt series (3.9 to 5.6 GiB), where per-thread scratch is large next to a 3.9 GiB working set. Minor faults are 3.0–56 million per run and system time is 8–24% of CPU time (higher at j1 and in G, where the run is shorter).

## Ranked performance ideas

Benefit is a share of the CPU wall time for the family or configuration named. "Measured" means the benefit comes from a measurement in this report or in the cited PR. "Estimate" is calculated from the stage tables here, not run.

| # | idea | where it applies | expected benefit | risk | status |
|---|---|---|---|---|---|
| 1 | **G only: sum the weighted frames in Fourier space and run one inverse FFT**, instead of one per frame. With no local fit the model is null and the real-space sum is plain addition, so the transforms are linear. | G (no `--patch_*`, no `--save_noDW`, no even/odd). DW iFFT is 28–41% of a G movie at j1 (tutorial 13.4 of 32.8 s). | About 90–95% of DW iFFT: **26–39% of G wall** | Medium: float summation order changes, so products are not byte-identical to main and the RELION parity baseline needs sign-off. #187 removes a copy in the same stage but not the transform count. | Estimate |
| 2 | **Huge pages on THP-`madvise` hosts** (`GLIBC_TUNABLES=glibc.malloc.hugetlb=1`) | All families on cpu64. System time is 8–24% of CPU time and there are 3.0–56 M minor faults per run. | #188 measured 452 s to 371 s (−18%) on the 24-movie tutorial batch | Very low (deployment setting) | Covered by #188 |
| 3 | **Run several j1 processes instead of one j8 process** at a fixed 8 CPUs, or bind threads. j8 efficiency is 46–55% for every family. | All families; the limit is RAM: 8 × j1 RSS is 22 GiB (tutorial) to 290 GiB (EMPIAR-10441, which exceeds the 226 GB host, so at most 6 processes). | At most 8/3.9 ≈ **2.0× throughput** from the measured j8 speedup; #184 measured 1.33× at 4 CPUs on a small fixture | Low (no product change); memory-bound for 10441 and 144-frame EER | Estimate (calculated from j1 and j8), #184 covers the mechanism |
| 4 | **Avoid slow FFT sizes** (pad or crop to a smooth size) | 3838×3710 and 7420×7676: FFT cost per Mpx-frame is 1.6× and 2.2× the 4096² value. | Upper bound 16–25% of L wall (global FFT and iFFT at the 4096² rate; DW iFFT would add to it); net 10–15% after the extra pixels | High: changes numerics and the FFT geometry; the CUDA counterpart `--fft_size_policy fast` (#171) fails its backend gate | Estimate |
| 5 | **Patch work in L**: plan reuse, phase-update cropping, plan cache | Patch alignment is 10–23% of an L movie and patch FFT 7–18% at j1. | See the PRs' own measurements | Low to medium | Covered by #177, #183, #187 |
| 6 | **Dose-weight calculation** (symmetric weights in tiles) | DW weight is 7–15% of an L movie and 10–24% of a G movie; largest for 144 frames. | See #179 | Low | Covered by #179 |
| 7 | **Overlap EER decode with the first global FFT** (decode and transform frame groups as they arrive) | EER: read is 10–12% of an L movie and 17–19% of a G movie at j1, 20–22% of a G movie at j8; read scales only about 3.3× from j1 to j8. | Up to about half of the read time: **5–6% of L, 8–11% of G** | Low to medium (ordering, memory) | Estimate |
| 8 | **Peak RSS**: stream the unweighted stack | EMPIAR-10441 (36 GiB) and the 144-frame EER (21 GiB) at j1 | #178 measured −29% peak RSS on the tutorial (dose + noDW + even/odd option set, j4) | Low | Covered by #178 |
| 9 | **Binned variant of the super-resolution families** (`--bin_factor 2`, `--early_binning`) | 10441 and 10164 are super-resolution frames; production use is normally binned, which cuts memory and FFT work about 4×. | Not measured: these runs are unbinned by declaration | n/a | A corpus option to add, not an optimisation |

Measured no-ops on CPU: LZW decode (3–6 ms/Mpx-frame, the same as Deflate, at most 6% of a movie) and per-process or per-movie fixed costs (0.2–0.4 s per run). nvTIFF LZW (#141, #152) is a GPU-ingest matter; it does not pay on this backend. EER decode is the only input path worth a CPU change, at the sizes in idea 7.

## Recommended one-movie subset

One movie per family for future performance PRs, run next to the tutorial. Options are those in `../corpus.md`; the file is relative to the corpus data root.

| family | movie | L j8 wall (s, median) | G j8 wall (s, median) |
|---|---|---:|---:|
| tutorial | `tutorial/Movies/20170629_00026_frameImage.tiff` | 10.0 | 5.8 |
| EMPIAR-10028 | `…/Micrographs_part1/031_movie.mrcs` | 6.5 | 3.7 |
| EMPIAR-10361 | `…/PS.18.2.4_CTEM_103-12_0007_Jan20_08.57.33.tif` | 38.6 | 24.1 |
| EMPIAR-10641 | `…/Dataset/HM70-1_10-A-002_0002_Oct28_23.00.41.tif` | 44.4 | 27.3 |
| EMPIAR-10441 | `…/frames/20May09_3A-3_109-21_0003.tif` | 147.5 | 88.3 |
| EMPIAR-10474 Falcon3 | `…/2019-06-21_20-39-45.801_eer_data_4096x4096.eer` | 25.8 | 15.5 |
| EMPIAR-10474 Falcon4 | `…/FoilHole_10919949_…_001116_Fractions.mrc.eer` | 59.9 | 36.5 |
| EMPIAR-12963 | `…/FoilHole_4674725_Data_4659374_4659376_20230406_014501_EER.eer` | 18.8 | 11.6 |
| EMPIAR-10164 | `…/frames/TS_01_000_0.0.mrc` (linked `.mrcs`) | 16.7 | 10.6 |
| EMPIAR-10216 | `…/FoilHole_14961495_…_1739_Fractions.mrc` (linked `.mrcs`) | 23.5 | 13.2 |

The wall figures are per movie from the two-movie runs (the 10441 and 12963 runs have one movie). All ten movies at j8 take about 6.5 min in L and 4 min in G. For a quicker set that still covers every shape and decode path, use the tutorial, EMPIAR-10361, EMPIAR-10441 (or the 144-frame EER), EMPIAR-10164 and EMPIAR-10216. Use movie 1 of EMPIAR-10216 (it takes the usual motion-model path; see above). A PR that changes only one backend needs the L runs for patch changes and the G runs for global changes.

## Limitations

- **Shared host.** cpu64 is shared. Besides the permanent `ctffind` processes (cpus 26 and 32 at the start), other users' `refmac5` jobs ran on the host during much of the matrix, and in the repair phase they sat on cpus 2 and 3 for hours while `ctffind` migrated onto cpu 0. All 293 runs held the benchmark lock, so no other timed MotionCorr run overlapped, but unlocked jobs did. Lane-only `/proc/stat` deltas missed part of the effect: a run with 0.0 foreign core on its own lane took 28% more CPU time when a `refmac5` job ran on a neighbouring core (tutorial G j1: 63.8 s against 49.6 s). The CPU-time rule above removes such runs. The retained medians change by at most 8.4% (tutorial L j8) and usually under 2% if every record is used instead (see the sensitivity line below the tables), but the tables are still not a clean-host measurement.
- **Repetitions.** The planned 3 unprofiled and 2 profiled repetitions per cell were taken, but after exclusion 18 of 56 cells have fewer (named below the tables). Stage breakdowns and profile overhead for those cells rest on one profiled run (EMPIAR-10441 L j1 has none, so its stage row is missing), and a single profiled record can be off by several percent.
- **Placement.** Threads are not bound inside the cpuset (declared). Binding would change the j4 and j8 numbers and was not tested here.
- **THP is `madvise`.** SCARF is `always`, and the effect on frame allocation is large, so these times do not transfer to SCARF. No `GLIBC_TUNABLES` were set (see idea 2).
- **Warm page cache, local disk.** Cold-cache or network-storage reads are not measured.
- **Sub-stage markers inside OpenMP regions** cover the main thread only, so sub-stage shares are given at j1 only.
- **Timings and memory only.** Correctness and scientific equivalence are not claimed. Output hashes of the kept runs are retained for later comparison; MRC headers and logs carry timestamps, so whole-file hashes will differ between runs and the payload hash is the comparable one.
- **Placeholders:** dose per frame (except 10361, 10441, 12963 and the tutorial), voltage for several accessions, and default gain orientation are stated in `../corpus.md`. Dose weighting cost does not depend on them.
- The tutorial L j8 kept output tree comes from a run that was flagged for foreign load; its timings are excluded, the product hashes are unaffected.
