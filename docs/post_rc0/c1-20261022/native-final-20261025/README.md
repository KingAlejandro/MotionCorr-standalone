# C1 native-final window (iteration i8), 25-26 October 2026

Tested production source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (unchanged); binaries are the existing e77a51a2 builds read in place plus the attribution builds `3d560a16` and `21093fe9` and the out-of-tree ingest-fault binary. Consolidated results: [../ACCEPTANCE_PACKET.md](../ACCEPTANCE_PACKET.md).

- `tools/`: qualification tooling (new or derived; derivation scripts and diffs retained: `make_v3_derived.py`, `c1_item12_mg.diff`, `c1_mg_publication.diff`; the stock QF/C1 drivers are not edited). The ingest-poison tooling and its host controls are `cuda_ingest_sticky_fault.cu`, `c1_ingest_build.sh`, `c1_ingest_poison.py`, `c1_ingest.sh`, `test_c1_ingest_poison.py` (`python3 tools/test_c1_ingest_poison.py`, 7 tests).
- `summary/`: stage table, per-row result JSONs, Xid snapshots, binary hashes.
- `c1-i8-evidence.tgz` + `c1-i8-collected-index.json`: 734 copied receipts/logs/results with sha256 and VM path; the index also lists the 4072 uncopied bulky files (MRC payloads, per-movie trees) with size and sha256.
- `SHA256SUMS` covers every other file in this directory.

Failed or superseded attempts are retained, not relabelled: `i8-mg-item12` (grader StopIteration at `d4poison`), `i8c-mg-item12-regrade` (digest normalisation), `i8-a13` (grader FAIL), `chain-i8b.sh` (unexecuted draft).
