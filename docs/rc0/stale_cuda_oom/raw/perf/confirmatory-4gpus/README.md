# Confirmatory timing campaign, tutG and e10216L (#228, D14): evidence

Single attended campaign on 4GPUs GPU3 (`GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`), 2026-10-18 21:11:24–22:43:19Z. Operator: coordinator T3 9cf60de2, after R-D11 round 9 GO-ATTENDED. The design is frozen in `../confirmatory-draft/` (source `0b11f6a8`).

**Result: tutG PASS and e10216L PASS** (D14: no resolved slowdown, and the upper 95% bound of median(fix − main) ≤ +0.5% of the median main wall).

| Workload | Pairs | Median d | CI as % of main wall |
|---|---|---|---|
| tutG | 256 (128 AB / 128 BA) | −5.27 ms | −0.313 … +0.110 % |
| e10216L | 176 (88 AB / 88 BA) | −16.85 ms | −0.552 … +0.114 % |

All four windows completed cleanly: worker rc 0, not killed, no leftovers. Locks were released after 1448.7, 1303.2, 1435.5 and 1310.1 s of the 2700 s budget. There were no operator interventions, and no WARN, OVERRUN or ORPHAN events.

## Contents
- `operator-prestart.txt`: frozen hashes, clean tree at `0b11f6a8`, GPU state and start time.
- `operator-watch.sh`, `operator-watch.log`: the operator's watch.
- `campaign.out`: launcher output.
- `manifest.json`: sha256 `ea4c9dd6…`, identical to `../confirmatory-draft/manifest.json`.
- `<workload>/window<i>/`: `holder.json` (lock-holder record), `complete.json`, `runs.jsonl` (raw ledger), `nvidia-smi.csv`, `mpstat.txt.gz`, `worker.log`, `logs/` (per-run payload output).
- `tutG-result.json`, `e10216L-result.json`: the campaign's `combine` output.
- `recombine/`: an independent re-run of `combine` from these committed ledgers and the frozen manifest with the frozen driver (`../confirmatory-draft/confirm_pairs.py`, sha256 `86f2db90…`). It is identical to the campaign result files.

## Copy and storage
- Copied from `/mnt/clathrin/alex-motioncorr-rc0/W-D11/confirm4/` with `ssh 4GPUs 'tar czf - …' | tar xzf -`. All 967 files were verified byte-identical against `SHA256SUMS.original`, which was computed on 4GPUs.
- Nothing was excluded. The run left no product files (scratch was removed).
- The four `mpstat.txt` samplers (1.6–1.8 MB each) are stored gzip-compressed, losslessly. Their original sha256s are listed in `COMPRESSED.txt` (`gunzip -c <file> | sha256sum`).
- Total size here: about 4.6 MB.
