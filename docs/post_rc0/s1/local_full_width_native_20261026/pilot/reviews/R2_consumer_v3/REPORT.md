# Review r2: local full-width pilot consumer v3 (Opus, read-only)

Reviewer: Claude Opus 5.5. Branch `experiment/local-full-width-weight-20261026` HEAD `215c37b0743dd63a793650e8f0cfda4a2778ace9`, clean, not edited. Package `/tmp/mc-local-full-width-pilot-20261026/`: `SHA256SUMS_v3` verified 27/27 OK before the review. The package was byte-identical before and after the review (`results/pilot_before.sha256` = `results/pilot_after.sha256`, 52 files). The 24 originals equal R1's `pilot_after.sha256` (`results/ORIGINALS_VS_R1.txt`). No native, GPU, SSH, build, movie or image-intensity work was done. Local runs used uv CPython 3.13.7 with NumPy 2.4.2, OMP/BLAS 1 thread, and under 1 MB of scratch in a tempdir. There was no network access.

**Verdict: no BLOCK. M1 is closed at the consumer level. One new MATERIAL pre-admission coverage gap (M2): the pair and decision layer required by PLAN.md lines 15 and 17 has no code. The remaining findings are LOW.** The draft stays HELD. There is no native producer driver. Every receipt that was admitted was written by the test helper from the same `expected` dict that admission checks against. That proves the consumer logic, not that any producer will obey it.

## What was checked
1. Plan freeze. `SCORER_V3_PLAN.md` hash matches its `.sha256`. Its mtime is 20:24:00 and `score_fields_v3.py` is 20:25:16, so code came after the plan (weak evidence). The code implements plan checks 1–10 and the scoring binding as written.
2. Author suite re-run on current bytes: **109/0** (`results/AUTHOR_TESTS_rerun.json`, `logs/author-tests-rerun.log`). Negatives go through `expect_code`, which requires the exact `AdmissionError.code`. A wrong code, a foreign exception or an admission all count as FAIL (test_score_fields_v3.py:95-104). So the receipt, argv, env, inventory and witness tests target the specific contradiction rather than accepting any exception. The exception is the v2 low-level numerical negatives (lines 339-348), which accept any `Exception`. That is acceptable as a regression check of unchanged v2.
3. Author mutation controls: the run1 survivors (`runtime_hash`, `run_dir`) were caused by weak tests, as ATTEMPTS_v3 says. The strengthened tests are a valid-JSON runtime tamper (line 251-253) and a copied tree with a self-consistent receipt (line 174-175). Both reach the intended guard first. Run3 log shows 11/11 killed. I did not re-run that harness.
4. **Reviewer guard-removal controls on 21 guards that the author's 11 mutants do not cover** (`scripts/extra_mutants.py`, `results/EXTRA_MUTANTS.json`).
   - 17 killed: exit, receipt case, receipt run_dir string, binary, argv equality, cwd, input bytes, declared env, publication hash, stdout, LOG_CASE, truth name, STAR file name, manifest pin, runtime geometry, admit-side placeholder.
   - 4 survived. All are shadowed or untested guards, not broken ones; see T1–T3. A fifth row (`witness_grid_recheck`) had no intended test and is reported only for completeness.
5. **Gap probes** (`scripts/gap_probes.py`, `results/GAP_PROBES.json`). These reuse the author's `World` builder unchanged. All 13 outcomes were as predicted.
6. Pin consistency.
   - `verify_tool_pins` passes for all 15 `tools` entries at the three roots. The comparator pin is `53449d2d…5f0f47`.
   - `V2_SHA256` (score_fields_v3.py:12) equals the admission pin and the file (`e0ef769c…`).
   - The carried-over v1 `tools_sha256` (6 entries) agrees with the v3 entries.
   - `supersedes` equals the v1 admission hash `a094387e…`.
   - Apart from the v3 additions, ADMISSION v3 equals v1, row by row.
   - COMMANDS v3 argv/cwd/env/inputs/witness equal v1 (author test, re-run).
7. Witness and log formats against source at HEAD:
   - `src/motioncorr_runner.cpp:4962` emits exactly `WITNESS_LINE` (score_fields_v3.py:24).
   - `:2183` emits `Working on <fn_mic> with <n> thread(s).`, which is what LOG_CASE (score_fields_v3.py:246) expects when `fn_mic` is the bare `<case>.mrcs`.

## Prior findings disposition
| R1 | status | evidence / residual |
|---|---|---|
| **M1** arm/argv/env/cwd/witness | **CLOSED (consumer)** | Admission checks receipt arm (:180), flag iff ON (:189), exact argv (:193), declared env (:209) and observed controlled env (:213), cwd and staged inputs (:195-207), and canonical run_dir (:170, :184). Probes P1/P2: a fully forged, self-consistent receipt that moves 3×3 ON products into the OFF slot (or the reverse) is rejected by WITNESS, the one check that does not rely on the receipt. Residual P3: for global-only cases nothing product-level distinguishes the arms. PLAN requires those trees to be identical anyway. |
| L1 witness location/format | CLOSED | Reads `output/<case>.log` with the exact line, 9/0 by arm and grid. Residual LOW W1 below. |
| L2 receipt completeness | CLOSED | Complete output walk equals the receipt and the baseline names. runtime.json and stdout.log are hash-bound. Residual: stderr is neither captured nor bound, and the run_dir top level is not inventoried (P9). |
| L3 wrong ROI / cross-case STAR | CLOSED at `field_metrics_bound`/`score_admitted` | ROI, manifest pin, truth name and STAR name/movie stem are checked, and paths are derived from run_dir. `field_metrics_lowlevel` stays open by design and is labelled as such. |
| L4 pins | CLOSED | 15 pins verify. Residual LOW P-anchor below. The comparator is pinned but never invoked; see M2. |
| L5 deviations | CLOSED (documented) | ADMISSION_AMENDMENT_v3 names the staged cwd, the new root and 326f03a→634e4b48. The OFF gate decides empirically. |
| L6 oracle V1 imports | CLOSED (provenance note) | oracle_floor.py is unchanged and still imports V1. ORACLE_PROVENANCE_v3 values equal R1's table. The oracle result is unchanged and was not re-run. |

## New findings

**M2 (MATERIAL, pre-admission coverage): PLAN.md lines 15 and 17 consumer gates have no implementing code.** `score_admitted` scores one run. No code in v1, v2 or v3 computes the following:
- (a) OFF whole-product compatibility with the retained tree. `compare_products.py` is pinned but never called, and `on_launch_permitted` (score_fields_v3.py:299-301) accepts caller-typed `'PASS'` strings.
- (b) exact equality of the OFF/ON full-precision global trajectory and the serialised global block.
- (c) identity of the five global-only OFF/ON publication trees.
- (d) the DC/coupled manipulation witnesses and pairwise global counters. `factorial_common.manipulation` exists and is pinned but is unused.
- (e) the same binary across a pair. In probe P8, OFF with binary `ab…` and ON with `cd…` both admit.
- (f) the P1/P2 verdict itself.

Scenario: a future driver uses v3 as the single consumer, as the brief intends. OFF compatibility then becomes a typed string, and P2 can compare ON and OFF slots from different binaries or with different global trajectories. Both are the "vacuous PASS" that PLAN line 17 forbids. This is the same class of problem as M1, at the pair level. R1 did not raise it. It is not a defect in what v3 implements, and nothing executes while HELD. Fix before producer admission: a frozen, tested `admit_pair` / `decide_pilot` that calls the pinned comparator and `manipulation`, checks binary equality and global equality, and computes P1/P2.

**LOW**
- **W1 witness marker match** (score_fields_v3.py:248). Lines count only if they contain the exact case-sensitive marker. A hyphen-less or lower-case variant on OFF is neither counted nor rejected (P4, P5). The binary is hash-pinned, so the practical risk is small. A case-insensitive `local full.?width` pre-scan that rejects any non-exact match would close it.
- **P-anchor** (score_fields_v3.py:99-127, 160). `commands` and `admission` are caller-supplied dicts with no in-code hash anchor; only `MANIFEST_SHA256` and `V2_SHA256` are anchored. In probe P7, COMMANDS edited to `--max_iter 9` and `OMP_NUM_THREADS=8`, with a matching receipt, admits. The trust root is currently `SHA256SUMS_v3`. At final admission, `resolve_expected_row` should check the admission and commands file hashes or regenerate the commands.
- **Expected-dict trust** (score_fields_v3.py:252). This line checks only that `expected` is internally coherent. In P6, a hand-built expected with `patch_grid=[1,1]` admits a 3×3 ON run that has 0 witnesses; the resolved expected rejects it (P6b). A driver must only use `resolve_expected_row` output.
- **T1** (test_score_fields_v3.py:204). The "extra file in staged cwd" test passes only because `{}` mismatches the real MANIFEST pin. With the names guard (:201) removed, an extra file is still rejected by that byte mismatch, and `missing staged movie` admits. Nothing isolates the names guard against an extra file whose bytes match its fixture pin.
- **T2** (score_fields_v3.py:237). `json.loads('1e400')` yields `inf` without calling `parse_constant`, so the NumPy finiteness guard is the only defence against overflow literals. There is no test for that path, and the mutant survives. The guard itself is correct.
- **T3** (score_fields_v3.py:138-139, 218-220). The output-symlink and publication-escape guards are shadowed by inventory equality, partly because the test helper skips symlinks (test:79). Defence in depth holds: P10 shows that a symlink listed with the target hash is still rejected. The tests just do not isolate these guards.

## Remaining honest limits
- There is no producer driver. Receipt argv, env, cwd, exit and binary_sha256 are claims. Only the output bytes, staged inputs, runtime.json/stdout hashes and the log witness are checked against disk.
- The 9-line witness count and the LOG_CASE first line are source-derived predictions that no run has confirmed. LOG_CASE also assumes the fixture STAR names the movie as the bare `<case>.mrcs`. The fixture STAR bytes are not available locally. Both checks fail closed if wrong.
- Tests replace the real `fixture_files` pins with fakes, so the 33 real input pins are never exercised. Only noisy scoring uses real retained bytes.
- Native stays HELD. Still missing: trusted SSH, the Linux binary and source archive, compiler/config, venue/lease, the 33 fixture bytes and the 8×19 baseline bytes at the venue.

## Artifacts
`scripts/extra_mutants.py`, `scripts/gap_probes.py`; `results/` (AUTHOR_TESTS_rerun.json, EXTRA_MUTANTS.json, GAP_PROBES.json, ORIGINALS_VS_R1.txt, pilot_before/after.sha256); `logs/`; `ATTEMPTS.txt`; `SHA256SUMS`.
