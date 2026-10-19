# RC0 paired whole-job CPU comparisons for #179 and #183 (C5/C7)

Measurement only; no product source changed. Rule: the amended decision rule on [#10](https://github.com/KingAlejandro/MotionCorr-standalone/issues/10#issuecomment-6223528151), register rows C5/C7 on #198.

## Result

| PR | measurement criteria (rule items 1-3, product identity of 4) | still open before GO (not run here) |
|---|---|---|
| #179 | **Met.** Resolved faster on tutorial (−3.28 %) and e10474f4 (−3.97 %), both beyond the null; e10216 unresolved (−3.17 %); no family slower; products identical. | full CTest on current main; CUDA fallback CTests (item 5) |
| #183 | **Met, narrowly.** e10641 −2.15 % resolved and beyond the null, so the ≥2 % floor is cleared by 0.15 points; the CI is −3.1 % to −1.5 %. e10216 −3.11 % is resolved by `stats.paired` but not beyond null_max. No family slower; products identical. | full CTest; CUDA fallback CTests (item 5); second independent numerical reviewer (item 6) |

## Per family

ΔT = B − A in whole-job wall seconds (negative = candidate faster). Median and 95 % sign-test CI come from `tools/profiling/lib/stats.py` `paired()` (`MIN_PAIRS = 6`), used unmodified. noise = 1.4826·MAD of the pair differences. null_max = largest |d| of the six AA null pairs of that family (second run − first run, same binary). "Resolved" in the last column needs the CI to exclude 0, |median| > noise, and |median| > null_max.

### #179 symmetric dose weights (4de2f59b)

| family | pairs (+null) | median A / B (s) | median ΔT (s) | 95 % CI (s) | % change | noise (s) | null_max (s) | resolved | products identical to A |
|---|---|---|---|---|---|---|---|---|---|
| tutorial | 6 (+6) | 19.179 / 18.565 | −0.629 | [−1.172, −0.488] | −3.28 % | 0.145 | 0.225 | **faster** | 7/7 B runs, 19/19 A runs |
| e10216 | 6 (+6) | 43.626 / 42.877 | −1.383 | [−2.335, +0.166] | −3.17 % | 1.026 | 1.956 | no (CI includes 0) | 7/7, 25/25 |
| e10474f4 | 6 (+6) | 114.128 / 109.826 | −4.530 | [−4.860, −4.040] | −3.97 % | 0.254 | 1.229 | **faster** | 7/7, 19/19 |

### #183 local patch phase window and final-update skip (d039ea22)

| family | pairs (+null) | median A / B (s) | median ΔT (s) | 95 % CI (s) | % change | noise (s) | null_max (s) | resolved | products identical to A |
|---|---|---|---|---|---|---|---|---|---|
| e10216 | 6 (+6) | 43.752 / 42.281 | −1.360 | [−2.170, −0.111] | −3.11 % | 0.290 | 1.956 | no: CI excludes 0 but |ΔT| < null_max | 7/7, 25/25 |
| e10641 | 6 (+6) | 91.023 / 88.858 | −1.958 | [−2.785, −1.368] | −2.15 % | 0.444 | 1.386 | **faster** | 7/7, 19/19 |

The e10216 null_max (1.956 s) comes from one pair; the other five null pairs are within ±0.85 s. Identity counts include the discarded warm-up; "A runs" include warm-up and null runs.

Supporting numbers (`summary.json`):
- Every pair shows the candidate faster, except #179 e10216, where 2 of 6 pairs are slower (+0.166 s, +0.099 s; sign test p = 0.69). All other comparisons are 6/6 negative (sign-test p = 0.031, the minimum possible with 6 pairs).
- Order effect (second-position cost, from AB vs BA medians) is at most 0.22 s and does not change a verdict.
- User+sys CPU time moves the same way: #179 −3.4 / −4.2 / −4.3 %, #183 −3.3 / −2.8 %.

## Setup

- Host cpu64 (AMD EPYC 7763, 64 CPUs, kernel 6.8.0-86), shared. `flock /tmp/motioncorr-cpu64-bench.lock` held for every build and for each round (one family's pairs; released between rounds).
- **CPU mask 8-15, not 0-7.** At the start, two other long-running `ctffind` processes (unpinned, affinity 0-63) occupied cpus 0 and 1, i.e. two busy cores inside 0-7. 8-15 is on the same NUMA node (0-31), and the mask is identical for every arm and family. During the runs foreign load above 0.25 core appeared only outside the lane, on cpus 17, 25, 32, 33, 36, 40, 42 and 49 at various times (the `ctffind` pair plus short bursts from other users; `foreign_other_cpus` in `raw/runs.jsonl`, about 2 cores in total in nearly every run). Lane foreign load was ≤ 0.016 core in every run, so no run was flagged and none was repeated. Foreign activity on neighbouring cores is not excluded as a source of error.
- `taskset -c 8-15`, `--j 8`, `OMP_NUM_THREADS=8`, `OMP_PROC_BIND`/`OMP_PLACES` unset, `GLIBC_TUNABLES` unset, THP `madvise` (read before each run), config L (`--patch_x 5 --patch_y 5`), dose weighting on, `--bfactor 150 --seed 1`, options per family as `docs/workload_corpus/tools/run_matrix.py` (dose, `--expected_frames`, gain, EER grouping). Two movies per family in one process; whole-job wall is `CLOCK_MONOTONIC` around the process.
- Families: #179 tutorial, e10216, e10474f4 (Falcon 4, 144 fr, grouping 40); #183 e10216, e10641. The e10216 baseline and null runs are shared by both candidates.
- Design: per family one discarded warm-up per arm, then 6 rounds. Each round holds one AB (even rounds) or BA (odd rounds) pair per candidate plus one AA null pair, in shuffled order. 117 runs in total (9 warm-up, 108 measured), 0 flagged, 0 product differences.
- Binaries (Release, `-O3 -DNDEBUG`, `-DCUDA=OFF`, built under the lock at `taskset -c 16-23`, cmake `~/.mc-venv/bin/cmake`):

  | arm | source SHA | binary sha256 |
  |---|---|---|
  | A | `1db869025507ac801845b4001b84e6bc0e77a645` | `0746b03b2e77bf6fa5a431c54d42176899a07b94bf1b031824f797ded3215236` |
  | #179 | `4de2f59badc21b959917299f41d8d8518b352ed8` | `e0ac28a3fc74ef4a0a43400c772ae2441a6931a01799adaa764c8fdf812a83c0` |
  | #183 | `d039ea226e2aa4da610bf33de27bfb3ecf465a71` | `8d372f0380bcb6985d2ef242d0cb56f7300a03da7ffe12f1946adc12be045e70` |

  Sources shipped with `git archive`. Main at `2b3c74b3` differs from `1db8690` in the logfile.pdf failure cleanup and tests only (checked with `git diff`), not CPU compute, so A is the exact base of both candidates.
- Product identity: every run's tree compared with the family's first A warm-up tree using `tools/profiling/lib/identity.py` (MRC header with the writer clock masked, extended header and payload; STAR/EPS byte-identical after root normalisation; `.log` and `.pdf` excluded as in that module). All 117 runs identical, including the A-vs-A controls.
- Input sha256: `raw/input_sha256.txt`.

## Files

- `paired_driver.py`, `analyse.py`: the driver run on cpu64 and the analysis (`stats.paired`, unmodified, plus null_max).
- `raw/runs.jsonl`: every run (command, mask, THP, binary sha, wall, user/sys, RSS, foreign load per lane and elsewhere, `ps` before/after, identity result). `raw/smoke-runs.jsonl`: two tutorial A runs used to check the driver and the identity comparison before the real run. `raw/driver.log`, `raw/host_and_binaries.txt`, `raw/families.json`.
- `summary.json`, `tables.md`: analysis output. Per-run `.time` and stdout logs stay on cpu64 in `/home/ubuntu/mc-rc0-paired-20261017/results/`.

## Limitations

- `mcprof compare` was not used: it measures one process per arm with its own instrumentation, so I reproduced the pair-wise design in `paired_driver.py` and used `stats.py` as is. The AA null is not part of `mcprof`; null_max is my reading of the rule (largest |d| over the null pairs). Under the more lenient reading (|median| of the null pairs, at most 0.38 s) #183 e10216 would also count as resolved beyond the null; no GO conclusion changes.
- Single host, one workload instance per family, 6 pairs each (the minimum). The CIs at 6 pairs are the widest the statistics allow at 95 %.
- The null uses the same binary twice, so it does not cover differences between separately built binaries (different build directories).
- #183 e10641 clears the 2 % floor by 0.15 points; its lower CI bound is −1.5 %.
- This measures CPU builds only. CUDA fallback CTests, full CTest on current main and the second numerical reviewer for #183 were not part of this task.
