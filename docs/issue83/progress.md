# Issue 83 — raw progress log

Chronological worklog for the issue #83 validation. Kept raw on purpose: the
findings below include three defects in the *harness* that first presented as
product failures, and the record of how each was told apart from a real one.

## Provenance and base

- Isolated headless checkout, branch `opus/issue-83-headless-20260927`, started
  from `1d7e13f41b6eaf64b367d49ff0f0f5a3e09c0a26`.
- Live origin checked before work: `origin/main` was at the same `1d7e13f`, and
  `origin/integrate/cuda-stabilization` at `9154b68`, an ancestor. **No base
  update was taken**; the declared starting commit stands.
- One worktree only. No other checkout was created or modified.

## Reading

Read `AGENTS.md`, ADR #66 (`agents/designs/issue_66_stabilization.md`), the
merged evidence under `docs/stabilization_20260926/` and `docs/issue66_truth/`,
the runner option and resume paths in `src/motioncorr_runner.cpp`, the CUDA
stage marker in `src/acc/cuda/cuda_alignpatch.cu`, `src/micrograph_model.cpp`,
and the merged `tools/compare_motioncorr.py` and `tools/run_known_motion_gates.py`.

Two facts that shaped the harness:

- The native-CUDA completion marker in `cuda_alignpatch.cu:469` is **not**
  TIMING-guarded, so an execution witness works on any build configuration.
- `MotioncorrRunner::getOutputFileNames` (`motioncorr_runner.cpp:487`) keeps the
  movie's relative directory, so products land under `<outdir>/Movies/`.

## Fixtures

Fixtures are generated, never committed.

> **Withdrawn.** This section previously read "All five known-motion fixtures
> were regenerated and every `.mrcs` sha256 **matched** the committed
> `test-data/known_motion/MANIFEST.json`." That was not true, and the section
> "Fixture drift between hosts" below — written later, from a check that
> actually read the manifest out of git — contradicts it: all five cases
> mismatched on SCARF under NumPy 1.22.4. The original claim rested on the
> manifest the generator writes beside its own output, which agrees with those
> outputs by construction. The withdrawal is recorded as W6 in
> `withdrawals.md`; the replacement check is
> `tools/validation_issue83/verify_fixtures.py`, and what it establishes on
> each host is stated per-run in `provenance.md`.

## Compute

- **GPU**: dedicated SCARF Slurm allocations only, every one `--exclusive` on
  its own node, 4x A100-SXM4-40GB, driver 580.178.04, nvcc 12.8.61. First
  round `-p gpu --gres=gpu:1 --cpus-per-task=8 --exclusive` on `gn0005`;
  corrected-harness rounds `--cpus-per-task=16` on `gn3000`. No allocation was
  ever shared, and the QOS one-running-job cap means the `gn3000` jobs could
  not have overlapped. Full detail, including the other jobs on this shared
  account and the GPU UUIDs, is in `provenance.md`.
- **CPU**: `cpu64` (small-refmac-machine), 64 cores, load checked before each
  launch, under `flock /tmp/motioncorr-issue96-cpu-validation.lock`. The
  diagnostic matrix cited in the report used `taskset -c 56-63`, `--j 8`; the
  gate-contract validation of each harness commit uses
  `taskset -c 32-63 numactl --membind=1`, 16 threads.
- The shared 4GPUs fallback was **not used**; the dedicated route was available
  throughout. No credential, billing or terms-accepting change was made.

## Findings — harness defects, not product defects

Each of these first appeared as a failing row. Each was traced to the harness
before being reported, and none is a defect in the program under test.

### 1. Output paths (fixed in `fd1ea50`)

The first full run reported 22 of 24 rows failing with "missing declared
product" while every base run exited 0. The harness looked for products at the
top level of the output directory; the runner preserves the movie's relative
directory. The only two "passes" were the two rows that expect a rejection --
which is exactly the shape of a harness bug rather than a product bug.

Fixed by mirroring the runner's rule in `products.output_stem()` and threading
relative stems through the inventory, witness logs, comparator pairs and resume
hashes.

### 2. Auxiliary products compared by digest (fixed in `bab9f46`)

Four rows (`dose_on_savenoDW`, `evenodd`, `evenodd_dose_noDW`,
`power_spectrum`) failed with "extra products differ from base" while reporting
**3/3 movies exact**. The tell was the pattern: the fast `repeat` schedule often
passed while the slow `batch` and `resume` schedules always failed.

Byte-diffing a flagged pair settled it:

```
sizes 1049600 1049600
n_diff_bytes 2
first 251 last 252   all_in_header True
base bytes: b'29'    test bytes: b'30'
```

Two bytes, inside the MRC label region, a seconds field. The payloads are
identical. Runs that straddle a second boundary digest differently.

The auxiliary products now go through `tools/compare_motioncorr.py` like the
main image, which already reports `Normalized headers: ... Non-timestamp
labels: 0 diff bytes`. Confirmed directly on the flagged pair: `Pixel-identical:
True`, `Image RMSE 0.000000e+00`, `PASS`. No threshold was introduced or
changed.

Byte identity is **kept** for the resume-preservation check, where it is the
stronger and correct test: it shows completed products were left untouched
rather than rewritten to the same pixels.

### 3. Trajectory row count (fixed in `bab9f46`)

`frames_subset` failed with "12 global_shift rows, expected 8". The expectation
was wrong. `micrograph_model.cpp:456` sizes the trajectory by the whole movie
and writes `NOT_OBSERVED` (`-9999`, `micrograph_model.cpp:29`) for frames
outside the summed window. The actual output is correct and more informative
than the expectation:

```
_rlnMicrographStartFrame  3
1  -9999.00000  -9999.00000
2  -9999.00000  -9999.00000
3   0.000000    0.000000
...
10 -2.95729     1.162846
11 -9999.00000  -9999.00000
12 -9999.00000  -9999.00000
```

The check now requires one row per movie frame *and* exactly the requested
number of observed rows -- stricter than the row count it replaced. Verified
with a positive and a negative control.

## Incident — SCARF home quota, and a job killed by SIGPIPE

Job 3510277 died `FAILED, ExitCode 0:13` (signal 13) at 5:42, after creating all
25 row directories but before writing `summary.json` or starting the all-24 leg.
Root cause was not the harness: the home volume was at its quota
(`105.23 GB used, soft 90, hard 110`), so the job script's
`exec > >(tee ...)` process substitution could not write and the step took
SIGPIPE.

Almost all of that home usage is **other threads' trees** (`i53-scarf` 63G,
`mc-io`, `mc-stabilize-*`), which were left untouched. Only my own superseded
intermediates were removed, and my working tree was relocated to
`/scratch/scarf1415/mc-i83-tree` (unquotaed). The replacement job script drops
the process substitution entirely -- Slurm already captures stdout -- and runs
Python unbuffered.

SCARF has no outbound access to GitHub; its `origin` is a local bundle, so the
fix was shipped as an incremental bundle whose sha256 was verified on arrival
(`02a4e01f...`) before `git reset --hard`.

## Coordination

- Issue **#73**'s EER pilot was found running on cpu64 pinned to `taskset -c
  48-55`, the mask this work had been using. The CPU rerun was moved to a
  **disjoint** mask (`56-63`) rather than sharing cores. The CPU leg is a
  bit-identity diagnostic, not a timing benchmark, so disjoint cores are
  sufficient; no other user's processes were altered.
- No production CUDA, runner, CMake or I/O file was modified; #85 owns active
  I/O work, #74 owns event profiling, #53/#55 own the scheduler.

## Capacity datapoint

Issue #83 asks for a memory contract to be *measured* where a capacity claim is
made, so exactly one datapoint was taken rather than a sweep: the largest
declared row, `realscale_local` (2048x2048, 24 frames, local 5x5, native CUDA),
sampled from `nvidia-smi --query-compute-apps` every 0.5 s while it ran.

**Peak 1266 MiB of 40960 MiB** on one A100-SXM4-40GB, 32 samples (job 3510288).

The sampler reads the driver, not anything the program says about itself. This
is one configuration on one device and is not a capacity claim for other
geometries, frame counts or devices. No CPU-fallback behaviour is claimed, and
none is inferred from any exit status. Exhaustion and allocation fault
injection stay with **#69**.

That job's wrapper returned 1, which is the harness behaving correctly rather
than a row failing: it was invoked with `--rows realscale_local`, so 24 of the
25 declared rows were unrun, and an incomplete matrix is deliberately nonzero.

**Corrected — a detail withdrawn for want of a record.** This paragraph went on
to say the row "passed -- 2/2 movies exact under repeat, batch and non-prefix
resume, native CUDA witnessed, `declaration_drift` null". The only preserved
artefact of that job is `raw/scarf-gn0005/capacity.json`, whose `stdout_tail`
reads in full `[issue83] realscale_local: pass` and
`{"declared": 25, "attempted": 1, "pass": 1, "fail": 0, "error": 0}`. The
per-schedule figures, the witness and the drift field would have come from an
`evidence3/matrix-realscale/summary.json` that is **not preserved under
`raw/`**, so they are **withdrawn** — not because they are doubted, but because
nothing here supports them. What the record does support is the single word
`pass` and the 1-of-25 attempt count above. The `realscale_local` row's
per-schedule result of record is job 3511154's, in the matrix table.

## Fourth harness defect -- a renderer field that was never emitted

`render_capacity()` read `geometry`, `frames` and `patches` from the capacity
JSON. `measure_capacity.py` emits none of them; the configuration description
is in `note`. Published as-is the report would have read
"None, None frames, None". Fixed in `d48d875` to render the recorded note.

Worth stating plainly: this was caught by reading the renderer against the
producer, not by running it. A report generator that fails silently into
`None` is exactly the kind of thing that turns into a confident-looking table
with nothing behind it.

## Fixture drift between hosts, and a provenance claim that was wrong

Prompted by re-reading review on PR #82, which flags that
`test-data/generate_known_motion_fixture.py:489` rewrites every recorded hash
instead of comparing against the committed manifest, the fixture provenance
here was rechecked properly. It did not hold.

SCARF's system NumPy is **1.22.4**; cpu64's is 2.x. The same generator at the
same commit produced **different bytes** for all five cases. Each host had also
written its own `MANIFEST.json` next to its own fixtures, so each host agreed
with itself and the divergence was invisible to the check performed earlier.
cpu64's fixtures match the committed manifest; SCARF's did not.

Regenerating on SCARF under `netcdf4-python/1.7.2-foss-2025a` (NumPy 2.3.1)
reproduces the committed hashes exactly, which isolates the cause to the NumPy
1.22-versus-2.x arithmetic the manifest's own note warns about.

What this does and does not invalidate, stated separately:

- **Schedule equality is unaffected.** Repeat, batch and resume are each
  compared against a base run on the same host over the same bytes. Whether
  those bytes are the declared ones does not bear on whether an identical
  configuration reproduces identical pixels.
- **Native CUDA witnesses are unaffected.** They come from runner and kernel
  output, not from the input.
- **The all-24 leg is unaffected.** It reads the real tutorial runroot, not
  generated fixtures.
- **Motion-truth verdicts on SCARF were affected in provenance** and were
  re-run on verified fixtures. The earlier verdicts were internally consistent
  -- ground truth was generated alongside the movie -- but they were not the
  declared, versioned fixture, so they are superseded rather than cited.

`tools/validation_issue83/verify_fixtures.py` (`f51b45f`) reads the manifest
from git and refuses to proceed on mismatch. The corrective job aborts before
producing any evidence if the check fails, so undeclared inputs cannot silently
become published results.

This is the failure mode the issue warned about in a different guise: exit
status, counts and a matching-looking hash table are not provenance. The table
was real; it was just a comparison of the fixtures against themselves.

## Gates that quantified over nothing (`4c2305b`)

Review of PR #89 at `7098a6f` found the same defect in four more places. It is
worth naming once, because it is the defect of this whole issue: **`all()` over
an empty set is true**, and a gate written as "nothing mismatched" passes a run
that looked at nothing.

| Where | Passed vacuously when | Now |
|---|---|---|
| `verify_fixtures` | no digest was compared at all | counts comparisons per kind; `vacuous` fails the run (W7) |
| `run_matrix` per-schedule witness | `repeat`/`batch`/`resume` contributed no evidence | witness computed over every invocation and consumed by the row verdict (W8) |
| `run_matrix` rejection rows | the declared token appeared anywhere in the output, backtrace included | delimited match on a diagnostic line, recorded verbatim (W9) |
| `run_all24_schedules` | `check_products(..., {}, None)` asserted no metadata | asserts the invocation's own binning, first frame, dose and pre-exposure (W10) |

Two things follow, and both are stated rather than smoothed over.

**The runners changed, so the published GPU records are behind them — but not
in the same way for both claims.** Jobs 3511139 and 3511154 ran `7ba584e`;
`run_matrix.py` and `run_all24_schedules.py` changed at `4c2305b`. The STAR
metadata assertion did not exist at `7ba584e`, so nothing in those records can
supply it and the report marks it **UNRUN on GPU** rather than carrying the old
verdict forward. Closing that needs one fresh dedicated allocation.

The per-schedule native claim is a different case, and the previous revision of
this document got it wrong. Each schedule's own `backend_evidence` in those
records already carries a per-movie kernel stage marker written by the CUDA
code path into that schedule's own output directory, so the claim is
**measured, and the report now publishes it as PASS for all 23 payload rows**.
What `7ba584e` did not keep is the startup banner of every non-final invocation
— the weaker, redundant witness — and that gap is disclosed per cell as
`banner K/N` rather than used to withhold the rows. The withholding was a
defect in this repository's renderer, not a property of the records; see W8a in
`withdrawals.md`.

**Every new gate has a negative control, and every control has a meta-check.**
A control that passes with its gate reverted is testing nothing, so each gate
is monkeypatched back to its published form at runtime and the control must
then fail — **20 such checks**: 17 reverted gates plus three on the suite's own
exit status, which itself used to be computed by quantifying over a set that
was empty when every control skipped.

> **Corrected.** For two rounds these meta-checks lived in an untracked
> `.scratch/meta_rev1.py`, so "thirteen meta-checks pass" was the one claim in
> these documents anchored to a file that was not in the repository and whose
> output appeared in no job log — the shape of evidence this issue exists to
> refuse. They are now `tools/validation_issue83/meta_controls.py`, committed,
> re-runnable, and writing a `--json` record preserved alongside the control
> suite's. The same applied to the report recipe, now
> `tools/validation_issue83/regenerate_report.sh`. The count rose from 13 to 20
> because this round's gates got meta-checks too.

## Runs of record

These are the records `report.py` is actually invoked on
(`tools/validation_issue83/regenerate_report.sh` passes six JSON records drawn
from these four runs — matrix, truth and fixture-verify all come from
3511154). They are **not** one run,
and the report says so section by section:

| Section of the report | Host | Commit | Record |
|---|---|---|---|
| Declared matrix, input provenance, motion truth | SCARF `gn3000` (exclusive) | `7ba584e` | job **3511154**, `raw/scarf-gn3000-3511154/` |
| Integrated all-24 screen | SCARF `gn3000` (exclusive) | `7ba584e` | job **3511139**, `raw/scarf-gn3000-3511139/` |
| Capacity datapoint | SCARF `gn0005` (exclusive) | `0a6dbff` | job 3510288, `raw/scarf-gn0005/capacity.json` |
| CPU matrix (diagnostic) | cpu64, `taskset -c 32-63 numactl --membind=1` | `4c2305b` | `raw/cpu64-4c2305b/matrix.json` |
| Gate contracts, controls, CPU pixels | cpu64, `taskset -c 32-63 numactl --membind=1` | `4c2305b` | `raw/cpu64-4c2305b/` |

The CPU diagnostic section previously came from `raw/cpu64/matrix-cpu-summary.json`
at `bab9f46`, pinned `taskset -c 56-63`. That record predates the per-schedule
witness and the delimited rejection matcher, so it is no longer the source; it
stays on disk unedited. The replacement is the head-commit run, which reaches
the same counts (24 pass, 0 fail, 0 error, `realscale_local` unrun) under the
current contracts.

> **Corrected.** This table previously named jobs 3510290 and 3510288 at
> `d48d875` as the runs of record, and the paragraph under it said the matrix
> and all-24 legs came from one harness revision so that "one published table
> should come from one harness revision". Neither is true of the report as
> published: that superseded gn0005 run was replaced by the two `gn3000` jobs
> above, and the matrix and all-24 sections come from two *different* jobs.
> **A second correction on top of that one:** the superseded gn0005 records
> preserved under `raw/scarf-gn0005/` are not 3510290's at `d48d875` either.
> The preserved log is `job-3510297.log`, header commit `f51b45f`, and the
> summaries fall inside its window. No record for 3510290 exists under `raw/`.
> Rather than
> re-assert a single-revision claim the evidence does not support, the report
> now labels each section with its own source record and flags the ones outside
> the provenance block's run window. The same correction applies to the
> sentence in `provenance.md` under "Exact commands".

Superseded runs, preserved and not carried into the report: 3510276
(output-path bug), 3510277 (quota/SIGPIPE), 3510283 (`realscale_local`
declaration drift, since fixed), 3510297 (pre-correction harness, at
`f51b45f` — the run whose verdicts are preserved in `raw/scarf-gn0005/`),
3510290 (no record preserved), 3511145
(cancelled; started from a dirty tree), the first cpu64 matrix (harness
expectations 2 and 3), and `raw/cpu64/matrix-cpu-summary.json` (pre-contract
harness, replaced by the head-commit CPU run).
