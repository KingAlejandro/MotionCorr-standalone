# Native N controls and the harmful case (W6 follow-up)

PR #278 (W6, offline replay) finds that DCg+H2g passes 15 of 16 W5 phase-ramp controls and loses the mandatory harmful case vel1-N20-iso only in the map32 domain. This round runs the controls
natively. Prediction frozen first: [PREDICTION.md](PREDICTION.md) (commit f6897956, before any code, movie or native run of this round).

**Result.** Natively DCg+H2g passes 15 of 16 controls at each stop (runtime and STAR agree in every row); the one failure is vel1-N20-iso, which **fails in all four native arms, including the flags-off baseline**
(a: 10.495 Å RMS at the production stop; the map32 replay predicted a PASS at 0.054 Å, the double replay a FAIL at 10.472 Å). So on the harmful case native behaviour follows the double replay.
P3 and P4 hold natively (no PASS-to-FAIL for DCg+H2g; trajectory RMS 11.8586 to 11.7542 px, still FAIL); the P5 domain prediction (native follows map32) is falsified; P6 holds. DCg+H2g agrees with both replays on all 32 rows;
the other arms do not follow either replay consistently (details below). Research evidence only: one 128 x 96 base image, global alignment only, no local fit, CPU only.

## 1. Movies (W5 controls rendered as native input)

W5 defines the controls in `w5_intervention_20261025/scripts/intervention.py` (probes block): base image `fixtures/integer_target.npy` (sha256 `287e0a82...`, identical to the regenerated K267 fixture),
`Ft = fft2(base)/(NX*NY)`, frame f spectrum `shiftF(Ft, -f*vel)` (`shiftF` from the pinned independent review's `indep.py`, sha256 in `results/nc/movies/render_report.json`), vel0 = (-1, 2), vel1 = (-0.8125, 0.53125) px/frame,
N = 5, 9, 13, 20, truth = the constant field `f*vel`. `scripts/render_ncontrols.py` loads W5's own code in place (W5 scratch on cpu64, read-only, `common.verify()` pins every input), takes the real part of the inverse transform
and writes the repo's `write_mrc_stack` MRC (mode 2, float32, un-flipped) and `STAR_TEMPLATE` STAR. Nothing else is added (no noise, no content change).

| Check | Result |
|---|---|
| Independent re-render (a separate formula, no W5 code) vs the W5-code frames | max abs diff 4.3e-14 |
| Imaginary part discarded when taking the real part | max 1.1e-06 (vel1), 1.2e-15 (vel0) |
| Stored float32 frames vs the W5 float64 frames | vel0: 0 (integer shifts, exact); vel1: max abs diff 3.8e-06 (float32 rounding of values near 100) |
| sha256 of the W5 float64 frames and of the written files, per movie | `results/nc/movies/render_report.json` |
| W5 replay (`indep.py` `replay`, prod and iso weight, 5 / 50 iterations) on the W5 spectra vs W5 `factorial.json` trajectories | max 0.0 px (all 64 probes) |
| The same replay on the stored frames vs on the W5 spectra | vel0: 0.0 px; vel1: at most 2.0e-03 px (vel1-N5 prod 50 it), otherwise below 5e-07 px |
| Row order / format null control | frame 0 equals the base image exactly (max diff 0.0); flipud differs by 4.42 and fliplr by 4.00, so a flip would be seen; MRC read-back equals what was written |
| Movie vs the K267 `integer.mrcs` (same motion: vel0 N=5 is the retained integer case) | 5 of 61,440 pixels differ, by one float32 ulp (7.6e-06) |
| Native `vel0-N5-prod` vs the K267 `integer` arms | flags-off and H2g bit-identical (0.2636 / 0.3927 and 0.4461 / 0.3786 Å); DCg and DCg+H2g within 3e-5 Å at the production stop; DCg at 50 iterations 0.378 Å here against 0.234 Å there |

The last row says: the movies are the retained fixture to float32 rounding, and the DCg-alone 50-iteration trajectory is sensitive to a one-ulp input change (it is not a stable quantity here).

## 2. `--experimental_isotropic_weight` (source `20e52f57`)

W5 `lib.py` `iso` is the production weight with the x frequency divided by `nx` instead of `nx//2 + 1`. Native check before implementing: `alignPatch` builds `exp(-2 * dist2 * scaled_B)` with `dist2 = (ly/nfy)^2 + (x/nfx)^2`, `nfx = nx/2 + 1`, `ly` the
signed row frequency and `scaled_B = 150`; W5 `prod` is `exp(-2B((ky/NY)^2 + (|kx|/(NX//2+1))^2))` with B = 150 (`-300 * ...`). **No difference found** for the production weight: same normalisations, same B, same signed `ly` (at the Nyquist
row the sign differs but only squares enter), and for 128 x 96 the CCF is not down-sampled (`ccf_downsample` auto gives 192 > 128, so no crop) and the search range is 47 in both. Iso therefore differs from native prod only in x: `x_norm = pnx` instead of `nfx`.

The flag applies to the global alignment only (patch weights unchanged), is CPU-only (refused with `--gpu` before the device query, rejected without `--use_own`; covered by `ExperimentalFlagsCli`). To make the weight and the choice testable the weight expression was moved unchanged into
`MotioncorrRunner::ccfWeightAt` and the selection into `ccfWeightXNorm`; flags-off identity was re-verified on the rebuilt source (below).
`IsotropicWeight` checks `ccfWeightAt` against W5 reference values (7 bins, relative 1e-12, prod with `x_norm` 65 and iso with 128, computed from the W5 formulas), the `x_norm` selection, and through `alignPatch` that the flag changes the global estimate, leaves the
unflagged result bitwise unchanged and leaves a patch alignment unchanged. Five mutants (flag ignored, wrong normalisation, leak to patches, formula factor, prod norm hard-coded) are all killed (`scripts/mutants_h5.sh`); a first version of the test let the wrong-normalisation
mutant survive, so the selection was made testable and the whole chain rerun (attempt 1 kept in `attempt1/`; its 128 scored rows are identical to the rerun's).

Flags-off / DC-off identity with the rebuilt source (`build-h5off` `149a2928...`, `build-h5on` `a7db45df...`): full CPU CTest 94 tests (93 passed, 1 skipped for pbzip2, 0 failed) and 95 tests (94 passed, 1 skipped, 0 failed); known-motion trees (193 files, 88 gated) and the synthetic movie (14 / 7) IDENTICAL to e77a51a2 for both builds; capture on identical to capture off; DC global and half-gain on still change the products.

## 3. Native arms and scoring

128 native runs (`scripts/run_ncontrols.py`; the K267 command line with `--patch_x 1 --patch_y 1 --last_frame_sum N`, `--j 2`, CPUs 48-55 under the lane lock, hook binary with `MC_EXPERIMENT_CCF_DC_ARM` set on every run and `MC_DIAG_MODEL_OUT` capture): 4 arms
(a; DCg = ARM global; H2g = `--experimental_coupled_peak global`; DCg+H2g) x 2 stops (production; `--max_iter 50 --experimental_align_tolerance 1e-9`) x 2 weights (production; `--experimental_isotropic_weight`) x 8 movies. All exited 0.
Scored by `scripts/score_ncontrols.py`, which imports the W5 `common.py` (`score`, `field`, `rms`) unchanged: ROI y[12:84] x[12:116], 0.885 Å/px, frame-zero gauge, limits 0.20 / 0.40 / 0.80 Å; runtime from the capture, STAR from the serialized file.
Runtime and STAR verdicts agree in all 128 rows (max difference 5.0e-06 px). DC manipulation: DCg arms zero 10,068/10,068 and DCg+H2g 10,048/10,048 global CCF frames and 0/0 patch frames (no patch alignment runs); arms a and H2g zero 0 of 8,130 / 8,768.

Controls passing all limits (runtime and STAR), of 16 per stop:

| Stop | a | DCg | H2g | DCg+H2g |
|---|---|---|---|---|
| production | 7 | 6 | 8 | 15 |
| 50 / 1e-9 | 9 | 13 | 7 | 15 |

Native N-control table (runtime RMS Å and verdict; P = PASS, F = FAIL; STAR gives the same verdict in every cell; p95 and max in `results/nc-scores.json`):

| Control | Stop | a | DCg | H2g | DCg+H2g |
|---|---|---|---|---|---|
| vel0-N5-prod | prod | 0.264 F | 0.519 F | 0.446 F | 0.074 P |
| vel0-N5-prod | long | 0.393 F | 0.378 F | 0.379 F | 0.000 P |
| vel0-N9-prod | prod | 0.384 F | 0.567 F | 0.505 F | 0.027 P |
| vel0-N9-prod | long | 0.304 F | 0.052 P | 0.954 F | 0.000 P |
| vel0-N13-prod | prod | 0.274 F | 0.283 F | 0.204 F | 0.003 P |
| vel0-N13-prod | long | 0.382 F | 0.001 P | 0.288 F | 0.000 P |
| vel0-N20-prod | prod | 0.300 F | 0.304 F | 0.234 F | 0.003 P |
| vel0-N20-prod | long | 0.152 P | 0.000 P | 0.432 F | 0.000 P |
| vel1-N5-prod | prod | 0.524 F | 0.326 F | 0.496 F | 0.030 P |
| vel1-N5-prod | long | 0.429 F | 0.314 F | 0.359 F | 0.000 P |
| vel1-N9-prod | prod | 0.552 F | 0.392 F | 0.163 P | 0.007 P |
| vel1-N9-prod | long | 0.338 F | 0.059 P | 0.582 F | 0.000 P |
| vel1-N13-prod | prod | 0.363 F | 0.237 F | 0.209 F | 0.003 P |
| vel1-N13-prod | long | 0.321 F | 0.001 P | 0.236 F | 0.000 P |
| vel1-N20-prod | prod | 0.222 F | 0.247 F | 0.286 F | 0.002 P |
| vel1-N20-prod | long | 0.198 P | 0.000 P | 0.433 F | 0.000 P |
| vel0-N5-iso | prod | 0.070 P | 0.034 P | 0.068 P | 0.082 P |
| vel0-N5-iso | long | 0.017 P | 0.000 P | 0.032 P | 0.000 P |
| vel0-N9-iso | prod | 0.051 P | 3.888 F | 0.052 P | 0.011 P |
| vel0-N9-iso | long | 0.030 P | 0.000 P | 0.022 P | 0.000 P |
| vel0-N13-iso | prod | 0.041 P | 0.016 P | 0.034 P | 0.001 P |
| vel0-N13-iso | long | 0.011 P | 0.000 P | 0.008 P | 0.000 P |
| vel0-N20-iso | prod | 0.038 P | 0.036 P | 0.031 P | 0.003 P |
| vel0-N20-iso | long | 0.021 P | 0.000 P | 0.024 P | 0.000 P |
| vel1-N5-iso | prod | 0.064 P | 0.043 P | 0.052 P | 0.034 P |
| vel1-N5-iso | long | 0.014 P | 0.000 P | 0.025 P | 0.000 P |
| vel1-N9-iso | prod | 0.037 P | 0.036 P | 0.039 P | 0.009 P |
| vel1-N9-iso | long | 0.018 P | 0.000 P | 0.019 P | 0.000 P |
| vel1-N13-iso | prod | 0.037 P | 0.024 P | 0.027 P | 0.004 P |
| vel1-N13-iso | long | 0.008 P | 0.000 P | 0.013 P | 0.000 P |
| vel1-N20-iso | prod | 10.495 F | 10.472 F | 10.471 F | 10.402 F |
| vel1-N20-iso | long | 10.515 F | 10.467 F | 10.453 F | 10.403 F |

## 4. The harmful case, vel1-N20-iso (runtime RMS / p95 / max Å, verdict; trajectory RMS px)

Production stop:

| Arm | Native | Trajectory RMS px | W6 double | W6 map32 |
|---|---|---|---|---|
| a | 10.495 / 14.853 / 14.860 FAIL (STAR FAIL) | 11.8586 | 10.472 FAIL | 0.054 PASS |
| DCg | 10.472 / 14.811 / 14.811 FAIL (STAR FAIL) | 11.8328 | 10.472 FAIL | 10.472 FAIL |
| H2g | 10.471 / 14.831 / 14.834 FAIL (STAR FAIL) | 11.8318 | 10.402 FAIL | 0.021 PASS |
| DCg+H2g | 10.402 / 14.711 / 14.711 FAIL (STAR FAIL) | 11.7542 | 10.402 FAIL | 10.402 FAIL |

50 iterations / 1e-9:

| Arm | Native | Trajectory RMS px | W6 double | W6 map32 |
|---|---|---|---|---|
| a | 10.515 / 14.875 / 14.875 FAIL (STAR FAIL) | 11.8812 | 10.467 FAIL | 0.012 PASS |
| DCg | 10.467 / 14.803 / 14.803 FAIL (STAR FAIL) | 11.8276 | 10.467 FAIL | 10.467 FAIL |
| H2g | 10.453 / 14.802 / 14.803 FAIL (STAR FAIL) | 11.8109 | 10.403 FAIL | 0.022 PASS |
| DCg+H2g | 10.403 / 14.712 / 14.712 FAIL (STAR FAIL) | 11.7546 | 10.403 FAIL | 10.403 FAIL |

All four native arms fail at both stops. DCg+H2g reproduces W6's 10.402 / 10.403 Å (both domains); native DCg reproduces the double S-P value (10.472 / 10.467 Å), which is the same as W6's S-D in both domains; native a (10.495 / 10.515 Å) is close to the double replay (10.472 / 10.467), not to map32 (0.054 / 0.012).

## 5. Prediction scorecard

| # | Prediction (frozen) | Native result | Verdict |
|---|---|---|---|
| P3 | No N = 9/13/20 control that passes under arm a fails under DCg+H2g (runtime or STAR), any stop or weight | 0 violations over the 12 cells where a passes (runtime and STAR) | **confirmed** natively (W6: falsified in map32) |
| P4 | vel1-N20-iso at the production stop: DCg+H2g trajectory RMS <= a + 1e-6 px | 11.754152 vs 11.858575 px: holds (both FAIL; 50 iterations 11.7546 vs 11.8812) | **confirmed** (the harmful case is not a PASS-to-FAIL natively because a already fails) |
| P5 | Native follows map32 on the harmful case: a passes at both stops, DCg and DCg+H2g fail | a **fails** at both stops (10.495 / 10.515 Å) | **falsified**: native follows the double replay on the harmful case |
| P6 | DCg+H2g passes every N = 5 control (both weights, stops, velocities; runtime and STAR) | all 16 N = 5 cells pass | **confirmed** |

P5 row comparison (runtime PASS/FAIL agreement with the same-named W6 arm, 32 rows per arm): double 28 / 31 / 17 / 32 and map32 28 / 30 / 19 / 32 for a / DCg / H2g / DCg+H2g, i.e. 108 against 109 of 128: a tie. Within it: **DCg+H2g matches both replays in every row** (and its RMS is within 20% in all 32 rows for both);
arm a disagrees with each replay in 4 rows (double: the N=9/13 production-weight 50-iteration rows where the replay passes and native fails; map32: vel1-N20-iso at both stops and vel0/vel1-N13 production-weight 50 iterations), and its RMS is within 20% of map32 in 21 rows against 15 for double;
H2g alone matches map32 better (RMS within 20% in 17 rows against 5; verdict agreement 19 against 17) and agrees with neither well, as in the earlier H2 rounds. Native follows neither replay as a whole: the harmful row follows double, baseline magnitudes and H2g follow map32 more, DCg+H2g follows both.

## 6. Regressions versus arm a (any increase in RMS, p95 or max, runtime or STAR, no threshold; `results/nc-scores.json`, `regressions`)

48 rows (24 cells, each listed once for runtime and once for STAR with identical values): H2g 16 cells, DCg 7 cells, DCg+H2g 1 cell. Verdict losses (PASS to FAIL): DCg at vel0-N9-iso production stop (0.051 to 3.888 Å RMS), and H2g at vel0-N20-prod and vel1-N20-prod at 50 iterations (0.152 to 0.432 and 0.198 to 0.433 Å; W6 had the same two losses for H-P in map32). **DCg+H2g has one increase: vel0-N5-iso at the production stop, RMS 0.070 to 0.082, p95 0.110 to 0.126, max 0.110 to 0.126 Å, PASS to PASS** (W6: 0.035 / 0.051 to 0.082 in double / map32).
Guard (DCg+H2g, global peaks): 8 fires in 10,048 peaks, all offset > 1 px, in vel0-N9 and vel0-N20 production weight (2 each, both stops); H2g alone 95 in 8,768 (15 not negative definite, 80 offset > 1 px).

## Limits

Global alignment only, one base image, constant-velocity phase-ramp movies without noise (diagnostic, not gate-role fixtures); several long trajectories put truth outside the fixed ROI (as in W5). CPU only; no CUDA run, so CPU/CUDA agreement and the CUDA refusal on a CUDA build are UNRUN.
The isotropic weight is a W5 comparator, not a candidate option. The sensitivity of DCg alone (50 iterations) to one-ulp input changes (section 1) means single rows of that arm should not be over-read. The noisy production-stop regression diagnosis of the previous round is unchanged.
