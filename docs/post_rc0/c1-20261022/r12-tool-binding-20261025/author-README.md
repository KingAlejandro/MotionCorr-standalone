# R12 c1_item12.py HERE-binding fix (tooling only, unapplied)

Patch: `r12-binding-fix.patch` (sha256 985ac80434b52c4fa334aa44b20881c2ef678f7edaa09f32fe149dd2935c98fd), against #282 `a406983b`.
Applies with `git apply` from the repo root; verified clean on a `git archive a406983b` export (tools-v2 + docs/rc0/qf/tools).
Touches only docs/post_rc0/c1-20261022/tools-v2/{make_c1_item12.py,c1_item12.py,c1_item12.diff} and adds test_c1_item12_binding.py.
`orig/` = pristine copies; `fixed/` = patched; `base-with-test/` = base plus the new test (3 of 5 cases fail). No project branch or worktree was written.
Control: `cd fixed/docs/post_rc0/c1-20261022/tools-v2 && python3 -B -I test_c1_item12_binding.py` (5 tests, 5 OK).
