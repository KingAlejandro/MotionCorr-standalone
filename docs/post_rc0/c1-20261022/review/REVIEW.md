# C1 source-integration review, round 1

Reviewer: independent Sonnet 5.5 review task (did not author any C1 component). 22 Oct 2026, ~21:00 UTC.
Candidate: `integration/c1-20261022`, frozen source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`; main `3691374061f782bc84531fd1c79d017ddcb5a7c2`.
Worktree: `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-870e8c9d`, detached at e77. Report folder: `/tmp/motioncorr-c1-integration-review-r1-NGiVKt`.

This is a source-integration/DRAFT-readiness review. It is not an M1 merge authorisation and not a qualification result.

## Verdict

**No material production/test/build source finding at e77.** Six advisory findings (A1–A6) and three process notes (P1–P3) below; none is a defect in the integrated source, none requires a source change before qualification continues.
Qualification itself is incomplete (T24, K267/K269/K272, R12/D12/R9, S1 sticky, A13 and W1 witness rows have no result in the packet I reviewed). The source is ready to proceed to those rows. Historical 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE motion-truth totals are untouched by anything I read.

## What I reviewed and how

Local metadata, raw text/JSON/XML, git object reads and bounded arithmetic/hash checks only. No SSH/GPU/native job, no test or evidence-script execution, no edits/commits/pushes/comments, no nested agents, no GitHub or Notion access (so PR head/CI/review state is taken from the ledger, not live). One numeric thread, load average 3–5 at start.

Read in full: `AGENTS.md`; `docs/release/POST_FREEZE_TEST_PLAN.md` §9; the Notion plan (`/tmp/motioncorr-orchestrator-20261022-notion-plan.txt`); `docs/post_rc0/c1-20261022/{QUALIFICATION_PLAN,MERGE_LEDGER}.md`; the complete production delta (`src.diff`, 717 lines: `src/` + `tools/multi_gpu` + `tools/profiling`) and the whole `CMakeLists.txt`, `ci.yml`, `validate_test_collection.py`, `test_ci_fail_closed.py` deltas; the modified pre-existing tests (`cuda_dose_normalization.cpp`, `cuda_patch_batch.cpp`, `test_truncated_gain_defect.py`); `test_compressed_mrc_status.py`, `cuda_local_admission.cpp`, `cuda_hermitian_inverse.cpp` main(); the SUPPORT/README/RC0_ACCEPTANCE_REPORT deltas; `OVERLAY.md` of the tools overlay.
Raw native packet `/tmp/motioncorr-orchestrator-20261022/c1-full-ctest-e77a51a2/` (22 files): parsed myself (`junit_check.py`), not through the parent's grader. I did not open the original PR #281 six-review/ledger text; the ledger in the C1 tree and the parent audit JSON were used as pointers only.

Retained in the report folder: `receipts.txt` (command outputs below), `ancestry.txt`, `lostlines.py/.json`, `remerge_files.txt`, `junit_check.py/.json`, `src.diff`.

## Integration checks (all PASS)

| Check | Method | Result |
|---|---|---|
| 14 heads are ancestors of e77; main is an ancestor | `git merge-base --is-ancestor` per head (`ancestry.txt`) | all 14 + main: yes |
| Merge parents match the ledger | `git rev-parse <merge>^2` for the 14 first-parent merges | all 14 equal the ledger head (#267 66952415 … #241 6c72a87b) |
| Merge order | `git log --first-parent main..e77` | #267,#269,#272,#254,#260,#270,#252,#251,#244,#248,#249,#245,#242,#241 as planned; normal `--no-ff` merges |
| No conflict markers | `git grep` for `<<<<<<<`/`>>>>>>>` at e77 (non-JSON/log) | none |
| **No production conflict resolution** | `git show --remerge-diff` on every merge (`remerge_files.txt`) | hand-resolved files only: `CMakeLists.txt` (#260,#270,#252,#242,#241), `RC0_ACCEPTANCE_REPORT.md`, `SUPPORT.md`, `tools/test_ci_fail_closed.py`, `tools/validate_test_collection.py`. No `src/` file was ever hand-resolved. Matches the ledger table exactly (including #254/#244 clean) |
| No PR-added line lost | multiset check: every line each PR added vs its merge-base exists in the e77 file (`lostlines.json`) | only expected supersessions: `CUDA_SUITE` single-name line in `test_ci_fail_closed.py` (#260/#252/#251, replaced by the merged list) and four lines of `run_realistic_motion_census.py` (#269, replaced by #272, whose merge tree equals the #272 head). The `missing_in_final` entries are 0-byte log files, verified empty at head and at e77 |
| Numerics source equals the #273 native source | byte comparison with `d751ff28` | `cuda_alignpatch.cu`, `cuda_fft_prep.cu`, `cuda_hermitian.cuh`, `cuda_realspace_dw.cu` byte-identical |
| D2/D3 source equals #274 | diff vs `a1036901` | only the numerics above plus three independent fixes: #244/#248 TIFF identity (33 lines in `cuda_movie_session.cu`), #245 `error.{h,cpp}`, #249 `image.h::finish()` + 2-line runner call. The plan's sentence "C1 src minus numerics equals #274" omits those three; the I1 row text does cover them |
| Exclusions respected | path scan | no DC (#262), nonconvergence policy (#268), guard (#264), STAR (#265), CPU C2R (#266) or Metal changes; `src/` touches only the 8 files + `cuda_patch_retry_admission.h`; #273/#274 packets absent; no new third-party code or runtime dependency |
| Native-tested source = frozen source | `git diff 1ff59b74 e77 -- . ':(exclude)docs/post_rc0/c1-20261022'` | empty: the six commits after the last merge change only `docs/post_rc0/c1-20261022`. The CTest packet (e77 checkout) is therefore code-identical to the merge result |
| Overlay 1aac4159 | `git diff e77 1aac4159` | 8 files added, all under `docs/post_rc0/c1-20261022/tools-v2/`; `src tests tools CMakeLists.txt .github test-data` identical; e77 is an ancestor. Not a freshly tested production SHA. Snapshot `/tmp/…/c1-tools-1aac4159` (11 files) hash-matches the committed blobs |

## Fail-closed lists, registrations, acceptance entries

- `DEFAULT_REQUIRED_TESTS`: #260 (`PeakFitArithmetic` + 3 mutants), #252 (`PatchRetryAdmission`), #249 (`CompressedMrcStatus_{bz2,xz,zst}`) all present. `CUDA_REQUIRED_TESTS`: `CudaPeakFit`, `CudaPeakFitMutant_float_denominator`, `CudaStaleErrorAfterOom`, `CudaLocalAdmission`, `CudaEarlyStreamingOom`, `CudaStreamingPlanClassificationCleanup`. `CUDA_SUITE` in the control test restates the same six, and the Case-E assertion now checks every name instead of one.
- CMake: all registrations from the 11 PRs that touch it are present; `mc_cuda_mutant` now dispatches on prefix (`Oracle` → `--expect-oracle-failure`, `Hermitian` → invariant build + `--expect-invariant-failure`, else `--expect-mismatch`); `CudaPeakFitMutant` correctly falls to the default arm. Mutant/identity source patching is unique-match or `FATAL_ERROR`, so a lost/duplicated anchor fails configure; it configured and built on all three configurations.
- Both #249 report entries survive: `## 8. Post-RC0 fixes` (#214, RC0_ACCEPTANCE_REPORT.md:317) and `## Post-RC0 #246` (:376; differs from main by one trailing blank line). #213/#215/#214 SUPPORT limitation bullets are all present. #249's "source/test head `39aca256`; later commits docs/evidence only" is true except for `test_import_subset_boundaries.py`, which came from main (#247) and is identical to main in C1.
- Expected set (my parse): CPU 74+16=90, CUDA 108+35=143, CUDA+nvCOMP 111+37=148. Per-PR additions sum correctly (CUDA: 241:1 242:1 244:1 245:2 248:1 249:3 251:2 252:2 254:12 260:6 270:4 = 35). #267/#269/#272 add no CTest tests; their Python tests run only from `ci.yml`.

## Native CTest packet (read independently)

- JUnit: CPU 90/90, CUDA 143/143, CUDA+nvCOMP 148/148; `failures=0`, `skipped=0`, no `skipped`/`error`/`failure` children, no duplicates, no zero-duration test, every status `run`; JUnit names == expected_collection set == names in the log's Passed lines, in all three configurations. Each log ends `ctest rc=0`, `validate_test_collection rc=0`; CPU log also `test_ci_fail_closed rc=0` (8 tests).
- Binary sha256 per build, HEAD e77, mask 8–9, GPU3 UUID `GPU-b2cb2c39-…`, bench lock probe free: in each log header. A100 80GB PCIe, driver 570.86.10, CUDA 12.8, cuFFT 11303.
- Pre/post nvidia-smi XML for CUDA and nvCOMP: lane UUID present, zero volatile/aggregate ECC counts, remapped-row corr/unc 0 and pending/failure `No`, retired pages N/A, zero compute processes, 1 MiB used. All four health receipts exit 0. Kernel Xid logs remain UNRUN, as stated.
- All 22 members hash-match `c1-full-ctest-parent-verification.json`; archive sha256 `b038211f…12df` matches.
- New device mutants reject for visible reasons where the retained output allows (invariant failure at the unprojected site for `no_projection` and `wrapper_no_projection`; `INVARIANT FAIL` on both CCF mutants; `3 case(s) differ` for both border mutants). See A5 for the ones whose reason is truncated.
- The CTest packet is **not** tutorial/truth/recovery evidence and I draw no such inference.

## Scratch ownership, admission, retry and failure paths

- **Hermitian projection (#254) allocates nothing and writes only consumption scratch.** The five `cufftExecC2R` sites in `src/` are all preceded by `projectHermitianColumns`: per-patch CCF (`cuda_alignpatch.cu:628`) and batched CCF (`:992`) on `d_Fccs`, the global inverse on `d_inverse_tile` after a device-to-device copy (`cuda_movie_session.cu:2146–2162`, resident `d_Fframes` untouched), the wrapper inverse on `d_comp` after a host-to-device copy (`cuda_fft_prep.cu:255`), and dose weighting on the per-frame C2R scratch `d_Fframe` written by the weight kernel (`cuda_realspace_dw.cu:392`). Admission arithmetic (D2/D3) therefore needs no adjustment for it. Each call uses the surrounding file's error convention (`ALIGN_LAUNCH`, `HANDLE_ERROR`/`LAUNCH_HANDLE_ERROR`, or the explicit record+drain+`return false` in the session).
- **FP64 peak fit (#260) and border branch (#270)** are per-thread arithmetic; no memory or control-flow interaction with D2/D3.
- **Local admission geometry matches the real patches.** The runner's `pw=(nx/patch_x)/2*2` equals the even-rounded `patch_bounds` width (`x_end = x_start + nx/patch_x`, odd widths trimmed by one), so admission sizes the patches the loop will actually prepare. The admission is placed after preprocessing release and before the existing downstream fallbacks, and on decline downloads real frames, marks them non-raw and discards the session.
- **Retry admission** is only reached in the non-converged branch after resident preparation; on decline it preserves both real and Fourier host frames before discarding the session and frees the stale patch-spectrum buffer. Later patches see a null `movie_session` and take the non-resident path. Overflow/invalid-geometry refusal is checked before any `int` plan distance is formed.
- **D3 early refusal** only runs when `use_gpu && !early_binning && !movie_session`, before host widening; it latches a fatal planning error before cuFFT cleanup can mask it. No interaction with the compressed-MRC drain, which is later and only in the host-read block.
- **#249 drain** (`motioncorr_runner.cpp:2600`) runs after the OpenMP read region on the serial path, so a decoder failure takes the same exception route as the frame-read errors rethrown just above it (the CUDA error guard and session RAII apply). It runs only for `n_frames == nn`, matching the documented "any frame omitted is a subset" rule; `finish()` nulls the pipe before it can throw, so the destructor cannot double-close.
- **#248 identity** (`cuda_movie_session.cu:1426–1445, 1838, 1849, 2030–2031`): tag-scan descriptor pinned (`dev/ino/size/mtime ns`), rechecked on the path before handle opening, on each fresh handle, and before every chunk's decoder submit. Decline logs a named line and returns to the host reader; scratch teardown still synchronises the copy stream. Compiled out without nvCOMP (`<sys/stat.h>` and the helper are inside the guard).
- **#245**: `std::vector` ownership replaces `new[]`/`delete[]`; the only other reader of the buffer is the ownership test. Printing twice or copying no longer double-frees.
- **#242** (`run_dataset.py`): raising `_RestorationFailed` from the `finally` and catching it in `main()` returns 3 exactly where `return 3` in the `finally` did, including when the body raised.
- Pre-existing tests changed by C1: `cuda_dose_normalization.cpp` `launch_checks == 1+2*count → 1+3*count` (one more launch per frame, the projection) and a host-projected oracle input; `cuda_patch_batch.cpp` hooks are `#ifdef MC_CHECK_HERMITIAN` only; `test_truncated_gain_defect.py` turns a silent EER-section skip into a failure when Pillow is missing (only when EER inputs are supplied). No tolerance was loosened.

## Findings (advisory; none blocks qualification)

**A1 — #249 GPU route has no exact-SHA witness (evidence gap, medium).**
Scenario: the `CompressedMrcStatus_{bz2,xz,zst}` rows in the CUDA and CUDA+nvCOMP CTest runs execute the CPU route. `CMakeLists.txt:518–521` registers them with `--binary … --codec` and no `--gpu`; the retained JUnit command line has no `--gpu`. `tests/test_compressed_mrc_status.py:65` only passes `--gpu <id> --ingest float` when given. `finish()` is shared code, so the GPU route is expected to behave the same, but nothing in the e77 packet shows it, and the #249 GPU evidence is at its own SHA (`39aca256`, pre-numerics, pre-D2/D3).
Resolution: run the same driver with `--gpu <GPU3 UUID>` from the CUDA and nvCOMP e77 builds under the GPU3 lock (all three codecs, the full/first/last/middle/damaged/shim cases), with route witness, or leave the row UNRUN in the packet. A13 in the plan lists the CTest rows only.

**A2 — `CudaLocalAdmission` takes its local-alignment threshold from the production diagnostic (low).**
`tests/cuda_local_admission.cpp:55–57` parses `required` out of the "requires N bytes" log line, then checks admit/decline at `required-1/required/required+1`. That proves threshold mechanics and the diagnostic, not that the formula equals real peak use. (The retry formula is derived independently in `retryBytes()` and does not share this weakness.) Formula adequacy rests on the D2 balloon rows at `bb348554`, which the plan does not rerun on C1.
Resolution: the M1 packet states the D2/D3 balloon and floor claims ("10441 at 37.5 GiB", Falcon 4, 10216, the 22 GiB D3 floor) as retained at their own SHAs and not rerun on C1, or reruns them. SUPPORT.md already attributes them to `bb348554`/`4cd85167`.

**A3 — two merged fixes modify RELION-inherited, CPU-shared source (decision framing, low).**
#245 changes `src/error.{h,cpp}` and #249 `src/image.h`, files listed as upstream in `SOURCE_MANIFEST.txt` (lines 50–51, 62–63); #249's drain also changes CPU-build behaviour (a decoder failure now rejects). Plan §9.2 treats fixes to upstream-inherited behaviour as a parity divergence needing sign-off. M1's wording names #249 and #248 but not #245. `SOURCE_MANIFEST.txt` gets no "Local change" entry for either (it has only four such entries in total, so this follows existing practice). Upstream copyright/licence headers are unchanged and all new code is original, GPL-2.0-or-later-compatible.
Resolution: list #245's `src/error.{h,cpp}` change in the M1 packet as an inherited-source change with "no numeric/format effect" and its evidence (`RelionErrorOwnership`/`RelionErrorUnprinted`, 6,400-byte LSan control at the PR SHA), and decide whether to add manifest entries.

**A4 — most C1-added tests are outside the fail-closed lists (low, inherited).**
Added but not required by name: CPU 8 of 16, CUDA 22 of 35, CUDA+nvCOMP 24 of 37 (e.g. all `CudaHermitian*`, `CudaRealspaceBorderBranch*`, `CudaNvcompTiffIdentity*`, `DatasetFinalization`, `TestHygiene235`, `RelionError*`, `HermitianProjectionOracle`, `RealspaceBorderValidation`). The C1 grader's expected union and its four named tests cover this for qualification, but after merge `validate_test_collection.py` would accept a build that silently dropped them. The ledger already records this as inherited; the plan said to keep the union, which was done.
Resolution: post-M1 test-only follow-up adding them to the lists (new SHA, CPU/CUDA collection re-entry only). Not a C1 change.

**A5 — passed-test output is truncated at 1024 bytes in the retained JUnit (evidence retention, low).**
For six new device mutants (`CudaHermitianInverseMutant_dose_no_projection`, four `CudaHermitianOracleMutant_*`, `CudaPeakFitMutant_float_denominator`) and the three host `PeakFitArithmeticMutant_*`, the middle of the output is dropped, so the rejecting line cannot be read from the packet. The pass relies on the `--expect-*` exit contract. For `dose_no_projection` the retained head shows the session and wrapper stages passing, which makes the dose site the only possible rejecter. Also only `float_denominator` is mutated on the device for peak fit; `early-store` and `wrong-scale` are host replays only (stated in the CMake comment).
Resolution: for later iterations raise `--test-output-size-passed`; do not rerun for this.

**A6 — #248 decline classification and message (low).**
A mid-ingest identity decline records no CUDA error, so `ingestMovie` classifies it `NotApplicable` rather than `RecoverableFailure` (`cuda_movie_session.cu:1242–1249`); the runner takes the same host re-read for both and overwrites the device buffers, so products are unaffected. Under pinned `--ingest nvcomp` the error text (`motioncorr_runner.cpp:2350–2354`) says "no nvCOMP, no session or unsupported encoding" and does not mention identity; the logfile line does. `mtime`/`size` equality between `fstat` and `stat` is unverified on PanFS/NFS/Lustre; a spurious decline there costs a host fallback under `auto` and a refusal under pinned `nvcomp`. T24's per-movie nvCOMP witness will show this on the chosen filesystem; I do not expect it on local disk.
Resolution: none required. Note filesystem identity in the T24 record.

**Nits.** `CMakeLists.txt:920` — the "Worker-lifetime device gain retention" comment now precedes `cuda_local_admission` (`:922`) instead of `cuda_device_gain_pool`, an artefact of the union. `RC0_ACCEPTANCE_REPORT.md` has three `## 8.` headings (:272, :290, :317), the D2 section sits before `## 7. Sign-off` and the D3 section after it (as authored, headings not renumbered per the ledger). Each per-PR section still quotes its own pre-merge CTest totals (e.g. "CPU 75/76 … #246"), which C1's 90/90 supersedes; they are historical and correctly SHA-bound.

## Process notes

- **P1 — no CI evidence for the integrated SHA is in my inputs.** The ledger CI column is per component head. Current-head CI (CPU build/checks, CUDA compile-only, with the new scipy install and four new Python tools) needs to exist for the final C1 SHA before an M1 recommendation; it will establish no native claim. #267/#269/#272's Python tests (`test_motion_diagnostics/realistic_motion/realistic_image/combined_eval`) are not in CTest and not in the CTest packet. The parent's host-test log is separate. SciPy (BSD-3) is a CI/test-fixture dependency only, no runtime or build dependency; §9.1 of the post-freeze plan says "no dependency", so say so in the packet.
- **P2 — C1 lands 756 documentation files / 48.4 MB** (35 MB is `docs/post_rc0/s1/km_truth/raw.tar.gz`, inherited from #269). M2 is framed for #273/#274 only; the parent's M2 inventory/draft already covers this, so nothing new beyond cross-referencing it in M1.
- **P3 — tutorial attribution wording.** The Notion plan asks that every changed output be attributed to "a named fix". The overlay narrows N-only reproduction to `COMBINED_NUMERICS_COMPOSITION_ONLY` and treats single-fix attribution as exact-byte reproduction by the only254/only260/only270 builds. That is the honest reading; the final packet must not call a combination-only result a per-fix attribution.

## Tooling work-in-progress (not production defects)

I did not rerun or audit the helpers beyond what bears on scope. Consistent with the parent's record: e77's T24/R12 helpers are v1 tools; the first T24 iteration (`772f2cf5`) failed in orchestration (escaped `$SC`), all 36 resulting comparisons classified INVALID and retained; the corrected tools are the docs-only overlay `1aac4159`, deployed outside the exact checkout. The overlay claims "production source delta is empty": confirmed above. Not yet evidenced: the eight Linux ownership/timeout controls and anything the latest tools produce. Their final review belongs after those results; this round does not qualify the timeout/group cleanup.

## Remaining qualification blockers (not source defects)

All below have no result in the packet I reviewed; they stay UNRUN/pending, not PASS:

1. T24 24-movie tutorial comparison vs frozen RC0, G and L, with nvCOMP route witness per movie and per-fix attribution (C1 == N expected; F-fresh == F-retained lane control).
2. K267 / K269 / K272 known-motion and image rows on CPU and CUDA; every inherited truth failure retained with attribution, none reclassified.
3. R12 (resident retry incl. D2 admission), D12 one-worker dataset rows, R9 compact matrix, W1 route witness.
4. S1 `CudaStickyContext` (opt-in, not collected by CTest; needs the ≥4-CPU window) and the one-worker dataset endpoint: parent reports the wrapper stages exited 0; the full evidence is not in my inputs.
5. A13 (QF item 13 at `--j 8`), two/four-worker and UUID-selective poison arms, genuine nvCOMP-ingest poisoning, performance, SCARF, downstream science: UNRUN by design.
6. A1 above (GPU-route witness for `finish()`).
7. Current-head CI for the final C1 SHA (P1) and a final latest-tool evidence review.

## Resolution criteria for a re-review

A later change to production/test/build source, a re-merge, or a change to a fail-closed list requires a fresh delegated review. Evidence-only additions (T24/K/R/D results, overlay outputs) do not change this verdict, but each result needs its own SHA, binary hash and receipts. An unexplained product change from C1 outside the three numerics fixes (for example an identity-induced route fallback, or a C1 ≠ N product) blocks the M1 recommendation per the plan.

## Limits

Static and packet-based. I did not build, configure or run anything, so claims about behaviour rest on source reading plus the retained native receipts. I did not re-review each component's numerical correctness individually; I read the whole production delta and found no defect, but that does not replace the per-head reviews. Live GitHub head/CI/review state was not checked.
