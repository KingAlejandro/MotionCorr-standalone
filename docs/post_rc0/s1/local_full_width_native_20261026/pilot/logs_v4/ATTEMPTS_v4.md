# v4 attempts (append-only)
Plan frozen: PAIR_V4_PLAN.md sha256 09679533... (PAIR_V4_PLAN.sha256) before pair_decision_v4.py or any v4 test existed.
1. run1 (logs_v4/test-run1.log): 92 pass, 3 fail, then an infrastructure crash aborted the rest. All test defects, criteria unchanged:
   (a) the anchor tests called w.gate, which re-synced the test admission and hid the tamper; (b) OFF-side counter edits made after the
   gate were correctly caught earlier by the pre-ON binding (PRE_ON), so the OFF counter negatives now run both ways (edit before the
   gate: pair layer must find it; edit after: record must reject); (c) the T2 literal assumed a repr that the retained text lacks, and
   the helper now records a fault instead of aborting the suite.
2. run2: TypeError (crafted_scores(**{tuple keys}) is invalid Python) aborted the decision-rule block; test defect, fixed to a dict argument.
3. run3: 125 pass, 1 fail: 'case without its ON directory' reached the per-case admission (PRE_ON) before the pair-completeness check. Code fix in pair_decision_v4.py: validate all 8 OFF/ON pairs up front. Criteria unchanged.
4. run4: 126/126 pass. The baseline-symlink test pointed at a file with different bytes, so the byte guard shadowed the symlink guard; test changed so the symlink target holds the pinned bytes (run5).
5. test run5: 126/126. mutation run1 (logs_v4/mutation-run1.log, MUTATION_V4_run1.json): 29 killed, 3 declared shadowed, 3 reported SURVIVED.
   The survivors are shadowed guards, not weak tests: (a) comparator verdict check: the real comparator exits 1 whenever it reports DIFFERENT, so the
   rc check and verdict check shadow each other (each alone survives; both removed together are killed); (b) global DC counter drift guard: manipulation()
   forces zeroed == eligible == coupled global peaks, so the coupled-counter guard always fires too; (c) cases_present: its missing-case half is also
   caught by the pair-completeness guard; the guard is credited only with the unlisted-extra-directory test. Harness classification updated accordingly
   (shadowing declared up front, not claimed as kills); no suite criterion changed.
