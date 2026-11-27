**Verdict: not ready for the remote regrade as written.** The grader's row and pair logic is sound, and nothing in the checks is falsely green on the retained evidence. The plan, the precheck and the MRC validation have gaps that need fixing in a new reviewed commit first. They are listed below. Nothing remote was used.

**Setup:** I reviewed `364a1a73`, branch `verify/264-native-20261022`, in worktree `t3-96f54dde`. Local checks ran from my own directory `/tmp/motioncorr-guard264-regrade-v2-review-r1-20261023-sonnet/` (`inv1`–`inv4`) under a nonblocking lease, one thread, host load ~3/14. I made no edits to the repository or evidence, and did no SSH, build, native or GPU work.

## What holds

- **Scope and contract:**
  - The commit touches only `n3-cpu1-regrade-v2/`; there is no `src`, `tests` or `tools` change since `3751bd05`.
  - `CONTRACT.md` is byte-identical to the `bab2a17c` freeze.
  - The README hashes match (`regrade_v2.py` `8bf7b10f…`, `test_regrade_v2.py` `a7783cf4…`).
  - The `.py` files carry GPL SPDX headers.
- **Author controls:** I re-ran them: 33/33, exit 0, with the same needles. Regenerating the manifest from `evidence.tar` is byte-identical to the committed one (101 files, 8 cases).
- **Global-row logic:** it is correct. A value change in x or y, signed zero, NaN/inf, missing, duplicate or wrong labels, two blocks and non-numeric tokens all fail. Row parity with the original is exact.
- **Image relation, bindings, N4:** the image-relation logic works as intended. The binary, spec and stdout bindings and the exact N4 kill set are enforced, and the CUDA rows stay UNRUN.

## Findings

**F1 (launch-blocking): `REMOTE-PLAN.md` promises checks that no script implements.**
- Item 2 of the plan says the precheck verifies the live binaries (`sha256sum build-ov-*/motioncorr`) and each source tree's HEAD, diff, status and runner/helper hashes against the `check_sources.py` values.
- `remote_precheck.py:42-56` checks only the 101 manifest hashes and that the 16 MRCs exist as regular files. It contains no git, binary or source code.
- The grader binds `RUN.json` `binary_sha256` to the receipt text, which is two recorded artifacts rather than the live binary.
- `check_sources.py` can't stand in. It needs `G_SCR`/`G_SHA` and compares the setup-time `SOURCES.txt` manifest, which is the earlier R4 finding about manifest versus live source.
- Running git inside the scratch trees may rewrite `.git/index` unless `GIT_OPTIONAL_LOCKS=0` is set. That would break the "writes nothing in the scratch" claim. I did not verify the git behaviour.
- Fix: either implement and review a read-only live check (the parent's `verify_guard_cpu1_live_v2.py` remote block is a template), or drop the claim and rely on the already-published post-run checks.

**F2 (medium): MRC validation is too weak to support "recomputed from immutable payload".**
- `mrc_payload` (`regrade_v2.py:141-147`) checks only length ≥ 1024 and that the extended-header size is consistent.
- Dimensions, mode and payload length are never validated, and the two headers are never compared.
- I built directory-mode fixtures where all 16 MRCs were header-only (flip pairs differ by one byte): FULL PASS, exit 0 (probe P1).
- Equal truncated payloads also gave FULL PASS (P3), and equal payloads under disagreeing headers gave PASS (P2).
- The precheck passes P1 as well, because it records only whole-file sha256 and size with nothing to compare against.
- Fix: require size = 1024 + extended header + nx·ny·nz·bytes(mode) in the grader, and have the precheck assert the 16 sizes are equal.

**F3 (medium): the regrade output is not self-binding, and nothing guards immutability.**
- In directory mode, `REGRADE_V2.json` records no hash of any file it consumed (`DirSource.identity` is just the path). Only `precheck.json` has hashes, and it is a separate step.
- Files are re-read repeatedly with no snapshot, and there is no post-run re-check, mtime or "chain finished" test. Another process or the same user could change a file between precheck and grade.
- The MRC hashes have no pinned comparator at all.
- The report writes `historical_original.pairs[].image_data_equal` next to the recomputed value, but nothing asserts they agree. That is a cheap contradiction gate for the stop-on-contradictory-evidence rule.
- `--out` is not refused under `--scratch-root`, and `REGRADE_V2.json` is written non-atomically (`regrade_v2.py:303,319`).
- Fix: record per-file sha256 in the report, re-run the precheck after grading and compare, assert recomputed equals original booleans, and refuse `--out` under the scratch.

**F4 (low): symlink handling is looser than the README says.**
- Only a symlink escaping the root is refused (the control covers only that). A symlink to a file inside the root is read as "missing": an MRC gives FULL UNRUN, exit 2 (P4).
- A symlinked directory component inside the root is followed silently: FULL PASS (P5).
- Both the grader and the precheck check only the leaf.

**F5 (low): a few parse and binding slips.**
- `isdigit()` and `\d` accept non-ASCII digits. An Arabic-Indic digit in a value was accepted as numerically equal (P6). A superscript frame digit crashes into the generic handler: exit 1, still fail-closed, but through a traceback path (P9).
- A frame written as `01` is accepted, although the contract says a plain integer (P7).
- The `RUN.json` `arm`, `case`, `argv`/`--o` and `cwd` fields are not checked (P11). Binding rests on the binary hash, the injected spec and the stdout/stderr path suffix. The precheck pins the file bytes, which is only as good as F3.

**F6 (control power):**
- I ran 24 mutants of the grader against the 33 controls. 17 were killed; the remaining 7 are accounted for below, and there are three genuine control gaps.
- The first gap is a y-only difference: there is no control for a y-value change or y signed zero, so removing the y comparison survives. My probe P8 shows the real grader does fail on a y change, so this is missing coverage rather than a code defect.
- The second gap is the check that the three arms' binary hashes are distinct.
- The third is the spec-hash consistency check.
- Of the other four survivors, two are equivalent mutants (N4 exactness and the pair-count check are implied by the row checks), one is a redundant guard (the receipt-versus-prediction check), and one is a regression guard that never fires in the controls (the original-parity check).
- The retained `CONTROLS.json` files record no grader hash, so they can't be tied to `8bf7b10f`. The README's `controls-01`/`02` claims are otherwise accurate.

Minor: the plan should record the remote `python3` version, and check the clone HEAD and `regrade_v2.py` hash before running.

## Recommended next step

Close F1–F3 in a new reviewed commit, so the namespace commit hash changes and it needs a fresh review. Add the y-only and distinct-binaries controls, and F4/F5 if cheap. Then re-offer the bounded, read-only CPU 13 regrade. This review supports nothing about guard adoption, CUDA (16 rows UNRUN), the N3/N4 aggregate (INCOMPLETE), science or merge. The original FAIL (24 rows PASS, pairs 3 PASS / 5 FAIL, N4 PASS) stands.

## Artifacts (all under the review directory)

| Artifact | sha256 / note |
|---|---|
| `inv1/author-controls.log` | `a750a2e6…3218` (rc 0) |
| `inv1/author-controls/CONTROLS.json` | `8b3c5848…5095` |
| `inv2/MUTANTS.json` | 24 mutants (`mutants.py`, `inv2.log`) |
| `inv3/PROBES.json` | probes P0–P11 (`probes.py`) |
| `inv4/` | precheck runs and the manifest regeneration |
| `REVIEW.md` | short verdict stub |

Failed controls: none. The mutant survivors and the P1–P5, P6, P7, P9 and P11 results above are the findings, retained in `inv2` and `inv3`.
