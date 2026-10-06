# Issue 83 — native CUDA option, repeat and resume support matrix

Validation evidence for issue #83, produced on top of the merged experimental
core (PR #82) and evidence (PR #81) under the ADR #66 stabilization spec.

| Document | Contents |
|---|---|
| `support-report.md` | Generated compact support table. Rows without a raw result are named `unrun`. |
| `provenance.md` | Hosts, devices, load, affinity, source/binary/input hashes, exact commands. |
| `progress.md` | Raw chronological worklog, including every defect found and how each was told apart from a product defect. |
| `withdrawals.md` | Every claim published in an earlier revision that the evidence did not support, what contradicted it, and what now gates it. |
| `raw/` | Machine-readable per-case reports the table is rendered from. |

## What this validates, and what it does not

**It validates implementation coverage**: for each declared configuration, did
the run execute natively on CUDA, produce the complete declared product set with
readable headers and original-pixel metadata, and reproduce byte-identically
across the uninterrupted, repeated, per-movie batched and non-prefix resumed
schedules.

**It does not define any numerical acceptance criterion.** Pixel and trajectory
equality is delegated verbatim to `tools/compare_motioncorr.py --gate exact`,
and motion accuracy to `tools/run_known_motion_gates.py`, both used exactly as
merged. This work sets no threshold and changes no comparator definition, FFT
engine, precision default, RNG or scientific formula.

**Numerical gates are a separate verdict from implementation coverage.** A row
passing here says a configuration is implemented, native and reproducible; it
says nothing about whether its pixels are scientifically correct. Historical
CPU/RELION Gate 2 failures remain failures, and no exact schedule comparison
converts one into a pass. The backend profile's relative image RMSE stays a
nonblocking diagnostic inside its own explicit profile.

**Exit status and counts are never accepted as evidence.** Every schedule
comparison is per movie: a missing movie, a missing image/metadata pair, or an
unreadable comparator report fails the aggregate even when the process exited
zero. Native CUDA execution is asserted from execution witnesses in the runner
and kernel output, not from the presence of a `--gpu` flag; on CPU runs, any
CUDA witness is itself an error.

## Scope boundaries

Owned here: `tools/validation_issue83/` and `docs/issue83/` only. No production
CUDA, runner, CMake or I/O file is modified.

Deliberately out of scope, tracked elsewhere:

- EER and compressed decoding rows: issue **#8** (declared unsupported here).
- Broad allocation/plan/execution fault injection and memory-capacity sweeps:
  issue **#69**. Exactly one measured capacity datapoint is in scope here —
  peak device memory for the largest declared row, sampled from the driver.
  It is a measurement of one configuration, not a capacity contract.
- Multi-GPU sharding: issues **#53 / #55**. The scheduler is consumed only once
  its aggregation is independently valid; no second scheduler is created here.
- Optional CUDA event profiling: issue **#74**.
- Active I/O and gain-sum optimization: issue **#85**.

- The CUDA resident-alignment **fallback** path: not exercised here. Review on
  PR **#82** reports that the fallback at `motioncorr_runner.cpp:2019` retries
  without resetting `local_xshifts`/`local_yshifts`. The largest declared row
  peaked at 1266 MiB of 40960, so nothing in this matrix comes near triggering
  it. A local row passing here says nothing about that path.

Early binning is never compared against late binning as an exact oracle (#68).
Each binning mode is only compared against itself across schedules.

## Fixture provenance

Fixtures are verified against the manifest **tracked in git**, by
`tools/validation_issue83/verify_fixtures.py`, not against the copy the
generator writes next to its own output. The latter agrees by construction and
hid a genuine cross-host divergence (NumPy 1.22.4 versus 2.x) during this work.
A run whose fixtures fail that check does not produce evidence.

## Replay

See `tools/validation_issue83/README.md` for the exact commands, and
`provenance.md` for the hashes and environment each recorded result came from.
