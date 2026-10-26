# Native pilot r2 (cpu64, CPU only): continuation completed, driver rc 0, no STOP

**All 15 continuation launches ran and exited 0; `DECIDED` at 23:32:19Z; global launches 16 (the old noisy OFF + 15 new).** This is the raw terminal record only. An independent result review (not the author) is still required;
nothing here is an acceptance, adoption or full100 claim.

## What ran
- Driver `driver_v5_2.py` (`278f781d...`) with module `bc7ab56c...`, admission `7a431e8d...`, commands `2bd36fac...`, parent release `b30c63ab...`, release index `4d67fa2b...`, binary `bb92e061...`, archive `87349cb6...`; run once under the pinned `lane.py` (8 overlapping leases + bench lock held, CPUs 32-47, OMP 2 / BLAS 1),
  no TTY, `setsid nohup`, stdout/stderr in `receipts/native-run-r2/`. Launch 23:31:37Z, terminal 23:32:19Z; driver rc 0, lane rc 0. The release files, the 7 critical files, the binary/archive/receipt and the existing `noisy/OFF` inventory matched before launch.
- **Mixed provenance:** the first noisy OFF came from the r1 run under `driver_v5_1.py` (reused unchanged, never relaunched; the r1 ledger, STOP, release and all its files are unchanged); the 15 new launches ran under `driver_v5_2.py`. Launch, sampling, lease and cleanup code is identical between the two.
- **Parent setup record:** the parent's first release-writer attempt referenced the existing r1 directory (a literal copy slip); the exclusive `mkdir` refused before any write and r1 was unchanged; the corrected writer used the approved single `decision-native-r2` (`PARENT_SETUP_ATTEMPTS.md`). No producer or reuse-gate retry occurred.
- Ledger: `REUSED noisy/OFF`, then `launching`/`finished` for noisy ON, then each other case OFF and ON, 15 launches, all `exit 0`, none timed out, then `DECIDED`. No STOP file. 8 pre-ON records (noisy re-evaluated from the saved OFF, 7 new OFF runs), 8 pair records, 17 guard receipts with lane-owned leases.

## Frozen decision (unchanged driver rules)
`prediction SUPPORTED`, `acceptance NOT_ACCEPTED_NO_AUTOMATIC_ACCEPTANCE`.
- **P1 holds:** affine, pedestal, zero, integer and fractional are PASS on runtime and actual STAR, OFF and ON, under .20/.40/.80 A.
- **P2 holds:** noisy ON is strictly lower than OFF in rms, p95 and max for both fields: runtime 1.6454 -> 1.0954, 3.3373 -> 2.2402, 7.2840 -> 4.4692; STAR 1.6454 -> 1.0954, 3.3373 -> 2.2403, 7.2838 -> 4.4693 (A).
- **Noisy raw gate remains FAIL** on both runtime and STAR (ON values exceed .20/.40/.80); P2 improvement does not change it.
- Every-increase list: empty (no ON > OFF on any case, field or metric). flat and repeated: UNIDENTIFIABLE, raw distances identical OFF/ON (flat rms 2.1044, repeated rms 9.0126 A).

## Separate observations (records, not gates)
- `local_enabled`: True on noisy, affine, pedestal (3x3), False on the five 1x1 cases, both arms. Witness lines: 9 on the three 3x3 ON runs, 0 elsewhere.
- Global trajectory: float64-bit equal and the serialised global STAR block equal for OFF vs ON in all 8 cases; the five global-only pairs have identical runtime, case STAR and whole-product comparator output (7 gated products each).
- Convergence/acceptance (`pair_summary.txt`): global converged in all 16 runs; patch acceptance noisy 8 of 9 patches (one not converged) in both OFF and ON, affine and pedestal 9 of 9 in both arms.
- Resource sampling: `OBSERVED` in all 16 runs, 7 samples each, max Threads 2 and tasks 2, mask `32-47` as the kernel reported (receipt only; `--j 2` was not treated as proof). Wall about 0.13 s per run.

## Not established
This is a CPU, 8-case, tiny-fixture pilot. It does not establish full-field/real-movie accuracy, byte neutrality beyond the compared products, harm controls, N5/9/13/20, GPU behaviour, or any default/adoption change. The noisy case still fails the raw gate in both arms. No full100, no merge, no evidence comment, no watcher.
Raw products, receipts and the parent's preflight are sealed in `~/Documents/MotionCorr-evidence/20261026/Native-local-full-width-native-r2-DONE/` (`COPY_INDEX.tsv`); this directory holds the compact receipts (`receipts/`, per-run RUN.json/runtime.json/stdout.log/log) and `remote_hashes_after_terminal.txt`.
