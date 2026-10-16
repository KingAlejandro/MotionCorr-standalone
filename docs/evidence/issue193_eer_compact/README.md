# #193: EER on the compact uint16 ingest route (4GPUs, A100, 8-CPU lane)

Base: main `0ac2726a` (includes #197, the resident patch retry). Candidate: `a86a334c` (the same code change rebased onto it). Both Release `-O3`,
CUDA 12.8, nvCOMP 5.3.0.16, built from `git archive` into `/dev/shm`. Config L (`--patch_x 5 --patch_y 5`), options from #191, `--gpu 0 --j 8`,
`taskset -c 96-103`, GPU0 by UUID, bench and gpu0 locks held by `mcprof`. Inputs: the SHA-256 values in #191 `input-verify.json` (copies in tmpfs).
Movies used: Falcon 3 x2, Falcon 4 x2, 12963 x1 (+ gain).

`compare-<family>.md` are the `mcprof compare` reports (6 pairs, 3 profile passes). Product identity passes in all three.

| family | process wall base -> cand (s) | verdict | peak RSS base -> cand (MiB) |
|---|---|---|---|
| Falcon 4 (144 fr) | 25.780 -> 20.821 | resolved faster, -4.95 s, 6/6 pairs | 12296 -> 7687 |
| Falcon 3 (58 fr) | 12.549 -> 10.337 | resolved faster, -2.31 s, 6/6 pairs | 5261 -> 3416 |
| 12963 (gain) | 5.250 -> 4.605 | resolved faster, -0.64 s, 6/6 pairs | 3720 -> 2358 |

Stages, steady-movie median over the 3 profile passes, base -> cand (ms):

| family | host read movie | gain and sum | movie teardown | global fft | patch alignment |
|---|---|---|---|---|---|
| Falcon 4 | 9893 -> 8357 | 964 -> 562 | 1322 -> 325 | 53 -> 558 | 137 -> 138 |
| Falcon 3 | 4163 -> 3454 | 333 -> 227 | 540 -> 138 | 21 -> 231 | 61 -> 61 |
| 12963 | 3131 -> 2727 | 228 -> 130 | 385 -> 104 | 14 -> 152 | 181 -> 178 |

`global fft` grows because the compact staging is released there (munmap of the native movie), which the float path does at teardown.
Movie 0 `patch alignment` (profile pass 1): Falcon 3 346 -> 351 ms, 12963 186 -> 179 ms, so the non-converging-patch retry no longer costs more in the compact arm.

`negative-control-pins-ctest.txt` is from the earlier run of the same code change on main `116eb04a` (candidate `eeb7ccf5`): a build with +1 on one expanded
sample fails identity (`mcprof compare` exit 2), `--ingest float` and `--ingest compact` on Falcon 3 give products identical to base, and ctest is 83/84
(`CiFailClosedControls` fails only because the tree was staged with `git archive`). These were not re-run on the rebased head.
