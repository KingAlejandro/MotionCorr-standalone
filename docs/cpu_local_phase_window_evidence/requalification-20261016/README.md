# PR #183 requalification, 16 October 2026

**Superseded by the [current main 1db86902 acceptance](merged-1db86902/README.md).**
The earlier d7171b81 results below are preserved, not current-head claims.

Base: `d7171b81` (merged, not rebased, merge commit `bd408a48`). Code: `7c453e5ef54816f0eacdbdf532f133e284e49ac1`.

All review findings accepted. No numerical gates changed.

- GNU/ELF witness wraps `sin`/`sinf` as well as `sincos`/`sincosf`, counting one sine per phase whether separate or compiler-fused. Positive expected counts are unchanged. macOS has no linker-wrap witness; exactness and multi-iteration checks still run.
- Local `alignPatch` omits the converged/iteration-limit update, because no later read consumes it. Global updates remain complete, including the last. The predicate preserves the old convergence comparison even for NaN.
- The declaration now explicitly says local `Fframes` are consumed scratch, not returned aligned spectra. Cropped and final-unapplied bins must not be reused.
- The production alignment differential requires at least one cropped case with >=2 iterations, on every platform. Observed: 36 of 108 rows on macOS. A skipped needed update changes the accumulated trajectory/log oracle.

Expected benefit is calculated, not newly measured: for a 768x742 patch / 192x192 CCF, complex updates per shifted group fall from 285,670 to 18,624 (6.52%); phase-table entries from 1,127 to 289. With I local iterations the update count further falls from I to I-1, eliminating all phase updates when I=1 and half when I=2. No inference of whole-job speedup or RSS reduction follows. The separate corpus screen owns timing.

## Provenance

Trees shipped with `git archive <sha> | ssh cpu64 'tar -x -C DIR'`. Initially builds used the shared lock; the orchestrator then explicitly reassigned correctness work to exclusive CPUs **56-61** (NUMA node 1), **without flock**. All successful final Linux checks inherit `taskset -c 56-61`, build parallelism 4, `OMP_NUM_THREADS=6` / `OMP_THREAD_LIMIT=6` (movie payloads j1/j4). Work is confined to `/home/ubuntu/fix183-20261016/`; no corpus/screen inputs, foreign processes, `/mnt`, or GPU host touched. Runs are correctness controls, not timed benchmarks. The host is shared, with unrelated `ctffind` load; no timing conclusion is drawn.

Raw commands, statuses, logs, binary/input/product SHA-256 and mutation recipes are in this directory. The old evidence above this directory is preserved historical evidence, not the acceptance record for the current code. The earlier off-branch source/driver provenance is not repaired by assertion; the new run replaces it for current exactness claims.

## macOS

Release CPU-only configure/build at code `7c453e5e`: exit 0. Full CTest: exit 8, 56 pass / 2 fail / 1 platform skip out of 59. Only `SyntheticRegression` and `MultiGpuScheduling` fail. Plain `d7171b81` reproduced both: exactly 23.649856567382812 max-pixel difference and the same tomography healthy-tree assertion. No tolerance or gate is waived beyond the two task-authorized inherited macOS failures. `NativeMovieStaging` is an explicit platform skip, not a pass.

Commands:
```
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDA=OFF -DPython3_EXECUTABLE=$HOME/.venvs/global/bin/python3
cmake --build build -j4
ctest --test-dir build --output-on-failure
```

Mutants build successfully (exit 0) and each test exits 1:
- Skip all local updates: `local versus full production alignment shifts/logs differ`.
- Run only iteration-limit 1 rows: `no cropped alignment exercised a needed phase update (>=2 iterations)`.
Restored source builds and focused test exit 0.

## Linux

At source `7c453e5e`, all commands below exit **0**:

- Release CPU-only configure/build and `ctest --test-dir build-release --output-on-failure`: **59/59** pass, no skips.
- Debug CPU-only configure/build with explicit `-DCMAKE_CXX_FLAGS_DEBUG="-O0 -g"` and `ctest --test-dir build-debug --output-on-failure`: **59/59** pass, no skips.
- Plain `d7171b81` Release build.
- Both `cpu_patch_phase_window` binaries: 300 helper geometries; positive production sine count witness; 108 differential alignments, including **36 cropped multi-iteration cases**.
- `python3 exact.py`: four strict 5x5 product pairs (tutorial and generated 512x512x16 synthetic, j1/j4), DW/noDW/even/odd, group_frames=5. **16 MRC + 8 STAR pairs** have matching canonical SHA-256; all 16 MRC payload hashes match. Full headers are compared with only the first-label writer timestamp masked; STAR only substitutes its own output root. Full tree inventory/other deterministic products also pass (48 compared files). Logs/PDFs have the existing explicit exclusions.
- `python3 linux-mutants.py`: all three builds succeed, each mutated test exits **1**, restored builds/tests exit **0**. Removing fallback-sine counting in Debug fails the unchanged positive count expectation; full-local updates and restoring dead-final updates each fail the local call-count oracle.
- Negative product control: flipping exactly the first MRC payload byte yields comparator status **1**, with exactly one difference (`payload differs at byte 1024`); inventories remain equal. The control driver exits 0 only because rejection was expected.

See `linux-builds.sh`, `exact.py`, `linux-mutants.py`, and `linux/*.command` for literal commands/statuses. `linux/exact-results.json` retains binary/input/product digests and every movie command/status. Tutorial/gain were downloaded independently from the published `spa-tutorial-data-v1` release and match its SHA256SUMS. Synthetic recipe: `candidate/test-data/generate_synthetic_fixture.py --profile standard --outdir data`, seed 20260923.

The initial source-archive Release CTest was **58/59 (exit 8)**: `CiFailClosedControls` expects the git-backed invalid-ref diagnostic, but an archive has no `.git`. It is retained as `archive-no-git-release-ctest.*`. Restoring exact-commit Git metadata (without changing tracked bytes) makes it pass; no test was skipped or changed. The short-ref metadata fetch failure (128) is also retained; the full 40-character source IDs succeed. Old waiting lock commands were stopped only after checking their ownership; successful pinned checks supersede those queued attempts.

Code CI run [38946764298](https://github.com/KingAlejandro/MotionCorr-standalone/actions/runs/38946764298) is green at `7c453e5e`: Linux build/smoke/full CTest and CUDA compile-only. Final evidence commit is documentation-only; `code-blobs.txt` / `base-blobs.txt` retain every source/test/CMake blob ID. No off-branch source identity is assumed.

## Limits

No new wall-time or peak-memory measurements, no CUDA execution, no scientific-equivalence claim beyond same-backend exact outputs on the stated fixtures. Representative whole-job benefit remains a separate merge gate; keep draft. Older helper ratios and the unexplained single-movie gap do not establish benefit for this merged head.
