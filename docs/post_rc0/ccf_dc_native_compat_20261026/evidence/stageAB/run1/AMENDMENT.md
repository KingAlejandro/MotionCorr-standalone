# Amendment (2026-10-26, after the parent's mechanical check): `logs.sha256` entry for `chain.out`

The original `logs.sha256` (47 entries, written on the venue by `stageAB_chain.sh`) is retained unchanged. A mechanical re-check found 46 of 47 entries matching the retained files and one mismatch: `logs/chain.out`, manifest `7f0ff9f6e91b2a6e02be7a5110124b42f8de54c7e9297398e2f6e4d89698f27d`, retained file `ec94665f1b2791878dd7a429106db6a386a90c183386a9d57d98bb144f88fe24` (15905 bytes).

Cause, established from the retained script and file only (nothing was rerun): the chain's own stdout was redirected into `logs/chain.out`, and the script computed `sha256sum *` over `logs/` while that file was still open for appending. The manifest hash equals the SHA-256 of the first 15826 bytes of the retained `chain.out`, that is everything up to and including the line `316M ... /home/alex/mc-dcnative-ab-20261026`. The final 79 bytes were written after the hash was taken:

    47 /home/alex/mc-dcnative-ab-20261026/logs.sha256
    == done 2026-10-26T22:18:34Z

(the `wc -l` of the manifest and the closing `== done` line). All other 46 logged files, including both oracle JSON files and the three test logs, match their original entries. No result depends on `chain.out` hashes; the checks that matter are in the per-step `.rc`, `.check`, `.witness` files and the JSON.

So the original manifest did not bind a closed `chain.out`; it is not claimed as "all 47 verified". `SHA256SUMS.v2` binds every current file under `run1/` except itself and this amendment (fully closed files, one entry per file, `chain.out` at its full 15905-byte hash). The Stage C driver avoids this pattern: it never hashes a file that a live process is still writing, and verifies its manifest by re-hashing after writing it.

## Parent's independent confirmation and the checker scar (recorded without widening any claim)

- The parent's mechanical check found the same single mismatch (1 of 47, `chain.out` only) and independently proved the prefix: the original manifest hash `7f0ff9f6...` equals the SHA-256 of the first 15826 bytes of the current 15905-byte `chain.out`, and the remaining 79 bytes are exactly `47 /home/alex/mc-dcnative-ab-20261026/logs.sha256\n== done 2026-10-26T22:18:34Z\n`. The cause is therefore established, not assumed: the manifest was written before the script's own `wc` and closing `done` prints. The producer, oracle and tests were not rerun for this diagnosis.
- The parent also parsed Stage A and the oracle JSON on its own: pure 28 tests with 17 skipped (the native class, by design); exp 28 with 0 skipped; iso 28 with 0 skipped; both oracle JSON files have every gate non-empty and passing with no failures; per-path eligible totals reproduce the report table. The 46 other manifest entries (including all logs and JSON) match, so no scientific array or result hash differs.
- Checker scar, retained as is: the first checker (`stageAB_check.py unittest`) reported `test_n_score_reproduces_all_16_retained_rows` as "not ok" in its `A-*.check` outputs because that test has a docstring and `unittest -v` prints its result on the following line; the one-line regex missed it. The `A-*.check` files are kept exactly as produced; `stageAB_reparse.py` (offline, run afterwards) and the parent's own parse show the test `ok`. The pure run's 17 skips are the native class and are not counted as native passes.
- The original `logs.sha256` is not edited. `SHA256SUMS.v2` is additive and binds only the current closed files.
