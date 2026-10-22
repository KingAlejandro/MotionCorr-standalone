# Independent review R2: #262 gpu_worker_v3 and R1 responses

Target `b36067fbf163073c01a134416c241b1187353112` (author worktree `t3-6c79c479`, parent `e84ea024`).
I exported it with `git archive` into `target/`. I did not modify the author checkout. No SSH, remote,
GPU, native, build or push.

Files in scope (SHA-256): `tools/gpu_worker_v3.py` `a0510eaa…c106c9`, `tools/test_gpu_worker_v3.py`
`73735e79…e13e2c3a`, `tools/run_v3_controls.py` `bcd816b9…`, `tools/v3_mutants.json` `003e542f…`,
`tools/multi_gpu/process_ownership.py` `8de59b8c…08cb` (unchanged), `review-r1/{REVIEW,RESPONSES}.md`,
`gpu_worker_v3_controls/**` (18 attempts), `proposed-null-replicate-gpu-r2.json` `39fd2c0f…`.

## Verdict

- R1 responses: M1–M4 and m6–m9 are fixed for the paths the macOS mocks can exercise. M5 is
  partly fixed: the schema is restored and the consumer is explicitly blocked, which is acceptable.
  m10(d) is not fixed in substance (R2-m2). m12 is acceptable as UNRUN, but its coverage is
  insufficient (R2-m3).
- **One new material finding (R2-M1)**, which is Linux-only and invisible to every Mac control.
- Linux-only host mock (fake SMI, no GPU): **not ready yet.** R2-M1 and R2-m1 predict failures
  in K5/K12/K13 (intermittent) and K15 (deterministic). Fix those first; then the Linux host mock is
  the right next step.
- Real-GPU admission/deployment: **not ready.** Linux subreaper adoption, the `taskset` prefix, real
  `nvidia-smi` and the namespace-aware reader are all UNRUN or unimplemented. The exclusive GPU lane
  is a separate decision.

## Material finding

**R2-M1. On Linux the worker's own `nvidia-smi` queries are adopted as owned processes.** This
produces false `EXITED_WITH_OWNED_SURVIVORS` stops, and can produce a false `CLEANUP_FAILED` with the
lease held indefinitely.

- `Smi._run` launches every query with `start_new_session=True` (`gpu_worker_v3.py:82-83`). The
  query is therefore a direct child of the worker with PGID ≠ the worker's group.
- In subreaper mode, `ProcessOwnership.refresh` adopts exactly such children as owned
  (`process_ownership.py:309-323`: `ppid == parent_pid`, `pgid != parent_group`, not pre-existing).
  The observer thread does this every 0.05 s.
- The sampler keeps querying until `stop.set()` at `gpu_worker_v3.py:350`. That is after the
  post-exit survivor check (`:336-341`), after `terminate_owned` (`:342`) and after the
  `remaining` check (`:347`).

Scenario: a clean job exits while a sampler query is in flight. Then `live` contains the query and
the status becomes `EXITED_WITH_OWNED_SURVIVORS` (`:341`). `terminate_owned` verifies and signals the
query's group (`:157-161`), and the outcome is `RESOURCE` (exit 75) after a successful job. If a new
sampler query is alive at `:347`, `remaining` is non-empty, `cleanup_failed` is set, and the worker
writes `CLEANUP_FAILED` and holds the lease until an operator SIGKILLs it (`:374`, `:431-432`). The
same race affects the TIMEOUT and CANCELLED paths: K12/K13 would report `CLEANUP_FAILED` and time out
instead of exiting 78 or 4.

The per-job probability is about the sampler's query duty cycle, 2·t_query / (2·t_query + 0.25 s).
This is inferred, not measured. For a real SMI call of ~0.1 s it is ~40%. The fake SMI's Python
startup gives a similar range, so the Linux mock would show it too.

Evidence: `linux_adoption_demo.py` (data-only; synthetic process table, no signals, real `refresh()`
adoption branch). In subreaper mode the query PID 3000 is owned and `verified_group(3000)` is True,
while a helper kept in the worker's group (4000) is not. After the job root exits, owned-live is
`[3000]`, so v3 would set `EXITED_WITH_OWNED_SURVIVORS` and target groups `[2000, 3000]`. Polling
mode (the Mac controls) owns nothing. Output: `linux_adoption_demo.out`.

Fix direction (author's choice): stop and join the sampler before the `:335` ownership check, or
exclude the worker's own query identities from ownership. Add a Linux control that holds a sampler
query in flight across job exit.

## Moderate

- **R2-m1. K15's pass criterion holds only on macOS.** With Linux adoption, any observer error ends
  in `hold_lease`, even when nothing was launched. `own.restore()` (`gpu_worker_v3.py:444`) raises when
  `self.errors` is non-empty or `refresh()` fails (`process_ownership.py:266-269`), and `:446` then
  holds the lease forever. On macOS `restore()` returns immediately (`:256`), so K15 sees exit 75 and
  a free lease. The same scenario on Linux never exits, so K15 fails deterministically. Before the
  Linux mock, decide whether a zero-owned observer error should exit 75 or hold the lease. Then make
  K15's expectation match per platform.
- **R2-m2. The worker's own-group exclusion is still unobservable (R1 m10(d)).** Review mutant
  `r2_no_own_group_exclusion` removes both `os.getpgrp()` exclusions in `terminate_owned`
  (`:152`, `:156`). It passes **22/22** (`attempts/attempt-02-…`, exit 0). No owned process can carry
  the worker's PGID: jobs start in a new session, and Linux adoption excludes `pgid == parent_group`.
  So "shared-PG sentinel unsignalled" in K12/K13 cannot fail for this defect. The exclusion is a
  correct guard. Describe it as structurally untested, not as covered by K12/K13.
- **R2-m3. The m12 null does not cover the contention set.** The 57 null jobs are `e10216-00…07`. The
  54 contention jobs share **0 of 54** (movie, grid, arm) cells with them. 31 of the 54 are `e12963-*`,
  and the null has no `e12963` job. The packet's rule ("no attribution unless the null is byte-stable")
  is necessary only, and no causal claim is made, so this is acceptable as UNRUN. Before the null
  runs, record that null stability alone does not license attribution for uncovered movies or for
  the `e12963` dataset. Alternatively, add a dataset-matched null (for example, an exclusive repeat of
  the 54 jobs).

## Minor

- The worker returns `OK` without requiring `sampler.ok > 0` or `gpu_witness_uuids == [UUID]`
  (`:378-381`). A job that exits before the first sample is accepted with an empty witness, so the
  future reader must enforce the route witness.
- The census treats `EXITED_NONZERO` as complete (`:241`). The docstring/RESPONSES phrase "status
  EXITED" is literally true but easy to misread as exit 0. FINAL `counts` do separate the two.
- Errors before the lease (runs-dir `mkdir`, log or lease `open`) give an untyped traceback with
  exit 1 and no receipt. "Every exit path writes a typed receipt" is slightly overstated.
- `terminate_owned` refuses to signal even the unreaped `Popen` root when the observer has errors
  (`:145-146`). The job then runs to completion under a held lease. This is fail-closed and
  documented; `p.send_signal` on an unreaped child would be PID-safe.
- README v3 command binds `--binaries-sha256 28d84f5d…`. That value has no committed source;
  `binaries.json` is remote. A mismatch fails closed (exit 64), but verify the value before use.
- `test_gpu_worker_v3.py:12` advertises `--only`, which is not implemented.

## R1 disposition

| R1 | R2 status |
|---|---|
| M1 unbounded wait / dead observer | Fixed (bounded waits, CLEANUP_FAILED + receipt before hold, observer gate; K14/K15, mutant killed). Linux caveat R2-m1. |
| M2 exceptions / FINAL 0 | Fixed (typed per-stage exits 64/65/70/75/76; K4a–c, K9, K17, K18). Pre-lease I/O minor above. |
| M3 skip-existing | Fixed (non-empty refusal + census; K1/K8, mutant killed; attempt-08's non-exercise disclosed and fixed in 16). |
| M4 binding | Fixed (six bind checks, each K1 case discriminates its own check). |
| M5 witness/schema/consumer | Schema/witness restored (K5). Consumer unimplemented and **blocked**; no evaluation claim found. Witness not enforced (minor). |
| m6 sampler | Fixed (K7, mutant killed). |
| m7 cancel | Fixed (K10/K11, mutant killed). |
| m8 birth identity | Fixed (K16 unit, mutant killed). |
| m9 hung query | Fixed within stated limit (K4b); D-state unreproducible. |
| m10 harness | (a)(b)(c) fixed: identity-checked signals, reap in finally, mutants committed and reproduced by hash. (d) not observable (R2-m2). |
| m11 prefix | `/usr/bin/time` grandchild covered (K5); `taskset` and subreaper path UNRUN; R2-M1 lives there. |
| m12 null | Frozen, UNRUN, no causal claim; coverage gap R2-m3. |
| minors | ECC `[N/A]` fails closed (K2a, mutant); lease derived from index; scan UTC retrospective mtime bound (honest); polling timing unchanged. |

Scope and licence: the commit adds files only under `docs/post_rc0/s1/dc_factorial_20261022/` and
modifies only `resource_stop_20261022/README.md`. `src/`, `tools/multi_gpu/`, `campaign.py`, v2 and
its controls are unchanged. The `review-r1/` files are byte-equal to
`/tmp/motioncorr-dc-gpu-worker-review-r1-20261022/` (REVIEW.md `5a277e91…`). The new files are
`GPL-2.0-or-later`, stdlib only, and compatible with the repository's GPL-2.0. No historical
PASS/FAIL/UNRUN label was changed.

## Controls and evidence

- Retained author attempts: `check_attempts.py` confirms all 18. Each `worker_under_test.py` hash
  equals ATTEMPT.json, controls.json and the committed mutant replacement applied to v3. Test hashes
  match (01–08 `36cbb492…`, 09–18 `73735e79…`). 09 is 22/22. Each of 10–18 fails a superset of its
  `expect_fail`. 07 has a K12 harness error and 08 did not fail K8, as disclosed. No leftovers.
- Review attempt 01 (`run_v3_controls.py … worker`): unmodified v3, **22/22 PASS**, exit 0,
  PID 50238, 22:44:30–22:45:07Z.
- Review attempt 02 (`… mutant-r2_no_own_group_exclusion`, review-only `v3_mutants.json`
  `35083b18…` in a separate export `target-r2mut/`): **22/22 PASS** (mutant survives), exit 0,
  PID 52738, 22:45:14–22:45:50Z.
- Both ran on macOS 14 CPUs, load ~4–5, Python `/Users/alex.konstantinov/.local/bin/python3 -B`.
  Before each run I checked occupancy and found no mock processes. The runner uses its own session
  with identity-checked fallback, which was not needed. A post-run scan found no `sleep 300/301`,
  mock_job, smi.py, launcher or fault_entry process. No pkill/killall or name-based signal was used.
- Hashes of all review artefacts: `HASHES.txt`.

## Not done / limits

No Linux execution, so R2-M1's probability is inferred and R2-m1 comes from static reading of the
helper. No subreaper, `taskset`, real `nvidia-smi`, GPU, native or remote action. The binaries hash
and remote queue were not re-verified. These are host-mock and static findings only.

## Recommended next bounded action

The author fixes R2-M1 and settles the R2-m1 policy, with one Linux-targeted control each. A fresh
review follows. Then run the Linux-only host mock on 4GPUs with a fake SMI under the correctness
lock, NUMA0, and both `taskset` and `/usr/bin/time` prefixes. Real-GPU admission waits for that, for
a reviewed namespace reader, and for the exclusive lane.
