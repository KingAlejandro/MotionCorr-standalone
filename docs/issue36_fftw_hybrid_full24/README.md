# Issue 36: full 24-movie tutorial gate for the opt-in hybrid FFTW CUDA path

Source under test: `KingAlejandro/MotionCorr-standalone`, branch `exp/issue36-fftw-global-hybrid`,
commit `5407373be31a6fe5f79a8cc5709be00723921b19`. No source, tolerance, or comparator change was made.

This extends [`docs/issue36_fftw_hybrid/README.md`](../issue36_fftw_hybrid/README.md), which reported two
movies, to the complete 24-movie RELION SPA tutorial set that Issue #36's final pass criterion requires.

## Headline result

| Full 5x5 CUDA mode | Gate 2 relaxed, corrected image | Trajectory | STAR fields |
| --- | --- | --- | --- |
| Default CUDA | **0 / 24 pass** | 24 / 24 pass | 24 / 24 pass |
| `MOTIONCORR_EXPERIMENTAL_ALL_FFTW=1` | **12 / 24 pass** | 24 / 24 pass | 24 / 24 pass |

**The all-FFTW option does not make the 24-movie tutorial gate pass.** It improves the corrected-image
relative RMSE on every one of the 24 movies, by a factor of 2.18x to 26.60x (median 7.20x), and it moves
the pass count from 0/24 to 12/24 — but 12 movies still exceed the unchanged `0.001` relative-RMSE limit.

All 48 comparisons completed with `coverage.complete = true`; no comparison is missing.

## Why the earlier two-movie result looked like a clean pass

The two movies in the earlier report, `00021` and `00046`, are among the **best** cases in the full set.
`00046` has the lowest all-FFTW relative RMSE of all 24 movies (3.925e-4) and `00021` is 5th lowest
(6.187e-4). The set median is 9.734e-4, essentially on the 1e-3 limit. The earlier two-movie sample was
therefore not representative, which is exactly what the earlier report flagged as unverified.

This run reproduces that earlier work exactly, so the difference is coverage, not configuration:

| Quantity | Published (2-movie report) | Measured here |
| --- | ---: | ---: |
| `00021` default relative RMSE | 0.006105328 | 0.006105328 |
| `00046` default relative RMSE | 0.010438802 | 0.010438802 |
| `00021` all-FFTW relative RMSE | 0.000618735 | 0.000618735 |
| `00046` all-FFTW relative RMSE | 0.000392505 | 0.000392505 |
| `00021` all-FFTW CCF transfer bytes | 360,562,176 | 360,562,176 |

All four values agree to nine decimal places.

## Aggregate metrics against the unchanged relaxed gate

Relaxed-gate thresholds, used with no override: max frame shift error `0.05` px, coordinate shift RMS
`0.02` px, image RMSE `0.02`, max absolute pixel error `5.0`, image relative RMSE `0.001`.

| Metric (24 movies) | Default CUDA | All-FFTW CUDA | Threshold |
| --- | ---: | ---: | ---: |
| Relative image RMSE, min | 5.026511e-03 | 3.925052e-04 | — |
| Relative image RMSE, median | 7.162018e-03 | 9.733595e-04 | — |
| Relative image RMSE, max | 1.043880e-02 | 3.015376e-03 | 1e-3 |
| Movies over the relative-RMSE limit | 24 | 12 | 0 |
| Image RMSE, max | 9.403306e-03 | 2.727364e-03 | 2e-2 (pass) |
| Max absolute pixel error, max | 3.007114 | 2.319769 | 5.0 (pass) |
| Max frame shift error, max | 1.283500e-02 | 3.811000e-03 | 5e-2 (pass) |
| Coordinate shift RMS, max | 8.107678e-03 | 2.124822e-03 | 2e-2 (pass) |
| Total STAR field differences | 0 | 0 | 0 (pass) |
| Pixel-identical movies | 0 | 0 | — |

The **only** failing criterion in either mode is corrected-image relative RMSE. Trajectory, absolute image
RMSE, max-pixel, and STAR checks pass for all 24 movies in both modes, including default CUDA. Per Issue
#36's instruction, the trajectory-only status is not reported as the Gate 2 status.

The default-CUDA range here (5.027e-3 to 1.044e-2) is close to but not identical with the range recorded
in Issue #36's opening comment (2.899e-3 to 1.0082e-2); those numbers came from an earlier build and
commit, so they are not expected to match digit for digit.

## Per-movie results

Relative image RMSE against the same-source CPU reference. `PASS`/`FAIL` is the overall relaxed gate.

| Movie | Default relRMSE | Gate | All-FFTW relRMSE | Gate | All-FFTW max pixel err |
| --- | ---: | :---: | ---: | :---: | ---: |
| 00021 | 6.105328e-03 | FAIL | 6.187349e-04 | PASS | 0.6457 |
| 00022 | 7.073201e-03 | FAIL | 2.053765e-03 | FAIL | 1.7343 |
| 00023 | 5.994510e-03 | FAIL | 4.645673e-04 | PASS | 0.9357 |
| 00024 | 5.026511e-03 | FAIL | 1.182160e-03 | FAIL | 2.3198 |
| 00025 | 7.242691e-03 | FAIL | 7.305632e-04 | PASS | 0.8395 |
| 00026 | 8.358252e-03 | FAIL | 8.613321e-04 | PASS | 1.1108 |
| 00027 | 6.378202e-03 | FAIL | 6.226599e-04 | PASS | 0.9968 |
| 00028 | 7.477015e-03 | FAIL | 1.110500e-03 | FAIL | 1.5158 |
| 00029 | 7.698313e-03 | FAIL | 1.083240e-03 | FAIL | 1.5742 |
| 00030 | 5.557336e-03 | FAIL | 5.500098e-04 | PASS | 0.5744 |
| 00031 | 6.494629e-03 | FAIL | 2.573402e-03 | FAIL | 1.5820 |
| 00035 | 7.579742e-03 | FAIL | 7.973401e-04 | PASS | 0.6803 |
| 00036 | 8.217213e-03 | FAIL | 2.404826e-03 | FAIL | 1.6266 |
| 00037 | 9.916038e-03 | FAIL | 1.399873e-03 | FAIL | 1.0645 |
| 00039 | 7.730981e-03 | FAIL | 1.168595e-03 | FAIL | 1.6204 |
| 00040 | 6.393003e-03 | FAIL | 1.497669e-03 | FAIL | 1.2403 |
| 00042 | 7.117248e-03 | FAIL | 7.204679e-04 | PASS | 0.8905 |
| 00043 | 5.717798e-03 | FAIL | 8.441910e-04 | PASS | 1.0389 |
| 00044 | 7.206787e-03 | FAIL | 8.634791e-04 | PASS | 1.3166 |
| 00045 | 8.602042e-03 | FAIL | 1.177925e-03 | FAIL | 0.9572 |
| 00046 | 1.043880e-02 | FAIL | 3.925052e-04 | PASS | 0.5689 |
| 00047 | 6.672346e-03 | FAIL | 1.689956e-03 | FAIL | 1.2396 |
| 00048 | 7.686024e-03 | FAIL | 6.135746e-04 | PASS | 0.6573 |
| 00049 | 6.563678e-03 | FAIL | 3.015376e-03 | FAIL | 1.1245 |

All movie names are `20170629_<id>_frameImage`; all have 24 frames.

### Worst cases

Default CUDA, by relative RMSE: `00046` 1.0439e-2, `00037` 9.9160e-3, `00045` 8.6020e-3,
`00026` 8.3583e-3, `00036` 8.2172e-3.

All-FFTW, by relative RMSE: `00049` 3.0154e-3, `00031` 2.5734e-3, `00036` 2.4048e-3,
`00022` 2.0538e-3, `00047` 1.6900e-3.

The result straddles the limit rather than clearing it. The 12 all-FFTW failures exceed the limit by only
1.08x to 3.02x, and the three highest passes (`00044` 8.635e-4, `00026` 8.613e-4, `00043` 8.442e-4) sit
just under it. A small change in input or build could move individual movies across the line, so the
12/24 split should be read as "roughly half, marginally", not as a stable partition.

## Time and memory

Single unpaired wall times recorded alongside the correctness runs, for the whole 24-movie set on one
A100 (GPU 0): default CUDA 1:07.52, all-FFTW CUDA 1:23.82. Maximum resident set size 1,648,292 kB and
1,656,208 kB respectively. The CPU reference took 17:30.32 on a different host and is not a paired
speed comparison.

These single runs are **not** a controlled timing result. An optional paired timing repeat was deferred
when another GPU job took the shared benchmark lock; it was stopped and is excluded from this report.

Per-movie FFTW cost, from the 24 all-FFTW movie logs (`fftw_profile.json`): each movie performs exactly
1 global and 25 local FFTW CCF activations, spends 111.93-131.93 ms on CCF host transfers and
424.02-563.71 ms on host FFTW plus peak finding.

## Method and provenance

Full detail is in [`provenance.json`](provenance.json). Key points:

- **Source.** All 415 git-tracked files were staged to both hosts from a `git archive` of commit
  `5407373`. The tracked-tree digest `eb13f7dc...` was verified byte-identical on both hosts, with zero
  missing and zero extra files.
- **Inputs.** The 24 TIFFs plus `gain.mrc` were verified byte-identical across the two hosts
  (combined digest `b88e3cdf...`), as was `movies.star` (`fb998f70...`). Per-file digests are in
  [`input_sha256.txt`](input_sha256.txt).
- **Binaries.** CUDA `553ca549...` (CUDA 12.8.61, g++ 13.3, FFTW 3.3.10, Release, `TIMING=ON`, sm_80).
  CPU `a718c012...` (Release, `CUDA=OFF`, `TIMING=OFF`).
- **CPU reference was rebuilt, not reused.** The existing `c595f068...` CPU binary on `cpu64` was built
  from a source tree (`de8062a4...`) that does **not** match commit `5407373`: `CMakeLists.txt` and
  `src/acc/cuda/cuda_alignpatch.cu` differ, beyond documentation. The exact-match precondition for reuse
  failed, and those results covered only 2 of 24 movies, so fresh same-source references were produced.
  (Both differing non-doc files are CUDA-only, so they would not change a `CUDA=OFF` build's behaviour;
  reuse was still declined because the stated precondition was not met.)
- **Comparator.** `tools/compare_motioncorr.py`, SHA-256 `8fee004c...`, unmodified since #19, run with
  `--gate relaxed` and no tolerance override.
- **Batched and one-movie invocations agree here.** All three configurations processed the full
  24-movie STAR in one process each. A separate run used one-movie STAR files and fresh processes;
  all 48 comparator results agree exactly on status, image RMSE, relative RMSE, maximum pixel error,
  coordinate RMS, and maximum frame shift. The comparator JSONs from that control are retained below.
- **Transfer integrity.** The CPU reference outputs were relayed to `4GPUs` for comparison and verified
  byte-identical at both ends (`68c1b515...`).
- **Host hygiene.** All `4GPUs` builds and movie runs ran under top-level `taskset -c 96-103` with `-j8`
  build parallelism and the shared `/tmp/motioncorr-bench.lock`. All four A100s were idle with zero
  compute apps before the CUDA runs. No other user's process was touched.

### Artifacts

- [`comparisons/`](comparisons/) — 48 per-movie comparator JSON reports (24 movies x 2 CUDA modes).
- [`one_movie_comparisons/`](one_movie_comparisons/) — 48 independent comparator JSONs from the
  one-movie invocation control.
- [`aggregate.json`](aggregate.json) — per-criterion pass counts, distribution statistics, worst cases,
  and the full per-movie record.
- [`compare_summary.tsv`](compare_summary.tsv) — one line per comparison with status and exit code.
- [`fftw_profile.json`](fftw_profile.json) — per-movie FFTW CCF activation counts, transfer bytes, and
  host times.
- [`input_sha256.txt`](input_sha256.txt), [`provenance.json`](provenance.json).

Raw MRC outputs and process logs are deliberately kept out of Git, in
`4GPUs:/home/alex/MotionCorr-issue36-full24-run2/` and
`cpu64:/home/ubuntu/MotionCorr-issue36-full24-run2/`.

## Conclusion

Issue #36's final pass criterion — repeat the complete 24-movie CPU-versus-CUDA comparison and report all
gate metrics including failures — is now satisfied as a measurement, and the answer is negative for the
gate: with the unchanged `0.001` limit, default CUDA passes 0/24 and the all-FFTW hybrid passes 12/24.

The hybrid is a real and consistent improvement: it reduces corrected-image relative RMSE on all 24
movies, by a median factor of 7.2x, and it brings the median movie to the edge of the limit. It is not a
fix. The earlier two-movie pass reflected a favourable sample rather than general behaviour.

No tolerance was changed and none is proposed here. The remaining divergence is confined to the corrected
image; trajectory and STAR outputs already agree within the relaxed gate on all 24 movies in both modes.
