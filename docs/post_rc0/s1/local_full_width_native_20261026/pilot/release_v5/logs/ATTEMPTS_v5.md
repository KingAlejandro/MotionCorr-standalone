run3 (logs/test-run3.log): 117/120. The new f11 test (binary changed between launches) showed the driver staged and counted the ON launch before its identity re-check; code fix: re-verify identity right after the guard, before staging/ledger. Test retry expectation for f11 is IDENTITY (context creation fails first).
# v5 attempts (append-only; plan frozen first: V5_PLAN.md sha256 1ce58083..., commit 6edf74d3)
- cpu64 build: attempt 1 build ok, ctest rc 127 (ctest not on PATH; logs kept); attempt 2: 4 pass, 4 aborted fail-closed because MC_EXPERIMENT_CCF_DC_ARM was unset in the DC
  build; attempt 3: those 4 rerun with arm none, 4/4 pass. (The plan listed "arm unset" for all; the four alignPatch tests need arm none, as the DC hook documents.)
- test runs: run1 identity group 32/0; run2 full 109/0; run3 117/120 (f11: driver counted the launch before the binary identity re-check; code fixed); run4 120/0; run5 120/0.
- mutation run1 (logs/mutation-run1.log): 29 killed, 2 shadowed declared, 5 reported SURVIVED. Findings: (a) a test-state leak in g_identity (a shared dict mutated by the
  symlink test left the link path in the admission for all later tests, so the archive/commit/receipt tests were rejected by the symlink guard instead of their own); fixed
  with deep copies and an isolated symlink test (pin and receipt agree on the link path); (b) three harness fragments pointed at tests the mutant cannot affect (partially
  disabled expression keeps the approved_by check; receipts are written with g={}; the L1 failure surfaces as an infrastructure exception in g_l1); fragments corrected.
