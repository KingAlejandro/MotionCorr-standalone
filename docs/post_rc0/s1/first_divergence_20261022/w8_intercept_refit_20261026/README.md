# W8: offline intercept refit of the H7a F observations — status: controls done, census HELD

**Current result.** Arm A, the naive midpoint refit (W7's recommendation read literally), **fails its noiseless controls** and is not eligible for the census. Arms B1/B2 (physical, integer-time) and C (midpoint fit, transformed before publishing) pass every gate K1–K8 and agree to ≤ 5e-12 px. The census fit has **not been run**. Per the reviewer's HOLD it waits for the parent to acknowledge these controls. All numbers are offline reconstructions; no native or scientific claim is made.

Plan frozen before any computation: [PLAN.md](PLAN.md) (`95a853e0`). Controls: [results/controls.json](results/controls.json), log [results/controls.log](results/controls.log).

| control | A (naive midpoint) | B1 | B2 | C |
|---|---|---|---|---|
| K1 rank / spatial rank / times per patch | 43/43, 6, 40 | 43/43, 6, 40 | 43/43, 6, 40 | 43/43, 6, 40 |
| K1 condition, raw / column-scaled | 5.7e5 / 306 | 5.3e5 / 290 | 5.0e5 / 289 | 5.7e5 / 306 |
| K2 published field at f = 0 | exactly 0 | exactly 0 | exactly 0 | exactly 0 |
| K3 linear, max error px | 1.3e-12 | 1.2e-12 | 8.8e-13 | 1.3e-12 |
| K4 quadratic | **0.10 FAIL** | 1.3e-13 | 1.0e-13 | 9.3e-14 |
| K5 cubic | **0.21 FAIL** | 2.1e-14 | 2.0e-14 | 2.6e-14 |
| K6 random full field | **0.073 FAIL** (0.21 on 5760x4092) | 2.2e-12 | 1.0e-12 | 1.6e-12 |
| K7 offset invariance | 5.2e-12 | 8.6e-12 | 3.0e-12 | 4.3e-12 |
| K8 equivalence vs B2 (noiseless / noisy) | — | 1.4e-12 / 5.2e-12 | — | 7.6e-13 / 4.0e-12 |

The table shows 4096x4096 values; 5760x4092 gives the same verdicts (controls.json). A's published fields match the reviewer's algebra to ≤ 9e-14 px: `b(f² − f)` for a quadratic truth and `c(f³ − 1.5 f² + 0.75 f)` for a cubic.

- **K9:** a deterministic step `eps` with no frame-0 error gives `delta = eps`, `delta(1) = 3 delta(0)`, and anchor ratio 1.02598 = sqrt(20/19). So the W7 anchor ratio cannot establish cause.
- **K10:** for `y = [0, 0, 3]`, the least-squares constant 1 gives RMS 1.414 / p95 1.9 / max 2.0, while the constant 1.5 gives 1.5 for all three. A least-squares floor is an RMS floor only.
- **K11** (perfect census inputs `G = g`, observations `Tr[Tc − g]`, unchanged evaluator; RMS / p95 / max Å):

| truth | native (no intercept, z = g + 0.5) | A | B1 / B2 / C |
|---|---|---|---|
| in-model 4096² | 0.0016 / 0.0036 / 0.0094 | 0.0016 / 0.0034 / 0.0089 | 0.0000 (≤ 2.4e-12 px) |
| in-model 5760x4092 | 0.0016 / 0.0036 / 0.0094 | 0.0016 / 0.0034 / 0.0090 | 0.0000 |
| outmodel | 0.885 / 1.505 / 1.778 | 0.885 / 1.505 / 1.777 | 0.885 / 1.505 / 1.771 |

**Next action (held for parent).** Run the frozen census with arm B2 as two separately scored offline reconstructions: R-rt (runtime global) and R-ser (STAR read-back global). Score against the native runtime and serialised fields, and test the predictions in PLAN.md.

## Receipts

- Source pins: evaluator `tools/check_realistic_motion.py` sha256 `b0ab099a...` and generator `a10f694a...`, both via `git archive 4fa272f6`. Patch centres come from the H7a F logs `dose1-s00` and `nonsquare-s00`.
- Command: `uv run --no-project --with numpy python -I scripts/w8_controls.py /tmp/w8src <H7a results/runs> results/controls.json`, with OMP/OpenBLAS/vecLib at 2 threads. Exit 0, 5.4 s wall.
- Resources: local Mac (14 CPUs, load ~10 from other work), NumPy 2.5.4, Python 3.15.1. cpu64 was unreachable at preflight (ssh port 22 timeout), so the declared local fallback was used.
- Truth isolation: `scripts/w8_fit.py` imports only NumPy.
