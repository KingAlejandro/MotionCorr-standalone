# R2 bounded author follow-up: derived-arithmetic diagnostics v2.2

PASS for local CLI/data controls, with fresh independent R3 REQUIRED before
publication/full-campaign use. No caller adoption or scientific/native claim.
R2 CHANGES REQUIRED and all earlier versions/failures/evidence remain intact.

## Exact source, worktree and scope

Worktree /Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-f9432421.
Branch experiment/262-analysis-record-errors-20261023.
Follow-up parent95efc2989505cda083fc801eddb987405967ba93.
Original bounded base4f44f42233f2466f8461524badeba18522759f3c.
All additions are inside analysis_record_errors_v2_20261023; all1299 files
already present at the follow-up parent remain byte-identical to their Git blobs.
No original manifests, controls, source, contracts or failure receipts changed.
FILES_v2_2.txt lists new files; SHA256SUMS_v2_2 binds them except itself.
The final commit adds evidence only, with source/control blobs unchanged.

- Frozen amendment and R2 retention: 4a53415daa94a22b7f630afce9e831ad05a37223.
- New adapter source: 264be46c273fa514b1c1dc0cdf72302062a3791e.
- New/pinned controls and exact tested head:
  070e3eab2af455f391395eacfcb8340a9abe2792.
- summarize_v2_2.py SHA256:
  c2f391822b880fba20b7a9571e4d5150fa3b365bd18afff2e44f90fef939ef45.
- Immutable v2.1 source SHA256:
  759084711ff1e08373c9a7f3fdae22d94f8f37ca79880d22a1c01a133a58fd45.
- R2 report SHA256:
  2d443581bebdffa00437912846c6006041941c6590b34993cc346f70b567b4d4.

## Contract and narrow change

A finite/schema-valid input stays EVALUATED. An aggregate arithmetic failure is
recorded separately as a derived-error event identifying operation, metric,
condition/backend/arm, relevant seed when applicable, and operand input ids.
Input byte identities remain in record_audit. Text reasons represent a failed
result safely; no nonfinite JSON number is inserted. Derived events do not
inflate malformed/error/missing input counts or global_error_count.

Targeted checks wrap the existing st.median and subtraction results, catching
only OverflowError at those arithmetic sites. The arithmetic itself is unchanged:
there is no replacement median, clamping, physical/sign threshold, generic JSON
sanitizer or broad catchall. Audited all seven cell median sites, paired deltas,
regression delta emission and paired median. max selects an already validated
finite input; remaining arithmetic counts/tests are bounded by10 seeds.

Cell median failure nulls only that nonrepresentable derived field, keeps n and
coverage, sets cell EVALUATION_ERROR and conservatively blocks both p-values for
comparisons involving the cell. Unrelated cells retain their states.

A failed paired subtraction keeps the matched input slot. pairs and coverage
matched remain10 for the R2 full-input fixtures. finite_delta_count plus
unrepresentable_delta_count partition those matched slots; W/L/T use finite
deltas only and are explicitly denominated. If any delta is unavailable, the
full-cohort median is null rather than computed on a selected subset. Operand
ordering can retain a known regression with its original finite operands, null
delta and an error reference. No unavailable delta becomes a tie or numeric FAIL.

A paired-median failure nulls median_delta but retains all finite deltas/W/L/T.
Any pair arithmetic failure sets EVALUATION_ERROR and BOTH sign_p and McNemar
p null. Paired-only errors leave representable cell medians/other comparisons
intact. Summary state becomes EVALUATION_ERROR/CLIexit2 for any derived error.
Unlike an unlocatable input error, this does not globally contaminate unrelated
inference. Each actual failed operation is counted once in derived_errors;
row/pair references do not duplicate the global event count. coverage.md shows
summary/row derived counts and affected matched/finite/unrepresentable counts.

Output format /2.2; filenames tierB-v2.json and coverage.md retained. Exit0 may
still describe incomplete work. Exit2 and a diagnostic label are not scientific
acceptance. Full accounting is frozen in AMENDMENT_v2_2.md.

## Actual CLI results and independent mechanism controls

Four harnesses ran once at070e3eab, all launcher exits0:

- derived_controls_v2_2.py:261 assertions PASS. Both R2 immutable actual CLI input
  sets read in place, zero hash mismatches; fixed adapter exits2 and writes strict
  JSON/audit/coverage. Both keep20 EVALUATED input audits, each complete arm n10,
 10 matched pairs, zero fabricated input errors/missing seeds and null affected
  p-values. Neither input set is relabelled malformed.
- finite-large-median produces exactly two events: cell_median/rms and
  paired_median/rms. Cell median and pair median are null; all10 deltas remain
  finite. The affected cell is erroneous; other cells keep honest states.
- finite-large-difference produces one paired_subtraction/rms seed00 event.
 9 finite deltas+1 unavailable=10 matched inputs, paired median null, and the
  regression retains -1e308/1e308 operands with null delta/error reference.
  The arm cells remain COMPLETE; the unaffected max comparison retains its
  original improves label and p0.001953125. Summary remains EVALUATION_ERROR.
- Additional bounded fixtures isolate paired-median overflow with arm values
  +/-5e307, exercise all seven cell median sites, and check accepted finite
  integer subtraction whose derived result exceeds float range. A representable
  +/-1e307 fixture preserves median delta2e307, harms and p0.001953125 without
  clamping. Original ordinary finite-negative compatibility also passes below.
- Four SEPARATE restore mutants bypass only the cell median, paired subtraction,
  regression delta emission or paired median protection. Each actual CLI exits1
  with strict-serialization ValueError and neither output, reproducing diagnostic
  loss, and is REJECTED. These distinguish the repaired mechanisms. No false
  numeric motion PASS was observed or claimed.
- range_controls_v2_2.py:111 original assertions PASS, including the three R1
  parsing/range failures, their diagnostic-loss restore mutants, finite-negative
  compatibility and unlocatable-error handling.
- run_controls_v2_2.py:114 original assertions PASS, including finite OUTSIDE ROI,
  record-error/duplicate/null/NaN schemas, valid math, missing versus UNRUN,
  frozen-base and drop-record discriminators. Original F8 state/exit rejection
  is separate from R1/R2 diagnostic-loss mutant rejection.
- compare_baseline_v2_2.py:15 original checks PASS; new source ONLY for the one
  baseline regeneration. All736 input hashes match frozen EVALUATIONS.json,
  input bytes unchanged afterward. Every original field of80 rows,240 pairs
  and878 regressions is parsed-identical. Nominal30 improves/185 neutral-mixed/
 1 harms/12 IN_PROGRESS/12 UNRUN unchanged. Coverage800=734 evaluated+66 missing,
  no errors/explicitUNRUN;2 plain CUDA controls separately audited. Overall
  IN_PROGRESS and derived_error_count0. Nothing regraded in the old packet.

No failed new harness/control or experiment retry. Expected mutant exit1 and
historical R1/R2 failures are retained byte exact. Harness copies differ ONLY
in target filename; HARNESS_BINDINGS_v2_2.json and STATIC_v2_2.json verify this.
All input-loader, finite-number and original sign/McNemar/failure/band/coverage
function ASTs match v2.1; only targeted derived sites and their reporting change.

## Whole commands and retained identities

Python prefix for every actual run: /Users/alex.konstantinov/.local/bin/python3 -B.
Commands below resolve script/attempt paths against this owned subtree:

    derived_controls_v2_2.py v2_2_attempt_01/derived
    range_controls_v2_2.py v2_2_attempt_01/range
    run_controls_v2_2.py v2_2_attempt_01/focused
    compare_baseline_v2_2.py /tmp/motioncorr-orchestrator-20261022/dc-B-pass3-collected v2_2_attempt_01/baseline

All four exit0; each has full absolute argv/source/harness SHA256/actual exit,
UTC and cap in v2_2_attempt_01/*-START.json and *-EXIT.json. DERIVED_CONTROLS.json
and inherited RANGE_CONTROLS/CONTROLS.json retain every child CLI argv/exit,
mutant ACCEPT/REJECT, script/input hashes, stdout/stderr and assertions. Baseline
COMMAND/START/COMPARISON.json bind Python executable hash and all736 inputs.
These retained commands are the exact runnable invocations, not planned checks.

Read/hash old frozen736 inputs in place; no corpus copy or archive extraction.
Native source3eee0a4b4e367f9b57f950c440c89679a5ec9c93 remains historical only.
Snapshot34ed4c76f1f5091d88764e5178f57b167641a30f2487fa066536770efb303a5c;
archive679d65fd112e89000d1162b7af1ccf729f1f728ef327d691078e196cc78d0767;
original summaryd389944a16c2a8bba2b56728e9988d1c76e30bc882559b83108626ef873a928f.

R2 selective byte-exact whitelist: review-r2-retained/WHITELIST.json binds50
regular files,172497 bytes: full REPORT, BOUNDARY_PROBES, boundary_probes.py,
identity/scope metadata, original reviewer SHA256SUMS, both40-record-total small
actual CLI input sets and their stdout/stderr. Duplicate large source/control/
baseline exports are omitted; original reviewer manifest is retained. No prior
review/source/failure artifact was rewritten.

## Resources, limits and next action

Local stdlib/GPL-2.0-or-later,14 logical CPUs, unpinned macOS affinity. Five
numeric-thread variables OPENBLAS/OMP/MKL/VECLIB_MAXIMUM/NUMEXPR all1 (full names
in harnesses). One local JSON job at a time. Fresh occupancy/free-space receipts
precede EACH harness; initial2.9GiB available. Nonblocking lifetime shared lease
/tmp/motioncorr-analysis-record-errors-v2-20261023.lock, PID90861, acquired before
writes and held through evidence commit/verification. No contention/retry loop.
Cap128MiB; new attempt approximately13.9MiB allocated before final receipts.
UUID/native binary/ingest witness N/A for JSON-only analysis; Python binary hash
retained. No packages, signals, remote compute connection/SSH, native/build/GPU/
SMI/evaluator/worker/process-mock runs or foreign-process changes. GPU PAUSED.

Fresh independent R3 must review the exact final head/source and focused controls
before publication or full-campaign use. No caller integration, real worker
exception test, raw movie/native binary/remote RUN/RECEIPT audit, native execution,
performance/cost, full campaign or science was run. All F1-F7 limitations remain:
fixed scene/motion, dependent noise/affine conditions, tiny uncalibrated effects,
unadjusted multiplicity, partial unmatched cohorts,2 not4 plain controls,
plain-vs-none and none-vs-none CUDA replicate UNRUN,54 TierC FOREIGN boundaries.
Historical2 PASS/10 FAIL/4 UNIDENTIFIABLE and #65 UNRUN/INCONCLUSIVE unchanged.
No M3/C1/C2/M6/default/policy decision. Parent owns publication/scheduling; no
push/PR/comment/Notion writes or nested agents.

## Diff-check qualification

Full staged diff-check exits2 only for the exact trailing space emitted by the
unchanged frozen summarizer in v2_2_attempt_01/focused/frozen-base/out/tables.md:26.
That old-code receipt is retained byte exact. Scoped diff-check excluding only
that generated table exits0; both commands/outputs are in DIFF_CHECK_v2_2.json.
No source/artifact repair or numerical rerun was made to remove the whitespace.
