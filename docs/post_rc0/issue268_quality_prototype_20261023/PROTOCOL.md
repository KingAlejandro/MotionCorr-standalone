# #268 quality-report prototype — frozen controls and expected outcomes

Frozen before any native run of prototype code. Design: `DESIGN.md`.
Every row below is UNRUN until a retained record shows otherwise. A failed row
is retained as FAIL; it is not retried in place or repaired by changing an
expectation, gate or tolerance.

## Inputs

The committed generator `test-data/generate_motion_diagnostics.py`
(schema `motion-diagnostics/2`) regenerates 128×96×5 fixtures whose four files
per case must equal `test-data/motion_diagnostics_v2/GENERATION_RECORD.json`
byte-for-byte (checked before any run; a mismatch stops the campaign). Cases
used: `zero`, `integer`, `fractional`, `affine`, `flat`, `noisy`. Fixtures are
read-only; each run gets its own copy in `in/` so all relative paths match.

Common argv (from the #273 run contract, `--j 1`): `--use_own --j 1
--bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1
--last_frame_sum 5 --skip_logfile`, plus the listed patch grid. Thread
environment `OMP_NUM_THREADS=1`.

## Binaries (CPU Release; same compiler/flags per venue)

| Id | Source | CMake |
| --- | --- | --- |
| B0 | C1 base `bbf24607` (production source = `e77a51a2`) | default |
| B1 | experiment head | default (option OFF) |
| B2 | experiment head | `-DMOTIONCORR_EXPERIMENTAL_QUALITY_REPORT=ON` |
| B3 | experiment head | option ON + `-DCUDA=ON`, compile only, never executed |

## Comparison rule ("products identical")

Per movie: STAR bytes identical; MRC (`.mrc`, `_noDW.mrc`) header identical
except the MRC creation timestamp bytes, and voxel data identical; joint
`corrected_micrographs.star` identical; the same set of product files exists,
ignoring `*.quality*.json`, `quality_summary*.json`, PDF/EPS (dates) and logs
(wall time). Exit status identical. All runs use the same relative paths.

## Native processes (remote, at most 16; this manifest has 12, 14 after A1)

| P | Binary | Input batch / patches | Extra | Purpose |
| --- | --- | --- | --- | --- |
| P1 | B0 | batch6, 3×3 | — | C1 reference |
| P2 | B1 | batch6, 3×3 | — | default build neutrality vs P1 |
| P3 | B2 | batch6, 3×3 | — | runtime-off neutrality vs P1 |
| P4 | B2 | batch6, 3×3 | flag | report-on vs P1 |
| P5 | B0 | affine, 3×3 | `--max_iter 1` | forced-limit reference |
| P6 | B2 | affine, 3×3 | `--max_iter 1`, flag | forced limit, local drops |
| P7 | B0 | zero+integer, 1×1 | integer `.mrc` path pre-created as a directory | write-failure reference |
| P8 | B2 | zero+integer, 1×1 | same + flag | write failure reported |
| P9 | B2 | batch6, 3×3 | flag; `flat.quality.json` pre-created as a directory | sidecar write failure |
| P10 | B2 | batch6, 3×3 | flag; `quality_summary.json` pre-created as a directory | aggregate write failure |
| P11 | B2 | batch6, 3×3, `--only_do_unfinished` | flag; prepared resume tree (below) | old/missing/stale sidecar resume |
| P12 | B0 | same prepared tree without sidecars | `--only_do_unfinished` | resume reference |

batch6 = zero, integer, fractional, affine, flat, noisy in one movies STAR.
`--max_iter 1` is an existing production option; it is a forced iteration-limit
fixture and is not evidence about the default five-iteration case.

Prepared resume tree (copies, never originals): zero and integer from P1 (no
sidecars → `sidecar_missing`); fractional and noisy from P4 with sidecars
(`resumed_sidecar`); affine from P4 with its sidecar's recorded STAR SHA-256
altered (`sidecar_stale`); flat from P4 with its STAR removed (incomplete →
reprocessed, `this_run`).

## Frozen expected outcomes

E1. P2 and P3 products identical to P1; P3 writes no quality file. [default-off]

E2. P4 products identical to P1, exit 0, six sidecars + one aggregate.
For every movie: global `iterations` equals the number of global
` Iteration k: RMSD` lines in its log; `final_incremental_rmsd_px` matches the
last logged global RMSD to the log's printed precision; `state` is `converged`
iff that RMSD < 0.5 and otherwise `iteration_limit` with iterations = 5.
Per patch: attempts/iterations/final RMSD agree the same way with the patch
section; `converged_patches + dropped_patches = 9`; CPU `same_input_retries=0`.
`local_model` is `retained` iff the STAR has a local model block, otherwise
`global_only` with a reason consistent with the observation count.
All movies `published`; `motion_identifiability` and `peak_validity` are
`not_assessed` for all, including `flat`; aggregate counts equal the sidecars,
`quality_evidence_complete=true`, `joint_output=published`.
Prediction only (from #273 CPU at `d751ff28`, not a pass criterion): zero
`converged`; integer, fractional and noisy `iteration_limit`; affine, flat
`converged`. A difference from the prediction is reported, not a failure,
provided the report matches the solver as above.

E3. P6 products identical to P5; global `iteration_limit` with iterations=1
(forced); patch counts match the log; if fewer than 4 patches converge,
`local_model=global_only`, reason `too_few_converged_observations`.

E4. P8 exit equals P7 exit (non-zero); retained products identical; zero
`published`, integer `failed` / `product_write_failed`; aggregate
`joint_output=withheld_movie_failures`; P7/P8 `local_alignment` and
`local_model` are `not_requested` (1×1).

E5. P9 products and exit identical to P1/P4; `flat` sidecar absent; aggregate
lists the flat write failure and `quality_evidence_complete=false`; other five
sidecars equal P4's apart from run id and identity fields.

E6. P10 products and exit identical to P1; six sidecars written; no regular
aggregate file; a stderr warning names the aggregate path.

E7. P11 and P12 exit 0 with identical joint STAR and identical flat products
(flat reprocessed in both). P11 aggregate: zero, integer `unknown_legacy`
`sidecar_missing`; affine `unknown_legacy` `sidecar_stale`; fractional, noisy
`resumed_sidecar`; flat `this_run`; `quality_evidence_complete=false`.

## Amendment A1 (before any remote evidence run)

A local Mac development run of P1–P12 (not evidence) showed that P6 retains
the local model (5/9 patches converge in one iteration), so E3 does not reach
the too-few-observations fallback. A local probe with the unmodified base binary
showed `integer`, 3×3, `--max_iter 1` prints "too few valid local
trajectories". Added rows, raising the manifest to 14 processes:

| P | Binary | Input / patches | Extra | Purpose |
| --- | --- | --- | --- | --- |
| P13 | B0 | integer, 3×3 | `--max_iter 1` | reference |
| P14 | B2 | integer, 3×3 | `--max_iter 1`, flag | too-few fallback reported |

E8. P14 products and exit identical to P13; global `iteration_limit`,
iterations=1 (forced); `local_model=global_only`, reason
`too_few_converged_observations`, observations ≤ 18; the STAR has no local
model block; patch counts match the log.

## Amendment A2 (before any remote evidence run)

A second local development run failed E5 only because the five sidecars'
`products.micrograph.sha256` differed from P4's: the MRC header's first label
holds the write time, which the product comparison already masks. The sidecar
binds the exact file bytes, which is intended. E5 now compares P9 and P4
sidecars excluding identity and the two product SHA-256 values, and separately
requires every P9 sidecar to bind P9's own STAR, micrograph and movie bytes.

## Checker negative controls (no native process)

The checker must reject each of these copies of P4 output: (N1) integer global
state rewritten to `converged`; (N2) one voxel byte flipped in a copy of
`fractional.mrc`; (N3) flat `motion_identifiability` set to `identifiable`;
(N4) P8's integer publication rewritten to `published`; (N5) one patch's
iteration count incremented.

## Rows that stay UNRUN in this task

All CUDA execution (global resident/host-staged, batched, per-patch device,
same-input retry, device-preparation decline); retained e10216-01; distortion
guard and fit-RMSD fallback reasons unless a listed run happens to produce them;
dataset/multi-GPU aggregation; tomography; `--aggregate_only`; timing.

## Resources

Remote 4GPUs CPU only: cores 14–15 (NUMA0), one numeric thread per process
(`taskset -c 14`), builds `-j2` under the shared nonblocking
`/tmp/motioncorr-build.lock` plus a dedicated CPU lease, fresh scratch under
`/mnt/clathrin` capped at 8 GiB. Admission requires the old guard wrapper
3315461 / chain 3315463 to have no live compute. No GPU process, no
`nvidia-smi`. Local Mac runs are development checks on one thread and are not
part of this evidence manifest.
