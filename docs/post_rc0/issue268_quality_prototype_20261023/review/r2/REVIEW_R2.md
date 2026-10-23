# #268 quality-report prototype — independent R2 review

Verdict: **READY FOR DRAFT PUBLICATION ONLY**, with the two remaining limitations below carried into the draft description or a separate docs-only correction. No blocking finding for that scope. This is not a merge recommendation, M4/schema/C2 adoption, native CUDA qualification, performance result, or scientific accuracy PASS. Claims that F1/F2 are completely fixed need narrowing.

Reviewer: fresh Codex 6.1 Sol context, 23 October 2026. No nested agents or Claude authentication attempt. No cache-hit claim.

## Revisions and ownership

- Review checkout `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f84b09ae`, branch `review-issue-268-report-quality`, left clean at `1f0a58bf6e0639d8b62f74da52f250cc664c0b30`. Exact objects were read with `git show`/`git diff`; checkout source was not used as candidate source.
- Author checkout `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-2566d166`, branch `experiment/268-quality-report-20261023`, observed clean at `e9c1e9b41a918293928417d57d31adf1e4e50300`; never modified.
- Prototype base `bbf24607dec537bd13351f061047ea38bd38237b`; R1 implementation `c347f59f25a2148642130136c6462491c8db36d1`; R1 evidence head `eeb68f1f7accd7d52e0e745efaade26f6898105f`.
- V2 design/protocol `a95d7edd80169495b795384fc7a1f0247c57908a` and `798e8d5ab5180823d8825068a69c036e0b1256ac` precede V2 source `1215febd526c4e4499d75c67cd888192153bcc3c`.
- Tested head `2f43425340b7525e85288e7b35ee109dd3a4c3cc`, tree `0de56473e5b1b4aa174952489907b3460216854d`. Its `src/` and `CMakeLists.txt` are identical to `1215febd`. Evidence head `e9c1e9b41a918293928417d57d31adf1e4e50300` changes neither.
- Root checkout `/Users/alex.konstantinov/Documents/MotionCorr` was not accessed or changed. No review commit, push, PR, GitHub comment or Notion write was made. No existing PR is being reviewed/linked here; #268 is the issue.

All R2 writes are inside this invocation:
`/tmp/motioncorr-q268-review-r2-20261023-codex/b1565895-bf79-4578-8a29-f09a3e9a30d7/`.
A live Python process acquired nonblocking directory locks before creating review artifacts and holds the invocation lease through completion. Local occupancy was checked before controls; load about 5 at admission on the busy Mac. Controls used `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1` and Python `-B`. No CPU affinity was set locally. Scratch was about 2.2 MiB before this report, below 512 MiB. No system/shared installation, native executable, compiler/build, SSH, SMI or GPU operation occurred.

## Inputs and live context

Read the full fetched Notion plan, AGENTS.md, release plan section 9, original R1, DESIGN.md, DESIGN_V2.md, PROTOCOL.md including its dated correction, PROTOCOL_V2.md including A1, README_V2.md, source, checker and unit-test objects. Original R1 SHA-256 matches `eb3d5ab38664fdd59c6b6861b2aeda792563f8ac64efe9629b913d4bb28bea9b`. Input hashes are in `input_identity.json`; selected exact-object hashes are in `extracted.json`.

Read the full #268 snapshot issue/comments and refreshed live using `gh api repos/KingAlejandro/MotionCorr-standalone/issues/268` and paginated `/comments` (both exit 0). The issue is still open, updated 21 October, comments `[]`. The task's user-selected report-quality/preserve-publication direction authorizes this separate experimental prototype; it is not production approval.

## Findings

**R2-F1, low: resume validation remains partial, despite the broad strict-validation claim.**
Exact source `1215febd`, `src/quality_report.cpp:342-392`, particularly `350-363`; accepted states are copied at `589-601`. The validator checks the global state's vocabulary and the type of `iterations`, but does not compare `state` with `converged`, `solver_returned`, final RMSD, tolerance or max_iter. It does not validate identity, per-patch objects/attempts or their count semantics either. For a concrete example, copy Q4's noisy sidecar and change only `global_alignment.state` from `iteration_limit` to `converged`. Its original `converged=false`, `solver_returned=false`, iterations=5 and RMSD=1.409976700889825 remain. All implemented validation predicates and product bindings still pass; resume copies `converged` into the aggregate. With otherwise valid peers this can still claim `quality_evidence_complete=true`. Missing `identity` or nonsensical unexamined fields similarly are not rejected. The custom parser also is not a fully strict JSON parser (`224-246`, `284-288`), so README's unqualified schema/type/invariant language is too broad.

This is a source/data-only trace, not execution of the C++ reader: the review explicitly forbids builds/native execution. `resume_contradiction_data.json` retains the concrete modified data. The five R5 tamper cases and named U3 checks are fixed; the residual requires edited, corrupted or foreign sidecars and does not change product completion or publication. Non-blocking for an explicitly limited draft. Next source iteration: validate consumed state invariants and essential schema fields; add focused contradiction/type tests before freezing a fresh protocol and obtaining exact-source evidence. At minimum, qualify the docs now.

**R2-F2, low: root collisions are detected by spelling, so filesystem aliases can evade F1.**
Exact source `1215febd`, `src/motioncorr_runner.cpp:1658-1665` counts raw `std::string` roots. `getOutputFileNames` (`695-718`) replaces dots but preserves repeated slashes. Input rows `in/zero.mrcs` and `in//zero.mrcs` therefore produce distinct map keys `out/in/zero` and `out/in//zero`, which identify the same POSIX output files. Both rows take the ordinary `published`/sidecar branch instead of `ambiguous_output_root`; the later sidecar overwrites the earlier one and the first summary hash can become stale, while completeness is still true. The same issue is possible through pre-existing output-directory symlinks. The ordinary duplicate and shared-extension cases tested in Q5/Q6 are correctly fixed.

This is a source/path-data trace (`alias_collision_data.json`), native alias campaign UNRUN. It has the same scope as R1's collision limitation: an input shape that production already permits to overwrite products. Non-blocking for the experimental draft, but README should describe detection as equal generated-root strings, not all shared filesystem outputs. A later source iteration should select a narrow identity rule for output roots and test it without changing production processing or overwrite policy.

**Checker scope, non-blocking:** after rebinding the summary sidecar digest, the frozen checker accepts changing a patch's `solver_returned`, its `max_iter`, `largest_delta_px`, or identity option `bfactor`. These are not covered by all 12 advertised negative controls. R2 independently checked actual per-patch return/iteration fields against logs/argv and inspected the source limits; no mismatch in the retained reports was found. `largest_delta_px` has no independent full-precision receipt here; its hook and running-maximum semantics are source-reviewed only. Do not treat the checker PASS as exhaustive field validation.

## Source, scope and license review

- OFF preprocessing was independently stripped without compiling. Residual diffs against `bbf24607` are retained as `*.off.diff`: includes/whitespace, storing the previously discarded global bool, and a scope block; the bool does not affect downstream decisions. No numerical operator, gate, tolerance, retry, product metadata or joint-membership decision changes were found.
- CMake option is OFF by default; its definitions cover the C++ core and CUDA translation units in the directory scope. The runtime parser flag is compiled only with the option. OFF-build unknown-option warning/continued processing is correctly documented by prospective amendment A1, rather than changed.
- All solver call sites were traced: CPU global/patch, resident/host-staged CUDA through the shared core, batched `PatchBatchLog`, and existing CUDA fallback/retry. TLS capture lifetime and sequential movie ownership are appropriate. Batched tolerance remains null and search range remains unobserved. CUDA runtime correctness is not established.
- Membership indexing preserves one report row per retained membership occurrence. Completed patch decisions distinguish dropped from interrupted; the native interrupted hook remains UNRUN. Thresholds come from production locals and fit rejection is recorded inside its original branch.
- Sidecars follow writer drain. Aggregate follows final publication outcome and precedes existing failure/rethrow. Atomic close/rename failures clean up temporary files and warn; product-write failures retain the production exit. Report exceptions are handled at writer boundaries. No newly discovered reachable product/exit drift was found. Report-on adds allocation/hashing/I/O; this is not a proof against all resource-exhaustion exceptions. Summary-write-failure on V2 remains UNRUN, as declared.
- GPL-2.0-or-later notices remain. No new external dependency or license conflict was found; SHA-256 is the self-contained FIPS implementation already present in the prototype.
- Convergence records the incremental solver test only. Flat input may be `converged` while identifiability and peak validity remain `not_assessed`. No truth result was promoted or changed.

## Evidence independently audited

`audit.py` does not import the author's checker. It completed with `AUDIT PASS` (exit 0), retained in `audit-attempt1.out`.

- 226 retained campaign files and all 5 raw-named tar members match their exact SHA-256 entries. Archive members were read in RAM, never extracted to invalid local names. Manifest has 1,113 unique entries; 882 other entries are hash-only, including copied checker-control products/inputs. This is not 1,113 retained files.
- Campaign manifest/run records agree on 16 Q1-Q16 processes, argv, binary selection, `taskset -c 14`, `--j 1`; Q11/Q12 exit 1, all others exit 0. Driver records one-thread environment, builds at -j2 on CPU14-15 under nonblocking build lock, and CTest at -j1 on CPU14-15. Driver PID 3333420 and source-tree/clean receipts agree. Its unpinned orchestration-shell affinity 0-123 is not a claim that compute was unpinned.
- Source and tree receipts agree with Git. Fixture hashes agree with the exact tracked GENERATION_RECORD; inputs are 128x96x5 float32 (246784 bytes including header), also reported in logs. No movies were regenerated or executed in R2.
- Independently rederived 16 untampered/current sidecars, 108 patches and 7 summaries. Iterations, six-significant-digit logged RMSD, solver booleans, routes, argv/max_iter, patch indices/finals/counts/retries, observation counts, reached limits, fit RMSD vs logs, STAR model presence, publication, membership/order and summary counts agree. Five current-run IDs are distinct; Q9 correctly retains prior identity for resumed data. Q9's deliberately edited sidecars were not counted as fresh correct reports. Q9/Q10 per-movie hashes are unchanged (30/24 files); joint STAR equal.
- Actual retained STAR/sidecar bytes were hashed independently. Input/MRC bindings agree with the hash manifest, which is receipt consistency only for absent data. No independent byte-for-byte or timestamp-normalized MRC comparison can be rerun from this sparse bundle. Original remote R1-R10 product verdicts remain retained campaign evidence.
- 37 normalized per-movie log pairs agree across all relevant comparisons, including encoding and product-write failure. Only the frozen wall-time/source/backtrace exclusions were removed; solver lines were preserved.
- Driver hash matches launch_inputs.sha256. The bundle itself is absent, so its listed hash was not independently recomputed. Native binaries are absent, so their hash receipts, configured revision, argv and sidecar identities were reconciled; binaries were neither hashed anew nor run by R2.

Exact binary receipts (SHA-256):

- V0 `97f44b8ab3c95cb0aca9f3fd93580e34bf34f34ad5ca1245180b27ebba39d3a1`
- V1 CPU OFF `625ac268aac6baccc91631e596b91db55a4a07021296e45d9a836d69f3fab74a`
- V2 CPU ON `9a9f1bfafaf1139bd115d2b753f05a3381c5d308b9a396967f688c0dc0b45e25`
- Unit `51c77943c23884d6a4c4fccb7ba8980379b8ca2ec10418dcc50c9279c66d6819`
- V3 CUDA OFF `4102738df8075c6f1f270d8337bbd953305135ce68ecfa092f0aa9f8082773b2`
- V4 CUDA ON `c112a1b9bb36e678d8aa7ea6af54389203e3295f181d65aead875b7e919acd0d`

Small documentation nit: README_V2's abbreviated V3 hash ends in `19`; the receipt above ends in `b2`.

Full CPU CTest logs were independently counted: OFF 90 collected = 89 Passed + 1 Skipped; ON 92 = 91 Passed + the same 1 Skipped, zero failed. Skip is CompressedMrcStatus_bz2. The ON registration set is exactly OFF plus QualityReportCheckerSelftest and QualityReportUnit. Collection-check receipts exit 0. These are recorded native CPU results, not tests executed by R2. CUDA OFF/ON motioncorr targets compile (build receipts exit 0); all CUDA execution UNRUN. No GPU UUID is applicable to this CPU-only campaign.

## Local frozen data controls and commands

All Python invocations used `/Users/alex.konstantinov/.local/bin/python3 -B` with the one-thread environment above:

1. `audit.py`: exit 0, AUDIT PASS; independently checks hashes, fields, logs, CTest counts, source trees and OFF residuals.
2. Exact `quality_controls_v2.py selftest`: exit 0, v1 and v2 selftest PASS (`selftest.out`).
3. `checker_replay.py`: exit 0. Calls the unmodified frozen Q4/Q6/Q8/Q9/Q12/Q15 report/collision/encoding/resume predicates and original negative_controls: untouched PC accepted, all NC1-NC12 rejected. The adapter supplies an in-memory filesystem for raw filenames and explicit hash-only objects for missing input/MRC files, with input size derived from geometry. It does not invent product bytes or run the full product-comparison campaign. Results and accepted-field probes are in `checker_replay_results.json`.
4. Supplemental data/source checks verified the CTest registration union, Q9/Q10 unchanged per-movie hashes, and the two source-only finding examples. No C++ unit binary was run in R2.

No failed control was retried. One exploratory concatenated read requested a nonexistent `receipts/identity.txt`, producing exit 1; the actual identity is `sources.txt` plus `binaries.txt`, read successfully. Some early oversized tool output was truncated and the needed files were subsequently read in bounded chunks. No failed campaign was repaired, no original evidence rewritten, and no lost historical log reconstructed.

## Limits and next bounded action

Historical #273 2 PASS / 10 FAIL / 4 UNIDENTIFIABLE and #65 UNRUN/INCONCLUSIVE are unchanged. No accuracy test ran here.

Still UNRUN: all CUDA execution (including resident, host-staged, batched, decline and same-input retry), native interrupted-patch trigger on every route, V2 summary-write-failure, distortion-guard and fit-RMSD fallback reasons, e10216-01, dataset/multi-GPU aggregation, tomography and timing. LastTest.log was overwritten by collection inspection; the exact U2 branch on Linux remains unrecorded even though native Q8/R4 covers invalid UTF-8 filenames. Full runtime qualification/re-entry requirements remain outstanding.

Parent may publish a draft with this review and those boundaries. Before publication, put the two residual F1/F2 limitations and corrected V3 suffix in the draft text or a separate docs-only correction; source/native results stay tied to 1215febd/2f434253. No source fix or new experiment is required merely to publish this experimental draft. If iterating source, keep a fresh source identity/protocol and obtain exact-source native CPU and relevant CUDA evidence before any stronger claim. Maintainer retains M4/schema/publication-policy/C2 decisions.

R2 artifact whitelist is `SHA256SUMS`, excluding its own self-line. Review commit: none; production/source changes: none.
