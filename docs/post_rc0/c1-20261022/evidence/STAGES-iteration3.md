# Iteration 3 stage receipts (chain-i3.sh, tools packet 4facd76d, tested source e77a51a2; UTC, 22 Oct 2026)

| started | stage | finished | exit |
|---|---|---|---|
| 2026-10-22T21:24:03Z | i3-run-F-fresh-G | 2026-10-22T21:24:11Z | 0 |
| 2026-10-22T21:24:11Z | i3-lane-hash-G | 2026-10-22T21:24:14Z | 0 |
| 2026-10-22T21:24:14Z | i3-run-c1-G | 2026-10-22T21:24:20Z | 0 |
| 2026-10-22T21:24:20Z | i3-cmp-F-c1-G | 2026-10-22T21:24:24Z | 1 |
| 2026-10-22T21:24:24Z | i3-run-N-G | 2026-10-22T21:24:30Z | 0 |
| 2026-10-22T21:24:30Z | i3-cmp-F-N-G | 2026-10-22T21:24:33Z | 1 |
| 2026-10-22T21:24:33Z | i3-run-only254-G | 2026-10-22T21:24:39Z | 0 |
| 2026-10-22T21:24:39Z | i3-cmp-F-only254-G | 2026-10-22T21:24:42Z | 1 |
| 2026-10-22T21:24:42Z | i3-run-only260-G | 2026-10-22T21:24:49Z | 0 |
| 2026-10-22T21:24:49Z | i3-cmp-F-only260-G | 2026-10-22T21:24:52Z | 1 |
| 2026-10-22T21:24:52Z | i3-run-only270-G | 2026-10-22T21:24:58Z | 0 |
| 2026-10-22T21:24:58Z | i3-cmp-F-only270-G | 2026-10-22T21:25:02Z | 0 |
| 2026-10-22T21:25:02Z | i3-cmp-N-c1-G | 2026-10-22T21:25:05Z | 0 |
| 2026-10-22T21:25:05Z | i3-cmp-only254-c1-G | 2026-10-22T21:25:08Z | 1 |
| 2026-10-22T21:25:08Z | i3-cmp-only260-c1-G | 2026-10-22T21:25:11Z | 1 |
| 2026-10-22T21:25:11Z | i3-cmp-only270-c1-G | 2026-10-22T21:25:15Z | 1 |
| 2026-10-22T21:25:15Z | i3-attribute-G | 2026-10-22T21:25:15Z | 0 |
| 2026-10-22T21:25:15Z | i3-run-F-fresh-L | 2026-10-22T21:25:22Z | 0 |
| 2026-10-22T21:25:22Z | i3-lane-hash-L | 2026-10-22T21:25:26Z | 0 |
| 2026-10-22T21:25:26Z | i3-run-c1-L | 2026-10-22T21:25:33Z | 0 |
| 2026-10-22T21:25:33Z | i3-cmp-F-c1-L | 2026-10-22T21:25:36Z | 1 |
| 2026-10-22T21:25:36Z | i3-run-N-L | 2026-10-22T21:25:44Z | 0 |
| 2026-10-22T21:25:44Z | i3-cmp-F-N-L | 2026-10-22T21:25:47Z | 1 |
| 2026-10-22T21:25:47Z | i3-run-only254-L | 2026-10-22T21:25:54Z | 0 |
| 2026-10-22T21:25:54Z | i3-cmp-F-only254-L | 2026-10-22T21:25:57Z | 1 |
| 2026-10-22T21:25:57Z | i3-run-only260-L | 2026-10-22T21:25:57Z | 1 |

Allowed exits: lane-hash, N-vs-C1 and attribution only 0; other comparisons 0 or 1 (valid IDENTICAL/DIFFERENT); everything else only 0. Exit 1 on a `cmp-*` stage is a valid DIFFERENT result. The chain stopped at `i3-run-only260-L` (exit 1): see ITERATION3_DIAGNOSIS.md.
