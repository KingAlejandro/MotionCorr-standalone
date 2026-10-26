# W6: offline DCg+H2g on the W5 controls (frozen before any W6 computation)

Written 2026-10-26 by an independent worker (Opus 5.5) that did not author the candidate,
before any W6 code or result exists. This file is not edited after this commit.

## Candidate (PR #286, branch experiment/global-damping-20261026, head 16442167)

DCg+H2g, global alignment only, gain 1:
- DCg: the (0,0) bin of the global CCF spectrum is set to zero before the inverse FFT
  (native `experimentCcfDcZero` call site in `alignPatch`).
- H2g: the separable parabola is replaced by the coupled 2x2-Hessian quadratic on the same 3x3
  neighbourhood, mirroring native `coupledPeakOffset`: g central first differences,
  H_xx/H_yy second differences, H_xy = (c[+1,+1] - c[+1,-1] - c[-1,+1] + c[-1,-1])/4,
  offset = -H^{-1} g. Guard: keep the separable result unless H_xx < 0 and det H > 0 and
  |offset| <= 1 px in each component. Guard firings are counted and reported.
- Patch peaks, patch CCF DC, weights, search window, stop rule, fit and scoring are unchanged.
  The guard is fixed by the native source and is not tuned.

## Framework (reused, not modified)

W5 round 2 (`w5_intervention_20261025/round2/scripts/lib.py`, SHA256 e47e05a2..., as bound in
round2/SHA256SUMS): `Estimator` (double map, or `map32` = unnormalised CCF rounded to float32
after NumPy double FFT), `patch_fit`, `field_result` (W5 runtime and STAR scoring, fixed ROI
y[12:84] x[12:116], 0.885 A/px, limits 0.20/0.40/0.80 A RMS/p95/max). map32 is not native CPU
arithmetic; it rounds only the CCF map. No native, GPU or CUDA run.

## Arms and cases

Arms {separable, H2} x {pedestal, DC-zeroed}, gain 1, global only:
S-P (baseline, inherited), S-D (DCg alone), H-P (H2g alone), H-D (candidate DCg+H2g).
Domains: double and map32. Stops: production 5 iterations / 0.5 px, diagnostic 50 / 1e-9.

- Phase-ramp controls: vel0 = (-1, 2), vel1 = (-0.8125, 0.53125) px/frame, N = 5/9/13/20,
  prod and iso weights, both stops, both domains (the W5 probes ran double only; the map32
  S-P probe baseline is new and is labelled as such).
- Harmful counterexample: vel1-N20-iso-5it (11.832823 px trajectory RMS at baseline, double);
  50 iterations also reported.
- Retained five-frame fixtures through the round-2 offline pipeline (global + unchanged patch
  fit): zero, integer, fractional, affine, pedestal, noisy, flat, repeated. The round-1
  noisy STAR-observation sensitivity case holds the captured native global trajectory fixed,
  so a global-peak change cannot act on it; the round-2 full replay of `noisy.mrcs` is the
  noisy harm case instead.
- Local fixtures at the diagnostic stop: the framework convention passes 50 / 1e-9 to the patch
  fit as well, which leaves a NULL local model (noted in the E1 review). Primary rows keep that
  convention for baseline identity. A secondary, labelled `patch-native` row runs patches at
  50 iterations / 0.5 px, which is the native `--max_iter 50 --experimental_align_tolerance 1e-9`
  semantics. No other tolerance is introduced.

## Validation before any arm is scored

- S-P must reproduce the W5 round-2 gain-1 fixture arms (double and map32, both stops) and the
  32 W5 double phase-ramp probes, trajectories within 1e-5 px (target: exact), including the
  11.832823 px harmful case.
- The W6 estimator with both flags off must equal the unmodified lib `Estimator` bit for bit.
- The stored float32 patch-map peak replay (round 2 control) must still hold to 1e-6 px.
- The double S-P Jacobian at truth (N=5, prod, vel0) must reproduce round-2 eigenvalues
  0.698524 / -1.192520 within 1e-6.

## Predictions

- **P1.** map32 with the pedestal reproduces the native finding that H2 alone does not help
  integer/fractional, while map32 with DC zeroed plus H2 does. Operationally: map32 H-P leaves
  integer and fractional FAIL at both stops (runtime and STAR), and map32 H-D makes both PASS all
  three limits in runtime and STAR at both stops. Either part failing falsifies P1.
- **P2.** Double-domain eigenvalues for H2 at gain 1 are about -0.23/-0.25 at N=5, stable.
  Operationally: the central-difference Jacobian at truth (eps 1e-3 px, N=5, prod, vel0 and
  vel1) has eigenvalues within 0.01 of -0.228752 and -0.249565 and spectral radius < 1.
- **P3.** DC+H2 at gain 1 does not regress any N=9/13/20 control that passes at baseline, under
  either stop or weight. Operationally: no control with S-P verdict PASS (runtime or STAR) has
  H-D verdict FAIL, evaluated in double and in map32 against the same-domain baseline. A single
  PASS-to-FAIL in either domain falsifies P3. Numeric increases are listed separately.
- **P4.** The N20 harmful case is not worse than baseline: H-D trajectory RMS <= S-P + 1e-6 px
  for vel1-N20-iso-5it, in each domain against that domain's S-P.
- **P5 (added).** In double, DC zeroing only subtracts a constant from the map, so S-D equals S-P
  and H-D equals H-P within 1e-6 px final trajectory on every phase-ramp control and every
  identifiable fixture, at both stops. Flat and repeated are reported, not predicted.
- **P6 (added).** map32 N=5 prod vel0 Jacobian at truth: with the pedestal, both S-P and H-P are
  the identity (all eigenvalues 1 within 1e-6; the float32 dead zone); with DC zeroed, H-D
  eigenvalues are within 0.05 of the double H2 values.
- **P7 (added).** In double, H2 (H-P = H-D by P5) makes integer and fractional PASS at both stops.
- **P8 (added).** The native production-stop noisy harm reproduces offline: map32 H-D noisy at
  5 iterations is worse than map32 S-P in both RMS and max (runtime and STAR).

Also reported, without prediction: affine, pedestal, zero (expected to stay PASS), flat and
repeated (stay UNIDENTIFIABLE), guard firing counts per run, the H2 Jacobian eigenvalues for
N=9/13/20 and iso weight, and every increase in RMS, p95 or max of any arm versus same-domain
S-P, listed individually with no materiality threshold.

## Rules

No fixture, tolerance, ROI, limit, weight or scoring change. No floor subtraction. No guard or
gain change after results. One frozen run; a code defect found afterwards is fixed only with a
disclosed rerun of the whole set, and this file is not edited.
