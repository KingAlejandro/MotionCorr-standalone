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

All five known-motion fixtures were regenerated and every `.mrcs` sha256
**matched** the committed `test-data/known_motion/MANIFEST.json`. Fixtures are
generated, never committed.

## Compute

- **GPU (primary)**: dedicated SCARF Slurm allocation, `-p gpu --gres=gpu:1
  --cpus-per-task=8 --exclusive`, node `gn0005`, 4x A100-SXM4-40GB, driver
  580.178.04, nvcc 12.8.61. No allocation was ever shared: the only other job on
  this account (3510270) was on a different partition and node.
- **CPU (diagnostic)**: `cpu64` (small-refmac-machine), 64 cores, load checked
  before each launch, bounded mask via `taskset`, `--j 8`.
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
The row itself passed -- 2/2 movies exact under repeat, batch and non-prefix
resume, native CUDA witnessed, `declaration_drift` null.

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

## Runs of record

| Leg | Host | Commit | Outputs |
|---|---|---|---|
| GPU matrix + all-24 + report | SCARF `gn0005` (exclusive) | `d48d875` | job 3510290, `evidence4/` |
| Capacity datapoint + realscale row | SCARF `gn0005` (exclusive) | `0a6dbff` | job 3510288, `evidence3/capacity.json` |
| CPU matrix (diagnostic) | cpu64, `taskset -c 56-63` | `bab9f46` | `evidence3/matrix-cpu/` |

The GPU matrix and all-24 legs were re-run in full at `d48d875` rather than
splicing the corrected `realscale_local` row into the earlier `bab9f46` report:
one published table should come from one harness revision, and the rerun costs
about ten minutes on an already-allocated exclusive node.

Superseded runs: 3510276 (output-path bug), 3510277 (quota/SIGPIPE), 3510283
(`realscale_local` declaration drift, since fixed), and the first cpu64 matrix
(harness expectations 2 and 3). Their verdicts are not carried into the report.
