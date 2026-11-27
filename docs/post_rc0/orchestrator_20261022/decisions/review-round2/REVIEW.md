# Independent read-only review, round 2 — decision-preparation packet (PR #281)

- **Reviewed commit:** `d585570cff82b934f528b54a851647090bb1a1b7` ("docs: bind reviewed decision corrections and parent verification"). Round 1 reviewed `6f78f16d`; the intervening commits are `72486b23`, `a23403de` (patch-identical to Sonnet's `af96d247`, verified with `git diff` of both patches) and `d585570c`.
- **Worktree:** detached in the reviewer worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-37fccfcc`. `git status` was clean before and after.
- **Object reviewed:** `docs/post_rc0/orchestrator_20261022/decisions/`. MANIFEST has 58 entries, all hash-matched. Only `MANIFEST.json` itself is unlisted.
- **Live PR #281 at 2026-10-22T21:10:08Z:** open, draft, head `d585570c`, base `36913740`; 0 reviews, 0 issue comments.
- **Report folder:** `/tmp/motioncorr-decisions-review-r2-20261022/`. The supporting outputs are listed under "Commands and limits".

## Verdict

**F1–F5 are closed.** The corrected text is source-accurate, keeps every historical PASS/FAIL/UNRUN/INCONCLUSIVE/UNIDENTIFIABLE state, and adopts no policy or behaviour. The packet:

- keeps C1 qualification INCOMPLETE and C2 UNFROZEN;
- marks every new numerical, scientific and policy trial UNRUN;
- labels the 51 DC Tier-C statuses as a dated 20:45 snapshot;
- states that the current plan requires normal merges;
- leaves every merge-mode alternative unapproved.

**I found one new factual error (R2-1, should-fix) and no publication blocker.** R2-1 is in the M2 description of what direct merges of #273/#274 would change. It does not change the M2 choices as framed. Everything else new is polish.

This review makes **no merge, release, closure or policy recommendation.**

## Closure of round-1 findings

| Finding | Status | Evidence checked |
| --- | --- | --- |
| **F1** M4 scope (global and local) | **Closed** | `M4_M5_OPTIONS_DRAFT.md` L5–7, 19–43, 74–75, 82–88, 105–109. Re-read `src/motioncorr_runner.cpp` at `1f0a58bf` (sha256 `8a3a1ad8…`, equal to provenance). Lines confirmed: `:3530` initial `converged=false`; `:3656` `if (!converged)` gate; `:3678–3679` shift reset; `:3683–3700` #192 resident retry prep; `:3809` second attempt through `alignPatch`; `:3812` skip; `:3855–3858` stderr global-only fallback when `n_obs <= 18`. The brief states the backend-divergent convergence and its Refuse consequence (#273 README L186–201 at `805d9de2`: CPU at the iteration limit and CUDA converged for integer/fractional; 9/9 vs 8/9 patches for affine/noisy, all accuracy FAIL). It also covers ad0b230 parity sign-off, local attempt/drop/fallback states, the zero-frame `not_run` limitation and control 6. The existing same-input retry is acknowledged next to the Retry option (L85–88). All five provenance source hashes and the brief hash match. |
| **F2** M2 sizes, history and recipe | **Closed** (but see R2-1) | **Sizes and history:** the #273/#274 unique trees (2,748,458 / 1,328,117 bytes) and the history import are reproduced by direct `git rev-list --objects \| git cat-file` counts. The history import is 947 blobs / 60,411,705 bytes; 730 / 49,466,987 are in the tip tree and 217 / 10,944,718 are history-only. The C1-relative and main-relative per-PR figures (41/3,025,652; 38/1,825,744; 298/48,447,241; 132/7,026,217) also reproduce. **Recipe:** I ran `inventory_c1_docs.py` with the recorded arguments (exit 0). The tree output is byte-identical to `M2_c1_docs_inventory_e77a51a2.json` (sha256 `ba8515ab…f143`), and the `results` and `recipe` blocks equal the committed history JSON. The script imports only stdlib and reads no sibling JSON. **Merge modes:** L32–49 correctly separate tip from history. They state that same-tree squash changes commit identity but not necessarily tree identity, and that a compact tree changes both. They also say that normal merges are the current plan, that alternatives are unauthorised, and that results do not transfer to a new identity. The widening question (L74–79) makes no choice. **Docs references:** the 57-file `docs/` grep hit count reproduces and is labelled unclassified. |
| **F3** eligibility exposure | **Closed** | Every non-tutorial family carries the corrected audit text. Per-movie `development_exposure` lists `#243` for all 114 movies, and adds `#255/#261/#271` for the 30 e10216/e10474f3/e12963 movies. That membership is corroborated in the `pr255/261/271` snapshots ("30 movies, each tested at two grids"; the 60-config census). `dc262_tier_C_selected` / `dc262_status_in_2045_snapshot` was checked against the cited CSV (`b427037f`, sha256 `34a22d3a…5eae`, equal to the record). Tier C has 51 distinct movie groups × 16 rows, 816 rows in total, **all UNRUN at 20:45**. The ID set and statuses match `exposure_metadata_sources.json` exactly. Tier A/B groups are synthetic (`zero`, `dose2-s06`, …), so the 20:45 Tier-B EXIT0 rows do not expose any of the 114 movies. Only the `tier`, `group` and `status` columns were parsed. The M6 disjointness/collection-unit question is explicit: W5 L48–59 and eligibility README L73–80. The 12963 two-movie pilot is listed as exposed and outside the inventory. |
| **F4** W7 diff semantics | **Closed** | Each provenance row now records `github_base_tip_sha`, `comparison_merge_base_sha` and the exact three-dot argv. Recomputed: the merge bases are `c8844894` for #243 and #250 and `36913740` for the rest. Path counts are 1897/329/108/4/86/60, all with 0 non-docs paths. W7 L6–7 and L27–33 explain the #250 case. The legacy `base_sha` field still equals the base tip, which is consistent with the new field. |
| **F5** #256 note | **Closed** | The live #256 body at 21:08:45Z is byte-equal to `sources/pr256-round2-after.json`; head `f6257294` is unchanged and `updated_at` is 20:59:41Z. The new wording ("#261 retains the negative result: #260's scalar repair does not remove the principal S1 discrepancy") agrees with #261's A0→A1 17→19 and McNemar p=0.754. The earlier after-snapshot is retained unmodified. |

## New finding

### R2-1 (should-fix) — M2 misdescribes what direct merges of #273/#274 onto C1 would change

`M2_EVIDENCE_RETENTION_DRAFT.md:51–54` says that an ordinary merge of `805d9de2` "changes source and tests" and that `a1036901` "changes source and the CI workflow".

**Scenario.** I ran `git merge-tree --write-tree e77a51a2 <head>` (git 2.56.0) to model the ordinary merge onto C1:

- **#273:** the merge **conflicts** in `CMakeLists.txt` and `docs/release/RC0_ACCEPTANCE_REPORT.md`. The `CMakeLists.txt` conflict hunk is C1's #226 D2 `PatchRetryAdmission` test registration, which `805d9de2` lacks. Apart from these two files, the merged tree only adds the 36 unique docs files. No `src/` or `tests/` file differs from C1.
- **#274:** the merge **conflicts** in `tools/test_ci_fail_closed.py`. Apart from that file, it only adds the 32 unique docs files. **Neither `a1036901` nor `805d9de2` touches `.github/`**, either relative to main or relative to C1.
- **Where the "source" wording comes from.** The new blobs with source names (227,181 and 376,693 bytes by name hint) are **history-only intermediate versions**. Their content is already in C1 or is superseded at the merge result.

**Impact.**
- The conclusion "not a docs-only merge" still holds, but the reason is merge conflicts in build and test-tooling files, not source changes.
- A maintainer weighing a normal merge of either head is told about source and CI-workflow changes that do not exist.
- The maintainer is not told that a normal merge needs conflict resolution. A careless resolution of the `CMakeLists.txt` hunk could drop a C1 test registration.

Option 2 (a new docs-only commit) is described correctly and is unaffected.

**Resolution.** Replace L51–54 with a tree-level statement:
- direct merges conflict in the named files, and the merged tree otherwise adds only the unique docs trees;
- the extra non-docs blobs are history-only;
- no `.github/` change is involved.

Record the git version, because `merge-tree` conflict detection depends on it. No execution beyond Git metadata is needed.

## Optional polish (no decision impact)

- **`review-round1/PARENT_CHECK.json`:**
  - It records "57 exact" manifest bindings while MANIFEST now lists 58. The 58th entry is apparently `PARENT_CHECK.json` itself, added after the check. Saying so would remove the apparent mismatch.
  - Its tree/history outputs are under `/tmp` and are not retained, and it ran from the parent worktree on Python 3.13.7 rather than the recorded 3.14.8.
  - I did not use it as evidence. My own recipe run and direct Git counts are independent of it.
- **M4 L24–25:** "CPU-only builds take the CPU alignment path once" is incomplete. A CUDA build that makes no device attempt also calls `alignPatch` once (`converged` starts `false` at `:3530`, and the `:3656` gate is then always entered). Suggested wording: "the CPU route".
- **Concatenation typos remain:**
  - `MANIFEST.json`: "provisional114moviepresence", "12963mapping", "bodies255/256"
  - `exposure_metadata_sources.json` `other_exposure`: "unblinded12963two-movie", "this114movie"
  - `eligibility.json` `M6_disjointness`: "of114development", "separate12963pilot"
  - `M8:14`: "source637b8117"
- **Round-1 polish not taken up:** the binomial note (a single false pass raises the planning N from 59 to 93), and `captured_utc` on `pr255/256-w7-after.json`. Both are optional.

## Decision readiness by item (current, as preparation only)

| Item | Can the question be put to the maintainer now? | Unresolved prerequisites (not publication blockers) |
| --- | --- | --- |
| **M8** (#64/#138/#46/#52) | Yes. Unchanged since round 1; live heads `401a810f`/`875857f1`/`2ef82b02`/`edb57b5d` unchanged at 21:10Z. | None for the choice itself. Any closure remains administrative and maintainer-only. |
| **W7** (six docs PRs) | Direction (archive vs land-as-docs) yes. | Retention location, demonstrated retrieval, and a latest-head review before any landing (#256 explicitly). Closure is not ready. |
| **M2** | Yes, as the narrow #273/#274 question plus the widening question; correct R2-1 first. | For any extraction or compaction: classify the 57 `docs/` references, verify archive retrieval and licence/access, and account for sources and fixtures. Any departure from normal merges needs a separate explicit approval and a decision on binding validation to the new identity. C1 qualification is incomplete. |
| **M4** | Scope (global/local/combined) and whether to authorise a minimal report-only prototype: yes. Policy adoption: no. | Prototype native evidence (UNRUN), backend-divergence and mixed-batch controls, a resume/legacy compatibility choice, and ad0b230 parity sign-off for any refuse/retry change. |
| **M5** | Direction only. | Supported domain, semantics and versioned contract are undefined. Analytic edge fixtures are UNRUN. |
| **M6 / W5** | Only the cohort disjointness and collection/session-unit question (W5 L48–59) is concrete enough to ask now. The executable protocol is not. | Eligibility fields (licence, session, dose/grouping, gain transform, matched particles/halfsets/masks), 26 STAR-path reconciliations, the EMPIAR-12963 mapping, an independently justified harm model and operating characteristics, M3/M4/M5 dispositions, required truth criteria, C2 freeze, and independent protocol review. #65 stays INCONCLUSIVE with no positive certification path. All cohorts are INCOMPLETE. |
| **M1 / M3 / M7** | Not from this packet (README L27–28 says so). | C1 qualification, the full DC experiment evidence (Tier C UNRUN at the 20:45 snapshot), and scientific evidence. |

**True publication blockers for this draft packet:** none found. R2-1 should be corrected before M2 is put to the maintainer.

## Commands and limits

All commands ran from the reviewer worktree. Live endpoints: `gh api` GET only on `repos/KingAlejandro/MotionCorr-standalone`, 2026-10-22T21:08:32Z–21:10:18Z.

- `git checkout --detach d585570c…`
- `git diff --stat 6f78f16d d585570c`
- MANIFEST and `s14_eligibility/ARTIFACTS.json` rehash: Python stdlib with `hashlib`. All 58 and all 15 entries match.
- `git show 1f0a58bf:src/motioncorr_runner.cpp`, then a line read. The five provenance source hashes match.
- `git rev-list --objects <range> | cut -d' ' -f1 | git cat-file --batch-check='%(objecttype) %(objectsize)'` for `3691374..e77a51a2`, `e77a51a2..{805d9de2,a1036901}` and `3691374..{805d9de2,a1036901}`.
- `python3 -B inventory_c1_docs.py --repo . <recorded args> --tree-out tree.json --history-out history.json`: exit 0. Byte-identical tree; equal `results` and `recipe`. Local packed sizes match the record.
- `git merge-tree --write-tree [--name-only] e77a51a2 {805d9de2,a1036901}`, then `git diff --name-only e77a51a2 <tree>`: exit 1 for both, with the conflicts listed above.
- `git diff --name-only <base>...<head>` and `git merge-base` for the six W7 PRs.
- `git show b427037f:…/matrix-snapshot-2045.csv > dc-2045.csv` (sha256 equals the record). Only the `tier`, `group` and `status` columns were parsed.
- `gh api pulls/{281,64,138,46,52,243,250,255,261,271,273,274}`, `pulls/281/reviews`, `issues/281/comments`, and `pulls/256` (saved as `pr256-live.json`).
- `git show 805d9de2:docs/post_rc0/parallel_20261022/numerics/README.md` (L170–205).
- `git grep -l docs/ e77a51a2 -- src tests tools cmake .github CMakeLists.txt`: 57 files.

**Retained outputs:** `tree.json`, `history.json`, `dc-2045.csv`, `pr256-live.json`.

**Limits.**
- No edits, commits, pushes, PR or issue comments, Notion writes, SSH, GPU or native work, CTest, raw data, archive extraction, or scientific endpoints.
- **Side effect:** `git merge-tree --write-tree` wrote unreachable tree and blob objects into the shared repository object store. No ref, index or worktree file changed, and the objects are eligible for `git gc`.
- The packet's stdlib Git-metadata recipe was executed. No other bundled script was executed.
- I did not audit the full source beyond the cited lines or re-review the earlier W1 six-source ledger. App-owned reviews were not enumerated. Merge-conflict detection is specific to git 2.56.0.
- Mac load average was ~5.9 (single-threaded Python only).

## Resolution criteria for any further round

1. **R2-1:** M2 L51–54 states the tree-level effect of direct merges: the named conflicts, unique docs only, history-only source blobs, no `.github/` change.
2. Optionally, the PARENT_CHECK 57/58 note and the M4 "CPU route" wording.
3. The packet still states UNAPPROVED/UNRUN, C1 qualification incomplete and C2 unfrozen. No new outcome inspection or execution is introduced.

R2-1 is a single-paragraph text correction. Whether it needs a further independent round is the parent's call; nothing else is outstanding from this review.
