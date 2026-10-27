# Final packet index (HELD consumer/oracle packet)

| Area | Where |
|---|---|
| Scientific design, admission and commands drafts | `PLAN.md`, `ADMISSION_DRAFT.json`, `COMMANDS_DRAFT.json` (original, unchanged) |
| Scorer v1/v2, oracle, retained-score checks | `score_fields.py`, `score_fields_v2.py`, `oracle_floor.py`, `ORACLE_FLOOR_*`, `EXISTING_SCORE_CHECK*.json` (unchanged) |
| v3 consumer (M1, L1-L6) | `SCORER_V3_PLAN.md`, `score_fields_v3.py`, `ADMISSION_DRAFT_v3.json`, `COMMANDS_DRAFT_v3.json`, `ADMISSION_AMENDMENT_v3.md`, `ORACLE_PROVENANCE_v3.md`, `tests/test_score_fields_v3.py`, `tests/mutation_controls_v3.py`, `logs_v3/`, `SHA256SUMS_v3`, `V3_INDEX.md`, `V3_DELTA_FOR_REVIEW/` |
| v4 pair/decision (M2) | `PAIR_V4_PLAN.md`, `pair_decision_v4.py`, `tests/test_pair_decision_v4.py`, `tests/mutation_controls_v4.py`, `logs_v4/`, `SHA256SUMS_v4`, `V4_INDEX.md`, `V4_DELTA_FOR_REVIEW/` |
| Driver contract and release checklist (new, documentation only) | `DRIVER_RELEASE_REQUIREMENTS.md` |
| Independent reviews | `reviews/R1_oracle_scorer_v2/`, `reviews/R2_consumer_v3/`, `reviews/R3_pair_decision_v4/` (R1 compact; sibling durable archives hold full originals) |
| Native access probes | `ACCESS_CHECK.json`, `access_r2/ACCESS_CHECK.json` (both: strict direct probes timed out, exit 255) |
| Integrity | `PACKET_SHA256SUMS` (every file in this directory except itself); the original `SHA256SUMS_v3` (27) and `SHA256SUMS_v4` (22) still verify inside this directory |

Key results: v3 109/109 (run3; run1 107 plus two surviving mutants, tests strengthened, criteria unchanged); v4 126/126 (run5; runs 1-4 kept, three
test defects and one code fix recorded); 11/11 and 31 killed + 5 declared shadowed guard controls. R3 verdict: M2 closed at the consumer level, no
BLOCK, no new MATERIAL, four LOW; L1 is a documented caller contract, L2-L4 are mandatory release-checklist items, none fixed now.

Durable originals (additive, with a verified COPY_INDEX.tsv): `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-final-packet-r1/`; earlier
siblings `Native-local-full-width-pilot-oracle-review-r1`, `...-pilot-consumer-review-r2`, `...-source-review-r1`, `...-implementation-r1`.

Not shown: any producer, driver, native or real-fixture result; final pins; byte neutrality; harm; science. HELD. Source/tests/CMake are not part of this
packet and are unchanged.
