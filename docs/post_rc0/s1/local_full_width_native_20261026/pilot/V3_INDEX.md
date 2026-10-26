# v3 consumer package index (HELD; nothing launched)

New files only; PLAN.md, ADMISSION_DRAFT.json, COMMANDS_DRAFT.json, score_fields.py (V1), score_fields_v2.py, oracle_floor.py
and every other original are byte-unchanged (`V3_DELTA_FOR_REVIEW/originals_unchanged.txt`: all 24 listed originals
UNCHANGED). Hashes: `SHA256SUMS_v3`.

| file | purpose |
|---|---|
| SCORER_V3_PLAN.md (+ .sha256) | criteria frozen before any v3 code or test existed |
| score_fields_v3.py | admission/scoring entry (M1, L1-L3); imports v2 by pinned hash |
| tests/test_score_fields_v3.py | 109 checks; logs_v3/test-run{1,2,3}.log |
| tests/mutation_controls_v3.py | 11 guard-removal controls; logs_v3/mutation-run{1,2,3}.log |
| build_admission_v3.py, command_manifest_v3.py | write ADMISSION_DRAFT_v3.json, COMMANDS_DRAFT_v3.json (L4) |
| ADMISSION_AMENDMENT_v3.md | deviations, stop rule, limits |
| ORACLE_PROVENANCE_v3.md | independent reproduction note and pinned original import set (L6) |
| logs_v3/ | every run, including run1 (2 surviving mutants) and run2/run3; ATTEMPTS_v3.md |
| V3_DELTA_FOR_REVIEW/ | read-only diff of the new files and the originals-unchanged proof |

Opus originals are archived additively at
`~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-pilot-oracle-review-r1/` (COPY_INDEX.tsv, 208 files).

Results: run3 (final admission, 15 tool pins): 109 checks, 0 failed; mutation controls 11/11 killed. Run1: 107 pass, 2
surviving mutants, tests strengthened in run2 without changing criteria. Environment: uv CPython 3.13.7, NumPy 2.4.2, 1
thread, scratch <1 MB, no network, no build, no native job. Branch source/tests/CMake untouched at `215c37b0`.
Not claimed: producer behavior (none exists), native acceptance, estimator accuracy, byte neutrality.
