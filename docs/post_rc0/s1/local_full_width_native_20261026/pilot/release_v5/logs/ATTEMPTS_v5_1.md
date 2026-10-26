# v5.1 driver patch attempts (append-only; criteria frozen first: AMENDMENT_M1_RESOURCE_RECEIPTS.md, commit c196d7a9)
- mac run1 (logs/test-v51-run1.log): 38/0, 4 Linux-only checks SKIPPED (not passed).
- mutation run1 (logs/mutation-v51-run1.log): 13 killed by named tests, 1 killed by killing the test process (SIGTERM handler removed), 2 reported SURVIVED (lease_ancestor, lease_inode): both were
  killed by an infrastructure exception in g_parse (a test recorded an int as the detail string), so the named controls did not get to report; test fixed to str(why); mutants re-run in run2.
- mutation run2: lease_inode still reported SURVIVED because the harness also demanded the 'unheld' control, which that mutant cannot affect (no entries at all); the orphaned-inode control did fail (1 failure). Harness fragment corrected; final mutation run is run3.
