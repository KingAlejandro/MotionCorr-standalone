# Round-3 read-only delta review: PR 289 native CCF DC (ad87df9 vs 37e6cac)

Reviewer: Opus, independent, read-only. Date 2026-10-26. Scratch: this directory (~8.5 MB).

## Verdict

- **Source/adapter at ad87: CLEAR, no BLOCK, no MATERIAL.** Round-2 N1 and N2 are fixed and both have tests that fail when the fix is reverted. Two LOW findings remain, both optional.
- **Science: no claim.** Venue evidence at the final SHA is still UNRUN. This covers def/exp/iso CTest (CcfDcRequest, WrongKind, G1-G6, mutants, CcfDcTapField, CcfDcRowsPure, CcfDcRowsNative) under the recorded `.mc-venv` Python/NumPy. The ad87 tree has only `evidence/venue_attempt1/`, and the response correctly marks B1 and L7 OPEN. Parent release needs that evidence plus the source, binary, input, CLI, GPU UUID, affinity and lock receipts.

## Pins (verified with git objects; checkout HEAD = PR head = ad87df9eb996e692f60394f0fcafdadc2c9305fc)

- **Parent.** ad87's parent is 37e6cac064b38d2e49dacfef959cde0b70dd036b.
- **Source.** The `src` tree is `80cbd7a8…` at b75039a0, 37e and ad87. `git diff b75039a0 ad87 -- src` is empty.
- **Unchanged since 37e.** `tests` tree `fdedf1db…`, `CMakeLists.txt` `f9f59612…` and `test-data/generate_ccf_dc_n_controls.py` `e4d5878a`.
- **37e..ad87 diff.** The diff touches only the following:
  - `tools/ccf_dc_native_rows.py` (blob `52d5775c`) and `tools/test_ccf_dc_native_rows.py` (blob `d689a527`);
  - CONTROL_PLAN, PINS, counts, ledger, make_ledger and make_pins;
  - ROUND1_RESPONSE, ROUND2_REPORT, ROUND2_RESPONSE and `round2_n1_evidence/`;
  - `evidence/retained_n_runs/` (32 files plus INDEX).
- **ROUND2_REPORT in the PR.** sha256 `867a5249…` is byte-identical to my R2 report. The R1 report hash `0affbfc4…` is unchanged.
- **Retained N runs.** All 32 INDEX entries have source blob at `ed1a0e3f` = INDEX `git_blob` = committed ad87 blob, and the sha256 matches. The INDEX set equals the tracked set (`index_check.out`).
- **PINS.json.** All 30 pinned paths match their ad87 blobs (`pins_check.out`).
- **Counts.** The ledger has K 96 / N 64 / M 16 = 176 rows and SEL 52 (20 K + 32 N arm `both`). `pairs.csv` has 112 rows. counts.json agrees.

## Round-2 findings

**N1 (dense-ROI p95): FIXED.** `n_score` (`tools/ccf_dc_native_rows.py:314-324`) builds a (N, y1-y0, x1-x0, 2) broadcast of the per-frame Å error and passes it to the unchanged `vector_metrics`.
- `vector_metrics` uses the Euclidean norm on the last axis, linear `np.percentile`, rms and max. There is no new gate and no floor or offset subtraction. Limits remain .20/.40/.80, pixel size 0.885 and gauge frame 0.
- `grade_n` passes the manifest ROI `[12,84,12,116]` from the unchanged generator. The ROI gives 72×104 points; the axis order does not matter for a spatially constant field.
- `test_n_score_reproduces_all_16_retained_rows` passes on the retained files: runtime and STAR rms/p95/max/verdict, plus trajectory RMS, all agree within 1e-12. The harmful vel1_N20 iso row is still STAR rms 10.4948 Å, FAIL.
- Test power: reverting to `vector_metrics(err)` makes both the 16-row test and the one-in-five quantile test fail (`mut_frame_p95.out`).

**N2 (absent tap): FIXED.** I ran `scripts/probe.py` (`probe.out`) through `grade_n` on fabricated run directories, using the retained vel0_N5 STAR and tap and no producer.
- **Tap content.** These tap variants are all INVALID with no runtime score: absent, empty, `{"status":"incomplete"}`, malformed JSON, NaN, 4 of 5 frames, 17 coefficients, `local_enabled=false` with nonzero coefficients, and a string `local_enabled`. A tap that disagrees with the STAR by 1e-3 px is also INVALID.
- **Run preconditions.** A valid tap does not rescue a failed run: rc 1 gives FAILED_RUN, a missing `corrected_micrographs.star` gives INCOMPLETE_PUBLICATION, and an absent witness gives INVALID. `_head` returns before tap handling.
- **Declarations.** Declaring a tap on a def build raises ValueError. A def row with a stray tap is SCORED with `runtime_representation: NOT_REQUESTED` and no runtime score.
- **K path.** Non-TapError bridge or STAR read-back exceptions are now INVALID (`:305-306`). Only `check_case` refusals stay results (`:307-310`).
- **Test location.** The K and N absent-tap tests (`test_absent_tap_fails_closed`, `test_def_build_row_is_star_only_by_declaration`) are in NativeRows, so they skip without a binary. They count only once venue CcfDcRowsNative passes. My host probe covers the same logic.

**L1 (all-site selectivity): FIXED** (`:143-152`). Reverting it to declared-site-only fails `test_witness_selectivity_on_every_reached_site` (`mut_declared_site_only.out`). Under the 37e code, the wrong-arm retry case and the global-only local-reach case would have been VALID, so the test discriminates.

**L3 (N threads), L4 (identity), L5 and L6: FIXED as stated.**
- `N_OMP=2` and `K267_OMP=8`, with a pure test.
- `both_succeeded` requires rc 0 in both runs. Its test is native-only.
- Render-report blob `52bf72f5`; venue citation corrected; N `both` rows tagged SEL.

**L2:** accepted as before. **L7:** OPEN, venue.

## New LOW findings (optional; neither changes a score)

- **LOW-1. An N tap with `local_enabled=true` and nonzero local coefficients is SCORED.** Location: `tools/ccf_dc_native_rows.py:344-355`. Probe row `le_true_coeffs`. `grade_n` reads only `tap["global"]`, so a tap claiming a local model on a global-only 1x1 row is not rejected. The witness still rejects any reached local call, and N scoring uses only the global shifts, so no verdict changes. Fix: make an N row INVALID when `tap["local_enabled"]` is true.
- **LOW-2. INVALID tap rows can carry `runtime_representation: "SCORED"`.** Location: `:286` and `:343`. The field is set before `load_tap`, so rows that end INVALID on a tap error still say SCORED (probe rows empty, placeholder and so on). `row_status` governs, so this is a labelling hazard only. Set the field after a successful load, or call it REQUESTED.

## Performed vs UNRUN

**Performed** (localhost, OMP/BLAS at most 2 threads, uv offline CPython 3.15.1 / NumPy 2.5.4; all inputs from `git archive ad87`):
1. Git pin checks above (`index_check.out`, `pins_check.out`), and a full read of the 37e..ad87 tools/test/response/plan diff.
2. `test_ccf_dc_native_rows.py`: rc 0, 11 pure OK, 15 native skipped (no binary) (`test_ccf_dc_native_rows.out`). `test_ccf_dc_tap_field.py`: rc 0, 6/6 OK (`test_ccf_dc_tap_field.out`).
3. `scripts/probe.py`: N2 fail-closed variants (`probe.out`).
4. `scripts/mutate.py`: two revert mutants on scratch copies, both caught (`mut_*.out`). The copies were deleted.

My first test attempt used `python -I`, and failed rc 1 on import because `-I` drops the script directory from `sys.path`. Its outputs are retained as `test_native_rows_pure.out` and `test_tap_field.out`; the rerun used `-E -s`.

**UNRUN:**
- any MotionCorr build, CTest, oracle, mutant, native/GPU/CUDA run, SSH or venue job;
- CcfDcRowsNative, including the native-only N2 and L4 tests;
- C-REPRO, B3/B4/SEL and all K/N/M jobs;
- `make_ledger` regeneration. Only the counts were cross-checked.

No repo edits.
