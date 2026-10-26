# Actual commands (run in /tmp/mc-w8-common-mean-screen-20261026; PY = `uv run --offline --no-project --with numpy python -I -B`, caps 2)

1. Extraction (git objects, read-only): `git archive 0b3478b5 <W8 PLAN README scripts results/{refit,score,admission}.json>`; `git archive 4fa272f6 tools test-data` (py files only; MRC/TIFF excluded); `git archive 4fa272f6 <300 F/{runtime.json,metrics.json,output/movie.star} paths>`. rc 0. No SSH, no remote access: the metadata was already in the git objects and the local worktree.
2. Admission (before): `PY w8_admit.py inputs/runs admission/admission_before.json` rc 0, manifest 60a67d64... Compared with W8 admission.json (equal) and with the worktree copy at 4fa272f6 (0 mismatches).
3. PLAN.md frozen at 2026-10-26T18:13:33Z (sha256 427d215c...), before steps 4-5.
4. Stage 1: `PY scripts/s1_common_mean.py <W8 scripts> inputs/runs <W8 refit.json> results/stage1_d.json` rc 0.
5. Stage 2: `PY scripts/s2_score.py src_4fa272f6 inputs/runs <W8 refit.json> <W8 score.json> results/stage1_d.json results` rc 0 (baseline gate passed; identity passed).
6. Admission (after): `PY w8_admit.py inputs/runs admission/admission_after.json` rc 0; `PY scripts/s3_tables.py <dir>` (post-processing only).

# Failed / superseded attempts (nothing hidden)
- Step 2 first try: a shell variable holding the python command was not word-split by zsh ("command not found"). No input was read and no analysis ran. Re-run with an array, as above.
- Before the first stage 2 run, the pedestal32 CSV-row expression in s2_score.py was malformed (a leftover from drafting); it was corrected before any execution. The edit changed only CSV formatting for the 10 unchanged rows, not scoring logic.
- Stage 1 and stage 2 each ran once with no failure. No tolerance, gate, set or rule was changed after the PLAN freeze.
