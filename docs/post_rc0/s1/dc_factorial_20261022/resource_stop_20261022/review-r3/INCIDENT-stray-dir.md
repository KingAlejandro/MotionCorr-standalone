# Reviewer incident (R3), 2026-10-23 00:03:36Z

`ls` on this Mac is aliased to a long-format lister, so `INV=$(ls -d $R/inv-*)` captured a multi-line
string. zsh does not word-split, so `mkdir -p $INV/scripts` created ONE untracked nested directory named
`Permissions Size User ... 23 Oct 00:59  /tmp/.../scripts` in the shell cwd, the reviewer's own T3 worktree
`work-272-evaluator-contract-20261022` (not the author worktree t3-6c79c479). It held only the replay
script and three error outputs (python could not open the script; no replay ran). Verified birth times
00:03:36-37Z, untracked, reviewer-created only; removed at ~00:04Z with shutil.rmtree on that exact single
entry. work-272 git status afterwards: clean; HEAD 1f0a58bf unchanged. Replays re-run below with literal paths.
