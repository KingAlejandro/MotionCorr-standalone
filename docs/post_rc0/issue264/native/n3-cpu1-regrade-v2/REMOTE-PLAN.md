# Prospective remote regrade v2 of the cpu1 outputs: plan only, not authorised

The plan needs a fresh independent review of `regrade_v2.py`, `remote_precheck.py` and this plan, and then
parent permission. Nothing remote has been run for v2.

**Scope.** This is a read-only regrade of the immutable cpu1 products in
`/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1` (the "scratch"). It runs no native,
build, GPU query or movie processing, and writes nothing in the scratch. The original `RESULTS.json`, `CPU_SUBSET.json` and the
subset FAIL stay as they are. The only new input is the 16 pair-member MRC payloads, which the local archive lacks.

**Lane.** Host 4-gpu-vm, CPU 13 only (`taskset -c 13`, checked with `taskset -pc`), one numeric thread,
system `python3 -I -B` (stdlib only). A new nonblocking lease `/tmp/motioncorr-guard264-cpu13-regrade.lock`
is taken for the duration; contention stops the run. The parent confirms CPU 13 is free of its DC reservation
before GO. Before anything is read, a `/proc/stat` 3 s sample must show CPU 13 at 50% busy or less. Expected cost is a few seconds and under 10 MB of new files.

**New namespace.** `/mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1-regrade-v2-<sha12>`,
where `<sha12>` is the reviewed commit carrying these tools. It holds:
- a `git bundle create … HEAD` of that commit and its sha256;
- a clean clone of it;
- `precheck.json`;
- `out/` (the grader's `--out`);
- run receipts (`*.cmd`, `*.exit`, start and finish UTC, uid).

The namespace must not exist before the run. Nothing is retried. A failed step is kept, and any later attempt uses a new namespace.

**Bindings checked before grading (fail closed):**
1. `remote_precheck.py check --scratch-root <scratch> --manifest EVIDENCE_MANIFEST.json`.
   - Every one of the 101 consumed files (24 rows × RUN/STAR/stdout/stderr, 3 build receipts, `known-observations.json`, `RESULTS.json`) must be a regular file whose sha256 equals the value from the retained `evidence.tar` (`3cc13020…2760`).
   - The 16 pair-member MRCs must exist as regular files; their whole-file sha256 are recorded.
2. Read-only identity checks of the scratch:
   - `sha256sum build-ov-{base,cand,mut}-cpu/motioncorr` equals the receipts (`3ee3c739…`, `789e5e5b…`, `7e0b2cab…`);
   - the `src-ov-*` trees' HEAD, full diff sha256, status and runner/helper hashes equal the `check_sources.py` EXPECT values;
   - `predictions_iter2.json` in the clone hashes to `6ff11cb5…859e`.
3. The grader re-verifies every RUN.json against its build receipt, the 21 injected specs against the receipts, the receipts against the predictions, and row parity with the original `RESULTS.json`.

**Run:**
```
taskset -c 13 python3 -I -B <clone>/docs/post_rc0/issue264/native/n3-cpu1-regrade-v2/regrade_v2.py \
  --scratch-root <scratch> --predictions <clone>/docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json \
  --receipts <scratch>/n3-cpu1/known-observations.json --original-results <scratch>/n3-cpu1/RESULTS.json \
  --out <namespace>/out
```

**Expected outcome (prospective).** Exit 0 (FULL PASS) only if the payload relation matches the decisions:
- equal for F, G, Z;
- different for A_x, B_x, A_y, B_y, E.

The original grader recorded the same relation from these files, but v2 recomputes it from the bytes. Any other outcome is retained as a FAIL of regrade v2. It is not repaired and does not alter the original result.

**Allowed claim if FULL PASS:** "regrade v2 (exact global rows, MRC payload relation recomputed) passes the cpu1 CPU subset
on TEST-ONLY overlay builds; the original raw-text grader's FAIL is retained". Nothing about CUDA rows (16 UNRUN), N3/N4
aggregate (INCOMPLETE), the original iteration-0a N3 (UNRUN), production or ordinary-movie behaviour, accuracy or timing.
