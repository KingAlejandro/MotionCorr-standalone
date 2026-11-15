# H6: local patch DC zeroing and the coupled peak on patches

Frozen spec: [H6-local-dc-coupled-PREDICTION.md](h6_local_dc/H6-local-dc-coupled-PREDICTION.md), copied verbatim, SHA256 `d5a954d13e8b215904c9194b41dbcf8cfb807b16a2431b4649745301566d8c14` verified before any run.
No new flags, no code change this round: the binary is `build-h5on` (`a7db45df...`, source `20e52f57`, the hook build with runtime capture; identical to the previous round's binary). Control DCg+H2g is reused from the H4 round, not rerun.

**Result.** DCb+H2a (DC arm `both`, coupled peak `all`) makes `pedestal` PASS at both stops (0.262 to 0.117 Å RMS, max 1.016 to 0.537) and `affine` PASS at the long budget (max 0.849 to 0.513), keeps every earlier pass, and
takes noisy at the production stop from 3.049 / 6.32 / 21.30 to 1.645 / 3.34 / 7.28 Å (still FAIL; noisy is characterization). Zeroing the patch DC bin carries most of it: DCb+H2g gets 74% of the pedestal RMS improvement. The peak factor on patches
alone (DCg+H2a) changes nothing for pedestal. Predictions 1 to 4 hold and 5 is reported; the falsification branch (prediction 2 failing) does not apply. Research evidence on the 3x3-patch fixtures only; the phase-ramp N controls have no local fit and were not rerun.

## Arms (native CPU, K267 eight cases, unchanged checker, runtime capture on; limits 0.20 / 0.40 / 0.80 Å)

All 48 native runs exited 0 (6 arms x 8 cases), lane CPUs 48-55 under the lock. Counts of checker verdicts (STAR) per arm, PASS / FAIL / UNIDENTIFIABLE:

| Stop | DCg+H2g (control) | DCb+H2a | DCb+H2g | DCg+H2a |
|---|---|---|---|---|
| Production stop PASS / FAIL / UNIDENT. (checker, STAR) | 4 / 2 / 2 | 5 / 1 / 2 | 5 / 1 / 2 | 4 / 2 / 2 |
| 50 / 1e-9 PASS / FAIL / UNIDENT. (checker, STAR) | 3 / 3 / 2 | 5 / 1 / 2 | 5 / 1 / 2 | 4 / 2 / 2 |

Selected cells, runtime RMS / p95 / max Å and runtime gate (STAR gives the same gate in every cell; full tables with STAR in [results/h6_arm_table.md](h6_local_dc/results/h6_arm_table.md)):

| Case | Stop | DCg+H2g (control) | DCb+H2a | DCb+H2g | DCg+H2a |
|---|---|---|---|---|---|
| integer | prod | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS | 0.0742 / 0.1157 / 0.1157 PASS |
| integer | long | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS |
| fractional | prod | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS | 0.0297 / 0.0483 / 0.0483 PASS |
| fractional | long | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS | 0.0000 / 0.0000 / 0.0000 PASS |
| affine | prod | 0.1589 / 0.3370 / 0.6948 PASS | 0.1170 / 0.2603 / 0.5374 PASS | 0.1550 / 0.3170 / 0.6361 PASS | 0.1518 / 0.2963 / 0.5281 PASS |
| affine | long | 0.1758 / 0.3748 / 0.8490 FAIL | 0.1156 / 0.2577 / 0.5129 PASS | 0.1542 / 0.3128 / 0.6234 PASS | 0.1347 / 0.2842 / 0.4434 PASS |
| pedestal | prod | 0.2623 / 0.5771 / 1.0160 FAIL | 0.1169 / 0.2603 / 0.5375 PASS | 0.1550 / 0.3169 / 0.6364 PASS | 0.2623 / 0.5771 / 1.0160 FAIL |
| pedestal | long | 0.2628 / 0.5784 / 1.0333 FAIL | 0.1155 / 0.2578 / 0.5127 PASS | 0.1542 / 0.3129 / 0.6236 PASS | 0.2628 / 0.5784 / 1.0333 FAIL |
| noisy | prod | 3.0491 / 6.3200 / 21.2952 FAIL | 1.6454 / 3.3373 / 7.2840 FAIL | 3.0135 / 6.4164 / 20.7812 FAIL | 1.6636 / 3.3642 / 7.4602 FAIL |
| noisy | long | 1.8029 / 3.7120 / 9.8838 FAIL | 1.6520 / 3.3537 / 7.2942 FAIL | 1.8953 / 3.8990 / 10.5469 FAIL | 1.7756 / 3.6113 / 9.5847 FAIL |

Zero stays PASS; flat and repeated stay UNIDENTIFIABLE in every arm; integer and fractional are identical to the control in every arm (prediction 3).

## Manipulation control (DC hook arm `both`, global and patch CCF frames zeroed; summed over the eight cases)

| Arm | Stop | DC arm | Global CCF frames zeroed | Patch CCF frames zeroed | H2 guard fires / peaks (global; patch) |
|---|---|---|---|---|---|
| DCg+H2g (control) | prod | global | 95/95 | 0/260 | 20/95; 0/0 |
| DCg+H2g (control) | long | global | 1510/1510 | 0/345 | 255/1510; 0/0 |
| DCb+H2a | prod | both | 95/95 | 225/225 | 20/95; 2/225 |
| DCb+H2a | long | both | 1510/1510 | 450/450 | 255/1510; 24/450 |
| DCb+H2g | prod | both | 95/95 | 260/260 | 20/95; 0/0 |
| DCb+H2g | long | both | 1510/1510 | 310/310 | 255/1510; 0/0 |
| DCg+H2a | prod | global | 95/95 | 0/235 | 20/95; 51/235 |
| DCg+H2a | long | global | 1510/1510 | 0/335 | 255/1510; 51/335 |

`both` zeroes N/N global and N/N patch CCF frames; `global` zeroes N/N global and 0/M patch frames. The coupled-peak counts show H2 on patches only in the `all` arms (patch peaks fitted there).

## Prediction scorecard

| # | Prediction | Result | Verdict |
|---|---|---|---|
| 1 | Flags-off identity to e77a51a2 unchanged, re-verified with the binary used | same binary hash as last round; known-motion trees IDENTICAL (193 files / 88 gated) and synthetic movie IDENTICAL (14 / 7) for the default and hook builds, capture on identical to off; the previous round's full CPU CTest (95 tests, 0 failed) ran on this binary | confirmed |
| 2 | Pedestal: DCb+H2a has lower RMS than DCg+H2g at the production stop; the patch DC factor (DCb+H2g) gives most of that improvement | runtime RMS 0.2623 (control) to 0.1169 (DCb+H2a); DCb+H2g 0.1550, i.e. 74% of the improvement (STAR 74%; long budget 74%). DCg+H2a is identical to the control for pedestal | confirmed |
| 3 | Integer and fractional identical to DCg+H2g in every arm | identical in all 24 cells (3 arms x 2 stops x 2 cases, runtime and STAR, exact equality of RMS / p95 / max) | confirmed (no defect) |
| 4 | Affine at the production stop keeps its DCg+H2g PASS in DCb+H2a | PASS 0.1170 / 0.2603 / 0.5374 (control 0.1589 / 0.3370 / 0.6948); also PASS at the long budget (control FAIL, max 0.849) | confirmed |
| 5 | Everything else reported; every increase versus DCg+H2g listed | see below | reported |

**Falsification branch.** The branch triggers if prediction 2 fails (pedestal no better with patch DC zeroing); prediction 2 holds, so it does not apply, and the local error is not left to the W5 objective-bias diagnosis for pedestal. The spec names no branch for success; this is a research result, with the caveats below.

## Regressions versus DCg+H2g (any increase in RMS, p95 or max, runtime or STAR, no threshold)

Four rows (two cells, each in runtime and STAR), all noisy FAIL to FAIL, all DCb+H2g: production stop p95 6.320 to 6.416 Å (RMS and max fall: 3.049 to 3.014, 21.30 to 20.78); 50 iterations RMS 1.803 to 1.895, p95 3.712 to 3.899, max 9.884 to 10.547 Å.
**DCb+H2a and DCg+H2a have no increase in any case.** (`results/h6.json`, `regressions_vs_control`.)

## Noisy: edge patches (1,3) and (2,3) (converged = last patch RMSD < 0.5 px; a patch that does not converge is dropped)

| Arm | Stop | Patch (1,3) | Patch (2,3) |
|---|---|---|---|
| DCg+H2g (control) | prod | REJECTED (5 it, last 1.30 px) | REJECTED (5 it, last 2.68 px) |
| DCg+H2g (control) | long | converges (7 it, last 0.16 px) | converges (16 it, last 0.38 px) |
| DCb+H2a | prod | converges (3 it, last 0.25 px) | REJECTED (5 it, last 1.59 px) |
| DCb+H2a | long | converges (3 it, last 0.25 px) | REJECTED (50 it, last 1.58 px) |
| DCb+H2g | prod | REJECTED (5 it, last 0.64 px) | REJECTED (5 it, last 3.37 px) |
| DCb+H2g | long | converges (7 it, last 0.45 px) | converges (12 it, last 0.38 px) |
| DCg+H2a | prod | converges (3 it, last 0.50 px) | REJECTED (5 it, last 2.25 px) |
| DCg+H2a | long | converges (3 it, last 0.41 px) | converges (22 it, last 0.45 px) |

DCb+H2a keeps patch (1,3), the top-right anchor, at both stops, which is the corner the previous round showed was extrapolated after (1,3) was dropped; (2,3) still does not converge in either DCb+H2a run (it is dropped even after 50 iterations).
DCb+H2g repeats the control's production-stop loss of both edge patches (3.01 / 20.78 Å, essentially the control's corner extrapolation), so on noisy the improvement needs the coupled peak on patches and not only the DC factor; DCg+H2a also keeps (1,3) at the production stop (1.664 / 7.46 Å).

## Guard and limits

Guard fires: global peaks 20/95 (production) and 255/1510 (long) in every arm (flat and repeated, all not negative definite, as before); patch peaks DCb+H2a 2/225 and 24/450, DCg+H2a 51/235 and 51/335 (the pedestal patches, with the DC bin left in), DCb+H2g none (separable on patches).
Limits: one synthetic family, 3x3 patches on three cases only (affine, pedestal, noisy), one run per arm; noisy still FAILs in every arm and is characterization, not a gate role; the DC hook is a #262 experiment ported for the CPU path only, so CUDA parity and a CUDA-build refusal run are UNRUN; the native N controls are global-only and were not rerun, so the effect of the patch options on them is not tested (nothing local enters).
No new flags, no tuning, and no change to the existing flag code. I did not review the existing flag code for defects beyond what these runs exercised; none surfaced (integer and fractional are exactly identical to the control, which would have shown a stray effect of the new arms on the global path).
