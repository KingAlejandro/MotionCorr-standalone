# H3: pedestal removal x peak/update law (frozen before any H3 run)

Frozen by the orchestrator (Opus 5.5) on 2026-10-26 after PR #286 (head f7a50e2f) reported H2 and half-gain,
and before any H3 code or result exists.

## Why

- **H2 failed natively.** The coupled 2x2 peak improves nothing natively (integer 0.264 -> 0.446 A at the
  production stop), although the double-precision analysis predicts eigenvalues -0.23/-0.25 for it.
- **Pedestal dead zone.** The challenge measured that the 100.0 pedestal puts the float32 CCF peak at
  ~40000, where the peak curvature is only 6 ULP. That makes a ~0.083 px dead zone, and the corner stencil
  behind H_xy is then dominated by quantisation.
- **Hypothesis.** The float32 pedestal is what defeats H2 natively. Removing it (zeroing the global CCF DC
  bin, the existing #262 'global' DC arm) should restore the double-precision behaviour.

## Arms

All arms: native CPU, K267 eight cases, unchanged checker, ROI and limits.

| Arm | Change | Notes |
|---|---|---|
| DCg | Global CCF (0,0) bin zeroed; separable peak; gain 1 | DC hook ported verbatim from 3eee0a4b (`src/experiment_ccf_dc.h` and its call sites), global only, CPU only |
| DCg+H2g | DCg plus `--experimental_coupled_peak global` | |
| DCg+half | DCg plus `--experimental_global_half_gain` | |

Each arm runs at the production stop and at max_iter 50 / tolerance 1e-9.
Matched controls are reused from #286 without rerunning: a, b, c, d, h2glob-prod and h2glob-long.

## Predictions

1. Flags off and DC off: identical to e77a51a2 (re-verify with the rebuilt binary).
2. DCg alone (separable, gain 1) does not make integer or fractional meet the limits at the long budget.
   The separable over-gain (double-precision eigenvalue -1.19) remains.
3. DCg+H2g improves integer and fractional RMS versus DCg alone at both stops, and at least one of them
   meets 0.20/0.40/0.80 A in STAR at the long budget.
4. DCg+half at the long budget keeps the integer/fractional/affine passes of arm c (no loss).
5. Zero stays PASS. Flat and repeated stay UNIDENTIFIABLE. Noisy and pedestal are reported in full, and
   any RMS or max increase versus the matched non-DC arm is listed as a regression.

## Falsification and consequence

- **If prediction 3 fails** (DCg+H2g is no better than DCg alone at the long budget), the separable-peak
  over-gain is not the native cause, even without the pedestal. The challenge's mechanism is then rejected
  for native CPU, and half-gain's native benefit needs another explanation before any further prototype.
- **If prediction 3 holds**, the principled candidate is pedestal removal plus the coupled peak at gain 1.
  It then needs N=9/13/20 controls, noisy harm checks and CUDA parity before any adoption discussion.
