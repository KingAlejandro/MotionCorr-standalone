# v2.1 amendment: retain diagnostics for numeric range record errors

Frozen before implementation. Parent head e8e14fc5c44018cb5b583d9e9a6e9f3f4a580836.
Independent R1 CHANGES REQUIRED report SHA256:
7c70b8b24b106e3fdf9f38d6a5fa8f6e5088d7e3c5d2e046463b5ad4024fd1c2.
Original v2 source/contracts/controls/results/review failures remain byte exact.
This adds summarize_v2_1.py and versioned controls/evidence in this subtree only.

R1 establishes three diagnostic-loss defects, not false numeric PASSes:
JSON1e999 can decode to inf in native_exit or a nested INPUT_ERROR reason, then
strict audit serialization raises; integer10**400 in a required metric raises
OverflowError in math.isfinite. Existing114/15 passes remain historical.

Minimal repair: supply a parse_float callback which uses the usual float()
conversion and raises ValueError if the result is nonfinite; leave the existing
parse_constant/duplicate-key/JSON-object validation in place. All decoded
float leaves, including nested audit metadata, are therefore finite. Conversion
failures are caught by the existing record-error path before audit fields are
copied. No recursive sanitizer, arbitrary token replacement or broad exception
catch is added. Required-number validation catches only OverflowError from
math.isfinite and returns false, taking the existing invalid-metric record-error
path. No metrics are invented, coerced, clipped or converted into truth FAIL.

A range error that prevents complete decoding retains filename and byte hash,
with the exact conversion-error reason. No declared metadata is fabricated or
salvaged by regex from malformed JSON. An expected filename maps to its one
seed slot; an unrecognizable filename cannot supply a schema-validated identity
and is a global input error, blocking all complete labels/p-values. This follows
v2 read_records' existing malformed-record/identity contract and Tier B's exact
filename/id/arm/backend/group schema. Keep unknown declared metadata null when
decoding fails. Successful numeric decoding retains v2 metadata as before.

The output format marker becomes motioncorr-dc-tierB-record-errors/2.1; filenames
remain tierB-v2.json and coverage.md so existing standalone data checks can be
reused. Exit2 means written EVALUATION_ERROR summary/audit/coverage; exit0 can
still mean incomplete. Neither is scientific acceptance; no caller adopts it.

Controls frozen here: replay all six immutable R1 probe inputs, including the
three actual range CLI cases; assert exit2, both output files, strict JSON audit,
input hash, one affected expected seed slot (where locatable),9 matched pairs
and null affected p-values. Restore parser-only mutation must reproduce missing
summary exit1 for both overflow-token cases; restore finite-number predicate
must reproduce missing summary exit1 for the huge integer. These mutants are
rejected by the contract, while original v2 failure receipts remain intact.
Also check negative overflow, nested nonstandard NaN, non-object, duplicate keys,
unlocatable range errors, and ordinary finite negative-number compatibility.

Reuse the original114 assertions and15 baseline checks with pinned original
harness identities. Make additive copies differing only in their target filename
summarize_v2_1.py; do not alter check logic. Baseline reads/hashes736 frozen inputs
in place once using new source only. Preserve all ordinary metrics/labels and
finite OUTSIDE_FIXED_ROI, missing-vs-UNRUN behavior, thresholds/statistical policy.
No new numerical endpoint or campaign/evaluator/native run.

Local Python CLI/data only, numeric environment1, fresh occupancy and nonblocking
lifetime lease /tmp/motioncorr-analysis-record-errors-v2-20261023.lock (PID72708),
cap128MiB. macOS affinity unpinned; native/GPU UUID/binary/ingest N/A. No remote
connections, nested agents, source outside subtree, publication or caller work.
All failed new checks are retained; repairs need a separate committed iteration.
Fresh independent R2 is required before publication/full-campaign use. All native
3eee0a4b / packet4f44 qualifications, F1-F7, truth/science/defaults are unchanged.
