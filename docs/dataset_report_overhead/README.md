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
