# Review delta

Baseline text/package snapshots are under `review-baseline/`, with hashes in `review-baseline/BASELINE-SHA256.txt`. `REVIEW-DELTA.patch` shows changes to the consumer, manifest and protocol, plus the new controls harness. The original RESULT collision and duplicate protocol file are preserved byte-exact in the baseline directory.

## Changes

- Corrected the unchanged field-error labels to RMS/p95/max for runtime and STAR separately.
- Split and hard-pinned original v2 FAIL, v3 remaining-seven RESULT, v3 protocol and selector 1,1 regrade. Capture bytes now join to authoritative source pins; the selector 2,1 receipt is checked against all 94 source-index records, iteration inventory is scoped to CPU-affine capture paths, and runtime inputs join to the original index and pinned v3 identities.
- Enforced exact STAR coverage of 45 expected centre/frame rows, including unknown centre/frame, duplicate and missing rejection.
- Added the CPU64-only negative-control harness and metadata-only source-iteration scope fixture. Byte-mutated controls update their local manifest pins.
- Made the consumer refuse to overwrite its output.

## Verification

Syntax compilation passed for all four prepared Python files. Declared input hashes, tar membership, source pins, direct source-byte hashes and the metadata-only iteration-scope fixture passed. No capture arrays were read or numerically analyzed. Structural negative executions and numerical/CPU64 work remain UNRUN.

## Input tar

- Baseline SHA-256: `625d91c54307555bcea0642f3e95352e3d784ebe9572a5007d040390d4342468`
- Current SHA-256: `e0a04ac543c8f36a2c9fe6072a75d489b879ec1ec75d4353b996168f29821542`
