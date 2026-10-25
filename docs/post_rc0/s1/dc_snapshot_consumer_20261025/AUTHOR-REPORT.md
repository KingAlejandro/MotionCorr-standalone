# DC v2.2 snapshot consumer — ready for parent CPU64 run

Date: 2026-10-25. Scope is the frozen DC snapshot only. All authored files and outputs remain under `/tmp/motioncorr-20261025-dc-consumer`; no project branch was edited.

## Implementation

`dc_snapshot_consumer.py` is a bounded caller for the unchanged standalone v2.2 adapter. It verifies the copied 736 record files against the original `EVALUATIONS.json` ID/hash map, verifies the frozen queue/RUN/Tier A and retained-artifact hashes, then invokes exactly:

```text
python3 -B summarize_v2_2.py EVAL_DIR NEW_ADAPTER_OUTPUT_DIR
```

It keeps adapter exit and summary state as separate receipt fields, joins queue IDs to RUN exits and Tier B evaluation coverage, preserves the orphan separately, and compares parsed `rows`, `pairs`, and `regressions` arrays with the retained expected artifact. It does not inspect evaluator metric values or reimplement their validation/statistics. Adapter JSON and `coverage.md` remain byte-for-byte child outputs in the new run namespace.

The only v2.2 summary-state enums are:

| Adapter state | Required adapter exit | Meaning in this report |
|---|---:|---|
| `COMPLETE` | 0 | All Tier B summary rows have ten evaluated inputs; it does not complete the campaign or establish science. |
| `IN_PROGRESS` | 0 | Tier B summary coverage is incomplete. |
| `EVALUATION_ERROR` | 2 | The adapter retained present-input or derived-arithmetic errors. This is not a motion-truth failure. |

The wrapper records `READY_FOR_PARENT_REVIEW` only when the child output, exit/state pair, and frozen baseline comparison are coherent. Other explicit outcomes include `EXIT_STATE_MISMATCH`, `SUMMARY_MISSING`, `SUMMARY_MALFORMED`, `SUMMARY_FORMAT_INVALID`, `CONSUMER_CONTRACT_MISMATCH`, and `BASELINE_DIFFERENT`. There is no generic scientific `PASS` enum. Wrapper exit 0 means the report was consumed coherently; it does not promote the adapter state.

## Input and historical evidence

- Corrected-path collection receipt: `COLLECTION-ATTEMPT2.json`, 736 records, 43,425,487 content bytes, all hashes matched; archive SHA256 `b787ca32838b7ef9b94f310ebed91883fffdcd97f31132652481626862a401a0`.
- `COLLECTED_INPUTS.tsv` lists the 736 IDs/hashes and corrected source path `S/eval/B`. The earlier proposed `S/B` list remains as `MISSING_INPUTS.tsv` history; `COLLECTION-ATTEMPT1.json` retains its path-not-found outcome. The corrected location is based on the parent’s worker source readback and successful collection receipt.
- The original expected v2.2 summary is copied to `expected/tierB-v2.json`, SHA256 `c2d8d92bbafbc950576c4709309412b4b8b6dfa99a2dabf59e42a09ee9f69e8a`. It contains 80 rows, 240 comparisons, and 878 regressions. The caller compares these arrays exactly; it never rewrites the artifact.
- The older 371-regression artifact remains separately copied as `expected/tierB-older-371.json`, SHA256 `c9956b9f82acb639317d77077961ab0c379844caec4f59aa8c0917dd09331d5b`. The caller verifies its identity/count but does not combine it with the 878-regression snapshot.
- Queue: 1,700 entries. RUN inventory: 1,403 exit-0 receipts. Snapshot join controls confirmed 68 Tier B queue IDs without evaluator records, 519 completed Tier C runs without terminal evaluation, 587 completed runs without a terminal grade, and 296 no-RUN jobs plus the separately identified interrupted orphan. All 587 stay ungraded; absence is not treated as a known exception.
- Tier A’s 80 summary identities are checked by ID only. No numeric Tier A metrics or raw movie/MRC payloads are read by the wrapper.

## Verification performed here

Commands, run from `/tmp/motioncorr-20261025-dc-consumer`:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile dc_snapshot_consumer.py tests/test_subprocess_controls.py
```

Result: **9 controls passed**. Fake child processes covered exit 0 + `EVALUATION_ERROR`, nonzero + `COMPLETE`, missing summary, malformed summary, schema-invalid non-null summary, valid exit 0 + `IN_PROGRESS`, valid exit 0 + `COMPLETE`, and valid exit 2 + `EVALUATION_ERROR`. The schema-invalid child exited 0; the consumer wrote a structured `SUMMARY_FORMAT_INVALID` receipt and returned 1 without baseline/join processing. A metadata-only queue/RUN join control reproduced the 1,700 / 1,403 / 68 / 519 / 587 counts and kept 297 no-RUN queue IDs split into one orphan plus 296 without a RUN receipt. These controls did not invoke the real adapter.

Independent-review follow-up: baseline comparison and queue join now run only when the non-null summary has the v2.2 format/state and actual list-valued `rows`, `pairs`, `regressions`, and `record_audit`. Invalid dictionaries remain in the structured receipt; they cannot raise during the subsequent join.

A separate local byte-only preflight verified all 736 copied record hashes, the manifest, 1,700 queue IDs, 1,403 RUN receipts, and 80 Tier A IDs. It did not invoke the adapter. The adapter source copy is SHA256 `c2f391822b880fba20b7a9571e4d5150fa3b365bd18afff2e44f90fef939ef45`, matching reviewed source `264be46c273fa514b1c1dc0cdf72302062a3791e`; tested tools head `070e3eab2af455f391395eacfcb8340a9abe2792`; independently reviewed final `4841c4aeed8e87ccde1b65a7c3725e44ea5ddeb9`.

Consumer SHA256 `5b5dfd32892bef042dd530dcadf7bc5f5ae9c6f63a65165206d05cbdc2471c6f`; subprocess controls SHA256 `18b7f956a888a5c8761ead530007f153f55dd89e3e4009b49c2d0669c01fc363`; corrected input manifest SHA256 `b0623a16dd68bcaaf1e86889ae170fdfb4f9d29fd2a5bd979a9026990d649971`.

## Parent run protocol

After fresh CPU64 admission, stage this owned directory plus the small copied manifests/queue/RUN inventory and `collected-snapshot/B`. Use one core and the parent’s 2 GiB bound. The adapter itself is one serial Python standard-library process; no wall time was measured here. The 43.4 MB of per-record JSON is the only campaign analysis input. The 43.4 MB tar is optional provenance and is hash-checked if supplied; it is never extracted by the consumer.

Run with a new output directory (do not reuse one):

```sh
python3 -B /tmp/motioncorr-20261025-dc-consumer/dc_snapshot_consumer.py \
  --eval-dir /tmp/motioncorr-20261025-dc-consumer/collected-snapshot \
  --evaluations /tmp/motioncorr-20261025-c1dc-harvest/snap/dc/evaluation-snapshots/B-pass3-20261022-2244/EVALUATIONS.json \
  --queue /tmp/motioncorr-20261025-c1dc-harvest/snap/dc/queue.json \
  --run-exits /tmp/motioncorr-20261025-c1dc-harvest/dc_run_exits.txt \
  --tier-a-summary /tmp/motioncorr-20261025-c1dc-harvest/snap/dc/A-summary.json \
  --archive /tmp/motioncorr-20261025-dc-consumer/COLLECTED-736.tar \
  --out /tmp/motioncorr-20261025-dc-consumer/runs/cpu64-dc-B-pass3-v22-01
```

If the CPU64 environment uses different staged paths, change only those input/output paths. Keep the same hashes and adapter. Review `runs/.../dc-join.json`, `adapter-output/tierB-v2.json`, `adapter-output/coverage.md`, and `SHA256SUMS`. No adapter run, native job, build, SSH launch, campaign restart, GPU/science/M3 qualification, GitHub write, or Notion write was performed here.
