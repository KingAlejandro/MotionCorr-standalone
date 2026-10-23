# v2.2 freeze: derived-arithmetic diagnostics without changing input coverage

Frozen before code. Follow-up parent95efc2989505cda083fc801eddb987405967ba93.
R2 CHANGES REQUIRED report SHA256:
2d443581bebdffa00437912846c6006041941c6590b34993cc346f70b567b4d4.
New additive files only; all earlier versions/contracts/checks/failures/evidence
remain byte exact. Still a standalone Tier B tool; no caller adoption.

Finite input validity does not imply representability of summary arithmetic.
Keep those records EVALUATED and preserve audit identities, n, n_records,
cell coverage, matched pairs and expected10 seed slots. Aggregate arithmetic
errors must NOT be fabricated as malformed/error/missing input seeds.

Use the SAME st.median and subtraction as before, with targeted checks on their
results and only OverflowError catches at those operation sites. No stable-
median replacement, clamping, sign/plausibility bound, threshold or new policy.
Nonrepresentable derived values become null. Attach an explicit derived-error
event with condition/backend/arm/metric/operation, operand input ids and a text
reason/result representation (never a nonfinite JSON number). These diagnostics
are separate from record_audit errors and global_error_count, which retain their
existing meanings. Format marker /2.2; output filenames unchanged.

Audit all cell medians, paired subtraction, regression delta emission and paired
median. max selection returns an already validated finite input; counts, exact
sign/McNemar tests have at most10 seeds and bounded integer arithmetic. There
are no other unbounded arithmetic-derived values in this standalone adapter.

Cell median failure: keep valid input/failure counts, null only its failed median,
set that cell state EVALUATION_ERROR. Conservatively suppress BOTH sign_p and
failure_mcnemar_p on every comparison involving that cell, even if a different
metric is representable. Other cells keep their own honest states.

Paired subtraction failure: retain the matched input slot (pairs and coverage
matched count still include it). A finite_delta_count and unrepresentable_delta_count
partition matched pairs; W/L/T describe only representable deltas. Suppress the
full-cohort paired median if any delta is unavailable; never silently compute it
from a smaller subset. If operand ordering proves a regression, retain its record
with finite operands, null delta and a derived-error reference, rather than lose
it or serialize infinity. This ordering is diagnostic only for the failed delta;
ordinary finite W/L/T arithmetic is unchanged.

Paired-median failure: null median_delta, retain all matched inputs/finite-delta
counts and W/L/T. Any pair arithmetic failure sets that comparison category to
EVALUATION_ERROR and BOTH p-values null. A paired-only failure does not corrupt
otherwise representable cell aggregates or unrelated comparisons. Propagate
summary state EVALUATION_ERROR/CLIexit2 if ANY derived error exists, without
blocking unrelated cells/comparisons globally. Unknown/unlocatable INPUT errors
retain the earlier global blocking rule. Each actual operation failure is one
flat derived-error event; row/comparison references do not double-count events.

coverage.md must show overall state/derived-error count, row derived counts and
affected paired coverage; strict JSON must always retain record and derived
error diagnostics for these arithmetic sites. No numeric truth FAIL is invented.

Frozen controls: actual CLI on both immutable R2 input sets must exit2 with both
outputs, zero record errors, evaluated/matched10, zero fabricated error/missing
seeds, exact arithmetic events, null nonrepresentable values/p-values and honest
unaffected cells. Add an isolated paired-median fixture (each arm +/-5e307, deltas
1e308), finite near-boundary representable and ordinary negative fixtures.
Restore separately the cell median, paired subtraction, regression-delta emission
and paired median mechanisms; each must reproduce old exit1/report loss and be
rejected by the diagnostic contract. No false numeric PASS claim.

Copy original111 range,114 focused and15 baseline checks, only target filename
changes, with source-hash bindings. Their anchors/check logic stay unchanged.
One new-source-only baseline regeneration reads/hashes736 existing inputs in
place; every old field of80 rows/240 comparisons/878 regressions must match.
All failed new checks retained; repairs require a new committed iteration.

Local stdlib/GPL-2.0-or-later, numeric threads1; fresh occupancy/free space,
nonblocking lifetime shared analysis lease before writes (PID90861), cap128MiB.
No remote/native/build/GPU/SMI/evaluator/worker/process-mock, packages, signals,
publication/caller work or nested agents. GPU PAUSED. Fresh independent R3 before
publication/full-campaign use. All original native3eee0a4b/source packet4f44,
truth/statistical/science/default/F1-F7 and C1/C2/M6 qualifications stay unchanged.
