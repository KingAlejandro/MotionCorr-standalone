### 1. Unprofiled wall, CPU and memory (median [min-max] over repetitions)

Process wall for the whole run (process start, all movies, dataset report, exit). Default `--ingest auto` unless marked. CPU = user+sys of the process tree. VRAM proc = NVML per-process peak (includes the CUDA context); sampled at ~10 ms, so a lower bound.

| family | movies | cfg | n | wall s | s/movie | CPU s | CPU/wall | RSS GiB | VRAM proc MiB | VRAM dev delta MiB | minflt (M) | majflt |
|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RELION tutorial | 2 | G | 5 | 1.41 [1.35-1.42] | 0.70 | 1.7 | 1.23 | 0.35 | 3260 | 3269 | 0.10 | 12 |
| RELION tutorial | 2 | L | 5 | 1.43 [1.41-1.51] | 0.72 | 1.7 | 1.20 | 0.36 | 3362 | 3371 | 0.10 | 0 |
| RELION tutorial `--ingest nvcomp` | 2 | G | 5 | 1.36 [1.34-1.44] | 0.68 | 1.6 | 1.20 | 0.35 | 3260 | 3269 | 0.10 | 0 |
| RELION tutorial `--ingest nvcomp` | 2 | L | 5 | 1.49 [1.43-1.51] | 0.74 | 1.8 | 1.23 | 0.36 | 3362 | 3371 | 0.10 | 14 |
| EMPIAR-10028 | 2 | G | 5 | 2.20 [2.20-2.38] | 1.10 | 7.0 | 3.16 | 1.61 | 2672 | 2681 | 1.15 | 0 |
| EMPIAR-10028 | 2 | L | 5 | 2.32 [2.23-2.40] | 1.16 | 7.0 | 3.04 | 1.61 | 2736 | 2745 | 1.16 | 3 |
| EMPIAR-10361 | 2 | G | 5 | 4.90 [4.86-4.97] | 2.45 | 23.8 | 4.86 | 1.66 | 11872 | 11881 | 0.87 | 0 |
| EMPIAR-10361 | 2 | L | 5 | 5.18 [5.14-5.28] | 2.59 | 24.2 | 4.67 | 1.66 | 12632 | 12641 | 0.87 | 15 |
| EMPIAR-10641 | 2 | G | 5 | 3.90 [3.80-3.94] | 1.95 | 13.7 | 3.51 | 1.88 | 13400 | 13409 | 0.94 | 1 |
| EMPIAR-10641 | 2 | L | 5 | 29.82 [29.80-30.02] | 14.91 | 39.9 | 1.34 | 7.01 | 15034 | 15043 | 7.04 | 0 |
| EMPIAR-10441 | 1 | G | 5 | 6.85 [6.77-6.87] | 6.85 | 22.3 | 3.26 | 5.04 | 37924 | 37933 | 1.58 | 2 |
| EMPIAR-10441 | 1 | L | 5 | 7.14 [7.06-7.17] | 7.14 | 22.8 | 3.19 | 5.04 | 40266 | 40275 | 1.59 | 15 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 | G | 5 | 12.43 [12.35-12.51] | 6.22 | 56.2 | 4.52 | 5.04 | 8052 | 8061 | 2.84 | 0 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 | L | 5 | 14.21 [14.05-14.34] | 7.11 | 58.4 | 4.11 | 5.25 | 9026 | 9035 | 3.04 | 0 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 | G | 5 | 25.99 [25.68-26.13] | 12.99 | 129.7 | 4.99 | 12.00 | 19060 | 19069 | 6.81 | 0 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 | L | 5 | 26.40 [26.03-26.41] | 13.20 | 129.8 | 4.92 | 12.01 | 20446 | 20455 | 6.78 | 0 |
| EMPIAR-12963 | 1 | G | 5 | 5.07 [5.05-5.10] | 5.07 | 21.1 | 4.15 | 3.57 | 5680 | 5689 | 1.05 | 2 |
| EMPIAR-12963 | 1 | L | 5 | 5.80 [5.79-5.94] | 5.80 | 21.9 | 3.77 | 3.70 | 6316 | 6325 | 1.16 | 2 |
| EMPIAR-10164 tilt series (8 fr) | 2 | G | 5 | 3.01 [2.99-3.17] | 1.50 | 7.7 | 2.57 | 2.33 | 4568 | 4577 | 1.25 | 0 |
| EMPIAR-10164 tilt series (8 fr) | 2 | L | 5 | 3.16 [3.13-3.21] | 1.58 | 8.0 | 2.53 | 2.19 | 4568 | 4577 | 1.25 | 1 |
| EMPIAR-10216 apoferritin (59 fr) | 2 | G | 5 | 4.75 [4.73-4.88] | 2.38 | 15.2 | 3.21 | 3.97 | 8176 | 8185 | 3.03 | 16 |
| EMPIAR-10216 apoferritin (59 fr) | 2 | L | 5 | 12.80 [12.73-12.88] | 6.40 | 23.2 | 1.82 | 4.22 | 9172 | 9181 | 4.26 | 1 |

### 2. Ingest path that ran (`--ingest_witness`, every run of the family) and host decode

Steady = movie 2..6 of the six-row replay (labelled replay), config L. `host read movie` is the host decode/render/convert stage; the nvCOMP path has none (decode runs inside `session and device ingest`). Share = stage / steady movie wall. Share ex-retry removes `patch alignment` from the denominator for families with non-converging patches (section 8).

| family | witness (movies per path, all runs) | host read, movie 1 (ms) | session and device ingest, movie 1 (ms) | host read, steady (ms) | share of steady movie | share ex-retry | ingest group, steady (ms) | host read ms/Mpx |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| RELION tutorial | nvcomp: 34 | 0 | 301 | 0 | 0% | 0% | 40 | 0.00 |
| EMPIAR-10028 | float: 34 | 408 | 153 | 396 | 57% | 59% | 492 | 1.48 |
| EMPIAR-10361 | compact: 34 | 1400 | 165 | 1392 | 67% | 70% | 1546 | 0.95 |
| EMPIAR-10641 | compact: 34 | 704 | 164 | 701 | 4% | 33% | 878 | 0.42 |
| EMPIAR-10441 | compact: 26 | 2429 | 168 | 2614 | 54% | 57% | 3074 | 0.55 |
| EMPIAR-10474 Falcon3 (58 fr) | float: 34 | 4429 | 160 | 4382 | 61% | 76% | 4717 | 4.50 |
| EMPIAR-10474 Falcon4 (144 fr) | float: 34 | 10093 | 168 | 10022 | 78% | 79% | 10946 | 4.15 |
| EMPIAR-12963 | float: 26 | 3142 | 162 | 3099 | 68% | 80% | 3329 | 4.74 |
| EMPIAR-10164 tilt series (8 fr) | float: 34 | 324 | 166 | 336 | 33% | 35% | 494 | 0.74 |
| EMPIAR-10216 apoferritin (59 fr) | float: 34 | 989 | 156 | 958 | 26% | 50% | 1318 | 0.97 |

### 3. Per-movie time from `--profile`: first movie vs steady, config L (ms)

Two-movie families: movie 1 vs movie 2 (profiled, device timing on). Replay: movie 1 vs the median of movies 2-6 of a six-row replay of movie 1 (**replayed rows, not distinct inputs**). Fixed = process wall minus the sum of movie walls.

| family | source | first movie | steady movie | first - steady | fixed outside movies (s) | process wall (s) |
|---|---|---:|---:|---:|---:|---:|
| RELION tutorial | 2 distinct movies | 639 | 181 | 459 | 0.66 | 1.49 |
| RELION tutorial | replay x6 | 644 | 181 | 463 | 0.77 | 2.32 |
| EMPIAR-10028 | 2 distinct movies | 976 | 815 | 161 | 0.53 | 2.32 |
| EMPIAR-10028 | replay x6 | 959 | 700 | 259 | 0.67 | 5.17 |
| EMPIAR-10361 | 2 distinct movies | 2375 | 2100 | 275 | 0.68 | 5.14 |
| EMPIAR-10361 | replay x6 | 2405 | 2063 | 342 | 0.82 | 13.64 |
| EMPIAR-10641 | 2 distinct movies | 16580 | 12736 | 3844 | 0.60 | 29.93 |
| EMPIAR-10641 | replay x6 | 16605 | 15730 | 874 | 0.73 | 96.19 |
| EMPIAR-10441 | 2 distinct movies | 6079 | - | - | 1.02 | 7.10 |
| EMPIAR-10441 | replay x6 | 6070 | 4843 | 1227 | 1.25 | 31.17 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 distinct movies | 7725 | 5915 | 1810 | 0.61 | 14.24 |
| EMPIAR-10474 Falcon3 (58 fr) | replay x6 | 7664 | 7208 | 456 | 0.89 | 44.68 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 distinct movies | 12801 | 12601 | 201 | 0.68 | 26.09 |
| EMPIAR-10474 Falcon4 (144 fr) | replay x6 | 12951 | 12776 | 175 | 0.85 | 77.63 |
| EMPIAR-12963 | 2 distinct movies | 5253 | - | - | 0.54 | 5.79 |
| EMPIAR-12963 | replay x6 | 5326 | 4548 | 778 | 0.72 | 29.01 |
| EMPIAR-10164 tilt series (8 fr) | 2 distinct movies | 1464 | 1079 | 384 | 0.59 | 3.13 |
| EMPIAR-10164 tilt series (8 fr) | replay x6 | 1468 | 1005 | 463 | 0.75 | 7.31 |
| EMPIAR-10216 apoferritin (59 fr) | 2 distinct movies | 3923 | 8288 | -4365 | 0.57 | 12.82 |
| EMPIAR-10216 apoferritin (59 fr) | replay x6 | 3973 | 3639 | 334 | 0.76 | 22.90 |

### 4. Top stages, config L, steady movie (replay where available): ms and share of the movie

| family | steady movie ms | stage 1 | stage 2 | stage 3 | stage 4 | stage 5 |
|---|---:|---|---|---|---|---|
| RELION tutorial | 181 | dose weighting 44 (24%) | session and device ingest 39 (22%) | patch alignment 26 (15%) | global ifft 22 (12%) | global fft 22 (12%) |
| EMPIAR-10028 | 700 | host read movie 396 (57%) | movie teardown 130 (19%) | gain and sum 94 (13%) | dose weighting 28 (4%) | patch alignment 24 (3%) |
| EMPIAR-10361 | 2063 | host read movie 1392 (67%) | global fft 224 (11%) | gain and sum 151 (7%) | dose weighting 125 (6%) | patch alignment 70 (3%) |
| EMPIAR-10641 | 15730 | patch alignment 13634 (87%) | movie teardown 711 (5%) | host read movie 701 (4%) | global fft 248 (2%) | gain and sum 165 (1%) |
| EMPIAR-10441 | 4843 | host read movie 2614 (54%) | global fft 741 (15%) | gain and sum 457 (9%) | dose weighting 341 (7%) | patch alignment 223 (5%) |
| EMPIAR-10474 Falcon3 (58 fr) | 7208 | host read movie 4382 (61%) | patch alignment 1418 (20%) | movie teardown 591 (8%) | gain and sum 354 (5%) | fix defects 289 (4%) |
| EMPIAR-10474 Falcon4 (144 fr) | 12776 | host read movie 10022 (78%) | movie teardown 1398 (11%) | gain and sum 891 (7%) | dose weighting 138 (1%) | patch alignment 137 (1%) |
| EMPIAR-12963 | 4548 | host read movie 3099 (68%) | patch alignment 697 (15%) | movie teardown 405 (9%) | gain and sum 233 (5%) | dose weighting 42 (1%) |
| EMPIAR-10164 tilt series (8 fr) | 1005 | host read movie 336 (33%) | movie teardown 217 (22%) | gain and sum 156 (15%) | dose weighting 80 (8%) | fix defects 74 (7%) |
| EMPIAR-10216 apoferritin (59 fr) | 3639 | patch alignment 1712 (47%) | host read movie 958 (26%) | movie teardown 458 (13%) | gain and sum 341 (9%) | dose weighting 58 (2%) |

### 5. First-movie stages, config L (ms): what the first movie pays extra

| family | first movie ms | top stages (first movie) |
|---|---:|---|
| RELION tutorial | 644 | session and device ingest 301; read gain 106; dose weighting 77; hot pixels 71; patch alignment 27 |
| EMPIAR-10028 | 959 | host read movie 408; session and device ingest 153; movie teardown 124; gain and sum 96; hot pixels 65 |
| EMPIAR-10361 | 2405 | host read movie 1400; global fft 224; gain and sum 215; session and device ingest 165; dose weighting 147 |
| EMPIAR-10641 | 16605 | patch alignment 14041; movie teardown 750; host read movie 704; global fft 251; gain and sum 188 |
| EMPIAR-10441 | 6070 | host read movie 2429; global fft 748; read gain 633; gain and sum 568; dose weighting 531 |
| EMPIAR-10474 Falcon3 (58 fr) | 7664 | host read movie 4429; patch alignment 1482; movie teardown 597; gain and sum 428; fix defects 291 |
| EMPIAR-10474 Falcon4 (144 fr) | 12951 | host read movie 10093; movie teardown 1391; gain and sum 784; session and device ingest 168; dose weighting 153 |
| EMPIAR-12963 | 5326 | host read movie 3142; patch alignment 767; movie teardown 416; read gain 403; gain and sum 238 |
| EMPIAR-10164 tilt series (8 fr) | 1468 | host read movie 324; movie teardown 212; hot pixels 212; dose weighting 198; session and device ingest 166 |
| EMPIAR-10216 apoferritin (59 fr) | 3973 | patch alignment 1744; host read movie 989; movie teardown 472; gain and sum 364; session and device ingest 156 |

### 6. Cost per megapixel-frame (steady movie, ms per Mpx-frame)

Mpx-frame = nx*ny*frames/1e6 (EER: grouped frames). Steady movie from the replay when present, else movie 2. Lower is cheaper. `ingest` = ingest group stages.

| family | container | Mpx-frame/movie | G steady ms/Mpx | L steady ms/Mpx | L ingest ms/Mpx | L tutorial ratio |
|---|---|---:|---:|---:|---:|---:|
| RELION tutorial | 16-bit Adobe-Deflate TIFF | 342 | 0.4 | 0.5 | 0.1 | 1.00 |
| EMPIAR-10028 | float32 MRC (.mrcs) | 268 | 2.6 | 2.6 | 1.8 | 4.91 |
| EMPIAR-10361 | u8 LZW BigTIFF | 1461 | 1.4 | 1.4 | 1.1 | 2.66 |
| EMPIAR-10641 | u8 LZW BigTIFF | 1650 | 0.9 | 9.5 | 0.5 | 17.96 |
| EMPIAR-10441 | u8 LZW BigTIFF | 4714 | 1.0 | 1.0 | 0.7 | 1.94 |
| EMPIAR-10474 Falcon3 (58 fr) | EER (65001) | 973 | 6.0 | 7.4 | 4.8 | 13.96 |
| EMPIAR-10474 Falcon4 (144 fr) | EER (65001) | 2416 | 5.2 | 5.3 | 4.5 | 9.96 |
| EMPIAR-12963 | EER (65001) | 654 | 5.9 | 7.0 | 5.1 | 13.10 |
| EMPIAR-10164 tilt series (8 fr) | MRC mode 0, signed int8 (.mrcs) | 456 | 2.1 | 2.2 | 1.1 | 4.16 |
| EMPIAR-10216 apoferritin (59 fr) | int16 MRC (.mrcs) | 990 | 2.0 | 3.7 | 1.3 | 6.93 |

### 7. Profile overhead (profiled vs unprofiled process wall)

`--profile` records clocks/rusage at ~45 stage boundaries per movie and, with device timing on (default), synchronises each timed CUDA step. `prof0` = `--profile_device_timing 0`, config L, one run.

| family | cfg | unprof s | prof s | overhead s | overhead % | prof0 (L) s | prof0 overhead s |
|---|---|---:|---:|---:|---:|---:|---:|
| RELION tutorial | G | 1.41 | 1.38 | -0.03 | -2.4 | - | - |
| RELION tutorial | L | 1.43 | 1.49 | 0.06 | 4.1 | 1.51 | 0.08 |
| EMPIAR-10028 | G | 2.20 | 2.22 | 0.02 | 0.7 | - | - |
| EMPIAR-10028 | L | 2.32 | 2.32 | 0.01 | 0.2 | 2.37 | 0.05 |
| EMPIAR-10361 | G | 4.90 | 4.87 | -0.04 | -0.7 | - | - |
| EMPIAR-10361 | L | 5.18 | 5.14 | -0.03 | -0.6 | 5.10 | -0.07 |
| EMPIAR-10641 | G | 3.90 | 3.96 | 0.06 | 1.5 | - | - |
| EMPIAR-10641 | L | 29.82 | 29.93 | 0.11 | 0.4 | 29.78 | -0.04 |
| EMPIAR-10441 | G | 6.85 | 6.80 | -0.05 | -0.7 | - | - |
| EMPIAR-10441 | L | 7.14 | 7.10 | -0.04 | -0.5 | 7.13 | -0.01 |
| EMPIAR-10474 Falcon3 (58 fr) | G | 12.43 | 12.54 | 0.10 | 0.8 | - | - |
| EMPIAR-10474 Falcon3 (58 fr) | L | 14.21 | 14.24 | 0.02 | 0.2 | 14.02 | -0.20 |
| EMPIAR-10474 Falcon4 (144 fr) | G | 25.99 | 26.03 | 0.04 | 0.1 | - | - |
| EMPIAR-10474 Falcon4 (144 fr) | L | 26.40 | 26.09 | -0.31 | -1.2 | 26.14 | -0.26 |
| EMPIAR-12963 | G | 5.07 | 5.06 | -0.01 | -0.2 | - | - |
| EMPIAR-12963 | L | 5.80 | 5.79 | -0.01 | -0.2 | 5.83 | 0.03 |
| EMPIAR-10164 tilt series (8 fr) | G | 3.01 | 3.11 | 0.11 | 3.6 | - | - |
| EMPIAR-10164 tilt series (8 fr) | L | 3.16 | 3.13 | -0.03 | -0.8 | 3.17 | 0.01 |
| EMPIAR-10216 apoferritin (59 fr) | G | 4.75 | 4.69 | -0.06 | -1.3 | - | - |
| EMPIAR-10216 apoferritin (59 fr) | L | 12.80 | 12.82 | 0.03 | 0.2 | 12.85 | 0.05 |

### 8. Patch-alignment convergence and traced device peak (per-movie logs, first usable L unprofiled run)

A patch whose first attempt reports `converged=no` takes the inherited retry path, which downloads the resident real frames to the host and repeats the patch alignment. `traced peak` = largest `Peak GPU memory allocated` line in the movie logs (device buffers of the alignment stages the code accounts for; not a process peak).

| family | movies | patches | retried (first attempt converged=no) | retry converged | traced peak MiB |
|---|---:|---:|---:|---:|---:|
| RELION tutorial | 2 | 50 | 0 | 0 | 1570 |
| EMPIAR-10028 | 2 | 50 | 0 | 0 | 1223 |
| EMPIAR-10361 | 2 | 50 | 0 | 0 | 6702 |
| EMPIAR-10641 | 2 | 50 | 41 | 1 | 7566 |
| EMPIAR-10441 | 1 | 25 | 0 | 0 | 21623 |
| EMPIAR-10474 Falcon3 (58 fr) | 2 | 50 | 4 | 0 | 4417 |
| EMPIAR-10474 Falcon4 (144 fr) | 2 | 50 | 0 | 0 | 10957 |
| EMPIAR-12963 | 1 | 25 | 2 | 0 | 2972 |
| EMPIAR-10164 tilt series (8 fr) | 2 | 50 | 0 | 0 | 2106 |
| EMPIAR-10216 apoferritin (59 fr) | 2 | 50 | 30 | 0 | 4493 |

### 9. VRAM: measured peak on the 80 GB A100 and arithmetic estimate for smaller cards

Measured = NVML per-process peak over every run of the family (all cells; sampled, so a lower bound; includes the CUDA context). **Estimate** = 2 x one float32 movie (resident `d_Fframes` half-spectra + `d_Iframes` real frames, docs/vram_live_ranges.md) + the overhead measured on the families. It is arithmetic, not a measurement on a small card.

| family | float32 movie GiB | 2x movie GiB | measured peak GiB (G / L) | measured - 2x movie GiB | fits 24 GiB | fits 40 GiB | fits 48 GiB |
|---|---:|---:|---|---:|---|---|---|
| RELION tutorial | 1.27 | 2.55 | 3.2 / 3.3 | 0.74 | yes | yes | yes |
| EMPIAR-10028 | 1.00 | 2.00 | 2.6 / 2.7 | 0.67 | yes | yes | yes |
| EMPIAR-10361 | 5.44 | 10.89 | 11.6 / 12.3 | 1.45 | yes | yes | yes |
| EMPIAR-10641 | 6.15 | 12.29 | 13.1 / 14.7 | 2.39 | yes | yes | yes |
| EMPIAR-10441 | 17.56 | 35.12 | 37.0 / 39.3 | 4.20 | no | borderline | yes |
| EMPIAR-10474 Falcon3 (58 fr) | 3.62 | 7.25 | 7.9 / 8.8 | 1.56 | yes | yes | yes |
| EMPIAR-10474 Falcon4 (144 fr) | 9.00 | 18.00 | 18.6 / 20.0 | 1.97 | yes | yes | yes |
| EMPIAR-12963 | 2.44 | 4.88 | 5.5 / 6.2 | 1.29 | yes | yes | yes |
| EMPIAR-10164 tilt series (8 fr) | 1.70 | 3.39 | 4.5 / 4.5 | 1.07 | yes | yes | yes |
| EMPIAR-10216 apoferritin (59 fr) | 3.69 | 7.38 | 8.0 / 9.0 | 1.58 | yes | yes | yes |

**Estimate: how many frames of each geometry fit** (same arithmetic: peak = 2 x frames x nx x ny x 4 B + that family's measured overhead; fits when peak < 95% of the nominal capacity; the 80 GB measurement is the only calibration).

| geometry | measured overhead GiB | max frames, 24 GiB | 40 GiB | 48 GiB | frames in the corpus movie |
|---|---:|---:|---:|---:|---:|
| RELION tutorial (3710x3838) | 0.74 | 207 | 351 | 422 | 24 |
| EMPIAR-10028 (4096x4096) | 0.67 | 177 | 298 | 359 | 16 |
| EMPIAR-10361 (5760x4092) | 1.45 | 121 | 208 | 251 | 62 |
| EMPIAR-10641 (5760x4092) | 2.39 | 116 | 202 | 246 | 70 |
| EMPIAR-10441 (11520x8184) | 4.20 | 26 | 48 | 58 | 50 |
| EMPIAR-10474 Falcon3 (58 fr) (4096x4096) | 1.56 | 169 | 291 | 352 | 58 |
| EMPIAR-10474 Falcon4 (144 fr) (4096x4096) | 1.97 | 166 | 288 | 349 | 144 |
| EMPIAR-12963 (4096x4096) | 1.29 | 172 | 293 | 354 | 39 |
| EMPIAR-10164 tilt series (8 fr) (7420x7676) | 1.07 | 51 | 87 | 104 | 8 |
| EMPIAR-10216 apoferritin (59 fr) (4096x4096) | 1.58 | 169 | 291 | 352 | 59 |


Fit rule on the measured peak: `yes` below 95% of the nominal capacity, `borderline` below 100%, `no` above. The overhead (measured minus 2x movie) is 0.67 to 4.20 GiB across the families.


### 10. Context: CPU baseline on cpu64 (different host; not a speedup comparison)

CPU = `--use_own` without CUDA on cpu64 (EPYC 7763, Release, 8 CPUs, `--j 8`, L), movie 2 of the run (movie 1 for one-movie families), from the CPU thread's `cpu/summary.json`. GPU = 4GPUs (EPYC 7452, A100), L, steady movie of the replay. Both run main 116eb04a with 8 CPUs and `--j 8`. The hosts differ (EPYC 7763 vs 7452, kernel, page cache vs tmpfs), so differences in host-decode times are not attributable to the code. No speedup is claimed.

| family | CPU L j8 movie ms | CPU ms/Mpx | CPU host read ms | GPU L steady movie ms | GPU ms/Mpx | GPU host read ms |
|---|---:|---:|---:|---:|---:|---:|
| RELION tutorial | 9636 | 28.2 | 245 | 181 | 0.5 | 0 |
| EMPIAR-10028 | 6280 | 23.4 | 356 | 700 | 2.6 | 396 |
| EMPIAR-10361 | 38372 | 26.3 | 1530 | 2063 | 1.4 | 1392 |
| EMPIAR-10641 | 46522 | 28.2 | 1004 | 15730 | 9.5 | 701 |
| EMPIAR-10441 | 151392 | 32.1 | 3307 | 4843 | 1.0 | 2614 |
| EMPIAR-10474 Falcon3 (58 fr) | 24946 | 25.6 | 3133 | 7208 | 7.4 | 4382 |
| EMPIAR-10474 Falcon4 (144 fr) | 60976 | 25.2 | 7889 | 12776 | 5.3 | 10022 |
| EMPIAR-12963 | 18569 | 28.4 | 2503 | 4548 | 7.0 | 3099 |
| EMPIAR-10164 tilt series (8 fr) | 16505 | 36.2 | 328 | 1005 | 2.2 | 336 |
| EMPIAR-10216 apoferritin (59 fr) | 22610 | 22.8 | 740 | 3639 | 3.7 | 958 |

### Run filtering and failures

240 measured records (excluding warm-ups): 240 usable arms, 0 excluded attempts, 0 failed runs.

