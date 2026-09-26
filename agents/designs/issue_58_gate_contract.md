# Architectural Design Specification: #58 — MotionCorr numerical gate contract

- **Issue Reference**: [#58](https://github.com/KingAlejandro/MotionCorr-standalone/issues/58) — Clarify MotionCorr numerical gate semantics and relative-RMSE documentation
- **Track**: `track:validation`
- **Depends on**: #4 (original gate design, `agents/designs/issue_4_define_the_reference_outputs_and_numeric.md`), PR #19, PR #23, PR #25
- **Coordinates with**: #59 (synthetic motion truth), #60 (perturbation calibration), #61 (scientific non-inferiority)
- **Status**: Proposed
- **Scope**: Gate semantics, documentation correctness, and fail-closed behaviour of `tools/compare_motioncorr.py`. **No numerical acceptance threshold is changed.**

---

## 1. Problem statement

Three separate claims are currently conflated in the repository's documentation and in how results are read:

1. **Exact CPU regression** — does this build reproduce the recorded standalone CPU reference byte for byte?
2. **CPU-backend image agreement** — how far does a new backend's corrected micrograph sit from the CPU reference, in pixel units?
3. **Scientific acceptance** — does the backend preserve recoverable cryo-EM signal?

`docs/reference_gates.md` presents (1) and (2) as "Gate 1" and "Gate 2" and does not distinguish (3) at all. Because "Gate 2" is titled *Numerical Equivalence Gate*, a Gate 2 failure reads as a loss of scientific validity. It is not: the CUDA rerun recorded in `docs/cuda_24_movies_gate2_rerun.json` fails only the relative-RMSE check, by a factor of 2.9–10.1, while every trajectory, absolute-RMSE, max-pixel, STAR and exit check passes. That result bounds CPU disagreement; it does not measure signal loss.

The documentation also misstates the metric itself:

- The Gate 2 table justifies the absolute limit `Image RMSE <= 0.020` with "Relative RMSE < 0.1% of micrograph standard deviation". Those two statements are equal only when the reference standard deviation is exactly 20.0. On the committed synthetic fixture it is 64.28; on the 24 tutorial micrographs it is 0.806–0.935. On the tutorial data the absolute limit is **21.4x–24.8x looser** than the relative limit, so the stated justification is false by more than an order of magnitude in the direction that matters.
- The #4 design spec (§3.3) specifies the relative metric as relative L2 error, `||Δ||₂ / ||I_ref||₂`. The code implements `RMSE / σ(I_ref)` — normalised by the **population standard deviation**, not the L2 norm. These agree only for a zero-mean reference. On the committed fixture they differ by 13.03x.
- The Gate 1 table lists `Image RMSE <= 1.0e-7` and `Image Max Absolute Error <= 1.0e-7` as acceptance thresholds. Neither is evaluated in `--gate exact`; the enforced condition is raw byte identity of the pixel payload.
- Section 6 states that a directory containing several corrected MRC or per-movie STAR files makes "the tool fail". The tool records the ambiguity in `errors` and still exits `0`.
- `--gate custom` is implemented but documented nowhere.

Finally, the OR-to-AND change is unrecorded. `93556b4` gated the image on `rmse > tol AND rel_rmse > 1e-3` — either metric passing was enough. `6c8a105` made both independent requirements. That is a numerical-policy change with no note in any document.

---

## 2. Objectives and non-objectives

### 2.1 Objectives
- **O1** Publish one contract that separates CPU regression, backend CPU-agreement, motion truth, and scientific outcome into distinct tiers, each with its own question, oracle, enforcement status and owning issue.
- **O2** State the relative-RMSE formula exactly as implemented: symbol, denominator, aggregation domain, units, and constant-reference behaviour.
- **O3** State, per gate profile, which metrics are enforced and which are reported only.
- **O4** Record the OR-to-AND transition and the denominator change as numerical-policy history.
- **O5** Close the two fail-open paths where the tool reports a problem, or cannot see the payload it claims to gate, and still exits `0`.

### 2.2 Non-objectives
- **N1** No change to `0.001`, `0.020`, `5.0`, `0.05`, `0.02`, `1e-4` or `1e-7`. The `0.001` relative limit stays exactly where it is, as a strict CPU-agreement diagnostic.
- **N2** No reclassification of any recorded result. The CUDA rerun stays 0/24.
- **N3** No ground-truth tolerance, local displacement-field metric, perturbation calibration, or downstream science metric. Those are #59, #60 and #61 and are referenced, not implemented, here.
- **N4** No changes to fixtures, `test-data/`, the CUDA path, or any evidence JSON.

---

## 3. Gate tier model

| Tier | Question | Oracle | Profile | Enforced today | Owner |
|:--|:--|:--|:--|:--|:--|
| **A. CPU regression** | Does this build reproduce the recorded standalone CPU reference exactly? | Committed standalone CPU output on the same platform | `--gate exact` | Yes | #4 / #58 |
| **B. Backend CPU agreement** | How far is a new backend from the CPU reference, in pixel units? | Fixed standalone CPU `--j 1` output | `--gate relaxed` | Yes (diagnostic) | #36 / #58 |
| **C. Motion truth** | Is the known injected motion recovered, globally and locally? | Synthetic ground truth | reported only | **No** | #59 |
| **D. Scientific outcome** | Is recoverable signal preserved? | Downstream CTF / FSC / B-factor | not implemented | **No** | #61 |

Two constraints follow and must be stated wherever a result is reported:

- **Tier B is not Tier D.** Passing B does not establish scientific equivalence, and failing B does not establish signal loss. B measures distance from one particular CPU implementation.
- **Upstream RELION parity is a separate axis.** Standalone-vs-RELION 5.1 (#20) and standalone-vs-fixed-standalone-CPU (#23/#25) are different comparisons that happen to use the same profiles. They must never be reported as one number.

Tier B's limits remain uncalibrated against any known amount of lost signal. #60 owns that calibration; until it reports, B is a **change detector**, not an acceptance criterion.

---

## 4. Metric specification (as implemented)

For a single corrected micrograph pair, over all `N = nx·ny·nz` pixels of the reference (`nz = 1` for a corrected micrograph), with pixel values in the MRC file's intensity units:

```
Δ_i          = test_i − ref_i                          (float64)
RMSE         = sqrt( (1/N) Σ Δ_i² )                     intensity units
maxAbs       = max_i |Δ_i|                              intensity units
σ_ref        = sqrt( (1/N) Σ (ref_i − mean(ref))² )     intensity units, population (ddof = 0)
relative_RMSE = RMSE / max(σ_ref, 1e-12)                dimensionless
```

Properties that must appear in the documentation:

- The denominator is the **reference** image's population standard deviation, computed from pixels, not the MRC header `rms` word. It is not the test image, not the L2 norm, and not a per-pixel ratio.
- `relative_RMSE <= 0.001` is therefore equivalent to `RMSE <= 0.001 · σ_ref`, an absolute limit that moves with the dataset.
- **Constant reference** (`σ_ref = 0`): the denominator floors at `1e-12`, so any nonzero `RMSE` yields ~`1e12 · RMSE` and fails; an exactly zero `RMSE` yields `0` and passes. Fail-closed. Before `6c8a105` this branch returned `0.0` and passed unconditionally — that was fail-open.
- Aggregation is **per movie**. There is no dataset-level statistic inside the comparator; dataset verdicts are conjunctive over movies in the wrapper (`tools/compare_cuda_dataset.py` exits nonzero if any expected movie fails or is missing).

Trajectory metrics, over the frames of `data_global_shift`, in the units of `_rlnMicrographShiftX/Y` (pixels):

```
coord_rms_error  = sqrt( (1/F) Σ_f (Δx_f² + Δy_f²) )
max_shift_error  = max_f max(|Δx_f|, |Δy_f|)
```

---

## 5. Enforcement matrix (from code)

`tools/compare_motioncorr.py`, `--gate exact | relaxed | custom`:

| Check | `exact` | `relaxed` | `custom` |
|:--|:--|:--|:--|
| Pixel payload byte-identical | **enforced** | not checked | not checked |
| Core MRC header bytes 0–223 identical | **enforced** | not checked | not checked |
| MRC labels 224–1023, run timestamp masked | **enforced** | not checked | not checked |
| Image absolute RMSE | reported only | `<= 0.020` | `<= 0.010` |
| Image relative RMSE | reported only | `<= 0.001` | `<= 0.001` |
| Image max absolute pixel error | reported only | `<= 5.0` | `<= 5.0` |
| Trajectory coord RMS | `<= 1e-4` | `<= 0.02` | `<= 0.02` |
| Trajectory max shift | `<= 1e-4` | `<= 0.05` | `<= 0.05` |
| STAR float tolerance | `1e-4` | `1e-3` | `1e-3` |
| STAR derived motion fields compared | yes | **excluded** | **excluded** |
| STAR differences | `== 0` | `== 0` | `== 0` |
| Process exit status `== 0` | only with `--test-log` | only with `--test-log` | only with `--test-log` |
| Ground-truth recovery magnitude | reported only | reported only | reported only |

Notes that must be documented:

- `custom` is `relaxed` with a stricter default absolute image RMSE (`0.010`). It is not a separate policy; it exists so `--image-*` / `--shift-*` overrides start from a tighter base.
- In `exact`, `tol_image_rmse = 1e-7` and `tol_image_max_err = 1e-7` are assigned and printed as "threshold" in the human report but never compared. Byte identity is strictly stronger for every finite value except signed zero, where `+0.0` vs `−0.0` gives `RMSE = 0` yet fails byte identity. Exact is therefore stricter than its documented row, never weaker.
- `--image-relative-rmse` defaults to `1e-3` in every profile but is only evaluated outside `exact`.
- The relaxed/custom STAR check excludes `_rlnMicrographShiftX/Y`, `_rlnMotionModelCoeff`, `_rlnAccumMotionTotal/Early/Late`. Global shifts are recovered separately through `data_global_shift`; **local motion model coefficients are compared by nothing** in relaxed mode. That gap is #59.

---

## 6. Fail-open paths to close (O5)

Both are cases where the comparator cannot observe, or has already observed a problem with, the thing it reports on, and still exits `0`.

**F1 — unresolved or ambiguous inputs do not fail.** `input_errors` is assigned into `errors` and rendered in the report, but never sets `gate_passed = False`. When the ambiguity is **symmetric** — a reference and a test directory that each contain two corrected MRCs — both sides resolve to `None`, the image block is skipped, two "Multiple corrected MRCs" errors are printed, and `overall_status` is `PASS` with exit `0`. This contradicts `docs/reference_gates.md` §6 and the stated intent of `6c8a105` ("make MotionCorr reference gates fail closed"). An asymmetric ambiguity is already caught, because the resolved side triggers the missing-pair check.

*Decision:* any unresolved-input error fails the gate. Strictly stricter; no recorded result changes, because every committed comparison resolved cleanly.

**F2 — complete coverage cannot be required.** `report.coverage.complete` is computed and printed, but no caller can ask the comparator to enforce it. Two directories that both contain a STAR and no corrected MRC exit `0` with `coverage.complete = false`. The three Python wrappers each re-implement the coverage check themselves; `tools/run_regression_tests.sh`, the Tier A entry point, does not check it at all.

This is not a currently reachable false pass for Tier A: the committed reference bundle always supplies one MRC, so a missing or ambiguous test MRC is caught today by the pair-resolution check (verified). The flag makes the script's requirement explicit and keeps it true if the reference bundle, the output naming, or the discovery filter changes.

*Decision:* add `--require-complete-coverage`, **default off** so no existing caller changes behaviour, and pass it from `tools/run_regression_tests.sh`.

---

## 7. Deliverables

| Path | Change | Rationale |
|:--|:--|:--|
| `docs/gate_contract.md` | new | O1, O3, O4 — the tier contract, enforcement matrix, policy history, reproducible commands and evidence |
| `docs/reference_gates.md` | targeted corrections | O2, O3 — remove the false justification, correct unenforced Gate 1 rows and the §6 failure claim, document `custom`, link the contract |
| `tools/compare_motioncorr.py` | fail closed on F1; add `--require-complete-coverage` (F2); report the relative-RMSE denominator and its effective absolute limit | O5, O2 |
| `tools/run_regression_tests.sh` | pass `--require-complete-coverage` | F2 |
| `tools/test_compare_motioncorr.py` | additive tests pinning the contract | prevent silent drift of the documented semantics |

Out of scope and explicitly left to their owners: ground-truth tolerances and local displacement-field metrics (#59), threshold calibration (#60), scientific non-inferiority (#61), CUDA root cause (#36), upstream RELION parity (#20).

---

## 8. Verification plan

1. `tools/test_compare_motioncorr.py` passes, including new tests for the denominator identity, constant-reference fail-closed behaviour, exact-gate profile coverage, ambiguous-input failure, and the coverage flag.
2. `tools/run_regression_tests.sh` still passes end to end on a fresh CPU build with the new flag, on `cpu64`.
3. Every numeric claim in the new and corrected documentation is reproducible from committed artefacts (`docs/cuda_24_movies_gate2_rerun.json`, `test-data/fixtures/reference_output/`) with the commands recorded in `docs/gate_contract.md`.
4. `git diff origin/main --stat` touches only the paths in §7.

## 9. Risks

- **R1 — Tightening F1 fails a caller not audited here.** Mitigated: the only directory-mode caller in the repository is `tools/run_regression_tests.sh`; CI's `ctest` target does not invoke the comparator. The change is isolated in its own commit and revertible alone.
- **R2 — The tier contract is read as a proposal to relax Gate 2.** Mitigated: N1/N2 are restated in the contract document itself, and the contract records the current `0.001` result as an unchanged strict diagnostic.
- **R3 — Overlap with #59/#60/#61.** Mitigated: tiers C and D are declared with owners and explicitly *not* implemented; no file owned by those issues is touched.
