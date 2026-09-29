# Compact uint16 ingest: support matrix

Sixteen declared configurations of the Issue #85 lane C compact uint16 TIFF
ingest execute natively, produce the complete set of products each one asked
for, and reproduce a float32 reference byte for byte. This is same-backend
equality on one device. It is not CPU/CUDA agreement, not motion truth, and not
scientific validation; PR65's Stage B remains INCONCLUSIVE and the noisy-truth
failures remain failures.

Everything below is executed. Rows that were not run are listed as unrun in
[Not covered](#not-covered) and are not counted anywhere as passes.

## How a row passes

A row has to satisfy three independent things, because none of them implies the
others.

**Native stage.** Each movie's own `.log` must contain `Released native uint16
host staging after device forward FFT.` (`motioncorr_runner.cpp:1541`). That
line is reachable only when `stage_u16` is still true at `:2041`, which requires
that the staging buffer was allocated, every frame was uploaded as uint16,
`convertGainAndAccumulateU16Kernel` ran, and `computeGlobalForwardFFT` returned.
The earlier line `Staging this movie as native unsigned 16-bit` (`:1472`) is
recorded but never accepted as proof: it is printed before `CudaMovieSession` is
constructed at `:1584`, so a run whose `initialize()` fails prints it and then
falls back to the host. The row additionally requires `Movie FFT: batch=1`, a
resident reconstruction profile, and the **absence** of both
`Materialized native uint16 frames as float for CPU fallback.` and
`No resident CUDA session; widening the native uint16 movie to float.`

**Physical device.** No production code prints a GPU UUID — every identity it
emits is a runtime ordinal, which `CUDA_VISIBLE_DEVICES` and `nvidia-smi` order
independently. The harness therefore pins the process with
`CUDA_VISIBLE_DEVICES=GPU-<uuid>`, samples
`nvidia-smi --query-compute-apps=pid,gpu_uuid` at 0.12 s while the arm runs, and
requires the arm's own PID to be seen against that UUID and no other. An arm
that is never witnessed fails.

**Products.** Each arm is validated independently against a manifest that
declares the complete expected product set per movie, each product's own
geometry, the acquisition tags its `data_general` block must carry, its optics
group, and the joint-STAR tag that must point at each auxiliary image. Full
finite mode-2 payloads, normalized complete 1024-byte headers, extended headers,
and complete STAR content are compared. Then the two arms are compared.

The paired reference is a **float32 TIFF twin** carrying identical sample values.
`uint16 -> float32` is exact, and the sample format is the last conjunct of the
eligibility predicate at `motioncorr_runner.cpp:1467-1469`, so the twin is the
same computation reached by the other ingest path. Its own witness assertion —
the compact path must **not** be selected — is the paired negative control for
the native-stage check.

## Runs of record

| | Run of record | Second venue |
|---|---|---|
| Host | SCARF `gn0001`, Slurm **3514082** | `4-gpu-vm` |
| Allocation | `-p gpu --gres=gpu:1 --cpus-per-task=8 --mem=48G`; CPU mask 1,2,4,5,33,34,36,37 | `taskset -c 0-7`, no other compute app on the device |
| Device | `GPU-319bf3ef-abbc-f7d3-b57d-ee73fe0bff36`, A100-SXM4-40GB, the only GPU visible to the cgroup, idle before and after | `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, A100 80GB PCIe |
| Binary | `21a07802e8ca98738a4889e26750a04e109da883cafab1a1998930ab1f1f01c5`, built by Slurm 3514047, Release, CUDA 12.8.61, `sm_80` | `159e675a3186487c8b159a44f65a2b05b0ab25c9523c7a065b56f09f810409ce` |
| Result | **16/16 rows PASS, 28/28 arms UUID-witnessed, 38 products graded** | 16/16 PASS, 28/28 witnessed, 38 products |

Harness identity in both runs, matching the committed files byte for byte:
`run_compact_ingest_support_matrix.py`
`c05349d3a102b2c113a0f5373769cbab9972179bd05ac65c72e9f8482ef369f4`,
`compare_output_trees.py`
`b5d5d9986bcc928dfaa3ca32f0329061094eeaaf60233bd9fd3864df20441732`,
`compact_ingest_fixtures.py`
`682b4e18515bd6766ebc7369f7bcfa3c7affee48b949dd1b69b8702de14fe6d3`.

`scarf-3514075/` retains an earlier complete 16/16 run of the same matrix on
`gn0003` and a different device, made before the non-constant-product guard was
added. It is kept as a second SCARF execution, not as the run of record.

Two hosts, two A100 variants, two drivers, two independently built binaries. The
second venue is a shared VM, so it is reported as corroboration; the SCARF
allocation is the run of record. No timing is claimed from either.

Required-test suites at this head: **22/22 CPU** on `cpu64` from a clean clone of
`6bb67e4` (unchanged by the later test-only commits) (cores 32-63, 8-way, under the advisory issue-96 validation lock,
`ctffind` and the concurrent issue-85 codec run on cores 0-31 left alone), and
**29 collected / 28 passed** on the VM CUDA build. The single CUDA-build failure
is `CiFailClosedControls`, which needs `.git` to resolve its trusted manifest and
fails in any rsync'd working copy; it passes in the clean clone.

## Support table

Source `52881c9` on `t3code/compact-ingest-compatibility-tests`, which is
`6827b314` composed with main `6393547e`. Fixtures are generated by the harness:
`g1` = 64x48x6, `g2` = 54x72x8, uint16 Adobe-Deflate TIFF, `--angpix 1.4`,
`--voltage 300`, gain 1.5 where used. Per-arm command lines, per-product
header/extended/payload sha256, input/binary/harness hashes, PIDs, start ticks,
CPU masks and the device catalogue are in `support-20260929/*/support-matrix.json`.

| Case | Configuration | Products per movie | Native stage | Product oracle | Verdict |
|---|---|---|---|---|---|
| `base_gain` | g1, `--gainref --defect_file` | sum | released, no fallback | byte-equal to float32 twin | **PASS** |
| `base_nogain` | g1, no gain | sum | released, no fallback | byte-equal to float32 twin | **PASS** |
| `save_nodw` | g1, `--dose_weighting --save_noDW` | sum, `_noDW` | released, no fallback | byte-equal; `_rlnMicrographNameNoDW` points at `_noDW.mrc` | **PASS** |
| `power_spectrum` | g1, `--grouping_for_ps 2 --ps_size 32` | sum, `_PS` (32x32x1) | released, no fallback | byte-equal; `_rlnCtfPowerSpectrum` points at `_PS.mrc` | **PASS** |
| `even_odd` | g1, `--even_odd_split` | sum, `_EVN`, `_ODD` | released, no fallback | byte-equal; no even/odd association column present | **PASS** |
| `all_output_modes` | g1, noDW + even/odd + PS | sum, `_noDW`, `_EVN`, `_ODD`, `_PS` | released, no fallback | byte-equal, 5 products graded | **PASS** |
| `selected_unequal_groups` | g2, `--first_frame_sum 2 --last_frame_sum 8 --group_frames 2` (groups 2,2,3) | sum | released, no fallback | byte-equal; `_rlnMicrographStartFrame` = 2 | **PASS** |
| `second_geometry` | g2, gain | sum | released, no fallback | byte-equal to float32 twin | **PASS** |
| `successive_same_geometry` | g1 x3 in one process | sum x3 | released on all three | byte-equal to float32 twin | **PASS** |
| `successive_mixed_geometry` | g1, g2, g1 in one process, no gain | sum x3, two geometries | released on all three | byte-equal; per-movie shapes graded | **PASS** |
| `gain_geometry_mismatch` | g1 + g2, one g1 gain | first movie only | released on movie 0 | fails closed, named, publishes nothing for movie 1 | **PASS** |
| `repeat_all_output_modes` | repeat of `all_output_modes` | 5 | released on both runs | complete-tree equality, unchanged tolerances | **PASS** |
| `resume_non_prefix` | g1 x3, middle movie's products withheld, `--only_do_unfinished` | sum, `_noDW`, `_PS` x3 | released on the recomputed movie | resumed tree equals the uninterrupted tree; no completed product rewritten | **PASS** |
| `ineligible_float_tiff` | g1 as float32 TIFF | sum | compact path **not** selected | complete valid tree | **PASS** |
| `ineligible_early_binning` | g1 uint16, `--bin_factor 2` | sum (32x24x1) | compact path **not** selected | complete valid tree at the binned geometry | **PASS** |
| `damaged_movie_named` | g1 x3, movie 1 truncated mid-strip | sum x2 | released on both healthy movies | nonzero exit, no signal death, damaged movie named, publishes nothing, healthy products retained | **PASS** |

Cross-cutting, established by the rows above rather than asserted separately:
gain and no-gain both exact; a defect file exercising the host neighbour read of
the uint16 staging (`motioncorr_runner.cpp:1937-1938`) exact; two nonsquare
geometries; consecutive same- and mixed-geometry movies in one process; repeat
and non-prefix resume exact under unchanged tolerances.

## What the runs established that was not previously recorded

- **A failing movie withholds the whole joint STAR, not just its own row.**
  In both `gain_geometry_mismatch` and `damaged_movie_named` the healthy movies
  keep their `.mrc` and `.star`, and `corrected_micrographs.star` is not written
  at all. The requested "withheld joint STAR" behaviour is therefore
  all-or-nothing, which is stronger than withholding one row but also means a
  partially successful batch publishes no aggregate.
- **`--last_frame_sum` leaves no trace in the metadata.** The per-movie STAR
  records `_rlnMicrographStartFrame` and `_rlnImageSizeZ` (the movie's own frame
  count, not the summed count). A changed last frame is invisible to every
  metadata check and is caught only by pixel comparison.
- **`--even_odd_split` records no association outside tomography.** `_EVN.mrc`
  and `_ODD.mrc` are written, but `_rlnMicrographNameEven` / `_rlnMicrographNameOdd`
  are set only under `is_tomo` (`motioncorr_runner.cpp:1112-1121`). The manifest
  pins their absence so the row cannot drift into claiming an association it
  does not have.
- **One `--gainref` is bound to one geometry.** A mixed-geometry batch cannot
  share a gain reference; the size re-check at `motioncorr_runner.cpp:1452-1455`
  fails closed on the second movie. `successive_mixed_geometry` therefore runs
  without a gain, and the boundary is its own row.

## Not covered

Explicitly unrun or unsupported. None of these is a pass.

| Row | Status | Why |
|---|---|---|
| Odd end-to-end dimensions | **unrun** | The kernel is flat-indexed and `CudaU16StagingEquivalence` already covers 61x47 at session level, but no odd-extent movie was driven through the runner's cuFFT plans and patch extraction. |
| `--write_float16` products | **unrun** | Mode 12 is outside the comparator's payload-size table, and `--float16` forces `--grouping_for_ps > 0`, so the two must land together. |
| EER, compressed MRC, packed 4-bit, `SShort` TIFF, MRC mode 6 | **unsupported by the predicate**, ineligibility unrun for each | `motioncorr_runner.cpp:1467-1469` excludes them by construction. Only the float32 TIFF and early-binning ineligibility paths were executed. |
| Real 3710x3838x24 tutorial movies under the new output modes | **unrun here** | PR118 retains executed all-24 gain / no-gain / selected-frame / `--skip_defect` equality on its own source; those rows are not re-run and not re-claimed. |
| Genuinely poisoned device context | **unsupported** | The existing fatal-code injection in `run_u16_failure_controls.sh` and `run_preprocessing_failure_controls.py` sets return codes; it does not poison real hardware. Unchanged by this work. |
| Device-memory capacity bound for the compact path | **unrun** | No capacity claim is made. |
| Multi-GPU / multi-worker composition | **unrun, other owner** | Issue #26/#53 integration owner. |

## Controls that prove the checks can fail

Test-side guards introduced here are new, so each carries a control that removes
exactly one property from an otherwise valid input.

`tests/test_compare_output_trees.py`, 29 controls (16 pre-existing, 13 added):
missing declared `_noDW.mrc`; undeclared `_EVN.mrc`; `_PS.mrc` written at the
movie geometry instead of `--ps_size`; a mixed-size movie written at its
neighbour's shape; a dropped association column; an association pointing at
another movie's product; a wrong optics group; a changed
`_rlnMicrographStartFrame`, together with STAR number reformatting that must
**not** fail; a forbidden `_rlnMicrographNameEven`; ten malformed manifests; the
legacy no-`products` default; and the pre-existing non-finite pixel guard, which
had no control at all and which every "finite complete pixels" claim rests on.

In the matrix itself:

- The **float32 twin** is the control for the native-stage witness: the same
  assertion that demands the release line on the uint16 arm demands its absence
  on the twin, on inputs that differ only in sample format.
- **Non-constant products.** Byte equality between two arms is satisfied just as
  well by two identically blank images, so every declared product must have
  `dmax > dmin` and `rms > 0` on both arms, and its statistics are retained.
  Measured in the run of record: the plain sum spans 761.5 to 5201.2, `_noDW`
  1842.5 to 12892.9, and the 32x32 `_PS` 2.34 to 957.1.
- The **resume detector** is controlled in-line. Identifying recomputed movies
  by log presence could not have failed, because the control copies the
  completed tree and every log is already there; recomputation is now read from
  the products' `mtime_ns`, and the row reruns the same arm **without**
  `--only_do_unfinished` and requires the detector to trip. Measured: with the
  flag, only the aggregate products (joint STAR, EPS, PDFs) are rewritten;
  without it, all 12 completed per-movie products are.

## Production defects found, and where they belong

Neither is fixed here; this branch owns tests only.

1. **Reconstruction cleanup can lose a fatal release status** — the open Codex
   P1. `cuda_realspace_dw.cu:493-497` and `:342-348` turn a fatal
   `releaseAll()` status into a bare `false` *after* the D2H that produced the
   image; the file's `HANDLE_ERROR` does not record (contrast
   `cuda_fft_prep.cu:14-22`), the scoped owners at `:193-195` and `:413-414` are
   built with no `CudaFailureState`, and `motioncorr_runner.cpp:2747-2765` /
   `:2883-2895` then zero the sum and re-enter the device without calling
   `cudaRetryDecisionFor` or `discard_preprocessing_session`, so
   `Refusing CPU fallback after a fatal device error.` cannot fire. Minimal
   reproduction in the harness's terms: make `motioncorr_faultinject`'s wrapped
   `cudaFree` return `cudaErrorIllegalAddress` for the `d_Isum` free issued by
   `memory_cleanup.releaseAll()`, armed after the
   `[CUDA Unweighted Reconstruction Profile` line; the run exits 0 and publishes
   an MRC. Negative control: the same code at any preprocessing boundary exits
   nonzero with the refusal present. **Owner: shared CUDA reliability executor.**
2. **The compact-ingest selection line is logged before the session exists.**
   `motioncorr_runner.cpp:1472` asserts device-side expansion at a point where
   `initialize()` may still fail at `:1584`, so the line appears in runs that did
   no device work. No product is wrong; the hazard is to any test that greps it
   as a native witness. This matrix does not, and says so in its own docstring.
   **Owner: production runner owner.** Low severity, log ordering only.

## Provenance

- Source `52881c9`; merge parent `6827b314` (frozen PR118 compact-ingest source)
  and main `6393547e`.
- Required CPU test union preserved at 22 after composition: this branch's
  `PatchRetryState` and `OutputTreeComparator` plus main's
  `RunnerInterpolateRecenter` and `RunnerInterpolateShifts`. The three registries
  that restate it — `tools/validate_test_collection.py`,
  `tools/test_ci_fail_closed.py`'s `INTEGRATED_SUITE`, and its drop-one control
  loop — were all updated together, so the count gate cannot preempt the
  missing-name branch for any of the four.
- `CudaCompactIngestSupportMatrix` is registered under CUDA+Linux with labels
  `cuda;hardware`. Like `CudaWrapperUploadFailure` and `CudaErrorClass` it is not
  in `DEFAULT_REQUIRED_TESTS`, which is validated on the CPU-only CI build; that
  exclusion is the existing convention and is a known gap for every CUDA test,
  not one introduced here.

Raw per-case reports, logs and hashes: `support-20260929/`.
