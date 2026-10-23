# Independent review, round 3: #264 F5 correction and N3-only iteration 2 proposal

Reviewer: fresh delegated task, read-only. Head reviewed: `521fddae9dbb068b0ad47ad04c7dedec15585fad`
(parent `0a1f64ab3e192c3ebad57b35149d872b21331730`; base `3691374061f782bc84531fd1c79d017ddcb5a7c2`).
Host: macOS arm64, Apple clang, one job at a time, `OMP_NUM_THREADS=1`, load 3-5 of 14 CPUs.
No edits or commits to the repository, no push/PR/comment/Notion, no SSH/GPU/native job, no nested agent, no full CTest.
Outputs: this directory only (`r3/` holds scripts, logs and fake scratches; hashes in `r3-hashes.txt`).

Worktree identity: I detached the supplied worktree at `521fddae`. Before use, `HEAD` was that commit, `git status --porcelain` was empty
and there were no staged or unstaged changes. It was still clean after all my runs (the grader/predictor runs used `python -B` and wrote only here).

## Verdict

**No material finding. Iteration 2 is arithmetically and control-ready as a proposal. F5 is resolved at the prediction level.**
This is not native or scientific qualification: nothing has run natively, and native iteration 2 is not authorised by this review.
F3 (non-finite models accepted by both guards) and F4 (maintainer sign-off for the intended RELION-parity difference) are carried unchanged.
Three informational notes are listed at the end; none blocks the proposal.

## What changed, and what did not

`git diff --name-only 0a1f64ab 521fddae` lists nine files, all under `docs/post_rc0/issue264/`:
`README.md`, `host_controls/INDEX.md`, `native/n3-iter2/{FROZEN-ITER2.md, chain_iter2.sh, n3_iter2.py, predict_iter2.py, predictions_iter2.json}`, `review-round2/{RESPONSE.md, REVIEW.md}`.

- `git diff 52affe31 521fddae -- src tests tools CMakeLists.txt` is empty, and so is `git diff 4b0e4e73 521fddae -- src`.
  Production helper `src/local_motion_guard.h` sha256 `02d8f5c1…c146` (same bytes I compiled).
- A diff of `native/predict.py`, `native/predictions.json`, `native/tools/`, `native/FROZEN.md`, `native/n3_observation_overlay.patch`,
  `host_controls/attempt01-INVALID/`, `host_controls/attempt02/` and `review-round1/` between `0a1f64ab` and `521fddae` is 0 bytes.
  Iteration-1 files and the old campaign inputs are untouched.
- `review-round2/REVIEW.md` is byte-identical to my predecessor's report (sha256 `cd7d0026…895d`, matches `RESPONSE.md` and the reviewer's own `REVIEW.sha256`).

## F6 (discoverability): resolved, raw attempt 01 preserved

`README.md` gained a dated clarification (later commits, the two new CTests, `verify_model_controls.py`, `host_controls/`, round-1/2 records, native FROZEN files,
"treat N1-N4 as unrun here"). `host_controls/INDEX.md` marks `attempt01-INVALID/` INVALID with the stale-binary reason and says its `all_expected: true` field is not a result.
`attempt01-INVALID/model_controls.json` is unedited (`"all_expected": true` still present at line 427; zero diff). The stale `predict.py` comment is left because that file is frozen,
which is the correct reason. The README's verbatim old record sentence about "75 registered" is explicitly superseded rather than rewritten.

## F5: independent validation

### 1. Oracle independence

`r3/oracle.py` is mine. It defines the seven cases from the written definitions (`a = total / (Z h (2-h))` etc.), not from the author's JSON, and does not import `predict.py`.
It computes, per algorithm (`legacy`, `finite`, `uncentred`) and per frame:
- exact `Fraction` per-frame maxima from the pair-domain corners, plus exact sampling of 60 random in-image pairs per frame that must never exceed the corner maximum;
- a float64 scan of **every** in-image pixel pair (`np.diff` over the full 768x512 grid, no corner argument), required to agree with the exact value to 1e-9;
- the early-exit trace (running maximum, strict `> 3`, break after the frame).

Only after deriving did it compare with `predictions_iter2.json`: **all 7 coefficient sets (exact strings), all 21 rational values and all 21 decisions match** (`r3/oracle_iter2.txt`, `ALL MATCH AUTHOR`).
The `coeffX_float`/`coeffY_float` arrays the wrapper injects equal `float()` of my independently derived Fractions exactly. Running the author's `predict_iter2.py --out r3/…` regenerates the committed JSON byte-for-byte (sha256 `6ff11cb5…859e`).

### 2. Production helper, order and values

`r3/harness.cpp` compiles the real `src/local_motion_guard.h` (`-std=c++17 -O2 -Wall -Wextra -Werror`, `double` like `RFLOAT` in the default build)
with a model whose `getShiftAt` body is extracted verbatim from `src/micrograph_model.cpp`, and the real legacy block extracted verbatim from `36913740:src/motioncorr_runner.cpp:3917-3935`.
It makes the production call `maximumNeighbourShiftDelta<double>(model, 768, 512, 12, 3.0)`, finds the stopping frame by prefix calls, and takes the no-early-exit running maximum per frame with a huge stop value.
The N4 mutant is the same header with the four ` - Real(0.5)` removed (the replacement `setup.sh` performs; count 4 asserted).
Result (`r3/out_cand_iter2.txt`, `out_mut_iter2.txt`): **0 mismatches against my oracle for 21 value/stop/decision cells and all per-frame running maxima to 1e-12.**

| Case | Legacy (base) | Finite (candidate) | Uncentred (mutant) | Min relative margin to 3 at any evaluated frame (cand) |
| --- | --- | --- | --- | --- |
| A_x | 1.753420 accept z11 | **3.181818 reject, stop z10** | 1.748860 accept z11 | 4.545% (frame 9, 2.8636) |
| A_y | 1.755132 accept z11 | **3.181818 reject, stop z10** | 1.748289 accept z11 | 4.545% |
| B_x | 3.282981 reject z8 | 2.700000 accept z11 | 3.276145 reject z8 | 10.0% (cand); 4.2% legacy frame 7 |
| B_y | 3.288128 reject z8 | 2.700000 accept z11 | 3.277861 reject z8 | 10.0%; 4.1% legacy |
| E | 3.240000 reject z6 | 2.970000 accept z11 | 3.235781 reject z6 | 1.0% (decision only, no printed value) |
| F | 0.021484 accept | 0.021484 accept | 0.021484 accept | 99.3% |
| G | 5.454545 reject z2 | 5.454545 reject z2 | 5.454545 reject z2 | 9.1% (frame 1, 2.727) |

Order: the helper breaks after the frame whose running maximum exceeds the threshold, which is what the oracle and harness reproduce. Printed value is the stopping-frame running maximum
(A cand 35/11 = 3.181818; grader tolerance 2e-5 relative = 6.4e-5 absolute; ostream default precision 6 gives 3.18182, error 5e-6).
The mutant vs candidate decisions differ on A_x, A_y, B_x, B_y and E, so the N4 "kills at least one" condition holds with margin to spare.

### 3. Near-threshold fragility: iteration 2 removed it; iteration 1 had it

Negative control, **old input** (`r3/oracle_iter1.txt`, `perturb_iter1.txt`): with the iteration-1 A coefficients the candidate's frame-10 value is exactly 3 in rationals (margin 0.000%).
Through the production helper in double, the exact injected coefficients give running maximum 2.99999999999995 at frame 10 (stop frame 11, value 3.3), but random coefficient perturbations
of relative size 1e-12 already change the stop frame in **92/200 (A_x) and 102/200 (A_y)** trials, and 94-113/200 at every size from 1e-10 to 4e-2. The F5 mechanism is real and a coin flip.

Iteration-2 candidate A rows (`r3/perturb_iter2.txt`, production helper, 200 trials per size per case, random per-coefficient signs and magnitudes, zero coefficients given absolute noise):
- **0/200 changes** in stop frame or decision for A_x, A_y, B_x, B_y, F, G at every size up to 4e-2 (finite, uncentred and legacy algorithms alike), and for E up to 1e-2;
  E changes in 79/200 only at 4e-2, which is expected because its margin is 1% (it is a control, not a defect).
- Deterministic scalings give the exact margin: A flips stop frame at -6% (to z11) and +5% (to z9) but not at ±4%; E flips decision at +4%. So the control has power and the margin is the real distance, not an artefact.
- Fit rounding scale is orders of magnitude below the smallest margin (1% for E; 4.5% for the value-witnessed A rows), so the iteration-2 printed values are deterministic.

This also answers my predecessor's request that no value witness sits at a tie: no evaluated frame of any case and algorithm is within 0.5% of 3, and the nearest value-witnessed frame (A frame 9) is 4.5% off.

### 4. Wrapper and grader on synthetic rows (not native evidence)

I inspected `chain_iter2.sh`, `n3_iter2.py`, `tools/n3.py`, `runlib.py`, `lane.sh`, `setup.sh`, `stage.sh`, `build.sh`, `gpu_locked.sh`, `health.sh` before running anything.
`n3_iter2.py` rebinds `n3.PRED`, `n3.CASES`, `n3.N3` after import; `run()` and `grade()` read those globals at call time, so the iteration-2 predictions and the `n3-iter2/` output directory are used.

`r3/fakegrade.py` builds a fake scratch under `r3/fake/` (symlinking the worktree as `src-cand`, read-only) with 40 synthetic rows (5 arms x 7 cases + `Z_no_overlay` each), whose log lines, STAR coefficients
and images come from **my** oracle, then runs the unmodified `n3_iter2.py grade`:

| Test | Result |
| --- | --- |
| T0 complete synthetic iteration-2 rows | exit 0: runs PASS 40, pairs PASS 16, N4 PASS (supports all 40 rows and N4/Z) |
| T1 candidate A_x prints iteration-1 value 3.3 | exit 1, FAIL `guard value 3.3 vs 3.1818…` |
| T2 candidate A_x prints the tie value 3.0 | exit 1, FAIL (same reason) |
| T3 one mutant row missing | exit 1, UNRUN 1, N4 FAIL |
| T4 mutant A_x behaves like the candidate | exit 1, row FAIL (decision, value, STAR presence), N4 FAIL |
| T5 CUDA row without the GPU1 UUID witness | exit 1, FAIL `GPU1 not witnessed` |
| T6 `Z_no_overlay` run carrying an overlay line | exit 1, FAIL |
| T7 overlay witness reporting `n_frames=11` | exit 1, FAIL |
| Empty fake scratch (`fake_empty`) | exit 1: 40 UNRUN, pairs 0, N4 FAIL (deliberate fail-closed, `RESULTS.json` written; not native qualification) |

T1/T2 show the grader's expectations are the iteration-2 ones; a run that behaves like iteration 1 cannot pass it.

### 5. Static review of `chain_iter2.sh` and lane

- **No N1/N2 rerun.** Stages: `i2-health-start`, five overlay builds (`ov-base/ov-cand/ov-mut` CPU, `ov-base/ov-cand` CUDA), `i2-n3-cpu`, `i2-n3-gpu` under `gpu_locked.sh`, `i2-n3-grade`, `i2-health-end`. No tutorial movie, no CTest.
- **Fresh scratch/output binding.** `lane.sh` restricts `G_SCR` to `/mnt/clathrin/alex-motioncorr-guard264-20261022-*`. `setup.sh` refuses existing trees. `build.sh` refuses an existing build dir (exit 4), `stage.sh` refuses any existing stage artefact,
  `n3.run` refuses an existing run directory. Pointed at the iteration-1 scratch, the first overlay build would exit 4 and stop the chain; `src-cand` there also lacks `predictions_iter2.json`, so `n3_iter2.py` would fail at import. Outputs go to `n3-iter2/`.
- **Chain mutual exclusion.** Iteration 2 takes the same nonblocking `/tmp/motioncorr-guard264-cpu14-15.lock` the iteration-1 chain holds for its lifetime, so it exits 5 rather than overlapping a live iteration-1 chain; it also probes `/tmp/motioncorr-i61-cpu-14-15.lock`. Build lock and GPU1 correctness lock are nonblocking (exit 5), health runs pre and post under the GPU lock, GPU1 is selected by UUID with process-family witness, CPU 14-15, one numeric thread. First nonzero stage stops the chain; nothing retries.
- **Overlay and mutant.** Unchanged from iteration 1 (test-only, applied to separate trees; mutant = uncentred header + overlay). Same limits: injected observations test fit/guard/fallback/reconstruction wiring on a known model, not motion-estimation accuracy; N4 is CPU only.

## Gate, tolerance, source, default, policy

Unchanged: the 3 px threshold and strict `>`, the grading tolerances (value 2e-5 relative, coefficients 1e-5), the estimator, defaults, policy, and every iteration-1 prediction. Only the constructed A totals (3.3 to 3.5) differ, in new files.
The other five cases reproduce the iteration-1 rational predictions exactly (checked by me from both JSON files: coefficients and `value_rational` identical for B_x, B_y, E, F, G; changed for A_x and A_y only).
The change is motivated by review round 2 and the round-2 suggestion (a total near 3.5), not by any native outcome; `FROZEN-ITER2.md` states no iteration-1 N3 output had been read. I cannot verify that claim from here.

## Unresolved / prerequisites

1. **Native iteration 2: not run and not authorised.** Parent decides when, after the original chain is terminal (the CPU lock enforces non-overlap). Run needs a new commit, a bundle, a fresh scratch named by that commit's sha12, `setup.sh`, then `chain_iter2.sh`.
2. **F3** (non-finite fitted models accepted by both guards): carried, out of scope, source unchanged.
3. **F4** (maintainer sign-off for the intended RELION `ad0b230` parity change): carried, not in the branch, not assumed.
4. **Review currency.** A change to source, tests, tools or frozen iteration-2 predictions needs a fresh round; evidence-only additions can be assessed separately. If the parent amends the commit before running, the `src` tree must still equal `52affe31` and `predictions_iter2.json` must still hash `6ff11cb5…859e`.
5. Native N1, N2 and original N3/N4 results (iteration 1) are not reviewed here and stay as the parent records them.

## Informational notes (non-blocking)

- **I-1.** `n3.grade` raises `FileNotFoundError` (exit 1, no `RESULTS.json` written) if a row has `RUN.json` but no output MRC (reproduced: `r3/missing_mrc_grade.txt`). It fails closed and the stage log keeps the traceback; the chain would already have stopped on a nonzero run stage, so only an rc 0 run without output reaches it. Inherited from iteration 1 and not changed.
- **I-2.** `Z_no_overlay` has no frozen expected decision; it passes whichever way the real fixture goes provided the guard line and STAR local-model block agree. Inherited, and it serves as the "overlay off" control.
- **I-3.** Neither the wrapper nor `grade` re-verifies the `predictions_iter2.json` hash. Recording `sha256sum predictions_iter2.json` (expect `6ff11cb5…859e`) in `SOURCES.txt` at setup would make the binding auditable. Suggestion only.

## Statuses kept as-is

Host helper and real-model controls from rounds 1-2: PASS (unchanged, not rerun here; source identical). Native CPU/CUDA/nvCOMP CTest, N2, N3, N4 at any SHA: UNRUN for the purposes of this review.
No timing, accuracy or science claim. Arithmetic/control readiness of the iteration-2 proposal: **yes**. Native qualification: **no evidence yet**.

## Retained artefacts (this directory)

`r3/oracle.py`, `perturb.py`, `fakegrade.py`, `harness.cpp` (+ `getshift_body.inc`, `legacy_block.inc`, `inc_cand/`, `inc_mut/`), compiled `harness_cand`, `harness_mut`,
logs `oracle_iter2.txt`, `oracle_iter1.txt`, `perturb_iter2.txt`, `perturb_iter1.txt`, `fakegrade_out.txt`, `out_cand_iter2.txt`, `out_mut_iter2.txt`, `empty_grade.txt`, `missing_mrc_grade.txt`,
`predictions_iter2.regen.json`, fake scratches `r3/fake/`, `r3/fake_empty/`. File hashes: `r3-hashes.txt`. `REVIEW.md` hash: `REVIEW.sha256` (computed after writing).
