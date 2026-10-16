# Dataset-run report overhead

Two changes to the dataset-ready publication path, measured end to end with
`tools/multi_gpu/run_dataset.py` (`dataset_wall_s` = launch to
`merged/corrected_micrographs.star` + `merged/logfile.pdf`).

1. `035d9b5a` — the per-worker joint report is discarded by the aggregate, so
   the launcher now passes `--skip_logfile` to every worker by default
   (`--worker-joint-report` restores it).
2. `a3f9049f` — in aggregate mode `logfile.pdf` is rendered once from the EPS
   alongside the batch pass, instead of being produced by a second Ghostscript
   `pdfwrite` re-render of `header.pdf` + `all_batches.pdf`. The incremental
   path still concatenates, because there `all_batches.pdf` can carry earlier
   batches whose EPS the current run does not hold.

Both arms differ only in the binary; the launcher is held constant.

## Result — SCARF gn0005, exclusive allocation

Primary venue. `aggrep.out` / `aggrep.json`, 40 runs, 5 paired reps with
per-rep arm rotation and a discarded warm-up per arm.

| cfg | base_med | cand_med | saving | pct | agg base | agg cand |
|---|---|---|---|---|---|---|
| 1x8-24 | 6.368 | 5.995 | +0.374 | 5.9% | 0.970 | 0.555 |
| 1x8-96 | 20.944 | 19.637 | +1.307 | 6.2% | 2.739 | 1.388 |
| 4x8-24 | 5.026 | 4.612 | +0.414 | 8.2% | 0.991 | 0.576 |
| 4x8-96 | 9.950 | 8.682 | +1.268 | 12.7% | 2.775 | 1.423 |

`all_pass=True arm_witness_consistent=True intermediate_pdfs_present=True`.
Seconds, median of 5. The aggregate phase roughly halves in every
configuration and the dataset-wall saving tracks it; worker-phase medians move
by under 0.2 s, so the saving is the report change.

Arm witness: `merged/logfile.pdf.lst` exists only in the candidate, because
only the candidate renders `logfile.pdf` from an EPS list. It was `True` for
every candidate run and `False` for every base run.

## Second venue — 4GPUs

`4gpus-aggrep.out`, same protocol, 40 runs. Same direction, larger spread: the
box is shared and the per-rep values are visibly noisier than SCARF's.

| cfg | base_med | cand_med | saving | pct |
|---|---|---|---|---|
| 1x8-24 | 8.045 | 7.384 | +0.662 | 8.2% |
| 1x8-96 | 24.213 | 24.078 | +0.136 | 0.6% |
| 4x8-24 | 5.178 | 4.972 | +0.206 | 4.0% |
| 4x8-96 | 12.094 | 11.252 | +0.842 | 7.0% |

The two venues are not comparable in absolute terms: SCARF has THP `always`,
4GPUs has THP `madvise`, which alone is worth about 40x on frame allocation.

## Correctness

`aggorc3.out` / `aggorc3.json` (SCARF, three fresh 1x8/24 runs: base, base,
cand). Products are expected to be untouched; the artifact that actually
changes is `logfile.pdf`, which `compare_output_trees.py` skips by design
(`SKIP_SUFFIXES` contains `.pdf`). So the discriminating comparator is a
page-for-page r100 PNG raster, calibrated before the treatment was read.

Product oracle (MRC header+extended+payload, per-movie STAR, joint STAR):

```
null-base-vs-base      PASS
treat-base-vs-cand     PASS
ctl-mrc-payload-flip   FAIL  ['Movies/20170629_00021_frameImage.mrc']
```

Raster, 30 pages (6 header + 24 shifts):

| comparison | pages | differing |
|---|---|---|
| logfile null base-vs-base | 30 | 0 |
| logfile treat base-vs-cand | 30 | 0 |
| header treat | 6 | 0 |
| batch treat | 24 | 0 |
| c0 unperturbed | 30 | 0 |
| c1 page content swapped | 30 | 1 |
| c2 page dropped | 29 vs 30 | page count |
| c3 pages reordered | 30 | 2 |
| c4 header omitted | 24 vs 30 | page count |

The four perturbation controls are rebuilt from the base run's own EPS, so the
comparator is shown to see a swapped page, a dropped page, a reorder and a
missing header block before `treat=0` is read.

Whole-tree attribution against a base-vs-base null set leaves five paths:
three per-movie `.log` files, plus `logfile.pdf` and `logfile.pdf.lst`. The
`.log` differences are `Total GPU alignment time:` text and appear identically
in the null comparison. `logfile.pdf` differs at byte level because a different
Ghostscript invocation writes different PDF object bytes for the same
rendering — which is exactly what the raster separates. `logfile.pdf.lst` is
the new argument file; `src/motioncorr_runner.cpp:844` already protected that
name unconditionally, and aggregate publication enumerates the staging
directory, so neither needed a change.

### A trap in the first two oracle attempts

`aggorc.out` (retained, superseded): the raster reported `null=24/30` and
`treat=24/30`, i.e. it could not discriminate. Each shifts EPS embeds its own
absolute output path and that path is drawn into the plot, so two base runs in
different directories already differ on all 24 shift pages. `aggorc2.out`
(retained, superseded) fixed it by writing every arm to one identical path and
relocating afterwards — but the relocation left the joint STAR pointing at the
as-run path, which `compare_output_trees.py` rejects. `aggorc3.py` rewrites
`.star` and `.lst` after the move and leaves the EPS alone, so both oracles are
valid in one run.

## Test suite

`ctest.out`, candidate build on gn0005: 83/84 pass, including
`MultiGpuScheduling` (which runs the `test_aggregate_only.py` controls under a
fake Ghostscript) and `PdfConcat`. `CiFailClosedControls` fails identically on
the base build: the staged source trees have no `.git`, so the fail-closed path
emits "without git metadata" instead of the string the test matches. Venue
artifact, not the change.

## Behaviour change

On an aggregate report failure the error text changes from
`Aggregate-only full PDF concatenation failed.` to
`joinMultipleEPSIntoSinglePDF`'s `Aggregate PDF generation failed: …logfile.pdf`.
Both fail closed, and `requireAggregatePdf(logfile.pdf)` still runs afterwards.

## Provenance

- base `8f6b1ea1`, candidate `a3f9049f`
- SCARF `gn0005`, `gpu-devel`, `salloc --exclusive -N1 --gres=gpu:4`, job 3585712
- THP `always`; 4x A100; Ghostscript 9.54.0; CUDA 12.8.0; `-DCMAKE_BUILD_TYPE=Release -DCUDA=ON -DUSE_NVCOMP=ON -DCMAKE_CUDA_ARCHITECTURES=80`
- `sha256(build-base/motioncorr) = 661c55a4a86de16c2c1f10b81726a034d59222898e8237125ccab7b7f3b25a56`
- `sha256(build-cand/motioncorr) = e35dd405e949a9488a075ad2eb74e1cab3f8bea8e1d46f1d32f32e8444e43f8f`
- dataset staged to node-local `/tmp` to keep PanFS out of the measurement
- lanes: 8 physical cores per worker on the GPU's own NUMA node (0-7, 8-15 on node0 for GPU0/1; 16-23, 24-31 on node1 for GPU2/3)
- workload: 24 and 96 movies, `--dose_weighting --patch_x 5 --patch_y 5 --bfactor 150 --seed 1 --j 8 --ingest nvcomp`

## Limitations

- Both venues use Ghostscript 9.54.0. A different gs version changes the
  absolute aggregate-phase cost, though not the removal of one of two renders.
- The saving is a fixed per-run cost, so its share of the dataset wall falls as
  the movie count rises and rises as the worker count rises.
- `aggorc3` covers aggregate SPA only. The incremental and tomography report
  paths are unchanged by `a3f9049f` and are covered by `ctest` alone.

## Single-process logfile.pdf from EPS

`generateLogFilePDFAndWriteStarFiles()` in the normal (non-aggregate) path made
Ghostscript re-render `header.pdf` + `all_batches.pdf` into `logfile.pdf`, pages
the process already holds as EPS. When no `all_batches.pdf` exists before this
run's report, `logfile.pdf` is exactly header EPS then this run's batch EPS, so it
is now rendered from that EPS list on a thread alongside the batch pass and the
concatenation is skipped. The existence of an earlier `all_batches.pdf` is asked
once, before any report thread starts. If one exists (`--only_do_unfinished`,
incremental runs) the concatenation is unchanged. `header.pdf`, `batch.pdf`,
`all_batches.pdf` and the `.lst` files are produced as before; `logfile.pdf.lst`
is removed after use so the output inventory does not change. Evidence and
scripts: `single_process_logfile/`.

Venue: 4GPUs, A100 GPU0 (`GPU-eddb42fe`), `taskset -c 96-103`, bench flock, THP
`madvise`, Ghostscript 10.02.1, Release CUDA+nvCOMP build of both arms from
scratch in one locked region. Base `116eb04a` (`sha256 7b0d4b4c…`), candidate
`d1bb1406` (`sha256 d82a4224…`). Box shared; settle gate waited ~11 s per run.

### Timing (measured)

Default options, `--profile`, `--j 8 --ingest nvcomp`, 5 paired reps per count,
arm order alternating by rep, discarded warm-up per arm. Medians, ms:

| movies | report task base | cand | saving | process wall base | cand | saving |
|---|---|---|---|---|---|---|
| 12 | 510 | 326 | 179 (5/5 pairs) | 3597 | 3414 | 210 (4/5 pairs) |
| 96 | 2312 | 1202 | 1117 (5/5 pairs) | 20810 | 19835 | 978 (5/5 pairs) |

Task = `--profile` thread `main/joint star and logfile pdf`. The 12-movie wall
has one outlier pair (cand 4834 ms, -1214 ms); the median ignores it. Both
savings are below the 0.5 s / 1.3 s estimate. `timing_analysis.txt`,
`timing_runs.jsonl`.

### Correctness (measured)

Both arms of a configuration wrote to the same as-run path, because each shifts
EPS draws its own path onto the page; trees were then moved and `.star`/`.lst`
rewritten (`correct.sh`).

- Products, `docs/perf_integration/identity/cmp_trees.py`, 12 movies:
  default IDENTICAL (12 mrc, 61/61 files), `--even_odd_split` IDENTICAL (36 mrc,
  85/85), CPU path with `--even_odd_split --save_noDW` IDENTICAL (48 mrc, 97/97).
  The output inventory, including `logfile.pdf.lst` being absent, is identical.
  Comparator control: a flipped MRC payload byte gives DIFFERENT (and
  eo-vs-default gives DIFFERENT on inventory).
- `logfile.pdf`: 18 pages vs 18, 0 pages differ at `gs -sDEVICE=pnggray -r50`, in
  all three configurations. Raster comparator controls built from the base run's own
  EPS lists: unperturbed IDENTICAL; one EPS dropped 18 vs 17; two swapped 2 pages
  differ; header EPS dropped 17; batch before header 18 differ.
- Incremental, 6 movies then `--only_do_unfinished` over 12: step 2 of the
  candidate made a `-sOUTPUTFILE=…/logfile.pdf` concatenation call and no EPS-list
  call, as base; step 1 used the EPS list. Pages 12 vs 12 and 24 vs 24, 0 differ;
  products IDENTICAL.
- Ghostscript failure, 2 movies: a fake `gs` that exits 1, one that sleeps 1 s then
  exits 1, and a directory named `logfile.pdf`. Exit status 0 for both arms in
  all three, products written. Differences, all in the report:
  main prints `ERROR in executing: gs -dNOPAUSE … header.pdf all_batches.pdf`
  from the concatenation; the candidate prints `ERROR in executing: gs
  -sDEVICE=pdfwrite … logfile.pdf @…logfile.pdf.lst`. At `d1bb1406` the candidate
  also left a zero-byte `logfile.pdf` (the `touch()` fallback every other report
  PDF has) and, with a directory in the way, printed `Filename::touch ERROR`.
  From `aed8004a` the normal-path render passes `placeholder_on_failure = false`,
  so like main it leaves no `logfile.pdf` (or the directory untouched) and makes
  no `touch()` attempt. Checked on macOS CPU-only builds of `116eb04a` and
  `aed8004a` with the same three fake-`gs` cases: exit 0 and products written in
  both arms; only the failing command named on stderr differs.
- `run_dataset.py`, 4 movies, one worker: both arms PASS, merged inventory and
  `logfile.pdf` pages (10 vs 10) identical. `cmp_trees` still lists four
  `merged/` files; after normalising arm name, the random `.aggregate-XXXX` suffix
  and a PID the residual difference is zero. Workers write no `logfile.pdf`. No
  timing claim.

### Tests

New `LogfileFromEps` (CPU, fake Ghostscript that logs each call and its `@list`
content): fresh run makes three calls, `logfile.pdf` from header list then batch
list, no concatenation; incremental run with a prior `all_batches.pdf` makes the
concatenation `header.pdf all_batches.pdf` and no EPS-list call; failure cases
above. Three compiled mutants of the runner each fail it (`--expect-fail`):
`always_eps` (EPS-direct although a prior `all_batches.pdf` exists), `late_guard`
(the skip decision asks `exists(all_batches.pdf)` after the batch pass wrote it),
`eps_order` (batch list before header), and from `aed8004a` `placeholder` (an
empty `logfile.pdf` left after a failed render). At `aed8004a` on macOS CPU-only,
`LogfileFromEps` and its four mutants pass.

- 4GPUs, candidate `d1bb1406`, full CUDA suite: 87/88. Failing:
  `CiFailClosedControls`.
- cpu64, `-DCUDA=OFF`: 55/56, same failure.

`CiFailClosedControls` fails with `Cannot resolve git ref … in source archive
without git metadata`: the staged trees come from `git archive`. It was not run
on base here; it is the same test and cause recorded for the SCARF run above.

### Limitations

- Pixel equality is shown on Ghostscript 10.02.1 at r50 for 12-movie tutorial
  runs. The 96-movie logfile and 24-movie report were not rastered.
- The CPU-path identity run used the CUDA binary without `--gpu` on 4GPUs
  (the tutorial movies are not on cpu64), once per arm: 273 s base, 260 s cand.
- On a failed render the console messages differ as described above; the file
  outcome matches main from `aed8004a`.
- The 4GPUs and cpu64 suite results and all timing, identity and raster evidence
  are from `d1bb1406`. `aed8004a` changes only the failure path and was checked
  on macOS CPU-only builds.
- Multi-GPU launcher workers already skip the report and the aggregate already
  renders from EPS, so the endpoint is unchanged by design.
