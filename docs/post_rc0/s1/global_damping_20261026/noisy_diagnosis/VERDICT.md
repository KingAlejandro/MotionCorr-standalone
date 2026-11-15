# Noisy production-stop diagnosis: verdict against PREDICTION.md

Prediction (committed before the run, be7bdf14): hypothesis (ii), one or a few bad patch observations inherited from the changed global trajectory; forcing
5 global iterations should NOT remove the regression. Data: `results/noisy_diag/noisy_analysis.{md,json}`, per-arm `noisy.log` / `noisy.star` under `results/v2/*/noisy/`.

## What the 21.3 Å maximum is

- It sits at the top-right ROI corner (frame 5, y = 12, x = 115) of DCg+H2g at the production stop. Its frame-5 global shift is small (-2.0, 0.5 Å) and the
  frame's spatial-mean error is 0.90 Å (4% of the maximum). The estimated local polynomial at that pixel is (-16.4, +16.2) Å. The maximum is a corner extrapolation of the local fit, not a global-shift error.
- Patch (1,3) (centre (104,15), the top-right patch) does not converge in the five patch iterations (RMSD 4.66, 1.38, 0.85, 0.99, 1.30 px) and is dropped; so is patch (2,3) (centre (104,47)). Only one
  right-column patch, (3,3), is left, so nothing anchors the top-right corner. Patch (2,3) is also dropped in dcg-prod, h2glob-prod and the forced-5 run, which do not show the large error. Patch (1,3) is dropped only in DCg+H2g at the production stop.
- A bad accepted observation is present in most arms: patch (62,79) at frame 5 is 13.3 to 13.6 Å off the truth in arms a, dcgh2g-prod, h2glob-prod, the forced-5 run and dcgh2g-long (and (104,47) frame 5 is 20.3 to 20.4 Å off in arms a and dcgh2g-long). It is not what changes between arms.

## Per-iteration global update norms (px RMSD of the unscaled update, from each arm's `noisy.log`)

| Arm | iteration 1, 2, ... | stops after |
|---|---|---|
| dcg-prod | 1.563, 0.566, 0.391 | 3 |
| dcgh2g-prod | 1.893, 0.369 | 2 (0.369 < 0.5) |
| h2glob-prod | 1.928, 1.117, 0.943, 0.532, 0.474 | 5 (0.474 < 0.5 only at the cap) |
| diag run (global forced to 5) | 1.893, 0.369, 0.074, 0.016, 0.004 | 5 |

The iteration-1 norms are ordinary (1.56 to 1.93), so there is no large transient. DCg+H2g converges fastest in the global alignment and stops at iteration 2.

## The discriminating run

`diag-dcgh2g-g5`: noisy only, DCg + H2 global, `--max_iter 5 --experimental_align_tolerance 1e-9` (global alignment forced through 5 iterations; patch settings as in the production stop).
Result 1.704 / 3.426 / 7.417 Å against 3.049 / 6.320 / 21.295 Å for the production stop, and 1.744 / 3.515 / 7.383 Å for dcg-prod. The regression disappears. The global
spatial-mean errors barely change (frames 2 to 5: 0.79, 0.59, 0.28, 0.99 Å against 1.56, 1.39, 1.12, 0.90 Å). The tiny extra global updates (0.074, 0.016, ... px) change which patches converge:
(1,3) now converges (5 iterations, 0.36 px) and anchors the corner.

## Verdict

- **(ii), my prediction: confirmed on where and what, falsified on persistence.** Confirmed: the maximum is localised at a corner, the frame's spatial-mean error is 4% of it, accepted patch observations carry errors of 13 to 20 Å (several px), and the patch set is what differs. Falsified: I predicted that forcing 5 global iterations would not remove the regression; it removes it (7.4 Å). The reason is that forcing the iterations also changes the trajectory the patches inherit, which I noted as a weakness of that clause but wrote down anyway. Neither of (ii)'s refutation conditions (spatial-mean error at least 70% of the maximum; all accepted observations under 2 px) is met.
- **(i), transient frozen by the stop: its outcome test is met, its mechanism is not.** The forced-5 run restores the dcg-prod level, as (i) said it would. But there is no large global transient (iteration-1 norm 1.89 against 1.56 and 1.93), and the global-shift error is small and almost unchanged by forcing. What the early stop freezes is a global state about 0.07 px from the converged one; the harm comes through the patch stage, not through the global shifts.
- **(iii), H_xy amplified by noise on global peaks: not the carrier.** Its stated refutation (per-frame spatial-mean error not above dcg-prod's by more than 1.5x at every frame) is not met in the formal sense (ratios 1.8 to 5.1, absolute 0.9 to 1.6 Å against 0.2 to 0.7 Å), so it is not refuted by its own rule. But the maximum is a corner extrapolation carrying 4% frame-mean error, forcing the global iterations leaves the frame-mean errors close to dcg-prod's while the maximum collapses, and the guard never fires here (0 of 10 peaks). H2 global peaks may add a 1 to 1.6 Å frame-mean offset; they do not explain 21 Å.
- **Net:** two of the three survive in part and they are not exclusive. The regression is a stop-rule by patch-acceptance interaction: the global alignment stops at iteration 2, which changes patch (1,3)'s input enough that it fails to converge in 5 iterations and is dropped; the top-right corner is then extrapolated by the local polynomial, with a pre-existing bad accepted observation at (62,79) frame 5 adding to it. It is a noise-sensitivity of the patch fit to a 0.07 px change of its input, on a fixture where several patches already carry large errors in the baseline (`noisy` is characterisation, not a gate role). No guard, stop rule, weight or threshold was changed in response.
