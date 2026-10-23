# #268 quality-report prototype v2 — current state

Hardened after review R1. Still experimental, default-OFF and observation-only;
not M4 adoption or an approved schema; off C1 and `main`. `README.md`,
`evidence-c347f59f-4gpus/` and `evidence_c347f59f/` describe `c347f59f` only and
are unchanged. Design `DESIGN_V2.md`; frozen controls `PROTOCOL_V2.md` (with
amendment A1, recorded before the remote run).

Commits: protocol `a95d7edd` (+ correction wording `798e8d5a`), source
`1215febd`, harness/doc corrections `2f434253` (no `src`/`CMakeLists.txt`
change since `1215febd`; `receipts/source_diff_vs_1215febd.txt` is empty).
Tested head `2f434253`, tree `0de56473`.

## Result (4GPUs, CPU 14–15, `2f434253`)

| Row | Verdict | Shows |
| --- | --- | --- |
| R1 off-by-default | PASS | OFF build and ON build without flag: products and logs equal C1 V0; no quality file |
| R2 report-on | PASS | products and logs equal V0; strengthened sidecar and summary checks pass for all six movies |
| R3 duplicate + shared root | PASS | 4 summary entries for 4 membership rows; all `output_root_collision`, `ambiguous_output_root`, no sidecar; evidence incomplete; products, logs, joint STAR equal V0 |
| R4 encoding | PASS | non-UTF-8 movie path written as `{"non_utf8_bytes_hex": "696e2f7a65726fe92e6d726373"}` (bytes equal the file name); UTF-8 `in/zéro.mrcs` kept as a string; strict UTF-8 JSON; products equal V0 |
| R5 strict resume | PASS | BOGUS state, identifiable claim, missing global block, string `bytes`, `peak_validity: valid` → `sidecar_invalid`; untouched flat → `resumed_sidecar`; no per-movie file changed; joint STAR equals V0 resume |
| R6 product write failure | PASS | exits 1/1; integer `failed`/`product_write_failed`; joint withheld; products and logs equal V0 |
| R7 sidecar write failure | PASS | exit 0, products equal V0, failure recorded, evidence incomplete |
| R8 too-few fallback | PASS | `global_only`/`too_few_converged_observations`, `min_observations_exclusive` 18 from the production local, unreached limits null |
| R9 OFF build given the flag | PASS | exit 0, stderr warning names the option, products and logs equal V0, no quality file (amendment A1) |
| R10 temporary files | PASS | no `*.tmp.*` in any of the 16 run trees |
| PC + NC1–NC12 | PASS | untouched copy accepted; each targeted tamper (identity hash, argv, summary sidecar hash, summary count, attempts, patch relabel, observations, fit RMSD, movie bytes, collision relabel, encoded-path hex, resume relabel) rejected |
| QualityReportUnit (U1–U4) | PASS | interrupted patch, encoding, 18 resume checks, null-for-unknown. Which U2 branch ran on Linux is not recorded: CTest kept only pass/fail and `LastTest.log` was overwritten by the later `ctest --show-only` collection check. On macOS the name cannot be created, so only the validation branch ran there |

CTest (cores 14–15, `-j1`): V1 (OFF) 90 collected, 89 passed, 1 skipped
(`CompressedMrcStatus_bz2`, environment skip), 0 failed; V2 (ON) 92 collected =
V1's 90 + `QualityReportCheckerSelftest` + `QualityReportUnit`, 91 passed, same
1 skipped, 0 failed. `validate_test_collection.py` PASS on both. CUDA option
OFF (V3) and ON (V4) compiled (`--target motioncorr`), never executed.

## Response to review R1

- **F1** fixed: one entry per membership occurrence; colliding roots are
  ambiguous, unbound, and mark evidence incomplete. Production overwrite
  behaviour is unchanged (R3).
- **F2** fixed: strict schema/type/vocabulary/invariant validation before any
  resumed content is used (R5, U3). `/0` sidecars are `sidecar_invalid`.
- **F3** fixed: labelled hex-bytes object for ill-formed UTF-8 (R4, U2).
- **F4** fixed in the serializer (`interrupted`, U1). The runner hook is
  source-only: no native trigger exists, so it is UNRUN on every route.
- **F5** fixed where narrow: limits are copied from the production locals and
  the fit-RMSD test is no longer restated; identity no longer lists constant
  tolerance/search range. Not bound: the batched CUDA tolerance (now null) and
  the search range (not observed). `largest_delta_px` stops at the first
  offending frame, as production does.
- **F6** fixed: unknown values are null (U4).
- **F7** documented: dated correction in `PROTOCOL.md`; v1 design sentence about
  flag rejection corrected in `DESIGN.md` (it was false: the parser only warns).
  `006d8bc2` is a second summary-only commit of the same `c347f59f` campaign,
  made during the interrupted session; it is kept as is. Lost development check
  outputs are described, not reconstructed.

## Identities

Binaries: V0 `97f44b8a…a1`, V1 `625ac268…4a`, V2 `9a9f1bfa…25`, unit
`51c77943…19`, V3 `4102738d…b2`, V4 `c112a1b9…0d` (`receipts/binaries.txt`).
Static witness: V0/V1 contain neither the flag string nor `mcquality::`
symbols, V2 does; the command is recorded in the receipt. Every sidecar's
`binary_sha256` equals V2 and its revision equals `2f434253` (`dirty` false).
Driver and bundle hashes match `launch_inputs.sha256`. Driver PID 3333420,
lease `/tmp/motioncorr-q268v2-cpu14-15.lock`, admission receipt shows the old
q268 lock and guard/old-driver PIDs absent or unheld. Scratch
`/mnt/clathrin/alex-motioncorr-q268v2-20261023-2f434253` (684 MiB, retained).

Retained files: 226 campaign files plus 5 non-UTF-8-named files in
`nonutf8_named_files.tar.gz` (macOS cannot store those names) match
`receipts/campaign_files.sha256` (1113 entries; MRC/EPS/PDF and inputs are
hash-only).

Counts: 16 campaign MotionCorr invocations (Q1–Q16). CTest ran 90 + 92 tests;
the MotionCorr processes those tests start were not counted.

## Limits / UNRUN

All CUDA execution; native interrupted-patch trigger; summary write failure
on v2 (atomic write path unchanged, not rerun); distortion-guard and fit-RMSD
fallback reasons; e10216-01; dataset/multi-GPU aggregation; tomography;
timing. Identifiability and peak validity remain `not_assessed`. Convergence
is not accuracy; #273 totals are untouched.

## Independent R2 publication review

Fresh Codex 6.1 Sol R2 at `e9c1e9b4` found no blocker for **draft publication
only**, with two remaining source/data-trace limitations. The full report and
its whitelisted controls are retained in `review/r2/`; this paragraph changes
no source or result and does not claim a new native run.

- Resume validation covers the named R5/U3 cases, but is not full schema or
  solver-invariant validation. A sidecar changed from `iteration_limit` to
  `converged` can still be accepted while its boolean/RMSD fields contradict
  that state. Unexamined identity/patch fields are also not comprehensively
  validated. The review did not execute that C++ reader probe.
- Collision detection covers equal generated-root strings. Filesystem aliases
  such as `in/zero.mrcs` and `in//zero.mrcs`, or pre-existing directory symlinks,
  can evade detection and yield stale summary bindings. The alias scenario is
  source/path-data evidence; native alias execution is UNRUN.

Thus the F1/F2 responses above mean the specifically tested cases are fixed,
not that arbitrary collision or resumed-report corruption is excluded. The
frozen checker also does not exhaustively validate every report field; R2
independently checked the retained solver fields and found no disagreement.

R2 independently verified 231 retained members (226 ordinary plus five raw-name
tar members), 16 current sidecars/108 patches/seven summaries and 37 log pairs,
and reproduced the positive/12 negative data controls. Absent native binaries,
raw input/MRC products and the launch bundle were reconciled by recorded hashes,
not rehashed or executed. Full CUDA runtime, wider re-entry qualification,
scientific accuracy and M4/schema adoption remain outside this review verdict.
