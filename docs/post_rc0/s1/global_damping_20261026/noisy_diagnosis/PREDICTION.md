# Noisy production-stop regression of DCg+H2g: prediction (written and committed before the discriminating run)

Observation to explain: `noisy`, #267 fixture, native CPU, STAR scores. Flags-off arm a 2.343 / 4.38 / 9.90 Å;
DCg+H2g at the production stop (5 iterations, 0.5 px) 3.049 / 6.32 / 21.30 Å; DCg+H2g at 50 iterations / 1e-9 1.803 / 3.71 / 9.88 Å.

**What I had already seen before writing this** (disclosed, not hidden): the per-movie logs of the existing arms
(`<arm>/noisy/noisy.log`, which the K267 driver does not suppress) show the global iteration RMSDs: dcgh2g-prod 1.893, 0.369 (stops at iteration 2);
dcg-prod 1.563, 0.566, 0.391 (stops at 3); h2glob-prod 1.928, 1.117, 0.943, 0.532, 0.474 (stops at 5). I had not looked at any per-frame or per-patch error,
and the iteration-1 norms look ordinary (no large transient). 21.3 Å is about 24 px; max/RMS is about 7, which points at something localised.

## Hypothesis (choose one): (ii) one or a few bad patch observations

A wrong CCF peak in a noisy patch is accepted (its patch RMSD falls under 0.5 px, or the observation is otherwise kept), and the third-order local fit
spreads it, most strongly at an ROI corner or edge frame. The bad observation is inherited from the changed global trajectory (DCg+H2g stops the
global alignment at iteration 2, a different residual than h2glob or dcg give the patches).

## Discriminating run (the only new run)

Noisy case only, same argv as the K267 driver and same binary, with `MC_EXPERIMENT_CCF_DC_ARM=global`, `--experimental_coupled_peak global`,
`--max_iter 5 --experimental_align_tolerance 1e-9`. This forces the global alignment to run all 5 iterations (no early stop at 2) and leaves the
patch alignment exactly as in the production-stop arm (max_iter 5, 0.5 px). No guard, stop rule, weight or threshold is changed; the tolerance flag is the
existing diagnostic one. Analysis uses the STAR local-shift observations, the runtime field, the per-movie iteration logs and the truth field.

## Predictions and refutations

- (ii) predicts: the pixel that carries the 21.3 Å maximum lies at an ROI corner or edge, its spatial-mean (global-trajectory) error at that frame is
  well below the maximum (under half of it), and at least one accepted patch observation near it has an error of several px at the frames where the maximum sits.
  **(ii) is refuted if** the per-frame spatial-mean error of the frame carrying the maximum is at least 70% of the maximum (the error is a global shift error,
  uniform over the ROI), or if every accepted patch observation has error under 2 px at that frame.
- Forcing 5 global iterations should NOT remove the regression under (ii): noisy max stays above 10 Å and RMS above 2.5 Å.
  **(i) (a transient frozen by the stop) is supported if** the forced-5-iteration run brings noisy to the level of dcg-prod (RMS about 1.7, max about 7.4) or better,
  and refuted if RMS stays within 20% of 3.049 and max within 20% of 21.30. (i) also predicts a global iteration-1 or iteration-2 update much larger than in
  dcg-prod and h2glob-prod; the logs above already show it is not (1.89 against 1.56 and 1.93), which counts against (i) before the run.
- **(iii) (H_xy amplified by noise on low-SNR global peaks, guard silent)** predicts the per-frame global error of DCg+H2g (spatial-mean error per frame)
  is larger than dcg-prod's at the same iteration or in the final trajectory, with the error present in the global shifts themselves (frame-wise, spatially uniform).
  **(iii) is refuted if** the final per-frame spatial-mean errors of dcgh2g-prod are not larger than those of dcg-prod by more than a factor of 1.5 at every frame
  (largest per-frame ratio), i.e. the global trajectory is not the worse one.

Verdict rule: report which of (i), (ii), (iii) survives and which are refuted. If two survive or none does, say so. No remedy is attempted in this round.
