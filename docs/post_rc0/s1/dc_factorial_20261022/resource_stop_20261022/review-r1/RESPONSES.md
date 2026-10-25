# Author responses to review R1

`REVIEW.md` and the reviewer's files in this directory are byte copies of
`/tmp/motioncorr-dc-gpu-worker-review-r1-20261022/` (REVIEW.md SHA-256
`5a277e917242333cf5a7c001688cf40c6b1a995606f6bce3d23fede03b7a6090`). The frozen
v2 worker, its controls and receipts are unchanged. All fixes are in the new
`tools/gpu_worker_v3.py`; controls are `tools/test_gpu_worker_v3.py`, run through
`tools/run_v3_controls.py`, with mutants in `tools/v3_mutants.json`. Evidence:
[../gpu_worker_v3_controls/](../gpu_worker_v3_controls/README.md). No native,
remote, GPU or Linux run was made. v3 is not deployed.

| Finding | Response in v3 | Control (final harness, attempt 09) | Mutant rejected (attempts 10–18) |
|---|---|---|---|
| M1 unbounded wait, no record, dead observer unseen | Child and cleanup waits bounded (`--cleanup-grace`); if owned processes cannot be shown gone, RUN.json `CLEANUP_FAILED` and a `CLEANUP_FAILED_LEASE_HELD` receipt are written before the lease is held; observer health is required before every launch. The unreachable exit 5 is removed. | K14 observer error during timeout; K15 observer failure before launch | `unbounded_child_wait` fails K14 |
| M2 exceptions leave orphans and FINAL code 0 | Each stage has its own boundary: invalid binding exit 64 with no output; input admission RUN.json `INPUT_ADMISSION_FAILED` exit 65; query timeout/failure/malformed/hung typed STOP exit 75; collision STOP exit 70; record/launch errors RUN.json `JOB_STAGE_ERROR`; worker-level error STOP exit 70. A final-health failure after clean completion is exit 76 and does not hold the lease. | K4a–c, K9, K17, K18 | — |
| M3 silent count reduction | Non-empty `--runs-dir` is refused (exit 64), and FINAL carries an exact census of every expected id; exit 0 only if all have RUN.json status EXITED. | K8 restart after NOT_LAUNCHED (same namespace refused, fresh namespace runs), K1 nonempty | `v2_resume_semantics` fails K1, K8, K9 |
| M4 queue/binary binding | Required `--queue-sha256`, `--expected-jobs`, `--binaries-sha256`; unique ids; every entry backend cuda / build cuda-exp; the cuda-exp binary hash re-checked; lease path derived from `--gpu-index`; binding recorded in every RUN.json and receipt. The README command names the exact proposal file and hashes. | K1 (queue hash, count, backend, duplicate, binaries hash, binary hash) | `no_queue_hash_binding` fails K1 |
| M5 route witness and schema | `gpu_witness_uuids`, `host`, `bench_lock`, `exit` (null when not launched) and all other campaign RUN.json keys restored, plus `status` and `schema`. Namespace-aware evaluation and matrix are **not implemented**; evaluation of any v3 namespace is blocked until a reviewed reader exists. | K5 (witness = target UUID, all campaign keys present) | — |
| m6 sampler evidence | Sampler counts successes and failures (errors retained), any failure stops the worker after the job, join bounded at 2 × query timeout + 10 s and an unjoined sampler is a stop. | K5 (ok > 0, failed 0), K7 mid-job query failure | `sampler_failures_uncounted` fails K7 |
| m7 cancel during admission | Cancellation checked after each admission query and immediately before `Popen`. | K10, K11 | `no_cancel_before_popen` fails K11 |
| m8 owned PIDs without birth | Owned = live, birth-matched identities (`known_live`) captured before and after each query. | K16 PID-reuse simulation | `owned_by_identity_keys` fails K16 |
| m9 hung query | Queries run in their own session with a bounded wait; on timeout the session is SIGKILLed after a PID/birth/PGID check; an unreaped query is reported `QUERY_HUNG`. A process in uninterruptible sleep cannot be forced; that remains a stated limitation and is not reproducible on the Mac. | K4b query timeout, query processes confirmed gone | — |
| m10 harness cleanup and mutant evidence | Every signal from the harness and runner re-checks PID, birth, PGID, session and kill(pid,0) permission; each control reaps its recorded processes in `finally`, including detached-session grandchildren; the runner's timeout fallback is identity-checked SIGTERM then SIGKILL. Mutants are committed as exact replacements. A sentinel is the worker's parent in the worker's own process group. No name-based signal was used. | K12, K13 (tree of 3 including setsid and new-session children reaped; shared-PG sentinel unsignalled) | `no_group_signal` fails K12, K13 |
| m11 production prefix | K5 runs jobs through `/usr/bin/time -l -o …` (job is a grandchild); witness and no false foreign stop. `taskset` is Linux-only: **UNRUN** on the Mac. | K5 | — |
| m12 contention replicate lacks a null | A frozen null replicate is proposed: [../proposed-null-replicate-gpu-r2.json](../proposed-null-replicate-gpu-r2.json) (`39fd2c0f…`), the 57 CUDA Tier C jobs that ran before the foreign onset with clean GPU2 snapshots. No contention attribution of any replicate difference is allowed unless the null replicate is byte-stable. The comparison tool does not exist yet. UNRUN. | — | — |
| minor: scan UTC | `incomplete-runs.json` is unchanged. Retrospective bound only: the local copy of the scan output was written at 2026-10-22T21:43:31Z (file mtime), after the 21:40Z stop. No scan time was recorded at the time. | — | — |
| minor: ECC `[N/A]` | Fails closed: only `0` admits. | K2a | `ecc_na_accepted` fails K2a |
| minor: lock vs index | The lease path is derived from `--gpu-index`; no separate `--lock`. A UUID reported at another index is refused. | K2c | — |
| minor: polling perturbs timing | Unchanged: v3 records stay `wall_s_unqualified` and must not be used for timing. | — | — |

Control attempts 01–08 used an earlier harness (`36cbb492…`) and are retained.
Two of them exposed harness defects, both fixed before the final set:
attempt 07 K12 read the launcher's PID file before its line was written
(harness error; that control registered and killed only the launcher, and a
post-run process check found nothing left); attempt 08 K8 left the fake
foreign process active during run 2, so the resume mutant was not exercised.
The pre-fix control runs of v2 remain unretained, as already stated.
