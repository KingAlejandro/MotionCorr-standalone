# Amendment: driver resource receipts and operational hardening (criteria frozen before any change or test)

Answers Opus review r1 of release v5 (report sha256 `b7351eca...ff521ac`): M1 (child thread/mask sampling required by approved PLAN.md line 23, not implemented) and the operational LOW-A, -B, -C, -D.
Scope is driver-only. `pair_decision_v5.py`, `ADMISSION_V5.json`, `COMMANDS_V5.json`, the C++ source, tests, CMake and the binary are unchanged and keep their anchors. The frozen release packet at
`668be682` (driver `676eff39...`) is kept as is, in Git and in the durable copy `Native-local-full-width-release-v5-prep-r1/`; the patch is a new file `driver_v5_1.py` (a modified copy with a reviewable
diff), so the old driver is never overwritten. A `PARENT_RELEASE.json` for the patched driver must name the sha256 of `driver_v5_1.py`. No producer runs, no `PARENT_RELEASE.json` is created, no movie, no build, no GPU, no new
native payload. Nothing here changes physics, timing or the MotionCorr process; the child is only observed.

## M1: resource receipts (a record, never a gate)
During the child wait, `driver_v5_1.launch` samples `/proc` and stores `resource_samples` in `RUN.json` (an extra key; `admit_producer` reads named keys only):
- Schedule: one sample immediately after `Popen`, then a poll every 20 ms for the first second, then every 100 ms until exit or timeout. Stored samples are capped (400); sampling continues for the summary and
  `truncated` is set. No sample is ever skipped silently.
- Per sample (monotonic ms since Popen): for the child and the descendants reachable through `/proc/<pid>/task/*/children`: pid, ppid, name, state, `Threads`, task count (`/proc/<pid>/task` entries),
  `Cpus_allowed_list` as read from that process (never copied from the expected mask), utime/stime ticks, VmRSS.
- Status: `OBSERVED` (at least one successful read of the child), `PARTIAL` (reads succeeded but some failed), `UNOBSERVED` (none; reason recorded, for example no `/proc` or the child exited before the first read).
  Read failures are counted with the first error strings. `--j 2` is never treated as proof of `Threads == 2`.
- Summary over all samples: max Threads, max task count, distinct `Cpus_allowed_list` values, processes seen, sample count, first/last sample time. Deviations (for example Threads 3) are receipts, not a new STOP or threshold.
  No retry of a native run for lack of a sample; UNOBSERVED is reported as such. The sampler does not slow, pause, signal or alter the child.

## LOW-A: lease ownership
`real_guard` replaces the flock probe with `/proc/locks`: for every overlapping lock path the current `os.stat` inode (and device) must appear as a `FLOCK ... WRITE` entry whose owner pid is in the driver's
ancestor chain (walked through `/proc/<pid>/status` PPid, so an intermediate wrapper shell is fine). A lock held by a peer, an unheld lock, or a lane that holds an orphaned inode while a peer holds the recreated path
all fail. The env-string set equality stays. `lane.py` (pin `e0143e89...`) is unchanged; no lock is released or taken by the check and no process is signalled. Controls: unheld, ours, peer-held, recreated-inode with a
peer, intermediate wrapper; pure parsing/decision tests on fixture text everywhere, real-process controls on cpu64 only.

## LOW-B: scratch and free space
Per step the guard records free bytes (`statvfs`) of the campaign filesystem and refuses below a floor of 1 GiB (`max(1 GiB, admission min_free_bytes)`; the current admission has no such key, so 1 GiB; the parent may raise it
only through a later admission, set before any outcome; it is a resource floor only). `prior_scratch_bytes` stays the frozen conservative constant (6,041,466,254 B for four retained namespaces, measured at freeze) and is
labelled so in every guard receipt (`prior_scratch_frozen: true`); a live pre-launch measurement of those namespaces by the parent is still required. No fake freshness is claimed.

## LOW-C: child lifecycle
On any exception, `KeyboardInterrupt`, `SystemExit` or SIGTERM (converted to an exception inside the campaign), the driver terminates only its own child process group (SIGTERM, short wait, SIGKILL, then wait/reap; a group
signal only while the child is still unreaped and is its own session/group leader), writes a `RUN.json` marked aborted (exit None or the real code, the real exception text), appends `finished`/`STOP` with the real exception, and
launches nothing further. A `Popen` failure writes a `RUN.json` with `launch_error` and a ledger STOP. On Linux the child sets `PR_SET_PDEATHSIG = SIGKILL` through `ctypes` (no new package), so an abrupt driver death
(SIGKILL) takes the direct child with it. Unavoidable limits, documented not engineered around: grandchildren are not covered by the parent-death signal, SIGKILL of the driver cannot run cleanup code (the ledger then has a
`launching` without `finished`), and there is no cgroup or supervisor.

## LOW-D: release binding limits
`PARENT_RELEASE.json` can only format-check `delta_review_report_sha256` and `approved_by`; the driver cannot see the report. Binding the report file, the tests file and the fresh resource admission to the release is the parent
release index's responsibility; shared libraries are pinned in the admission but not re-hashed on disk before each launch; `controlled_environment_observed` is the dict passed to `Popen`, which is the actual environment
because nothing is inherited. The parent verifies the actual report file.

## Tests (fixed before running; `tests/test_driver_v5_1.py`; fake child only, <= 2 threads, scratch < 150 MB)
Everywhere (macOS and Linux): pure parsers on fixture `/proc` text; lease-ownership decision on fixture `/proc/locks` text with the five controls; the sampling loop with injected readers (multi-thread child with a mask that
differs from the expected one recorded as read and the run continues; enough samples; a read failure gives PARTIAL; no readable sample gives UNOBSERVED; truncation keeps the summary updating; a fast child gives an honest
UNOBSERVED/short result; a non-zero exit and a timeout still carry `resource_samples`; the extra key leaves `admit_producer` passing; resource keys are non-empty whenever a read succeeded); exceptions in the wait
(KeyboardInterrupt, SIGTERM, an injected sampler error) leave no running child, an aborted `RUN.json`, a STOP ledger line with the real exception and no further launch; a `Popen` failure; the guard receipts carry the
free-disk and frozen-prior fields and the floor refuses.
Linux only (cpu64 under fresh 32-47 leases and the guard, `-j1`, no MotionCorr child): real `/proc` sampling of a multi-thread Python child (`Threads` > 1, task count, the mask the kernel reports), real flock controls on
temporary lock files (unheld, ours via an ancestor, peer-held, recreated inode, wrapper between owner and driver), and the parent-death signal killing a long-sleeping child after the parent is killed. These are reported as
SKIPPED (not passed) on macOS. Guard-removal controls for the mac-testable guards; shadowed guards declared, not claimed. Every run, failures included, is kept; no criterion is relaxed after results.
