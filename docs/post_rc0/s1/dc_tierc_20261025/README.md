# DC Tier C evaluation and four-arm comparison

Evaluated the 519 completed Tier C records (408 CPU / 111 CUDA) once, with the **unchanged** deployed `evaluate.py` (SHA-256 `dcc5ddb3...de14d`) as `evaluate.py C ROOT`. Tier C reads only `ROOT/runs` and `ROOT/src`, so no path amendment was needed and no separate evaluator review applies. No MotionCorr/native run was started. Source `3eee0a4b`; experiment source archive `src.tar` SHA-256 `b7152c0a...8d49c` verified.

- **Inventory** (`INVENTORY.json`, from the campaign host): 816 Tier C jobs = 408 CPU exit 0, 111 CUDA exit 0, 296 CUDA never run, 1 CUDA interrupted orphan (`C-e12963-03-p3-cuda-both`, no RUN.json; listed in `INVENTORY.json`, not staged, not graded). Per-file sizes/SHA-256 come from each RUN.json; the on-disk product set equals the pinned set for every record; 0 problems.
- **Evaluation**: cpu64, CPUs 32-47, `flock -n /tmp/motioncorr-dc-tierc-cpu32-47.lock`, `/usr/bin/python3` 3.12.3 + NumPy 1.26.4 (same as late68), one thread, 16 GiB address cap, 5 whole-config batches of at most 10.4 GB each (disk 94 GB free; staging deleted after each batch). Each batch: stream pinned files from 4GPUs (tar read on CPUs 104-107), verify every byte (all matched), evaluate once under a one-shot marker, clean up. All 5 child exits 0: 136+76+128+135+44 = **519 graded**, 0 evaluator errors. Receipts: `actual/`.
- **Comparison**: declared in `COMPARISON-PROTOCOL.md` before the Tier C output was read; results in `results/REPORT.md` and CSVs. The script imports the unchanged `tools/summarize.py` rule and refuses to run unless it reproduces the reviewed 804-record summary exactly (80 rows / 240 pairs / 965 regression entries: it does).
- **Controls**: `test_stage_verify.py` (1 accept + 5 rejects: flipped byte, extra file, missing file, symlink, wrong RUN exit) and `test_analyze.py` (known delta and sign, swapped-arm direction flip, limit crossing, Holm, Tier C convergence flip).

## Limits

- Tier C has no truth. It cannot show improvement or harm in accuracy; it shows change vs `none`, convergence and CPU/CUDA agreement.
- CUDA coverage is 28 of 102 configs (14 movies from 2 datasets, e10216 and e12963): the CPU/CUDA axis is not representative and its movie-level sign test overstates independence (per-family counts are in the report).
- The unchanged evaluator calls `compare_motioncorr.py --gate backend` without `--test-log`, so the strict gate exits non-zero for every pair by construction (0/28 etc.). Only the relative RMSE and trajectory numbers are used.
- Holm over the 60 Tier B cells cannot reach significance with 10 seeds (smallest exact sign p = 0.00195; x60 = 0.117). Cell labels are exploratory.
- Raw payloads (43.6 GB) were not copied off the campaign host; `RETRIEVAL.json` lists the durable small-file archive and the pins. No DC variant, default, gate, tolerance, ROI, scoring or regression-rule change; M3 stays with the maintainer. Old 371/878 and 804/965 snapshots are untouched.
