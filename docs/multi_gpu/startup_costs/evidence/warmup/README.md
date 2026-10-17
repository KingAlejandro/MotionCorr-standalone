# Evidence: context warm-up and registered pinning together (#53 steps 1+2)

Recorded 2026-10-14/15 on `perf/cuda-warmup-thread`. That branch is not merged
(the decision is on #53). Arms: main `116eb04a`; c1 = step 1 `6d9527a9`;
c2 = steps 1+2 `351db93d`, binary-equal to the final head `c2fcb409`; c3 = c2
plus a dropped dose-weighting preload.

| Path | Content |
|---|---|
| `4gpus-fixed/` | Fixed-cost series: 8 rounds at 12 and 96 movies, every run profiled. `fixed_ab.sh`, `analyse.txt`, `paired.txt`, `profiles.tgz`. `slow_rounds.py`/`slow_rounds.txt` re-read the profiles for where slow rounds spent their time. |
| `kit24/` | `mcprof compare` main vs c2, 24 movies, 10 of 12 pairs clean plus 3 profiled passes (`report.md`, `raw.tgz`): −55 ms, not resolved. |
| `scarf/` | `run_dataset.py` A/B on gn0005, c2 vs main (`ab-3618965.out`, `warmab.json`): 1×8 −118 ms (12/12), 4×8 no effect. `position.txt` gives the run-order breakdown. |
| `identity/` | Identity matrix, 9 rows plus 2 controls: `summary-c2.txt` on the c2 binary, `summary-c3.txt` on c3. |
| `ctest/` | Full ctest at `c2fcb409` (the log labels it c3; it was built from `src-c4`, which held `c2fcb409`): CUDA 92/94, CPU 51/52. The failures are `CiFailClosedControls`, because the staged tree has no `.git`, and `MultiGpuScheduling`, which missed a 0.25 s timing threshold once in launcher code this branch does not touch. |

Step 2 measured alone is in [`../pinned_register/`](../pinned_register/README.md).
