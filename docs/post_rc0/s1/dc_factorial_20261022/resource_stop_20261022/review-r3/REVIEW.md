# Independent review R3: #262 gpu_worker_v4, its controls and the r2 runner

Target `0751c2f395277d0b6a18089a41da3089a2bdb7c6` (`experiment/262-four-arm-20261022`), exported with
`git archive` into `target/` (tools subtrees only). Author worktree not modified. Local macOS only; no SSH,
Linux, real `nvidia-smi`, GPU, native or build action. Reviewer invocation `68728dae-abb5-4481-a169-5cd09328e32c`.

In scope (SHA-256): `gpu_worker_v4.py` `071a1588…c853`, `test_gpu_worker_v4.py` `c2b6e80a…940d`,
`run_v4_controls_r2.py` `071e36f8…5fe`, `run_v4_controls.py` `6e83ab5d…7b5`, `v4_mutants.json` `322c0283…9b8`,
`tools/multi_gpu/process_ownership.py` `8de59b8c…08cb` (unchanged), `campaign.py` `8701cf24…eae` (unchanged).
Read: R1 and R2 reports, `review-r2/RESPONSES.md`, `collision_20261022/README.md`, the refused r2 attempt and
its runner `1dd8c2e3…`, all 37 retained v4 attempts (tabulated from their own files).

Note for the parent: the author worktree HEAD moved during this review to `44d3cf57` ("retain independently
reproduced partial DC truth analysis"); it adds only `analysis_B_pass3_20261023/` files and does not touch any
file reviewed here. This review is of `0751c2f3`.

## Verdict

- Worker v4: **no material correctness finding** for the R2-M1 fix, the zero-job policy, own-group exclusion,
  witness requirement, binding, census or lease lifetime, on static trace of the Linux helper paths plus the
  macOS mocks. Moderate/minor findings below.
- **One material finding in the control tooling (R3-M1):** the "corrected" r2 runner still refuses on the
  same watchdog PID, deterministically, so the next authorized fresh local attempt would be refused again.
- One control-power gap (R3-m1): the surviving `unbounded_child_wait` mutant is rejectable; the stated reason
  for its survival is wrong. Demonstrated with a review-only control.
- Readiness: **further bounded author repair** (runner + harness, optionally one worker line) before the one
  Linux FAKE-SMI host mock. Not ready for any GPU use.

## Material finding

**R3-M1. The corrected runner's owner rule selects the runner itself, so the false refusal is not fixed**
(`run_v4_controls_r2.py:77`, `:97-100`).
The owner is "the nearest ancestor whose argv contains the session id". The runner's own argv always contains
`--session-id <id>` (that is how the id arrives, `:77`), and `mine` includes `os.getpid()`. Sorting by depth puts
the runner first, so `owner` = the runner PID and `owner_family` = the runner's own (empty) subtree. The T3
parent-death watchdog (PID 23952 in the refused attempt), a child of the Claude process whose argv carries
`--resume=<id>`, is again counted as another author.
Evidence: data-only replay of the committed `main()` with a synthetic process table copied from the refused
attempt (`scripts/runner_admission_replay.py`; `processes()` replaced, expected hashes deliberately wrong so the
harness can never start; nothing spawned or signalled):

| case | result | owner | others |
|---|---|---|---|
| refused-attempt tree | REFUSED "another author-session…" | runner PID | [23952] |
| positive control: same tree, runner argv without the id | passes admission, refused later at the hash check | 23920 | [] |
| orphan duplicate Claude (PPID 1, same `--resume`) | REFUSED | runner PID | [23952, 75362] |
| unrelated `launcher.py` | REFUSED | runner PID | [23952, 5555] |

Consequence: the README and RESPONSES statement that the false refusal is corrected is incorrect. Under T3 the
watchdog always exists, so every attempt with this runner is refused (UNRUN). This fails safe (no false
admission), but it blocks the stated next evidence step and would waste the next authorization.
Fix direction: bind the owner explicitly (parent-supplied owner PID + birth, verified to be in the runner's
ancestor chain), or match the Claude process by its `--resume=<id>` token and skip the runner and its shells.
Add a unit control with a synthetic process table covering the refused tree and an orphan duplicate, like the replay.

## Moderate

- **R3-m1. `unbounded_child_wait` survives only because no control reaches its path; the RESPONSES reason is
  wrong.** RESPONSES says the bounded wait matters only for a root surviving SIGKILL. It also matters whenever
  `terminate_owned` returns without signalling the root while `own.errors` is empty: an ownership refresh
  exception at `gpu_worker_v4.py:185-188` or `:192/:200-201` (main-thread-only or transient failure, or one that
  wins the race against the observer's next 50 ms tick). The existing K14 fault fails in every thread, so it
  takes the `own.errors` branch, which reaps the root through its handle; that is why the mutant survives.
  Review-only control R3-K25 (`scripts/r3_mainthread_refresh_control.py`, frozen harness machinery, refresh
  fails in the worker's main thread only after the job starts, `job_timeout=2`):
  real v4 `071a1588` **PASS** (CLEANUP_FAILED RUN.json and CLEANUP_FAILED_LEASE_HELD receipt within ~6 s,
  lease held, worker alive); mutant `1e7e1f3b` (committed replacement; same hash as author attempt 26) **FAIL**:
  no RUN.json and no receipt after 40 s. That is R1-M1's failure mode (lease held with no record of why).
  Commit a control of this kind.
- **R3-m2. Those exception paths skip the PID-safe root signal** (`:187-188`, `:200-201`). In R3-K25 the real v4
  recorded `signals: []` and the timed-out root (PID 70291) was still alive when the receipt appeared. On a real
  GPU a TIMEOUT or CANCELLED job keeps running under the held lease until it ends on its own. Fail-closed, but
  inconsistent with the `own.errors` branch (`:176-183`), which signals the unreaped `Popen` root. Fix: do the same
  root TERM/KILL through the handle before those returns.

## Minor

- Lease policy is inconsistent for unreaped queries: the zero-job failure path releases only if every query is
  reaped (`:505`), but normal paths release with a QUERY_HUNG query or an unjoined sampler's query still alive
  (`:473-475`, `:377-378`, `:522`). State the policy or unify it.
- Typed-receipt coverage is overstated (docstring `:47`). `Smi._run` maps only timeout and nonzero exit to
  `QueryError`; a `Popen` `OSError` (missing binary, fork `EAGAIN`/`ENOMEM`, `EMFILE`) is untyped. At `:407` it
  escapes after cleanup and before `self.write`, so a job that ran loses its RUN.json (exit code, witness,
  sampler) and the stop is WORKER_STAGE_ERROR. At `:516`, and for a malformed RUN.json in `census` (`:512`), it
  escapes before FINAL is written (no FINAL receipt; the lease is released when the process exits).
- Provenance labels: v4 RUN.json records `worker='gpu_worker_v3'` and `schema='dc262-run/v3'` (`:294`, `:298`,
  `:311`); docstring `:60` says "v3 namespace". `binding.worker_sha256` is correct, but a consumer keyed on
  `worker` would misattribute rows.
- Binary identity is hashed once at bind (`:258`); each RUN.json's `binary_sha256` is the manifest value, not a
  per-launch measurement over a long queue. Input hashes come from `campaign.admit`'s (path, size, mtime) cache
  and a **blocking** `flock` (`campaign.py:140-155`): an unbounded wait while holding the GPU lease if another
  process holds that admission lock, and SIGTERM cannot interrupt it. Both are inherited from campaign.py.
- A native job that exits nonzero before creating a CUDA context has an empty witness and is classed RESOURCE
  (exit 75, `:429-432`), not a data row. This halts the resume; state it as intended or separate it.
- Runner limits (`run_v4_controls_r2.py`): it detects only same-session-id copies and live control processes.
  An author copy with a different session id that edits files is seen only afterwards through
  `inputs_changed_during_attempt` (the frozen copies protect the run itself). False positives (safe) for any
  process whose argv mentions the id (for example a `tail` of the transcript path) or an unrelated
  `launcher.py`/`smi.py`; the leftover scan uses the same name markers and can misattribute.
  An uncaught `PermissionError` from `os.kill(p.pid, 0)` at `:127` would leave no ATTEMPT.json (negligible).

## Verified (no finding)

- R2-M1 fix, traced through the Linux helper: queries have no `start_new_session` (`:104`), so their PGID is the
  worker's; `refresh()` skips `pgid == parent_group` in the adoption branch (`process_ownership.py:315-318`), and
  propagation needs an owned parent (`:324-341`), which the worker never is. A direct child listed by
  `_child_pids` gets `known[pid] = None` and is not owned. The sampler is stopped and joined before
  classification (`:376-378`), and query identities seen among owned processes fail closed (`:395-399`).
  Discriminating controls: `v3_query_lifecycle` fails K19a+K20 (author 02, 19), `query_new_session` fails K20
  (03, 20).
- R2-m1 policy (`:496-511`) is implemented as stated. K15L discriminates (`no_zero_job_release` fails K15L in
  05 and 22). On Linux nothing in the zero-launch path spawns a child outside the worker's group (`campaign.admit`,
  `bench_status` and `usage_bytes` spawn no processes), so `own.identities` stays empty.
- Own-group exclusion: K22 discriminates for the healthy branch (06, 23); the `own.errors` branch never calls
  `killpg`. Witness: K23 discriminates the empty-witness half (07, 24).
- Retained attempts, recomputed from each attempt's own files: worker/harness hashes as claimed; real worker
  30/30 in 01 (`1ffacb1d`) and 18 (`c2b6e80a`); survivors are 04/21 `sampler_after_classification` (redundant
  layer while queries stay in the worker group; survival is expected and honestly stated) and 09/26
  `unbounded_child_wait` (see R3-m1). 28–33 are orphan-launched and 34–37 untrusted, as the collision README says.
  The RESPONSES figures cite only 01–27.
- Timeouts cannot pass: every process-level control requires an exact exit code or an observed receipt, and
  `single()` fails on leftovers or a sentinel signal.
- Scope: `0751c2f3` modifies only `resource_stop_20261022/README.md` and adds files under
  `docs/post_rc0/s1/dc_factorial_20261022/`; `src/`, `tools/multi_gpu/`, `campaign.py`, v2/v3 and their controls
  are unchanged. No PASS/FAIL/UNRUN label was rewritten. The refused r2 attempt is retained as UNRUN.
- Licence: the four new `.py` files are `GPL-2.0-or-later`, stdlib only, and import in-repo GPL code; compatible
  with the repository's GPL-2.0.

## Readiness and preconditions

Recommendation: **further bounded author repair**, then one Linux FAKE-SMI host mock. The worker logic does not
block a Linux mock, but the evidence tooling does:

1. Fix R3-M1 and add its synthetic-table unit control. The current runner cannot admit an attempt under T3.
2. Commit an R3-K25-type control (main-thread-only refresh failure). Optionally fix R3-m2; if the worker
   changes, the fresh review should cover that delta.
3. K5 uses `/usr/bin/time -l` (`test_gpu_worker_v4.py`, K5 prefix), a BSD flag. GNU time rejects `-l`, so K5 is
   predicted to fail deterministically on Linux (static; UNRUN). Select `-v` on Linux. Add one control with the
   production prefix `taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log`.

Preconditions for the later Linux mock (4GPUs, CPU-only): fresh read-only preflight; nonblocking locks per the
#198 policy; NUMA0 `taskset` inside the allocation; `/home/alex/.mc-venv/bin/python3` (no NumPy needed);
`TMPDIR` set to a fresh bounded scratch under `/mnt/clathrin`; `--smi` pointed at the fake, plus a failing
`nvidia-smi` shim first on `PATH` to witness that no real query runs; the harness lease under its own temp dir,
never `/tmp/motioncorr-gpuN-correctness.lock`; no `prlimit --as`; record `ownership_mode ==
'linux-child-subreaper'` in the job RUN.json as the witness that the subreaper path actually ran; identity-checked
cleanup only; retain every attempt; no in-place retry. Any actual GPU use additionally needs the reviewed
namespace-aware consumer (still unimplemented and blocked) and an exclusive lane. This review authorizes neither.

## Reviewer actions and limits

- Static reads; `git archive` export; hashing; the data-only runner replay (4 cases, no processes spawned).
- R3-K25 local mock, macOS 14 CPUs, load 5.3–6.1, no pre-existing mock processes, `OMP/OPENBLAS/VECLIB=1`,
  `TMPDIR` inside this invocation, each run in its own session under a 240 s identity-checked bound (not needed):
  real v4 run PID 70174, 00:06:45–00:06:51Z, exit 0; mutant run PID 70408, 00:06:52–00:07:32Z, exit 1. All
  harness signals were identity-checked SIGKILLs of that control's own processes; post-scan found no leftovers.
  Iteration 1 of the script failed its own patch assertion before starting any worker; it is retained in
  `mock/iter1-script-assert-UNRUN/`.
- Reviewer incident: see `INCIDENT-stray-dir.md`. An aliased `ls` created a stray untracked directory in the
  reviewer's own worktree `work-272`; it was inspected and removed exactly. The author worktree was never written.
- Not done: Linux, subreaper execution, `taskset`, real `nvidia-smi`, GPU, native, remote hash checks, the full
  author mutant campaign.
