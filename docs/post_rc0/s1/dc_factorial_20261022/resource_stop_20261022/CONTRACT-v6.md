# GPU worker v6 contract amendment (frozen before code changes)

Frozen 2026-10-23 in response to review R4 (`review-r4/REVIEW.md`, `cf7fcbad…`). CONTRACT-v5 still
applies except where this amendment changes it. v2–v5, their controls, the v5 static evidence and all
reports stay unchanged. `campaign.py` and `process_ownership.py` stay frozen. Binary re-hashing and the
campaign admission lock stay out of scope. The namespace consumer stays unimplemented and blocked, and
GPU readiness stays blocked.

## Versioning

`tools/gpu_worker_v6.py`; RUN.json `schema='dc262-run/v6'`, `worker='gpu_worker_v6'`.

## R4-1: the hold is established before any I/O and never escapes

- `hold_lease` first sets SIGTERM, SIGINT and SIGHUP to ignored and marks the worker as holding. Only
  then does it attempt the receipt. A receipt that cannot be written falls back to one JSON line on
  stderr, which is best effort; if stderr fails too, that is ignored. The pause loop is always reached.
- Normal receipts (STOP, FINAL) and RUN.json are written atomically (temporary file, fsync, rename) on a
  best-effort basis. A write error never raises: it is recorded in memory and on stderr. The worker
  promises no file receipt when storage is unwritable.
- A RUN.json write failure for a job whose cleanup was verified is a typed safe stop,
  `RECORD_WRITE_FAILED` (exit 79), and the lease is released. If cleanup was not verified, the lease is
  held whatever happened to the writes.
- After the lease is taken, `main` has a backstop. Any unexpected exception holds the lease unless the
  worker has launched no job, recorded no owned identity and left no query unreaped. Only that case
  counts as a safe release, and it gets a typed STOP.

## R4-3: owned original-session group fallback (root unreaped only)

On every path where descendant ownership cannot be verified (observer errors, initial refresh
exception, in-loop refresh exception), v6 signals the job root's original process group in place of
the bare root. It sends TERM, then KILL after a bounded wait, and does this only while all of these
hold, re-checked before each signal:

1. `root.returncode is None`: Popen has not reaped the root. No code in the worker reaps it any other
   way (no `os.wait`; `restore()` runs only after job cleanup).
2. The process table shows PID `root.pid` with the birth recorded at launch and parent = this worker,
   live or zombie.
3. Its PGID equals `root.pid`. The root was created with `start_new_session=True`, so its original
   group and session IDs are its PID.
4. `root.pid != os.getpgrp()`.

Why the group ID cannot be stale or foreign. While the root is unreaped, its PID is not free, so no
other process can be created with that PID, and no group with that ID can be created except by the
root itself. A process can join group `root.pid` only from inside the root's session, which only the
root's own descendants can be in. The worker's `nvidia-smi` queries and its observer run in the
worker's own group and session, so they can never be members. The root is never reaped before the
group signals: the group is signalled first, and the root is reaped afterwards.

If any condition fails, the worker falls back to root-only signalling, or to nothing if the root is
already reaped, and records the reason. Descendants that left the group (`setsid` or `setpgid`) are
not signalled; they keep cleanup unverified and the lease held, with the reason in the record and the
receipt. Under the production prefix `taskset … /usr/bin/time -v … binary`, `taskset` execs into
`/usr/bin/time`. That process is the root, and the binary is its child in the same group, so the group
signal reaches it. GNU time on Linux is UNRUN; the mock uses macOS `/usr/bin/time` as the same root
plus same-group child topology.

## R4-4 and other ordering

- Cleanup uncertainty takes priority over outputs and witness `JOB_STAGE` errors.
- Observer activation failure (zero jobs, nothing launched) writes FINAL on a best-effort basis before
  release.
- SIGHUP is treated as cancellation while running, and ignored while holding.
- Limits: SIGKILL of the worker, a crash of the interpreter, or loss of power releases the flock at
  process exit and orphans any running job. That cannot be prevented from inside the worker. Launch
  discipline for the later Linux run: start the worker detached in its own session with SIGHUP
  ignored, record its PID and birth, and never SIGKILL it except after reading a lease-held receipt.

## Controls (harness `test_gpu_worker_v6.py`, runner `run_v6_controls.py`)

Separate single-branch controls, each with its own single-site mutant:

| Control | What it checks | Mutant |
|---|---|---|
| K25a | Initial-refresh branch: job root and its group gone, root/group signal recorded, lease held | `initial_branch_root_signal_removed` |
| K25c | In-loop refresh branch: the first two main-thread refreshes succeed, the third fails; root gone, lease held | `loop_branch_root_signal_removed` |
| K14R | `own.errors` branch: root gone, lease held | `errors_branch_root_signal_removed` |
| K25W | Real macOS `/usr/bin/time` as the job root, with a refresh failure: the same-group child (the "binary") is gone; a setsid escapee keeps the lease held | `root_only_no_group` |
| K31a | Runs dir made unwritable mid-job, with cleanup uncertain: worker alive, lease held (independent flock witness), stderr fallback line present | `unguarded_hold_receipt` |
| K31b | Injected ENOSPC on every record write, with cleanup uncertain: as K31a | `unguarded_hold_receipt` |
| K31c | Injected EIO on record writes, with clean cleanup: exit 79, lease released, typed stderr line | `record_write_unchecked` |
| K32 | Cleanup uncertain plus an outputs-hash error: lease held, not a JOB_STAGE release | `jobstage_before_cleanup` |
| K33 | Outputs-hash error alone: RUN.json keeps `outputs_error`, typed JOB_STAGE stop, lease released | — |
| K34 | Observer activation fails: FINAL written, exit 75, lease released | `no_activation_final` |
| K35a | SIGHUP mid-job: CANCELLED, tree reaped, lease released | `no_sighup_handler` |
| K35b | SIGHUP to a held worker: still alive, lease held | — |

v5's targeted mutants are ported unchanged. On Linux, K5P and K25W must also assert
`ownership_mode == 'linux-child-subreaper'`; that is UNRUN here.

Runner: owner binding, admission, lease, load and namespace rules as in v5. The real worker runs as
three harness invocations (base controls; R3 set; R4 set), each bounded at 180 s, followed by the
targeted mutants. The verdict is read from each `controls-*.json` file, never from the runner's exit
status.
