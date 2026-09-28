# Superseded runs, retained on purpose

These are validation runs of earlier heads of this branch. They are kept rather than deleted
because two of them record corrections, and a correction that only exists in git history is
not visible to someone reading the tree.

| file | head | why it was superseded |
|---|---|---|
| `cpu_validation_412f2f98be40.log`, `cli_contract_412f2f98be40.txt` | `412f2f98` | first full run; its CLI file carries an **appended correction** — it claimed CUDA default behaviour was unchanged, which was an inference from the diff, not a recorded check, since no CUDA build existed |
| `cpu_validation_189ed1fc8e72.log`, `prefetch_*_stdout_189ed1fc8e72.txt`, `cli_contract_189ed1fc8e72.txt` | `189ed1fc` | run after the scope audit strengthened the test assertions, before the code review's fixes |
| `tsan_run_c699a52db4a6.log` | `c699a52d` | first ThreadSanitizer run, before the destruction-order fix |
| `tsan_attempt1_aslr_flake.log` | `c699a52d` | the attempt whose serial arm died before `main()` with `FATAL: ThreadSanitizer: unexpected memory mapping`, a loader-time TSan/ASLR interaction. Rerun under `setarch -R`. Kept because "we retried it and the second one was fine" is a claim a reader should be able to check |

All results quoted in the parent `README.md` come from the current head's run, not from these.
