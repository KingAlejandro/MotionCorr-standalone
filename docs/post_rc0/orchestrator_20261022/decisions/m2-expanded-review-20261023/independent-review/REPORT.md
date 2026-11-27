# M2 retention review: dependency and provenance (read-only)

Scope: retention REVIEW only. No deletion, move, history rewrite, merge-mode change or merge was done or proposed, and no retention option is adopted. No source, native, science or policy conclusion. Every PASS/FAIL/UNRUN/INCONCLUSIVE/UNIDENTIFIABLE record is untouched. This task made no repo edit, commit, push, Notion or GitHub write, SSH, build or GPU use, and no archive was extracted or executed.

## Pinned refs (all resolved locally, full SHA)

| Ref | SHA |
| --- | --- |
| main | `3691374061f782bc84531fd1c79d017ddcb5a7c2` |
| C1 as pinned by PR281 (`e77`) | `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` |
| C1 as published now (`bbf`) | `bbf24607dec537bd13351f061047ea38bd38237b` |
| PR281 head reviewed | `1b15f10b423c246bd25a6cb7b9252954f7a97131` |
| #269 (selected layer) | `1b29b7f9eea1976a0b7a9e2ef5f9ca00477324b1` |
| #273 / #274 heads | `805d9de27898b4a10e6212e65098d5995a40fdb1` / `a1036901bbc17900a0c515ad047efb50449c14f7` |

- Main is an ancestor of e77, bbf and 1b15. e77 is an ancestor of bbf.
- e77..bbf is 16 commits and 158 changed paths, **all under `docs/`** (`git diff --name-only e77 bbf | grep -v '^docs/'` returns 0 lines).
- The scoped trees (`src`, `tests`, `tools`, `cmake`, `.github`, `CMakeLists.txt`, `ci.yml`) have identical oids at e77 and bbf. The prior source-side classification therefore carries over to bbf. Docs trees and history differ, and this report gives both columns.
- The local `origin/docs/orchestrator-ledger-20261022` ref is now `b3fc4692`, one docs commit after 1b15f10b ("record maintainer review scope and parked PR selections", 16 files, +427). The review is pinned to 1b15f10b as asked. I did not refresh live GitHub.
- PR281 numbers are pinned to e77. This review does not relabel them. Re-running the PR281 recipe (sha256 `16ed1f12…`) on e77 reproduces its committed tree JSON byte-for-byte and its history `results` and `recipe` exactly. The same recipe on bbf gives the bbf column below.

## Result

1. **The 57 `docs/` hits are classified.** Only 22 of 90 hit lines (15 files) read a docs path at run time. The other 68 are comments, links, strings, a generated-output default, or false positives. The full list is `DOCS_REFS_TABLE.md` and `out/docs_refs_classified.csv`.
2. **Two docs trees that C1 adds (absent from main) are read by tests that CI runs.** Any retention option that removes or relocates them breaks those tests:
   - `docs/issue213/evidence/` (92 files, 322,972 B), read by `StickyCudaProcessLifecycle`.
   - `docs/post_rc0/s1/synth_combined/eval_v2.py` (the directory is 37 files, 376,409 B), run by CI step `tools/test_combined_eval.py`.

   The PR281 M2 draft says the first is something "C1 changes" and does not mention the second.
3. **`km_truth/raw.tar.gz` (34,973,613 B) is not read by any test, CMake, CI or docs script.** It is a bulky raw evidence archive, identical to selected #269 at blob level. It holds the only in-tree copies of two campaign scripts.
4. **The only archives with a committed reader are all docs-internal and manual.** `native_v2_raw.tar.gz`, `d2/native_retry/raw-logs.tgz` and #274's `raw-logs.tgz` are read by verify scripts. `SUMMARY.json.gz` is read by the report generators.
5. **`verify_composition.py` needs history objects.** It runs `git show/diff` on three commits that are ancestors of C1 and not of main.
6. **Retrieval is verified locally only.** Commits and blobs are present and intact in this clone. The remote pinned URL is not verified.

## Dependency classification of `docs` references

Scope was `src tests tools cmake .github CMakeLists.txt` at e77. There is no `cmake/` directory in the tree, and `ci.yml` contains no `docs` string. Hits came from `git grep -E 'docs/'` plus `git grep -w docs`, which finds path joins like `/ "docs" /`. The second grep added 3 files to the prior 57-file count.

| Class | Lines | Files | Meaning |
| --- | ---: | ---: | --- |
| ACTIVE (all sub-classes) | 22 | 15 | code opens, imports or runs the path |
| COMMENT_OR_LINK | 60 | 42 | docstring, comment or markdown pointer; not executed |
| STRING_LITERAL | 4 | 4 | CLI help, printed or error text |
| GENERATED_PATH | 1 | 1 | output default, never read |
| FALSE_POSITIVE | 3 | 3 | `onlinedocs/` URL (`float16.h:53`), `docs.amd.com` (`error.h:173`), SQL comment "See docs for format" (`nsys_2024_6_schema.sql:216`) |

Several files have more than one class, so file counts do not sum to 60.

### Active reads (every one, with the registration that makes it run)

| file:line | Referenced path | Runs under | Path at main / C1 |
| --- | --- | --- | --- |
| `tests/test_compare_output_trees.py:16` | `docs/issue85_laneC/compare_output_trees.py` | CPU ctest `OutputTreeComparator`, run by CI | same tree oid on main |
| `tests/test_sticky_cuda_process_lifecycle.py:245` | `docs/issue213/evidence/control-{cuda,nvcomp}-final/{single,multi}.txt` (3,028, 6,708, 3,123, 6,831 B) | CPU ctest `StickyCudaProcessLifecycle` (UNIX), run by CI | **absent from main; new in C1** |
| `tools/test_combined_eval.py:16` | `docs/post_rc0/s1/synth_combined/eval_v2.py` (3,202 B) | CI step `ci.yml:105` (not ctest) | **absent from main; new in C1** |
| `tests/run_stale_cuda_error_controls.py:54` | `docs/issue85_laneC/compare_output_trees.py` | CUDA hardware ctest `CudaStaleErrorAfterOom` | on main |
| `tests/run_preprocessing_failure_controls.py:70` | same comparator | CUDA hardware ctest `CudaPreprocessingFailurePaths` | on main |
| `tests/run_preprocessing_failure_controls.py:69` | `docs/issue69/evidence/ownership-20260929/compare-native.py` | only with `--float-host`, which no CMake test passes | on main |
| `tests/run_tiff_identity_later_chunk_controls.py:19` | `docs/rc0/qf/tools/compact_compare_output_trees.py` (imports stdlib and numpy only) | CUDA+nvCOMP hardware ctest `CudaNvcompTiffIdentityLaterChunk` | on main |
| `CMakeLists.txt:1224` | `docs/issue85_laneC/compare_output_trees.py` as add_test argv | opt-in `CudaU16FailurePaths`, only with `-DMOTIONCORR_U16_TEST_MOVIE` | on main |
| `tests/run_enumeration_boundary_control.py:27` | `compare-native.py` (default `--comparator`, run at `:112`) | not registered (manual) | on main |
| `tools/gate_representations.py:18,19` | `docs/cuda_24_movies_gate2_rerun.json`, `docs/spa_24_movies_manifest.json` | not registered (manual) | on main |
| `tools/nsys_analysis/selftest.py:150,207` | `docs/profiling_20261001/data24/arms24.json` (4,494,591 B) | not registered (manual); the check fails if the file is absent | on main |
| `tools/single_gpu/{run_dose_options,run_option_matrix}.py:6,7`, `run_dose_pairs.py:50,135`, `run_pairs.py:25,97`, `refresh_profile.sh:23` | `docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json}` | not registered; read from the caller-supplied `--source` or `$D/baseline-src` tree, not this checkout | on main |

Notes:
- **Docs trees that C1 does not change.** `issue85_laneC`, `rc0/qf/tools`, `issue69/evidence/ownership-20260929`, `profiling_20261001/data24` and the two gate JSONs have identical tree oids on main, e77 and bbf. The two "absent from main" rows (`issue213/evidence`, `synth_combined`) are the only active targets that arrive with C1.
- **Not wired into CTest or CI.** Nothing under `docs/post_rc0/c1-20261022` or `km_truth` is referenced by any non-docs path except the docstring `test-data/generate_realistic_motion.py:5`.
- **No archive is a test input.** No active read opens an archive. The archive readers are all inside docs (below).
- **Draft wording to correct.** The PR281 M2 draft lists `tutorial_24_movie_manifest.json` with the test dependencies. It is read only by the unregistered `tools/single_gpu/*` scripts via `--source`.
- **Comment targets that do not resolve.** Five distinct targets resolve at neither main nor C1; they exist only on other branches:
  - `docs/output_timing_20260930/mutants.txt` (`multidim_array.h:2712`, `test_runner_numerics.cpp:223`)
  - `docs/issue69/gpu_plan.md` (`cuda_fault_matrix.cpp:23,379`)
  - `docs/multi_gpu/negative_controls.py` and `docs/multi_gpu/gpu_evidence/a0_device_list_witness.log` (`test_multi_gpu_scheduling.py:12,16`)
  - `docs/issue95_staging` (`test_native_movie_staging.cpp:222`)

  These were unresolved before C1 and are evidence links only. `run_stale_cuda_error_controls.py:25` is not a dangling target; the regex captured a function name.
- **Supplementary out-of-scope mentions** (not line-classified): `README.md` 10, `agents/designs/*` 11 lines in 6 files, `test-data/README.md` 4, `test-data/*.py` and `real_cutdown_plan.json` 1 each. All are links or comments.

## Archive inventory and dependency (headers and hashes only)

Method: `git cat-file` into hashlib and Python `tarfile` in stream mode, which reads member headers only. I did not hash, read or extract any member. 20 distinct archive blobs came from the main→tip docs diffs of e77, bbf, #273 and #274. For each blob I recomputed the git object id from content (all 20 match) and its sha256.

**Archive count and bytes.** At e77 there are 11 archives, 38,643,183 B. At bbf there are 16 (the 5 added are `c1-20261022` receipts), 39,240,108 B. There are 3 more unique to #273 and 1 more unique to #274. None of the 20 is on main. The full table with per-archive reader, recorded-digest location and member counts is `COMPONENT_TABLE.md` and `.csv`.

### Component table (compact; sizes logical)

| Component | Digest / size | Tip or history | Dependency class | Retention requirement | Retrieval evidence or gap |
| --- | --- | --- | --- | --- | --- |
| `docs/post_rc0/s1/km_truth` tree, 48 files | tree `1a0118ec`, 40,290,016 B | tip of #269, e77, bbf (same tree oid); plus 15 history-only versions (1,966,508 B) | evidence plus docs-hosted tools; no src/tests/tools/CI read; one manual script reads inside it | preserve as committed, or a verified retrieval | tree-oid equality verified locally |
| `km_truth/raw.tar.gz` | blob `bc962a97`, 34,973,613 B, sha256 `4b0afb90…ce8dd` | tip; added once by commit `678b0453`; no other versions | **bulky raw evidence archive**: 9,198 regular files, 153,433,730 B uncompressed; read by no test, CMake, CI or docs script | evidence; the retention decision is the maintainer's | equal to #269 by blob oid; recorded in `ARTIFACTS.sha256:35` and equal to recomputed |
| `km_truth/native_v2_raw.tar.gz` | `f058c937`, 536,160 B | tip | **executable fixture dependency** (docs-internal): `verify_composition.py:98-101`; 205 members (185 files, 20 dirs) | keep with `native_v2_raw_index.json` and the script | recorded in `ARTIFACTS.sha256:25`, equal |
| `km_truth/SUMMARY.json.gz` | `dd5c038d`, 521,940 B (3,466,021 B decompressed) | tip | generator input: `build_report.py:8`, `export_tables.py:6` | keep with generators | recorded, equal |
| `issue226/d2/native_retry_20261022/raw-logs.tgz` | `ce874507`, 313,875 B, 156 members | tip e77/bbf/#274 | **executable fixture dependency**: `support/verify.py:7-14` | keep with `archive.sha256`, `raw-index.json` | `archive.sha256` equal |
| #274 `integration_20261022/raw-logs.tgz` | `81c3680d`, 695,240 B, 647 members | **#274 tip only** (not in C1) | **executable fixture dependency**: `support/verify.py:7-10` | the M2 question | `archive.sha256` equal |
| #273 `numerics/native-receipts.tar.gz` | `df005b1e`, 1,390,257 B, 536 members (16 tiny `.mrc`) | **#273 tip only** (not in C1) | raw receipts; written by `collect_remote.py`; no committed reader found | the M2 question | recorded in README:168 and `archive-verification.json:9`, equal |
| Other C1 raw archives (d2/d3 raw-logs, d3 receipts, issue253 ×2, issue257, issue215, 5 bbf-only) | 9 at e77 and 5 more at bbf; 89,590 to 1,044,455 B | tip | raw evidence; **no reader** | evidence | see gaps below |
| `synth_combined/` (37 files) | tree `4ce7b7c7`, 376,409 B | tip e77/bbf, **absent from main** | **ACTIVE CI dependency** (`eval_v2.py`) | must stay reproducible with the C1 tests | present at e77 and bbf |
| `issue213/evidence/` (92 files) | tree `bbf98b2c`, 322,972 B | tip e77/bbf, **absent from main** | **ACTIVE ctest dependency** (4 files) | must stay reproducible with the C1 tests | present at e77 and bbf |
| Reachable history main..e77 (PR281-pinned) | 102 commits; 947 blobs, 60,411,705 B (730 / 49,466,987 in tip; 217 / 10,944,718 history-only) | history | n/a | n/a | reproduces PR281 exactly |
| Reachable history main..bbf (current) | 118 commits; 1,099 blobs, 61,752,600 B (869 / 50,703,396 in tip; 230 / 11,049,204 history-only) | history | n/a | n/a | new values; not PR281-pinned |

The remaining 8 rows of the 21-row `COMPONENT_TABLE.csv` (per-archive detail, the #273 and #274 unique-tree totals, and the docs trees unchanged since main) are not repeated here.

### Facts behind the table

**`km_truth/raw.tar.gz`**
- **Contents.** Extension counts are json 3,597, star 1,928, log 1,832, lst 911, txt 904, py 12, stdout 7, exit 6 and one file with no extension. There are no image or movie members, no links and no exec bits.
- **Digest cross-check.** `raw.sha256` has 9,198 entries and the tar has 9,198 member names. The two name sets are identical, and the sha256 of `raw.sha256` itself equals the recorded `06313e2c…`. Member bytes were not recomputed.
- **Script copies.** Of its 12 `.py` members, 7 have recorded digests equal to a tracked file (six `km_truth` copies and `test-data/generate_realistic_motion.py`). Three differ from the current tracked versions: `transfer_direct.py`, `tools/run_realistic_motion_census.py` and `tools/check_realistic_motion.py`. **`generate_campaign.py` and `transfer_direct_zstd.py` have no tracked file anywhere.** This comparison used the recorded digests, not the archive's member bytes.
- **Selected #269.** The `km_truth` tree oid `1a0118ec` is the same at 1b29b7f9, e77 and bbf, so all 48 files are identical to the selected layer.

**The other km_truth archives.** `native_v2_raw.tar.gz` and `SUMMARY.json.gz` are real inputs to docs scripts. `verify_composition.py:19` sets `ROOT = parents[5]`, so it only works at its committed depth.

**Pinned history dependency.** `verify_composition.py:24-26,54-66` uses commits `677abcfa`, `66952415` and `88b34ae0`.
- All three are present locally and are ancestors of e77.
- None is an ancestor of main.
- `:56,:60` assert that working-tree files equal `git show <sha>:<path>`.

**Other docs scripts with a git or history dependency.** `c1-20261022/tools/c1_setup.sh:9-15` fetches main and the branch `integration/c1-20261022` plus two scratch bundles. `c1_attr_build.sh`, `c1_ctest.sh` and a few issue239/240 scripts also call git. The grep is a lower bound because wrapper forms can be missed.

**History-only objects.** Of the 217 blobs at e77, the largest groups are earlier versions of repeatedly edited files: `CMakeLists.txt` (32 versions, 2.28 MB), `RC0_ACCEPTANCE_REPORT.md` (26), `SUPPORT.md` (22), `src/*`, and 15 `km_truth` versions. `km_truth` accounts for 42,256,524 B of the 61,752,600 B reachable at bbf.

## Normal merge versus docs-only extraction or squash (UNAPPROVED; no savings promised)

- **Normal merge.** It makes every one of the blobs above reachable on main: 947 at e77 and 1,099 at bbf. That includes the history-only versions and the commit SHAs that `verify_composition.py` needs. Local packed bytes (40,633,122 at e77 and 41,510,257 at bbf) are packing-specific and are not a transfer or storage figure.
- **Docs-only extraction or squash.** It would not keep intermediate commits in main ancestry. Anything that cites those SHAs would then need the original branches or refs to stay retrievable. That includes the three commits above and the `c1_setup.sh` branch fetch.
- **Active read paths.** A tip-only change that drops or moves `issue213/evidence` or `eval_v2.py` breaks the two CI-run tests regardless of merge mode.
- **Bulk.** `km_truth` is 83% of the tip docs delta (40,290,016 of 48,385,636 B at e77). The other 8,095,620 B include 2,611,470 B of archives outside `km_truth`. `raw.tar.gz` alone is 34,973,613 B and no test or CI step reads it, but the draft's "keep or extract" choice still needs the maintainer.
- **The #269 head** is itself an ancestor of C1. Its PR branch holds the same `raw.tar.gz` blob regardless of how C1 is landed.
- **Normal-merge preview.** The conflict statements in PR281 M2 (`merge-tree` conflicts in `CMakeLists.txt`, `RC0_ACCEPTANCE_REPORT.md` and `tools/test_ci_fail_closed.py`) are unchanged. I did not re-run `git merge-tree`, to avoid writing unreachable objects.

## Retrieval status: what is verified and what is only proposed

**Verified locally (this clone)**
- All 7 pinned commits are present (`git cat-file -e`).
- All 20 archive blobs re-hash to their object ids and sha256. The recorded sha256 in the repo equals the recomputed value for 17 of the 20.
- Local branch refs at the pinned tips:
  - `integration/c1-20261022` = bbf24607
  - `cuda-numeric-fixes-integration` and `c1/pr273` = 805d9de2
  - `integration/226-d2-d3-20261022` and `c1/pr274` = a1036901
  - `integrate-pr267-into-pr269` and `c1/pr269` = 1b29b7f9
- e77 and 1b15f10b are not the tip of any ref.
- Remote-tracking refs exist at the same tips. `origin/integration/c1-20261022` was last updated by a push at 23 Oct 00:02:42 (+0100); `FETCH_HEAD` is 00:03:47.

**Not verified**
- Whether any remote branch or URL exists now. No network access was used. A remote-tracking ref records the last fetch, not a live state.
- Durability. Only 3 tags exist (`rd10a-head`, `spa-tutorial-data-v1`, `v0.1.0-rc0`), and none protects a pinned head. Branch retention would depend on branches not being deleted.
- The clone is shallow with one boundary commit, `4998599a`. It is not an ancestor of main, e77 or bbf, so it does not truncate the ranges used here.
- The local object store has `garbage: 5` entries (temp pack and object files). I did not touch them.

## Unresolved gaps and flags (no deletion chosen)

1. **Three archives have no recorded archive-level sha256.** They are `issue226/d2/raw-logs.tgz` (1,044,455 B), `issue226/d3/raw-logs.tgz` (392,629 B) and `issue215/evidence/raw-evidence.tar.gz` (192,818 B). Neither the full digest nor a 16-hex prefix appears in the repo. This review's recomputed digests are `cacc76de…`, `6140b4ea…` and `7d007280…`.
2. **`issue215` verifiers read `/tmp` download copies.** The committed archive path is not the one read.
3. **`raw.tar.gz` holds the only in-tree copies of `generate_campaign.py` and `transfer_direct_zstd.py`.** Member-level hashes were not recomputed, so equality of the other script copies rests on recorded digests.
4. **`startup-controls-attempt1.tgz`** (bbf only) has one symlink member pointing at an absolute remote path. It was listed only, never extracted. It is also the only archive that would trip a naive extractor.
5. **Licence.** The repo is GPL-2.0 (`LICENSE`, `COPYING`). 17 of 415 docs `.py`/`.sh` files carry a licence or SPDX marker. EMPIAR-derived licence/access fields remain unverified, as the earlier reviews recorded. The archives hold no movie or image payload apart from 16 tiny `.mrc` in `native-receipts.tar.gz`. No notice was changed.
6. **Owner.** I found no retention owner named for any archive in the files I read; this was not searched exhaustively.
7. **PR281 draft wording** (corrections for the parent, not made here):
   - `docs/issue213/evidence` is new in C1, not "changed".
   - The `synth_combined` CI dependency is missing.
   - `tutorial_24_movie_manifest.json` is not read by CTest or CI.
   - The 57-file hit count is now classified; with `-w docs` it is 90 lines in 60 files.
8. **Scope limits.** Static reading only. No test, native, GPU or archive-member execution, so no runtime PASS is claimed for any dependency above.

## Material concerns (scenario and line)

| Scenario | Location | Consequence |
| --- | --- | --- |
| CPU ctest, run by CI | `tests/test_sticky_cuda_process_lifecycle.py:245-262`, `CMakeLists.txt:449-451` | If `docs/issue213/evidence/` is removed or moved, `StickyCudaProcessLifecycle` fails with FileNotFoundError. The directory is not on main. |
| CI step | `tools/test_combined_eval.py:16`, `ci.yml:105` | If `eval_v2.py` is missing, the step fails (`assertEqual(returncode, 0)`). The directory is not on main. |
| Manual verifier | `km_truth/integration_20261022/verify_composition.py:24-26,54-66,98-101` | It needs three history commits, an exact-tree checkout and `native_v2_raw.tar.gz`. It cannot run as written if the commits leave the ancestry or the files move. |
| Opt-in CUDA test | `CMakeLists.txt:1224` | Only affects builds with `-DMOTIONCORR_U16_TEST_MOVIE`. |

No defect in `src/`, `tests/` or the build was found. These are retention dependencies, not source bugs. There is no material source concern for the bounded retention task.

## Commands, resources, limits

- **Host and load.** Mac, Darwin 25.6.0, load average 4.1–7.0 across the session. One local process at a time, no numeric threading, scratch about 3.6 MB under `/tmp/motioncorr-m2-retention-review-20261023/`. No duplicate source tree or archive was created.
- **Python.** `/Users/alex.konstantinov/.local/bin/python3 -I -B` (3.13.7), stdlib only. Git 2.56.0.
- **Git access.** Read-only (`ls-tree`, `diff`, `grep`, `rev-list --objects`, `cat-file`, `for-each-ref`, `merge-base`, `rev-parse`). No `merge-tree --write-tree`, checkout, fetch or gc. The shared object store is `/Users/alex.konstantinov/Documents/MotionCorr/.git`; the root checkout was not touched.
- **Scripts** (in `scripts/`): `archives_and_refs.py`, `classify_docs_refs.py`, `payload_ext_scan.py`, `composition.py`, `history_groups.py`, `recorded_digests.py`, `build_tables.py`, plus `inventory_c1_docs.pr281.py`, the PR281 recipe extracted by `git show` (sha256 `16ed1f1243a4e4d5fc19cc4c1178ddbbbefcd67a258c052b7975c81c0299be13`) and run on e77 and bbf with the PR281 arguments (exit 0; the stderr files contain only `/usr/bin/time -p` output, about 1 s each). Every script I wrote carries `SPDX-License-Identifier: GPL-2.0-or-later`.
- **Reports and decisions read in full.** Decisions review round 1 and round 2 (`/tmp/motioncorr-decisions-review-r{1,2}-20261022/REVIEW.md`), parent `RESPONSE.md` and `PROVENANCE.json` for both rounds, and the M2 draft at 1b15f10b in full. The history inventory and merge preview were read in part (the inventory's numbers were re-derived by re-running its recipe; the merge preview was not re-run). The Notion plan (sha256 `13e074f9…2796`) was grepped for the M2 line only (`:236`); I did not read it in full.
- **Artifacts** (all under `/tmp/motioncorr-m2-retention-review-20261023/`): `REPORT.md`, `COMPONENT_TABLE.{csv,md}`, `DOCS_REFS_TABLE.md`, `out/*.json`, `out/docs_refs_classified.csv`, `scripts/`, `SHA256SUMS`.

## Recommended next bounded action

For the parent, if M2 stays in the PR281 packet: correct the draft wording in item 7, add the two C1-new test dependencies (`docs/issue213/evidence/`, `docs/post_rc0/s1/synth_combined/eval_v2.py`) and the three missing archive digests to the retention accounting, then ask the maintainer. This review adopts no option.
