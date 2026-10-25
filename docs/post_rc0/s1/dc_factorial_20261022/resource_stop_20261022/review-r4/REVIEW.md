# Independent review R4: #262 gpu_worker_v5 source delta and control readiness

Reviewed revision: `1a62f0f94bded08279d879caed6482c817843833` (tree `71dc0c6d…`), read as exact git objects
(`git show <sha>:<path>`) from `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-6c79c479`; the author worktree was not
written. Tested source/control commit `8770453f`, contract commit `a2255956`, parent `44d3cf57`. Reviewer: Sonnet 5.5,
invocation `inv-a01ff47e-3d27-4e4a-8d0e-c1f6857ac9ce`, 2026-10-23 00:2x-00:3xZ.

Scope of this review: the v5 delta and the readiness of its controls. Not science, not GPU readiness. No SSH, Linux, build,
taskset, real `nvidia-smi`, GPU, worker process or mock process, and no process signalling. Only static reads and data-only
controls (synthetic process tables, in-memory mutants, `census`/`parse` unit calls, one mocked `hold_lease` call that raises
before any signal call), one numeric thread, Python 3.14.8, host load 22–38 (nothing here was timed).

## Verdict

- **No material finding in the v5 delta.** Every R3 item (M1, m1, m2, the integrity minors, K5/K5P) is implemented as the
  contract says, and the new controls K28/K30 and the admission units discriminate in my data-only reruns.
- **Bounded Mac real-worker mock suite: GO as written, no author change required.** The suite is safe by trace: the harness
  and runner only signal after a PID/birth/pgid/session recheck; the worker signals only its own Popen root or re-verified
  owned groups. Results must be reported with the limits below (R4-1…R4-4): a PASS does not cover them. The runner will
  refuse on its own while load exceeds the logical CPU count (14).
- **Linux fake-SMI qualification: not yet.** Do it only after the Mac results are retained, and after R4-1 and R4-3 are either
  repaired with a control or recorded in the contract as accepted limits (preconditions at the end).
- Source is not qualified. Worker implementation controls K25a, K25b, K27, K29, the full v5 harness and the five targeted
  mutants remain UNRUN by the author and by me.

## Findings

Severity is for the stated claim "never release the lease while unresolved owned work exists, with typed receipts". None blocks
the Mac mock; R4-1 and R4-3 matter before any GPU use.

**R4-1 (moderate, pre-existing in v4, uncontrolled): an I/O error in a receipt write releases the lease.**
`receipt()` (`gpu_worker_v5.py:247-252`) does an unguarded `write_text`; `hold_lease()` (`:254-258`) calls it before ignoring
signals and pausing; `main` calls it again from its own `except Exception` handler (`:527-528`); `run_job` writes RUN.json
unguarded (`:454`); FINAL is unguarded (`:561`). If the runs directory becomes unwritable or full (ENOSPC, EDQUOT, EIO,
directory removed) at the point of a CLEANUP_FAILED outcome, `hold_lease` raises instead of holding, the `except` handler
raises again, the exception leaves `main`, the process exits, and the kernel drops the flock — with the unresolved job tree
possibly still alive and no CLEANUP_FAILED_LEASE_HELD receipt.
Data-only evidence (`out/hold_and_census_probe.json`): `hold_lease` on a nonexistent runs dir raises `FileNotFoundError`; no
`signal.signal` call and no `signal.pause` were reached. The end-to-end exit follows from `sys.exit(main())` having no
handler (static). No harness control writes into an unwritable runs dir after launch.
Fix direction: in `hold_lease`, wrap the receipt write and fall back to stderr/stdout, then always reach the pause loop;
same fallback for the `main` handler; a control that `chmod`s the runs directory from the mock job after the flag.

**R4-2 (control gap): only half of "both refresh-exception branches" is witnessed.**
K25a's fault makes every main-thread `refresh()` fail, so `terminate_owned` leaves at the first refresh (`:203` → `:206-207`).
The in-loop branch (`:219-222`) is never entered, and the `own.errors` branch (`:198-201`, now `signal_root`) is only
reached by v4's K14, whose check asserts receipt, lease held, worker alive and CLEANUP_FAILED but not that the root was
signalled or gone. The v5 mutant `no_root_signal_on_refresh_exception` removes `:206` and `:221` together, so a regression of
either alone (or of `:200`) survives. I generated two single-site mutants (`_r4mutant_loop_branch_root_signal_only_removed`,
`_r4mutant_errors_branch_root_signal_removed`; targets unique, compile); their survival under K25a/K14 is predicted from the
trace, not run. Fix direction: a K25c that fails refresh on the second call (or after a flag set during `terminate_owned`) and
asserts root gone; add root-gone to K14. Equivalent-mutant note: removing `:200` is not equivalent, only unobserved.

**R4-3 (limitation not stated, Linux-relevant): root-only signalling does not stop the native binary under the production prefix.**
With `taskset -c N /usr/bin/time -v -o … binary`, the Popen root is `/usr/bin/time` (taskset execs) and the CUDA binary is its
child. GNU time ignores SIGINT/SIGQUIT but not SIGTERM, so TERM/KILL of the root kills time and orphans the binary (static
knowledge of GNU time, UNRUN here). K25a uses a mock whose root is the job itself, so "root gone" passes. In production the
R3-m2 harm (a timed-out job keeps using the GPU under a held lease) persists; the contract does accept that descendants are
not signalled, but RESPONSES presents R3-m2 as resolved. Fix direction: record it in the contract, or signal the original job
process group while the root is unreaped (its pgid is the root's PID and cannot belong to anyone else while the root is
unreaped; members that `setsid` are missed). Linux qualification must run a K25a variant with a `/usr/bin/time` wrapper above
the mock job.

**R4-4 (minor): `CLEANUP_FAILED` can be masked.** `run_job` returns `JOB_STAGE` for an `outputs_error`/`dc_witness_error`
(`:455`) before it tests `cleanup_failed` (`:456`). With both faults, `main` takes the STOP path instead of `hold_lease`
(`:521-526`), and the lease is held only if `own.known_live()` is non-empty or the restore raises at the end (`:531-545`);
`cleanup_errors` or `remaining is None` alone do not hold. The output-hash and witness-parse error branches themselves have
no control (the contract's "RUN.json for every job that ran" is static there). Reorder `:455`/`:456`, add a unit.

**Observations (no action required before the mock):**
- R4-5: the observer-activation failure path releases the lease without FINAL (`:494-496`, STOP only); the contract says FINAL
  whenever the lease is released. No query or job exists on that path. Also the docstring "Cleanup signals only process
  groups…" omits the root-only paths.
- R4-6: SIGHUP is not handled; a hangup kills the worker and releases the lease while the job root (new session) keeps
  running. Same class as SIGKILL; handle by launch discipline (the Linux launcher must ignore SIGHUP, or map it to cancel).
- Redundant layers, not gaps: the generic `except Exception` at `:437`/`:554-555` and the `and not unreaped` clause at `:539`
  (backstopped by `:556-559`) are invisible to K27/K29 but harmless. v4's mutant campaign was not retargeted on v5; the v5 delta
  touches `_run` and `terminate_owned` only, and the retained v4 mutant targets `no_group_signal`/`no_own_group_exclusion`
  are textually unchanged in v5.
- `_run`: `p.kill()` signals only the direct query PID, fine for the real `nvidia-smi`; a wrapper `--smi` command would leave
  grandchildren in the worker's group (the docstring already says so).
- The census treats `{"status":"EXITED","exit":null}` as `EXITED_NONZERO` (complete). Data-only probe, harmless.
- Writes are not failure-atomic at file level (`write_text`); a torn RUN.json is classified `UNREADABLE_RUN_JSON` and not
  complete (conservative), which is the K28 case.

## R4 questions, answered

| Question | Result |
|---|---|
| Owner PID/birth/ancestor/exact token excludes the T3 watchdog, refuses orphan/foreign | Verified by reading `run_v5_controls.py:48-75` and by rerunning the author's 11 synthetic cases (11/11 PASS) plus my 9 (8 as expected; the 9th, a literal-quoted token, is a fixture artifact, since `ps` prints argv without quotes). The real refused tree (retained ATTEMPT.json: ancestors `[1,14052,14053,16404,16516,23920]`, watchdog 23952 a child of 23920 with an exact `--resume=<id>` token) is the shape the base case uses. Tuple birth (ProcessTable on macOS) equals JSON list birth. An ancestor of the owner carrying the exact token is refused (fail-safe; not present in the real tree). A reader such as `less run_v5_controls.py` in the owner's tree is refused (fail-safe). |
| Bad birth, non-ancestor, wrong id, space form | Covered by the author's cases; same PASS. |
| Both refresh-exception paths signal only the Popen root and keep the lease | Code: `signal_root` (`:186-192`) uses `root.send_signal`, which is PID-safe until reaped; both `:206` and `:221` call it and then return errors, so `cleanup_failed` is true and `main` holds. Control: only `:206` is witnessed (R4-2). Production topology: R4-3. |
| Typed spawn error preserves RUN and FINAL | `_run` types `OSError` (`:114-117`); post-job and final queries catch it (`:436-437`, `:552-555`); RUN.json is written after every post-job step. Control K27 discriminates the typed error against the untyped mutant (static trace); not run. |
| Census malformed JSON does not erase audit | `census` (`:289-308`) never touches the file and classifies it `UNREADABLE_RUN_JSON`; my probe covered `[]`, `null`, wrong-typed status, empty file, missing `exit`. `out/units-*.json`: real PASS, `census_raises` FAIL. |
| Query/sampler quiescence and lease policy, all release/error paths | Enumerated every release: `:488` (never acquired), `:496` (no queries or jobs exist), `:562` (after `unreaped` check, `:556-559`), hold paths, and implicit release by an escaping exception (R4-1). The zero-job release requires no unreaped query (`:539`). Residual: an unjoined sampler thread alone (`sampler_unjoined`) does not hold the lease; it is bounded by `2*query_timeout+10` and only matters if the thread starts a query after the unreaped check (negligible). |
| v5 label/schema | `dc262-run/v5`, `gpu_worker_v5` on all three record sites (`:319`, `:323`, `:336`); docstring and log name say v5. Remaining `V3_FAULT`/`runs-v3`/`gpu_worker_v3_k16` strings in the harness are internal fixture names, not provenance. |
| K25a/b, K27, K28, K29, K30 and targeted mutants | K28 and K30 rerun: pass on the real worker, fail on `census_raises` (K28) and on two prefix mutants (K30). K25b discriminates `unbounded_child_wait` (the root sleeps 300 s, `signal_root` is a no-op in the test process, so only the bounded `p.wait(timeout)` yields a receipt inside the 40 s window), K25a discriminates the combined root-signal removal, K27 the untyped spawn, K29 the `if unreaped` removal — static traces, not run. All five mutant targets are unique in the exact worker blob (`out/mutant_check.json`). Gaps: R4-2, R4-4. |
| Time prefix: Mac `-l`, Linux `-v`, K5P production | `time_prefix` selects by platform; K5 passes it; K30 checks `' -l '`, `' -v '` and that the worker default equals `taskset -c {cpu} /usr/bin/time -v -o {out}/time-v.log`. K5P is correctly UNRUN on macOS and does not check `ownership_mode` (R3 asked for the `linux-child-subreaper` witness; add it for Linux). |
| Source, manifests, hashes, licence, scope | Hashes match the author's list: worker `1e3d6f0a…`, harness `a2b320be…`, runner `4f70d4fa…`, mutants `c82e22b3…`, admission test `7ba17622…`, CONTRACT `34800fe1…`, retained R3 REVIEW `275d97ae…` (equal to the reviewer's file); `process_ownership.py` `8de59b8c…` and `campaign.py` `8701cf24…` unchanged. `git diff --name-status 44d3cf57 1a62f0f9`: 50 added, 1 modified (resource_stop README), all under `docs/post_rc0/s1/dc_factorial_20261022/`; nothing outside, no `src/`/`tools/multi_gpu/`/`campaign.py` change. All new `.py` files carry `GPL-2.0-or-later`, stdlib only, matching R3's assessment. The README edit records the suite as UNRUN and does not alter any PASS/FAIL/UNRUN label. |

Runner timing: v4's retained full-harness runs took 57–63 s; v5 adds roughly 25–30 s of controls, so the 180 s bound has
margin on an idle host, and an overrun fails visibly (SIGTERM, no result JSON), never as a PASS. The runner exits 0 on `RAN`
whatever the harness result, so the verdict is read from `controls-*.json`, not the exit code.

## Genuine control gaps versus redundant mutants

Genuine: R4-1 (no unwritable-runs-dir control), R4-2 (single-branch root signalling), R4-3 (production wrapper topology),
R4-4 (outputs/witness error ordering), `ownership_mode` witness for Linux, no control for the K29 injected set being a real
`QUERY_HUNG`. Redundant or equivalent: the generic `except Exception` fallbacks, the `:539` unreaped clause, v4 mutants not
retargeted, the substring and r2-owner admission mutants overlapping (the r2 mutant is a hybrid that still applies the token
check, so it fails by over-refusal with one reason; its discriminating case is the watchdog tree).

## Preconditions for the later Linux fake-SMI qualification

Fresh read-only preflight and nonblocking locks per the current resource policy; fake `--smi` plus a failing `nvidia-smi` shim
first on `PATH`; harness lease in its own temp dir, never `/tmp/motioncorr-gpuN-correctness.lock`; no `prlimit --as`;
`TMPDIR` under a fresh bounded `/mnt/clathrin` scratch; launcher ignoring SIGHUP; K5P and a K25a variant with a
`/usr/bin/time` wrapper above the mock job; assert `ownership_mode == 'linux-child-subreaper'` in the RUN.json; R4-1 and R4-3
repaired or recorded; every attempt retained, no in-place retry. This review authorizes neither run.

## What I ran (all data-only, one numeric thread, `python3 -B -I`)

1. `git show` export of the exact blobs into `target/` (tools files, contract, RESPONSES, R3 review, static evidence) plus
   `process_ownership.py`/`campaign.py`/v4 worker for diffing.
2. `scripts/mutant_check.py`: uniqueness of every replacement target, in-memory `compile`, emitting mutants; 9 mutants OK.
3. `test_run_v5_admission.py --json`: 11/11 PASS (`out/admission-units.*`).
4. `scripts/extra_admission.py`: 9 extra synthetic cases (`out/extra_admission.*`); 8 as expected, 1 fixture artifact.
5. `test_gpu_worker_v5.py --only K28,K30` against the real worker (PASS/PASS) and the mutants: `census_raises` K28 FAIL;
   `k30_default_prefix_l`, `k30_default_prefix_no_taskset` K30 FAIL (`out/units-*`). These import the worker module only;
   no Fixture, subprocess or signal.
6. `scripts/hold_and_census_probe.py`: mocked `hold_lease` on an unwritable receipt dir (raised, nothing held) and eight
   census edge cases.

Not done: any worker/mock process, K25a/b, K27, K29, K5/K5P, full suite, mutant campaign, Linux. Every UNRUN above stays UNRUN.
Process note: the nonblocking lifetime lease was taken only at the report-writing stage; earlier steps wrote only inside this
invocation directory, and no other invocation directory existed.

## Unresolved objections

R4-1 and R4-3 before any GPU use; R4-2 and R4-4 as control or ordering fixes, ideally in the same bounded revision, which would
need a fresh delta review. None blocks the one bounded Mac mock suite as written.
