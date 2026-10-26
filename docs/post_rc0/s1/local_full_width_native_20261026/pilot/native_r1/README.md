# Native pilot r1 (cpu64, CPU only): STOP after 1 of 16 launches

**Result: 1 producer ran (noisy OFF, exit 0, 0.13 s wall). The pre-ON gate then stopped on `COMPARATOR`; noisy ON and the other 14 launches never ran. No rerun, per no-retry. P1/P2 are not computable (no ON run).
This is an infrastructure/gate STOP, not a scientific FAIL.**

## What ran
- Driver `driver_v5_1.py` (sha256 `c4ec6752...`) with `--execute` under the pinned `lane.py` (all 8 overlapping leases plus the bench lock held, CPUs 32-47), no TTY, `setsid nohup`. Launch 23:02:36Z, terminal 23:02:41Z,
  driver rc 1, lane rc 0. Release files, module `0826d64a...`, admission `dae759f7...`, commands `2bd36fac...`, binary `bb92e061...`, source archive `87349cb6...`, build receipt `da0681be...` and the two review reports all matched before launch.
- Ledger: `launching noisy/OFF`, `finished exit 0, timed_out false`, `STOP COMPARATOR (launches 1)`. Guard receipt for noisy/OFF: leases owned by the lane pid, foreign busy cores 0.0, free disk 86 GB, combined scratch 6.44 GB.
- OFF child resource samples: `OBSERVED`, 7 samples, max Threads 2 and tasks 2, mask `32-47` as the kernel reported it, 3 processes seen (receipt only, no gate).
- Gate steps that passed before the stop: OFF admission (receipt, argv, env, inventory, runtime, witness 0), baseline inventory/bytes (152 pins), **OFF `runtime.json` and `noisy.star` byte-identical to the retained baseline**, OFF manipulation coverage. Failed step: the pinned whole-tree comparator.

## The comparator result
`compare_products.py` (rc 1): 10 files, 7 gated, 2 differing: `corrected_micrographs.star` (689 B vs 719 B) and `noisy_shifts.eps` (57383 B vs 57398 B). Equal: `noisy.mrc` pixels and header (label block timestamp differs, not gated), `noisy.star`, the three accumulated-motion EPS.

## Post-hoc diagnosis (read-only, does not change the frozen STOP; `POSTHOC_DIAGNOSTIC.txt`)
The retained baseline files embed the original production root `/tmp/motioncorr-b2-factorial-20261026/evidence/runs/noisy/UP_only/output`. The gate passed the durable copy path
`/home/ubuntu/motioncorr-evidence/.../UP_only/output` as the comparator's root A, which does not occur in those files, so the comparator's root normalisation did not apply to the baseline side. After replacing each file's own embedded root with a
placeholder, both files are equal. So the two differences are the embedded output path (length differences 30 B and 15 B match the two roots), not a product difference. This is a defect in how release v5 invoked the pinned comparator (the baseline
copy used as root A); its tests used a synthetic baseline whose embedded root was its own path, so they could not show it, and neither review nor the dry run (no OFF run existed) exercised it. The comparator, binary, source and data pins are not implicated.

## State and what is needed
15 of 16 launches are unused but no further launch is allowed by this run. Continuing needs a parent disposition: a corrected, reviewed release and a fresh decision directory and budget decision. One fact that bears on that choice: the task copy of the baseline at
`/tmp/motioncorr-b2-factorial-20261026/evidence/runs/<case>/UP_only` (same 152 pinned bytes) sits at the very root the files embed. Nothing was changed or rerun here.

## Files
`receipts/` holds the decision directory (release files, ledger, STOP, guard, pre_on comparator command/JSON), the run wrapper and logs, and the OFF `RUN.json`, `runtime.json`, `stdout.log`, `noisy.log`. `remote_hashes_after_terminal.txt` lists hashes of every file under evidence/decision/run dirs and the frozen pins.
Raw products, the binary, the source archive and the parent's preflight files are sealed in `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-native-r1-STOP/` (`COPY_INDEX.tsv`).
Not established: any ON result, any P1/P2 metric, neutrality, harm, N5/9/13/20, GPU. No full100, adoption, merge or default change. No evidence comment or CI watcher.
