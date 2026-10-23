# Independent F8 v2 review: CHANGES REQUIRED

Verdict applies only to the standalone versioned Tier B summary-tool draft at
e8e14fc5c44018cb5b583d9e9a6e9f3f4a580836. One P2 correctness finding blocks readiness.
No full-campaign use, merge, production policy or scientific acceptance is approved.

## Finding R1 (P2): numeric range errors bypass the promised record-error summary

Exact source: docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023/summarize_v2.py,
lines 93-94 (JSON decoding), 64-65 (finite_number), 101-104 (audit values), and 273 (serialization).

Python's default JSON float parser accepts the numeric token `1e999` as positive
infinity; parse_constant only rejects the nonstandard NaN/Infinity tokens. With an
otherwise valid seed-00 global record containing `exit: 1e999`, read_records marks
an error but copies infinity into native_exit. Writing the audit then raises
ValueError at line 273. The same occurs with an INPUT_ERROR record whose supplied
reason contains a nested 1e999. Each actual CLI exit is 1, with no tierB-v2.json,
coverage.md or machine-readable EVALUATION_ERROR diagnostics.

A third independent probe puts the JSON integer 10**400 in truth.field.px.rms.
math.isfinite raises OverflowError at line 65 before a summary is constructed.
Actual CLI exit is again 1 and no summary is written. These are present record
errors, rather than the separately documented CLI/directory/output-creation
exceptions. They violate the strict-nonfinite/schema error and exit2 contracts.
They do not create a false numeric PASS; they lose the explicit, denominated
error report which is the purpose of this fix.

Reproductions are immutable under probes-01/{overflow-exit,overflow-audit-reason,
huge-integer-metric}/. PROBES.json retains argv, all input SHA256s, actual exits
and missing-summary results; stdout/stderr are retained per case. No probe was
retried or repaired. The source is unmodified.

Recommended bounded fix: reject float-overflow tokens during decoding, make the
required-number predicate return a record error rather than raise on oversized
integers, and ensure diagnostics remain strict-JSON serializable. Add CLI
discriminators for all three scenarios, asserting exit2, written audit/coverage,
one error seed slot and null affected p-values. Preserve the current iteration
and review the new exact source in a fresh independent task.

## Verified scope and identities

Author worktree: /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9432421.
Author branch: experiment/262-analysis-record-errors-20261023.
Base: 4f44f42233f2466f8461524badeba18522759f3c.
Contract: 6ac2b0950ca0c12a08c780d2afc55678755e5a60.
Adapter source: 0152caf226774d35d0abf861174830700704fe10.
Focused controls: b12a556e57852566008044e4b9729edaa2e00d39.
Baseline harness: ab237e8b368d63000ae87c13f1b156bb87f16f3f.
Final evidence-only head: e8e14fc5c44018cb5b583d9e9a6e9f3f4a580836.
Adapter SHA256 at all four source/test/final heads:
3614afe2c7fab034cbdfada3879f1315398b7ff6ac39709a8b53c1084ce78675.

All 505 added files are confined to the new owned subtree; no old files or caller
were changed. All 504 author SHA256SUMS entries verify against exact git objects.
The final commit changes no adapter blob. SPDX GPL-2.0-or-later is retained;
adapter dependencies are Python stdlib. No scope/license finding.

Reviewer checkout: /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-b1f9501e,
branch review-dc-record-error-fix, HEAD 1f0a58bf6e0639d8b62f74da52f250cc664c0b30.
It remained clean and unchanged. No checkout/index/author/root writes, new git
commits, nested agents, pushes, PRs, comments or Notion writes.

## Independent verification

All commands use /Users/alex.konstantinov/.local/bin/python3 -B (CPython 3.13.7).
Exact extraction paths are under exact/; IDENTITY.json binds git-object hashes
and the Python executable SHA256. No source was imported from the author checkout.

- `python3 -B exact/analysis_record_errors_v2_20261023/run_controls.py controls-01`:
  exit0, 114 assertions PASS. Ordinary valid arithmetic, labels, finite OUTSIDE
  ROI, null errors, statuses, duplicates, identity conflicts, unlocatable errors,
  missing versus UNRUN and both-arm single-seed error accounting pass. Frozen
  base and removal mutant both produce exit0/IN_PROGRESS/9 pairs for the present
  failure; fixed adapter produces exit2/9 matched/1 error/null p-values. This
  discriminates F8 behavior, not merely a message string.
- `python3 -B exact/analysis_record_errors_v2_20261023/compare_baseline.py
  /tmp/motioncorr-dc-B-pass3-analysis-review-r1-20261023-sonnet/inv1/snap baseline-01`:
  exit0, 15 checks PASS. Read/hash 736 inputs in place, zero mismatches against
  frozen EVALUATIONS.json, and input bytes unchanged afterward. Every original
  field of 80 rows, 240 comparisons and 878 regressions is identical. Coverage:
  800 experiment slots = 734 evaluated + 66 missing; zero error/explicit UNRUN;
  two separate CUDA CONTROL_ONLY records. Nominal categories remain
  30 improves/185 neutral-mixed/1 harms/12 IN_PROGRESS/12 UNRUN. Overall IN_PROGRESS.
- `python3 -B probes.py`: harness exit0; six independent CLI runs. Cross-condition
  conflicting filename/id correctly contaminates both identities, group mismatch
  correctly blocks its cell, and error+absence occupies one error pair slot.
  All three exit2 with written summaries and null p-values. The three numeric
  probes fail the required behavior as recorded above; harness exit0 only means
  its diagnostic collection completed, not that those probes passed.
- AST.json: exact AST equality for sign_p, mcnemar_p, g, failure, band_transfer.
  Static inspection and whole-baseline comparison confirm unchanged ordinary
  pairing math, effects, gates, tolerances and statistical policy. Error filtering
  intentionally removes invalid numeric observations while preserving expected
  slots and suppressing inference. No numeric motion FAIL is invented.

The unchanged author harnesses query git HEAD from their extraction directory.
GIT_DIR was explicitly set to the reviewer checkout for that read-only query;
their source_sha receipts therefore say 1f0a58bf. This is not claimed as the
tested author SHA. IDENTITY.json independently binds the exact tested adapter and
harness git objects to e8e14fc5 and the unchanged adapter to its source head.

The CLI contract is explicit: exit0 can mean incomplete; exit2 denotes present
record errors. No caller consumes this new format yet. Parent must separately
select/integrate it and inspect both exit and state. The three crashes above
prevent readiness even for this versioned standalone tool's promised behavior.

## Inputs, resources and limits

Read the full supplied Notion plan including W2/ground rules, AGENTS.md, release
plan section9, full old F8 review, qualified snapshot response and evaluator/
checker schemas. Refreshed issue262 and its two full comments live through the
GitHub connector; no issue or PR was changed. One comments-call schema error
(repo_full_name required) was corrected; it was not an experiment retry.

Prior review SHA256 b7d5ea7bc013aa3f71e20b07f1c9d29ceed8f4d55b52aa5292f3054ed1c064c0.
Evaluator SHA256 dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d.
Frozen summarizer SHA256 25fc2a25a8673d5484c38937b74681d09ce96b1bdb3306057ea9a4959f82a897.
Frozen summary SHA256 d389944a16c2a8bba2b56728e9988d1c76e30bc882559b83108626ef873a928f.
Snapshot SHA256 34ed4c76f1f5091d88764e5178f57b167641a30f2487fa066536770efb303a5c.
Archive SHA256 679d65fd112e89000d1162b7af1ccf729f1f728ef327d691078e196cc78d0767.
Archive was read/hash checked in place and linked read-only for the harness;
no archive extraction, full corpus copy or old result rewriting occurred.

Only this fresh UUID namespace was written. LEASE.json records the nonblocking
lifetime flock and holder; lease bootstrap precedes all evidence writes. One
stdlib data process at a time, all five numeric-thread environment variables=1.
Host occupancy was checked before checks (START receipts); busy macOS host,
affinity unavailable/unpinned. Scratch was approximately10MiB allocated, below
64MiB cap; approximately4GiB free at preflight. No contention or retry loop.
Device UUID, ingest route, native binary hash and GPU allocation are N/A for
JSON-only checks. No SSH/Linux/native/build/GPU/SMI/evaluator/worker/process-mock
execution, package installation or foreign-process modification.

Native evidence, performance, science, full campaign, real worker exceptions,
raw movies/binaries/remote RUN and RECEIPT bytes, and caller integration are UNRUN.
F1-F7, fixed scene/deterministic motion, noise-only/dependent affine conditions,
uncalibrated tiny effects, unadjusted multiplicity, partial cohorts, two rather
than four plain controls, plain-vs-none B UNRUN and TierC FOREIGN boundaries
remain. No endpoint floor or p-adjustment is adopted. Historical motion truth
2 PASS/10 FAIL/4 UNIDENTIFIABLE and #65 corrected workflow UNRUN/certification
INCONCLUSIVE remain unchanged; no M3/C1/C2/M6/default or policy decision.

Next action: return R1 to the existing author context for one bounded separate
numeric-validation iteration, then fresh exact-source review. Parent retains
publication, merge, scheduling and any full-summary selection.
