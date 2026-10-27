# Amendments to the frozen design (design commit 4ad43a3f); no criterion was relaxed

1. Mutation check on the first source commit (dd2a92bb): removing the session's duplicate-patch guard was not detected, because the patch-directory-exists check also throws on a repeated patch. The test now requires the session guard's own message. Fixed in `f473fbc9`; the corrected mutant now fails the test (`evidence/r2/mutants_unit.txt`). Run 1's results are kept in `evidence/attempts/r1/`.
2. The CLI test also covers extra refusals beyond the frozen list with the flag on (`--experimental_isotropic_weight`, `--experimental_global_half_gain`, `--bfactor`, `--patch_x`). These add coverage only.
3. First configure attempt failed (CMake picked a Python without NumPy); the rerun passed `-DPython3_EXECUTABLE` (`evidence/attempts/r1/attempt1-wrong-python/`).
