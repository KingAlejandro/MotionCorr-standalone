# H2: coupled 2x2-Hessian subpixel peak (frozen before any H2 run)

Frozen by the orchestrator (Opus 5.5) on 2026-10-26, before any H2 code or result exists.
Source of the hypothesis: the independent Gemini 4 review of W5 E1
(`20261026/E1-damping-challenge/REVIEW.md`), checked analytically by the orchestrator.

## Mechanism

The inherited subpixel estimator fits separate 1D parabolas along the centre row and the centre column
of the 3x3 CCF neighbourhood. For a quadratic peak with Hessian H and true offset p, the row slice
peaks at x = p_x + (H_xy/H_xx) p_y, and similarly for y. With H_xx ~ H_yy the estimate is therefore
(I + rho*sigma_x) p, where rho = H_xy/sqrt(H_xx H_yy), and its gains are 1 +/- rho.
At rho = 0.756 that is 1.756 and 0.244. Multiplied by the leave-one-out factor N/(N-1) = 1.25 at N=5,
the larger gain is 2.195, which reproduces the measured update Jacobian of -2.1925 (eigenvalue -1.19).
The N=5 instability is therefore a peak-definition defect. Scalar damping masks it, and it also slows
the under-gained mode.

## Intervention (one factor)

A default-off option replaces the separable parabola with the full quadratic peak:
- H_xx and H_yy are second differences on the centre row and column (unchanged).
- H_xy = (c[+1,+1] - c[+1,-1] - c[-1,+1] + c[-1,-1]) / 4.
- The gradient g is the central first difference.
- The offset is delta = -H^{-1} g.
- Guard, fixed now: if H is not negative definite (H_xx < 0 and det H > 0), or if |delta| > 1 px in
  either component, use the inherited separable result for that peak. Report how often the guard fires.

Arms:
- H2-all: applied to every subpixel peak, global and patch.
- H2-global: applied to global alignment only.

No gain scaling, no DC change and no tolerance change in these arms, apart from the existing
diagnostic tolerance arm described below.

## Predictions (K267 eight cases, native CPU, unchanged checker, ROI and limits)

1. With flags off, products and metrics are identical to e77a51a2 / C1 CPU K267
   (1 PASS / 5 FAIL / 2 UNIDENTIFIABLE).
2. Integer and fractional (five-frame, global only): field RMS decreases versus flags-off under the
   production 5-iteration / 0.5 px stop. At least one of the two meets 0.20/0.40/0.80 A in both runtime
   and STAR under the 50-iteration / 1e-9 diagnostic budget.
   - Possible limit: the float32 pedestal deadzone (about 0.083 px steps) may leave a residual. If so,
     that is attributed to DC/pedestal quantisation and is not tuned here.
3. Affine still FAILS. The 0.343 px objective bias at truth is not a peak-arithmetic effect.
   Any affine improvement must be reported, but not as a cure.
4. Zero stays PASS. Flat and repeated stay UNIDENTIFIABLE.
5. Harm check: noisy and pedestal are reported in full. Any increase in RMS or max versus flags-off is
   listed as a regression, without a materiality threshold chosen after the fact.
6. CPU/CUDA agreement is not assessed (CPU-only prototype).

Falsification: if neither integer nor fractional improves under the production stop, or if H2 makes
noisy worse in RMS and max, H2 is not a candidate repair.
