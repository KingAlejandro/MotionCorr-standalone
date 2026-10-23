# Independent R2 review: CHANGES REQUIRED

One P2 diagnostic-loss finding prevents readiness for the standalone versioned draft at final 95efc2989505cda083fc801eddb987405967ba93. Original R1's three reproductions are repaired and independently pass. No native, scientific, full-campaign, merge or caller-integration readiness is established.

## R2-F1 (P2): accepted finite metrics can overflow summary arithmetic and erase diagnostics

File: docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023/summarize_v2_1.py:237 (cell median), :254 (paired subtraction), :258 (regression delta), :262 (paired median), :285 (strict serialization). The predicates at :64-77 establish input finiteness, which does not establish finiteness of these derived values.

Two independent bounded actual-CLI inputs satisfy the adapter's existing finite-number/schema checks:

1. `finite-large-median`: start with the existing complete 20-record none/global fixture. Set truth.field.px.rms to the finite JSON number 1e308 in all ten global records. The even median at line237 adds its two central values, producing inf although the mathematical median is representable. Strict json.dumps at line285 raises ValueError. Actual exit1; neither tierB-v2.json nor coverage.md exists.
2. `finite-large-difference`: use the unchanged fixture except seed00 none RMS=-1e308 and global RMS=1e308. Both inputs are finite; the current contract explicitly retains finite-negative compatibility and specifies no sign/plausibility bound. The subtraction at line254 produces inf, which enters the regression record at lines258-259. Strict serialization again raises ValueError. Actual exit1; neither output exists.

These are deliberately extreme corruption/range controls, not plausible measured motion or a proposal for a physical-value threshold. They demonstrate a remaining route to the same diagnostic-loss failure class as R1: a single bounded input set can prevent the entire denominated audit and coverage from being written. No false numeric motion PASS was observed. The nonzero process exit is visible, but the requested machine-readable error state and null inference are absent. A finite-leaf decoder alone does not close this route.

Retained without retry or repair: boundary-01/{finite-large-median,finite-large-difference}/eval/B, stdout.log, stderr.log; full argv/exits/input SHA256s in BOUNDARY_PROBES.json. `boundary_probes.py` generates exactly these fixtures and runs the exact unmodified final adapter. Its collection harness exits0; that is not a PASS for the two CLI controls. Both actual adapter exits are1.

Recommended bounded follow-up: handle arithmetic range failure at the summary calculations explicitly, retaining strict-JSON audit/coverage and suppressing affected inference, with a declared error/accounting treatment. Preserve ordinary finite arithmetic and statistical policy. Do not clamp values, invent motion FAILs, introduce physical thresholds, relax gates or build a generic JSON sanitization framework. Re-review a distinct exact-source iteration. No more experiments were run after confirming these two mechanisms.

## Exact source, scope and license

Reviewed final: 95efc2989505cda083fc801eddb987405967ba93.
New adapter source: 2cd9376753ea41e406c0c6a3c63345433249b06a.
Author tested tools: e4f5820db9f2c87d83283e3d3a8805521321ae5f.
Original bounded base: 4f44f42233f2466f8461524badeba18522759f3c.
Prior v2/R1 final: e8e14fc5c44018cb5b583d9e9a6e9f3f4a580836.

Adapter git blob d4faf5799869fd9db8bfe3ef798eca79e1aeaf4c is identical at source/tested/final commits. Adapter SHA256 is 759084711ff1e08373c9a7f3fdae22d94f8f37ca79880d22a1c01a133a58fd45. New range/focused/baseline harness blobs also match tested and final heads. The only Python files added after the tested tools are generated restore/removal mutant evidence, not changed tools.

All changes from the bounded base are confined to analysis_record_errors_v2_20261023. All505 pre-existing owned files are byte-identical to e8e14fc5, including original v2 source, contracts and failures. Verified original504, v2.1-789 and final793 SHA256 manifest entries directly against exact git objects, zero mismatches. Final new-file membership has794 unique entries and exactly matches the additive diff from e8e14fc5. The retained author packaging sort-order failure and separate membership correction are consistent; neither changed an experiment. Existing generated whitespace was preserved.

The loader changes only by finite_float, the required-number predicate catches OverflowError, and the format marker changes to /2.1. Independent AST checks show every other common adapter function unchanged; original sign/McNemar, field access, failure components and band selection match the frozen summarizer. Original focused/baseline harness copies differ only in target filename. No gates, tolerances, effects, ordinary pairing arithmetic, multiplicity policy, native source, evaluator, worker or caller edits. SPDX GPL-2.0-or-later is retained, imports are Python stdlib, repository license/upstream provenance files unchanged. No additional scope/license finding.

## Independent passing verification and discrimination

All runs use /Users/alex.konstantinov/.local/bin/python3 -B (CPython3.13.7), SHA256 127b5dc839447e76f0ed6a6c3b3097dc7903547d2f1a1fe21d7fc40c20b7bc65. Exact extracted scripts are under exact/docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023. `run_checks.py` retains each command, environment, UTC, hashes, stdout/stderr and actual exits. One invocation of each:

- `range_controls_v2_1.py <scratch>/range-01`: exit0;111 assertions PASS. All six immutable R1 probe input sets were replayed from exact retained git objects. Original overflow-exit, nested-overflow reason and huge-integer required metric each exit2, write strict JSON plus coverage, retain one error seed/9 matched pairs and null both affected p-values. No numeric truth FAIL is invented. Negative overflow, nested NaN, unknown/unlocatable range input and ordinary finite-negative compatibility also pass. Conflicting cross-condition identities contaminate both expected identities; group mismatch and error+absence retain correct accounting.
- Three range restore mutants: default-parser restoration produces exit1/no outputs for both 1e999 cases; original finite_number restoration produces exit1/no outputs for10**400. All REJECTED. These discriminate diagnostic loss, not an improvement in motion-truth verdicts.
- `run_controls_v2_1.py <scratch>/focused-01`: exit0;114 assertions PASS. Includes valid metrics/labels, both-arm single-slot errors, non-EVALUATED/unknown/missing status, malformed JSON, duplicate keys, null/nonfinite required metrics, duplicates/conflicting ids, finite OUTSIDE_FIXED_ROI, and missing versus explicit UNRUN. Frozen base and drop-non-EVALUATED mutant both exit0/IN_PROGRESS with9 pairs for a present native failure; fixed adapter exits2/EVALUATION_ERROR with9 matched+1 error and null p-values. This separately discriminates the F8 state/exit failure. No tested mutant survives.
- `compare_baseline_v2_1.py /tmp/motioncorr-orchestrator-20261022/dc-B-pass3-collected <scratch>/baseline-01`: harness and adapter exit0;15 checks PASS. Read/hash736 records in place, zero differences from frozen EVALUATIONS.json, input bytes unchanged afterward. Every original field of80 rows,240 comparisons and878 regressions is identical. Coverage800=734 evaluated+66 missing,0 explicitUNRUN/errors, with2 separately audited plain CUDA controls. Nominal categories30 improves/185 neutral-mixed/1 harms/12 IN_PROGRESS/12 UNRUN; overall IN_PROGRESS.
- Additional evidence inspection, not another experiment: strict-parse30 generated summaries; independently assert cell and pair coverage sums10 and both p-values null for affected comparisons/global errors. All pass. EVIDENCE_INSPECTION.json retains exact AST/tool bindings, per-control exits, final manifest checks, all baseline input hashes and protected-checkout comparisons.

The unchanged harnesses read git HEAD from their extraction directory. GIT_DIR explicitly resolves the review checkout's gitdir for this read-only metadata query; their source_sha therefore says1f0a58bf. This is not claimed as the tested author revision. IDENTITY.json, SCOPE.json and EVIDENCE_INSPECTION.json bind exact git objects and script hashes to source/tested/final identities independently.

Key retained hashes:

- Original R1 report7c70b8b24b106e3fdf9f38d6a5fa8f6e5088d7e3c5d2e046463b5ad4024fd1c2; probes sourceb8e55d6781024d466a3695fc432ea1ec800e99ef12c21e4c57619090fa2ed34a.
- Prior TierB reviewb7d5ea7bc013aa3f71e20b07f1c9d29ceed8f4d55b52aa5292f3054ed1c064c0.
- Frozen evaluator dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d (static read only); frozen summarizer25fc2a25a8673d5484c38937b74681d09ce96b1bdb3306057ea9a4959f82a897.
- EVALUATIONS.json4ec94412fb98e6b1e4fda26b8b510e8f23c235a22ad162774e448c2a228d988a; frozen summaryd389944a16c2a8bba2b56728e9988d1c76e30bc882559b83108626ef873a928f.
- Snapshot34ed4c76f1f5091d88764e5178f57b167641a30f2487fa066536770efb303a5c; archive679d65fd112e89000d1162b7af1ccf729f1f728ef327d691078e196cc78d0767. Archive read/hashed in place via a read-only symlink; never extracted/copied.

## Context, retained failures and resources

Read supplied AGENTS.md, complete cached Notion plan/common brief, release plan section9, original contract/report, full prior TierB F1-F8 review and REVIEW_RESPONSE.md, full fresh R1 REPORT.md/PROBES.json/probes.py, v2.1 amendment/report, RANGE_CONTROLS and final packaging receipts. Refreshed issue262 and both full comments live through the GitHub connector, read only (https://github.com/KingAlejandro/MotionCorr-standalone/issues/262). No external writes/publication.

Initial occupancy/free space checked before writes/checks: busy macOS host (Defender/Jamf services prominent),3.8GiB available. Own UUID exclusive nonblocking lifetime flock acquired before evidence writes; shared /tmp/motioncorr-analysis-record-errors-v2-20261023.lock also acquired nonblocking before any data controls. Both retained in LEASE.json/SHARED_LEASE.json and held through evidence/report creation. Five numeric-thread variables all1; one stdlib JSON job at a time; macOS affinity unavailable/unpinned. Approximately12.6MiB allocated before final report, under64MiB; final resource receipt records disk/occupancy. Device UUID/native binary/ingest witness N/A for JSON-only checks. GPU paused/current occupancy UNKNOWN; no SSH attempt or gateway retry.

Reviewer metadata setup had one retained failure: an inferred /Users/alex.konstantinov/.t3/worktrees/MotionCorr container directory is not a git checkout; git exited128 and metadata launcher1. SETUP_FAILURE_01.txt records it. No control had run, no source/input was changed; a separate metadata invocation used the user-specified Documents root. No experiment retry. All range/focused/baseline harnesses passed on their only invocation. Both new boundary failures are retained unchanged. No source repair or silent rerun.

Read-only protected checkout identities/statuses are unchanged before/after:
review t3-27c413fe@1f0a58bf6e0639d8b62f74da52f250cc664c0b30 clean;
author t3-f9432421@95efc2989505cda083fc801eddb987405967ba93 clean;
Documents/MotionCorr@c8844894c7c6366abf297699b5312e4b775eb5b0 with its pre-existing untracked pr117-fix-measure-20260929/ only.
No checkout/reset/index/source edits, commits, pushes, PRs, comments, Notion, SSH, native/build/GPU/SMI/evaluator/worker/process-mock runs, nested agents or PR monitoring. Only fresh UUID evidence and lease handles were written.

## Limits and handoff

UNRUN: full campaign, caller integration, actual evaluator/worker exceptions, raw movie/native binary/remote RUN/RECEIPT re-audit, native execution, performance/cost and science. F1-F7 remain unchanged: fixed scene/deterministic motion, noise-only seeds/dependent affine copies, tiny uncalibrated effects/no CUDA none-vs-none replicate, unadjusted multiplicity, partial unmatched cohorts,2 not4 plain CUDA controls/plain-vs-none TierB UNRUN, field-distance-dominated failure union, and limited/post-partial-look endpoint provenance. TierC FOREIGN boundaries are unchanged.

Historical2 PASS/10 FAIL/4 UNIDENTIFIABLE and #65 UNRUN/INCONCLUSIVE remain unchanged. No M3/C1/C2/M6/default/policy recommendation. R2-F1 blocks standalone-versioned-draft readiness only; passing baseline/control evidence does not waive it. Parent owns the next bounded author iteration, any fresh review and all publication/scheduling decisions.

SHA256SUMS is this review's explicit regular-file whitelist, excludes itself and the external archive symlink; the archive hash is independently retained in baseline COMMAND.json. No memory-derived source state is relied on; live objects and retained inputs supplied all technical conclusions.
