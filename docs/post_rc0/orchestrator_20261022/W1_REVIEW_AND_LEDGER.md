# W1 independent source reviews and live ledger, 22 October 2026

Reviewer: W1 task (claude-sonnet-5-5), which authored none of the six PRs. Branch `docs/orchestrator-ledger-20261022`, based on `origin/main` `3691374061f782bc84531fd1c79d017ddcb5a7c2`. Production source, tests and root checkout are unchanged. No remote or GPU compute was run.

Live data: `pr_ledger.csv` and `pr_ledger.json` (29 open PRs, refreshed from GitHub this cycle; checks queried by head SHA). `c1_pairwise_merge_conflicts.json` records `git merge-tree` results for the C1 candidates.

**The "latest-head review" column means a review recorded on the current head.** GitHub shows no review at all on #267, #269, #270, #272, #241 and #242, so this report is the first review of the current head for those PRs that I could find. Every "KingAlejandro" review is the same account the agents post from, so I cannot tell from GitHub who reviewed. The parent supplied no prior-review facts for these six, so I treated each as having no earlier source review except #245 and #249 below.

## Result by exact head

| PR | Head reviewed | CI on this head (CPU build / CUDA compile only) | Material findings | Source review basis |
|---|---|---|---|---|
| #269 | `1b29b7f9` (base #267 `66952415`) | success / success | none | this task |
| #272 | `1f0a58bf` (base #269 head) | success / success | none | this task |
| #241 | `6c72a87b` | success / success | none | this task |
| #242 | `430699df` | success / success | none | this task |
| #245 | `b8b8adbf` | success / success | none | this task; older review at `6530c96d` |
| #249 | `5791f69e` | success / success | none | this task; older review at `84872649` |

"No material findings" is a statement about source correctness, failure and metadata behavior, scope and GPL compatibility at that head. It is not a merge recommendation: no native evidence exists on any of these exact heads except as listed under "historical" below, and CI is CPU build plus CUDA compile only.

All six heads are MERGEABLE/CLEAN against their own base. They conflict with each other (see C1 integration below). All six heads fetched from origin match the live PR head SHAs.

### #269 and #272 (with the #267 checker they stack on)

Stack contract: `66952415` (#267 head) is an ancestor of #269 `1b29b7f9`, which is an ancestor of #272 `1f0a58bf`. `tools/check_motion_diagnostics.py`, `tools/test_motion_diagnostics.py` and `test-data/generate_motion_diagnostics.py` are byte-identical across #267, #269 and #272. #269's non-evidence diff against #267 is 6 files (CI line, `generate_realistic_motion.py`, `check_realistic_motion.py`, `run_realistic_motion_census.py`, `summarize_realistic_motion.py`, `test_realistic_motion.py`). #272's is `check_realistic_image.py`, a census-driver edit, `test_realistic_image.py`, `test_combined_eval.py`, the `eval_v2.py` repair and one CI line.

Checked in source:

- **Sampling and status** (`tools/check_motion_diagnostics.py:62-85`). Truth sampling that leaves the ROI stays an input error (exit 2). Candidate sampling that leaves the ROI sets `sampling_status=OUTSIDE_FIXED_ROI`, keeps all field metrics and sets `signal.estimated_motion_bilinear` to JSON null; exit is 1 (`:216`). The accuracy gate (RMS 0.20, P95 0.40, max 0.80 Å) is unchanged and `UNIDENTIFIABLE` still applies only to flat/repeated signals (`:71-74`).
- **Image contract** (`:186-194`). A malformed or nonfinite summed image remains exit 2, not a quality state. `check_realistic_motion.py:50-54` also reports sampling status without aborting.
- **Fresh invocation reports** (`docs/post_rc0/s1/synth_combined/eval_v2.py`, `1f0a58bf`). Each checker call writes to a private temp path and only a report from that invocation with exit 0 or 1 is consumed and copied. Exit 2 yields `ABORT_NO_RESULT`, no `image`, no `sampling_status`, and the cached report bytes are unchanged.
- **Ancestor root discovery** (same file). The nearest ancestor containing both `tools/check_motion_diagnostics.py` and `test-data/generate_motion_diagnostics.py` is used; a copy under a source root with symlinked `tools`/`test-data` works.
- **Census failure handling** (`run_realistic_motion_census.py:96-97`, `summarize_realistic_motion.py:41-42`). A partial seed or an existing arm directory fails loudly rather than being overwritten; a nonzero native exit cannot enter the accuracy table; nonconvergence is counted separately from exit status.

Bounded local checks, macOS arm64, Python 3.13.7, NumPy 2.4.2, SciPy 1.17.1, one numeric thread, host load about 7-11 on 14 CPUs: at #272 `1f0a58bf`, `tools/test_motion_diagnostics.py` 11 tests OK, `test_combined_eval.py` 4 OK, `test_realistic_image.py` 4 OK, `test_realistic_motion.py` 13 OK (each rc 0).

Discriminating mutants (run on a copy of `1f0a58bf`, nothing retained in the repo):

- Old `eval_v2.py` from `a6a40e8f`: `test_combined_eval.py` fails 3 of 4 tests (wrong source root, cached report consumed).
- `check_motion_diagnostics.py` with the `except InvalidSamplingError` clause disabled: `test_combined_eval.py` fails 1 and `test_motion_diagnostics.py` fails 8 (3 fail, 5 error).

Retained evidence: the four `evidence/v2-comb-*.eval.json` files were produced by the earlier evaluator and still show `noisy`/`repeated` as `checker_exit` 2, `ABORT_NO_RESULT`, no `sampling_status`. The README states they keep their original source identities. They are historical and are not re-evaluated by the fixed wrapper; no result there was changed.

Low-severity findings (neither blocks the stack):

1. `tools/check_motion_diagnostics.py:212` writes the JSON report outside the `try`. A finite candidate that overflows a metric makes `json.dumps(allow_nan=False)` raise. Reproduced: with the `zero` case and a STAR whose frame-5 `_rlnMicrographShiftX` is `1e200`, the CLI prints `ValueError: Out of range float values are not JSON compliant: inf`, exits 1 and writes no report. That exit code is the documented exit for sampling failure or gate failure. `eval_v2.py` is unaffected because it requires the report file to exist. Native outputs are not expected to reach this. The same file is shared by #267, #269 and #272.
2. `docs/post_rc0/s1/synth_combined/image_batch.py:23` and `tools/check_realistic_image.py:183` reuse a cached truth scene. The batch driver keys it by geometry only; the CLI keys it by nothing. Today every condition shares the scene parameters, so no wrong result is possible. A receipt with a different `scene_seed`, `texture_rms` or `oversample` and the same geometry would silently reuse the wrong truth.

Operational note for any rerun of the census (not a source defect): `run_realistic_motion_census.py:30` picks the first idle GPU in order 2, 3, 1, 0, independent of `--cpus`, and releases its lock when `run_seed` returns (`:101-102`), so no final-health check runs under the lock. Pass explicit CPU masks consistent with the current #198 policy and verify the NUMA/GPU pairing before using it.

### #241 (issue #235)

Source change: `tools/profiling/mcprof.py` `cmd_selftest` now keeps selftest scratch, including child processes, on local `/tmp` and restores `tempfile.tempdir` and `TMPDIR`; `tests/test_truncated_gain_defect.py:157` turns a missing Pillow with supplied EER inputs from a silent skip into a recorded failure. Optional EER stays optional (`:151-153` unchanged).

Checks: `tests/test_hygiene_235.py` passes (2 tests) at head. Copied onto `origin/main` it fails both tests (rc 1): the late-file `rmdir` model reproduces `ENOTEMPTY`, and the old `eer_section` returns no failure without Pillow. No material finding. Not verified: PanFS itself (the PR also says so), native CUDA.

Observation: the new `TestHygiene235` test is not added to `DEFAULT_REQUIRED_TESTS` in `tools/validate_test_collection.py`, so losing its CMake registration would not trip the collection gate. Same for #242's `DatasetFinalization`.

### #242 (issue #240)

`tools/multi_gpu/run_dataset.py`: `main()` now wraps `_main()`; the finalization `finally` raises a private `_RestorationFailed` instead of `return 3`, and `main()` returns 3. I walked the semantics: `restoration_failed` can only be true after `verdict=='PASS'`, which is set immediately before `return 0`, so the only paths are the success return and a `BaseException` raised in that window. Old code swallowed either and returned 3; the new code replaces either and returns 3. Status write and handler restoration order are unchanged. Other importers (`tests/test_process_ownership.py`) call `main`/module symbols unchanged.

Checks: `test_dataset_finalization.py` OK at head; on main with Python 3.14 it fails the static no-finally-return control. Under Python 3.14.8 with `-W error::SyntaxWarning`, `compile()` of `run_dataset.py` fails on main (rc 1) and passes at head (rc 0). `test_dataset_endpoint.py` rc 0 (Python 3.14, no NumPy). No material finding. The semantic subtests pass on main as well, so only the static control discriminates; that is the defect in question.

### #245 (issue #239)

`src/error.h` changes `RelionError::backtrace_buffer` from `void**` to `std::vector<void*>`; `src/error.cpp` uses `.data()` and removes the delete that made printing consume the buffer. No other user of `backtrace_buffer` exists in `src`, `tests` or `tools`. I built the new test with clang and `-fsanitize=address`: at head both modes exit 0; with the same test against main's `error.cpp`, ASan reports a double free in `operator<<` (`error.cpp:82`). No material finding.

The earlier review's non-blocking follow-up is still open: `RelionErrorOwnership` and `RelionErrorUnprinted` are not in `DEFAULT_REQUIRED_TESTS`. The leak case needs LeakSanitizer, which exists only in the retained Linux sanitizer records, not in the ordinary `--unprinted` test.

### #249 (issue #214)

**Both acceptance entries are retained.** `git diff origin/main origin/check-decompressor-exit-status -- docs/release/RC0_ACCEPTANCE_REPORT.md` has 0 deleted lines and adds the `## 8. Post-RC0 fixes` #214 entry; main's `## Post-RC0 #246` section is still present (line 278 vs 256 on main). Source semantics: `CompressedMRCReader::finish()` drains, checks `ferror` and `pclose`, clears the pipe before reporting; the runner calls it only when `n_frames == nn` (every header frame selected, including explicit first=1/last=N), after the serial read-error rethrow. Header-only (`micrograph_model.cpp:631`) and subset reads keep early close. Between the natively tested `39aca256` and head, the only non-doc change in `src`/`tests`/`tools`/`CMakeLists.txt` is the #247 test merge (`tools/profiling/tests/test_import_subset_boundaries.py`).

I did not build or run the native decoder tests (no binary available locally; the retained logs are a CPU/CUDA/nvCOMP record at `39aca256`). No material finding.

Untested corner, not a finding: every nonzero decoder status now rejects a full read, including a warning-only status such as `xz`'s documented exit 2. No fixture covers it.

## Ledger notes (full data in `pr_ledger.csv`)

- 29 open PRs; all have both CI checks green on their current head except #52, which has no checks. CI is CPU build plus CUDA compile only.
- Latest GitHub review is on an older head for #243, #244, #245, #248, #249, #251, #252, #254, #260, #64 and #65. The head moved past the review for each of these; none of those reviews covers the current head. #255, #261 and #250 have a review on the current head; #138 has only a bot comment.
- No review on any head: #267, #269, #270, #272, #241, #242, #256, #271, #273-#276 (the parent states #275/#276 were independently reviewed; I did not find that review on GitHub).
- Issue changes since 21 October that bear on the work: #238 updated at 18:43 UTC today; #253, #257-#259, #262-#266 and #268 were updated on 21 October and are still open. No new owner or PR for #258, #263-#266 or #268 appeared among open PRs.
- Main is still `36913740` and has changed no production source since `c8844894` (only #247 docs and a profiling test). Native evidence on `c8844894`-based heads of #241, #242, #245 and #249 is therefore on source equal to main's production source. This is recorded in the CSV as historical SHA equivalence and is not an exact-head native PASS.

## C1 integration (for the parent's separate C1 worker)

Pairwise `git merge-tree` over twelve C1 candidates (#254, #260, #270, #252, #251, #244, #248, #249, #245, #242, #241, #272) shows 22 conflicting pairs of 66. Every conflict is in `docs/release/RC0_ACCEPTANCE_REPORT.md`, `docs/release/SUPPORT.md`, `CMakeLists.txt`, `tools/test_ci_fail_closed.py` or `tools/validate_test_collection.py`. All are append-style additions. Production sources never conflict in these pairs. The same both-entries rule that applied to #249 recurs for #241/#242/#244/#245/#248 in the acceptance report; the CMake and collection-list conflicts need the union of registrations. My sequential simulation attempt did not complete (the union-merge step did not commit), so I have not verified an ordered C1 merge and make no claim about its result.

## Missing qualification rows

| Row | PRs | Status |
|---|---|---|
| Exact-head native execution (CPU, CUDA, CUDA+nvCOMP full CTest, actual vs expected collected counts) | #249, #245, #242, #241 | UNRUN on current head; historical results above |
| Native CUDA execution for the numerical set | #254, #260, #270, #251, #252, #244, #248 | not examined in this task |
| C1 composition: all fixes together, 24-movie baseline comparison, route witness on eligible TIFF, Classes A/D/E/R rows | C1 | UNRUN |
| #269/#272 native campaign on the combined C1 binary | #269, #272 | UNRUN; existing campaign was on #273's composition (`d751ff28`) |
| LeakSanitizer on Linux for #245 at current head | #245 | UNRUN on current head; retained at `1c14e888` |
| PanFS retest, real EER inputs | #241 | UNRUN |
| Decoder warning-exit fixture; pbzip2 native on local host | #249 | UNRUN |
| Required-test registration in `DEFAULT_REQUIRED_TESTS` | #241, #242, #245 | absent |
| Independent latest-head review recorded on GitHub | #267, #270, #273-#276 and the PRs listed above whose head moved | missing or stale |

## Decision-queue suggestions

- **M1 (merge C1).** Not recommended yet, and nothing here is a merge recommendation. Source review is complete for the six PRs. Remaining blockers are the UNRUN rows above and fresh independent latest-head reviews for #244, #248, #251, #252, #254 and #260, whose heads moved after their GitHub reviews. Per the updated plan, M1 can proceed on engineering evidence only: no unexplained regression, intended output changes published, every inherited truth failure listed.
- **M2 (bulky evidence trees).** #269 adds 38.5 MiB of blobs, mostly `raw.tar.gz`, `native_v2_raw.tar.gz` and `SUMMARY.json.gz`; #272's evidence is 0.4 MiB. Suggest the maintainer decide on #269's archives specifically: keep the compact CSV/JSON tables on main and leave the raw tarballs on the branch, with a hash index on main.
- **M8 (legacy PRs).** No new evidence from this task. #64, #65 and #138 have bot comments only on older heads; #52 has no checks. Per the plan, #65 stays the S1.4 protocol source. I did not expand queue-hygiene work.
