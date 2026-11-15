# H6: extending pedestal removal and the coupled peak to local patches (frozen before any H6 run)

Frozen by the orchestrator (Opus 5.5) on 2026-10-26, after #286 head 8389606b and before any H6 run.

## Why

DCg+H2g, the current candidate, conditions only the GLOBAL CCF.
- **What it fixes:** the global five-frame failures (integer and fractional pass at the production stop) and
  15/16 native N-controls. The only miss is the harmful iso case, which also fails at baseline.
- **What remains:** the cases that use the local fit still fail or are fragile:
  - pedestal: 0.262 / 0.577 / 1.016 A;
  - noisy: corner extrapolation after edge patches are dropped;
  - affine at the long budget: max 0.849 A.
- **Hypothesis:** patch CCFs still carry the float32 pedestal, which quantises their peak curvature, and
  they still use the over-gained separable fit. Zeroing the patch CCF DC bin too (the existing #262 'both'
  arm) and applying the coupled peak to patches (`--experimental_coupled_peak all`) should improve the
  local observations.

## Arms

All arms: native CPU, K267 eight cases, unchanged checker, ROI and limits, runtime and STAR.

| Arm | Change |
|---|---|
| DCb+H2a | DC arm 'both' (global and patch CCF DC zeroed), coupled peak 'all' |
| DCb+H2g | DC 'both', coupled peak 'global' only; separates the DC factor on patches |
| DCg+H2a | DC 'global', coupled peak 'all'; separates the peak factor on patches |

Each arm runs at the production stop and at max_iter 50 / tol 1e-9.
Matched control: DCg+H2g from #286, reused and not rerun.

## Predictions

1. Flags-off identity to e77a51a2 is unchanged. Re-verify with the binary used.
2. Pedestal: DCb+H2a has lower RMS than DCg+H2g at the production stop. The patch DC factor (DCb+H2g) gives
   most of that improvement.
3. Integer and fractional (global only): identical to DCg+H2g in every arm, because patches do not enter.
   Any difference is a defect to report.
4. Affine at the production stop keeps its DCg+H2g PASS in DCb+H2a.
5. Noisy and every other case are reported in full. Any RMS, p95 or max increase versus DCg+H2g is listed
   as a regression, with no materiality threshold.

## Falsification

If prediction 2 fails (pedestal no better with patch DC zeroing), patch pedestal quantisation is not the
remaining local error. The candidate then stays global-only (DCg+H2g), and the local error goes back to
the W5 objective-bias / patch-acceptance diagnosis.
