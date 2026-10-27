# Local read-only audit bundle: native local full-width weight pilot (cpu64, CPU only)

For the independent result audit. **Read-only**; every file is bound in `MANIFEST.json` (bytes + sha256, written after all files closed; `MANIFEST.sha256` is the hash of the manifest).
Contents: `truth/` (the 8 truth field NPYs and `MANIFEST.json` 9697c203..., equal to the fixture pins), `runs/<case>/<arm>/` (RUN.json, runtime.json, case STAR, case log, stdout.log, the staged input STAR, and `products_inventory.json` with bytes/sha256 of EVERY file in that
run directory including the products that are not copied), `decision_r2/` and `native_run_r2/` (the r2 DECISION, ledger, release, release index, parent review reports, guard receipts, pre-ON and pair records with comparator JSONs, wrapper/driver/lane logs), `decision_r1/` and `native_run_r1/`
(the r1 STOP records), `diagnosis_r1_comparator/`, `pins/` (admissions, commands, build receipt, reused-OFF index, baseline inventories, final remote verification, frozen hashes), `AUDIT_TABLES.json/.md` and `audit_tables.py`.
**Excluded:** all MRC pixel payloads (`*.mrc`, `*.mrcs`), the EPS/PDF products and the large baseline trees; they stay on cpu64 and in the durable run archive and are bound by hash in `products_inventory.json`.
The first OFF (noisy/OFF, produced in r1 under driver v5.1) is unchanged; the r1 STOP stands as a STOP (the comparator STOP is not a retrospective PASS). The 16 runs are real binary runs; the "synthetic" wording in the retained DECISION scope refers to the driver tests.
Not claimed: noise-origin causation, p-values or independent-seed statements (noisy is one exposed realization), N5/9/13/20 or harm re-qualification, full100, GPU, adoption.
