# Attempts (all kept)

1. `test_resid_lib.py` attempt 1 failed (rc 1, `FAIL: nonzero g0 accepted`): a test defect, not a library defect. The "bad" array used a zero offset (`[0,1e-9] * [1,0]`), so it never violated the g=0 rule. Attempt-1 script and stdout are in `out/test_resid_lib.attempt1.py` and `out/hand_tests.attempt1.stdout`. Only the test array changed (`bad0[0,0,1] = 1e-9`); `resid_lib.py` was not edited. Attempt 2 passed ("hand-array checks: all passed"). Both ran on hand arrays only, before the freeze.
2. Before the freeze I read file structure only: `stage1_fit.json` keys, patch-centre lists and runtime G values, the sealed screen outputs, the iteration lines of the noisy logs (to write the log parser), and the truth array shape was first loaded by `observe.py` itself. No residual, H, e_Tr, s, eta or fitted-error value existed before `FREEZE.txt` (2026-10-27T00:29:33Z).
3. A system `python3` without NumPy was used once for a shape probe and failed; every packet script ran with `~/.local/bin/python3` (3.13.7, NumPy 2.4.2), as pinned.
4. `observe.py` ran once (rc 0, 0.06 s). `make_tables.py` ran once (rc 0). `supplementary.py` was added after the freeze and is labelled post-freeze; it only does arithmetic on `observation_residual.json`.
No frozen file was edited after `FREEZE.txt`; no criterion was relaxed.
