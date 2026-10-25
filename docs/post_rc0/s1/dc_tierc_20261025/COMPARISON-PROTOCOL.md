# Four-arm comparison: declared before computing

Declared 2026-10-25 before the Tier C evaluation output was read and before any new comparison statistic was computed. Source for all statistics: `analyze_dc_fourarm.py`. No variant, default, gate, tolerance, ROI, scoring or regression rule is changed by this packet (maintainer decision M3).

## Data and independent units

- **Tier B** (`motion-counting/1`, truth available): 804 records = 800 experiment records (10 conditions x 2 backends x 4 arms x 10 seeds) + 4 plain controls. Scene and motion are fixed within a condition; the 10 seeds are independent noise draws. Unit = seed, paired across arms within (condition, backend). CPU and CUDA records of one seed share the same input, so backends are analysed separately and never pooled as extra units. The 10 conditions differ in the DC property, not in scene: they are reported separately and are not treated as exchangeable replicates.
- **Tier C** (real movies, no truth): 51 movie groups x 2 patch grids (p3, p5) x 4 arms x 2 backends = 816 queue jobs. Unit = movie group. The two grids of one movie are dependent: movie-level values are the mean over the grids present in every compared arm; grid-level values are descriptive only. Tier C has no truth, so it cannot show improvement or harm in accuracy. It shows change vs `none`, convergence change and CPU/CUDA agreement.

## Primary family (the only inferential tests)

1. Tier B, 60 cells: arm in {global, local, both} vs `none`, 2 backends, 10 conditions; metric = field RMS (Angstrom); paired delta = arm - none per seed; exact two-sided sign test (the existing rule) with Holm adjustment over the 60; paired bootstrap 95% interval of the median delta (10,000 resamples of seeds, `numpy.random.default_rng(20261025)`).
2. Tier C, 3 tests: CPU/CUDA relative image RMSE of arm minus that of `none`, per movie (movies with CPU and CUDA present for both arms), exact two-sided sign test with Holm over the 3 arms; bootstrap 95% interval of the median over movies.

Everything else is descriptive with no p-value: p95 and max against the 0.20 / 0.40 / 0.80 Angstrom limits (rms / p95 / max, the unchanged `field_distance_status` rule), joint limit pass counts, image signal retention (in-band and top-band transfer; report-only, no criterion exists), global/local field components, failure and convergence changes (paired discordant counts, exact McNemar p shown but not part of any family), Tier C change-vs-none magnitudes, Tier B backend gap in field RMS.

## Harm

- **Existing regression rule** (unchanged, `tools/summarize.py`): any seed where arm is strictly worse than `none` on field RMS, field max, in-band transfer or top-band transfer. All entries are retained in `tierB_regressions_all.csv` and must reproduce the 965 entries of the reviewed v2.2 summary exactly.
- **Material harm** (a subset declared here, listed one by one): Tier B seed where (a) `none` meets a limit (rms <= 0.20, p95 <= 0.40 or max <= 0.80 Angstrom) and the arm does not; or (b) the arm introduces a failure that `none` lacks (native exit, global non-convergence, local model disabled, outside ROI, field distance FAIL); or Tier C movie-grid where the arm is non-converged and `none` on the same backend is converged.
- Signal transfer loss and Tier C image change are reported without a harm label.

## Incomplete or unmatched comparisons

A table lists per tier, backend and arm: expected, present, evaluated, never-run, orphan and unmatched counts, and every Tier C comparison dropped for a missing arm or backend. Never-run jobs (296) and the interrupted orphan (1, no RUN record) are not completed records and are never evaluated or counted as graded.
