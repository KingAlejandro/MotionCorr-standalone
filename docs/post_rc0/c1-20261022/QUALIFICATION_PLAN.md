# C1 qualification plan (frozen before any native run)

Candidate: `integration/c1-20261022`, built by normal merges from main `3691374061f782bc84531fd1c79d017ddcb5a7c2`.
Owner: W1 (Sonnet 5.5). Candidate-specific; `RC0_ACCEPTANCE_REPORT.md` is not edited for C1 here beyond the entries the merged PRs themselves carry.
Merge, tag, gate, tolerance, default and policy decisions (M1–M8) belong to the maintainer.

## Acceptance contract (plan of 22 Oct 2026, including the later revision)

C1 acceptance for M1 is **engineering qualification**, not scientific qualification: independent latest-head reviews; passing independent
operator oracles and discriminating controls; exact-candidate native integration/recovery evidence; required tests actually collected and run;
no unexplained or unapproved regression. Intended output changes, every remaining truth failure and its attribution/limits are published.
Bounded correctness fixes may be recommended for merge with inherited estimator failures retained, which is not a scientific PASS, a
support-class promotion or permission to relax a gate. An unexplained regression introduced by C1 blocks the merge recommendation.
Labels are PASS, FAIL, UNRUN, INCONCLUSIVE, UNIDENTIFIABLE; planned is not a pass; exit 0 is not acceptance; CI and CUDA compile-only
establish no native, science or performance claim. #264/#265/#266 are not folded in. #262 DC, #268 policy, #275/#276, #138/Metal, #273/#274
bulky evidence trees are excluded (#273/#274 are used only as references for conflict resolution and source comparison).

## Composition

Merge order (all normal `--no-ff` merges, none ancestor of main): #267, #269, #272; #254, #260, #270; #252, #251; #244, #248, #249, #245, #242, #241.
PR heads at integration: see `MERGE_LEDGER.md`. Conflicts were append-style in `CMakeLists.txt`, `RC0_ACCEPTANCE_REPORT.md`, `SUPPORT.md`,
`tools/test_ci_fail_closed.py`, `tools/validate_test_collection.py`; resolved as unions (both sides kept, `CUDA_SUITE` merged to one list).
Source comparison: `src/` and `CMakeLists.txt` numerics after #270 equal #273's composition; C1 `src/` minus the numerics equals #274's D2/D3 source.

## Fixed lane

4GPUs, GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d` only, CPUs 8–9 (max 2), numeric threads 1 unless a driver requires `--j 2`, compile parallelism 2,
shared build lock `/tmp/motioncorr-build.lock` and GPU3 lock `/tmp/motioncorr-gpu3-correctness.lock` taken nonblocking (contention = stop, no retry),
fresh occupancy before each stage, scratch `/mnt/clathrin/alex-motioncorr-c1-20261022-<source SHA12>` (<=160 GiB), inputs read in place. No timing claims.
GPU0/1/2 and CPUs 10–15 belong to other workers and are not touched. Correctness does not wait for the bench lock (#198 policy); its state is recorded.

Decoders: `pbzip2` is not on the default PATH. The pinned private copy (`/mnt/clathrin/alex-motioncorr-214/tools/usr/bin/pbzip2`, sha256
`35410d19…f21e`, v1.1.13, all libraries resolve) is verified by `c1_env.sh` and placed on the job PATH only; every configure uses
`-DMC_REQUIRE_ALL_DECODERS=ON`, so a missing decoder fails configuration instead of becoming an optional-decoder waiver. Build lock: W2 held it at
19:07 UTC (PID 3062911, verified by the parent); C1 does not wait in a loop. Configure-only trees (E1) do not compile and do not take the lock.

## Pre-launch tooling iteration

Source `579bfad8` (scratch `…-c1-20261022-579bfad8c6f1`, setup only, no native results; retained, not reused) was superseded before any native launch
after the parent's harness review of the qualification tools: (1) `c1_sticky.sh` held the GPU3 lease around a driver that takes that lease itself;
(2) post-run health failures were discarded by `c1_ctest.sh`, `c1_item.sh`, `c1_sticky.sh` (exit 37 injected, wrapper exit 0 reproduced);
(3) the sticky driver hardcodes `--j 4`/`OMP_NUM_THREADS=4` against a 2-CPU lane; (4) a single-worker dataset needs no second device;
(5) the legacy item 12 uses `--j 8` and exact-output/retry-count expectations that predate #254/#260/#270. Corrections, tooling only:
no outer sticky lock; every wrapper propagates a failed post-check as exit 37 and stops on a failed pre-check (`test_c1_wrappers.py` reproduces the
parent's mocks and asserts the corrected behaviour); the sticky row runs only in a parent-granted window of at least 4 CPUs (`C1_STICKY_CPUS`), never
oversubscribed and with an unedited driver; item 12 is derived by `make_c1_item12.py` (diff in `c1_item12.diff`) with `--j 2`, C1-derived retry
expectations, and the #207/1db86902 comparisons kept as `legacy_*` keys that are never counted as pass or problem. The bench lock is probed and
recorded, not waited on (#198 policy; `c1_lane.py`).

## Rows (verdicts are filled in `RESULTS.md` from retained receipts)

| ID | Row | Command / tool | PASS criterion |
|---|---|---|---|
| I1 | Integration identity | git ancestry of all 14 heads, no conflict markers, source diffs vs #273/#274 | every head an ancestor; no markers; numerics src equal #273; remaining src diff vs #274 only numerics and independent fixes |
| H1 | Host Python controls (macOS) | `test_ci_fail_closed`, `test_motion_diagnostics`, `test_combined_eval`, `test_realistic_*`, `test_known_motion*` | all pass; local, not native evidence |
| B1 | Release builds | `c1_build.sh` CFG=cpu, cuda, nvcomp | rc 0, `-O3 -DNDEBUG`, sha256 recorded |
| E1 | Expected collection | `c1_expected_union.py` (configure-only trees of main, each PR head, C1) | expected = main ∪ per-PR additions equals C1 listing in all 3 configs; no test removed; every required-list name collected |
| C1-cpu / cuda / nvcomp | Full CTest, three actual configurations | `c1_ctest.sh`, `c1_grade_ctest.py` | JUnit set == E1 expected == `ctest -N`; all pass; none skipped/not run; `validate_test_collection` rc 0; (cpu) `test_ci_fail_closed` rc 0 |
| F1 | Focused registrations | table from E1 `added_by_pr` | every PR-added test (#254 Hermitian*, #260 PeakFit*, #270 Realspace*, #251 EarlyStreamingOom/ClassificationCleanup, #252 LocalAdmission/PatchRetryAdmission, #244, #241 TestHygiene235, #242 DatasetFinalization, #245 RelionError*, #249 CompressedMrcStatus_*) present in JUnit and passed in each configuration that registers it. #241/#242/#245 are checked here because they are absent from `DEFAULT_REQUIRED_TESTS`. The grader additionally names `TestHygiene235`, `DatasetFinalization`, `RelionErrorOwnership` and `RelionErrorUnprinted` explicitly (all four must be in the JUnit and pass in every configuration, independent of the old lists) |
| S1 | #244 genuine sticky context, opt-in | `C1_STICKY_CPUS=<>=4 CPUs> c1_sticky.sh cuda|nvcomp` | driver exit 0 with its own held-lease health checks; separate build trees with `MC_ENABLE_STICKY_CUDA_TEST=ON`. Needs a parent-granted window of >=4 CPUs (driver hardcodes `--j 4`); **UNRUN until granted**. The driver also covers the one-worker dataset failure endpoint |
| T24 | 24 tutorial movies G/L vs frozen RC0 | `c1_tutorial24.py`; arms F-fresh (6d68e2d6 nvcomp build, read in place), N (merge #254+#260+#270 only), only254, only260, only270, C1; compare to retained F `multigpu/{G,L}/s0` | products compared with `compare_output_trees --products-only`. Expected: C1 == N (D2/D3, #241–#249 must not change products); every F→C1 difference reproduced by a named numerics arm; F-fresh == F-retained (lane control). Witness `nvcomp` on every movie. CPU: F cpu vs C1 cpu, expected identical |
| K267 | #267 eight cases, CPU + CUDA | `c1_v2.sh` | native runs complete; checker/field results retained exactly as measured (history: all non-zero cases FAIL); comparison with retained #273 composition |
| K269 | #269 100 movies, CPU + CUDA, arm none | `c1_census.py` | exit 0 per movie; C1 CUDA == retained numerics-only plain build; C1 CPU == retained main CPU; field metrics vs injected truth reported unchanged in kind (FAIL/limits retained, not judged by C1) |
| K272 | #272 image check on the C1 census sums | `image_batch.py` via existing SciPy venv | reported; no gate |
| R12 | Class R recovery, resident retry (#197) incl. D2 admission | `c1_item.sh 12` (`c1_item12.py`) | adapted item 12: frozen/count/rec/fatal arms of C1 itself pass the unchanged internal rules; retried count is C1's own (non-zero); legacy #207/1db86902 comparisons reported separately |
| D12 | One-worker dataset rows (healthy aggregation and one-worker poisoned failure) | `c1_item.sh 12ds`; `c1_tutorial24.py dataset` (24 movies G/L, vs standalone arm) | grade_dataset rules d1/dpoison_1w; 24-movie 1-worker endpoint PASS with products equal to the standalone arm. Two-worker, 4-worker and UUID-selective poison arms need a second device: UNRUN |
| R9 | adapted #123 compact matrix (route witness, compact/nvcomp ingest) | `c1_item.sh 9cuda|9nvcomp` | 16/16 rows, 28/28 arms UUID witnessed |
| A13 | Class A/D rows: truncation, damaged, compressed | CTest rows (Truncated*, DamagedMovie, WriteFaults, CompressedMrcStatus_*, EerMemorySafety, CudaFaultMatrix ...) | QF item 13 (vendored real-data harness hardcodes `--j 8`) is **UNRUN** on the 2-CPU lane |
| W1 | nvCOMP route witness on eligible TIFF | `--ingest_witness` in T24 arms | witness `nvcomp` for each of 24 movies, G and L |

Rows that need a second device (2- and 4-worker arms, UUID-selective poison, multi-device publication) stay **UNRUN** until the parent allocates one; one-worker dataset rows are not blanket-UNRUN (D12).
Not rerun by W1 and therefore keep their earlier SHA: full seven-family product campaign (QF items 5/6), #178 fallback (7), EER matrix (11), ASan (15),
SCARF, soak, performance, downstream science, genuine nvCOMP-ingest poisoning.
Intended output differences to be attributed (not approved by this plan): #254/#260/#270 CUDA products; #249 compressed MRC late-decoder failure now rejects
(former Class D characterisation of end-of-stream corruption becomes a rejection).

## Evidence rules

One qualification manifest (`manifest.json`, generated before launch) pins source SHA, archive, every tool hash and the row list. A failing stage keeps its logs
and exit receipt; `c1_stage.sh` refuses to rerun a stage name. A repaired tool or a rerun is a new iteration with a new frozen receipt and a new scratch,
never an in-place repair. Stop and report on: an unexpected product change outside the attributed fixes, a gate relaxation, a resource conflict
or contradictory evidence.
