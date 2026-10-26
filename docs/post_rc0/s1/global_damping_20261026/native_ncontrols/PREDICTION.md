# Native N controls and the harmful case: prediction (frozen before any code, movie or native run of this round)

Question: W6 (PR #278 head 34681942, offline replay) finds that DCg+H2g passes 15 of 16 W5 phase-ramp controls at each stop but turns the mandatory harmful case
vel1-N20-iso from PASS to FAIL in the map32 domain only. Neither offline domain reproduces native exactly, so the controls run natively.

What I had already seen: the W6 README and PREDICTION.md (including its results tables), the W5 round-2 `lib.py` and the W5 `intervention.py` that builds the controls.
I have seen no native result of these movies. The native arms on the K267 fixtures are from earlier rounds.

## Movies, arms, scoring (fixed here, not tuned)

- Movies: the W5 phase-ramp controls. Frame f is the W5 spectrum `shiftF(Ft, -f*vel)` of the pinned base image `integer_target.npy` (128 x 96), rendered to real space, N = 5, 9, 13, 20,
  vel0 = (-1, 2) and vel1 = (-0.8125, 0.53125) px/frame. Truth is the constant field `f*vel`. No noise, no content change.
- Arms (global only; no local fit): a (flags off); DCg (`MC_EXPERIMENT_CCF_DC_ARM=global`); H2g (`--experimental_coupled_peak global`); DCg+H2g.
  Stops: production (5 iterations, 0.5 px) and `--max_iter 50 --experimental_align_tolerance 1e-9`. Weights: native production weight, and `--experimental_isotropic_weight` (W5 `iso`), on all 8 movies.
- Scoring: the W5 convention reused as code (`common.score` / `common.field`, ROI y[12:84] x[12:116], 0.885 A/px, frame-zero gauge, limits 0.20 / 0.40 / 0.80 A), runtime (full-precision capture) and STAR separately.
  Trajectory RMS is `rms(estimated global shifts - f*vel)` in px, as in W5/W6.

## Predictions (P3 and P4 are W6's wording with "S-P / H-D" replaced by the native arms)

- **P3.** DCg+H2g at gain 1 does not regress any N = 9/13/20 control that passes at baseline, under either stop or weight. Operationally: no control with arm-a verdict PASS (runtime or STAR)
  has DCg+H2g verdict FAIL, evaluated natively against arm a on the same movie, weight and stop. A single PASS-to-FAIL falsifies P3. Numeric increases are listed separately.
- **P4.** The N=20 harmful case is not worse than baseline: DCg+H2g trajectory RMS <= arm a + 1e-6 px for vel1-N20-iso at the production stop (the 5-iteration case), natively. The 50-iteration case is also reported.
- **P5 (domain).** Native behaviour on the harmful case follows the map32 replay, not the double replay: native arm a passes vel1-N20-iso at both stops (map32 S-P: 0.054 / 0.012 A RMS)
  and native DCg and DCg+H2g fail it (map32: about 10.4 A RMS). If native arm a fails it (as the double replay says, 10.47 A), native follows the double domain. Rows are compared on PASS/FAIL
  of the runtime score, over all 32 control rows per arm, between each native arm and the same-named W6 arm (a=S-P, DCg=S-D, H2g=H-P, DCg+H2g=H-D); the domain with more agreeing rows is reported.
- **P6.** DCg+H2g passes every N = 5 control natively (both weights, both stops, both velocities, runtime and STAR), as in both W6 domains.

Also reported without prediction: every regression versus arm a (any RMS, p95 or max increase, runtime or STAR, no threshold), per-arm guard-fire counts for the H2 arms, DC manipulation counts, N = 9/13/20 prod and iso rows.

## Rules

No guard, stop, weight, gain, ROI, limit or scoring change after any result. The isotropic-weight flag exists only to run the W5 harmful comparator natively. If a code defect is found, the whole set is rerun and the
defect disclosed; this file is not edited after its commit.
