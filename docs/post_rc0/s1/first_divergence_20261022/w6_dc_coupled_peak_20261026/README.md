# W6: DCg+H2g on the W5 offline controls

**Result.** DCg+H2g (global CCF DC bin zeroed, coupled 2x2 peak, gain 1) passes 15 of 16 phase-ramp
controls at each stop in both offline domains, including every N=5 and every production-weight
control. It passes integer and fractional at both stops in both domains, and affine at the
production stop. The mandatory harmful counterexample, vel1-N20-iso, still fails under the candidate in
both domains. In map32 the separable baseline passes that case (0.054 Å RMS), so the candidate turns a
PASS into a 10.40 Å failure. DC zeroing alone (S-D) causes the same loss, so the loss comes from
pedestal removal, not from H2. In double, the production-stop noisy harm seen natively reproduces:
noisy goes from 1.668 to 3.014 Å RMS and from 7.14 to 20.78 Å max. Predictions P2, P6 and P7 are
confirmed. P1, P3, P4, P5 and P8 are falsified.

This is an offline NumPy replay and not a native, CUDA or adoption result. The map32 domain does
not reproduce the native H2-alone failure (P1 below), so neither domain is a validated model of
native CPU arithmetic for these controls.

## What was run

Frozen prediction: [PREDICTION.md](PREDICTION.md), commit c9f097da, written before any W6 code.
[FREEZE.json](FREEZE.json) binds it, `scripts/w6.py` and `scripts/run_once.py` (commit 655f5ab9,
before the run). One run, exit 0. `scripts/report.py` is saved-result processing added afterwards.

- Framework: W5 round-2 `lib.py` imported unchanged (SHA256 e47e05a2…, as listed in
  round2/SHA256SUMS). It and round-2 `run_once.py` were never committed to git; byte-identical copies
  from the retained cpu64 scratch are in [framework/round2-scripts/](framework/round2-scripts/).
- Only the global estimator is subclassed (`W6Estimator`). The H2 peak mirrors native
  `coupledPeakOffset` at PR #286 head 16442167, including the guard (H_xx < 0, det > 0, |offset| <= 1
  px per component, else the separable result). DCg sets the CCF spectrum (0,0) bin to zero before
  the inverse FFT. Patch peaks, the patch CCF, weights, search, stop rule, 18-term fit, ROI
  y[12:84] x[12:116], 0.885 Å/px and the 0.20/0.40/0.80 Å limits are unchanged. No floor is
  subtracted.
- Arms: S-P (baseline), S-D (DCg only), H-P (H2g only), H-D (candidate). Domains: double, and map32
  (CCF map rounded to float32 after the NumPy double FFT). Stops: 5 iterations / 0.5 px and 50 / 1e-9.
- Cases: the 32 W5 phase-ramp controls (vel0/vel1, N=5/9/13/20, prod/iso, both stops) in each domain,
  and the eight retained five-frame fixtures through the round-2 offline pipeline. The round-1
  noisy STAR-observation case fixes the captured native global trajectory, so a global-peak change
  cannot act on it. The round-2 full replay of `noisy.mrcs` is used as the noisy harm case.
  Local fixtures at 50 iterations have an extra `patch-native` row (patches 50 / 0.5 px, the native
  `--max_iter 50` semantics), because the framework passes 1e-9 to the patch fit, which leaves a NULL
  local model.

## Validation (all exact)

| Check | Result |
|---|---|
| S-P vs W5 round-2 gain-1 fixture arms (8 cases x 2 domains x 2 stops: trajectory, coefficients, runtime/STAR metrics) | max difference 0.0 |
| S-P vs the 32 W5 double phase-ramp probes | max 0.0 px |
| Harmful baseline vel1-N20-iso-5it | 11.832822522791 px trajectory RMS, runtime 10.472048 / 14.810680 / 14.811067 Å |
| W6 estimator with both flags off vs unmodified lib `Estimator` (all 96 S-P runs) | bitwise equal |
| Stored float32 patch-map peak replay (lib and W6) | 0.0 px |
| Double S-P Jacobian at truth vs round 2 (N=5 prod, vel0 and vel1) | max 0.0; eigenvalues 0.698524 / -1.192520 |

## Prediction scorecard

| # | Prediction (operational form frozen in PREDICTION.md) | Result | Verdict |
|---|---|---|---|
| P1 | map32 + pedestal: H2 does not make integer/fractional PASS; map32 DC + H2 makes both PASS at both stops | H-P **passes** integer (0.182 / 0.071 Å RMS at 5 / 50 it) and fractional (0.086 / 0.096 Å). H-D passes both (integer 0.074 / 0.000006, fractional 0.030 / 0.000006 Å) | **falsified** (first part). map32 does not reproduce the native H2-alone failure |
| P2 | Double H2 Jacobian at truth, N=5 prod: eigenvalues within 0.01 of -0.2288 / -0.2496, stable | -0.228753 / -0.249565 for vel0 and vel1, spectral radius 0.2496, no imaginary part | confirmed |
| P3 | No N=9/13/20 control passing at S-P fails under H-D, either stop/weight/domain | 64 baseline-PASS scores checked. 4 lost, all **vel1-N20-iso map32** (5 it and 50 it, runtime and STAR): 0.054 to 10.402 Å and 0.012 to 10.403 Å RMS | **falsified** (map32). Double: no loss |
| P4 | Harmful vel1-N20-iso-5it: H-D <= S-P + 1e-6 px in each domain | Double: 11.754153 vs 11.832823 px (not worse; still FAIL, 10.402 Å runtime RMS). map32: 11.754152 vs 0.061555 px | **falsified** (map32). It holds against the W5 double baseline |
| P5 | Double DC zeroing is a no-op (S-D = S-P, H-D = H-P within 1e-6 px) | S-D differs from S-P by up to 0.704 px (pedestal 50 it) and 0.703 px (vel0-N13-prod-5it). H-D differs from H-P by up to 0.0154 px (vel0-N13-iso-5it) | **falsified**. The cause is not diagnosed |
| P6 | map32 N=5 Jacobian: pedestal arms are identity; H-D within 0.05 of double H2 | S-P and H-P eigenvalues all 1 (deviation 3.3e-13). H-D -0.227387 / -0.251443, max gap 0.0019 | confirmed |
| P7 | Double H2 makes integer and fractional PASS at both stops | integer 0.075 / 0.000000 Å, fractional 0.030 / 0.000000 Å RMS, runtime and STAR | confirmed |
| P8 | map32 H-D noisy 5 it worse than S-P in RMS **and** max | RMS 1.636 to 1.688 Å (worse), max 7.780 to 7.385 Å (better) | **falsified**. Double does show the native harm: 1.668 / 7.137 to 3.014 / 20.781 Å |

## Harmful counterexample (vel1-N20-iso; trajectory px, then runtime RMS / p95 / max Å)

| Domain | Stop | S-P | S-D | H-P | H-D |
|---|---|---|---|---|---|
| double | 5 it | 11.832823; 10.472 / 14.811 / 14.811 FAIL | 11.832823; 10.472 Å FAIL | 11.754153; 10.402 Å FAIL | 11.754153; 10.402 / 14.711 / 14.711 FAIL |
| double | 50 it | 11.827635; 10.467 / 14.803 / 14.803 FAIL | 11.827635; 10.467 Å FAIL | 11.754561; 10.403 Å FAIL | 11.754561; 10.403 / 14.712 / 14.712 FAIL |
| map32 | 5 it | 0.061555; 0.054 / 0.090 / 0.095 PASS | 11.832823; 10.472 Å FAIL | 0.024200; 0.021 Å PASS | 11.754152; 10.402 / 14.711 / 14.711 FAIL |
| map32 | 50 it | 0.013596; 0.012 / 0.017 / 0.019 PASS | 11.827637; 10.467 Å FAIL | 0.024834; 0.022 Å PASS | 11.754558; 10.403 / 14.712 / 14.712 FAIL |

STAR scores agree with runtime within 1e-5 Å in every row. The guard never fired on this case
(120 / 1020 H2 peaks, 0 fallbacks). The iso weight is a W5 harmful comparator control, not the
native weight.

## Scorecard: controls passing all limits in runtime and STAR

| Domain | Stop | S-P | S-D | H-P | H-D |
|---|---|---|---|---|---|
| double | 5 it | 7/16 | 7/16 | 15/16 | 15/16 |
| double | 50 it | 13/16 | 13/16 | 15/16 | 15/16 |
| map32 | 5 it | 8/16 | 7/16 | 12/16 | 15/16 |
| map32 | 50 it | 12/16 | 14/16 | 14/16 | 15/16 |

The only H-D failure in every cell is vel1-N20-iso.

Fixtures, H-D vs S-P (runtime RMS / p95 / max Å; STAR agrees within 3e-4 Å):

| Case | double 5 it | double 50 it | map32 5 it | map32 50 it |
|---|---|---|---|---|
| zero | PASS = PASS (0) | PASS = PASS | PASS = PASS | PASS = PASS |
| integer | 0.437 FAIL to 0.075 PASS | 0.268 FAIL to 0.000 PASS | 0.308 FAIL to 0.074 PASS | 0.265 FAIL to 0.000006 PASS |
| fractional | 0.326 FAIL to 0.030 PASS | 0.348 FAIL to 0.000 PASS | 0.432 FAIL to 0.030 PASS | 0.081 PASS to 0.000006 PASS |
| affine | 0.320/0.588/0.887 FAIL to 0.155/0.317/0.636 PASS | 0.326 to 0.263 FAIL (max 1.146 to 1.033); patch-native 0.282 FAIL to 0.154/0.313/0.623 PASS | 0.264/0.448/0.893 FAIL to 0.171/0.340/0.677 PASS | 0.304 to 0.263 FAIL; patch-native 0.277 FAIL to 0.152/0.325/0.539 PASS |
| pedestal | 0.320 FAIL to 0.155/0.317/0.636 PASS | 0.445 to 0.263 FAIL; patch-native 0.466 FAIL to 0.154/0.313/0.623 PASS | 3.942 to 0.262 FAIL (max 12.56 to 1.016) | 3.942 to 2.986 FAIL, **max 12.56 to 21.90** |
| noisy | **1.668/3.320/7.137 to 3.014/6.416/20.781** FAIL | **0.698 to 0.871** FAIL | **1.636 to 1.688** FAIL (max 7.78 to 7.39) | 0.881 to 0.871 FAIL (p95 up 1.682 to 1.695) |
| flat, repeated | UNIDENTIFIABLE in every arm | | | |

Full per-arm tables: [results/tables.md](results/tables.md).

## Every H-D regression versus same-domain S-P

Any increase in RMS, p95 or max, runtime or STAR, no threshold (`results/scorecard.json`, `regressions`):

| Row | Domain | Increase (S-P to H-D, Å) | Verdict |
|---|---|---|---|
| vel1-N20-iso-5it | map32 | RMS 0.054 to 10.402, max 0.095 to 14.711 (runtime and STAR) | **PASS to FAIL** |
| vel1-N20-iso-50it | map32 | RMS 0.012 to 10.403, max 0.019 to 14.712 (runtime and STAR) | **PASS to FAIL** |
| vel0-N5-iso-5it | double | RMS 0.035 to 0.082, max 0.059 to 0.126 (runtime and STAR) | PASS to PASS |
| vel0-N5-iso-5it | map32 | RMS 0.051 to 0.082, max 0.083 to 0.126 (runtime and STAR) | PASS to PASS |
| noisy 5 it | double | RMS 1.668 to 3.014, p95 3.320 to 6.416, max 7.137 to 20.781 (runtime and STAR) | FAIL to FAIL |
| noisy 50 it | double | RMS 0.698 to 0.871, p95 1.383 to 1.695, max 1.642 to 1.956 (runtime and STAR) | FAIL to FAIL |
| noisy 50 it patch-native | double | RMS 1.836 to 1.895, p95 3.748 to 3.899, max 9.591 to 10.547 (runtime and STAR) | FAIL to FAIL |
| noisy 5 it | map32 | RMS 1.636 to 1.688, p95 3.300 to 3.367 (runtime and STAR) | FAIL to FAIL |
| noisy 50 it | map32 | p95 1.682 to 1.695 (runtime and STAR) | FAIL to FAIL |
| pedestal 50 it, and its patch-native row | map32 | max 12.560 to 21.899 (runtime and STAR) | FAIL to FAIL |
| repeated 5 it | double | +4e-10 Å in RMS, p95 and max (runtime only) | UNIDENTIFIABLE |

Verdict losses in the diagnostic single-factor arms (all map32): S-D fractional 50 it (0.081 to 0.345 Å),
S-D vel1-N20-iso at both stops (to 10.47 Å), and H-P vel0-N20-prod-50it and vel1-N20-prod-50it
(0.118 to 0.355 and 0.140 to 0.362 Å). Counts of any-increase rows: S-D 65, H-P 46, H-D 23
(each row is one score of one case).

## Guard

The guard fired on no N=5 Jacobian evaluation. On H-D phase-ramp runs it fired only for
offset > 1 px: 10 of 3926 peaks in double and 8 of 10036 in map32, all in vel0 N=9/13/20 prod.
On fixtures, every H-D fallback was not negative definite and occurred on flat or repeated:
125 in double and 295 in map32. Per-row counts are in `results/scorecard.json`
(`guard_fired_rows`) and in each row's `guard`.

## Limits

- Offline NumPy replay only. map32 rounds only the CCF map. Native CPU uses float32 spectra and FFTs
  throughout. P1 shows map32 does not reproduce the native H2-alone failure, and the harmful case gives
  opposite S-P verdicts in the two domains. Which domain native follows on long movies is UNRUN.
- Phase-ramp controls have no local fit and are diagnostic, not gate-role image fixtures. Several long
  trajectories put truth outside the fixed ROI (sampling flags in each row's `application`).
- No native, GPU or CUDA run. CPU/CUDA agreement is not assessed. The historical ledger is unchanged.

## Reproduction

cpu64 (small-refmac-machine), `taskset -c 40-47` under `flock -n /tmp/motioncorr-w6-cpu40-47.lock`,
one BLAS/OpenMP thread, NumPy 2.5.3 / Python 3.12.3, assigned-lane busy fraction 0.0 at admission.
Wall time 81.6 s (not a benchmark). Scratch /tmp/motioncorr-w6-20261026 holds a copy of the W5 scratch
(the round-2 inputs and lib) plus this directory: 32 MB total.

```sh
ssh cpu64 'flock -n /tmp/motioncorr-w6-cpu40-47.lock taskset -c 40-47 ~/.mc-venv/bin/python -I -B /tmp/motioncorr-w6-20261026/w6_dc_coupled_peak_20261026/scripts/run_once.py w6'
python3 -I -B scripts/report.py   # saved-result processing, local
```

`results/w6.json` (SHA256 d9e2c0be…) holds every trajectory, iteration history, guard count,
coefficient set, per-frame score and Jacobian. All 408 generated STAR files are in `results/star/`.
`SHA256SUMS` binds the deliverable.
