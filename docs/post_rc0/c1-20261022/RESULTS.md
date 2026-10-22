# C1 qualification results: DRAFT checkpoint (incomplete)

**Status: incomplete draft. Not a merge recommendation; nothing here is scientific or performance qualification.** Maintainer decisions M1-M8 are untouched.
Tested source: `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (14 normal merges on main `3691374061f782bc84531fd1c79d017ddcb5a7c2`; see `MERGE_LEDGER.md`). Later commits on this branch change documents and
qualification tooling only (production-source delta empty; proven by `git diff e77a51a2 <commit> -- . ':!docs/post_rc0/c1-20261022'`). Resources: 4GPUs, GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, CPUs 8-9, builds `-j2`, no timing claims.
Independent source review: [review/REVIEW.md](review/REVIEW.md) (no material source finding; advisories answered in [review/ADVISORY_RESPONSE.md](review/ADVISORY_RESPONSE.md)). Receipts: [evidence/STAGES.md](evidence/STAGES.md), `evidence/summary/`, raw `evidence/c1-evidence-e77a51a2.tgz`.

## Rows

| Row | Verdict | Evidence and limits |
|---|---|---|
| I1 integration identity | **PASS** (git facts) | all 14 heads are ancestors; no conflict markers; numerics `src/` equals #273's composition; the independent review and the parent's preservation audit found no production-source resolution delta |
| H1 host Python controls (macOS) | **PASS** (not native evidence) | test_ci_fail_closed 8, motion_diagnostics 11, combined_eval 4, realistic_image 4, realistic_motion 13, known_motion_verdicts 8, known_motion_runner 8; run on the merged tree before the tooling commits |
| B1 Release builds | **PASS** | CPU `5692c6dc…`, CUDA `34e76812…`, CUDA+nvCOMP `d7c4e2e3…`, all rc 0, `-O3 -DNDEBUG`, `MC_REQUIRE_ALL_DECODERS=ON` with pinned `pbzip2`; sticky targets `3b6dec99…`, `ccb15a15…`; attribution builds N, only254, only260, only270 rc 0 |
| E1 expected collection | **PASS** (configure-derived, not credited to builds) | main 74/108/111; expected C1 **90/143/148** = main plus per-PR additions; missing 0, extra 0, removed 0 in all three configurations |
| C1-cpu full CTest | **PASS** | 90/90 = expected = `ctest -N`; `validate_test_collection` 0; `test_ci_fail_closed` 0 |
| C1-cuda full CTest | **PASS** | 143/143; GPU3 health pass before and after (identity, ECC, row remap, retired pages, no compute process) |
| C1-nvcomp full CTest | **PASS** | 148/148; same health receipts |
| F1 focused registrations | **PASS** | every PR-added test present and passed in each configuration that registers it; `TestHygiene235`, `DatasetFinalization`, `RelionErrorOwnership`, `RelionErrorUnprinted` required by name and passed. 16 CPU additions listed in `evidence/summary/ctest-cpu.c1grade.json` |
| S1 #244 sticky context (opt-in) | **PASS** (nvCOMP and plain CUDA builds) | unchanged driver, parent-granted 4-CPU window 8-9,14-15: healthy retry, single and three-movie poisoning (sticky error, attributed refusal, exit 1, no products), one-worker dataset failure; GPU health pass before and after |
| T24 24 tutorial movies G/L vs frozen RC0 | **UNRUN for C1** | see "Retained failed iterations" |
| W1 nvCOMP route witness (C1) | **UNRUN** | the frozen F binary showed `nvcomp` on all 24 movies (F-fresh G and L); no C1 arm has run |
| D12 one-worker dataset rows, K267, K269, K272, R12/12ds, R9, A1 (#249 GPU route) | **UNRUN** | queued behind the lane control; no result |
| A13 (QF item 13), 2/4-worker and UUID-selective poison arms, Xid log inspection | **UNRUN** | item 13 hardcodes `--j 8` (2-CPU lane); multi-device arms need a second device; kernel log needs privileged access |
| Truth failures (#267/#269/#272 cases), attribution of changed products | **no result** | inherited estimator failures are not judged by C1; attribution (`COMBINED_NUMERICS_COMPOSITION_ONLY` vs single-fix) pending T24 |

Not rerun by C1 and left at their own SHAs: full seven-family product campaign, #178 fallback, EER matrix, ASan, SCARF, soak, performance, downstream science, genuine nvCOMP-ingest poisoning.

## Retained failed iterations (nothing overwritten or relabelled)

1. **Pre-launch tool corrections** (sources `579bfad8`, `0f98ab76`: scratches kept, setup only, no results): sticky wrapper nesting the driver's lease; post-health failures ignored by wrappers; sticky driver `--j 4`; legacy item 12 `--j 8`/exact-output expectations; non-exclusive stage names; apps-only health check; census/#267 drivers `--j 8` and GPU2-first selection.
2. **T24 iteration 1** (tools packet `772f2cf5`): failed in orchestration (an escaped `$SC` in a remote heredoc gave `/t24/...` paths); all 36 comparisons were classified INVALID and the attribution stayed INVALID, as designed. F-fresh G/L (rc 0, `nvcomp` on 24 movies each) and the F-cpu G/L baselines (rc 0) are valid and retained.
3. **T24 iteration 2** (tools packet `1aac4159`, `chain-i2.sh`): stopped by its own rule at `i2-cmp-lane-G`, exit 2 (INVALID). Cause: the retained RC0 trees `W-QF/multigpu/{G,L}/{s0,w1,w2,w4}` contain no `.mrc` files, because the QF driver deleted `*.mrc`/`*.pdf` after grading; only the comparator reports (24 MRC hash triples) and the 25 STAR files survive. The F-fresh run itself was correct (24-row input matching the manifest hash, 24 witness lines `nvcomp`, 24 MRC + 25 STAR). No other iteration-2 stage ran.
4. **Repair, not yet used in a stage** (packet `4facd76d`, `tools-v2/OVERLAY.md`): `lane-hash` compares the 24 fresh MRC hashes with the retained comparator report and the 25 fresh STAR files with the retained STAR files. A read-only diagnostic of this repair on existing F-fresh outputs (not a qualification stage; directory `t24-diag-lane-hash`) gave IDENTICAL, 49/49 products for G and for L: the frozen F binary reproduces its RC0 products in this lane. Host controls: 24 tests (19 plus 5 for `lane-hash`) on macOS with the 8 Linux-only tests skipped, and the full suite OK on 4GPUs with 0 skipped.

## Changes M1 must disclose (intended or inherited, none yet attributed natively)

- #254/#260/#270 change CUDA products (C2R boundary, peak-fit arithmetic, warp border): output differences vs RC0 are expected and are not yet measured or attributed.
- #249: a compressed-MRC decoder failure at end of stream now rejects the movie (the former "accepted corruption" characterisation changes); affects CPU and GPU routes.
- #248: nvCOMP ingest declines on TIFF identity change, with host fallback under `auto` and a refusal under pinned `nvcomp`.
- #245 modifies RELION-inherited `src/error.{h,cpp}` and #249 `src/image.h` (see review A3); no numeric or format effect is claimed beyond the PR evidence.
- #251/#252: memory admission (D3 early refusal, D2 retry admission); balloon and floor claims stay at their own SHAs.
- C1 lands 756 documentation files / 48.4 MB (M2 inventory is the parent's).

## Limits

CI is not evidenced for this branch yet. Everything above that says PASS is a bounded engineering statement about the named rows on e77a51a2 and the named binaries; none is a scientific PASS, a support-class change or permission to relax a gate or tolerance. Kernel Xid inspection was not available.
