# Prospective remote regrade v2.1 of the cpu1 outputs: plan only, not authorised

This replaces `REMOTE-PLAN.md` for v2.1; the older plan is kept unchanged. It needs a fresh independent review (R2) of
`AMENDMENT-1.md`, `regrade_v2_1.py`, `EXPECT_LIVE.json`, `test_regrade_v2_1.py` and `mutants_v2_1.py` at the
committed revision, and then parent permission. Nothing remote has been run for v2 or v2.1.

**Scope.**
- **Read-only** over the immutable scratch `S = /mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1`. No native run, build, GPU query, `nvidia-smi` or movie processing, and no write anywhere below `S`.
- **No index writes.** Git runs with `GIT_OPTIONAL_LOCKS=0`, and each `.git/index` stat is checked unchanged.
- **Unchanged:** the original `RESULTS.json`, `CPU_SUBSET.json` and the subset FAIL.

**Lane.**
- 4-gpu-vm, CPU 13 only, under `taskset -c 13` (witnessed with `taskset -pc`), one numeric thread.
- A nonblocking lifetime lease `/tmp/motioncorr-guard264-cpu13-regrade.lock`; contention stops the run with no retry.
- The parent confirms CPU 13 is free of its DC reservation. A 3 s `/proc/stat` sample must show CPU 13 at 50% busy or less.
- System `python3 -I -B`, stdlib only.
- The interpreter version is recorded first. The plan requires `/usr/bin/python3` 3.8 or newer; the controls ran on 3.13.7, and the synthetic checks on 3.9.6.
- Expected cost: seconds, under 20 MB of new files.

**Namespace.** `N = /mnt/clathrin/alex-motioncorr-guard264-20261022-3751bd05a954-cpu1-regrade-v2-1-<sha12>`. It is new and outside `S`, and must not exist beforehand. It holds:
- a `git bundle create … HEAD` of the reviewed commit and its sha256;
- a clean clone of it;
- run receipts (`*.cmd`, `*.exit`, UTC start and finish, uid, `taskset -pc`).

**Steps.** Each step stops the run on nonzero exit; nothing is retried.
1. **Clone check.** `git -C N/clone rev-parse HEAD` equals the reviewed commit, and `git status --porcelain` is empty. `sha256sum` of `regrade_v2_1.py`, `EXPECT_LIVE.json`, `EVIDENCE_MANIFEST.json` and `AMENDMENT-1.md` equal the values in the R2-reviewed README. `predictions_iter2.json` is `6ff11cb5…859e`.
2. **Live precheck (pre):** `precheck-live --scratch-root S --expect N/clone/…/EXPECT_LIVE.json --proc-root /proc --out N/live-pre.json`.
   - Five trees: HEAD, diff sha256, exact status lines, runner and helper hashes. `.git/index` must be unchanged.
   - The three live binaries must equal their receipts and the EXPECT values, and be distinct.
   - No process may refer to `S`. Since the cpu1 chain is terminal (`chain.exit` 1, PIDs 3187169/3187170 and 3315461/3315463 gone), any hit is unexpected and stops the run.
3. **Files precheck:** `precheck-files --scratch-root S --manifest …/EVIDENCE_MANIFEST.json --out N/files-pre.json`. All 101 manifest hashes must match, and all 16 pair-member MRCs must meet the product contract (768×512×1, mode 2, nsymbt 0, `MAP `, 1,573,888 bytes).
4. **Grade:** `taskset -c 13 python3 -I -B …/regrade_v2_1.py grade --scratch-root S --manifest … --precheck N/files-pre.json --predictions …/predictions_iter2.json --out N/grade`.
   - The grader takes one snapshot of all 117 consumed inputs, binds them to the manifest and the precheck, re-reads them after grading, and publishes `REGRADE_V2_1.json` atomically.
5. **Post-checks:** `precheck-live … --out N/live-post.json` and `precheck-files … --out N/files-post.json`. Their tree, binary and file identities must equal the pre reports; any difference voids the regrade.

**Expected (prospective).** Exit 0 (FULL PASS) only if all of the following hold:
- the 24 CPU rows PASS under the unchanged rules;
- all 8 pairs have equal global rows;
- the payload relation recomputed from the bytes is equal for F, G and Z, and different for A_x, B_x, A_y, B_y and E;
- that relation agrees with the original booleans (contradiction gate);
- N4 exact holds.

Any other outcome is retained as a v2.1 FAIL. It is not repaired, and the original result is not changed.

**Allowed claim if FULL PASS:** "regrade v2.1 (exact global rows, validated MRC payload relation recomputed from bytes,
inputs bound and re-verified) passes the cpu1 CPU subset on TEST-ONLY overlay builds; the original raw-text grader's FAIL is
retained." Nothing about CUDA (16 rows UNRUN), the N3/N4 aggregate (INCOMPLETE), the original iteration-0a N3 (UNRUN),
production or ordinary-movie behaviour, accuracy or timing.
