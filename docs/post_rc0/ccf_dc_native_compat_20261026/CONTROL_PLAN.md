# Control and admission plan (PROPOSAL for the parent to freeze; no candidate producer has run)

Freeze rule: source SHA, binaries, inputs, configs, predictions, comparisons, criteria and the job ledger below are fixed before any candidate (`arm != none`) producer starts. The native movie campaign stays HELD until the independent review of this plan and the parent's pins (section 7). No full24/100, no held-out data, no gate or threshold change (`.001` relRMSE, ROI, gauge, `.20/.40/.80 A` unchanged, no scorer monkeypatch). A field FAIL or UNIDENTIFIABLE row is a result, never a harness failure; a new unexplained harm blocks promotion.

## 1. Builds and unit items (venue 4GPUs, correctness only, no timing)

| Build | Options | Role |
|---|---|---|
| `def` | `-DCUDA=ON` | default; no hooks |
| `exp` | `-DCUDA=ON -DMC_EXPERIMENT_CCF_DC=ON` | production-weight controls and the native movie tier |
| `iso` | `exp` plus `-DMC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT=ON` | TEST-ONLY binary for the isotropic N cells; never used for anything else |

`Release`, `-DCMAKE_CUDA_ARCHITECTURES=80`, `BUILD_TESTING=ON`, `-j8` under `taskset -c 80-87`, fresh lease per attempt, every attempt retained.

No full C1 CTest suite is rerun; the full-suite evidence for the unmodified base (C1 packet `b2d117a7`, production `e77a51a2`, non-docs tree identical to `b305b23b`) is reused for the base only. For this diff the CTest regex is `CcfDc|ExperimentCcfDc|PatchRetry|PeakFit|Hermitian|CudaLocalAdmission|CudaStaleErrorAfterOom|SyntheticRegression|HotPixelRng|GlobalIfftElision|Runner_|RunnerInterpolate|RunnerModelParser` in `def` and `exp`. In `iso`, `SyntheticRegression` is excluded from the identity selection: that test compares to the production baseline and the iso binary changes the global weight by design (attempt 1 recorded it failing there with image RMSE 0.26 and shift RMSD 0.083 px, `evidence/venue_attempt1/ctest-iso.log`). That failure is retained as evidence that the iso weight is detectable, not as a waiver of any identity claim: iso has no identity claim.

| # | Item | Pass means |
|---|---|---|
| B1 | `def` selection | rc 0; refusals hold; no hook compiled |
| B2 | `exp` selection + `ExperimentCcfDcStage` G1-G5 + 3 CPU and 4 CUDA restoring mutants + `CcfDcRequest` (+ two `WrongKind` negative controls) | oracle passes; every mutant rejected |
| B2i | `iso`: as B2 plus G6, 3 iso CPU/CUDA mutants and the key mutant | all pass; every mutant rejected |
| B3 | Flag-off identity, ledger rows tagged `B3` (48): per (K267 ID, backend) `def` unset = `exp` unset = `exp` none | `identity_report`: exit, `.star`, `corrected_micrographs.star`, product log, pixels, stdout identical; stderr identical as a line multiset (shell-child ordering); only the anchored progress-bar line and the anchored `Full movie wall time:` log line are normalised |
| B4 | Stage counts on real CUDA runs, ledger rows tagged `B4` (4: affine, CUDA, `exp`, arms none/global/local/both) | per section 4 rules; a row where a declared site is never reached is INCONCLUSIVE, not PASS |

Order: B1/B2/B2i, then the four B4 rows, then B3 and the rest of tier K/N. A failing item stops the campaign; it is fixed by a new commit and re-reviewed, not waived. The witness status `atexit` means the exit handler ran; success is the producer's actual exit status 0 plus complete publication.

## 2. Four comparisons (every case, declared before results)

| ID | Pair |
|---|---|
| C-BASE | CPU off <-> CUDA off |
| C-GOAL | CPU off (unchanged) <-> CUDA on (primary user goal) |
| C-COMMON | CPU on <-> CUDA on (common conditioned reference) |
| C-CPU | CPU off <-> CPU on (reference change) |

If only C-COMMON improves, parity with unchanged CPU is not claimed. Reported separately per pair: field metrics from the tap and from the actual STAR, `local_enabled`, convergence, witness counters, and (movie tier) the legacy relRMSE profile unchanged. All numeric regressions and OFF-pass -> ON-fail rows are kept. Process-0 or CPU agreement is not science.

Frozen prediction: C-COMMON relRMSE is lower than C-BASE in every movie case; C-GOAL is not lower than C-BASE by more than 1.5x in at least 2 of the 4 PR288 cases (#262 table: conditioning CUDA only against the original CPU gave 16 vs 17 S1-positives). Either outcome is reported as observed.

## 3. Inputs and criteria

**K267** (#267 motion diagnostics v2; `test-data/generate_motion_diagnostics.py`, `gen.CASES`, 128x96x5, schema `motion-diagnostics/2`). Eight IDs exactly: `zero`, `integer`, `fractional`, `affine`, `pedestal`, `noisy`, `flat`, `repeated`. Scored by the unchanged `tools/check_motion_diagnostics.py` (`check_case`, ROI `[12,84,12,116]`, limits `.20/.40/.80 A`). Pinned command (`k267_argv`): the retained `run_v2.py` command with 3x3 patches for all eight IDs (the retained run used 1x1 for `zero`, `integer`, `fractional`, `flat`, `repeated`, which never runs the local stage, so local/both would equal none/global) and without `--skip_logfile` so the product log exists; `--j 8`, `--bin_factor 1 --seed 1 --skip_defect --save_noDW --first_frame_sum 1 --last_frame_sum 5`, `--gpu 0` for CUDA with `CUDA_VISIBLE_DEVICES` pinned by UUID, default `MOTIONCORR_PATCH_BATCH`. The five 3x3 re-runs are therefore different jobs from the retained 1x1 runs; historical characterization results (integer/fractional/affine/pedestal FAIL, noisy FAIL or outside-ROI, flat UNIDENTIFIABLE, repeated outside-ROI) are kept as the record and are not overwritten. 96 jobs.

**W5 phase-ramp N controls** (original eight movies). Original inputs: the retained render report (`evidence/retained_render_report.json`, blob `cae19f3f`) pins `mrcs_sha256` and `star_sha256` for `vel0_N5/9/13/20`, `vel1_N5/9/13/20` (base image sha `287e0a82...`). The retained generator needed W5 scratch code (`common.py`, `indep.py`, sha256 in the report) that is not in git; it is not used. `test-data/generate_ccf_dc_n_controls.py` (Fourier shift of the K267 target, `frame_f(x) = base(x + f*vel)`) reproduces **all eight MRC files and all eight STAR files byte for byte, headers included** (`CcfDcRowsPure.test_n_control_generator` asserts it against the pins). The replacement is therefore admissible as the original inputs; no header-only difference exists. Truth files were not hashed in the report; truth is the movie's own construction (`f*vel`, vel0 = (-1, 2), vel1 = (-0.8125, 0.53125) px/frame). That is a provenance gap for the truth *file*, closed by (i) the analytic definition, (ii) frame 0 and sign checks against the K267 `integer` movie, and (iii) criterion C-REPRO below, which reproduces the retained trajectory RMS of all 16 retained rows. Scoring (`n_score`): frame-zero gauge, spatially constant field so the ROI `y[12:84] x[12:116]` is immaterial, 0.885 A/px, limits `.20/.40/.80 A`, vectors via `check_motion_diagnostics.vector_metrics`, runtime tap and STAR separately, no offset or floor subtracted. The retained scorer is not reused: it hard-codes W5 scratch paths and the old arm/log formats. Pinned command (`n_argv`): the retained one (`--j 2`, `--patch_x 1 --patch_y 1`, `--last_frame_sum N`) without `--skip_logfile`. Stop: production only; the retained second stop needs a research flag absent from C1 and is **UNRUN**. 8 cells per weight set; production-weight on `exp` (32 jobs), isotropic on `iso` (32 jobs).

**C-REPRO (pre-results).** Each of the 16 CPU arm-none N jobs (`repro.csv`) must reproduce its retained CPU arm-a row (`evidence/retained_cpu_reference.json`, source blob `dfb0fc42`): runtime and STAR `rms`, `p95`, `max` (Angstrom) and `traj_rms_px_runtime` equal within 1e-5 (A or px; ten float32 spacings at 20 px) and the same verdict. Arithmetic is identical to the retained binaries by construction (production weight is flags-off C1; the iso weight is the PR286 `ccfWeightAt` normalisation), but the host and compiler differ from the retained cpu64 run, so equality is checked, not assumed. If any row fails, the affected weight set stops there and is reported; the criterion is not widened after seeing results.

**Isotropic route.** Parent decision (a): the compile-gated test-only override (DESIGN) on CPU and CUDA, solely for these N controls, no production flag. Mandatory historical harm `vel1_N20` (isotropic): 10.4-10.5 A, FAIL in all four arms of the retained CPU record, baseline included; the candidate must not make any control that passes with arm none fail.

## 4. Runtime-tap consumers and row rules (`tools/ccf_dc_tap_field.py`, `tools/ccf_dc_native_rows.py`)

- Bridge: `MC_DIAG_MODEL_OUT` JSON -> dense `F,Y,X,2` field, truth-free. Inputs: the tap and `nx, ny, frames` from the pinned fixture/config. Field equation: the existing `check_realistic_motion.runtime_field`, groups `[1,u,u^2,v,v^2,uv]` each times `[z,z^2,z^3]`, `z` = frame index, `u = x/nx - .5`, `v = y/ny - .5`, plus the global shift (same as `src/micrograph_model.cpp` `getShiftAt` and `motion_field.MotionStar`). Rejects a missing/placeholder tap, wrong keys or lengths, non-finite or non-numeric values, and `local_enabled == false` with nonzero coefficients. `CcfDcTapField`: all 36 single-coefficient analytic cases (6 groups x 3 powers x 2 axes) on anisotropic 96x64, zeros/global/linear/quadratic/cubic, unit (no px/A scaling), frame 0, schema rejections, and five convention mutants (conventional `[1,u,v,u^2,uv,v^2]`, wrong axis normalisation, time offset, x/y components swapped, x/y coefficient sets swapped) that the same check must reject.
- Independent STAR comparison: the tap's numbers are rounded exactly as the STAR writer rounds (`src/metadata_table.cpp`: `%12.5f`/`%12.6f` for `0.001 <= |v| <= 1e5`, else `%12.5e`/`%12.6e`) and the resulting field must equal the field read back from the actual STAR within 1e-9 px (double evaluation order); otherwise the row is INVALID. The writer's own rounding loss is reported separately and bounded by 5e-6 * (1 + sum over coefficients of (frames-1)^(k+1) * max spatial factor).
- K267 scoring: the tap field is passed as a dense `.npy` and the actual STAR as `.star` to the unchanged `check_case`, results kept separate. N scoring as in section 3.
- Row status precedence: FAILED_RUN (actual exit != 0, even with a complete-looking tap or `atexit` witness; the tap is written before dose weighting and image writes, so it can exist after a later failure) > INCOMPLETE_PUBLICATION (movie, per-movie STAR, joint STAR, product log must exist and be non-empty) > INVALID (witness not `atexit`, wrong arm, wrong binary identity, inconsistent counters, a CPU run touching a CUDA site or a CUDA run touching a CPU site, tap/STAR disagreement) > INCONCLUSIVE > SCORED.
- Witness coverage (M3): for every stage the run is declared to reach, `calls_eligible > 0` and `frames_eligible > 0` at the declared site, for every arm including none; selected stage `zeroed == eligible`, unselected `zeroed == 0`. Declared sites: CPU `cpu`; CUDA `cuda_single` for global and `cuda_batched` for local (3x3 pinned, default batch cap). A never-reached declared site (for example no batched path, or a 1x1 run asked for a local arm) is INCONCLUSIVE and cannot PASS. N controls declare only the global stage and must show zero local calls.
- Convergence and acceptance come from the actual product log through the unchanged `check_realistic_motion.convergence`: CONVERGED, NOT_CONVERGED, AMBIGUOUS (exact `.5` or no verdict) or MISSING (no log or no global section); a missing marker is never a pass. `local_enabled` and patch convergence counts are reported separately.

## 5. Ledger (generated, nothing run)

`make_ledger.py` writes `ledger.csv` (176 jobs, all `HELD`, with `gates` and `cli` columns), `pairs.csv` (112), `repro.csv` (16) and `counts.json`.

| Tier | Jobs | Composition |
|---|---:|---|
| K | 96 | 8 IDs x 2 backends x 6 rows: `def` unset, `exp` unset, `exp` none/global/local/both |
| N | 64 | 8 cells x 2 backends x 2 arms (none, both) x 2 weight sets |
| M (held) | 16 | 2 movie IDs (00021, 00046) x 2 configurations (G, L) x 2 backends x 2 arms (none, both), `exp` |

B3 and B4 add no jobs: B3 is the 48 tagged K rows, B4 the 4 tagged K rows (their `exp` none row is shared with C-BASE/C-GOAL/C-CPU, produced once). Pairs: the four comparisons anchored on each cpu none job (K 32, N 64, M 16).

## 6. Native movie tier (HELD)

PR288's predetermined issue-36 movies `00021` and `00046`, G and L as defined in PR288 `RESULT`, input hashes as pinned there, one movie per process, `exp` for all four arms, matched settings (`--j 8`), 16 producers. The movie CLI and the consumer for the legacy `.001` profile are parent pins (not defined here). It runs only after sections 1, 3 and 4 pass, their review is done and the parent has frozen the pins.

## 7. Resources and records

Venue 4GPUs only. GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` (by UUID, `--gpu 0`), CPU 80-87 under whole-command `taskset`, one job at a time, `-j8` max, scratch under a new directory <= 20 GiB, raw outside Git with an index. Per attempt: fresh occupancy (compute apps, process list, `flock -n` on every `/tmp/*.lock`, fd walk for deleted locks) then exclusive leases on `/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock` plus the overlapping range/GPU/build locks. No stopping of others' jobs, no deletion of leases. Correctness only, no performance claim. Every command, binary and input hash, route, fallback, exit status and failure is recorded; failed attempts are kept (`evidence/`).
