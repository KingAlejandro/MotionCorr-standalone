# `--max_io_threads` probe, same VM and input as the baseline profile (26 October 2026)

Smallest follow-up to [baseline-profile-20261026](../baseline-profile-20261026/README.md): does the existing `--max_io_threads` flag change the measured `host read movie` phase and the whole job? Plan frozen before any timing: [IO_THREADS_PLAN.md](IO_THREADS_PLAN.md) (sha256 in `evidence/FROZEN.sha256`, 14:26:45Z; series started after). No code, default or acceptance-packet change; **C1 M1 stays held; A13 and K269-CUDA FAIL dispositions unchanged**; no qualification rerun.

## Pins and receipts

Source `e77a51a220cb0d91f4ac3c7fac211876d0c6833f` (clean); binary `build-cuda/motioncorr` `34e76812…d3535a` (no rebuild); input K269 `dose1-s01` (movie `3b6126ef…`, receipt `27d9a55b…`, STAR `ba3a39e5…`), all verified by the script before the first run ([pins.txt](evidence/logs/pins.txt)). GPU3 `GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d`, whole chain `taskset -c 96-103`, payload 96-101 `--j 6` (verified per run), kit and monitor on 102-103. GPU3 correctness lock and bench lock taken with `flock -n` and held throughout ([locks.txt](evidence/logs/locks.txt)); both free afterwards. C1 health PASS before and after; no Xid scan, no sudo; no other process touched. Window 112.8 s (timed series 67.3 s). Scratch 1.1 GB (retained outside Git, [retrieval-index.txt](retrieval-index.txt), 300 files). Route: `--ingest float` for all 17 processes (witness `movie.mrcs float` each), all other options identical to the baseline profile except `--max_io_threads` (baseline arm: flag absent, n_io_threads = 6).

Source scope (read-only): the cap reaches the host read OpenMP loop, the compressed-MRC reader and the session-ingest call (`motioncorr_runner.cpp` :2095-2100, :2562, :2142, :2324). With a float MRC on the float route only the host read loop is reached; other routes are not covered.

## Unprofiled timed runs (fixed order; kit `run_once`, process start to exit)

| # | cap | wall s | | # | cap | wall s |
|---|---|---|---|---|---|---|
| W (warmup) | 6 | 2.799 | | T07 | 2 | 4.215 |
| T01 | 6 | 2.734 | | T08 | 6 | 2.662 |
| T02 | 1 | 6.169 | | T09 | 6 | 2.729 |
| T03 | 1 | 6.042 | | T10 | 4 | 2.936 |
| T04 | 6 | 2.722 | | T11 | 4 | 2.947 |
| T05 | 6 | 2.693 | | T12 | 6 | 2.714 |
| T06 | 2 | 4.179 | | | | |

Observed AA (same configuration back to back): baseline T04-T05 1.0%, T08-T09 2.5%; cap1 2.1%, cap2 0.9%, cap4 0.4%; maximum 2.5%. Baseline range over the six timed baseline runs 2.662-2.734 s (2.7% of the minimum). These are descriptive observations of this series, not a calibrated resolution bound.

| variant | mean wall s | block-baseline mean s | pair ratio | both runs on the same side of both adjacent baselines |
|---|---|---|---|---|
| cap 1 | 6.105 | 2.728 | **2.24** | yes |
| cap 2 | 4.197 | 2.678 | **1.57** | yes |
| cap 4 | 2.941 | 2.722 | **1.08** | yes |

Peak RSS 2.81-2.83 GiB in every process.

## Built-in profile samples (after all timings; one sample per cap; not mixed with the timed runs)

| cap | read phase ms | share of movie | main-thread CPU in phase ms | main-thread minor faults | gain and sum ms | teardown ms | movie wall ms |
|---|---|---|---|---|---|---|---|
| 1 | 4392 | 80% | 4391 | 1,318,868 | 365 | 315 | 5494 |
| 2 | 2805 | 74% | 2722 | 671,830 | 243 | 308 | 3785 |
| 4 | 1568 | 62% | 1466 | 344,114 | 224 | 316 | 2538 |
| 6 (flagged) | 1288 | 56% | 1047 | 229,424 | 242 | 334 | 2285 |

The cap-6 sample was **flagged by the kit (foreign CPU on the payload lane, 0.35 cores)**; host load1 rose to 3.3 near the end of the window, with no foreign GPU process. Its timing claim is dropped per the plan; its stage values are shown for completeness and the direction check was repeated against the earlier baseline P1 read phase (1313.2 ms, other window, same configuration): same direction, caps 1/2/4 read-phase ratios 3.35/2.14/1.19 against it. The 16 other processes carry no flag. Process-wide minor faults are about 1.4-1.5 million at every cap.

## Checks (all 17 processes)

Exit 0; 14 published files equal to the baseline inventory; MRC sum finite and non-constant; witness `movie.mrcs float`; kit identity comparison against T01: **identical for every cap** (no differences to retain); no foreign GPU process in the monitor (one GPU UUID, 17 PIDs). Analysis: [iothreads-results.json](iothreads-results.json), `analyze_iothreads.py`.

## Result against the plan

Per the predeclared rules the hypothesis (read concurrency materially affects the read phase and the whole job under a warm cache) is **supported for caps 1, 2 and 4**: each variant's two runs repeat on the same side of both adjacent baselines, its whole-job deviation (+124%, +57%, +8%) exceeds the largest observed AA difference (2.5%), and the read-phase change has the same direction; the read phase is monotone in the cap (4392 > 2805 > 1568 > 1288 ms). All variants are slower than the default; nothing here is a speedup, an optimal cap or a case for a default change, and a cap above `--j` is not meaningful. The four profile samples are single samples.

What it does not resolve: why. At cap 1 the reading thread's CPU time (4391 ms) equals the phase wall (4392 ms), so in this warm-cache state the thread is on-CPU for the whole phase rather than blocked, but whether that CPU time is allocation and first touch, the page buffer, the `fread` copy, the float copy or file open per frame is **unresolved** (the phase encloses all of them, see the amendment in the baseline README). `gain and sum` is also higher in the cap-1 sample (365 vs about 225-245 ms); one sample, not interpreted.

UNRUN: cold cache, other formats and routes (nvCOMP, TIFF, compressed MRC), worker layouts, other CPU counts, caps above 6.
