# #264 N3/N4 iteration 2: proposal, frozen before any iteration-2 execution

Status: **proposal, not launched**. Written on 22 October 2026 while iteration 1 (`../FROZEN.md`,
candidate `0a1f64ab`) was still running. No iteration-1 N3 output had been produced or read when
this was frozen, so nothing here is selected from native outcomes. Iteration-1 files, predictions
(`../predictions.json`, sha256 `90e7a045…653d`) and any iteration-1 result stay as recorded,
including a FAIL.

## Why

Review round 2, finding F5: in iteration 1 the candidate (finite-pair) A_x and A_y rows reach
exactly 3 px at frame 10 (3.3 × 10/11), because the fields are linear in z. The native fit
recovers the coefficients with ~1e-13 rounding, so the strict `> 3` may stop at frame 10 and print
≈3.0 instead of the predicted 3.3. The reject decision is the same either way; only the
printed-value witness is not deterministic. `predict_iter2.py` reproduces this as a negative control:
iteration-1 margin 0, and a +1e-12 relative perturbation moves the stop from frame 11 to frame 10.

## Change

Only A_x and A_y change: finite-pair total 3.5 instead of 3.3. All other cases, the fixture
(`km_local_nonsquare`, 768×512, 12 frames), the overlay patch, the lane, the runner options, the
grading code and its tolerances (value 2e-5 relative, coefficients 1e-5) are unchanged.
The other five cases reproduce their iteration-1 rational predictions exactly (asserted).
Sources under `src/`, `tests/`, `tools/` and `CMakeLists.txt` are unchanged from `52affe31`.

| Case | Legacy (base) | Finite pairs (candidate) | Uncentred (mutant) | Min margin to 3 |
| --- | --- | --- | --- | --- |
| A_x `a(x−x²)` | 1.753420 accept, z11 | 3.181818 reject, stops z10 | 1.748860 accept, z11 | 4.5% |
| A_y `a(y−y²)` | 1.755132 accept, z11 | 3.181818 reject, stops z10 | 1.748289 accept, z11 | 4.5% |
| B_x, B_y, E_xy, F, G | as iteration 1 | as iteration 1 | as iteration 1 | 1% (E) to 99% |

Analytic controls in `predict_iter2.py`, all exact rationals over the running maximum at every
evaluated frame: the margin is at least 0.5% for every case and algorithm, and the decision and
stopping frame are unchanged under ×(1±1e-9) and two per-coefficient sign patterns, with values
within 1e-8. Changed rows are cross-checked against an exhaustive float64 pair scan.
E stays 1% inside the threshold: that is ~1e11 times the fit rounding and was not flagged in review.
`predict_iter2.py` hash-checks and imports the frozen iteration-1 emulation instead of copying it.
Its stale comment (`E … legacy ~5.94`; the early exit gives 3.24) is left in place because
`predict.py` is frozen.

Files: `predict_iter2.py` sha256 `7261cf90…f914`, `predictions_iter2.json` sha256 `6ff11cb5…859e`,
`n3_iter2.py` (the iteration-1 runner and grader with these predictions and output `n3-iter2/`),
`chain_iter2.sh`.

## Proposed run (parent decides when)

A new scratch `/mnt/clathrin/alex-motioncorr-guard264-20261022-<sha12 of the iteration-2 commit>`,
the same GPU1/CPUs 14–15 lane and locks. Run `../tools/setup.sh` with a bundle of the
iteration-2 commit, then `chain_iter2.sh`. It runs only the five overlay builds, the CPU and GPU
N3 runs, the grade and health. No N1 or N2 stage, and no build or run in the iteration-1 scratch.
Expected outcomes are those in `../FROZEN.md` for N3/N4 with the A rows above. The candidate A
rows must print 3.181818 (frame-10 stop). N4 still needs the mutant to differ from the candidate,
and it does on A_x, A_y, B_x, B_y and E.

Run only if parent schedules it. That may be after iteration 1 completes, and it does not depend
on whether iteration 1's A rows pass. A host wiring check is the only thing run so far: grading an
empty scratch gives 40 rows, all UNRUN, and N4 FAIL, so it fails closed.
Limits are as in `../FROZEN.md`: test-only overlay builds and injected observations, N4 on CPU
only, and no timing, accuracy or science claim.
