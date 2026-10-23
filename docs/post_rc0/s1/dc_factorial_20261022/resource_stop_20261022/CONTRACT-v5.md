# GPU worker v5 contract amendment (frozen before code changes)

Frozen 2026-10-23 in response to review R3 (`review-r3/REVIEW.md`, `275d97ae…`). v2, v3 and v4 and all
their controls and attempts stay frozen. v5 changes only the paths named here. GPU readiness stays
blocked; the namespace-aware consumer stays unimplemented.

## Versioning

`tools/gpu_worker_v5.py`, RUN.json `schema='dc262-run/v5'`, `worker='gpu_worker_v5'`, receipts carry the
worker hash in `binding`. A v5 namespace is not readable by `evaluate.py`/`matrix.py` (blocked).

## Lease and query policy (single rule)

1. The worker never reports a clean release while any process it started could still be running.
   That covers job roots, owned descendants and its own `nvidia-smi` query processes.
2. Any cleanup it cannot verify holds the lease, after a typed `CLEANUP_FAILED_LEASE_HELD` receipt naming
   what is unverified: owned processes, ownership errors or unreaped query PIDs.
3. The only release after an observer or restore failure is the existing zero-job case: no launch, no
   owned identity ever recorded, and no unreaped query (`OBSERVER_FAILED_ZERO_JOBS`, exit 75).
4. A worker-owned query that times out is SIGKILLed through its Popen handle. If it still cannot be
   reaped (`QUERY_HUNG`), it stays in the unreaped set, and rule 2 holds the lease at worker end.

## Root signalling under ownership uncertainty (R3-m2)

On every path where descendant ownership cannot be verified, the worker SIGTERMs and then SIGKILLs only
the unreaped Popen job root, through its handle, with bounded waits. That covers observer errors and both
ownership-refresh exception branches. Uncertain descendants are not signalled, the job record is
CLEANUP_FAILED, and the lease is held.

## Report integrity

- A `Popen` `OSError` for a query (missing binary, fork failure, descriptor exhaustion) is a typed
  `QueryError('QUERY_SPAWN_FAILED')`.
- A job that ran always gets a RUN.json, even if the post-job query, output hashing or witness parsing
  fails. Each failure is recorded in the record.
- `census` never raises; an unreadable RUN.json is status `UNREADABLE_RUN_JSON` (not complete).
- FINAL is written whenever the lease is about to be released. A failing final query is recorded as
  `final_error`.

## Controls (new harness `test_gpu_worker_v5.py`, runner `run_v5_controls.py`)

- K5 uses the platform's time flag (`-l` on macOS, `-v` on Linux). K5P runs the production prefix
  `taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log` on Linux only and is reported UNRUN elsewhere.
  A static unit test checks the selection and the worker's default prefix.
- K25a: refresh fails in the worker's main thread only after the job starts, and the job times out.
  Expected: CLEANUP_FAILED RUN.json, a lease-held receipt within a bound, lease held, job root signalled
  and gone.
- K25b: as K25a, with root signalling disabled in the test process (models a root that cannot be
  reaped). Expected: receipt within a bound. This makes the bounded child wait observable.
- K27: the fake SMI becomes unexecutable mid-job. Expected: typed query errors, the job's RUN.json kept,
  FINAL written.
- K28 (unit): `census` with a malformed RUN.json.
- K29: an unreaped worker-owned query (injected). Expected: lease held with a typed receipt.
- Runner admission (unit, synthetic process tables): original watchdog tree, orphan duplicate, bad owner
  birth, owner not an ancestor, unrelated command mentioning the id, live foreign control process.

## Runner owner binding (R3-M1)

The owner is supplied explicitly as `--owner-pid` and `--owner-birth`. It must be in the runner's own
ancestor chain, have that birth, and carry an exact `--resume=<id>` / `--resume <id>` token. Another
author is any process outside the owner's process tree carrying that exact token. Substring matching
is not used. Control processes are recognised by anchored names (`test_gpu_worker_v*`,
`run_v[45]_controls*`, paths under a `gpu_worker_v*_controls*` namespace) outside the runner's own
ancestor chain. Admission is a pure function with unit tests. The runner sets `TMPDIR` inside its
immutable namespace.

## Out of scope (documented limitations)

- Per-launch binary re-hashing: the binary is hashed once at bind.
- `campaign.admit`'s blocking admission `flock`, inherited from `campaign.py`, which is not changed.
- A native job that exits before creating a CUDA context has an empty route witness. It is classed
  RESOURCE and halts the resume. This is intended: a launch without a witness is not admitted as a
  data row.
- Linux execution, the subreaper path, `taskset`, real `nvidia-smi` and GPU use are UNRUN.
