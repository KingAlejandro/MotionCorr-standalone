# DC late-68 one-shot evaluator packet

## Frozen cohort and lineage

`late68-ids.txt` is the exact join of frozen queue membership (`tier=B`, `backend=cpu`), `dc_run_exits.txt` exit 0, and absence from the frozen `EVALUATIONS.json` ID/hash map. There are 68 records: 16 none, 16 global, 17 local, 17 both, and 2 plain. See `JOIN-MANIFEST.json` for source file hashes. The 2 plain rows are preserved as `CONTROL_ONLY`; the evaluator still reads their receipt before the branch.

`COLLECTION-MANIFEST.json` has exactly **411 unique stage paths**: 68 unchanged RUN records, 68 per-ID receipt copies, 66 × {runtime, movie STAR, movie log, movie MRC}, 2 truth caches, 7 checker/generator closure files, the exact deployed `evaluate.py`, and `SOURCE_SHA`. All 411 have non-null byte counts and expected SHA-256. The two truth caches and 66 MRCs have expected source hashes but their full payloads remain unverified until the parent's chunked collection pass. Stage total is 5,682,996,238 bytes (5.29 GiB). Parent collection must stop on any path, size, hash, duplicate, regular-file, or manifest mismatch.

`CURRENT-EVAL-GUARD.json` is a separate **parent-local metadata sidecar**, not a VM collection member. Its pin confirms 345 current `eval/B` files and zero of these 68 IDs present. The retained 736-record evaluation snapshot remains at its distinct frozen `evaluation-snapshots/B-pass3-20261022-2244/eval/B` path; neither it nor the current 345 records is staged or consumed by this run.

## Evaluator amendment

`source/evaluate-original.py` is the deployed 13,344-byte evaluator (SHA-256 `dcc5ddb3d52d14652f11214fb2a9339fb5fb63637d87dc0c82ee3a4c2d0de14d`). `source/evaluate-late68-v1.py` (SHA-256 `66903f90da17c72d785f1c18ff6149b5cf4cc4ad3ed940c39027c02422e114b7`) differs in exactly three path substitutions, shown in `evaluate-late68-v1.diff`: the two TRUTH cache paths now resolve under `ROOT/truth/` while retaining their original exact full SHA requirements; recipe receipts resolve under `ROOT/fixture-receipts/<record-id>/RECEIPT.json`. Numerical code, checker imports, thresholds, status logic, JSON serialization, output naming, and existing-output skip behavior are unchanged. `RUN.json` remains byte-identical; its former `cwd` remains recorded provenance and is not asserted as the staged host path.

The deployed import closure is pinned in `SOURCE-CLOSURE.json`: `check_realistic_motion.py`, `check_realistic_image.py`, `motion_field.py`, `generate_realistic_motion.py`, `check_motion_diagnostics.py`, `generate_motion_diagnostics.py`, and `generate_known_motion_fixture.py`. Parent source-closure metadata supplied exact hashes for all seven; the collection manifest pins all seven. The deployed `SOURCE_SHA` file is staged and checked too.

## One-shot CPU64 invocation

Parent streams the 411 manifest entries into a **new empty ROOT** and verifies the large members with chunked SHA-256 before invoking the runner. The runner rechecks the full staged tree with bounded 1 MiB reads, rejects links, extra/missing/duplicate paths, source/hash/size drift, any evaluation file already in `eval/B`, any run IDs beyond the exact 68, and any staged record whose identity/source/exit differs. It checks the separate current-evaluation sidecar and never imports the 736 or 345 evaluations.

After parent review and a fresh admission, invoke the runner once on CPU64 under `/home/alex/.mc-venv/bin/python3`, with admission JSON fields: `scope=dc-late68-evaluator-only`, fresh `captured_utc`, `cpu_core=62`, `cpu_lock_held=true`, `busy_check_clear=true`, `active_evaluator_processes=0`, `available_ram_bytes>=8589934592`, `ram_cap_bytes=8589934592`, `scratch_budget_bytes>=12884901888`, and `python_executable` equal to the runner interpreter. The runner binds CPU 62, sets BLAS/OpenMP thread counts to 1, caps evaluator address space at 8 GiB and each newly written file at 16 MiB, and invokes exactly one child: `evaluate-late68-v1.py B ROOT`. It writes `LATE68-RESULT.json` with the child exit distinct from all 68 per-record states. The one-shot marker prevents retry in that namespace. No output MRC is created.

The result records evaluation states only; it assigns no campaign/DC grade. Do not run v2.2 summary now. Parent must review lineage before combining these 68 new records with the separate frozen 736 snapshot. The current 345-file `eval/B` remains untouched. Existing 371 and 878 regression snapshots, gates, thresholds, and cohorts remain unchanged.

## Harmless controls and limits

`tests/test_path_amendment.py` checks exact evaluator hashes, the three-path-only amendment, compilation, and a synthetic plain-record subprocess that proves the receipt is resolved through the staged ID path while the old `cwd` is absent. It imports no real checker implementation and reads no scientific arrays. Local controls do not invoke the one-shot runner or the real 68 records.

Actual VM presence, hashes of staged large payloads, fresh resource admission, locks, RAM, and scratch must be rechecked by parent at run time. No native job, evaluator run, MRC payload read, campaign continuation, GPU/science/M3 claim, or new summary has been performed in this task.
