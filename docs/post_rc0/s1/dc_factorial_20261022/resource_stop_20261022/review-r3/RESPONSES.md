# Author responses to review R3 (2026-10-23)

Retained review files are byte copies of
`/tmp/motioncorr-dc-worker-v4-review-r3-20261023-opus/inv-68728dae-abb5-4481-a169-5cd09328e32c/`
(REVIEW.md `275d97ae…`), verified against the reviewer's `HASHES.txt` whitelist. The reviewer's
716 KB `target/` export of `0751c2f3` is not duplicated; its eight files are identified by the
hash lines in `HASHES.txt`. The contract amendment
[../CONTRACT-v5.md](../CONTRACT-v5.md) (`34800fe1…`) was committed (`a2255956`) before any code
change. v2, v3, v4, their controls, all earlier attempts and the refused r2 attempt (UNRUN) are
unchanged. No Linux, SSH, native, GPU or real `nvidia-smi` action.

## Correction to the R2 response (dated, does not rewrite it)

`review-r2/RESPONSES.md` said the `unbounded_child_wait` mutant survives because the bounded child
wait matters only for a root that survives SIGKILL. That was wrong. As R3-m1 showed, the wait also
matters whenever `terminate_owned` returns without signalling the root while `own.errors` is empty,
which happens on a main-thread-only ownership refresh failure. v4 attempts 09 and 26 survived only
because no control reached that path. The R2 file stays as written; this note supersedes that
explanation.

## Findings

| Finding | Response | Control | Evidence |
|---|---|---|---|
| R3-M1 runner owner rule selects the runner itself | New runner `tools/run_v5_controls.py`. The owner is given explicitly as PID + birth, must be in the runner's ancestor chain and carry an exact `--resume=<id>` / `--resume <id>` token; substrings are not used. Other authors are processes outside the owner's tree with that exact token, so the owner's watchdog child is inside the tree. Control processes are matched by anchored names outside the runner's chain. Admission is a pure function. | `tools/test_run_v5_admission.py`: 11 synthetic-table cases (refused r2 tree admitted, orphan duplicate refused, space-form token refused, bad birth refused, non-ancestor refused, wrong id refused, unrelated id mentions admitted, unrelated launcher/smi admitted, foreign harness/runner/namespace mock refused) | static run: 11/11 PASS; a data-only mutant with the r2 owner rule fails all 11 (including the watchdog tree), and a substring-token mutant fails 2 |
| R3-m1 `unbounded_child_wait` testable | K25a/K25b ported from R3-K25 into the v5 harness (main-thread-only refresh failure after job start, job timeout). K25b additionally disables root signalling in the test process (models a root that cannot be reaped), which makes the bounded wait the only thing between the fault and an indefinite silent hold. | K25a, K25b; targeted mutant `unbounded_child_wait` with `--only K25b` | suite result below |
| R3-m2 root not signalled on refresh exceptions | `signal_root` (TERM then KILL through the unreaped Popen handle, bounded) on the observer-error branch and on both refresh-exception branches; descendants stay unsignalled, the record is CLEANUP_FAILED and the lease is held. | K25a (root gone, root signal recorded, receipt bounded, lease held); targeted mutant `no_root_signal_on_refresh_exception` with `--only K25a` | suite result below |
| minor: lease policy for unreaped queries | One rule (CONTRACT-v5 §lease): any unreaped worker-owned query holds the lease after a typed receipt at worker end; the zero-job release still requires no unreaped query. | K29 (injected unreaped query); mutant `release_with_unreaped_query` | suite result below |
| minor: untyped query Popen OSError | `QueryError('QUERY_SPAWN_FAILED')`. | K27 (fake SMI made unexecutable mid-job); mutant `untyped_query_spawn` | suite result below |
| minor: RUN/FINAL lost on post-job failures | Post-job query, witness parsing and output hashing each record their own error and the RUN.json is always written; `census` never raises (`UNREADABLE_RUN_JSON`); the final query catches every exception and FINAL is written before release. | K27; K28 (unit); mutant `census_raises` | K28 static run PASS; suite below |
| minor: provenance labels | `schema='dc262-run/v5'`, `worker='gpu_worker_v5'`, docstrings say v5. | K5 checks both | suite below |
| K5 prefix on Linux | K5 selects `-l` (macOS) or `-v` (Linux); K5P runs the production `taskset -c {cpu} /usr/bin/time -v -o …` prefix on Linux only and is UNRUN on macOS; K30 checks the selection and the worker's default prefix statically. | K5, K5P (UNRUN on macOS), K30 | K30 static run PASS |
| minor: binary/input identity, blocking admission flock, empty-witness RESOURCE | Out of scope, documented in CONTRACT-v5: binary hashed once at bind; `campaign.admit` blocking flock inherited (campaign.py not changed); a job that exits before a CUDA context halts the resume by design. | — | — |
| minor: runner false positives / author copies with another session id | Anchored control names remove the unrelated `launcher.py`/`smi.py` false positive. A copy with a different session id is still detected only through `inputs_changed_during_attempt` (the frozen copies protect the run itself). | admission units | — |

Namespace-aware evaluation stays **unimplemented**; evaluation of any v5 namespace is blocked. GPU
readiness stays blocked. Linux subreaper execution, `taskset`, real `nvidia-smi` and uninterruptible
sleep are UNRUN.
