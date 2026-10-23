# #268 quality-report prototype — design note (experimental, unapproved)

Branch `experiment/268-quality-report-20261023`, base C1 docs head
`bbf24607dec537bd13351f061047ea38bd38237b` (production source identical to
`e77a51a2`). The maintainer selected "Report quality; preserve publication"
as the next M4 draft prototype. This is not M4 adoption, not an approved public
schema and not a production policy. It is off C1 and off `main`.

## What it does

One default-OFF observation report. When enabled, each processed movie gets a
versioned sidecar and the run gets one quality aggregate. Nothing else changes:
correction, trajectory, STAR/MRC/EPS products, per-movie log, exit status,
the existing same-input CUDA local retry, global-only fallback, writer
ordering, joint-STAR membership and resume completion are untouched. There is
no refusal, no new retry, no M5 peak policy and no new RELION STAR label.

## Opt-in

Two independent switches, both off by default:

1. CMake `-DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON` defines
   `MC_EXPERIMENTAL_QUALITY_REPORT`. Without it every hook is preprocessed
   out and the flag below does not exist (the parser rejects it as unknown).
2. Runtime `--experimental_quality_report` in an ON build. Without it the
   solver hooks see a null capture pointer and record nothing.

`--experimental_quality_report` is rejected with `--aggregate_only` and with
the external MotionCor2 route, which this prototype does not observe.

## Where values come from

All convergence values come from the solvers themselves through a thread-local
capture that the runner installs around each call; nothing is parsed from logs.

| Route | Source of iterations / final incremental RMSD / converged |
| --- | --- |
| CPU global and patch (`alignPatch`) | hook at the end of the CPU iteration loop |
| CUDA global resident / host-staged, CUDA per-patch device, CUDA host-staged patch retry | hook at the end of `cudaAlignPatchDeviceWithWorkspace` (shared core) |
| CUDA batched resident patches | existing `PatchBatchLog` (`rmsd` vector, `converged`) produced by the solver loop |

If a solver returns without running (CUDA wrapper with zero frames returns
`true`; `--max_iter 0`), no record is made and the state is `not_run`; the
returned `bool` is kept separately as `solver_returned`.

## Per-movie sidecar `<output root>.quality.json`

Schema `motioncorr-quality-prototype/0`. Fields (names are prototype names):

- `global_alignment.state`: `converged` | `iteration_limit` | `not_run` |
  `operator_error` (exception between the start of global alignment and the
  solver's return) | `not_assessed` (movie failed before global alignment).
  Plus `route` (`cpu`, `cuda_resident`, `cuda_streaming`), `iterations`,
  `max_iter`, `tolerance_px` (the unchanged 0.5), `final_incremental_rmsd_px`,
  `solver_returned`.
- `local_alignment`: `state` (`attempted` | `not_requested` | `not_assessed`),
  `patches_planned`, `solver_attempts`, `same_input_retries`,
  `device_preparation_declined`, `converged_patches`, `dropped_patches`, and a
  per-patch list of actual attempts (`route` = `cpu` | `cuda_batched` |
  `cuda_resident_patch` | `cuda_host_staged`, `kind` = `first` |
  `same_input_retry`, iterations, final RMSD, converged).
- `local_model.state`: `retained` | `global_only` | `not_requested` |
  `not_assessed`, with `reason` `too_few_converged_observations`
  (observations vs the existing `> 18` requirement), `distortion_guard_rejected`
  (largest delta vs the existing 3 px), or `fit_rmsd_above_threshold`
  (fit RMSD vs the existing fixed 10 px).
- `motion_identifiability`: always `not_assessed`. `peak_validity`: always
  `not_assessed`. Convergence never implies either; flat or boundary inputs that
  converge stay `not_assessed`.
- `publication.state`: `published` | `failed`, reason `movie_error` or
  `product_write_failed`, decided after the writer has drained.
- Identity/binding: run id, configured source revision and dirty flag,
  `/proc/self/exe` SHA-256 (or `unavailable`), backend/GPU id, alignment options,
  argv; input movie path, size and SHA-256; published STAR and micrograph path
  and SHA-256 (null when not published).

## Aggregate `<output>/quality_summary.json`

Schema `motioncorr-quality-summary-prototype/0`. One entry per joint-membership
movie (`fn_ori_micrographs`), in input order, with `source`:
`this_run`, `resumed_sidecar` (valid prior sidecar), or `unknown_legacy` with
reason `sidecar_missing` | `sidecar_invalid` | `sidecar_stale`. Counts by global
state, local-model state and publication state; `report_write_failures`;
`quality_evidence_complete` (false if any entry is `unknown_legacy` or any
sidecar write failed); `joint_output.state` = `published` |
`withheld_movie_failures` | `failed`.

## Write, staleness and resume behaviour

- Writes are atomic: temporary file in the same directory, checked close,
  `rename`. A failed write removes its temporary file.
- At movie start, an existing regular-file sidecar for a movie about to be
  reprocessed is renamed to `<root>.quality.superseded-<run_id>.json`; at run
  start an existing regular-file aggregate is renamed likewise. Nothing is
  deleted. A crash therefore leaves no current sidecar/aggregate rather than a
  stale one. Non-regular paths are left alone (and the later write then fails).
- Sidecars are written after the final writer drain, when the real publication
  outcome is known; then the aggregate. On movie failures the aggregate is
  written before the existing job error; when joint generation throws, the
  aggregate records `failed` before the exception is rethrown.
- A sidecar or aggregate write failure prints a warning on stderr, is recorded
  in the aggregate where possible, and never changes products or exit status.
- Resume (`--only_do_unfinished`): for a skipped complete movie the sidecar is
  accepted only if schema, movie path and size match, publication is
  `published`, and the current STAR and micrograph SHA-256 equal the recorded
  ones. Otherwise the entry is `unknown_legacy` with its reason. Resume
  completion and joint membership are decided exactly as before.

## Not implemented / limits

- CUDA hooks are source-wired only; every CUDA row is UNRUN in this task.
- Multi-GPU/dataset tooling does not read sidecars; dataset-level aggregation is
  not implemented. Tomography and `--aggregate_only` are not covered.
- Identifiability and peak validity are not assessed (M5 and W4 own them).
- Hashing the input movie and products costs time proportional to file size
  when the flag is on.

## Correction (23 October 2026)

"the parser rejects it as unknown" above is false. MotionCorr's argument parser
only warns about unknown options: an OFF build given
`--experimental_quality_report` prints `WARNING: Option
--experimental_quality_report is not a valid RELION argument` on stderr,
processes the movies normally and writes no quality files. This was found in a
local development run of the v2 harness (`/tmp/q268v2-dev1`, Q16) and is
unchanged by design: the parser's behaviour is production behaviour.
