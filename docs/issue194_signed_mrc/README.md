# #194: native staging for raw integer MRC movies

Candidate `ae25a714` against main `116eb04a`, 4GPUs A100 (GPU-eddb42fe, lane 96-103, `--j 8`), Release, CUDA 12.8, nvCOMP 5.3. Inputs in tmpfs, linked as `.mrcs`. Config L (no patches).

Options: `--use_own --dose_weighting --dose_per_frame 1.0 --bfactor 150 --seed 1 --expected_frames <8|59> --gpu 0 --j 8 --ingest_witness <file>`; `mcprof compare main cand --pairs 8` (1 warmup), two movies per run.

| input | SHA-256 |
|---|---|
| EMPIAR-10164 `data/frames/TS_01_000_0.0.mrc` (mode 0) | 117c3031…45039 |
| EMPIAR-10164 `data/frames/TS_01_020_30.0.mrc` | e6780acb…2029d |
| EMPIAR-10216 `..._1739_Fractions.mrc` (mode 1) | f399bd30…23a56 |
| EMPIAR-10216 `..._1742_Fractions.mrc` | c3b841e9…65ca1 |

Hashes match the PR #191 list. Full values are in `compare-*-report.md` provenance and PR #191.

| family | identity (12 files, 2 MRC) | wall main → cand, median | paired B-A (8 pairs) | peak RSS main → cand |
|---|---|---|---|---|
| 10164, 8-bit, 8 fr | PASS | 2.974 → 2.346 s | -0.629 s (-21.2%), resolved | 2302 → 1123 MiB |
| 10216, int16, 59 fr | PASS | 4.540 → 3.438 s | -1.120 s (-24.7%), resolved | 4070 → 2176 MiB |

Witness: cand wrote `compact` for every movie, main wrote `float`. Identity is checked on round 1 only (mcprof's rule). Reports are unprofiled wall; 4GPUs was shared (foreign CPU on the lane <= 0.01 cores).

`ctest-full-summary.txt`: 84 of 85 pass. `CiFailClosedControls` fails on this `git archive` tree (no `.git`: test_6 expects a different message) and fails identically when run from the main source tree.
