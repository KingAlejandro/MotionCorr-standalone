# Control and admission plan (PROPOSAL for the parent to freeze; nothing here has run)

Freeze rule: source SHA, binaries, inputs, configs, predictions, comparisons and matrix below are fixed before any candidate (`arm != none`) producer starts. The movie campaign stays HELD until (1) independent source review of the exact commit, (2) the unit/oracle/identity items in section 1 pass on the venue, and (3) the parent confirms this matrix. No full24/100, no held-out data, no gate/threshold change (`.001` relRMSE, ROI and `.20/.40/.80 A` limits unchanged, no scorer monkeypatch).

## 1. Build and unit items (venue 4GPUs; correctness only, no timing)

| # | Item | Pass means |
|---|---|---|
| B1 | Default CUDA build (`-DCUDA=ON`, no experiment option), full CTest incl. `CcfDcRequest` | rc 0; the default-build refusals hold |
| B2 | Experiment CUDA build (`-DMC_EXPERIMENT_CCF_DC=ON`), CTest incl. `ExperimentCcfDcStage`, six CUDA/CPU mutants (must be rejected) and `CcfDcRequest --experiment` | oracle G1-G5 pass; every mutant exits as expected |
| B3 | Flag-off identity: same tiny synthetic movie and known-motion tree through B1 binary and B2 binary with arm unset and `none`, CPU and CUDA | pixels, STAR, logs (output dir normalised) identical; exit/publication identical |
| B4 | Stage counts on a real CUDA run: tiny movie, arm none/global/local/both, witness | selected stage zeroed == eligible at `cuda_single` (and `cuda_batched` when the batch path runs); other stage 0; CPU sites 0 |

A failing item stops the campaign; it is fixed by a new commit and re-reviewed, not waived.

## 2. Four comparisons (all declared for every case, chosen before results)

| ID | Pair | Meaning |
|---|---|---|
| C-BASE | CPU off <-> CUDA off | legacy baseline |
| C-GOAL | CPU off (unchanged) <-> CUDA on | primary user goal: unchanged CPU as reference |
| C-COMMON | CPU on <-> CUDA on | common conditioned reference |
| C-CPU | CPU off <-> CPU on | reference change on the CPU itself |

If only C-COMMON improves, the report states that parity with unchanged CPU is not achieved. Measured separately per pair: relative image RMSE (legacy `.001` profile unchanged), runtime global shifts and coefficients (tap), `local_enabled`, global/local convergence (product log via the unchanged checker), witness counters, STAR fields. All numeric regressions and OFF-pass to ON-fail rows are retained and listed. Process-0 or CPU agreement is not science.

Frozen prediction (from #262 table, where conditioning CUDA only against the original CPU gave 16 vs 17 S1-positives, and from PR288 H_DC): C-COMMON relRMSE is lower than C-BASE in every case; C-GOAL is NOT lower than C-BASE by more than 1.5x in at least 2 of 4 PR288 cases (the unchanged CPU keeps its own pedestal rounding). Either outcome is reported as observed.

## 3. Mandatory tiny truth/harm controls (CPU and CUDA, arms none and both, plus global/local singles where a stage exists)

- The eight retained K267 cases (128x96x5 known-motion fixtures from `tools/run_known_motion_gates.py`/`test-data/known_motion`: high-signal zero/integer/fractional/affine/pedestal, five-frame, noisy, flat, repeated), scored with the unchanged `tools/check_known_motion.py`/`check_realistic_motion.py` from runtime tap and actual STAR separately. Historical failures (noisy, flat, repeated) are retained as characterization.
- The W5 phase-ramp N controls N = 5, 9, 13, 20 at vel0 and vel1, production-weight rows (16 cells), rendered by the retained `render_ncontrols.py` from the retained PR286 record (`ed1a0e3f`), scored by retained `score_ncontrols.py`, production stop.
- **Admission question (not resolved here): vel1-N20-iso and the 16 iso cells.** The isotropic weight (x frequency normalised by `pnx` instead of `nfx`) exists only as the CPU-only research flag `--experimental_isotropic_weight` (PR286 line, `20e52f57`). C1 has no such route, and CUDA computes its weight in `computeWeightsKernel` with `nfx` baked in and caches it in the workspace key, so a CUDA override is new estimator-side code, not a test fixture. This work does NOT add a production isotropic flag and does not invent a waiver. Options for the parent: (a) authorize a separate, compile-gated test-only override on both backends with its own review; (b) use the retained PR286 CPU binary as a retained CPU-only control for the iso cells (CPU off baseline only; no CUDA and no C-GOAL/C-COMMON, so iso candidate coverage is incomplete); (c) record the iso cells UNRUN and stop that qualification item. Until the parent chooses, the iso cells are UNRUN and any claim excludes them. Historical fact retained: vel1-N20-iso fails in all four arms of the CPU research record, baseline included (10.4-10.5 A).

## 4. Native movie tier (HELD; first matrix only)

PR288's predetermined issue-36 cases `00021` and `00046`, each G and L as defined in PR288 `RESULT`, input hashes as pinned there, one movie per process, same binary for CPU and CUDA, matched settings (`--j 8`, no seed difference). Arms: CPU off, CPU both, CUDA off, CUDA both = 4 cases x 2 (G/L) x 4 = 16 producers. Then the full comparison table of section 2, tap and STAR separately, and the PR288 legacy `.001` profile. Run only after sections 1 and 3 pass and the parent releases it; no further movies.

## 5. Resources and records

Venue 4GPUs only. GPU2 `GPU-063e5232-7fc5-f1e6-7a0d-260577c4e598` (select by UUID, `--gpu 0`), CPU 80-87 via whole-command `taskset`, one job at a time, build `-j8` max, scratch under a new directory <= 20 GiB with indexed raw outside Git. Before each build/test: fresh occupancy (nvidia-smi compute-apps, process list, `flock -n` on every `/tmp/*.lock`, fd walk for deleted locks), then a dedicated exclusive lease `/tmp/motioncorr-dcnative-gpu2-cpu80-87.lock`. No stopping of others' jobs, no deletion of leases. Correctness only; no performance claim. Record every command, binary and input hash, route, fallback, exit status and failure.
