# M2 evidence retention — unapproved decision brief

**DRAFT / UNAPPROVED / UNRUN as a decision.** All figures are local Git object
metadata (no blob content read, no archive opened, no fetch), pinned to C1
`e77a51a220cb0d91f4ac3c7fac211876d0c6833f` against main
`3691374061f782bc84531fd1c79d017ddcb5a7c2` (an ancestor of C1). They are not a
source review, native qualification, transfer-size measurement or retention policy.
Recipe and validation: `inventory_c1_docs.py` (explicit `--repo/--candidate/--base/--pr`
inputs, standard library only) and `M2_history_object_inventory_e77a51a2.json`.
`M2_c1_docs_inventory_e77a51a2.json` is the earlier tip-tree inventory, unchanged;
the new script regenerates it byte-for-byte.

## What the Notion question covers

Notion M2: "Whether bulky evidence trees from #273 and #274 land on main or stay
archived on branches." That question concerns the first two rows below, about
4.1 MB. The 40 MB-scale bulk is in the selected C1 layers and is outside its wording.

| Layer | Content | Size (logical bytes) |
| --- | --- | ---: |
| #273 unique tree (head `805d9de2`) | 36 files under `docs/post_rc0/parallel_20261022/numerics{,/live}`; 3 archives 1,427,214; largest `native-receipts.tar.gz` | **2,748,458** |
| #274 unique tree (head `a1036901`) | 32 files under `docs/rc0/issue226/integration_20261022{,/support}`; 1 archive, `raw-logs.tgz` | **1,328,117** |
| C1 tip tree, changed docs vs main | 756 files (48,300,778 unique blobs); 11 archives 38,643,183 | 48,385,636 |
| of which `docs/post_rc0/s1/km_truth` | 48 files, absent from main; `raw.tar.gz` 34,973,613; all 48 blobs identical to selected #269 head `1b29b7f9` (an ancestor of C1) | 40,290,016 |
| C1 reachable new history, main..C1 | 102 commits (24 merges), 947 blobs; 53,455,930 under `docs/` (name hint); 730 blobs / 49,466,987 are in the tip tree, 217 / 10,944,718 are history-only | **60,411,705** |
| Local packed disk for those 947 blobs | `objectsize:disk` in this clone; packing-specific, **not** a transfer or storage size | ~40.6 MB (40,633,122) |

The two unique trees are absent from C1 by path (one 5,701-byte and one 2,250-byte
blob in them are content-identical to blobs already at C1 under other paths).
For scale, main's `docs/` is 6,642 files / 69,865,100 bytes.

## History and merge mode

Tip size and history size differ. An ordinary merge of the selected C1 history
makes all 947 new blobs (60.4 MB logical) reachable, even if a later commit deletes
the bulky files. A squash onto the stated main tree can retain an identical tip
tree while avoiding the 217 history-only blobs; it still needs the 730 new blobs
present in the candidate tip (49.5 MB). A fresh compact composition that excludes
the bulky tip paths and keeps the component histories off main can avoid that
bulk too. A history rewrite only saves the objects actually excluded by its
resulting tree and ancestry; it is not automatically a storage reduction.

The current plan requires normal merges. None of these alternatives is selected
or authorized here. A squash or rewrite changes commit identity; a compact tree
also changes tree identity. Any alternative needs explicit maintainer approval,
source/fixture/dependency accounting and a decision about which validation can
be bound to the new identity. Qualification of `e77a51a2` is still incomplete;
this brief neither transfers its results to a new identity nor chooses a merge
mode.

A normal merge of either pinned head onto C1 needs conflict resolution.
`git merge-tree --write-tree` (Git 2.56.0) reports #273 conflicts in
`CMakeLists.txt` and `docs/release/RC0_ACCEPTANCE_REPORT.md`, and #274 in
`tools/test_ci_fail_closed.py`. Apart from those conflicted files, the synthetic
merged trees add only their 36/32 unique docs paths: no `src/`, `tests/` or
`.github/` path changes. Keep C1's test registrations and failure checks if a
later merge is chosen. This preview is not a resolved merge or its validation;
`M2_merge_preview_e77a51a2.json` retains the commands, paths and conflict output.

The 4/3 new commits and 41/38 new blobs (3,025,652 / 1,825,744 logical bytes)
count reachable history relative to C1. Intermediate source-named blobs in those
ranges do not imply production-source or CI-workflow changes in the merged tree.
A docs-only landing would instead be a new commit that adds the 36/32 unique
files and records the pinned heads. Merging either directly onto main rather
than after C1 imports 298 / 132 blobs (48,447,241 / 7,026,217 bytes), because
both heads contain earlier selected layers.

## Choices for the maintainer

1. **Keep #273/#274 integration trees on their branches** (current state). Main
   gains nothing from them. The pinned heads must then be retained as evidence
   (see W7/M8: no deletion of those branches without a verified retrieval path).
2. **Land only their unique trees on main** after C1, as a docs-only change with
   pinned source heads recorded: +2.75 MB and +1.33 MB logical. This needs a
   latest-head review of what is claimed, and adds no source.
3. **Compact main-tree record plus retained archives.** Freeze the inventory,
   archive digests, retrieval links and retention owner; verify retrieval and
   licence/access; check that no source, test fixture or acceptance evidence was
   removed. A docs-only revision needs explicit provenance accounting and cannot
   inherit an earlier SHA's test results. Under a merge-commit merge this
   saves nothing in history, per above.

Widening question: **do you want M2 widened to cover C1's own bulk** (the #269
`km_truth` tree, 40.3 MB at the tip, and the other ten archives), or kept to
#273/#274? The narrow M2 wording does not itself approve the 60.4 MB history import.
Widening would bring C1 retention into that decision; any change to the planned
normal-merge composition needs a separate explicit decision about its identity
and qualification.

## Constraints on any option

- `docs/` is not inert. At C1, tests, tools or CMake read paths under `docs/`
  (e.g. `docs/issue85_laneC/compare_output_trees.py` and
  `tutorial_24_movie_manifest.json`, `docs/rc0/qf/tools`,
  `docs/issue213/evidence/`, the last of which C1 changes). A line grep finds
  `docs/` in 57 files of `src`, `tests`, `tools`, `cmake`, `.github` and
  `CMakeLists.txt`; those hits are not yet classified as runtime reads versus
  comments. Source, tests, fixtures and tools must remain reproducible under any
  option, so classify them before moving or deleting anything.
- No file, archive, branch or input has been removed or moved, no archive was
  opened or executed, and no historical PASS/FAIL/UNRUN record has changed. Archive
  existence is not provenance. A retention choice is not permission to relax
  validation or to merge C1.
