# Driver v5.1 patch: package index (HELD; one independent driver-only delta review requested)

Answers Opus review r1 of release v5 (report sha256 `b7351eca615e95bee77fd67e16d22968eb61dad264be903020eba8b84ff521ac`, archived additively under
`~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-release-v5-delta-review-r1/`): M1 and the operational LOW-A to LOW-D. Criteria were frozen first in
`AMENDMENT_M1_RESOURCE_RECEIPTS.md` (sha256 `201114f28c4e6d69...`, commit c196d7a9). No producer was run, no `PARENT_RELEASE.json` exists, no movie, no build, no GPU.

## What is frozen and what changed
| file | sha256 | status |
|---|---|---|
| `pair_decision_v5.py` | `0826d64a29f40299b1d69f6b6776c29a5541f342c8e1f54ec5fa69bc01c9efd3` | unchanged |
| `ADMISSION_V5.json` / `COMMANDS_V5.json` | `dae759f7f12df05af24ca75f2bdbaa7eb9e5453186c86e9df27f81a3dcb53871` / `2bd36face2fed6f6a92398eb0402a63e6c6ea3624832e45c823f289a061b8081` | unchanged (anchors, binary, source archive, build receipt unchanged) |
| `driver_v5.py` (668be682 packet) | `676eff39d62aebdafb8623bd4c4046ba5f1367cc2d71dc07b8f1ce82fc6a5267` | unchanged, kept |
| **`driver_v5_1.py`** | `c4ec675277439dba574355d6deac2f53d2b4881953c8955d31cc2d2b3944b327` | new: modified copy, diff in `V5_DELTA_FOR_REVIEW/driver_v5_to_v5_1.diff` |
| `tests/test_driver_v5_1.py`, `tests/mutation_controls_v5_1.py` | `4ab6031f67e07528...`, `ac56c4bcc01c4b51...` | new |
Source, tests, CMake and the binary are unchanged. A `PARENT_RELEASE.json` for this driver must name the sha256 of `driver_v5_1.py` (the v5 module and admission hashes are as before).

## Changes in `driver_v5_1.py`
- **M1:** immediately after `Popen`, then every 20 ms for the first second and every 100 ms after, the child and its descendants (through `/proc/<pid>/task/*/children`) are sampled: pid, ppid, name, state, `Threads`,
  task count, `Cpus_allowed_list` as read from that process, CPU ticks, VmRSS. The samples (capped at 400 stored, the summary keeps updating) go into `RUN.json` as `resource_samples` with an explicit status
  (`OBSERVED`/`PARTIAL`/`UNOBSERVED` and a reason), read-failure counts and a truncation flag. Deviations such as `Threads 3` are receipts, not a gate; `--j 2` is never proof of two threads; a run is never repeated for lack of a sample.
- **LOW-A:** `real_guard` checks `/proc/locks`: the current inode of each overlapping lock path must carry a `FLOCK WRITE` entry owned by an ancestor of the driver (a wrapper shell in between is fine). Peer-held, unheld, recreated-path
  and orphaned-inode cases are refused; no lock is taken or released by the check. The dry run under the real `lane.py` reported the lane pid as owner of all eight leases.
- **LOW-B:** per-step free-disk receipt with a floor of `max(1 GiB, admission min_free_bytes)` (the admission has none, so 1 GiB). `prior_scratch_bytes` stays the frozen conservative constant and every guard receipt says so
  (`prior_scratch_frozen: true`); a live pre-launch measurement of the prior namespaces by the parent is still required.
- **LOW-C:** on any exception, `KeyboardInterrupt`, `SystemExit` or SIGTERM the driver terminates and reaps only its own child process group, writes an aborted `RUN.json` and the real exception into the ledger, and launches nothing else; a
  `Popen` failure writes a `RUN.json` with `launch_error`. On Linux the child sets `PR_SET_PDEATHSIG` (ctypes, no new package) so an abrupt driver death takes the direct child with it. Limits: grandchildren are not covered, SIGKILL of the driver cannot
  run cleanup (the ledger then shows `launching` without `finished`), there is no cgroup or supervisor.
- **LOW-D (documentation):** `PARENT_RELEASE.json` can only format-check the review report hash and `approved_by`; binding the actual report file, the tests and the fresh resource admission, and checking the report file itself, is the parent release
  index's job. Shared libraries are not re-hashed on disk before each launch.

## Test receipts
- macOS, fake child: `tests/test_driver_v5_1.py` run3 38/0, 4 Linux-only checks SKIPPED (not passed); `tests/test_release_v5.py` still 121/0 (run8).
- cpu64, fresh leases (lane.py, 8 overlapping locks plus the bench lock, CPUs 32-47), `-j1`, fake child only, no MotionCorr child: `receipts_cpu64_v5_1/receipts/test-v51-linux-run1.log` **51/51, 0 skipped**, 10 s, max RSS 37 MB, no scratch left.
  It includes real `/proc` sampling of a multi-thread child (`max_threads 4`, mask `32-33` as the kernel reported it after the child was set to two CPUs, grandchild seen, 51 samples), real flock controls (ours, bash wrapper, unheld, peer-held,
  recreated inode with a peer), `real_guard` under the real lane with the free-disk floor, and the parent-death signal (with a control that survives without it).
- cpu64 dry run of `driver_v5_1.py` (no `--execute`) under the real lane: 16 rows planned, nothing created, guard receipt with `lease_owner_pids`, `free_bytes`, `prior_scratch_frozen` (`receipts_cpu64_v5_1/receipts/dryrun-2.json`).
- Guard-removal controls for the macOS-testable guards (`logs/mutation-v51-run3.log`): 15/15 killed (one by killing the test process). The Linux-only guards (free-disk floor, parent-death signal, real flock) are covered by the real-process tests above and are not mutated.
- Failed attempts and corrections are kept in `logs/ATTEMPTS_v5_1.md` (a test recorded an int as detail and hid two lease controls; a harness fragment demanded a control the mutant cannot affect).

## Not established
No native run; the real binary's thread count and mask are exactly what the receipts will show at the first producer (UNOBSERVED if a child ends before the first read). The fake child proves driver logic, not that the binary obeys the frozen contract. No scientific, neutrality,
harm or GPU claim. One independent delta review of this patch (M1 plus the operational changes only) is requested; the parent writes `PARENT_RELEASE.json` and the final decision directory. No merge, default change, adoption or full100.
