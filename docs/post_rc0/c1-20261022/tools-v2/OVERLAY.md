# Tools v2 overlay (task-local, for stages not yet started)

Tested source SHA (binary provenance, unchanged): `e77a51a220cb0d91f4ac3c7fac211876d0c6833f`. Everything run so far (E1, builds, sticky rows, CPU/CUDA CTest, any
running CUDA+nvCOMP CTest) stays bound to that SHA, its scratch `…-c1-20261022-e77a51a220cb`, its frozen manifest (`e23d2e4c…`), and the v1 tools used.
This overlay has its own packet SHA (the commit that adds this directory). It changes qualification tooling only: the production source delta between the two
SHAs is empty (`git diff e77a51a2 <packet> -- . ':!docs/post_rc0/c1-20261022'` prints nothing; recorded in the evidence). The overlay is deployed outside the
exact checkout (`$C1_SCR/tools-v2-run/` = v1 tools with these files on top) so `src/` stays exact and clean.

Applies to stages not yet started: T24 arms/comparisons/attribution/dataset, R12/12ds, K267/K269 helpers are unchanged. It does not alter a completed or running stage,
a retained receipt, a numerical option, a gate, or the expected collections. No wider rerun of earlier rows is required by this change.

| File | Change from v1 |
|---|---|
| `c1_tutorial24.py` | comparison results are validated before use: DIFFERENT only for a complete, consistent products report (24 movies, expected inventory, no duplicates, status/rc agree); everything else INVALID with reasons; comparator command, stdout, stderr, rc, input/manifest/comparator/report hashes retained per label; attribution reads validated class files only, refuses missing/invalid input, flags comparator inconsistency, labels N-only reproduction `COMBINED_NUMERICS_COMPOSITION_ONLY` (not an individual-fix attribution), keeps N→C1 changes and unattributed products as blockers; exit 0/1/2 as documented; GPU runs go through `c1_lane.run_case_nb`; `dataset` refuses to run unless the lease is held |
| `c1_lane.py` | `run_case_nb`: nonblocking GPU3 lease (`LOCK_EX|LOCK_NB`), stop on contention, stop on a foreign process on the lane GPU (no polling), pre- and post-run health while the lease is held (failed post-check turns a successful child into rc 37, `child_rc` kept); bench lock probed only |
| `make_c1_item12.py` → `c1_item12.py` | `run_case = c1_lane.run_case_nb` (the same nonblocking/health rules for R12) |
| `c1_item.sh` | `12ds` holds the canonical lease (nonblocking) for the whole dataset row; health checked while held |
| `test_c1_t24_failclosed.py` | 12 host controls: invalid reports/ missing files never read as identity or empty differences; valid PASS and numeric-difference FAIL preserved; single-fix/combined/unattributed distinction; lease contention, foreign occupant, pre-health failure stop before launch; post-health failure after a successful child is rc 37 with the lease held; existing failures not masked |

Limits: the host controls use mock reports and programs; they are not native evidence. Attribution is at the level of the four builds (N, only254, only260, only270);
single-fix reproduction is exact-byte reproduction of C1's product by that build alone, N-only reproduction is the combination, and interactions stay unresolved.

## Iteration record

Iteration 1 of T24 (packet `772f2cf5`, `chain-3.sh`) failed in orchestration, not in the tools: the one-off chain script escaped `$SC` inside a remote heredoc, so every
arm after F-fresh launched with `/t24/...` or `/build-nvcomp/...` paths and failed before running; all 36 resulting comparisons were correctly classified INVALID and the
attribution stayed INVALID (the fail-closed handling worked as designed). Retained unchanged in `t24/`: F-fresh G/L (valid, rc 0, nvcomp witness), the failed stage
receipts, the INVALID class files, and the F-cpu runs that were launched with correct paths. Iteration 2 (`C1_T24_DIR=t24-i2`, stage names `i2-*`, chain written locally
and copied, not generated through nested quoting) re-runs every GPU arm in its own directory; the iteration-1 F-cpu arms may be used as the CPU baseline only if
their run records are rc 0. Packet 2 adds only the `C1_T24_DIR` override to `c1_tutorial24.py`.

## Corrections after the parent's real-CLI and timeout controls (packet 3)

* `classify` expects `star_count == n + 1` (the comparator counts the n per-movie STAR files plus the joint STAR); the first host tests had repeated the same wrong
  count in their mock reports. New controls run the actual `compare` wrapper against the actual comparator on tiny trees (tests/test_compare_output_trees.py builder):
  identical -> rc 0 IDENTICAL, one-pixel difference -> rc 1 DIFFERENT with the product named, truncated tree -> rc 2 INVALID, provenance retained.
* `attribute` now requires the frozen-lane control `F-fresh_vs_F-retained` to be IDENTICAL: DIFFERENT is a blocker (exit 1), missing or INVALID makes the attribution
  INVALID (exit 2). Cached class files are validated for schema (state/products consistent, unique strings), label, the expected base/candidate trees and the
  stored comparator report hash; absent `products` is no longer treated as `[]`.
* `run_case_nb` starts the child in its own session and, on timeout or when anything of that session outlives a finished child, terminates only that session (SIGTERM, then
  SIGKILL), waits until it is empty and reaps the child, all before the post-run health check and the lease release. A timeout stays a timeout failure (rc None); a
  descendant outliving a successful child is rc 38; processes surviving cleanup are rc 39. Cleanup and PIDs are recorded in `cleanup`.
* The lane tests need Linux `/proc`: they run on 4GPUs (host-only, sleep-only children) with `C1_TEST_REPO` pointing at the exact checkout; they are skipped on macOS.

## Iteration 2 stop and the retained-baseline lane control (packet 4)

Iteration 2 (`chain-i2.sh`, packet `1aac4159`) stopped at `i2-cmp-lane-G` (exit 2, INVALID) after `i2-run-F-fresh-G` (exit 0), as designed. Root cause: the retained RC0 trees
`W-QF/multigpu/{G,L}/{s0,w1,w2,w4}` contain no `*.mrc` files. The QF driver `docs/rc0/qf/tools/multigpu_publication.py` deletes every `*.mrc` and `*.pdf` after grading
(`p.unlink()` loops near lines 310-316 and 440-447) and removes its `cmp/` trees; it keeps the comparator reports `cmp-*-products.json`, which carry header/extended/payload sha256
for all 24 MRCs of each tree, and the 25 STAR files. The F-fresh run itself was correct: 24-row input STAR identical to the manifest hash, 24 witness lines all `nvcomp`, 24 MRC/24 STAR/24 EPS/24 log
plus the joint STAR (the earlier "one witness line" was my progress print slicing the list to its first element).

Repair (tooling only, fixed contract unchanged: 24 movies, 24 MRC, 25 STAR): `c1_tutorial24.py lane-hash` compares F-fresh with the retained baseline by (1) validating the fresh tree with the comparator
(self-comparison, which also yields its hashes), (2) requiring the retained comparator report to be a complete validated PASS whose 24 MRC hash triples satisfy base == candidate, (3) requiring
every fresh MRC header/extended/payload hash to equal the retained hash, and (4) requiring the 25 fresh STAR files to equal the retained STAR files after output-root normalization. Missing, malformed
or inconsistent inputs are INVALID, never identity. Attribution still requires the lane control IDENTICAL. No comparison between fresh arms changed.
