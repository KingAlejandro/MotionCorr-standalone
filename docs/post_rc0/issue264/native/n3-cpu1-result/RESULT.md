# #264 cpu1 result and pair-failure diagnosis (23 October 2026)

**cpu1 CPU subset: FAIL, as recorded.** The chain exited 1 at `cpu1-grade`. All three CPU overlay builds and
all 24 native CPU rows exited 0. The unchanged grader gave 24 PASS / 0 FAIL / 16 UNRUN rows and N4 PASS (the
mutant differs on exactly A_x, A_y, B_x, B_y, E). Base/candidate pairs were 3 PASS / 5 FAIL. The subset's only
problem: "CPU base/candidate pairs not 8 PASS". The FAIL is not downgraded or regraded here. The full
N3/N4 aggregate stays INCOMPLETE (16 CUDA rows UNRUN), and the original iteration-0a N3 stays UNRUN.
No source changed. Parent owns the F1/F2 binding and reap checks.

## Diagnosis: grader comparison defect, not a trajectory change

The five failing pairs (A_x, B_x, A_y, B_y, E) are exactly the cases where base and candidate decide
differently. In every one, `same_global_shifts` is false while the decision and the image relation are as
predicted.

- **The numeric global trajectory is identical.** `diagnose_pairs.py` reuses the unchanged
  `tools/n3.py` `star_blocks` on the retained STARs. All 8 CPU pairs have the same 12 `(frame, x, y)`
  rows, and all three arms agree per case. The global-alignment section of each per-movie log is
  byte-identical in all 24 runs (sha256 `ef69c8af…bb10`, `raw/global-alignment-log-sections.txt`; that
  file's header text says "first16" by mistake, but the hashes are full).
- **Mechanism.** `star_blocks` takes the text from `data_global_shift` up to the next `data_`.
  `Micrograph::write` (`src/micrograph_model.cpp`, global block then `local_motion_model` only if
  `model != NULL`; empty `hot_pixels`/`local_shift` tables print nothing under `--skip_defect`)
  makes what follows the rows depend on the decision. Before an accepted model the extracted text ends
  `'\n\n'` and then `# version 50001` is cut off at `data_`. When rejected it runs to end of file and ends `' \n \n'`.
  So the raw-string comparison differs exactly when the decisions differ, and is equal for F, G and Z.
- **No upstream path can change it.** Global shifts are set only at the global-alignment stage
  (`motioncorr_runner.cpp:3378`), before patch alignment (3447), the fit (3851) and the guard. No later
  `setGlobalShift` exists in that path, so the local accept/reject cannot alter the global trajectory.
- **Harm controls (`diagnosis.json`):**
  - a 1e-6 change to one retained shift value is detected by the row comparison;
  - two synthetic STARs with identical rows, one followed by a model block and one ending, reproduce the extraction mismatch.
- **Why the pre-launch mocks missed it.** `test_cpu1_controls.py` synthesised STARs without the real writer's
  `# version 50001` separators and trailing `' \n'` lines, so its global-block extraction was equal on both paths.
  That mock could not observe this defect. It is a control gap in my iteration-1/cpu1 tooling, inherited by the
  iteration-2 proposal. R4 noted that the first native run would be the first real test of the STAR conventions.

**Impact.** Only the `same_global_shifts` sub-check of decision-flip pairs is affected. Per-row decisions,
printed deltas, published/absent models, coefficients, image relations and N4 were all graded by unchanged code
and passed. No production or guard defect is indicated. The same defect would fail every flip pair of the
iteration-1 GPU arms and of the iteration-2 proposal, so neither should run with the current grader.

## Next discriminating action (proposal only; needs parent review before any use)

1. Freeze a distinct grader version, a new file in a new directory. It compares the parsed numeric global rows
   (frame, x, y as printed) for equality instead of the raw block string; everything else stays unchanged.
   Its controls must use real-writer STARs from `raw/failed-pairs/`:
   - identical rows with a different following block must PASS;
   - one altered value must FAIL;
   - a missing row must FAIL.
2. Apply it as a separately labelled regrade of the immutable cpu1 outputs (`raw/evidence.tar`), leaving this
   FAIL and its `RESULTS.json`/`CPU_SUBSET.json` untouched. Then use it for any later iteration.

No native rerun is needed for step 2.

## Evidence (this directory)

- **`raw/evidence.tar`** (sha256 `3cc13020…2760`): read-only copy of `launch-cpu1/`, `logs/`, `n3-cpu1/{RESULTS,CPU_SUBSET,known-observations}.json`, the three `build-ov-*-cpu.binaries.sha256`, and every row's RUN.json, STAR, stdout and stderr.
- **Extracted for reading:** `raw/RESULTS.json`, `raw/CPU_SUBSET.json`, `raw/known-observations.json`, `raw/CHAIN.txt`, `raw/chain.exit` (1), `raw/build-ov-*-cpu.binaries.sha256`.
- **Binary hashes:** base `3ee3c739…`, cand `789e5e5b…`, mut `7e0b2cab…`.
- **`raw/failed-pairs/<case>/ov-{base,cand}-cpu.star`:** the ten raw STARs of the failing pairs.
- **`diagnose_pairs.py`, `diagnosis.json`** (sha256 `ec5e03de…f6d3`).
- **Commands:** run `python3 -B diagnose_pairs.py <extracted evidence> --out diagnosis.json` on the Mac with one thread (exit 0). The remote reads were read-only metadata and log hashing, pinned to CPUs 14–15. No GPU query, build, native run or movie processing.

**Limits.** STAR and log values carry 6 significant digits; the in-memory double trajectory was not dumped. The
argument that global shifts cannot depend on the guard decision rests on source order plus byte-identical
logs and STAR rows, not on a full-precision trace. The CUDA rows were never run.
