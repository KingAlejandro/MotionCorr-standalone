# W6 round 2: harmful-case mechanism and P5 check

**Mechanism.** vel1-N20-iso fails by capture at iteration 1, and the capture is specific to the iso
weight. From the zero start, each frame is correlated against the sum of the other 19 frames, which
is smeared along a 15 x 10 px line. Under iso that CCF has near-equal maxima at the two ends of the
smear, and the leave-one-out centroid between them is not a maximum. At iteration 1 every one of the 20
frames takes an integer peak 4-5 px from the ideal displacement, in every arm and in double. The run
then settles into an exact period-2 cycle rather than a fixed point. Frames 1-9 and 19 sit one iso
autocorrelation alias, (-11.0, 12.6) px, away from the other frames, and that offset changes sign
every iteration. Updates stay at 23.7 px RMS while the error stays at 11.8 px. The same trajectory
under prod picks the centroid (every frame within 1 px) and converges. Hypothesis (ii), a single
overshoot transient, is rejected: the large updates never decay.

**Why map32 S-P escapes.** At iteration 1, frame 0 is the anchor frame, since every update is
peak_f - peak_0. Its float32 CCF carries the pedestal (about 190025, ulp 0.0156). Its top three local
maxima are exactly tied at 190024.859375: (13,-11), (12,-10) and (4,-1). The row-major scan takes
(13,-11). With DC zeroed, the same maxima are 2604 ulps apart, and map32 then takes (4,-1), as double
does. This is where map32 S-P and map32 H-D first diverge: iteration 1, frame 0, from an identical
state. That changes all 19 updates by (-9, +10), and from there iteration 2 reaches 0.17 px. No frame
was frozen in the dead zone. The escape therefore rests on the scan-order tie-break at the anchor
frame. Whether the opposite tie-break would also escape is untested.

**P5.** The brief's expectation that iteration-1 peaks agree to about 1e-12 px does not hold. For the
three vel0 rows they differ by 1.7-12 px at iteration 1. This is not a replay defect. These controls
have integer velocity, so for end and middle frames the CCF is exactly symmetric about the
leave-one-out centroid. The two maxima are then tied in exact arithmetic: 0-3 ulps apart, mirror
images about the centroid, with the map symmetric to within 1-7 ulps. Rounding chooses between them,
and removing the DC constant changes the rounding. For the pedestal fixture, the brief's explanation
holds with a larger starting error. The iteration-1 difference is 1.85e-5 px, the same order as the
expected rounding scale at that pedestal level (eps·|peak|/|curvature| = 1.26e-5 px). It then grows
by 1.196 per iteration, matching the separable N=5 unstable eigenvalue |-1.1925|, to 0.07 px by
iteration 46. Integer-argmax flips at iteration 50 take it to the final 0.70 px.

Offline NumPy replay only. No native, GPU or CUDA run.

## Prediction scorecard ([PREDICTION.md](PREDICTION.md), commit a51133de)

| # | Result | Verdict |
|---|---|---|
| M1 capture | Iteration 1: all 20 frames >= 4 px off in double iso, every arm. Endpoint frame errors lie within 0.46 px of the iso autocorrelation lattice. A start at truth stays at truth in every arm and domain, for both weights. A 50% start passes in every iso arm in both domains, at both stops | confirmed |
| M2 no later step exceeds iteration 1 | Raw update RMS goes 11.37, 19.91, 23.20, 23.70 px and stays there (max frame 33.6 px) | **falsified** |
| M3 prod picks within 1 px; prod sidelobe lower | Double and map32 DC arms: max deviation 1 px. map32 S-P/H-P: 7 frames >= 2 px off at iteration 1, but they recover. Largest secondary autocorrelation maximum: prod 0.895, iso 0.913 | confirmed except the map32 pedestal arms |
| M4 map32 divergence early, not a dead-zone freeze | S-P vs H-D and S-P vs S-D: first argmax and subpixel divergence at iteration 1, frame 0, same state. S-P vs H-P: subpixel at (1, 2), argmax at (2, 2). No zero-update frames | confirmed |
| M5 iteration-1 peaks within 1e-9 px | vel0-N13-prod 8.98 px, vel0-N9-prod 1.68 px, vel0-N13-iso 12.2 px, pedestal 1.85e-5 px | **falsified**. Exact ties (vel0) and pedestal-scale rounding; no replay defect |
| M6 a jump at an argmax flip, not smooth growth | vel0 rows: argmax flip at iteration 1 (frames 6,12 / 0,8 / 6). Pedestal: smooth growth at 1.196/iteration for 49 iterations, then argmax flips at iteration 50 | **falsified** as a general claim (true for vel0, not pedestal) |

Mechanism verdict against the brief's options: (i) capture holds, and (iii) iso-specificity holds as
its cause. (ii) is rejected as a single transient; the large steps are a sustained period-2 alias
cycle. The 19.9 px iteration-2 RMS step here is the first step of that cycle, not a separate
transient.

## Harmful case per iteration (vel1-N20; raw update RMS px, max frame px, frames >= 2 px off, error after px)

| Run | Iteration 1 | 2 | 3 | 4 | Final error / endpoint update RMS (50 it) |
|---|---|---|---|---|---|
| iso double S-P | 11.37, 18.1, 20, 8.60 | 19.91, 28.9, 20, 11.34 | 23.20, 33.1, 20, 11.87 | 23.70, 33.6, 20, 11.84 | 11.828 / 23.655 |
| iso double H-D | 11.34, 18.1, 20, 9.16 | 20.58, 29.8, 20, 11.43 | 23.15, 32.8, 20, 11.72 | 23.47, 33.2, 20, 11.75 | 11.755 / 23.509 |
| iso map32 S-P | 19.52, 31.2, 20, 9.54 | 9.44, 14.8, 20, 0.171 | 0.166, 0.24, 0, 0.062 | 0.066, 0.12, 0, 0.027 | 0.0136 / 0.0168 |
| iso map32 H-D | matches iso double H-D (raw update RMS within 2e-5 px every iteration) | | | | 11.755 / 23.509 |
| prod double S-P | 11.34, 18.8, 0, 1.20 | 1.39, 2.7, 0, 0.36 | 0.25, 0.4, 0, 0.28 | 0.21, 0.3, 0, 0.21 | 0.00004 / 0.0001 |
| prod double H-D | 11.62, 19.4, 0, 1.16 | 1.22, 2.0, 0, 0.062 | 0.064, 0.1, 0, 0.002 | 0.002, 0.0, 0, 0.000 | 0.000 / 0.000 |
| prod map32 S-P | 11.39, 18.9, 7, 1.25 | 1.38, 2.9, 0, 0.31 | 0.35, 1.2, 0, 0.28 | 0.23, 0.5, 0, 0.22 | 0.158 / 0.221 |

The ideal first update from zero, N/(N-1)·t_f, has RMS 11.35 px. Iteration 1 under iso has the right
size and the wrong peaks. Frame 0 under iso has argmax (4,-1) against an ideal of (8.1,-5.3); its two
top maxima, (4,-1) and (13,-11), differ by 1.7e-4 of the AC peak in double. The period-2 cycle is
exact: the state at iteration 41 equals the state at iteration 43. Iso autocorrelation local maxima
include (-11,13) at 0.899 of the central peak; the largest is (±17,±29) at 0.913.

## map32 divergence point (iteration 1, frame 0, identical zero state)

| | map32 S-P (pedestal) | map32 H-D (DC zeroed) | double S-P |
|---|---|---|---|
| Top maxima | (13,-11), (12,-10), (4,-1): all 190024.859375 | (4,-1) 7.379167, (13,-11) 7.377925, (-47,9) 7.087054 | (4,-1) 15.4642632567, (13,-11) 15.4642631557 |
| ulp at peak / top-two gap | 0.015625 / 0 ulps | 4.8e-7 / 2604 ulps | AC gap 1.0e-7 |
| Chosen argmax, peak | (13,-11), (13.100, -10.643) | (4,-1), (3.633, -0.314) | (4,-1) |

3x3 values at each argmax are in `results/mech.json` (`map32_divergence`).

## P5 per iteration (double, max over frames)

| Row | Iteration-1 peak difference | Argmax differs | Final |
|---|---|---|---|
| vel0-N13-prod-5it S-P vs S-D | 8.98 px | iteration 1 frames 6, 12; iteration 2 all 13; iteration 3 nine frames | 0.703 px |
| vel0-N9-prod-5it S-P vs S-D | 1.68 px | iterations 1-2, frames 0, 8 | 0.325 px |
| vel0-N13-iso-5it H-P vs H-D | 12.2 px | iteration 1 frame 6; iterations 2-3 several | 0.0154 px |
| pedestal-50it S-P vs S-D | 1.85e-5 px | none until iteration 50 (frames 1, 2) | 0.704 px |

Tie check (`results/tie_check.json`), iteration-1 zero-state double maps: each flipped frame's top two
maxima are a mirror pair about the centroid, 0-3 ulps apart, and the map is symmetric to within 1-7
ulps. This holds with and without the pedestal.

## Provenance

Prediction a51133de. Scripts frozen in [FREEZE.json](FREEZE.json); the launcher's script name was
corrected and re-frozen before the run (0ba41bd9). `mech.py` ran once, exit 0, 30.9 s.
Its 32 logged vel1-N20 runs equal the W6 trajectories bit for bit (`checks`), and `W6Estimator` is
taken verbatim from W6 `scripts/w6.py` (hash-pinned). `tie_check.py` was written after `mech.json` was
seen, ran once (exit 0) and changes no result; it is not frozen. Both ran on cpu64, `taskset -c 40-47`
under `flock -n /tmp/motioncorr-w6-cpu40-47.lock`, one BLAS/OpenMP thread, NumPy 2.5.3 / Python
3.12.3, in the existing scratch /tmp/motioncorr-w6-20261026 (under 40 MB).

```sh
ssh cpu64 'flock -n /tmp/motioncorr-w6-cpu40-47.lock taskset -c 40-47 ~/.mc-venv/bin/python -I -B /tmp/motioncorr-w6-20261026/w6_dc_coupled_peak_20261026/round2/scripts/run_once.py mech'
ssh cpu64 'flock -n /tmp/motioncorr-w6-cpu40-47.lock taskset -c 40-47 ~/.mc-venv/bin/python -I -B /tmp/motioncorr-w6-20261026/w6_dc_coupled_peak_20261026/round2/scripts/tie_check.py'
```
