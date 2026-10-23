# #268 quality-report prototype — hardening v2 (responds to review R1)

Review: `/tmp/motioncorr-q268-review-r1-20261023/REVIEW_R1.md`
(SHA-256 `eb3d5ab3…28bea9b`), findings F1–F7. Base for this change: the tested
prototype `c347f59f` and its evidence head `eeb68f1f`. That evidence and
`006d8bc2` stay as they are and cover `c347f59f` only. Everything below stays
default-OFF and observation-only: products, publication, exit status,
production processing, joint membership, overwrite behaviour, STAR content,
gates and defaults are unchanged.

Schema strings become `motioncorr-quality-prototype/1` and
`motioncorr-quality-summary-prototype/1`. On resume, a `/0` sidecar is
`unknown_legacy` / `sidecar_invalid` (it lacks the v1 fields), not trusted.

## F1 — duplicate inputs and shared output roots

`initialise()` records, under the build option only, which processed index
(or none) belongs to each joint-membership occurrence. The summary has exactly
one entry per membership occurrence, in membership order; duplicates are neither
collapsed nor refused. Occurrences are grouped by output root
(`getOutputFileNames(movie)` without extension). If two or more occurrences
share a root, the products of one can overwrite another's, so no product can be
attributed:

- no per-movie sidecar is written for that root (any earlier one is superseded,
  as before);
- each such entry has `output_root_collision: true`, `publication` =
  `ambiguous_output_root`, no sidecar, and `quality_evidence_complete=false`;
- a processed occurrence keeps the global/local states its own computation
  produced (these are observations of that run, not of the surviving files);
  a skipped occurrence is `unknown_legacy` with reason `output_root_collision`.

## F2 — strict resume validation

A prior sidecar is accepted only if all of these hold; otherwise
`unknown_legacy` / `sidecar_invalid`:

- schema `motioncorr-quality-prototype/1`, status `experimental_unapproved`;
- `movie.path` (text or encoded bytes), `movie.bytes` an integer or null;
- `global_alignment.state` in {converged, iteration_limit, not_run,
  operator_error, not_assessed}; `iterations` integer or null;
- `local_alignment.state` in {attempted, interrupted, not_requested,
  not_assessed}; integer counts;
- `local_model.state` in {retained, global_only, not_requested, not_assessed}
  with a reason consistent with it (null for retained; one of the three fallback
  reasons for global_only; `patch_grid_below_3x3` for not_requested);
- `motion_identifiability` and `peak_validity` exactly `not_assessed`;
- `publication.state` in {published, failed} with a matching reason.

Only then are bindings checked; a valid sidecar that is not `published` or
whose movie/STAR/micrograph identity differs is `sidecar_stale`. Product
completion (`isMovieComplete`) is unchanged.

## F3 — text encoding

Every text value is checked for well-formed UTF-8. Valid text is written as a
JSON string (unchanged). Ill-formed text is written as the object
`{"non_utf8_bytes_hex": "<lowercase hex of the raw bytes>"}`, which is lossless
and explicitly labelled. This applies to paths, argv and error messages. Resume
decodes either form before comparing paths. No file is renamed.

## F4 — interrupted patches

A patch record is marked complete only when the existing code reaches its
converged/dropped decision. A patch left incomplete by an exception is
`final: "interrupted"` (counted in `interrupted_patches`, not in
`dropped_patches`), and `local_alignment.state` becomes `interrupted` if any
patch is interrupted or fewer patches were recorded than planned. An attempt is
recorded only after its solver returns; a thrown attempt is not invented.
No native CPU trigger is known, so this is covered by a C++ unit control on the
serializer and the runner hook is source-only on every route.

## F5 — constants bound to production values

- The local-model fallback is recorded inside the production branches; the
  fit-RMSD test is no longer restated.
- `min_observations_exclusive`, `distortion_limit_px` and `fit_rmsd_limit_px`
  are copied from the production locals (`n_params`, `MAXIMUM_TOLERANCE`,
  `fit_rmsd_threshold`) when that branch is reached, otherwise null.
- The identity `options` no longer restate `tolerance_px`/`search_range_px`.
  The CPU and per-patch/global CUDA solvers record the tolerance they used.
  The batched CUDA log carries no tolerance, so it is null there.
  The search range is not observed (limitation).
- `largest_delta_px` is the running maximum up to the first frame that exceeds
  the limit, because the production loop stops there (documented).

## F6 — unknown is null

`movie.bytes` is null if the file cannot be measured. Solver fields
(`iterations`, `max_iter`, `tolerance_px`, final RMSD, converged) are null when
no solver recorded them. `not_run` keeps the actual values the solver reported
(for example `max_iter 0`).

## F7 — documentation

`PROTOCOL.md` is kept verbatim and gets a dated correction. New controls are in
`PROTOCOL_V2.md`.
