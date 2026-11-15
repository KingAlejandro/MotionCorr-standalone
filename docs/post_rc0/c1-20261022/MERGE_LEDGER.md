# C1 merge ledger (22 Oct 2026, base main `3691374061f782bc84531fd1c79d017ddcb5a7c2`, verified live)

All 14 heads re-verified live against GitHub immediately before the source freeze; none were an ancestor of main, so none was skipped as already included.
Every merge is a normal first-parent `--no-ff` merge. CI column: GitHub checks on that head (CPU build/checks and CUDA compile only; not native evidence).
Review column: latest GitHub review commit, which is older than the head for most PRs; independent source reviews recorded by the parent/ledger task
(`docs/post_rc0/orchestrator_20261022`) cover #269, #272, #241, #242, #245, #249 at the heads below. A latest-head independent review of C1 itself is still required.

| Order | PR | Head merged | Merge commit | CI | Latest GitHub review | Conflicts (all resolved as unions) |
|---|---|---|---|---|---|---|
| 1 | #267 | `66952415` | `86f7da3a` | PASS | none | none |
| 2 | #269 | `1b29b7f9` | `9ed5925d` | PASS | none | none |
| 3 | #272 | `1f0a58bf` | `1ee9cbfe` | PASS | none | none (result tree equals #272 head) |
| 4 | #254 | `b7f45176` | `d1249ec4` | PASS | COMMENTED @ `af2a5900` | none |
| 5 | #260 | `2b23fd3c` | `3d560a16` | PASS | COMMENTED @ `d888ab11` | `CMakeLists.txt` (mutant blocks), `RC0_ACCEPTANCE_REPORT.md` |
| 6 | #270 | `09ee7cb0` | `21093fe9` | PASS | none | `CMakeLists.txt` (host registrations) |
| 7 | #252 | `ad0c61a3` | `55a16659` | PASS | COMMENTED @ `1fd0aea6` | `CMakeLists.txt`, `test_ci_fail_closed.py`, `validate_test_collection.py` |
| 8 | #251 | `1dbdd47e` | `5496b903` | PASS | COMMENTED @ `4c82012b` | `RC0_ACCEPTANCE_REPORT.md`, `SUPPORT.md`, `test_ci_fail_closed.py`, `validate_test_collection.py` |
| 9 | #244 | `1b8239b1` | `495c4c92` | PASS | COMMENTED @ `88444f3e` | none |
| 10 | #248 | `855b134e` | `a21c3522` | PASS | COMMENTED @ `bbca3838` | `RC0_ACCEPTANCE_REPORT.md`, `SUPPORT.md` |
| 11 | #249 | `5791f69e` | `ca7bbe3a` | PASS | COMMENTED @ `84872649` | `RC0_ACCEPTANCE_REPORT.md`, `SUPPORT.md` |
| 12 | #245 | `b8b8adbf` | `c9372fe2` | PASS | COMMENTED @ `6530c96d` | `RC0_ACCEPTANCE_REPORT.md` |
| 13 | #242 | `430699df` | `c76536a7` | PASS | none | `CMakeLists.txt`, `RC0_ACCEPTANCE_REPORT.md` |
| 14 | #241 | `6c72a87b` | `1ff59b74` | PASS | none | `CMakeLists.txt`, `RC0_ACCEPTANCE_REPORT.md` |

Resolution notes. CMake: both sides' registrations kept (host tests, mutant blocks). Required-collection lists: union; `CUDA_SUITE` in
`tools/test_ci_fail_closed.py` = `CudaStaleErrorAfterOom, CudaPeakFit, CudaPeakFitMutant_float_denominator, CudaLocalAdmission, CudaEarlyStreamingOom,
CudaStreamingPlanClassificationCleanup`. Acceptance report and `SUPPORT.md`: every PR section kept verbatim, in merge order; both #249 entries retained
(the #214 section and the #246 compiler-settle section; #213, #215, #214 limitation bullets all present). The `## 8.` heading is used by three PRs'
sections as authored; headings were not renumbered. #274 was not merged; #273/#274 evidence trees are not in C1.

Inherited gaps (not fixed here): `TestHygiene235`, `DatasetFinalization`, `RelionErrorOwnership`, `RelionErrorUnprinted` (and others registered by
#244/#254/#270) are not in `DEFAULT_REQUIRED_TESTS`/`CUDA_REQUIRED_TESTS`; the C1 grader requires them by name independently.
