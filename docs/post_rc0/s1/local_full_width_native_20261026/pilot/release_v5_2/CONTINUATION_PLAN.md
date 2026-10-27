# Continuation plan (release v5.2): frozen before any code or outcome

Context: native pilot r1 stopped after 1 of 16 launches at the noisy pre-ON comparator (`STOP COMPARATOR`). Saved-file diagnosis (sealed, `native_r1/DIAGNOSIS_r1.md`): the gate passed the durable baseline copy as comparator root A while the baseline files embed the original
scratch root; with root A = the original scratch root the unchanged pinned comparator reports IDENTICAL on the saved trees. The r1 STOP is not promoted or waived. This plan prepares a bounded continuation; it is NOT a native run and not a release. The parent commissions one Opus delta review
and writes any new `PARENT_RELEASE.json`.

## What may change (metadata and anchors only)
- Baseline path anchor: `baseline_root` becomes the canonical original scratch root `/tmp/motioncorr-b2-factorial-20261026/evidence/runs`. The 152 pinned baseline bytes are unchanged; they are re-verified against the exact durable pins (the original scratch tree and the durable tree are
  both identical to the pins) before use, and each baseline `RUN.json` `--o` value must equal the audited `<baseline_dir>/output` path (below).
- New files only: `pair_decision_v5_2.py` (modified copy of `pair_decision_v5.py`), `driver_v5_2.py` (modified copy of `driver_v5_1.py`), `ADMISSION_V5_2.json`, `COMMANDS_V5_2.json` (byte copy of `COMMANDS_V5.json`), tests and a reviewable diff of each copy. v5, v5.1, the r1 release, the STOP,
  the OFF run and every sealed archive stay untouched. No change to the comparator or its normalisation, any numerical comparison, tolerance, ROI, gauge, weight, source, binary, commands, build, tool pins or the science criteria (P1/P2, the 8 endpoints, .20/.40/.80 A).

## Root audit (new, loud failure instead of a silent DIFFERENT)
Before the pinned comparator runs on a baseline, `pre_ON_gate`/`admit_pair` require: the pinned baseline `RUN.json` argv has exactly one `--o`; that value equals `str(<baseline_dir>/output)` resolved; its last two path components before `output` are `<case>/UP_only`; and
`corrected_micrographs.star` embeds that root at least once and embeds no other `/.../output` root. Otherwise `ROOT_AUDIT`. The comparator itself is invoked exactly as before.

## Controlled reuse of the one produced OFF (no producer rerun)
Only the frozen first OFF (`noisy/OFF`) may be reused, once. The admission carries a `continuation` block: RUN.json sha256 `ab9ae3736b667911fee1e735dc67ea2433067e5442e3536503f8422ab566951a` (verified against the live file before indexing), the canonical sha256 of the full inventory of `evidence/noisy/OFF`
(including inputs), the r1 ledger/STOP/release/release-index hashes, and the source/binary/archive/build-receipt pins. The driver refuses: a missing or changed first OFF (any byte), any other existing row (another case, an existing ON, a stray file in `evidence_root`), a reuse record naming any other case/arm,
a decision directory that is not fresh, a plan whose count plus the reused OFF is not exactly the budget (15 + 1 = 16). The new ledger starts with an explicit `REUSED` event (launches before 1, remaining 15). Then: guard, `pre_ON_gate(noisy)` re-evaluated from the saved outputs against the correct root (no producer),
noisy ON, then the 7 remaining cases OFF, gate, ON. 15 launches maximum; the global ceiling stays 16 including the old OFF. Fresh exclusive directories and no retry for every new launch; the old `RUN.json` and raw files are never touched. Launch, sampling, lease-ownership and cleanup code is copied unchanged from v5.1 (the diff shows only the continuation, reuse and audit parts).
No generic resume mechanism and no other reuse case.

## Release binding
A new `PARENT_RELEASE.json` (parent only, after review) must name the sha256 of `driver_v5_2.py`, `pair_decision_v5_2.py`, `ADMISSION_V5_2.json`, `COMMANDS_V5_2.json` and the reused first OFF `RUN.json`; the driver checks these.

## Tests and receipts (fixed before running; fake child and replay of the existing single OFF only; no native, no fit, no new truth read)
- Root audit: positive; baseline `RUN.json` `--o` of another case (basename); one digit changed in the path (numeric); missing `--o`; a second `--o`; an extra embedded root in `corrected_micrographs.star`; the durable-style path used as baseline root over original-root files (the r1 failure mode) now gives `ROOT_AUDIT`; a copy-only control showing correct normalisation still detects a changed MRC payload.
- Reuse: happy path with a fake child (15 launches, first ledger event `REUSED`, noisy/OFF untouched and never launched, then the decision with crafted scores); refusals for each case listed above plus a changed first OFF byte, an altered `RUN.json`, wrong admission reuse hash, release without or with a wrong reused hash, reuse naming `affine/OFF`, an existing ON, a stray file, a non-fresh decision directory, a later-case OFF compat failure (STOP before ON), the old STOP/ledger unchanged after the run.
- Guard-removal controls for the new guards, shadowing declared. v5/v5.1 suites still pass.
- Real-path checks on cpu64, no producer: hash audit of both baseline trees against the 152 pins; root audit of all 8 real baselines; the unchanged comparator on the real saved noisy OFF with the new root in a scratch decision directory (positive control); `driver_v5_2` dry run under the lane (validation only).
Every run, failures included, is kept. No criterion is relaxed after results. Not claimed: any ON result, P1/P2, neutrality, harm, GPU.
