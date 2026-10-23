# Numeric-range follow-up: v2.1 implementation handoff

PASS for bounded local CLI/data controls. Fresh independent R2 is REQUIRED before
publication or full-campaign use. This tool remains standalone; no caller adopts
its output. R1 CHANGES REQUIRED and all original v2 evidence are preserved.

## Branch, scope and exact identities

Worktree /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9432421.
Branch experiment/262-analysis-record-errors-20261023.
Follow-up parent e8e14fc5c44018cb5b583d9e9a6e9f3f4a580836.
Original exact base4f44f42233f2466f8461524badeba18522759f3c.
Only additive files in analysis_record_errors_v2_20261023. All505 existing owned
files are byte-identical to e8e14fc5, including v2source/contracts/results/checks.
FILES_v2_1.txt lists the new files; SHA256SUMS_v2_1 binds them except itself.
The final evidence commit contains no adapter or control source changes.

- Amendment/review-retention freeze: b80fa15fb152dce5c84f055ee42402ef49027f05.
- New adapter source: 2cd9376753ea41e406c0c6a3c63345433249b06a.
- New/pinned control source and exact tested head:
  e4f5820db9f2c87d83283e3d3a8805521321ae5f.
- summarize_v2_1.py SHA256:
  759084711ff1e08373c9a7f3fdae22d94f8f37ca79880d22a1c01a133a58fd45.
- Immutable v2 adapter SHA256:
  3614afe2c7fab034cbdfada3879f1315398b7ff6ac39709a8b53c1084ce78675.
- R1 report SHA256:
  7c70b8b24b106e3fdf9f38d6a5fa8f6e5088d7e3c5d2e046463b5ad4024fd1c2.

## Minimal change and contract

V2.1 adds parse_float=finite_float. It performs the usual float conversion,
rejecting an overflowed result with ValueError before decoded metadata can be
copied into the audit. All parsed float leaves, including nested reasons,
are finite. Existing nonstandard-constant/duplicate-key/JSON-object validation
remains in force. finite_number catches only OverflowError from the existing
math.isfinite call, routing an oversized required integer to its existing
record-error path. There is no broad exception handler, recursive sanitizer,
metric invention, clamping or new numerical/statistical endpoint.

A malformed/range-error record retains exact input byte hash, filename and
conversion diagnostic. If complete decoding fails, declared metadata remains
null; no regex identity salvage. The known filename supplies its expected seed
slot. An unknown filename is unlocatable and blocks inference/complete labels
globally rather than fabricating a seed identity. This is the existing schema
contract; see AMENDMENT_v2_1.md for the frozen justification.

Locatable errors retain10 expected slots=9 matched+1 error for the selected
comparison, and both inferential p-values are null. No input/evaluator error
becomes a numeric truth FAIL. Format marker is /2.1; output filenames remain
tierB-v2.json and coverage.md. Exit2 means written EVALUATION_ERROR diagnostics;
exit0 may still describe incomplete work. Neither is scientific acceptance.

## Actual CLI controls and mutant meaning

All three harnesses exited0 on their first invocation, at e4f5820d:

- range_controls_v2_1.py:111 assertions PASS. Replayed the six R1 immutable
  probe input sets in place. All six exit2 with strict-JSON summary/audit,
  coverage and affected p-values null. The three newly repaired range cases
  retain their one expected error seed and exact input hashes.
- Added negative1e999, nested NaN and unlocatable-range cases exit2 with
  strict-JSON diagnostics. The unknown filename blocks all inference without
  inventing a slot. Finite negative-number compatibility exits0 and retains
  the old arithmetic, demonstrating no added numeric sign/gate policy.
- Restoring Python's default float decoder reproduces exit1/no summary/no
  coverage for overflow-exit and overflow-audit-reason. Restoring the uncaught
  finite-number predicate reproduces exit1/no outputs for huge-integer-metric.
  All three mutants are REJECTED by the diagnostic contract. These are
  diagnostic-loss discriminators: old code did not produce a false numeric
  PASS, and no motion-truth gate verdict is claimed to change.
- run_controls_v2_1.py:114 original assertions PASS. Copies differ only in the
  target adapter filename; HARNESS_BINDINGS_v2_1.json pins the original bytes.
  Non-object/duplicate/NaN/null/status/identity/absence/UNRUN/finite-OUTSIDE-ROI
  behavior and valid arithmetic remain. The existing removal mutant and frozen
  base are rejected for exit0/IN_PROGRESS instead of the required present-error
  state. That F8 state/exit discriminator remains separate from R1 report loss.
- compare_baseline_v2_1.py:15 original checks PASS. Only the new adapter is
  used for the one frozen baseline regeneration; no evaluator runs. All736
  input SHA256s match and their bytes remain unchanged afterward. Every old
  field of80 rows,240 comparisons and878 regressions is parsed-identical.
  Nominal30 improves/185 neutral-mixed/1 harms/12 IN_PROGRESS/12 UNRUN remain.
  Coverage800=734 evaluated+66 missing,0 errors/explicitUNRUN, plus2 separately
  audited plain CUDA controls. Overall IN_PROGRESS, as before.

No failed new harness or unexpected fixed-source control was repaired/retried.
Expected mutant failures, full stderr and exits are retained in the new attempt;
original R1 failure artifacts remain byte exact. See RANGE_CONTROLS.json for
per-command ACCEPT/REJECT, raw argv, source/input hashes and expected exits.

STATIC_v2_1.json confirms all common adapter function ASTs except the required
predicate and loader are unchanged; the loader differs only by parse_float.
All harness assertion logic is unchanged. No stats/gates/tolerance edits.

## Commands, hashes and resources

Python for all actual runs: /Users/alex.konstantinov/.local/bin/python3 -B.
Exact harness commands (all exit0), from this subtree:

    range_controls_v2_1.py v2_1_attempt_01/range
    run_controls_v2_1.py v2_1_attempt_01/focused
    compare_baseline_v2_1.py /tmp/motioncorr-orchestrator-20261022/dc-B-pass3-collected v2_1_attempt_01/baseline

Every child runs the actual Python CLI. Parent *-START/EXIT.json retain full
absolute argv, source/adapter/harness hashes, actual exits and UTC. Child
RANGE_CONTROLS.json/CONTROLS.json and baseline COMMAND/COMPARISON.json retain all
input hashes, Python executable hash, outputs and expected rejection behavior.
No old archive/corpus was copied; the frozen736 input files were hashed/read
in place. Snapshot34ed4c76f1f5091d88764e5178f57b167641a30f2487fa066536770efb303a5c,
archive679d65fd112e89000d1162b7af1ccf729f1f728ef327d691078e196cc78d0767,
original summaryd389944a16c2a8bba2b56728e9988d1c76e30bc882559b83108626ef873a928f.

OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=VECLIB_MAXIMUM_THREADS=
NUMEXPR_NUM_THREADS=1. One local stdlib data job at a time on macOS,14 logical
CPUs, affinity unavailable/unpinned. Fresh bounded occupancy logs precede each
harness. Nonblocking lifetime lease /tmp/motioncorr-analysis-record-errors-v2-20261023.lock,
PID72708, acquired before any follow-up writes, held through final evidence
commit/verification. PRECHECK_v2_1.json records4GiB free, cap128MiB; new attempt
approximately10.5MiB allocated before final receipts. No contention/retry loop.
Device UUID/native binary/ingest route are N/A for this JSON-only analysis.
No packages, remote connection attempts, SSH/Linux/native/build/GPU/SMI/evaluator/
worker/process-mock jobs or foreign-process changes. GPU remains PAUSED.

## Retained review and limits

review-r1-retained/ preserves the full R1 report, PROBES.json, probes.py, identity,
AST/final metadata, reviewer SHA256SUMS, and all six small probe inputs/stdout/
stderr byte exact. WHITELIST.json binds138 selected files (approximately238KiB).
Duplicate source/check exports and large positive-probe summary exports are
omitted, with original hashes retained. No old review artifact is rewritten.

Fresh independent R2 must review the final head and adapter blob before any
publication/full-campaign use. This does not integrate a caller or inspect real
worker exceptions. Raw movies/native binaries/remote RUN and RECEIPT bytes,
performance, native correctness, cost, science and full campaign are UNRUN.
Native3eee0a4b / source packet4f44 and historical2 PASS/10 FAIL/4 UNIDENTIFIABLE
remain unchanged. F1-F7, fixed scene/motion, noise-only/dependent affine draws,
tiny uncalibrated effects, unadjusted multiplicity, partial cohorts,2 not4 plain
controls, plain-vs-none UNRUN,54 TierC FOREIGN boundaries and none-vs-none CUDA
replicate UNRUN persist. #65 UNRUN/INCONCLUSIVE, M3/C1/C2/M6/default and policy
boundaries remain. Parent owns publication and scheduling; nothing pushed,
published, commented or written to Notion, and no nested agents were spawned.

## Diff-check qualification

Full staged diff-check exits2 solely on a trailing space generated by the
unchanged frozen-base summarizer in v2_1_attempt_01/focused/frozen-base/out/tables.md:26.
The receipt remains byte exact. Scoped diff-check excluding only that generated
old-code table exits0; DIFF_CHECK_v2_1.json retains both commands/results. No
artifact was repaired or numerical/control run retried to remove whitespace.
