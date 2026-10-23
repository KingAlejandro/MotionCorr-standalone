# Tier B analysis-record errors v2: frozen contract

Issue: https://github.com/KingAlejandro/MotionCorr-standalone/issues/262
Base: 4f44f42233f2466f8461524badeba18522759f3c. Scope is a new standalone
Tier B summary adapter, not evaluator, worker, native code or old evidence.
F8 review SHA256 b7d5ea7bc013aa3f71e20b07f1c9d29ceed8f4d55b52aa5292f3054ed1c064c0.

## Source and caller inspection

Frozen tools/summarize.py (SHA256 25fc2a25...897) indexes by declared id,
overwriting duplicates, then drops non-EVALUATED pairs and calls fewer than ten
pairs IN_PROGRESS/UNRUN. Its main always exits 0 if it reaches the end, without
an evaluation-error result. Frozen tools/evaluate.py (dcc5ddb3...e14d), tier_b,
emits NATIVE_FAILURE for nonzero native exit, CONTROL_ONLY for plain, otherwise
EVALUATED. A thrown input/checker exception terminates the evaluator nonzero;
it need not leave a per-case record. Absence alone therefore cannot prove an
input error or a successful native run. No evaluator or caller is repaired here.
Worker-v5 explicitly says its namespaces are not yet evaluator compatible.

This new CLI reads EVAL_DIR/B/*.json and writes only a previously absent OUT_DIR.
Exit 0 means a descriptive summary was written without present record errors,
even when incomplete; exit 2 means EVALUATION_ERROR, with diagnostics written.
Neither exit is motion-truth/scientific acceptance. Input-directory/CLI/output
creation failures are nonzero exceptions. This is an explicitly invoked Tier B
adapter; it does not replace the all-tier caller or import its output anywhere.

## Classification and denominators

The frozen ten conditions x two backends x four arms x ten seeds define 800
expected experiment identities. Bind filename stem, id, backend, arm and group.
Preserve filename, byte SHA256, declared identity/status/exit, supplied error
reason and sampling in a record audit. This is evaluation-input identity, not
an independent raw-movie audit. Plain CONTROL_ONLY records are audited separately.

Absent identity is MISSING. A present explicit UNRUN with no truth/image metrics
and no nonzero native exit is UNRUN. Neither is an evaluator error. Every other
non-EVALUATED status, malformed JSON/schema/status, identity conflict, duplicate
identity (even identical bytes), nonzero EVALUATED exit, nonfinite/null required
metric or input-error record is EVALUATION_ERROR. Never invent numeric metrics
or convert these errors into a motion-truth FAIL. Unlocatable input errors make
the whole summary erroneous and block complete labels globally; locatable
errors block their affected cells/comparisons. No last-record-wins selection.

For EVALUATED records require the schemas/fields consumed by the frozen Tier B
summary, finite scalar metrics, declared sampling VALID/OUTSIDE_FIXED_ROI,
PASS/FAIL field-distance status, convergence bool/null and local-enabled bool.
OUTSIDE_FIXED_ROI is retained, with applicable field metrics and its existing
failure component. Tier B evaluate.py always calls the independent image
check_realistic_image.evaluate_sum, which emits interior metrics even for
OUTSIDE_FIXED_ROI. It defines no null-image exemption. Null required Tier B
metrics are record errors; do not reinterpret them as zero, a numeric FAIL or
an abstention. Tier A invalid-ROI/null contracts and all checkers are untouched.

Each cell reports expected=10, present, evaluated, missing, unrun and error
counts; evaluated+missing+unrun+error=10. Partial descriptive medians and failure
components use valid evaluated records only and state their denominator.
Observed native nonzero exits are separately counted, not truth failures.

For each paired comparison retain ten expected seed slots and report matched,
error, missing and explicit-unrun pair counts (error takes precedence, then
missing, then unrun). Also retain each arm's cell coverage and affected ids.
Any record error in either arm yields category EVALUATION_ERROR and null sign
p and McNemar p. Valid matched W/L/T, deltas and regressions remain descriptive
with explicit matched counts; no inferential p-value from a selected subset.
Without errors preserve the frozen IN_PROGRESS/UNRUN labels and exact original
math, tests, gates, effects and tolerances, including partial-cohort p-values.
These legacy partial p-values remain exploratory and explicitly denominated.

## Focused controls, frozen before implementation

Small generated immutable per-case fixtures: complete EVALUATED math/labels;
one-arm and both-arm present errors; malformed JSON/unknown status; true
absence versus explicit UNRUN; duplicate/conflicting identity; input error and
null required field; OUTSIDE_FIXED_ROI retains finite field/image metrics.
Restore-removal mutant discards non-EVALUATED records and must fail the
present-error discriminator. Retain every failed invocation; repairs require
a separate committed iteration, never overwrite an attempt.

Read/hash the 736 frozen inputs in place, regenerate once with v2, compare all
old row/pair/regression fields as parsed data against frozen tierB.json. Additive
format/coverage/audit fields are versioned. No archive extraction or corpus copy.
Local stdlib only, python3 -B, numeric-thread environment 1, nonblocking lifetime
lease /tmp/motioncorr-analysis-record-errors-v2-20261023.lock; scratch cap256MiB.
No GPU/native/build/SSH/timing work. Host affinity unavailable on macOS; UUID,
native binary hash and ingest route are not applicable to JSON-only analysis.

Historical totals, 878 regressions and nominal 30/185/1/12/12 labels are frozen,
not retrospectively regraded. F1-F7 and raw-input identity limitations remain.
No full-campaign, M3, default, science, cost, C1/C2 or M6 claim. Recommend a fresh
independent exact-source review after this bounded implementation.
