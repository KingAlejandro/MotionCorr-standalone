# gpu_worker_v5 controls

Contract: [../CONTRACT-v5.md](../CONTRACT-v5.md) (frozen before code, `a2255956`). Responses:
[../review-r3/RESPONSES.md](../review-r3/RESPONSES.md).

## Static and synthetic-data controls (no worker or mock process started)

`static-20261023T001802Z/` (sources in `source-hashes.txt`: worker `1e3d6f0a…`, harness `a2b320be…`,
runner `4f70d4fa…`, admission test `7ba17622…`):

| Control | Result |
|---|---|
| Runner admission, 11 synthetic process-table cases (`test_run_v5_admission.py`) | 11/11 PASS |
| Same cases, data-only mutant with the r2 owner rule (nearest ancestor by substring) | 11/11 FAIL (refused at the owner check, including the watchdog tree: the R3-M1 failure) |
| Same cases, data-only mutant with substring instead of exact `--resume` token | 2 FAIL (wrong-id owner admitted; unrelated id mention refused) |
| K28 census with a malformed RUN.json (unit) | PASS |
| K30 time prefix selection (`-l` macOS, `-v` Linux) and worker default production prefix (static) | PASS |

## Real-worker mock suite

At most one invocation of `run_v5_controls.py` is authorized (full harness on the real v5 worker,
then the five targeted mutants with `--only`). **Not invoked: UNRUN.** Author load
preflight at 2026-10-23T00:19Z read 15.15/15.28, and then 72.50/28.41 (1-/5-minute) on 14 logical CPUs.
That load came from other processes (Jamf, headless Chromium, Notion and others); no v4/v5 control
process was live. The authorization stays unspent. No retry or wait loop was used. Linux execution, K5P (`taskset` + GNU time)
and real `nvidia-smi` are UNRUN on macOS.
