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
| `tooling_controls/controls_cpu64_2026-09-28.log` | tooling controls, cpu64 cores 32-63 under the validation lock | current |
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

## What is unaffected

Wall times, CPU times, exit codes, product digests (MRC payload, core header, masked labels,
STAR, EPS), effective-settings witnesses, and the per-movie CUDA execution witness. The
timing result and the complete per-arm product evidence stand.
