# Author-session collision, 2026-10-22 23:46–23:49Z

Two orphan copies of this author session (Claude PIDs 75362, born 21:42:33Z, and 82476, born
23:35:05Z, both PPID 1, same resume id) ran alongside the owning process 23920. The parent verified
UID/birth/argv and stopped only the orphans and their captured descendants at 23:48:09Z
(`stop-receipt.json`, `pre-signal-tree.json`, `process-snapshot.json`, `stop-owned-orphans.py`), and
confirmed 23920 as the sole owner at 23:51:34Z (`sole-owner-readback.json`, `06b9cdf2…`). These files
are byte copies of the parent's receipts. The author sent no signals.

## Inventory and recovery

- [INVENTORY.json](INVENTORY.json) (`e5ae4b20…`) froze file hashes and all 37 v4 attempts before any
  recovery action.
- [RECOVERY-ACTIONS.json](RECOVERY-ACTIONS.json), 23:52:16Z, authorized by the parent:
  1. byte copy of the orphan-edited harness `tools/test_gpu_worker_v4.py` (`29c8ec27…`; mock jobs
     0.6 → 1.5 s, K19b job timeout 2.5 → 3.5 s) to `orphan-edited-test_gpu_worker_v4.py`;
  2. restore of the author's harness byte-exact from `gpu_worker_v4_controls/attempt-18-worker/test.py`
     (`c2b6e80a…`);
  3. atomic rename of the leftover `tools/_v4mutant_v3_query_lifecycle.py` (`8f04fb78…`, the committed
     mutant applied to v4) to `leftover-_v4mutant_v3_query_lifecycle.py`.

## Attempt trust (`gpu_worker_v4_controls/`, unchanged)

| Attempts | Launched by | Harness | Status |
|---|---|---|---|
| 01–17 | author | `1ffacb1d…` | retained, run one at a time; attempt 11 K4c was a query-timeout timing flake, fixed in `c2b6e80a` |
| 18–27 | author (the 23–27 command's result was lost in a session interruption) | `c2b6e80a…` | retained, no overlap |
| 28–33 | shell 18534 under orphan 75362 | `c2b6e80a…` | retained, no overlap, orphan-launched; not primary evidence |
| 34–37 | 34 orphan 82476, 35 author, 36–37 orphan 75362 | mixed (36 used `29c8ec27`) | **untrusted**: overlapping; 34 and 37 have no record, 36 exit −2 after the parent's SIGTERM |

None of these is evidence in the new namespace `gpu_worker_v4_controls-r2/`.

`gpu_worker_v4_controls/SUMMARY.json` was written after attempt 17 and covers attempts 01–17 only; `INVENTORY.json` covers all 37.
