run1: NameError (my copy transformation swallowed 'from pathlib import Path' in driver_v5_2.py); fixed before any test ran.
run2 (logs/test-v52-run2.log): 57/59: the 'numeric' root-audit test replaced a substring absent from the scratch path (no change made, so it was accepted), and the refusal helper assumed every ledger line has an event key. Both were test defects; fixed.
run3 (logs/test-v52-run3.log): 59/59.
mutation run1 (logs/mutation-v52-run1.log): the refusals-group mutants all showed "test process died" because the harness scratch copy lacked driver_v5_1.py (read by one refusal test) - a harness defect, not a mutant effect; two happy-path mutants
  were killed through an infrastructure exception in the group (the test names differ from the fragments I listed). Harness fixed (copy the file; fragment names corrected, stderr/stdout tails kept); full rerun is run2.
