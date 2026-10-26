# Driver v5.1 delta review (Opus, r2): CLEAR, conditional, for the bounded 8-case / 16-launch pilot

**Verdict: no BLOCK, no MATERIAL.** r1 M1 is closed; LOW-A is closed; LOW-B, LOW-C and LOW-D are closed as documented limits. The new findings are four LOWs and one evidence note (below). None needs a code change before the first producer. All evidence here comes from fake-child runs and saved metadata; this is not native acceptance and supports no scientific claim. The review grants no release. The parent still has to bind this report, the tests, the source admission and fresh resources in `PARENT_RELEASE.json` / the release index.

Reviewed: branch `experiment/local-full-width-weight-20261026`, HEAD `c9e17a958ef31d3e1febff0e5a2567026fa80812`, package
`docs/post_rc0/s1/local_full_width_native_20261026/pilot/release_v5/`. Prior review: `/tmp/mc-lfw-v5-release-opus-review-20261026-r1/REPORT.md`
sha256 `b7351eca615e95bee77fd67e16d22968eb61dad264be903020eba8b84ff521ac` (verified); manifest `4a161f2fc5b94f4720526ebf28c754138cf01f885a40c2534ef1da0925ad1ee8` (verified).

## Scope and identity checks (performed)
- `git diff --stat 668be682 c9e17a95 -- ':!docs'` is empty, so no production C++, tests or CMake changed. The three commits touch only the new v5.1 files. The amendment commit `c196d7a9` contains only `AMENDMENT_M1_RESOURCE_RECEIPTS.md` (sha256 `201114f2...bd38fc`), and it precedes the driver/tests commit `1143bfa3`.
- `SHA256SUMS_v5_1` and `SHA256SUMS_v5` both verify with no mismatch. `driver_v5_1.py` = `c4ec675277439dba574355d6deac2f53d2b4881953c8955d31cc2d2b3944b327`. `driver_v5.py` = `676eff39...6a5267` is unchanged. `pair_decision_v5.py` `0826d64a...`, `ADMISSION_V5.json` `dae759f7...` and `COMMANDS_V5.json` `2bd36fac...` are unchanged.
- `V5_DELTA_FOR_REVIEW/driver_v5_to_v5_1.diff` is byte-identical (after the header lines) to a fresh `diff -u driver_v5.py driver_v5_1.py`.
- Numerical command path: `argv`, `cwd`, `env` (expected environment plus `PATH=/usr/bin:/bin`), `_verify_identity`, staging, admission, `pre_ON_gate`, `admit_single` and `decide_pilot` are unchanged. The child-side changes are the `PR_SET_PDEATHSIG` prctl (Linux) before the unchanged `sched_setaffinity`, and the abort path's group SIGTERM → 5 s → SIGKILL (v5 sent SIGKILL directly on timeout). Neither touches the child's inputs.

## Prior findings: disposition
| r1 finding | v5.1 | disposition |
|---|---|---|
| **M1** child thread/mask not recorded (PLAN.md:23) | `ResourceRecorder` + `_wait_with_sampling` (`driver_v5_1.py:109-206`): sample immediately after Popen, then every 20 ms for 1 s, then every 100 ms. Records child + descendants via `task/*/children`: Threads, task count, `Cpus_allowed_list` read from each process, utime/stime, VmRSS. Status OBSERVED/PARTIAL/UNOBSERVED with reason, failure counts, truncation flag. Stored in `RUN.json.resource_samples` (`:381`) on success, non-zero exit, timeout, abort and launch error. | **Closed.** A record, not a gate; `admit_producer` still passes with the extra key (test). The cpu64 real child showed `max_threads 4`, `max_tasks 4`, mask `32-33` as read, grandchild seen, 51 samples. See N3 for the per-thread mask residual. |
| **L-A** lease probe proves "someone holds" | `/proc/locks` FLOCK WRITE on the current (dev, ino) owned by a driver ancestor (`:72-101`, `:282-296`) | **Closed.** Fixture controls cover ours, unheld, peer, orphaned-inode + recreated-path, READ, POSIX, other device and wrapper. Real cpu64 controls cover ours, bash wrapper, unheld, peer and recreated inode. Waiters (`->` lines) do not parse, which is correct because a waiter does not hold the lock. A device-number mismatch fails closed. The dry run reported lane pid 3637071 as owner of all 8 leases. |
| **L-B** scratch/free space static | per-step `statvfs` floor `max(1 GiB, min_free_bytes)` (`:306-310`); `prior_scratch_frozen: true` + note in every receipt | **Closed as documented.** `prior_scratch_bytes` is still the frozen constant, so the parent's live pre-launch measurement of the prior namespaces is still required. The floor is a resource floor and does not change any criterion. |
| **L-C** unexpected exceptions / child outliving driver | `except BaseException` in `launch` (`:387-409`) and `run_campaign` (`:475-477`); SIGTERM → `Terminated`; group kill + reap; PDEATHSIG | **Closed with documented limits** (no cover for grandchildren, no cleanup on SIGKILL, no cgroup). Tests cover KeyboardInterrupt, SIGTERM, an injected sampler error and a Popen failure (child gone, aborted `RUN.json`, real exception in a STOP line, one launch). See N1 and N2 for uncovered windows. |
| **L-D** report hash format-only | docstring/README/amendment state the limit | **Closed as documented.** Probe (`results/probe_check_release.log`): v5.1 accepts a release naming `c4ec…` and **rejects** `676e…`. v5 rejects `c4ec…`. v5.1 rejects a malformed report hash and `approved_by != parent`. `driver_v5.py` still accepts a release naming `676e…`, so the release must name `c4ec…` and invoke `driver_v5_1.py`. |

## New findings
**N1 (LOW) — SIGHUP is not handled.** Only SIGTERM is converted (`driver_v5_1.py:450-452`). If the driver runs in a tty session that hangs up (interactive SSH or a killed tmux pane), Python's default SIGHUP action ends it without cleanup. The outcome is the same as the documented SIGKILL limitation: no STOP line, no aborted `RUN.json`, and the ledger shows `launching` without `finished`. On Linux, PDEATHSIG still kills the direct child. There is no retry hazard because an existing ledger forbids a restart in place. The amendment lists SIGTERM only, so this is within the frozen criteria. Mitigation without a code change: launch through non-tty `ssh host cmd`, as the dry run did, or under `nohup`/`setsid`. A code fix would be one line: `signal.signal(signal.SIGHUP, _on_term)` with restore.

**N2 (LOW) — small unprotected windows in the cleanup path.**
(a) A signal that arrives after `Popen` returns but before the inner `try` (`:386-396`) skips the aborted `RUN.json`. The STOP line is still written, and on Linux PDEATHSIG kills the child when the driver exits.
(b) A second SIGTERM during the 5 s wait in `_kill_own_group` (`:219`) interrupts the reap. The group already has SIGTERM, and the outer STOP line is still written.
(c) A SIGTERM inside `_ledger` could leave a partial JSON line.
(d) The `prctl` return value is not checked (`:238`); the real cpu64 PDEATHSIG test shows it works on that host.
Each window lasts microseconds to seconds and needs an operator signal, so none is worth a change for the bounded pilot.

**N3 (LOW) — only the process-level mask is read.** `Cpus_allowed_list` comes from `/proc/<pid>/status` (`:129`), which is the main thread's mask. The thread count is recorded, but per-thread masks are not. The frozen environment has no `OMP_PROC_BIND`/`OMP_PLACES` (`COMMANDS_V5.json`), and a grep finds no `sched_setaffinity`/`pthread_setaffinity`/`omp_set_proc_bind` in non-doc C++/CUDA sources, so worker threads inherit the process mask. PLAN.md:23 ("actual process/thread/mask sampling") is satisfied in practice. An optional extension is to read `task/*/status`.

**N4 (LOW, design note) — a sampler bug spends a no-retry launch.** Any sampler exception outside the caught types reaches the `BaseException` path, which kills the native child and STOPs the campaign. The amendment's "injected sampler error" test freezes this behaviour. I found no realistic escape: `_one` catches OSError/ValueError/KeyError (plus IndexError for `stat`), the children walk catches OSError/ValueError, and the only uncaught case is an empty `VmRSS` value, which the kernel does not emit. "A record, never a gate" therefore holds in practice. A sampler failure would show as a STOP, not as hidden data loss.

**E1 (evidence note) — the cpu64 receipts do not hash the copy that ran.** The Linux 51/51 run and the dry run executed `/tmp/motioncorr-lfw-v5-20261026/pilot_v5_1/release_v5/`. I checked it read-only today (`results/cpu64_copy_hashes.txt`): `driver_v5_1.py` `c4ec…`, `tests/test_driver_v5_1.py` `4ab6031f…`, `test_release_v5.py`, fakes, module, admission and commands all equal the repo. Both files have mtime 22:48:26 UTC, before the 22:49 runs, and `lane.py` = `e0143e89…`. Today's hash plus an mtime that precedes the runs supports the binding but does not prove it retroactively. The fresh pre-producer admission should hash the on-host driver/module/admission it actually invokes.

## Performed vs UNRUN
Performed (Mac, 1 thread, scratch 0 B left, max RSS ~42 MB):
- `tests/test_driver_v5_1.py`: 38 pass / 0 fail, 4 Linux-only SKIPPED, not counted as passes (`results/test-v51-mac-review.log`, rc 0).
- `scripts/probe_check_release.py`: PASS.
- Read-only SSH to cpu64 for hashes and mtimes only. No job, lock or write.
- Inspection of the committed Linux receipts (51/51, 0 skipped, 10 s, 37 MB RSS, rc 0), the dry-run guard receipt, mutation run3 (15/15 killed, one by process death) and ATTEMPTS_v5_1.

UNRUN, by scope:
- full v5 suite (121) and the mutation matrix;
- Linux tests (receipts inspected instead);
- any native, MotionCorr, movie, GPU, build or benchmark run;
- a SIGHUP probe (N1 follows from Python's default disposition).

Native thread/mask receipts, OFF identity, the 9/0 witness and the first-line predictions remain UNRUN until the producer. Any first OFF compat failure stops the campaign before ON, with no weakening.

## Failed attempts
`failedattempts/attempt1_no_timeout_binary_on_macos.txt`: the first cpu64 hash command used GNU `timeout`, which macOS does not have. Nothing ran remotely. It was repeated without `timeout`.
