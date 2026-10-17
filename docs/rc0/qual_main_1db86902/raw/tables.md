### Route-invariance (item 3): nvcomp build, `--ingest auto` vs `--ingest float`

| family | cfg | auto route | float route | CPU build route | products-only identity (MRC hdr+payload, STAR) | strict all-files | route-log allowance (declared prefixes) | other log diffs | peak RSS auto / float / CPU (GiB) |
|---|---|---|---|---|---|---|---|---:|---|
| tutorial | G | nvcomp | float | float | PASS | differs (route log lines) | PASS | 0 | 0.34 / 1.52 / 2.71 |
| tutorial | L | nvcomp | float | float | PASS | differs (route log lines) | PASS | 0 | 0.34 / 1.52 / 2.84 |
| e10361 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 1.54 / 5.67 / 11.06 |
| e10361 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 1.53 / 5.68 / 11.28 |
| e10474f3 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 3.16 / 5.02 / 8.53 |
| e10474f3 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 3.16 / 5.14 / 8.65 |
| e12963 | G | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 2.30 / 3.57 / 5.89 |
| e12963 | L | compact | float | float | PASS | differs (route log lines) | PASS | 0 | 2.30 / 3.63 / 5.97 |
| e10216 | G | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 2.10 / 3.89 / 7.50 |
| e10216 | L | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 2.10 / 4.01 / 7.66 |
| e10028 | G | float | float | float | PASS | PASS | PASS | 0 | 1.59 / 1.55 / 2.11 |
| e10028 | L | float | float | float | PASS | PASS | PASS | 0 | 1.54 / 1.58 / 2.43 |
| e10164 | G | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 0.80 / 2.14 / 3.78 |
| e10164 | L | compact | float | float | PASS | differs (route log lines) | PASS* | 0 | 0.85 / 2.08 / 4.60 |

`PASS*` = the comparator, run with the four prefixes declared in advance, still reports a log difference, but the retained logs show the only extra lines are the signed/int route record `Released native int16/int8 host staging after device forward FFT.` (added by #195; prefix `Released native int`); there are no other log differences (column "other log diffs" counts lines outside the extended prefix list).

### CPU-only build vs CUDA `auto` (item 3, `compare_motioncorr.py --gate backend`, DIAGNOSTIC ONLY)

Backend thresholds: shift RMS 0.02 px, max shift 0.05 px, image RMSE 0.020, max pixel error 5, relative RMSE 0.001 (nonblocking diagnostic).

| family | cfg | gate exit | shift RMS px | max shift px | image RMSE | max pixel err | relative RMSE |
|---|---|---:|---:|---:|---:|---:|---:|
| tutorial | G | 0 | 0.0049 | 0.0075 | 0.007547 | 0.04633 | 0.007096 |
| tutorial | L | 0 | 0.0049 | 0.0075 | 0.007233 | 3.007 | 0.008358 |
| e10361 | G | 1 | 0.0070 | 0.0149 | 0.2781 | 1.662 | 0.01095 |
| e10361 | L | 1 | 0.0070 | 0.0149 | 0.1814 | 44.86 | 0.009091 |
| e10474f3 | G | 0 | 0.0104 | 0.0159 | 0.01477 | 0.08318 | 0.01555 |
| e10474f3 | L | 1 | 0.0104 | 0.0159 | 0.4403 | 4.368 | 0.5999 |
| e12963 | G | 1 | 0.0172 | 0.0316 | 0.02191 | 0.2836 | 0.02273 |
| e12963 | L | 1 | 0.0172 | 0.0316 | 0.3783 | 5.819 | 0.499 |
| e10216 | G | 1 | 0.0166 | 0.0327 | 0.3937 | 2.342 | 0.01659 |
| e10216 | L | 1 | 0.0166 | 0.0327 | 9.097 | 97.29 | 0.4344 |
| e10028 | G | 1 | 0.0032 | 0.0074 | 5.983 | 28.27 | 0.01392 |
| e10028 | L | 1 | 0.0032 | 0.0074 | 5.667 | 1030 | 0.01401 |
| e10164 | G | 0 | 0.0009 | 0.0014 | 0.006514 | 0.05032 | 0.001494 |
| e10164 | L | 0 | 0.0009 | 0.0014 | 0.004267 | 3.063 | 0.001252 |

### #178 fallback (item 4): 1db86902 CUDA+nvCOMP build vs pre-#178 d7171b81 CUDA+nvCOMP build, both WITHOUT `--gpu`

| case | options beyond family G/L | CPU witness (cur / pre) | MRC compared | strict tree identity |
|---|---|---|---:|---|
| noDW-G | `--save_noDW` | 1 / 1 CPU lines, 0 / 0 CUDA | 2 | PASS |
| noDW-L | `--save_noDW` | 1 / 1 CPU lines, 0 / 0 CUDA | 2 | PASS |
| evenodd-G | `--save_noDW --even_odd_split` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| evenodd-L | `--save_noDW --even_odd_split` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| evenodd-23fr-L | `--save_noDW --even_odd_split --last_frame_sum 23` | 1 / 1 CPU lines, 0 / 0 CUDA | 4 | PASS |
| nodose-G | `(no --dose_weighting)` | 1 / 1 CPU lines, 0 / 0 CUDA | 1 | PASS |

