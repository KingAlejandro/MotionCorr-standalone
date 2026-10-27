# Round-2 read-only review: PR 289 native CCF DC prototype (delta 94e3957 + 37e6cac)

Reviewer: Opus, independent, read-only. Date 2026-10-26.

## Verdict

- **Source.** `src/` is byte-identical at b750, 94e and 37e (tree `80cbd7a8df2e0d88b82cda0c855a6ea81f165565`). There is no production arithmetic delta, and the round-1 source clearance stands.
- **B1 (CMake argv).** The code fix is correct: a host CMake generation for def/exp/iso gives no empty argv elements and the right wrong-kind controls in each build. **Venue CTest evidence is still missing**: `evidence/venue_attempt2/`, which ROUND1_RESPONSE cites, does not exist at 37e. B1 stays open until that evidence lands.
- **Retained per-case K267 CLI (37e).** CLEAR. The expected-stage declarations match the pinned commands. A missing CUDA batched or single path yields INCONCLUSIVE or INVALID, never a coverage PASS.
- **N tier.** **NOT ADMISSIBLE as written** (MATERIAL N1): `n_score` p95 is not the retained metric, so C-REPRO would fail on 12 of 16 rows for scorer reasons alone.
- **Historical N truth.** The explicit retained analytic definition is identified, and a host check against the retained STAR files confirms it (see the truth section).

## Pins

| Item | Value |
|---|---|
| Reviewed source (round 1) | `b75039a04f8d3937660066fcb391c79f6083e1f0` |
| Docs | `f293ab9dd9f80b53727832c49fbdcfb7d7a81f4e` |
| Round-1 response | `94e3957029221292463565be7c13707f6836dd1c` |
| Final snapshot | `37e6cac064b38d2e49dacfef959cde0b70dd036b` (parent 94e) |
| Trees at 94e and 37e | src `80cbd7a8…` (= b750); tests `fdedf1db…`; CMakeLists.txt `f9f59612…` |
| 94e..37e diff | CONTROL_PLAN, PINS.json, counts.json, ledger.csv, make_ledger.py, ROUND1_RESPONSE, `tools/ccf_dc_native_rows.py`, `tools/test_ccf_dc_native_rows.py` |
| Blobs at 37e | ccf_dc_native_rows.py `f52d6fad`, ccf_dc_tap_field.py `1491e46d`, generate_ccf_dc_n_controls.py `e4d5878a`, test_ccf_dc_native_rows.py `3f9e4978`, test_ccf_dc_tap_field.py `fa480190`, tests/test_ccf_dc_request.py `89acab77` (all equal to PINS.json) |
| Retained references | `evidence/retained_render_report.json` blob `52bf72f5` = ed1a0e3f `results/nc/movies/render_report.json`; `nc-scores.json` sha256 `dfb0fc42…` at both 4fa272f6 and ed1a0e3f |

## Findings

### MATERIAL

**N1. The `n_score` p95 is not the retained W5 metric.** Location: `tools/ccf_dc_native_rows.py:285-290` @37e, together with `CONTROL_PLAN.md:45` ("the ROI … is immaterial") and C-REPRO at `:47`.
- What it does: `n_score` takes the percentile over N frame vectors.
- What the retained scorer did: `C.score(C.field(g), truth)` on the dense ROI y[12:84] x[12:116], i.e. each frame repeated 72×104 times. Percentile interpolation differs between the two.
- Host check: I scored the 16 retained arm-a production-stop STAR files (ed1a0e3f) with the 37e `n_score` and the generator truth.
  - rms, max and trajectory RMS match the retained values to ≤1.1e-16.
  - p95 differs by up to **0.1204 Å**, and by more than 1e-5 in **12 of 16** rows (e.g. vel1_N13 prod 0.7273→0.6068; vel0_N9 prod 0.7993→0.6877).
  - A dense-ROI broadcast reproduces all 16 retained p95 values with a difference of exactly 0.0.
- Consequences:
  - C-REPRO would fail on 12 rows even with bit-identical producer output.
  - Near the 0.40 Å p95 limit, the per-frame p95 can turn a retained FAIL into a PASS.
- Fix (restores the retained definition; no gate change):
  1. Broadcast the per-frame error over the manifest ROI before `vector_metrics`.
  2. Correct the "immaterial" sentence.
  3. Add a pure test that scores the retained STAR/runtime blobs against `retained_cpu_reference.json` (about 1e-12).

**N2. A missing runtime tap is silently skipped.** Location: `tools/ccf_dc_native_rows.py:261` (K) and `:305` (N).
- Runtime scoring runs only `if (run/"tap.json").exists()`.
- An rc-0 experiment row with no tap (for example, a harness that did not set `MC_DIAG_MODEL_OUT`) is therefore graded `SCORED` with only the STAR representation and no marker.
- The plan requires runtime and STAR to be scored separately. A placeholder tap is tested; an absent tap is not.
- Fix: add a declared `tap_expected` flag (default on for experiment rows) and make an absent tap INVALID, or a runtime MISSING that blocks the row.

### LOW

- **L1. Selectivity is checked only at the declared site.** `grade_witness` (`:132-150`) checks it at the declared site alone. On CUDA, `cuda_single.local` (retry) is checked only for 0≤zeroed≤eligible. A wrong-arm zero on the retry path, or a local call reached through `cuda_single` on a global-only row, is not flagged. The C++ oracle covers the retry arithmetic. Apply the selected/unselected and not-requested rules to every reached (site, stage).
- **L2. `--expect-mismatch` accepts any `AssertionError`** (`tests/test_ccf_dc_request.py:52-59`), including assertions in the common prefix. I traced each of the five registered controls to a kind-specific assertion: `:117` needle for def→experiment; `:107` refusal for exp/iso→default; `:130` identity for exp→iso and iso→experiment. The paired positive `CcfDcRequest` shows the prefix passes in the same build, so this is acceptable. Matching the expected assertion message would be tighter.
- **L3. Undeclared thread-count deviation on N rows.** `run_env` sets `OMP_NUM_THREADS=8` for N rows, but the retained N runs used 2 (`run_ncontrols.py:26` @ed1a0e3f). The `n_argv` docstring nevertheless claims the retained command. Declare the deviation or use 2. C-REPRO would expose any effect.
- **L4. `identity_report` can call two failures identical.** At `:320-336` it reports `identical=True` for two runs with the same nonzero exit. B3 should also require rc 0.
- **L5. Stale references.**
  - `CONTROL_PLAN.md:45` cites render-report blob `cae19f3f`, which is not a git object; the correct blob is `52bf72f5`.
  - ROUND1_RESPONSE B1 points to `evidence/venue_attempt2/`, which is absent.
  - The response's "def 2/2, exp 3/3, iso 3/3" counts only the request/wrong-kind tests. This block now registers 4 tests in def and 6 in exp/iso (TapField, RowsPure, RowsNative).
- **L6. N-tier `both` rows are not tagged `SEL`.** They are also no-local-requested selectivity observations. Grading already reports local as NOT_APPLICABLE, so this is labelling only.
- **L7. The new CTests import numpy.** The venue interpreter is `/home/alex/.mc-venv/bin/python3` (attempt-1 configure log). Venue evidence must show CcfDcTapField, RowsPure and RowsNative as Passed, not failing on import. Generator byte-identity depends on numpy FFT: it passed here on numpy 2.5.4 / CPython 3.15.1. Record the numpy version used at the venue.

## Retained K267 CLI and expected stages (37e): CLEAR

- **Patch grid.** `K267_PATCHES` and `k267_argv` match `docs/post_rc0/s1/synth_combined/run_v2_cases.py` exactly: 3x3 for affine/pedestal/noisy, 1x1 for the other five, `--j 8`, OMP 8, the same flags. The only declared deviation is that `--skip_logfile` is dropped, with a native control to show it changes nothing. The `--patches` override exists only for separately labelled held configurations.
- **Expected stages.** `k267_stages` derives the stages from the patch count. N rows are global only.
- **B4 rows.** These are the 12 rows (3x3 × CUDA × exp × 4 arms). For every arm, they need `cuda_single.global` and `cuda_batched.local` with eligible>0, otherwise INCONCLUSIVE. Single-only local is INCONCLUSIVE (pure test). A CUDA row that touches a CPU site is INVALID. A CUDA-declared row graded on a CPU run is INVALID.
- **SEL rows.** These are the 20 rows (1x1 × 2 backends × local/both). Local eligible must be 0, otherwise INVALID; coverage is reported `NOT_APPLICABLE (… no-op selectivity)`; row status is SCORED and never local coverage. A caller declaring local on a 1x1 run gets INCONCLUSIVE.
- **Result.** No missing GPU path becomes a PASS. One limit: def-binary CUDA rows (B3) carry no witness, so they show identity only, not route.

## Historical N truth and input equivalence

- **Explicit definition.** The retained truth is defined explicitly in the pinned retained script `render_ncontrols.py` @ed1a0e3f: `tt = np.arange(N)[:,None]*vel`, saved as `{name}_truth.npy`. The frames are `shiftF(Ft, -f*vel)`. This is identical to `generate_ccf_dc_n_controls.truth`. The gap is therefore closed by an explicit retained definition, not only by matching residuals.
- **Byte identity.** The host run of `test_n_control_generator` reproduces all 8 MRC and 8 STAR files byte for byte against the retained render report.
- **Sign, time origin and gauge.** Checked on the retained STAR files:
  - Truth `+f*vel` reproduces rms, max and trajectory RMS to ≤1.1e-16.
  - With the sign negated, the rms differs by at least 4.10 Å.
  - With a one-frame time offset, it differs by at least 0.063 Å.
  - vel1_N20 iso STAR frames 11-19 track `+f*vel`, and frames 2-10 sit on a wrapped branch, which explains the retained 10.495 Å FAIL. That FAIL is preserved: the 37e `n_score` gives 10.4948 Å, FAIL.
- **Limit.** W5 `common.py` is not in git. My identification of its p95 as a dense-ROI broadcast is an inference, although it reproduces all 16 rows exactly.

## Performed vs UNRUN

**Performed** (host only, at most 2 threads; scratch `/tmp/mc-native-ccf-dc-opus-review-20261026-r2`, about 3 MB):
1. Git tree/blob pins for b750/94e/37e/f293/ed1a0e3f/4fa272f6. Full read of the b750..37e diff for CMake, tests and tools, and of the plan/ledger sections.
2. `cmake-check/`: CMake 4.4.4 generation of the exact 37e block (lines 573-612) for def/exp/iso, with `/bin/echo` as the interpreter. Result: 0 empty args, and the per-build test sets listed above. sha256: block `4ec5bd10…`, def `030fa052…`, exp `122654fb…`, iso `ee097608…`.
3. `test_ccf_dc_tap_field.py` (37e archive), run with uv offline numpy 2.5.4: 6/6 OK, rc 0 (`test_tap_field.out`).
4. `test_ccf_dc_native_rows.py` pure: 7 OK, 12 native skipped (no binary), rc 0 (`test_native_rows_pure.out`).
5. `scripts/nscore_retained.py`, scoring the 16 retained STAR/runtime files with the 37e `n_score` (`nscore_retained.out`), and `scripts/p95_probe.py`, per-row p95 against a dense-ROI broadcast (`p95_probe.out`).

**UNRUN:**
- any MotionCorr build, CTest, oracle, mutant, native/GPU/CUDA run or SSH;
- `CcfDcRowsNative`;
- venue B1/B2 for the CMake fix;
- C-REPRO, B3/B4/SEL, and all K/N/M jobs.

No failure was discarded, and no repo edits were made.

## Mandatory before parent release of the tiny K/N tiers

1. A fix commit for N1 (and N2), delta-reviewed. L1-L5 are optional at the author's discretion.
2. Venue CTest evidence at the final source SHA for def/exp/iso:
   - `CcfDcRequest` and every `WrongKind` passing;
   - CcfDcTapField, RowsPure and RowsNative passing;
   - G1-G6 and all 7 mutants rejected;
   - Python and numpy identity recorded.
3. Parent pins: source SHA, three binary hashes, K267 fixture MANIFEST, N MANIFEST (rendered at the venue and matching the retained pins), GPU UUID, and the CLI per `k267_argv`/`n_argv` including the OMP decision (L3).

The 16-movie tier stays HELD. This review does not clear promotion, a full 100, M1 or DC adoption.
