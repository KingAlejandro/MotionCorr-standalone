# v3 attempts (append-only)
1. tests run1: 107/107 PASS (logs_v3/test-run1.log). mutation_controls run1: 9 of 11 guard removals killed; two SURVIVED
   (logs_v3/mutation-run1.log, MUTATION_CONTROLS_run1.json): `runtime_hash` (the tamper test wrote `{}`, which still failed
   with the same RUNTIME code from the later parse) and `run_dir` (a copied tree whose receipt still named the old path was
   caught by the second run_dir check). Both were weak tests, not code defects. Criteria in SCORER_V3_PLAN.md unchanged;
   tests strengthened (valid-JSON runtime tamper; copied tree with a self-consistent receipt, which must hit RUN_DIR before CWD).
