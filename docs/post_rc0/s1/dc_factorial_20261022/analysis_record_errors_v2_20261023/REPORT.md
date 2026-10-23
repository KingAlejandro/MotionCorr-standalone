# F8 bounded implementation handoff

PASS for local summary-tool controls and frozen-input regeneration. Fresh
independent exact-source review remains required. No publication or adoption.

Worktree: /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9432421
Branch: experiment/262-analysis-record-errors-20261023
Exact base: 4f44f42233f2466f8461524badeba18522759f3c
Owned subtree: docs/post_rc0/s1/dc_factorial_20261022/analysis_record_errors_v2_20261023/
The final evidence commit is summary/evidence only; obtain final head with
`git rev-parse HEAD`. FILES.txt is the complete owned file list; SHA256SUMS
binds every owned file except itself. No existing packet/tool/source was edited.

## Commits and tested identities

- Contract freeze: 6ac2b0950ca0c12a08c780d2afc55678755e5a60.
- Adapter source: 0152caf226774d35d0abf861174830700704fe10.
- Focused black-box controls: b12a556e57852566008044e4b9729edaa2e00d39;
  controls ran at that exact head, 114 assertions PASS, launcher exit0.
- Frozen comparison harness: ab237e8b368d63000ae87c13f1b156bb87f16f3f;
  baseline ran at that exact head, 15 checks PASS, launcher/adapter exit0.
- summarize_v2.py SHA256:
  3614afe2c7fab034cbdfada3879f1315398b7ff6ac39709a8b53c1084ce78675.
  This adapter blob is unchanged across both tested heads and the evidence commit.

## Behavior and retained outcomes

Present unsuccessful/unknown/malformed/duplicate/conflicting records become
EVALUATION_ERROR with filename, declared identity/status/exit, supplied reason,
sampling, byte SHA256 and diagnostics. Such a record remains in the expected
cell denominator; affected comparisons expose matched/error/missing/UNRUN seed
counts and error ids. Both inferential p-values become null for affected
comparisons. Numeric deltas/regressions for valid matched records remain
explicitly descriptive. Input/resource/evaluator errors do not become numeric
motion-truth FAILs. Unknown unlocatable inputs block all complete labels.

CLI exit2 means present-record EVALUATION_ERROR. Exit0 means an error-free
summary was written, including potentially incomplete work. Missing records
and explicit UNRUN records have separate counts. No caller integration is
performed: invoke the new adapter explicitly, and inspect its state and exit.
A throwing evaluator may leave no record; absence cannot identify why it is
missing. The adapter cannot reconstruct an unrecorded exception from absence.

The complete fixture retains exact arithmetic, nominal label and failure-union
statistics. Both frozen base and drop-non-EVALUATED mutant return exit0 and
IN_PROGRESS for one present native failure; the discriminator rejects both.
The fixed source returns exit2, keeps9 matched+1 error seed and null p-values.
Both-arm errors occupy one affected seed slot. Other controls cover unknown
and missing status, malformed/non-object/duplicate-key/nonfinite JSON, duplicate
and conflicting identities, INPUT_ERROR, null field, absent/UNRUN, OUTSIDE ROI
with finite metrics and OUTSIDE ROI with a null required image metric. No
failed control/harness invocations or in-place repairs occurred. Expected
error-case child exits2 and mutant/base discriminator rejections are retained
in attempt-01/CONTROLS.json, with every child command, input hash and output.

OUTSIDE_FIXED_ROI keeps finite applicable field/image metrics and its existing
failure component. Tier B evaluator always computes independent image metrics;
it declares no null-image exemption. Null required Tier B metrics are explicit
record errors, never zero or silent removal. Tier A null/ROI handling is untouched.
See CONTRACT.md for source/schema and caller-exit justification.

## Frozen baseline: exact data comparison, not regrading

Read/hash existing 736 inputs in place; no archive extraction or corpus copy.
All736 digests match frozen/EVALUATIONS.json. One v2 regeneration reproduced
every original field of80 rows,240 comparisons and878 regressions exactly.
Original nominal categories remain30 improves /185 neutral-mixed /1 harms /
12 IN_PROGRESS /12 UNRUN. Coverage is800 expected experiment slots:734 evaluated,
66 missing,0 errors,0 explicit UNRUN. Two additional plain CUDA CONTROL_ONLY
records are audited separately. Overall state remains IN_PROGRESS. The66 missing
records are expected experiment slots, distinct from the snapshot's68 excluded
jobs (which also include2 plain CPU controls).

Frozen native source: 3eee0a4b4e367f9b57f950c440c89679a5ec9c93.
Snapshot: 2026-10-22T22:44:59Z;
SHA25634ed4c76f1f5091d88764e5178f57b167641a30f2487fa066536770efb303a5c.
Archive SHA256679d65fd112e89000d1162b7af1ccf729f1f728ef327d691078e196cc78d0767.
Frozen summary SHA256d389944a16c2a8bba2b56728e9988d1c76e30bc882559b83108626ef873a928f.
Frozen summarizer SHA25625fc2a25a8673d5484c38937b74681d09ce96b1bdb3306057ea9a4959f82a897.
Evaluator SHA256dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d.
Baseline START/COMMAND/COMPARISON.json retain all input hashes, Python executable
hash, exact argv, exit and parsed comparison checks. The copied sign/McNemar,
g, failure and band-transfer function ASTs match the frozen source exactly.

## Commands and resources

Both harnesses ran `/Users/alex.konstantinov/.local/bin/python3 -B`, with
OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=VECLIB_MAXIMUM_THREADS=
NUMEXPR_NUM_THREADS=1. Exact invocation paths/exits are in LAUNCH.json and child
commands in CONTROLS.json or COMMAND.json. Scratch is only this new subtree,
within256MiB (approximately7.6MiB allocated before final receipts). No packages
installed. macOS,14 logical CPUs, one stdlib process at a time; affinity is not
available/pinned. Nonblocking lifetime flock:
/tmp/motioncorr-analysis-record-errors-v2-20261023.lock, holder PID10339,
acquired before branch checkout/writes and held through checks/evidence commit.
Occupancy was refreshed before both control/regeneration runs (LAUNCH.json).
No contention/retry loop, SSH/Linux/build/native/GPU/SMI or foreign process changes.
UUID, native binary and ingest route are N/A for this JSON-only analysis. Python
binary hash is recorded; no native execution qualification is implied.

## Limits and next bounded action

This closes only F8 in a separate versioned tool, pending independent review.
It does not repair F1-F7, statistical policy or evaluator/worker namespaces.
Fixed scene/motion, noise-only seeds, dependent affine conditions, tiny
uncalibrated deltas, unadjusted multiplicity, incomplete cohorts,2 rather than4
plain controls, plain-vs-none UNRUN and54 Tier C FOREIGN boundaries remain.
None-vs-none CUDA correctness replicate is UNRUN under the experiment pause.
Raw movies, native binaries and remote receipt bytes were not re-audited here.
No native correctness, cost, science, full-campaign completion or M3 claim.
Historical2 PASS/10 FAIL/4 UNIDENTIFIABLE, #65 UNRUN/INCONCLUSIVE, M4 default-OFF
experimental/excluded-C1 and unresolved C2/M6 remain unchanged.

Parent next action: fresh independent read-only review of the final head and
adapter blob, rerun the focused data controls in fresh bounded scratch under a
nonblocking lease, inspect exit/state consumption before any separate full-
campaign summary. Parent owns publication and scheduling. Nothing pushed,
published, linked, commented or written to Notion; no nested agents.

## Diff-check receipt

The complete staged `git diff --cached --check` reported exit2 for one trailing
space in attempt-01/frozen-base/out/tables.md:26, generated by the unchanged
frozen summarizer ("Checker totals per backend/arm: "). That exact old-code
receipt is retained byte-for-byte. A scoped staged diff-check excluding only
that generated frozen-base table passes, exit0. No source/fixture/output was
repaired or experiment rerun to remove the whitespace.
