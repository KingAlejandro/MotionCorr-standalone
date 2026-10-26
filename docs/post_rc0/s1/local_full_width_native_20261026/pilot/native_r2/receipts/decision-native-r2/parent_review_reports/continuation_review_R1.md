# v5.2 continuation delta review r1 (Opus, read-only)

**Verdict: CLEAR, conditional, for the 15 remaining launches only.** No BLOCK, no MATERIAL finding.
Worktree HEAD `0e83d9c702ffdc0a871e443a4726723aa10dabe1` (PR 290 draft). No producer, ON, MotionCorr, build, image interpretation, PARENT_RELEASE, branch change or publication.

## Assessment
- **Root switch is a caller-argument repair, not a gate change.** The pinned comparator (`53449d2d...`) normalises the root string it is given. With the durable root (r1), the original scratch root embedded in the baseline STAR/EPS is never normalised, so no OFF could pass however good its products were: the r1 gate could not pass for any input. `pair_decision_v5_to_v5_2.diff` changes only anchors, schema strings, the `continuation` admission field and the new `_root_audit` (`pair_decision_v5_2.py:288-304`). Comparator invocation, `_read_comparison` (it still requires `root_a == resolve(a_root)`), tolerances, ROI, gauge and decision rules are unchanged. The audit makes the precondition explicit and fails loudly (ROOT_AUDIT), and the r1 failure mode now fails before any ledger is written (probe D: `BASELINE: ROOT_AUDIT`).
- **The r1 STOP stays a STOP.** r1 ledger/STOP/release/index hashes are checked before the run (`driver_v5_2.py:449-452`) and ledger/STOP again afterwards (`:517-524`). The new pre-ON record is written to a fresh decision directory.
- **Controlled reuse is one case, once, and the budget is enforced by structure.** Plan = noisy ON + 7x(OFF, ON) = 15; `15 + launches_before 1 == 16 == budget` (`:462-463`). `verify_reuse` requires `evidence_root` to contain only `noisy/OFF`, so once any new launch (even a failed one) creates `noisy/ON`, every later continuation is refused in any decision directory (probes F1-F3). Global launches therefore cannot exceed 16.
- **The reused OFF is usable downstream with no dead end.** The r1 `RUN.json` has the same receipt schema/fields as a v5.2 launch would write (launch code is outside the diff) and carries no driver hash, so `admit_pair`/`_score_arm` see an ordinary OFF. The author's real-path `pre_ON_gate` PASS (IDENTICAL, 7 gated, 0 differing) exercised `_admit(OFF)` on the actual receipt.
- **Delta completeness:** regenerated `diff -u` of `pair_decision_v5.py`->`v5_2` and `driver_v5_1.py`->`v5_2` equals the committed delta files byte for byte (headers excluded). `git diff c9e17a95..HEAD` touches only `native_r1/` (new) and `release_v5_2/` (new): no src/tests/CMake change, and `release_v5/` is untouched.
- **License:** no third-party content added.

## Verified (this review)
| check | result |
|---|---|
| `SHA256SUMS_v5_2` (51 entries) | all OK |
| plan at commit 5eed29de | `dfaf3dbc...` equals file |
| package hashes (driver `278f781d...`, module `bc7ab56c...`, admission `7a431e8d...`, commands `2bd36fac...` byte-identical to `COMMANDS_V5.json`, index `e85fe53c...`) | match brief |
| cpu64 deployed copies (`/tmp/motioncorr-lfw-v5-20261026/pilot_v5_2/release_v5_2`) | 6/6 identical |
| cpu64 live `evidence/` | exactly `noisy/OFF`, 15 files, each equal to the admission inventory; canonical inventory `601f8d51...` recomputed locally |
| cpu64 r1 ledger/STOP/release/index | equal to the admission hashes |
| 8 baseline `RUN.json --o` (original root) | each `= <root>/<case>/UP_only/output`; `/tmp` path is real (no symlink) |
| scratch headroom (dry-run guard) | 6.44 GB of 26.8 GB cap; one OFF publishes ~0.37 MB |
| author suite `test_continuation_v5_2.py` rerun | 59/59 (`results/test-v52-rerun.log`) |
| reviewer probes run2 | 10/10 (`results/probes-run2.log`) |

Probes (fake child): A reuse-gate comparator failure -> ledger `REUSED, STOP(launches 0)`, evidence unchanged; B see condition 1; C see condition 2; D durable root through the whole driver -> `BASELINE/ROOT_AUDIT`, no ledger; E see limit 3; F failed noisy ON then fresh dir -> `REUSE` refused, one launch on record.

## Conditions for the parent release (no code change required)
1. **The continuation has no single-use binding at driver level.** After a 0-launch STOP at the reuse gate, a NEW decision directory plus a NEW `PARENT_RELEASE.json` re-runs the gate and continues (probe B: accepted, 16 global). This spends no budget and the gate is deterministic on hash-frozen inputs, but it is a second gate attempt. The parent release index should name the one decision directory, and any reuse-gate STOP should be treated as terminal without a new review.
2. **`verify_reuse_records_unchanged` runs after `decide_pilot` has written `DECISION.json`** (`driver_v5_2.py:505-506`). If it fails, `DECISION.json` remains next to a ledger that ends in STOP (probe C). The terminal ledger event is authoritative.
3. Fresh resource admission, live prior-scratch measurement and the release index remain the parent's responsibility (v5.1 R2 limits, unchanged). Launch non-TTY via `setsid` (known N1 SIGHUP).

## Remaining limits (not blocking)
1. Mixed provenance: the DECISION will combine one OFF written by driver v5.1 under the r1 release with 15 runs written by v5.2. The launch code is identical, but the index should record both.
2. r1 records and evidence live in cpu64 `/tmp`; if `/tmp` is cleaned, the driver stops with REUSE (fails closed).
3. The reuse inventory covers files only, so an added empty directory inside `noisy/OFF` is not detected (probe E). No bytes change.
4. `_root_audit` checks `corrected_micrographs.star` only. A different root in the EPS would still make the comparator stop (fails closed).
5. The `audit_path_shape` mutant is legitimately shadowed: `baseline_dir` is always built as `<root>/<case>/UP_only`.
6. Not established: any ON result, P1/P2, neutrality, harm or GPU. These are fake-child and saved-byte checks, not native validation.

## Prior-context dispositions
- v5 R1 M1 (child resource samples missing): fixed in v5.1. The v5.2 diff contains no launch/sampling hunk, so the fix still holds.
- v5.1 R2 CLEAR conditional: M1 and lease inode owner closed. The cleanup / frozen `prior_scratch_bytes` / review-binding limits are carried over unchanged (condition 3).
- r1 STOP: preserved, hash-bound, not converted to a PASS.

## Failed attempts (kept in `failedattempts/`)
- attempt 1: cpu64 hash script wrapped in `timeout`, which macOS lacks (rc 127; nothing ran remotely). Rerun without it.
- probes run1: F3 was a vacuous placeholder (always true). Kept as-is; run2 replaces it with a real count (one launch in the first ledger, no ledger in the refused directory).
