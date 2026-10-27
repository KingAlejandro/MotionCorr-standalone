# Mac replicate census, not hash-identical to the frozen census

This amendment is committed before regeneration or native arms in the replicate.
It supersedes the admission disposition, while retaining the original hash-gate
STOP and the literal-rounding preflight STOP unchanged.

## Orchestrator decision (verbatim)

> The preflight shows equal total counts and a squared-count sum difference of 8. That fits a handful of ±1-count pixel flips out of about 6.7e8 pixels. Different random draws would change that sum by about 1e6 or more. Truth reconstructs identically (0 px), and the shape, seeds, parameters and generator source match. I classify this as rounding-level differences propagated through integer count sampling, the same recipe and not structural, so the replicate condition is met. Your stop was correct under the literal wording, so keep it recorded.

## Frozen scope

- All 100 movies are regenerated on this Mac from the frozen generator, seeds
  and parameters. The stack is the existing fresh venv: Python 3.15.1,
  NumPy 2.5.4, SciPy 1.18.1. No generator change is permitted.
- Truth/expectations come from the same local generation. The unchanged #269
  evaluator uses its analytic motion truth, fixed 129 × 129 ROI, frame-0 gauge
  and 0.20 / 0.40 / 0.80 Å RMS/p95/max limits. Runtime and actual written/read
  STAR fields are scored separately. No image-transfer qualification is implied.
- Per-movie local hashes are recorded, not compared with frozen movie hashes.
  Recipe fields must remain equal to the frozen receipts.
- OFF and B2 use the existing NEW macOS arm64 binary
  `e978af21352295bfe2cf756fa2916703d2b7e6c6b34c352d58630e7975155946`,
  built from git archive `326f03a073aec0d26c9cd585ce4f701d1c808245`,
  tree `44ea2f4c053229297f50ce7feb1066e291674b06`, Release `-O3 -DNDEBUG`,
  CUDA off, `MC_EXPERIMENT_CCF_DC=ON`. No rebuild or source change.
- Both arms use `--use_own --j 8 --patch_x 5 --patch_y 5 --group_frames 1
  --bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1
  --last_frame_sum 40 --skip_logfile --ingest float`, with runtime capture,
  `OMP_NUM_THREADS=8`, `OPENBLAS_NUM_THREADS=1`, CCF DC arm `none` and all other
  experimental arms none/off. B2 adds only `--experimental_local_b2`.
- One movie at a time: regenerate, hash, OFF, B2, score, retain compact records,
  delete pixels. At most two movies on disk; stop if free space falls below
  10 GiB (the stricter binary interpretation of 10 GB). Inspect occupancy before
  producers; leave the other local two-thread task and all unrelated work alone.
  No macOS CPU-affinity claim; timing is descriptive under observed contention.
- Retain every failure. No producer is silently retried. No SSH, remote-host
  attempt, evaluator/limit/ROI/gauge/source change or forced push.

## Predictions and reporting fixed before arms

- **P1:** agreement with W8 per movie is **UNTESTABLE on replicate inputs**.
- **P2:** B2 pass count is greater than OFF on the 80 in-model movies.
- **P3:** every OFF-pass/B2-fail movie is listed. Dose4 tail regressions are
  expected from the pilot; report them without excusing them. Also list every
  RMS/p95/max increase, separately for runtime and STAR.
- **P4:** per-movie OFF versus B2 wall time, descriptive only; no speedup claim.
- **P5:** OFF per-movie pass/fail agrees with the frozen Linux OFF census
  verdicts on most movies. Report the agreement count and every flip, without
  a numerical acceptance threshold. Use the #269 `cpu-none` records in the
  frozen local metadata archive, runtime and STAR separately.
- **P6:** for every movie, record total counts and the sum of squared counts
  for both Mac and frozen receipts. Report every movie whose totals differ or
  whose absolute squared-sum difference exceeds 1000. List and analyse these
  movies separately; do not silently pool them.

For P6, receipt moments mean the serialized detector-pixel moments used in the
preflight: sum = N × mean and sum-of-squares = N × (std² + mean²). Record the
unrounded calculations and exact representable-grid totals inferred from them
(quarter-count / sixteenth-count-squared grids for contrast025; integer grids
otherwise). For pedestal/scale conditions also recover the underlying Poisson
count moments as a diagnostic; do not substitute them for the declared receipt
comparison. Use the declared total/squared-sum rule without a new tolerance.

Report the requested overall 80 in-model / 20 remaining scorecards, explicitly
alongside P6-flagged and unflagged strata. The remaining 20 comprise 10 outmodel
movies and 10 pedestal32/no-local diagnostics; report each subgroup too. Report
paired two-sided exact sign tests on truth RMS (lower/higher/tie) for runtime
and STAR, overall and P6 strata. Shared noise across four conditions means
per-movie sign-test p-values are descriptive, not 80 independent realisations.

No merge/default change, Linux byte identity, native GPU execution, stable
performance improvement or broad scientific qualification is claimed.
