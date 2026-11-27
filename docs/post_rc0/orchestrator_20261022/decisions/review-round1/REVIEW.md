# Independent read-only review, round 1 — decision-preparation packet (PR #281)

- **Reviewed commit:** `6f78f16d4f5a98da1bf8be1acf4fe773e33625f8` (branch `docs/orchestrator-ledger-20261022`, draft PR #281). Detached in reviewer worktree `/Users/alex.konstantinov/.t3/worktrees/MotionCorr/t3-4765467d`; `git status` clean before and after.
- **Live PR #281 at 2026-10-22T20:48:43Z:** open, draft, head `6f78f16d…`, base `36913740…`; 0 reviews, 0 issue comments.
- **Object reviewed:** `docs/post_rc0/orchestrator_20261022/decisions/` — README, M2, M4/M5, W5/S1.4, M8, W7 drafts, their provenance JSONs, `MANIFEST.json`, `sources/`, `s14_eligibility/` (including `archive_metadata/`). Also the Notion plan text `/tmp/motioncorr-orchestrator-20261022-notion-plan.txt` (sha256 `13e074f9…2796`, mtime 2026-10-22 19:58:41 local).
- **Reviewer actions:** read-only. No source/doc edits, commits, pushes, PR/issue comments, Notion writes, SSH, GPU work, data fetch/decode or CTest. The only reads outside the packet were Git objects plus `gh api` GETs, which are listed below. Local arithmetic ran under `python3 -B`, single thread; host load average was ~4.7 at the time.

## Verdict

**As an unapproved decision-preparation DRAFT, the packet is broadly accurate and internally consistent. I found no silent behaviour selection, gate relaxation, relabelled failure, or treatment of parity as accuracy.** Historical PASS/FAIL/UNRUN/INCONCLUSIVE/UNIDENTIFIABLE states are preserved where they are cited. All 51 MANIFEST bindings match. The numerical inventories reproduce exactly, and the binomial arithmetic is correct and correctly bounded.

Three findings (F1–F3) should be fixed before the packet is used to *request* the M4, M2 or M6 decisions. They concern decision completeness and one artifact field error. They do not block publication of the packet as a draft. F4 and F5 are provenance and published-wording corrections. The rest is optional polish.

Concreteness of each requested decision:

| Item | Can be requested now? | Why |
| --- | --- | --- |
| M8 (#64/#138/#46/#52) | **Yes** | Every cited claim is corroborated by the retained snapshots and the live heads are unchanged. The disposition preserves heads and evidence and makes closure administrative. |
| W7 (six docs PRs) | **Direction yes; closure no** | The archive-or-land choice can be requested. Closure prerequisites (retention location, demonstrated retrieval) are correctly listed as unmet. #256 land-as-docs needs its own latest-head review (stated). |
| M2 | **After F2** | Tip sizes are correct. The brief omits the #273/#274 sizes the Notion question asks about, and the dependence on merge mode/history. |
| M4 | **After F1** | The options are framed for global alignment only. Existing local-patch nonconvergence behaviour and backend-divergent convergence are absent. |
| M5 | **Direction only** | The options and prospective fixtures are adequate for a draft. The supported domain is explicitly still undefined (stated). |
| W5 / M6 | **No (as the draft itself says)** | Eligibility and exposure (F3), harm model, C2 freeze and truth criteria are unresolved. It is correctly not presented as a preregistration. |

## Material findings

### F1 — M4 omits existing local-patch nonconvergence behaviour and backend-divergent convergence (M4 request readiness)

`M4_M5_OPTIONS_DRAFT.md:9–17, 21–27, 45–55` describe only the discarded **global** return value. At the inspected source `1f0a58bf` (`src/motioncorr_runner.cpp`, sha256 `8a3a1ad8…` = provenance):

- **Retry already exists.** On CUDA builds, a completed resident patch attempt that did not converge is re-attempted from the same input (`:3529–3545`, `:3656 if (!converged)`, `:3662–3681` reset of the accumulated shifts, `:3683–3700` issue #192 resident retry prep). The second attempt runs through `alignPatch()`, which re-dispatches CUDA when `use_gpu` is set (`:3809`).
- **Still-unconverged patches are dropped silently.** Such a patch is skipped by `:3812 if (!converged) continue;`.
- **Fallback to global is reported only on stderr.** When too few patches remain, `:3856` writes "too few valid local trajectories…" to **stderr** and falls back to the global trajectory (`mic.model = NULL; goto skip_fitting`). #268's own body cites this path (L3812/L3856) as part of the silent-nonconvergence defect.
- **Only CUDA logs convergence.** CUDA logs `converged=yes/no` (`cuda_alignpatch.cu:723,1070,1093`). The CPU log has only the RMSD lines (#268 body). A report-only prototype starts from asymmetric observability.
- **Convergence differs by backend on identical input.** The retained #273 packet (`805d9de2:docs/post_rc0/parallel_20261022/numerics/README.md:186–201`) records `integer` and `fractional` with CPU at the iteration limit and CUDA converged, and local patches at 9/9 CPU versus 8/9 CUDA for `affine` and `noisy`.
- **Inherited RELION behaviour.** The global result is ignored identically in RELION `ad0b230` (#268 body, L1512). Refuse or retry changes CPU behaviour inherited from RELION and breaks the parity invariant.

**Impact.**
- The proposed `global_alignment` field and the four options cannot satisfy "nonconvergence no longer silent" if the local skip-and-fallback path stays unreported.
- The Retry row (`:49`, "not another identical-state attempt") does not acknowledge that an identical-input local retry is current production behaviour.
- The Refuse option would make publication **backend-dependent for the same movie**. The maintainer is not told this.
- The parity sign-off that refuse/retry would need is not flagged.

**Resolution.** Add a short "existing local behaviour" paragraph with these line references. State whether M4 covers global only or both global and local; if both, add a local quality field such as patches attempted/retried/converged/dropped and fallback-to-global. Add backend-divergent convergence as a required control and a decision consequence for Refuse, and flag the ad0b230 parity dependency. No new execution is needed.

### F2 — M2 does not size the trees the decision asks about, and omits the history/merge-mode consequence (M2 request readiness)

The Notion text defines M2 as "Whether bulky evidence trees from #273 and #274 land on main or stay archived on branches". `M2_EVIDENCE_RETENTION_DRAFT.md:15–19` gives only path counts for those trees. I reproduced the counts: 36 paths unique to #273 under `parallel_20261022/numerics{,/live}`, 32 unique to #274 under `issue226/integration_20261022{,/support}`, none present in `e77a51a2`.

Their sizes, which are local object metadata:

| Tree | Logical bytes | Largest file |
| --- | ---: | --- |
| #273 unique | **2,748,458** | `native-receipts.tar.gz`, 1,390,257 |
| #274 unique | **1,328,117** | `raw-logs.tgz`, 695,240 |

The bulk is elsewhere and already inside the selected C1 layers: `docs/post_rc0/s1/km_truth` is 40,290,016 bytes, and its `raw.tar.gz` (34,973,613 bytes) is present at `#269 1b29b7f9` and absent from main. The brief says this, but it does not give the maintainer the numbers needed to see that the M2 question as worded concerns about 4 MB while about 40 MB is outside its wording.

Option 2, "extract compact main-tree record" (`:26–33`), is described as a tip-tree operation. Running `git rev-list --objects 3691374..e77a51a2` gives **947 new blobs: 60,411,705 logical bytes, of which 53,455,930 are under `docs/`, and about 40.6 MB on disk in the local pack**. The disk figure depends on packing and is not a transfer prediction. An ordinary merge of the component histories imports all of these regardless of a later tip deletion. Only a squash/rewrite, or a fresh compact commit with the components kept off main, avoids it. That would also change which SHA carries the tests (partly noted at `:31–33`).

`inventory_c1_docs.py:11` reads a sibling `M2_c1_docs_inventory.json`. That file was never committed (`git log --all` finds no history for the path), and the 36/32 counts come from it. README `:39–40` calls this a "/tmp inventory dependency", but the code reads a path beside the script. The counts do reproduce (above).

**Resolution.** Add the #273/#274 unique-tree sizes. Add one sentence and one number on history import, stating which merge modes each option implies. Correct the predecessor-dependency wording, or retain the predecessor file. Optionally ask the maintainer whether M2 should be widened to cover the km_truth bulk in the selected layers.

### F3 — `eligibility.json` exposure field is wrong for nine families and omits known development/tuning exposure (W5/M6 readiness)

`s14_eligibility/eligibility.json` sets `individual_scientific_exposure_audit` to `'UNRUN; historical tutorial study already unblinded'` for **every** family, including e10028…e12963. That text describes only the tutorial.

The 90 non-tutorial movies are the exact S1 development set. They are used by the #243 sweep, the #255/#261/#271 censuses, the W2 DC experiment (which feeds M3) and the e10216-01 nonconvergence record. `W5_S14_PROTOCOL_DRAFT.md:31–34` itself requires recording "whether prior scientific outcomes **or tuning** used the collection".

The Notion W5 requires "held-out collections including at least one S1 family". If development-exposed movies cannot serve as held-out data, an S1 family needs **new, disjoint movies from the same accession**, which implies acquisition. W5 (`:20–23, 40–42`) proposes no acquisition and only generically says to report a gap. Whether S1-family held-out movies must be disjoint from the 114 is an M6 choice the draft does not present.

**Resolution.**
- Correct the per-family field text.
- Add per-movie or per-family development/tuning exposure. At minimum, list the campaigns that consumed each ID, without inspecting any new outcomes.
- Add an explicit M6 question on disjointness and its acquisition implication.

No data access is needed.

## Should-fix (accuracy/provenance, not decision-blocking)

**F4 — W7 #250 provenance labels the wrong diff base.** `W7_DOCS_DISPOSITION.provenance.json` records #250 `base_sha 3691374…`, which is GitHub's current `base.sha`. The 329 `changed_paths` were computed against the merge base `c8844894…`; they equal `git diff 3691374...7fc9733f` exactly. A reader who repeats the documented "changed paths against each recorded base" (`W7_DOCS_DISPOSITION_DRAFT.md:24–27`) with a two-dot diff gets 346 paths: 14 deletions under `docs/post_rc0/issue246/` and one non-docs path (`tools/profiling/tests/test_import_subset_boundaries.py`). That appears to contradict "changes confined to docs/" (`:5–6`). The other five PRs have merge base equal to the recorded base, and all six byte totals reproduce exactly. **Fix:** record `merge_base` and the three-dot semantics.

**F5 — The published #256 body note can be read as the opposite of #261's conclusion.** The live/after snapshot (`sources/pr256-w7-after.json`, updated 2026-10-22T20:24:44Z) says "#261 retains the negative result for that repair as the principal remaining S1 cause." #261 says the counts "support the stated negative result for peak fitting as the principal missing cause". In other words, the repair is *not* the principal cause. The garbled clause can be read as asserting it *is*. W7 (`:19`) cites this note as carrying the qualifications. This is outward-facing text that the parent owns. **Fix:** re-word, for example: "#261 retains the negative result: #260's scalar repair does not remove the principal S1 discrepancy." The #255 note is accurate.

## Optional polish

- **Typos:** `M8:14` "source637b8117"; `archive_metadata/README.md:16` "total50/39"; `MANIFEST.json` "provisional114moviepresence", "12963mapping", "bodies255/256".
- **Snapshot timestamps:** `pr255/256-w7-after.json` carry `updated_at` but no capture timestamp. Add `captured_utc` for symmetry with the before-snapshots.
- **#65 base:** W5 omits the Notion instruction to refresh #65 "against C2 rather than its 3e3a196 base". Live #65 is head `2afbb314`, base `3e3a1967`. One sentence would close this.
- **Binomial note:** W5 could add that a single false pass raises the zero-failure planning N from 59 to 93 for the same 5%/95% bound. Gold-standard RELION halves also require MPI and fixed seeds; the latter is partly stated at `:65–66`.
- **Eligibility coverage:** the two #73/PR87 EMPIAR-12963 pilot movies (hash prefixes `b25af46f`, `3c8d113f`) are not in the sweep-based inventory. None of the ten e12963 sweep hashes match them, so they are a separate already-acquired resource that the inventory does not list.
- **State schema:** `cudaAlignPatch` returns `true` for `n_frames == 0` (`cuda_alignpatch.cu:1111`). A `not_run` state cannot be derived from the existing bool.

## Verified correct (bounded checks)

| Claim | Check | Result |
| --- | --- | --- |
| M4 global return discarded | Read `src/motioncorr_runner.cpp` at `1f0a58bf` | `:3367`, `:3371` discard the result. Shifts are recorded from `:3375`. Tolerance 0.5 at `:4679`, test at `:4854`, `return converged` at `:4866`. GPU wrapper at `:4657`. CUDA operator errors throw, so the bool is convergence. |
| Failure path and `dataset_ready` | Read failure path and `run_dataset.py` | `:1049–1094` retains per-movie outputs, fails the job and withholds joint output. `run_dataset.py:124,137` gate `dataset_ready` on aggregate PASS. |
| M5 bracket check | Read CPU peak fit | `:4804–4813` checks only that the denominator is nonzero (EPS); there is no bracket check. |
| Provenance hashes (M4, W5, M8) | Hashed the cited files | Five M4 source-file sha256 values, the brief hash and all M8/W5 snapshot hashes match. |
| MANIFEST | Hashed all 51 entries | 51 match. Only `MANIFEST.json` itself is unlisted, as expected. |
| M2 tip totals | Two-dot ACMR at `e77a51a2` vs `3691374` | 756 files, 48,385,636 logical bytes, 48,300,778 unique, 11 archives totalling 38,643,183. km_truth `raw.tar.gz` is at `#269 1b29b7f9` and absent from main. |
| W7 byte totals | `ls-tree -l` at each head | All six totals reproduce exactly. Paths are docs-only under three-dot diff (see F4). |
| S1.4 presence probe | Recounted `s14-presence.json` | 232 requested = 114 movies + 114 conventional STARs + 4 gains; 206 observed; 26 missing, all `movies.star`; 114/114 sizes match the manifest; 114 distinct declared hashes; exit 123 (xargs). Missing STARs by family: e10164 9, e10474f4 8, e10474f3 6, e10216 3. All families are `INCOMPLETE, not admitted`. |
| Archive metadata | Compared the selected EMPIAR fields | Matches the README table, including the unresolved 12963 mapping (raw 8192² at 0.97 Å versus corrected 4096² at 0.49 Å; recipe 4096², 39×49, 0.97 Å). No licence field is present, and licence is correctly not marked verified. |
| W5 historical values | Read #65 at `2afbb314` | Margins rho ≥ 0.95, d143 +0.05 Å and B −10 Å² match PROTOCOL.md:150–152. Stage B INCONCLUSIVE, no positive certification path, and the posthoc exploratory pilot all match. |
| Binomial arithmetic | Exact computation | `1−0.05^(1/20)` = 0.139108; N=59 gives 0.049508 and N=58 gives 0.050339, so 59 is the minimal zero-failure N. Independence and forward-model limits are stated correctly. |
| M8 claims | Searched the retained snapshots | "Not for merge", the 10 Å² warning tier (θ≈5.72, 0/228, 15/134), the leaked holdout, "#206 parked under T1", 0.01322–0.01323 / 1.04× / `637b8117`, and the projected 10–14× are all present. Live heads equal the pinned heads; all four PRs are open. |
| W7 row claims | Searched the snapshots | 27→17 superseding 27→15; 17/19/16 and 0/60 including e10216-01; 600 processes / five selected checks; the S1.3b wording; the OOM UNRUN. All present. #255/#256 heads are unchanged before and after, and the bodies only gained dated notes plus the #256 link repointing with the original snapshot retained. |
| M4 #273 characterization | Read #273 numerics README | `805d9de2` README:186–201 matches: flat VALID/UNIDENTIFIABLE, repeated OUTSIDE_FIXED_ROI/UNIDENTIFIABLE, noisy OUTSIDE_FIXED_ROI/FAIL. |

**Live endpoints**, all `gh api`, `repos/KingAlejandro/MotionCorr-standalone`, 2026-10-22T20:48:43Z–20:49:44Z:
- `pulls/{281,243,250,255,256,261,271,64,138,46,52,65,260,273,274}`
- `pulls/281/reviews` and `issues/281/comments`
- `issues/{268,263}` and their comments (0 each)
- `issues/{61,73}`: updated_at unchanged from the snapshots (2026-10-09T22:43:58Z, 6 comments; 2026-09-29T13:51:22Z, 5 comments)

**Limits.**
- No full source audit beyond the cited lines.
- No review of the earlier six-source review or the 29-PR ledger, which are out of scope.
- No archive extraction or payload hashing.
- No verification of durable retrieval.
- App-owned or non-GitHub reviews were not enumerated.
- History-blob disk size comes from this machine's pack and is not a transfer or remote-storage measurement.

## Resolution criteria for a round-2 review

1. **F1:** the M4 brief states its global/local scope; cites the existing local retry, skip and stderr fallback; adds backend-divergent convergence as a control and as a Refuse consequence; flags the ad0b230 parity dependency.
2. **F2:** the M2 brief gives the #273/#274 unique sizes and the history-import figure with its merge-mode dependency; the predecessor-dependency wording is corrected or the file retained.
3. **F3:** the eligibility exposure field is corrected per family; development/tuning exposure is recorded; the M6 disjointness/acquisition question is explicit.
4. **F4/F5:** the W7 provenance records merge-base semantics; the #256 note is re-worded by the parent.
5. The packet still states UNAPPROVED/UNRUN, and no new outcome inspection or execution is introduced by the fixes.

**Recommended next bounded action:** the parent applies the F1–F3 text and artifact fixes and the F4 provenance field, corrects the #256 note, then requests a fresh round-2 review of the new SHA. M8 can be put to the maintainer now.
