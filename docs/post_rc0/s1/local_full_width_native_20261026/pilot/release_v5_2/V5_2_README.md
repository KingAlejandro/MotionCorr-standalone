# Release v5.2 continuation: package index (HELD; not released; one independent delta review requested)

Prepares a bounded continuation of the native pilot after the r1 STOP. **Nothing native ran.** Criteria were frozen first in `CONTINUATION_PLAN.md` (sha256 `dfaf3dbc8bdb571a...`, commit 5eed29de). The r1 STOP is unchanged and not waived;
`release_v5/`, `driver_v5_1.py`, the r1 release, the STOP, the produced noisy OFF and all sealed archives are untouched. Source `634e4b48`, CMake `5bcfa987`, binary `bb92e061...`, archive `87349cb6...`, commands `2bd36fac...`, the comparator and the science criteria are unchanged.

## Files (all new; each copy has a reviewable diff in `V5_2_DELTA_FOR_REVIEW/`)
| file | sha256 |
|---|---|
| `pair_decision_v5_2.py` (modified copy of `pair_decision_v5.py`, 105 diff lines) | `bc7ab56c3b1acd700a96954d00a37d2e5af65e3e1b6e4bd2200cbfed100fcf74` |
| `driver_v5_2.py` (modified copy of `driver_v5_1.py`, continuation/reuse parts only) | `278f781d7ae1541db7df453315dd1bbb19360f5c01a31227b8d4de8d94a5b767` |
| `ADMISSION_V5_2.json` (v5 admission with the original-scratch `baseline_root` and a `continuation` block) | `7a431e8db3c2628fc99dc6f38618f8e354653d1c636be5e85ebaec6e2d02c97d` |
| `COMMANDS_V5_2.json` (byte copy of `COMMANDS_V5.json`) | `2bd36face2fed6f6a92398eb0402a63e6c6ea3624832e45c823f289a061b8081` |
| `REUSED_OFF_INDEX.json` (the produced noisy OFF: RUN.json `ab9ae373...`, all 15 file hashes, r1 ledger/STOP/release hashes) | `e85fe53c302fb329811ad5239a52791d3f08ac16428295390214232f2f587b15` |
| `tests/test_continuation_v5_2.py`, `tests/mutation_controls_v5_2.py` | `7f208de142f0c532...`, `c5926c7251e4f3ec...` |

## What changed
- **Baseline root:** `baseline_root = /tmp/motioncorr-b2-factorial-20261026/evidence/runs` (the root the baseline files embed). Both baseline trees were re-hashed on cpu64 against the exact durable pins: 152/152 equal in each, no symlinks (`receipts_cpu64_v5_2/baseline_*.txt`).
- **ROOT_AUDIT (new, loud failure):** before the unchanged comparator runs, the pinned baseline `RUN.json` must have exactly one `--o` equal to `<baseline_dir>/output`, and `corrected_micrographs.star` must embed exactly that root. The r1 failure mode (a durable path over original-root files) now stops with `ROOT_AUDIT`.
  No comparison, tolerance, ROI, gauge or weight logic changed.
- **Controlled reuse:** only the frozen first OFF (`noisy/OFF`), once. The driver refuses a missing or changed first OFF (any byte, extra file or changed receipt), any other existing row (another case, an ON, a stray file), a reuse record for any other case/arm,
  changed r1 ledger/STOP, a non-fresh decision directory, and a plan whose size plus the reused OFF is not exactly 16. The new ledger starts with `REUSED` (before 1, remaining 15, ceiling 16); then guard, `pre_ON_gate(noisy)` re-evaluated from the saved outputs (no producer), noisy ON,
  then the 7 remaining cases OFF/gate/ON: 15 launches at most, 16 globally. Fresh exclusive directories and no retry for every new launch. Launch, sampling, lease, cleanup and staging code is identical to v5.1.
- **Release binding:** a new `PARENT_RELEASE.json` must name `driver_v5_2.py`, `pair_decision_v5_2.py`, `ADMISSION_V5_2.json`, `COMMANDS_V5_2.json` and the reused OFF `RUN.json` hash (checked by the driver); the parent writes it only after review.

## Receipts and tests
- Fake child, macOS: `tests/test_continuation_v5_2.py` 59/59 (run3 and final; run2 had 2 test defects, kept in `logs/ATTEMPTS_v5_2.md`): root-audit positives and negatives (basename, last character, numeric, missing and second `--o`, extra and different embedded root, the r1 failure mode, a changed MRC payload still detected),
  happy path (15 launches, first event `REUSED`, noisy OFF never relaunched and unchanged, r1 ledger/STOP unchanged, new pre-ON record), 20 refusal cases each with no producer launched, a later-case OFF compat stop before its ON, a failing noisy ON.
  Guard-removal controls (`logs/mutation-v52-run2.log`): 15 killed, 1 shadowed as declared (the path-shape check is implied by how the baseline path is built). Regression: v5 suite 121/121, v5.1 suite 38/38 (4 Linux-only skipped, already passed on cpu64 earlier).
- cpu64, under the lane, no producer (`receipts_cpu64_v5_2/`): `driver_v5_2` dry run rc 0 (all 152 baseline bytes, root audit of all 8 real baselines, the frozen first-OFF inventory, guard; 15 launches planned, noisy ON first, nothing created); the unchanged comparator through `pre_ON_gate` on the saved noisy OFF with the new root: **PASS, IDENTICAL, 7 gated, 0 differing**
  (`proof_pre_on.json`, `diag-proof-r2/`). After the checks the whole `evidence/` hash, the r1 ledger and the STOP are unchanged and no owned process or flock remains.
- Remaining budget: 1 of 16 used; 15 remain (noisy ON and the 7 other cases OFF/ON). No new 16.

## Not established
No ON result, no P1/P2, no neutrality, harm, N5/9/13/20 or GPU. The audit proves the baseline root, not that the real binary produces identical products for other cases. No release exists; the parent commissions one Opus delta review (this continuation only) and writes any new `PARENT_RELEASE.json`.
No merge, default change, adoption or full100; no evidence comment or watcher.
