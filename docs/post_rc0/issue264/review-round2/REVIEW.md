# Independent review, round 2: DRAFT PR277 (#264 centred distortion-domain guard)

Reviewer: fresh delegated task, read-only. Head reviewed: `0a1f64ab3e192c3ebad57b35149d872b21331730`
(base `3691374061f782bc84531fd1c79d017ddcb5a7c2`). Host: macOS arm64, Apple clang, one job, `OMP_NUM_THREADS=1`, load ~4 of 14 CPUs.
No edits or commits, no push/PR/comment/Notion, no SSH/GPU/native run, no nested agent. Outputs: this directory only
(`src/` = `git archive` of the SHA, `clone/` = my own clone at the SHA, `build/` = my CMake build, `r2/` = logs and scripts, hashes in `r2/hashes.txt`).

Note on the supplied worktree: after I detached it at `0a1f64ab`, something else re-attached `HEAD` to branch `review-issue-264-round-2` at `1f0a58bf`
(195 staged paths; tracked files still equal `0a1f64ab`). I did not touch it and reviewed from the exported SHA, so nothing below depends on the worktree state.

## Verdict

**No material finding against the production source or the repository host tests. F1 and F2 are closed (F2 for the helper and call text; the runner-meaning part stays with N3).**
One material finding against the *frozen native N3 predictions* (F5): two rows have a knife-edge value witness. It does not touch the production decision.
No merge recommendation: native qualification is still UNRUN here, and the parity sign-off (F4) is still not in the branch.

## Source delta: unchanged

- `git diff 4b0e4e73 0a1f64ab -- src` is empty. `git diff 52affe31 0a1f64ab -- src tests tools CMakeLists.txt` is empty, so the "candidate = FROZEN.md commit, compiled sources = 52affe31" statement holds.
- vs base: `src/local_motion_guard.h` (new) and `src/motioncorr_runner.cpp` (guard block replaced by one call, include added). Threshold constant 3, strict `>`, message, `goto skip_fitting` are unchanged. Helper re-read: corner reduction, valid-pair domains, centred `ix/nx - 0.5` and the strict early exit are as in round 1.
- New code since round 1: `tests/test_runner_numerics.cpp` (+134, two modes), `CMakeLists.txt` (+7), two inventory edits, `tools/test_ci_fail_closed.py` mock inventories, `tools/validate_test_collection.py`, host-control scripts/records, `native/` matrix and tools.

## F1 (strict early exit): closed

New witnesses `strict exit: exact frame then larger frame` (X-along-x, 128x64, 3 frames, coefficient 384: frame 1 = exactly 3, frame 2 = 6) and the Y-along-y one (48x64, coefficient 192) expect 6 and reject. Independently confirmed: a `>=` early exit fails exactly those 4 checks (2 maximum + 2 decision) in my own rebuild (`r2/mut_ge_early_exit.err`). I checked the frozen expected values by hand (index map `getShiftAt`: x terms 3-5, x² 6-8, y 9-11, y² 12-14, xy 15-17; 3.98, 2.94, exact-3 cross term at 128x128).
Residual: the runner-side `>` decision is pinned only as source text (`LocalMotionGuardCall`), see "Limits".

## F2 (real model, call pin): closed for what a host test can show

- `LocalMotionGuardModel` uses the real `ThirdOrderPolynomialModel` and its own `getShiftAt`; the reference scans every in-image pair independently of the helper's corner argument; the 11 frozen rows are not computed by the helper (hand-derived rationals, all matched). The coordinate formula is restated in the reference, but the frozen rows pin it: uncentred and a +1/n half-pixel offset both fail hundreds of checks. Not a copied tautology.
- 252 sweep cases over 7 shapes incl. 1x1, 1xN, Nx1, 2x2, nonsquare; both decisions occur (reject=95, accept=85), and the test fails if they do not.
- `LocalMotionGuardCall` is a whitespace-normalised source pin: exactly one `maximumNeighbourShiftDelta` token, the whole `MAXIMUM_TOLERANCE`/call/`>` block exactly once. It cannot show that `nx`, `ny`, `n_frames` are the alignment-grid values; the overlay line `n_obs/nx/ny/n_frames` in N3 is the only witness of that, and it is printed from the same variables the call uses.

## Independent controls (host, CPU Release, `runner_numerics` built with `--parallel 1`, my clone at the SHA, exit 0)

| Check | Result |
| --- | --- |
| `runner_numerics local_motion_guard_model` | PASS checks=779 failed=0 reject=95 accept=85 (equals the author's count) |
| `runner_numerics local_motion_guard_call <runner>` | PASS; `ctest -N` lists `LocalMotionDistortionGuard`, `LocalMotionGuardModel`, `LocalMotionGuardCall` |
| `local_motion_distortion_guard` (51 checks) | PASS |
| `tools/test_ci_fail_closed.py -v` (NumPy python, in my clone with `.git`) | 8/8 OK |
| My own 15 helper mutants, a distinct rebuilt binary per mutant (asserted by sha), `r2/mutants.py` | all exit 1 with an ordinary `FAIL checks=779`: `>=` exit (4), no early exit (65), frames-1 (341), ix always first/last (128/138), iy always first (131), diagonal pair (388), no `abs` on x (104), uncentred (387), half-pixel offset (370), y-component only (179), x-component only (209), skip-condition removed (226), last-pair overrun (209), swapped last-pixel axes (283). Restored header: binary sha equals the baseline (`1db6c4e4…`), PASS. |

Author records: `host_controls/attempt01-INVALID/` shows the failure the author described (the uncentred and `>=` rows share binary `6cb5702921`, and swapped-dimensions and x-only share `f46c4dc46a`); it is retained and not used. `attempt02` rows have distinct binaries, fixed PASS(779), legacy exact block FAIL 489, `>=` FAIL 4, uncentred FAIL 387, last pair FAIL 195, swapped FAIL 342, x-only FAIL 179, restored PASS with the original binary, all six call mutants exit 1. My counts agree for the cases I share (4, 387). I did not run `verify_model_controls.py` itself: it needs a clean `git` worktree and `HEAD`, which the supplied worktree no longer provides; I reproduced its mutants in my own clone instead.

## Findings

**F5 (medium for the native campaign, none for production). N3 `A_x` and `A_y` candidate rows predict a printed value of 3.3, but frame 10 is exactly 3.0.**
`predict.py` builds the A cases so the last frame (z=11) gives 3.30 and the field is linear in z, so z=10 gives exactly 3.30*10/11 = 3 (my per-frame scan: `r2/frames.out`, `near-3-frames=[(10, 3.0)]`; the predictor's exact-Fraction early exit correctly does not stop there). The native fit recovers the coefficients with rounding error, so the frame-10 value is 3 plus or minus ~1e-14 (NumPy lstsq illustration, `r2/knife.py`: A_x -7e-14, +2e-14, -1e-14 and A_y +3e-14, +7e-14, +2e-13 for three assumed patch-centre layouts; this is an emulation, not the native SVD). If it lands above 3 by the strict `>`, the real guard stops at frame 10 and prints about `3` instead of `3.3`; `n3.py grade` then fails the row on `abs(guard - 3.3) > 2e-5 * 3.3`. The decision (reject) is the same either way, so the guard behaviour is right; only the value witness is a coin flip per case, and CPU and CUDA read identical fitted coefficients. Rows affected: A_x and A_y on `ov-cand-cpu` and `ov-cand-cuda`. Not affected: legacy and uncentred A rows (accept), all B/E/F/G rows (margins 1-10%), and N4's decision comparison.
Consequence for the running chain: an `A_*` value FAIL would be a prediction defect, not a guard defect, and must be retained as FAIL; the repair is a distinct iteration with a target that keeps every earlier frame at least a few percent off 3 (for example a finite total near 3.5, giving a deterministic frame-10 stop at 3.18) and a new `predictions.json` hash. Do not edit the frozen file in place.

**F6 (low, documentation).** `docs/post_rc0/issue264/README.md` at this head does not mention `LocalMotionGuardModel`, `LocalMotionGuardCall`, `host_controls/`, `verify_model_controls.py` or `native/FROZEN.md` (its test count, "75 registered", predates them), and `attempt01-INVALID`'s `model_controls.json` still says `all_expected: true`. The INVALID status exists only in the directory name and `review-round1/RESPONSE.md`. Harmless today; worth one sentence before publication. Also `predict.py` has a stale comment (`E ... legacy ~5.94`; the frozen value is 3.24 via the early exit at frame 6).

**F3 carried, unchanged (informational).** Non-finite models remain accepted by both the legacy and the new guard (`0 < NaN` is false). Source unchanged, so not re-run; out of scope, not a regression.

**F4 carried, unresolved.** The intended RELION `ad0b230` parity change (decisions differ only for models whose wrong-domain and correct-domain decisions differ) still needs the maintainer sign-off required by plan §9.2/§9.4. Not in the branch; I have not assumed it.

## Static review of the native tools (nothing run)

No definite unsafe or invalid witness behaviour found.
- Lane, locks, scratch cap and CPU 14-15 are enforced in `lane.sh`/`build.sh`/`gpu_locked.sh`/`ctest.sh`/`chain.sh`; locks are nonblocking and stop (exit 5) without retry; `stage.sh` refuses an existing stage and never retries; `health.sh` fails closed on `[N/A]`, a compute process on GPU1, ECC or remap states; GPU1 is selected by UUID and witnessed by process family in `runlib.py` (a missed sample fails the row, it does not pass it); every run directory refuses reuse.
- `n3_observation_overlay.patch` sits before `MC_STAGE("fit polynomial")`, uses the same `patch_xs[i] / nx - 0.5` coordinates, `patch_frames[i]` frame argument and `getShiftAt` as the fit, env-gated, test-only, applied to separate trees (`src-ov-*`); it needs `<sstream>`/`getenv`, already present in the runner. The N4 mutant tree is the uncentred helper plus the overlay. N3 explicitly injects observations, so it tests fit, guard, fallback and reconstruction wiring on a known model, not motion estimation accuracy; stated in `FROZEN.md` and `n3.py`.
- `n3.py grade`: base-vs-candidate pairing, N4 requiring the mutant to match its own predictions and to differ from the candidate on at least one case, and `Z_no_overlay` as a control are sound apart from F5. A missing STAR coefficient would raise a `TypeError` rather than pass (fails closed).
- `n2.py`: options exist in `compare_output_trees.py`/the runner (`--manifest`, `--input-star`, `--products-only`, `--json-out`, `--ingest_witness`); the N2 prediction (largest legacy delta 0.0073 px) cannot fire either guard, so any guard line is a contradiction that stops the chain.
- Author's N3 caveat stands: the exact 3 px boundary is not reachable through the SVD fit; the host tests cover it.

## Status of claims (unchanged vs round 1 unless stated)

- Helper regression with exhaustive reference, the real-model sweep and frozen witnesses, and 15+6 mutants: host **PASS** (macOS/Apple clang, CPU Release only).
- Native CPU/CUDA/nvCOMP CTest, N2 (24 movies), N3, N4: **not reviewed as results** (raw JUnit and chain output were not available to me; chain still running). Treated as UNRUN for any claim.
- CI is compile-only; no timing, accuracy or science claim.

## Remaining dependencies

1. Native N1-N4 results at the exact SHA, reviewed by the parent; A_x/A_y candidate value rows are expected to be unreliable (F5), so judge those rows on the decision and the STAR/model witnesses, and freeze a new iteration rather than repairing.
2. Maintainer sign-off for the parity change (F4); any decision on non-finite models (F3) is separate.
3. A fresh review round after any change to source, tests, tools or frozen predictions. Evidence-only additions can be assessed separately.

`REVIEW.md` sha256 is recorded in `REVIEW.sha256` (computed after writing).
