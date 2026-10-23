# Response to regrade-v2 review R1 (23 October 2026)

**Inputs.**
- R1 terminal report, verbatim: `review-r1/REVIEW-R1-terminal.md`, sha256 `acbb3a2d…f502`, copied from `/tmp/motioncorr-orchestrator-20261022/`.
- Reviewer stub: `review-r1/REVIEW-stub.md`.
- Reviewer artefacts (mutants, probes, logs): hashed in `review-r1/REVIEWER-ARTIFACT-HASHES.txt`, not copied.

**Unchanged.** `CONTRACT.md`, `regrade_v2.py`, its 33 controls, `remote_precheck.py`, `REMOTE-PLAN.md` and every
earlier artefact. The original subset FAIL (24 rows PASS, pairs 3 PASS / 5 FAIL, N4 PASS), 16 CUDA rows UNRUN
and the INCOMPLETE aggregate are unchanged.

**Where the repairs live.** `AMENDMENT-1.md` (frozen first, commit `45d41075`, sha256 `e556f54c…1af5`) and new files:
`regrade_v2_1.py`, `EXPECT_LIVE.json`, `test_regrade_v2_1.py`, `mutants_v2_1.py` and `REMOTE-PLAN-v2.1.md`.

| R1 finding | Change | Control evidence (`evidence-v2.1/author01`) |
| --- | --- | --- |
| F1 live checks promised but not implemented | `precheck-live` compares the five trees (HEAD, diff sha256, exact status lines, runner/helper hashes) with `GIT_OPTIONAL_LOCKS=0` and an index-stat guard. It checks three live binaries = receipts = EXPECT, distinct. It refuses any process referring to the scratch (no signals), and fails closed on a missing proc root. | live_pass and live_stale_index_stat_pass PASS; head, untracked, runner, binary-receipt, not-distinct, symlink-component, active-process and proc-missing all FAIL as intended. **Not demonstrated:** the index guard can't be shown to fire (see the mutant pass). |
| F2 weak MRC validation | Exact product contract from `rwMRC.h` and the fixture: 768×512×1, mode 2, nsymbt 0, `MAP `, 1,573,888 bytes; bounded reads; exact payload equality; header bytes beyond the descriptor ignored. `precheck-files` applies the same check. | Header-only, truncated, oversize, wrong mode, wrong shape, nsymbt 8 and missing map word FAIL; payload-equal pairs with differing label bytes PASS. |
| F3 no self-binding | One snapshot of the 117 consumed inputs, with per-file size and sha256 in the report; manifest and precheck binding; re-read after grading; contradiction gate against the original booleans; output refused inside the scratch, if pre-existing, or under a non-canonical path; atomic publication. | Manifest mismatch, changed-after-precheck, output inside scratch, non-canonical root and existing output all refused. **Not demonstrated:** the re-read check (no change can be injected mid-run without a test hook, which was deliberately not added). |
| F4 symlinks | `O_NOFOLLOW` on every component below the root; a symlink is invalid input, never "missing". | Symlinked leaf MRC and symlinked directory component FAIL (exit 1). |
| F5 grammar and RUN binding | ASCII-only block, canonical frame tokens, ASCII value grammar, no traceback on invalid input. Exact `label/arm/case/gpu/cwd/argv` against the recorded root. | `01`, superscript and Arabic-Indic digits FAIL without a traceback; RUN arm/case/cwd/argv and one changed option FAIL. |
| F6 control power | y-only change, y signed zero, distinct binaries, receipt-pin and spec controls; records carry grader, amendment and suite sha256 plus a consumed-identity digest; mutant pass with declared classes. | See below. |

**Controls.** One author invocation (`author01`, namespace `/private/tmp/mc264-v2-1-suite-01`): **65/65 as intended**,
recorded against grader `00cb38b3…b836`, amendment `e556f54c…1af5` and suite `b0a084d3…e129`. On the retained evidence,
the real archive gives STAR layer PASS and FULL UNRUN (no MRCs), with exact row parity and RUN binding on all 24 rows.

**Mutant pass (`evidence-v2.1/mutants01/MUTANTS.json`): retained as recorded, `all_consistent: false`.**
- **Harness defect.** The `out_inside_scratch_allowed` mutant (sha `f2922358…`) wrote `regrade-out/` into the built input
  `inputs/dir_out_inside_scratch/scratch/`. Every later mutant run then saw "output exists" there, so `dir_out_inside_scratch`
  is a contaminated hit for the 14 mutants after it. All 45 tar inputs were checked unchanged afterwards, and that directory is the only stray.
  A future pass must give each mutant fresh input copies or verify input integrity before each run. Nothing was rerun or patched here.
- **Excluding that contaminated control, 31 of 33 declarations hold:**
  - Killed with true coverage: y comparison, sign, frame token, ASCII line, MRC size/descriptor/map, precheck and manifest binding, symlink leaf, directory component, output inside scratch, non-canonical root, RUN argv, RUN arm, distinct receipts, live distinct, process scan, live receipt.
  - Equivalent: Unicode value regex, non-finite check, pair-descriptor equality, N4 exact kills, pair count.
  - Redundant: relation rule (with the contradiction gate), spec-hash, receipt-versus-prediction, parity.
  - Untested: row count (no control truncates frame 12), re-read check, live index check.
- **Two declarations were wrong:**
  - `contradiction_gate_removed` (declared redundant) is killed through the `contradicts original evidence` needle in two MRC controls. It is redundant for the verdict, but not for the reported reason.
  - `live_optional_locks_enabled` (declared killed) **survives**. The stale-index control cannot detect index writes on this host (macOS git), so the no-index-write property rests on `GIT_OPTIONAL_LOCKS=0` semantics and the untested index guard, not on a control.

**Remaining limits for R2.**
- Untested guards: row count, re-read, index.
- No full regrade or remote run (the full regrade is UNRUN).
- Printed precision only. CPU only.
- The plan requires `python3` 3.8 or newer, with the version recorded remotely; local runs used 3.13.7 (suite) and 3.9.6 (synthetic checks).

F3/F4 of the earlier guard reviews (non-finite models; maintainer parity sign-off) are carried unchanged.
