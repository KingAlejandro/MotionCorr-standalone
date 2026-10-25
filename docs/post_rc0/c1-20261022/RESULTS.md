# C1 qualification results: DRAFT checkpoint (incomplete)

**Status: incomplete draft. Not a merge recommendation; nothing here is scientific or performance qualification.** Maintainer decisions M1-M8 are untouched.
Tested source: `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (14 normal merges on main `3691374061f782bc84531fd1c79d017ddcb5a7c2`; see `MERGE_LEDGER.md`). Later commits on this branch change documents and
qualification tooling only (production-source delta empty; proven by `git diff e77a51a2 <commit> -- . ':!docs/post_rc0/c1-20261022'`). Resources: 4GPUs, GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, CPUs 8-9, builds `-j2`, no timing claims.
Independent source review: [review/REVIEW.md](review/REVIEW.md) (no material source finding; advisories answered in [review/ADVISORY_RESPONSE.md](review/ADVISORY_RESPONSE.md)). Receipts: [evidence/STAGES.md](evidence/STAGES.md) and [evidence/STAGES-iteration3.md](evidence/STAGES-iteration3.md), `evidence/summary/`, raw `evidence/c1-evidence-e77a51a2.tgz` and `evidence/c1-evidence-iteration3.tgz`.

## Dated CPU supplement, 22 October 2026 23:40 UTC

The table below retains the original iteration-3 checkpoint. Later CPU-only evidence
is separate and supersedes its blanket `UNRUN` wording only for the completed rows
listed here. Native tested source remains `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`;
all later commits are documents/tooling. No previous failed iteration is relabelled.

| Row | Current measured CPU status | Exact evidence and limits |
| --- | --- | --- |
| T24 CPU G | **PASS**, bounded engineering comparison | Parent readback22:59:43Z: native0/comparator0,24 movies/24 MRC/25 STAR each side, all24 MRC header/ext/payload hashes agree, no differing products. [G packet](cpu1d/parent-G-20261022/README.md). |
| T24 CPU L | **PASS**, bounded engineering comparison | Parent readback23:24:59Z: same complete inventory/hash/comparator checks for5×5 local. [L packet](cpu1d/parent-L-20261022/README.md). Both use unchanged output-root normalization for STAR, not raw-tree byte identity. |
| K267 CPU | **1 PASS / 5 FAIL / 2 UNIDENTIFIABLE** | C1 field/status metrics equal same-host frozen-F in all8 rows. Four native/evaluation/check stages exited0. Image/science acceptance is not implied. Historical noisy/repeated ABORT reports remain separate from repaired current sampling reports. [Single launch](cpu1d/actual-launch-attempt1/README.md). |
| K269 CPU census | **INCOMPLETE / live** at23:36:38Z | Exact chain wrapper3311648/start816540337 and chain3311661/start816540340, UID1004,CPU8–9; stage3322586/start816744577 in census. Ten prior stage exits0, no stop/done marker. This dated process observation is not a completion claim. |
| K272 CPU image and remaining recovery/GPU rows | **UNRUN / pending** | No result is inferred from the active chain. Full qualification remains incomplete; INCONCLUSIVE decision status, if later emitted, is not aggregatePASS. |

The separate `cpu1d` chain launched exactly once22:42:36Z. It keeps the numerical
helpers, stage bodies and exit allow-sets fixed, with startup-only namespace repairs;
failed cpu1c attempts remain retained. G/L CPU comparisons do not complete CUDA L
attribution or classify the known-motion image/census results. Current-head CI at
`9035a6e6` passed CPU build/smoke and CUDA compile-only, not native/science/performance.
No C1 merge recommendation follows. GPU experiments are paused under the maintainer's
choice to continue CPU and reviews. M2 review scope/M4 prototype direction/M8 parking
choices are recorded separately in PR281; no production policy or gate was adopted.

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
| T24 config G, 24 tutorial movies vs frozen RC0 | **PASS (G attribution complete, no blockers)** | iteration 3: lane control IDENTICAL (49/49); N equals C1 (0 differing products); 49 products change F to C1: 25 STAR reproduced by #260 alone, 24 MRC only by #254+#260 together (`COMBINED_NUMERICS_COMPOSITION_ONLY`, per-fix attribution unresolved); #270 alone changes nothing in G. Not a per-fix attribution of the MRC change; not scientific acceptance |
| T24 config L | **INCOMPLETE**, remaining attribution **UNRUN** | C1 L itself completed before the stop (including24 nvCOMP route witnesses, audited below). `i3-run-only260-L` stopped before launch on a foreign GPU3 process; see `ITERATION3_DIAGNOSIS.md`; remaining arms/comparisons and L attribution are not complete. |
| W1 nvCOMP route witness (C1) | **PASS**, bounded tutorial route row | Retrospective parent audit23Oct00:17:47Z verifies the already-completed C1 G and L arms:24 distinct TIFFs per arm, all`nvcomp`, exact input/RUN/build-binary bindings, lane-only UUID witness, health0/0 and cleanup empty. [Route audit](route-audit-20261023/README.md). Earlier`UNRUN` was a summary bookkeeping error; no new native run. |
| D12 one-worker dataset rows, K267, K269, K272, R12/12ds, R9, A1 (#249 GPU route), T24 CPU arms | **UNRUN** | dependent stages after the iteration-3 stop; no result |
| A13 (QF item 13), 2/4-worker and UUID-selective poison arms, Xid log inspection | **UNRUN** | item 13 hardcodes `--j 8` (2-CPU lane); multi-device arms need a second device; kernel log needs privileged access |
| Truth failures (#267/#269/#272 cases), attribution of changed products | **no result** | inherited estimator failures are not judged by C1; attribution (`COMBINED_NUMERICS_COMPOSITION_ONLY` vs single-fix) pending T24 |

Not rerun by C1 and left at their own SHAs: full seven-family product campaign, #178 fallback, EER matrix, ASan, SCARF, soak, performance, downstream science, genuine nvCOMP-ingest poisoning.

## Retained failed iterations (nothing overwritten or relabelled)

1. **Pre-launch tool corrections** (sources `579bfad8`, `0f98ab76`: scratches kept, setup only, no results): sticky wrapper nesting the driver's lease; post-health failures ignored by wrappers; sticky driver `--j 4`; legacy item 12 `--j 8`/exact-output expectations; non-exclusive stage names; apps-only health check; census/#267 drivers `--j 8` and GPU2-first selection.
2. **T24 iteration 1** (tools packet `772f2cf5`): failed in orchestration (an escaped `$SC` in a remote heredoc gave `/t24/...` paths); all 36 comparisons were classified INVALID and the attribution stayed INVALID, as designed. F-fresh G/L (rc 0, `nvcomp` on 24 movies each) and the F-cpu G/L baselines (rc 0) are valid and retained.
3. **T24 iteration 2** (tools packet `1aac4159`, `chain-i2.sh`): stopped by its own rule at `i2-cmp-lane-G`, exit 2 (INVALID). Cause: the retained RC0 trees `W-QF/multigpu/{G,L}/{s0,w1,w2,w4}` contain no `.mrc` files, because the QF driver deleted `*.mrc`/`*.pdf` after grading; only the comparator reports (24 MRC hash triples) and the 25 STAR files survive. The F-fresh run itself was correct (24-row input matching the manifest hash, 24 witness lines `nvcomp`, 24 MRC + 25 STAR). No other iteration-2 stage ran.
4. **Repair, now used in iteration 3** (packet `4facd76d`, `tools-v2/OVERLAY.md`): `lane-hash` compares the 24 fresh MRC hashes with the retained comparator report and the 25 fresh STAR files with the retained STAR files. A read-only diagnostic of this repair on existing F-fresh outputs (not a qualification stage; directory `t24-diag-lane-hash`) gave IDENTICAL, 49/49 products for G and for L: the frozen F binary reproduces its RC0 products in this lane. Host controls: 24 tests (19 plus 5 for `lane-hash`) on macOS with the 8 Linux-only tests skipped, and the full suite OK on 4GPUs with 0 skipped.
5. **T24 iteration 3** (tools packet `4facd76d`, frozen chain `397275b1…`, manifest `07e3dec2…`, launched once at 21:23:53Z): lane-hash IDENTICAL for G and L, G fully completed (attribution above), L completed through `only254`, then **stopped at `i3-run-only260-L`** (exit 1) because another user's `llama-server` (PID 3276184, user `dvi41342`) had a context on GPU3: an admission stop before launch, not a native failure. Details and the proposed iteration 4 are in [ITERATION3_DIAGNOSIS.md](ITERATION3_DIAGNOSIS.md); receipts in `evidence/STAGES-iteration3.md` and `evidence/c1-evidence-iteration3.tgz`; parent readbacks in `evidence/parent-readbacks/`.

## Changes M1 must disclose (intended or inherited)

- #254/#260/#270 change CUDA products (C2R boundary, peak-fit arithmetic, warp border): G differences are measured with the bounded composition attribution above; individual-fix MRC attribution and L attribution remain incomplete.
- #249: a compressed-MRC decoder failure at end of stream now rejects the movie (the former "accepted corruption" characterisation changes); affects CPU and GPU routes.
- #248: nvCOMP ingest declines on TIFF identity change, with host fallback under `auto` and a refusal under pinned `nvcomp`.
- #245 modifies RELION-inherited `src/error.{h,cpp}` and #249 `src/image.h` (see review A3); no numeric or format effect is claimed beyond the PR evidence.
- #251/#252: memory admission (D3 early refusal, D2 retry admission); balloon and floor claims stay at their own SHAs.
- C1 lands 756 documentation files / 48.4 MB (M2 inventory is the parent's).

## Limits

Current-head CI and final evidence review remain pending; the earlier9035a6e6 CPU/CUDA checks are recorded in the dated supplement. Everything above that says PASS is a bounded engineering statement about the named rows on e77a51a2 and the named binaries; none is a scientific PASS, a support-class change or permission to relax a gate or tolerance. Kernel Xid inspection was not available.


## 25 October bounded native completion (additive; engineering incomplete)

See [native packet](native-remaining-20261025/README.md) and [inner grades](native-remaining-20261025/PARENT-GRADE.json). Production source remains `e77a51a2`; the new helper is read-only qualification tooling.

- R9 CUDA/nvCOMP: each16/16 cases PASS,28/28 UUID-witnessed arms.
- #249 compressed-reader status: six CUDA/nvCOMP × codec rows, each12 cases with no failures.
- D12 G/L: native one-worker endpoints PASS/ready24; original comparison FAIL/INVALID on archived worker STAR retained. Separately reviewed v1.1 grades: canonical49 products IDENTICAL, archive inventory/bytes/exit hashes verified. No G native rerun. V1 import failure preserved.
- K267 CUDA:8 native exits0; checker1 PASS/5 FAIL/2 UNIDENTIFIABLE, including invalid noisy/repeated sampling. This does not establish truth accuracy or erase historical ABORT records.

Still held/UNRUN: genuine sticky-context window>=4 CPUs, real-data A13 `--j8`, CUDA K269/K272 census, multi-device dataset/UUID poison/publication, genuine ingest poisoning and Xid inspection. No aggregate C1/M1 PASS, scientific promotion or performance claim. Existing earlier-source rows keep their original identities.
