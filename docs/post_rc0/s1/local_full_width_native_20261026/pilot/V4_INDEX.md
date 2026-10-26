# v4 pair/decision package index (HELD; nothing launched)

Adds only new files. Every v1-v3 file, the oracle, reviews, tests and logs are byte-unchanged: `V4_DELTA_FOR_REVIEW/originals_unchanged.txt`
(R2's 52-file `pilot_before.sha256` and `SHA256SUMS_v3`: all UNCHANGED). Branch source/tests/CMake stay at `215c37b0`. Hashes: `SHA256SUMS_v4`.

| file | purpose |
|---|---|
| PAIR_V4_PLAN.md (+ .sha256) | criteria and test list, frozen before any v4 code or test existed |
| pair_decision_v4.py | `admit_single` (v3 + case-insensitive witness prescan), `pre_ON_gate`, `admit_pair`, `decide_pilot`; anchored to the unchanged v3 files |
| tests/test_pair_decision_v4.py | 126 checks (logs_v4/test-run{1..5}.log; final run5) |
| tests/mutation_controls_v4.py | 36 guard-removal controls: 31 killed, 5 shadowed as declared (logs_v4/mutation-run{1,2}.log) |
| logs_v4/ | every run incl. failed attempts; ATTEMPTS_v4.md |
| V4_DELTA_FOR_REVIEW/ | read-only diff of the new files and the originals-unchanged proof |

R2 originals are archived additively at `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-pilot-consumer-review-r2/` (14 files, COPY_INDEX.tsv).

## What is exercised
- The pinned `compare_products.py` (53449d2d...5f0f47) runs as a subprocess (command, rc, stdout, stderr and JSON retained under decision_dir/pre_on and
  decision_dir/pair, never in product dirs) on synthetic minimal-MRC/STAR/EPS trees; it detects header, payload, STAR, EPS and inventory changes.
- `factorial_common.star_blocks` and `manipulation` are executed unchanged from the pinned file by AST extraction (the module has top-level venue path
  effects), with only `check` replaced by one that raises PairError; the extracted source hashes are recorded in each pair record.
- The pre-ON record binds OFF receipt/runtime/output inventory, the baseline pin inventory, comparator JSON/command/file, admission/commands files, tool
  pins, binary path+sha256 and the identity fields; any later drift is rejected. The real (HELD, null-field) admission can never satisfy the gate.

## Limits
- Synthetic receipts and tiny fake products test consumer logic only; they do not show that a producer obeys. No native, no real MRC pixels.
- The test admission is a modified copy whose launch fields are filled and whose input/baseline pins match the fake bytes; its hash replaces the module
  anchors (documented test double). Scoring is real only for noisy/affine (retained runtime/STAR/truth); other cases use crafted metrics to test rules.
- Declared shadowed guards (a different guard fires first; not claimed as kills): comparator rc vs verdict check, global DC-counter drift vs coupled-counter and
  manipulation coverage checks, global-eligible > 0 vs manipulation's own check, PAIR_BINARY vs per-arm binary checks (a mixed-sha pair fails with BINARY).
- The comparator keeps its design: logs, PDFs and `.lst` files are inventory-only, so OFF logs/PDFs may differ from the baseline (tested). OFF STAR and runtime
  must equal the retained bytes exactly; if a real STAR embeds its output root this fails closed.
- Not shown: any producer, final binary/source/venue pins, the 33 real fixture pins, the 8x19 retained baseline bytes at the venue. Native stays HELD.
