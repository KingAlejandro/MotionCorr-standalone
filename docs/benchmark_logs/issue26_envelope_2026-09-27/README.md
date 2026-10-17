# Issue #26 raw records — preserved as produced, with corrections listed here

These files are the **unmodified output of the runs that produced them**. Nothing has been
regenerated, relabelled or deleted to match later conclusions. Three fields inside them are
now known to be instrument artifacts. They are left in place — editing a retained record to
hide a defect is worse than the defect — and are listed here so nobody reads them as results.

| File | Produced by | Status |
| :-- | :-- | :-- |
| `gpu/p0p1_series.json`, `gpu/p0p1_report.json` | GPU screen + Phase 0, repaired instrument | timings and product digests **valid** |
| `gpu/conf_series.json`, `gpu/conf_report.json` | 24-movie confirmation, repaired instrument | timings and product digests **valid** |
| `cpu64/cpu_series.json`, `cpu64/cpu_report.json` | cpu64 scaling, **instrument v1** | timings valid; interference fields limited, see below |
| `tooling_controls/controls_cpu64_2026-09-28.log` | tooling controls round 1, runner sha256 `b05260db…` | **superseded — two controls were defective**, see below |
| `tooling_controls/controls_cpu64_round2_2026-09-28.log` | tooling controls round 2, runner sha256 `e7276f5e…` | superseded — reviewer found the residuals below |
| `tooling_controls/controls_cpu64_round3_2026-09-28.log` | tooling controls round 3, runner sha256 `fbe01390…`, 26 controls | superseded — see round 4 |
| `tooling_controls/controls_cpu64_round4_2026-09-28.log` | tooling controls round 4, runner sha256 `e3fffa45…`, 28 controls | superseded by the Codex review fixes |
| `tooling_controls/controls_cpu64_round5_2026-09-28.log` | tooling controls round 5, 35 controls | superseded by the final delta |
| `tooling_controls/controls_cpu64_round6_2026-09-28.log` | tooling controls round 6, **37 controls, 0 skipped** | current |
| `gpu/*`, `cpu64/*` build and topology witnesses | build scripts | current |

## Known artifacts inside the retained records

1. **`stage_timers.*.["Peak GPU memory allocated [MiB]"] = 3134.34`** — a **sum** of 26
   per-call size-accounting values (25 patch calls at 62.59 MiB, one global call at
   1569.59 MiB), produced by a parser that added repeated keys. It is not a peak, not an
   allocator trace, and not a per-process high-water mark. The same applies to every other
   MiB-valued CUDA profile key in these files. The parser no longer sums size-like tags.

2. **`placement.numa_maps_head` / `placement.numa_policy`** — sampled on the launcher pid,
   which is `taskset`/`/usr/bin/time`, not MotionCorr. The retained `numa_maps_head` shows
   this plainly: every mapping reads `file=/usr/bin/time`. `numastat` values are **MB**. Any
   payload NUMA or node-locality reading of these fields is unsupported.
   `placement.inherited_Cpus_allowed_list` and `Mems_allowed_list` **are** valid, because
   `taskset` sets the mask before exec and it is inherited.

3. **`sampling.*` in `cpu64/cpu_series.json`** — instrument v1: `ps pcpu` is a lifetime
   average, threads are counted by `psr` regardless of run state, and ownership came from a
   process-tree walk that races with the sampler's own children (hence `ps` and `gs` in its
   own foreign list). `foreign_threads_inside_mask.max` is an aggregate over all commands at
   one sample; `foreign_in_mask_by_command` values are accumulated thread-sample hits, not
   simultaneous threads. No per-sample series or PID was retained, so ownership of the
   observed foreign work cannot be attributed. The GPU records use the repaired instrument
   (`/proc` interval deltas, state `R` only, session-id ownership) and are **not** comparable
   to these numerically.

Each record self-documents which interference instrument produced it, in
`sampling.foreign_definition`.

## Why the round-1 control log is superseded

It is retained because it is the artifact the defects were found in, not because its two
process-control results stand. Both were defective:

- **The payload-versus-launcher control was vacuous.** It launched `/usr/bin/env python`,
  and `env` *execs* Python, so `pid == launcher_pid == 3166638` in that log. The assertion
  that distinguishes payload sampling from launcher sampling was conditional on the pids
  differing and therefore never ran. Round 2 uses `/usr/bin/time -v` — production's own
  shape, which forks and stays alive — asserts differing pids unconditionally, and
  mutation-proves the discrimination: sampling the parent yields **1.45 MiB** and *fails*
  the same assertion the child passes at 266.07 MiB. That 1.45 MiB is exactly the figure
  earlier mis-published as "1.45 GB of node-local movie arrays".
- **The cancellation control did not exercise the failing case.** Its child did not ignore
  SIGTERM, so it never reached the path where a cooperative parent exits, `proc.wait()`
  returns, and the helper stops escalating while an owned child keeps running. Round 2 adds
  that case and shows both halves: launcher-exit escalation leaves the child alive and
  reparented to init where a descendant walk cannot see it, while pgid enumeration can.

## Why round 2 is superseded

The delta review confirmed the reported cancellation defect fixed but found four residual
paths and did **not** confirm the payload control. Round 3 closes them:

- **R1 (material).** Only the abnormal exit paths verified the group. A payload that exits 0
  while leaking a child — MotionCorr finishing while its ghostscript child still renders —
  left that child reparented, still in the group, burning the cpuset under the next arm, and
  adopted by the interference sampler so it was not even reported. Now every exit path
  verifies. `control_6` proves it fires: exit 0, residual detected, child reaped, confirmed.
- **R2.** A second Ctrl-C during the up-to-80 s cleanup escaped with the group unverified —
  worse since `start_new_session` removed the payload from the terminal's foreground group.
  Cleanup now defers SIGINT/SIGTERM and re-raises after.
- **R3.** The window between `Popen` and the `try` was uncovered; a `can't start new thread`
  under a `pids.max` cap would escape with the payload running. Now guarded.
- **R4.** `group_members` returned `{}` when `/proc` could not be enumerated, so "could not
  look" read as "group is empty" and cleanup reported confirmed. It now returns `None` and
  the caller treats that as unconfirmed.
- **FIX 2 not confirmed.** The mutation half mutated the *test's* argument, not production:
  reverting `execute_arm` to sample `proc.pid` would have left it green. `control_5` now
  runs `execute_arm` against a real compiled ELF stub and asserts on the emitted record —
  193.38 MiB for the payload where a launcher-sampling record would read ~1.5 MiB.
- **Skips counted as passes.** Four `check(..., True, "SKIP")` sites meant the suite printed
  "all controls passed" on a host where only one ran. Skips are now tracked separately and
  exit non-zero.

## Why round 3 is superseded

The second delta pass confirmed R1's detect-and-kill, R2, R3, R4, R5 and the reworked
payload control, and found one sub-item still open plus three new defects:

- **A reaped residual was published as clean.** Quarantine keyed only on cleanup *failing*,
  so a residual that was successfully killed left `quarantined=False`. But a process that
  outlived the payload was running **during the timed interval**, sharing the cpuset — and
  being session-adopted, it never appeared in the interference figures either. Reaping
  cleans the host, not the measurement. Quarantine now also triggers on a reaped residual,
  and `control_6` asserts it.
- **The `control_3` handshake read the wrong `/proc` field** — index 29 after dropping comm
  is field 32 `blocked`, which `signal.signal` never touches, so it stayed 0 and the loop
  ran all 200 iterations: a 15 s fixed delay wearing a handshake's name. Fixing the index
  alone would have been worse, because field 33 `sigignore` is already non-zero (CPython
  ignores SIGPIPE at init), so a `!= 0` test would break immediately and silently restore
  the race. Both the index and a SIGTERM-bit mask were needed. Suite runtime fell to 18 s,
  which is the corroboration that it now exits early.
- **An uncancelled `threading.Timer`** could fire after `execute_arm` returned and mutate a
  `placement` dict already embedded in `series`, aborting a completed series inside
  `json.dumps`. Now held and cancelled.
- **`resolve_payload` iterated a set**, so a payload that forks without exec gave an
  arbitrary identity. Now lowest-pid deterministic.

Also corrected: the comment justifying the residual check cited ghostscript, but
`CPlot2D.cpp:57` calls `gs` through blocking `system()`, which reaps it. The mechanism is
generic; that particular instance cannot occur here, and the comment now says so.

## Additional artifact caveat from the Codex review

`memory.peak_simultaneous_tree_rss_kib` in every retained series was collected with
`ps --ppid`, which selects only **immediate** children. Helpers spawned at a second level
were omitted, so the value is a **lower bound** on the process tree it names, and the
report's ~1.52 GiB per-process figure inherits that. The sampler now walks the full
descendant tree and records the peak's composition and unit; the retained values are not
re-measured.

Also: `sampling.*` in every retained series carries aggregates only. Per-sample interference
identity (pid, session, start time, command line, cpus, timestamp) is retained from this
source revision onward, so the attribution gap described above for the cpu64 records cannot
recur — but it cannot be filled retroactively for the existing files.

## The lane was shared during the round-5 controls, and the new records name who

While the controls ran, another worker's job was executing inside the 32-63 lane:
`python3 src/tools/calibration/layer2_forward.py --trials 5 --size 1024 1024 --frames 24`,
pids 3290541-3, session 3290533 — alongside the permanent unpinned `ctffind`. It was not
altered.

This is recorded because it demonstrates the per-sample identity requirement earning its
keep immediately. A control keyed on the *command name* `python3` failed, because that
neighbour shares the interpreter's name with the control's own payload; the aggregate
counters could not distinguish them. The per-sample records named the pid, session and full
command line in one look, the control was re-keyed on session id, and the ambiguity
disappeared. Aggregates alone would have left that failure unexplained — which is precisely
the attribution gap the ADR faults in the original CPU evidence.

## Stated limits of the repaired instrument

Three properties are bounded rather than complete. Each is recorded here so a reader does
not take the record for more than it is.

- **Per-sample interference retention is first-N.** The cap is 4000 in-mask samples (~67 min
  at 1 Hz) and both the cap and the drop count are in every record, so truncation announces
  itself. What is dropped is always the *tail*, so an arm that is clean early and contended
  late keeps identity for the clean part only. The unbounded aggregates still carry the
  magnitude of the late contention; only its attribution is lost.
- **Per-sample identity is recorded for in-lane processes only.** The host-wide
  `foreign_cpu_pct` figure is an aggregate with no per-sample attribution. The ADR asks for
  mean/max/n there, so this meets the contract, but the host-wide number cannot be traced to
  a process the way the in-lane records can.
- **Tree RSS is an upper bound.** Summing per-process resident sets double-counts pages
  shared between them — copy-on-write, shared libraries, shared file mappings — so
  `peak_simultaneous_tree_rss_kib` exceeds the tree's true physical footprint. It is also a
  *lower* bound in the retained pre-fix series, which used a depth-1 selection. Those are two
  different errors in opposite directions and should not be netted against each other.

**Operational note:** the runner now calls `setsid()` at startup to obtain an isolated
session, which detaches it from the controlling terminal. Ctrl-C at the launching terminal no
longer reaches it; stop a run with an explicit `kill` to its process group.

## Timing population versus audit population

From this source revision onward the two are distinct, and the distinction matters when
reading any retained series:

- The **product audit** spans every run, including failures. A failed record is retained,
  never deleted.
- The **timing population** — medians, paired contrasts, positional slot ratios — excludes
  runs that exited non-zero, timed out, were quarantined, had unconfirmed cleanup, or
  produced no products. A run that died early has a short wall time, and admitting it would
  make the configuration that failed look like the fastest, inverting the contract's own
  rule that a failed movie is not a faster arm. Excluded runs are listed by tag and reason
  in the report output.

The retained series in this directory contain no non-zero exits, so this change does not
alter any published median; it prevents the inversion rather than correcting one.

## What is unaffected

Wall times, CPU times, exit codes, product digests (MRC payload, core header, masked labels,
STAR, EPS), effective-settings witnesses, and the per-movie CUDA execution witness. The
timing result and the complete per-arm product evidence stand.
