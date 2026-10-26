# Control and admission plan (PROPOSAL for the parent to freeze; nothing here has run)

Freeze rule: source SHA, binaries, inputs, configs, predictions, comparisons and matrix below are fixed before any candidate (`arm != none`) producer starts. The movie campaign stays HELD until (1) independent source review of the exact commit, (2) the unit/oracle/identity items in section 1 pass on the venue, and (3) the parent confirms this matrix. No full24/100, no held-out data, no gate/threshold change (`.001` relRMSE, ROI and `.20/.40/.80 A` limits unchanged, no scorer monkeypatch).

## 1. Build and unit items (venue 4GPUs; correctness only, no timing)

Three builds of the same source, each in its own directory with its binary hash recorded:

| Build | Options | Role |
|---|---|---|
| `def` | `-DCUDA=ON` | default; carries no hooks |
| `exp` | `-DCUDA=ON -DMC_EXPERIMENT_CCF_DC=ON` | production-weight controls and the native movie tier |
| `iso` | `exp` plus `-DMC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT=ON` | TEST-ONLY binary for the iso N-control cells; its global weight is always isotropic, so it is never used for any other case |

All three use `Release`, `-DCMAKE_CUDA_ARCHITECTURES=80`, `BUILD_TESTING=ON`, `-j8` under `taskset -c 80-87`.

Test selection. No full C1 CTest suite is rerun. The valid full-suite evidence for the unmodified base (C1 packet `b2d117a7`, tested production `e77a51a2`, non-docs tree identical to `b305b23b`) is reused for the base only; it says nothing about this diff. For this diff the CTest regex is `CcfDc|ExperimentCcfDc|PatchRetry|PeakFit|Hermitian|CudaLocalAdmission|CudaStaleErrorAfterOom|SyntheticRegression|HotPixelRng|GlobalIfftElision|Runner_|RunnerInterpolate|RunnerModelParser`, in every build, plus the new items:

| # | Item | Pass means |
|---|---|---|
| B1 | `def`: selection above, incl. `CcfDcRequest` | rc 0; refusals hold; no hook compiled |
| B2 | `exp`: selection + `ExperimentCcfDcStage` (G1-G5) + 3 CPU and 4 CUDA restoring mutants + `CcfDcRequest --experiment` | oracle passes; every mutant is rejected |
| B2i | `iso`: as B2 plus G6 (isotropic-vs-production detectability >1e-3 px; one CUDA workspace reused global->local equals fresh), CPU/CUDA mutants `iso_wrong_norm`, `iso_leaks_local`, `cuda_iso_key_ignores_stage`, and `CcfDcRequest --experiment --iso` (witness `test_only_isotropic_global_weight: true`) | all pass; every mutant rejected |
| B3 | Flag-off identity: tiny synthetic movie and the eight K267 cases (section 3) through `def` and `exp` (arm unset and `none`), CPU and CUDA | pixels, STAR, logs (output dir normalised) identical; exit and publication identical. Not applicable to `iso` (its global weight is intentionally different) |
| B4 | Stage counts on a real CUDA run, tiny movie, arms none/global/local/both | selected stage zeroed == eligible at `cuda_single` (and `cuda_batched` if the batch path ran); other stage 0; CPU sites 0 |

A failing item stops the campaign. It is fixed by a new commit and re-reviewed, not waived. The witness status `atexit` means the exit handler ran; it does not mean the producer succeeded. Every producer's actual exit status and publication are retained by the harness and are the success criterion.

## 2. Four comparisons (all declared for every case, chosen before results)

| ID | Pair | Meaning |
|---|---|---|
| C-BASE | CPU off <-> CUDA off | legacy baseline |
| C-GOAL | CPU off (unchanged) <-> CUDA on | primary user goal: unchanged CPU as reference |
| C-COMMON | CPU on <-> CUDA on | common conditioned reference |
| C-CPU | CPU off <-> CPU on | reference change on the CPU itself |

If only C-COMMON improves, the report states that parity with unchanged CPU is not achieved. Measured separately per pair: relative image RMSE (legacy `.001` profile unchanged), runtime global shifts and coefficients (tap), `local_enabled`, global/local convergence (product log via the unchanged checker), witness counters, STAR fields. All numeric regressions and OFF-pass to ON-fail rows are retained and listed. Process-0 or CPU agreement is not science.

Frozen prediction (from #262 table, where conditioning CUDA only against the original CPU gave 16 vs 17 S1-positives, and from PR288 H_DC): C-COMMON relRMSE is lower than C-BASE in every case; C-GOAL is NOT lower than C-BASE by more than 1.5x in at least 2 of 4 PR288 cases (the unchanged CPU keeps its own pedestal rounding). Either outcome is reported as observed.

## 3. Mandatory tiny truth/harm controls (CPU and CUDA)

**K267 family** (#267 motion diagnostics v2, `test-data/generate_motion_diagnostics.py`, `gen.CASES`; 128x96x5; scored by the unchanged `tools/check_motion_diagnostics.py --case <id>` from the runtime tap and the actual STAR separately). The eight fixture IDs are exactly: `zero`, `integer`, `fractional`, `affine`, `pedestal`, `noisy`, `flat`, `repeated`. ("Five-frame" is their frame count, not a ninth case; high-signal = the five noiseless identifiable IDs, noisy/flat/repeated are characterization.) Historical native failures are retained: integer/fractional/affine/pedestal FAIL the original field gate; noisy FAIL or `INPUT_ERROR_OUTSIDE_ROI`; flat `UNIDENTIFIABLE`; repeated `INPUT_ERROR_OUTSIDE_ROI`. Jobs: 8 IDs x 2 backends x 4 arms (none, global, local, both) = **64**.

**W5 phase-ramp N controls** (retained `render_ncontrols.py`/`score_ncontrols.py`, PR286 record `ed1a0e3f`): 8 movies = vel0, vel1 x N 5, 9, 13, 20 (128x96, global alignment only; no patch alignment runs, so the local stage never fires). Each movie is a cell under a weight set: **8 production-weight cells** and **8 isotropic cells** (the retained record's 16 cells per stop). Stop: production only (C1 `max_iter 5`, tolerance 0.5 px). The retained record's second stop (`--max_iter 50 --experimental_align_tolerance 1e-9`) needs a research flag that C1 does not have and is not added here, so the long stop is **UNRUN** and excluded from any claim. Per weight set: 8 cells x 1 stop x 2 backends x 2 arms (none, both) = **32 jobs**; total **64** N-control jobs (production weight on `exp`, isotropic on `iso`). Scored with the unchanged ROI y[12:84] x[12:116], 0.885 A/px, frame-zero gauge, limits 0.20/0.40/0.80 A; runtime tap and STAR separately. Mandatory historical harm: `vel1-N20-iso` (10.4-10.5 A, FAIL in all four arms of the retained CPU record, baseline included); the controls that pass with arm none must not become failures under `both`; all N = 5 cells are retained as characterization.

**Isotropic route (parent decision (a)).** The isotropic cells use a separate compile-gated TEST-ONLY binary (`iso`): `MC_TEST_ONLY_ISOTROPIC_GLOBAL_WEIGHT` replaces `nfx` by `pnx` in the x frequency normalisation of the global stage's CCF weight, on CPU (`alignPatch`, `is_global`) and CUDA (`computeWeightsKernel` argument, `is_global`), with `is_global` added to the CUDA workspace key in that build. Compile-time constant: no CLI flag, no environment switch, local stage unchanged, off by default, requires the experiment option so the witness always reports `test_only_isotropic_global_weight`. The same arithmetic as the retained W5 `iso` (research flag `--experimental_isotropic_weight`, PR286 `20e52f57`, CPU only); the retained record (CPU, 128 runs) is the reference for CPU rows, with the exact-source limit that it ran on a PR286 binary, not on `iso`. If B2i fails or the CPU rows of `iso` do not reproduce the retained CPU rows for arm none, the iso item stops and is reported, with no waiver. The `iso` binary is never used for production-weight cells or for the native movie tier.

## 4. Native movie tier (HELD; first matrix only)

PR288's predetermined issue-36 movies `00021` and `00046`, each in its G and L configuration as defined in PR288 `RESULT` (input hashes pinned there), one movie per process, same binary for CPU and CUDA (`exp`), matched settings (`--j 8`). Arms: CPU off, CPU both, CUDA off, CUDA both. Count: 2 movie IDs x 2 configurations (G, L) x 4 arms = **16 producers**. Then the section-2 comparisons, tap and STAR separately, and the PR288 legacy `.001` profile unchanged. Runs only after sections 1 and 3 pass, the independent review of the control admission is done and the parent has frozen the pins; no further movies.

## 5. Resources and records

Venue 4GPUs only. GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` (select by UUID, `--gpu 0`), CPU 80-87 via whole-command `taskset`, one job at a time, build `-j8` max, scratch under a new directory <= 20 GiB with indexed raw outside Git. Before each build/test: fresh occupancy (nvidia-smi compute-apps, process list, `flock -n` on every `/tmp/*.lock`, fd walk for deleted locks), then a dedicated exclusive lease `/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock`. No stopping of others' jobs, no deletion of leases. Correctness only; no performance claim. Record every command, binary and input hash, route, fallback, exit status and failure.
