# Response to review R4 (cpu1 at 3751bd05)

`REVIEW-R4.md` is the verbatim report from
`/tmp/motioncorr-guard264-cpu-review-r4-20261022/REVIEW.md`, sha256
`ec5c10ec0938c36a59d403bb1783243faa2fb2748f941fe7be03e7ec3477d2b2`.

- **F1 accepted; option 2, as adopted by the parent.** `check_sources.py` compares the `SOURCES.txt` text, not
  the live trees. `FROZEN-CPU1.md` therefore overstates "checked by `check_sources.py` before any build"
  for `src-base` and the three overlay trees. That file is frozen and is not edited. Any claim from cpu1
  must say "setup-time `SOURCES.txt` plus live-tree receipt and parent live check". The live receipt
  (`SETUP-RECEIPT.md`, `live-receipt.txt`) recomputes HEAD, diff, status, runner and helper on all five
  trees, and they equal EXPECT. The parent repeats that check independently before GO and compares
  the build-log `source` lines afterwards. No tool change, so no new freeze or review.
- **F2 accepted as a mandatory parent post-run check:** receipt string versus `RUN.json` env for 21 rows;
  one binary hash per arm, equal to its build receipt; three distinct arm hashes.
- **F3:**
  - The bundle was made as `git bundle create … HEAD`, and a dry run reproduced the recorded diff hashes.
  - Live affinity (`taskset -pc`) is to be recorded at launch.
  - The 8 GiB cap is a start/end `du` check only; this response records that. The frozen plan is not edited.
  - The i61 probe creates the file if it is absent; it already existed.
- **Old F3/F4:** carried unchanged.

Allowed and disallowed claims are as R4 lists them. A cpu1 PASS would be a CPU-only, test-only overlay
result. It is not N3/N4 or CPU+CUDA qualification.
