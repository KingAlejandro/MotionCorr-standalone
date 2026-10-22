# Response to independent review round 1 (PR277 at 91380b3f)

`REVIEW.md` is the verbatim reviewer report, sha256
`ad010c8fdcbb1bf48ee7afcd5d50b01bc7207794fda5c193c752dce1f919bb10`.

- **F1 fixed in tests.** `runner_numerics local_motion_guard_model` (CTest
  `LocalMotionGuardModel`) adds 3-frame witnesses where frame 1 is exactly 3 px and frame 2 is
  6 px (x and y), plus an accept counterpart with two exact-3 frames. A `>=` early exit fails 4
  checks.
- **F2 addressed.** The same mode uses the real `ThirdOrderPolynomialModel` (all 36
  coefficients, 252 deterministic cases on 7 shapes including 1×N, N×1 and nonsquare, both
  decisions exercised) against a scan of every in-image pixel pair through its own `getShiftAt`,
  and the frozen oracle rows for each component/axis pairing. `LocalMotionGuardCall` pins the
  single runner call, the `3` threshold and the strict `>` as source text; it cannot show that
  `nx`/`ny`/`n_frames` mean the alignment grid, which N3 tests through the runner.
- **F3 not changed.** Non-finite models stay accepted by both guards; out of scope here.
- **F4.** Native qualification is frozen in `../native/FROZEN.md`; maintainer sign-off for the
  intended RELION-parity difference is still required and is not in the branch.

The 51-check standalone test and its recorded evidence are unchanged.

Host controls (`../verify_model_controls.py`, macOS/Apple clang, CPU Release): attempt 01 is
**invalid** for two mutant rows, which reused the previous binary because make did not see the
header rewrite; it is retained under `host_controls/attempt01-INVALID/`. Attempt 02 rebuilt a
distinct binary per case: fixed PASS (779 checks), exact legacy block FAIL 489, `>=` early exit
FAIL 4, uncentred FAIL 387, invalid last pair FAIL 195, swapped dimensions FAIL 342, x-component
only FAIL 179, restored PASS with the original binary hash; call-pin mutants (swapped `nx, ny`,
`n_frames - 1`, runner `>=`, threshold 4, second call) all exit 1. `tools/test_ci_fail_closed.py -v`
8/8 PASS.
