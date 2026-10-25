# gpu_worker_v4 controls, r2 namespace

One fresh real-worker attempt was authorized after the 23:48Z owner collision. It was **refused** by
the runner and is **UNRUN**:

- `attempt-20261022T235306Z-5a851a56-a4d6-41fd-9594-76eebc6ab50c/ATTEMPT.json`: status
  `REFUSED_UNRUN`, load 8.66/9.77 on 14 CPUs, inputs worker `071a1588…`, harness `c2b6e80a…`.
  The admission scan counted PID 23952 (child of the owning Claude 23920, the launcher's
  parent-death watchdog shell, whose argv carries the session id) as another author. No harness was
  started; nothing was signalled.
- Runner used: `runner-used-by-refused-attempt-1dd8c2e3.py` (`1dd8c2e3…`). The corrected runner is
  `tools/run_v4_controls_r2.py` (`071e36f8…`): session-id matches inside the owning Claude's own
  process tree are not another author; any v4 runner/harness/mock process outside the runner's own
  ancestor chain is still refused. The correction has not been executed.

No retry was made. A further attempt needs a new authorization. `.lease` is the runner's lease file
and is not committed.
