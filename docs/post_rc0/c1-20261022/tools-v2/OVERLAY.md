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
